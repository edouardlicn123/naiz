/*
 * hal_irq.c — Interrupt-driven BGM pump (devdoc 164 phase 1, OPNA Timer-B).
 *
 * Why this exists
 * ---------------
 * The engine pumps audio co-operatively: audio_tick() runs only from the
 * frame pump, so any long CPU-bound pass (menu redraw, portrait decode, a
 * blocking vblank sync) starves the BGM scheduler and the music stalls -- the
 * "M1 time debt" of devdoc 163.  The original PC-98 music drivers did not
 * have this problem because a resident driver plus a hardware timer ticked
 * the music independently of the game loop (F05).  This file reproduces that
 * model with the OPNA's Timer-B.
 *
 * Which IRQ line (devdoc 164 §四)
 * -------------------------------
 * The 86-board's OPNA timer IRQ is strapped in hardware, and the two known
 * sources disagree: QEMU's pc98-opna maps it to IRQ 3 (master, F04 §6) while
 * DOSBox-X/Blackbird put it on IRQ 12 (slave, G09 §3).  NP2kai -- the oracle
 * this project actually validates on -- resolves to IRQ 12: its default
 * snd86opt=0x7f yields nIrq=0xD0, and opntimer's s_irqtable[0xD0>>6]=
 * s_irqtable[3]=0x0c (sound/opntimer.c:13, sound/board86.c:150).  So this
 * file tries the slave line first and falls back to the master line: whichever
 * DPMI reports a usable protected-mode vector is the one we hook.  The EOI
 * sequence is slave-then-master either way, which is correct for both.
 *
 * Compile-gated by NAIZ_BGM_IRQ (default 0): the default build compiles this
 * file to nothing and the engine's co-operative pump is byte-for-byte
 * unchanged.  Enable with `make -C core EXTRA_DEFS=-DNAIZ_BGM_IRQ=1`.
 *
 * Toolchain note (devdoc 164 §三): Open Watcom ships no dpmi.h, so the vector
 * hook goes through INT 31h directly via int386() -- the same channel the
 * engine already uses for INT 21h/INT 18h.  Because that path is unverified
 * on this toolchain, hal_bgm_irq_init() reports failure instead of assuming
 * success, and a failed install leaves the co-operative pump running.
 *
 * Port I/O for the timer and the PIC lives here: per AGENTS §5.1 outb()/inb()
 * may only appear in core/plat/, and this is that place for the IRQ path.
 */
#include "hal.h"
#include "pc98.h"
#include "audio.h"    /* audio_tick(): engine pump entry (plat->engine precedent: cursor.h) */
#include <i86.h>
#include <dos.h>      /* _dos_setvect()/_dos_getvect() */

#if NAIZ_BGM_IRQ

/* --- OPNA Timer-B registers (F04 §2/§4) ----------------------------------
 * One Timer-B step is 2304 master clocks: tB = 2304 * (256 - NB) / phiM.
 * The manual's period formula counts phiM/2 cycles, so its 1152 is NOT a
 * master-clock count -- treating it as one is exactly how the old 129-unit
 * constant was derived (devdocs/168, docs/refdocs/F07 §3).  At the 86-board
 * crystal phiM = 7.9872 MHz with NB=200 a step is 16.154ms => ~61.9Hz:
 * about 2x the ~28Hz main loop, enough to decouple the beat.  The prescaler
 * ($2D-$2F) is deliberately never touched: changing it retimes FM/SSG pitch
 * and the timer together (F04 §8.3, high-risk). */
#define FM_REG_ADDR      0x0188
#define FM_REG_DATA      0x018A
#define FM_TIMER_B       0x26   /* 8-bit reload */
#define FM_TIMER_CTRL    0x27   /* D5=RESET B, D3=ENABLE B, D1=LOAD B */
#define FM_IRQ_ENABLE    0x29   /* D1=EN_TB (timer IRQ enable) */

#define FM_TIMER_B_NB    200

/* Timer-B period at phiM = 7.9872 MHz: tB = 2304 * (256 - NB) / phiM
 *   = 2304 * 56 / 7.9872e6 = 16.154 ms.
 * The ISR advances the virtual clock by this known delta (devdoc 165 定点时基):
 * the hardware timer IS the time base, so no DOS clock read is needed.
 * vclock stores time in 1/16 ms units, so 16.154 ms -> 258 units (258.46
 * truncated: -0.18% against a real 86 board, -0.02% under NP2kai).
 * Never go back to 129 -- that is the half-period value (devdocs/168). */
#define BGM_TIMER_B_UNITS 258

#define FM_CTRL_LOAD_B   0x02   /* D1: start Timer B */
#define FM_CTRL_ENABLE_B 0x08   /* D3: overflow sets the flag / asserts IRQ */
#define FM_CTRL_RESET_B  0x20   /* D5: clear the Timer-B flag (self-clearing) */

/* Two candidate IRQ lines for the 86-board timer (devdoc 164 §四).  The
 * slave line (IRQ 12) is tried first because NP2kai -- this project's oracle
 * -- uses it; the master line (IRQ 3) is the QEMU/F04 default kept as a
 * fallback.  PC-98 vector = base + IRQ-within-PIC: master base 0x08 (IRQ 3 ->
 * INT 0Bh), slave base 0x10 (IRQ 12 -> IRQ 4 on the slave -> INT 14h). */
#define BGM_IRQ_LINE_COUNT 2

typedef struct {
    unsigned char vector;    /* real-mode/PM interrupt vector number */
    unsigned char imr_port;  /* the PIC IMR that gates this line */
    unsigned char imr_bit;   /* the bit to clear in that IMR */
    const char   *name;      /* for logging */
} BgmIrqLine;

static const BgmIrqLine g_irq_lines[BGM_IRQ_LINE_COUNT] = {
    { 0x14, PIC1_IMR, 0x10, "IRQ12 (slave)" },  /* NP2kai default (this oracle) */
    { 0x0B, PIC0_IMR, 0x08, "IRQ3 (master)" },  /* QEMU/F04 default (fallback) */
};

static int g_irq_active = 0;
static int g_irq_line = -1;          /* index of the line we actually hooked */

/* ISR heartbeat (devdoc 165): incremented in the handler, read from the frame
 * path.  This is the only reliable proof the Timer-B actually fires -- the ISR
 * itself must not log (hal_logf is not ISR-safe), so the count is sampled by
 * the frame pump instead.  volatile: written in the ISR, read in the main loop. */
static volatile unsigned long g_isr_ticks = 0;

/*
 * The handler.  Bounded and allocation-free, and -- critically -- free of any
 * construct a hardware ISR may not use (devdoc 165 §四 B1-B4): no DOS/BIOS
 * call (int 21h is not reentrant), no floating point (Watcom's __interrupt
 * does not preserve the x87 stack, and pow() is a libm call), no hal_logf
 * (blocking serial I/O), no free() (the heap is not reentrant).  All four were
 * present in the first version of this handler and locked the machine a few
 * ticks in.
 *
 * Watcom's `__interrupt` saves/restores the full register set and iret's; the
 * handler takes no arguments.
 */
/* Set by the ISR handler itself; the engine reads it through the HAL
 * accessor hal_bgm_irq_in_isr() (devdoc 166). */
static volatile int g_bgm_irq_in_isr_flag;

static void bgm_irq_set_in_isr(int on)
{
    g_bgm_irq_in_isr_flag = on ? 1 : 0;
}

int hal_bgm_irq_in_isr(void)
{
    return g_bgm_irq_in_isr_flag;
}

static void __interrupt __far bgm_irq_handler(void)
{
    bgm_irq_set_in_isr(1);
    g_isr_ticks++;
    /* Fixed-step hardware time base, then the ISR-safe audio core: One capped
     * batch of BGM events + a PCM FIFO top-up, all via outb()/inb(). */
    hal_wallclock_fixed_advance(BGM_TIMER_B_UNITS);
    audio_tick_isr(BGM_TIMER_B_UNITS);  /* stage 3: fixed-unit pump (devdoc 168) */
    bgm_irq_set_in_isr(0);

    /* Clear the OPNA Timer-B flag then EOI.  The write must keep BOTH D1
     * (LOAD B) and D3 (ENABLE B) set: writing $27 with D1 clear makes
     * opna_settimer drop the Timer-B event (it stops), and with D3 clear the
     * NP2kai model stops raising the overflow flag / IRQ after one tick.  So
     * issue RESET B | ENABLE B | LOAD B in a single write, matching how a real
     * driver acknowledges the timer. */
    outb(FM_REG_ADDR, FM_TIMER_CTRL);
    outb(FM_REG_DATA,
         (unsigned char)(FM_CTRL_RESET_B | FM_CTRL_ENABLE_B | FM_CTRL_LOAD_B));
    outb(PIC1_CMD, PIC_EOI);
    outb(PIC0_CMD, PIC_EOI);
}

/* INT 31h wrapper.  Returns the offset part of a DPMI get-vector result
 * (CX:EDX = sel:off) so callers can tell a real handler from an empty one. */
static unsigned long dpmi_get_pm_vector(int vec, unsigned short *sel_out)
{
    union REGS r;
    r.x.eax = 0x0204;
    r.h.bl = (unsigned char)vec;
    r.x.ecx = 0;
    r.x.edx = 0;
    int386(0x31, &r, &r);
    if (sel_out)
        *sel_out = (unsigned short)r.x.ecx;
    return ((unsigned long)r.x.ecx << 16) | (r.x.edx & 0xFFFFUL);
}

int hal_bgm_irq_init(void)
{
    int i;

    /* Try each candidate line in priority order: the first one with a usable
     * protected-mode vector wins.  A line whose vector is empty (0:0) is not
     * a real IRQ path on this host, so we move on rather than write into the
     * dark. */
    hal_log("BGM IRQ: init enter\r\n");

    /* 快速初始化：限制每条线的检查时间，避免模拟器挂起 */
    for (i = 0; i < BGM_IRQ_LINE_COUNT; i++) {
        const BgmIrqLine *line = &g_irq_lines[i];
        unsigned short sel = 0;
        unsigned long off;

        hal_logf("BGM IRQ: probing INT %02Xh (%s)\r\n",
                 line->vector, line->name);
        off = dpmi_get_pm_vector(line->vector, &sel);
        hal_logf("BGM IRQ: 0204 -> %lx:%04x\r\n", off, (unsigned)sel);
        if (off == 0 && sel == 0) {
            hal_logf("BGM IRQ: no PM vector for INT %02Xh (%s); trying next\r\n",
                     line->vector, line->name);
            continue;
        }

        /* Install our handler.  In the DOS/4GW flat model a far code pointer
         * is a plain 32-bit offset (no real selector), so DPMI 0205's CX:EDX
         * sel:off split is wrong here -- it would pass the offset's high word
         * as a bogus selector and fault on the first IRQ.  _dos_setvect() takes
         * the handler directly and, for the auto-passup range 8-2Eh (INT 14h
         * qualifies), DOS/4GW routes both PM and RM to it (DOS/4GW FAQ 4a). */
        hal_logf("BGM IRQ: _dos_setvect(INT %02Xh) handler=%lx\r\n",
                 line->vector,
                 (unsigned long)(void (__interrupt __far *)())bgm_irq_handler);
        _dos_setvect(line->vector,
                     (void (_WCINTERRUPT _WCFAR *)())bgm_irq_handler);
        hal_logf("BGM IRQ: setvect done\r\n");

        g_irq_line = i;
        break;
    }

    if (g_irq_line < 0) {
        hal_log("BGM IRQ: no usable IRQ line; fallback to co-operative pump\r\n");
        return 0;
    }

    /* Program Timer-B FIRST, while the line is still masked: reload value, then
     * LOAD + ENABLE, then enable its IRQ at the chip ($29 D1).  $29 bit7 (SCH=6
     * voices) is re-asserted here; only the timer-enable bit is added. */
    hal_log("BGM IRQ: programming Timer-B\r\n");
    outb(FM_REG_ADDR, FM_TIMER_B);
    outb(FM_REG_DATA, (unsigned char)(FM_TIMER_B_NB));
    outb(FM_REG_ADDR, FM_TIMER_CTRL);
    outb(FM_REG_DATA, (unsigned char)(FM_CTRL_LOAD_B | FM_CTRL_ENABLE_B));
    outb(FM_REG_ADDR, FM_IRQ_ENABLE);
    outb(FM_REG_DATA, (unsigned char)(0x80 | 0x02));  /* SCH + EN_TB */

    /* Publish active state BEFORE unmasking: if the first IRQ lands the instant
     * the mask drops, the frame pump must already see the ISR as the owner. */
    g_irq_active = 1;

    /* Unmask the chosen line last (read-modify-write the right PIC's IMR). */
    {
        const BgmIrqLine *line = &g_irq_lines[g_irq_line];
        unsigned char imr = (unsigned char)inb(line->imr_port);
        hal_logf("BGM IRQ: unmask %s (imr %02x -> %02x)\r\n",
                 line->name, (unsigned)imr, (unsigned)(imr & ~line->imr_bit));
        outb(line->imr_port, (unsigned char)(imr & ~line->imr_bit));
    }

    hal_logf("BGM IRQ: Timer-B installed (NB=%d, ~61.9Hz, %s)\r\n",
             FM_TIMER_B_NB, g_irq_lines[g_irq_line].name);
    return 1;
}

int hal_bgm_irq_active(void)
{
    return g_irq_active;
}

unsigned long hal_bgm_irq_ticks(void)
{
    return g_isr_ticks;
}

void hal_bgm_irq_shutdown(void)
{
    if (!g_irq_active)
        return;
    /* Stop Timer-B (drop LOAD B), then mask the line we hooked again. */
    outb(FM_REG_ADDR, FM_TIMER_CTRL);
    outb(FM_REG_DATA, FM_CTRL_RESET_B);
    if (g_irq_line >= 0) {
        const BgmIrqLine *line = &g_irq_lines[g_irq_line];
        unsigned char imr = (unsigned char)inb(line->imr_port);
        outb(line->imr_port, (unsigned char)(imr | line->imr_bit));
    }
    g_irq_active = 0;
}

#endif /* NAIZ_BGM_IRQ */
