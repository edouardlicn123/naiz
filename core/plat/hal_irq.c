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
 * Which IRQ line (devdoc 164 §4)
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
 * Toolchain note (devdoc 164 §3): Open Watcom ships no dpmi.h, so the vector
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
 * The ISR advances the virtual clock by this known delta (devdoc 165 fixed time base):
 * the hardware timer IS the time base, so no DOS clock read is needed.
 * vclock stores time in 1/16 ms units, so 16.154 ms -> 258 units (258.46
 * truncated: -0.18% against a real 86 board, -0.02% under NP2kai).
 * Never go back to 129 -- that is the half-period value (devdocs/168).
 * The constant itself lives in hal.h now (devdoc 177): the engine's split
 * drain steps by one period and must agree with the handler. */

#define FM_CTRL_LOAD_B   0x02   /* D1: start Timer B */
#define FM_CTRL_ENABLE_B 0x08   /* D3: overflow sets the flag / asserts IRQ */
#define FM_CTRL_RESET_B  0x20   /* D5: clear the Timer-B flag (self-clearing) */

/* Candidate IRQ lines for the 86-board timer (devdoc 164 §4, devdoc 174).
 *
 * The line is strapped by the board's DIP switch, and the two reference
 * sources disagree -- QEMU's pc98-opna maps it to IRQ 3 (master, F04 §6) while
 * DOSBox-X/Blackbird put it on IRQ 12 (slave, G09 §3).  NP2kai resolves it
 * from the DIP value (cbus/board86.c): nIrq = 0x10 | ((opt&4)<<5) | ((opt&8)<<3),
 * and sound/opntimer.c::opna_timer() then indexes s_irqtable[4] =
 * {03h, 0Dh, 0Ah, 0Ch} with nIrq>>6 -- four possible strappings, four vectors:
 *
 *   INT 0Bh <- s_irqtable[0] = 03h  master IRQ3
 *   INT 15h <- s_irqtable[1] = 0Dh  slave  IRQ5
 *   INT 12h <- s_irqtable[2] = 0Ah  slave  IRQ2
 *   INT 14h <- s_irqtable[3] = 0Ch  slave  IRQ4   (NP2kai's opt=7Fh default)
 *
 * PC-98 vector = PIC vector base + line: master base 08h, slave base 10h.  The
 * engine cannot read the DIP switch, so it hooks one candidate at a time and
 * watches the tick counter (see hal_bgm_irq_probe_step): a hooked timer fires
 * ~62 times a second, so a handful of frames without a tick is a verdict.  The
 * observed line is INT 14h on this project's build (devdocs/168). */
#define BGM_IRQ_LINE_COUNT 4

typedef struct {
    unsigned char vector;    /* real-mode/PM interrupt vector number */
    unsigned char imr_port;  /* the PIC IMR that gates this line */
    unsigned char imr_bit;   /* the bit to clear in that IMR */
    const char   *name;      /* for logging */
} BgmIrqLine;

static const BgmIrqLine g_irq_lines[BGM_IRQ_LINE_COUNT] = {
    { 0x14, PIC1_IMR, 0x10, "IRQ12 (slave 4)" },  /* observed here (devdocs/168) */
    { 0x0B, PIC0_IMR, 0x08, "IRQ3 (master)" },    /* QEMU/F04 default */
    { 0x15, PIC1_IMR, 0x20, "IRQ13 (slave 5)" },
    { 0x12, PIC1_IMR, 0x04, "IRQ10 (slave 2)" },
};

/* devdoc 174 candidate scan.  One candidate is hooked at a time; ownership of
 * the clock/audio pump moves to the ISR only after that candidate has actually
 * ticked, so a wrong guess costs a fraction of a second of co-operative
 * pumping (which keeps running throughout) instead of silence.  Eight frames
 * is ~0.4 s under NP2kai's ~20 Hz pass rate and ~0.13 s at 60 Hz, i.e. ~25 or
 * ~8 Timer-B ticks -- MIN_TICKS rejects a stray edge from an unrelated line. */
/* 199E measurement builds can override with -D: with per-command serial
 * logging off the frame rate is far above 20Hz, so 8 frames only collect
 * ~2 ticks and the probe misjudges every candidate as silent.  Hardware
 * builds keep 8/6. */
#ifndef BGM_IRQ_PROBE_FRAMES
#define BGM_IRQ_PROBE_FRAMES   8
#endif
#ifndef BGM_IRQ_PROBE_MIN_TICKS
#define BGM_IRQ_PROBE_MIN_TICKS 6
#endif

/* devdoc 198: ALL three are read from the ISR handler AND written from the
 * main loop.  Without volatile, Watcom C caches the main-loop value in a
 * register and the handler's `if (g_irq_active)` branch is skipped forever
 * even after probe promoted ownership.  ISR handler still counts ticks
 * (that line happens to be unconditional), but the clock advance and unit
 * accumulation both stay dormant and audio_tick_isr_pending() reads 0. */
static volatile int g_irq_active = 0;
static volatile int g_irq_probing = 0;
static volatile int g_irq_line = -1;
static unsigned long g_probe_base_ticks = 0;
static unsigned g_probe_frames = 0;
static int g_probe_cursor = 0;       /* next candidate index to try */
static unsigned char g_irq_saved_imr = 0;
static void (_WCINTERRUPT _WCFAR *g_saved_vect[BGM_IRQ_LINE_COUNT])(void);
/* Protected-mode vector we displaced (sel:off read via DPMI 0204h before hooking).
 * DOS/32A may not mirror _dos_setvect() into the PM table, so we must save
 * + restore it explicitly via DPMI 0303h (devdoc 194 F2a). */
static unsigned short g_saved_pm_sel[BGM_IRQ_LINE_COUNT];
static unsigned long  g_saved_pm_off[BGM_IRQ_LINE_COUNT];

/* ISR heartbeat (devdoc 165): incremented in the handler, read from the frame
 * path.  This is the only reliable proof the Timer-B actually fires -- the ISR
 * itself must not log (hal_logf is not ISR-safe), so the count is sampled by
 * the frame pump instead.  volatile: written in the ISR, read in the main loop. */
static volatile unsigned long g_isr_ticks = 0;
/* Monotonic count of clock units produced by the handler (devdoc 176).  The
 * main thread keeps its own "already consumed" copy and drains the difference,
 * so no critical section is needed: an aligned 32-bit load/store is atomic on
 * this target, and a tick landing mid-drain is simply counted next time.  The
 * handler must not touch the consumer's copy -- that is exactly the
 * stack-segment hazard documented at bgm_irq_handler(). */
static volatile unsigned long g_irq_units_total = 0;

/*
 * The handler.  Bounded and allocation-free, and -- critically -- free of any
 * construct a hardware ISR may not use (devdoc 165 §4 B1-B4): no DOS/BIOS
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
    unsigned char status;

    bgm_irq_set_in_isr(1);

    /* devdoc 174: is this tick really ours?  A candidate line may be shared
     * with another board, and during the candidate scan we are hooked on a
     * line that may belong to one.  The OPNA status port ($188 read) carries
     * the Timer-B overflow flag in bit 1; anything without it is somebody
     * else's interrupt: acknowledge and leave without touching the clock. */
    status = (unsigned char)inb(FM_REG_ADDR);
    if (!(status & 0x02)) {
        bgm_irq_set_in_isr(0);
        outb(PIC1_CMD, PIC_EOI);
        outb(PIC0_CMD, PIC_EOI);
        return;
    }

    g_isr_ticks++;

    /* While the candidate scan is running the handler only counts: the
     * co-operative pump still owns the clock and the audio, and pumping here as
     * well would run the tempo at twice its rate for the duration of the probe
     * (devdoc 174). */
    if (g_irq_active) {
        /* Fixed-step hardware time base only.  The engine pump (BGM events +
         * PCM FIFO) must NOT run here: DOS/4GW delivers this IRQ on its own
         * stack segment (SS=0x00B0) while the flat data selector is DS=0x0160,
         * so any engine code that writes through a pointer to a *stack* local
         * (fmopn_reg_addr's bank/addr out-params, for one) silently writes to
         * a bogus linear address and the caller keeps a stale value -- every
         * FM register came out as address 0x00, i.e. a silent BGM, plus a
         * stray write into low memory (devdoc 176).  The handler therefore
         * touches globals only and leaves the work to audio_tick_isr_pending()
         * on the main stack. */
        hal_wallclock_fixed_advance(BGM_TIMER_B_UNITS);
        g_irq_units_total += BGM_TIMER_B_UNITS;
    }
    bgm_irq_set_in_isr(0);

    /* Clear the OPNA Timer-B flag then EOI.  Write RESET B | ENABLE B | LOAD B:
     *   D5 (RESET B) — clears the overflow flag (required, see F04)
     *   D3 (ENABLE B) — keeps Timer-B running
     *   D1 (LOAD B) — reloads counter from NB
     * Also re-assert EN_TB ($29 D1): if anything cleared it, Timer-B still
     * counts but its overflows don't assert the IRQ line, so total_hits stops
     * growing while the counter silently wraps. */
    outb(FM_REG_ADDR, FM_TIMER_CTRL);
    outb(FM_REG_DATA,
         (unsigned char)(FM_CTRL_RESET_B | FM_CTRL_ENABLE_B | FM_CTRL_LOAD_B));
    outb(FM_REG_ADDR, FM_IRQ_ENABLE);
    outb(FM_REG_DATA, (unsigned char)(0x80 | 0x02));  /* SCH + EN_TB */
    outb(PIC1_CMD, PIC_EOI);
    outb(PIC0_CMD, PIC_EOI);
}

/* INT 31h AX=0204h — Get Protected Mode Interrupt Vector.
 * Returns the current PM handler for the given vector.
 *
 * DPMI 1.0: success (carry clear) always.
 *   CX = selector (valid PM code selector)
 *   EDX = 32-bit linear offset (32-bit clients; 16-bit clients get low 16)
 *
 * Returns the full 32-bit linear address (sel << 16 | offset) so callers
 * can compare before/after hooking.  Selector is also returned via sel_out. */
static unsigned long dpmi_get_pm_vector(int vec, unsigned short *sel_out)
{
    union REGS r;
    r.x.eax = 0x0204;
    r.h.bl = (unsigned char)vec;
    r.x.ecx = 0;
    r.x.edx = 0;
    int386(0x31, &r, &r);
    if (sel_out)
        *sel_out = (unsigned short)r.x.ecx;   /* 16-bit selector */
    /* 32-bit client: EDX carries the full linear offset; CX carries the
     * selector (not offset high word — the DPMI spec is explicit).  We
     * pack them into a flat address for easy compare/print. */
    return ((unsigned long)(unsigned short)r.x.ecx << 16) | r.x.edx;
}

/* DPMI INT 31h AX=0205h — Set Protected Mode Interrupt Vector.
 * This is the correct function to hook a hardware interrupt for PM clients.
 * Unlike _dos_setvect (which on DOS/32A may only touch the RM table), this
 * writes directly into the DPMI host's PM dispatch table.
 *
 * Input: AX=0205h, BL=vector, CX=selector, EDX=32-bit offset
 * Success: carry clear, AX unchanged (0205h)
 * Failure: carry set, AX = error code (e.g. 8022h = invalid selector)
 *
 * Note: AX=0303h is *Allocate Real Mode Callback Address* — a completely
 * different function that wraps a PM procedure as an RM-callable stub.  We
 * do NOT want that here.  devdoc 194 F2a mentioned 0303h as a potential
 * option but 0205h is the canonical vector-setting service. */
static int dpmi_set_pm_vector(int vec, unsigned short sel, unsigned long off)
{
    union REGS r;
    r.x.eax = 0x0205;
    r.h.bl = (unsigned char)vec;
    r.x.ecx = (unsigned int)sel;
    r.x.edx = off;         /* full 32-bit offset for DPMI 1.0 32-bit clients */
    int386(0x31, &r, &r);
    /* DPMI 1.0: success leaves AX = 0205h, failure writes error code. */
    return (r.x.eax & 0xFFFFUL) == 0x0205;
}

/* Watcom C flat-model far function pointer layout (little-endian):
 * selector = upper 16 bits (flat code selector), offset = lower 32 bits.
 * We also accept _dos_setvect's result when the DPMI host mirrors the
 * RM table into PM (DOS/4GW auto-passup range 8-2Eh, INT 14h qualifies). */
union IrqHandlerAddr {
    void (_WCINTERRUPT _WCFAR *func)(void);
    unsigned long full;
};

/* Hook one candidate: install the handler, remember the vector it displaced,
 * then unmask that line.  Returns 0 if the line has no protected-mode vector at
 * all (not a real IRQ path on this host).
 *
 * DOS/4GW: _dos_setvect() writes the RM table and auto-passup mirrors it into
 * the PM table for INT 8-2Eh.  DPMI 0303h is AVOIDED because the flat-model
 * far pointer has no real selector (the upper 16 bits of the 32-bit offset
 * would be passed as a bogus selector and fault).
 *
 * DOS/32A: _dos_setvect() may or may not mirror into PM (not guaranteed by
 * the DPMI 1.0 spec).  We first call _dos_setvect, then READ BACK the PM
 * vector via DPMI 0204h.  If it did NOT change, we construct the handler's
 * sel:off from CS + RVA and call DPMI 0303h explicitly (devdoc 194 F2a). */
static int bgm_irq_attach(int idx)
{
    const BgmIrqLine *line = &g_irq_lines[idx];
    unsigned short sel = 0;
    unsigned long off;
    /* Did DPMI 0303h successfully set the PM vector?  Needed on detach so
     * we know whether to restore via 0303h or trust that _dos_setvect did it. */
    static int used_pm_setvect[BGM_IRQ_LINE_COUNT];

    hal_logf("BGM IRQ: probing INT %02Xh (%s)\r\n", line->vector, line->name);
    off = dpmi_get_pm_vector(line->vector, &sel);
    hal_logf("BGM IRQ: 0204 pre-hook -> %lx:%04x\r\n", off, (unsigned)sel);
    if (off == 0 && sel == 0) {
        hal_logf("BGM IRQ: no PM vector for INT %02Xh (%s); skipping\r\n",
                 line->vector, line->name);
        return 0;
    }

    /* Save displaced vectors so we can restore exactly what was there. */
    g_saved_pm_sel[idx] = sel;
    g_saved_pm_off[idx] = off;
    g_saved_vect[idx] = _dos_getvect(line->vector);

    /* Step 1: _dos_setvect sets the RM table.  DOS/4GW auto-passup (8-2Eh)
     * mirrors this into PM; DOS/32A does not guarantee it. */
    _dos_setvect(line->vector,
                 (void (_WCINTERRUPT _WCFAR *)())bgm_irq_handler);
    used_pm_setvect[idx] = 0;

    /* Step 2: verify — re-read the PM vector.  If _dos_setvect was mirrored,
     * great; otherwise we set it explicitly via DPMI 0303h. */
    {
        unsigned short pm_sel = 0;
        unsigned long pm_off = dpmi_get_pm_vector(line->vector, &pm_sel);
        hal_logf("BGM IRQ: 0204 post-_dos_setvect -> %lx:%04x\r\n",
                 pm_off, (unsigned)pm_sel);

        if (pm_off == g_saved_pm_off[idx] && pm_sel == g_saved_pm_sel[idx]) {
            /* PM vector still points to the original handler — we need 0303h. */
            unsigned short code_sel;
            /* CS is the flat code selector in DOS/4GW and DOS/32A flat models.
             * bgm_irq_handler's RVA is &bgm_irq_handler (32-bit flat offset). */
            __asm { mov code_sel, cs }
            hal_logf("BGM IRQ: PM vector unchanged by _dos_setvect; "
                     "DPMI 0303h sel=%04x handler=%lx\r\n",
                     (unsigned)code_sel,
                     (unsigned long)&bgm_irq_handler);
            if (!dpmi_set_pm_vector(line->vector,
                                    code_sel,
                                    (unsigned long)&bgm_irq_handler)) {
                hal_log("BGM IRQ: DPMI 0303h FAILED; IRQ may not fire on PM path\r\n");
            } else {
                hal_log("BGM IRQ: DPMI 0303h OK\r\n");
                used_pm_setvect[idx] = 1;
            }
        } else {
            hal_logf("BGM IRQ: PM vector was mirrored by _dos_setvect "
                     "(auto-passup); no DPMI 0303h needed\r\n");
        }
    }

    g_irq_saved_imr = (unsigned char)inb(line->imr_port);
    hal_logf("BGM IRQ: unmask %s (imr %02x -> %02x)\r\n",
             line->name, (unsigned)g_irq_saved_imr,
             (unsigned)(g_irq_saved_imr & ~line->imr_bit));
    outb(line->imr_port, (unsigned char)(g_irq_saved_imr & ~line->imr_bit));

    g_irq_line = idx;
    return 1;
}

/* Undo bgm_irq_attach(): mask the line again, restore the displaced
 * vectors (both RM via _dos_setvect and PM via DPMI 0303h if we set it
 * explicitly). */
static void bgm_irq_detach(void)
{
    if (g_irq_line < 0)
        return;
    {
        int idx = g_irq_line;
        const BgmIrqLine *line = &g_irq_lines[idx];
        outb(line->imr_port, g_irq_saved_imr);
        _dos_setvect(line->vector, g_saved_vect[idx]);
        dpmi_set_pm_vector(line->vector, g_saved_pm_sel[idx], g_saved_pm_off[idx]);
    }
    g_irq_line = -1;
}

/* Attach the next candidate that has a usable protected-mode vector.  Returns 0
 * once the list is exhausted; on success the candidate is hooked and the probe
 * window restarts against it. */
static int bgm_irq_probe_advance(void)
{
    bgm_irq_detach();
    while (g_probe_cursor < BGM_IRQ_LINE_COUNT) {
        int idx = g_probe_cursor++;
        if (bgm_irq_attach(idx)) {
            g_probe_frames = 0;
            g_probe_base_ticks = g_isr_ticks;
            return 1;
        }
    }
    return 0;
}

int hal_bgm_irq_init(void)
{
    /* devdoc 174: program Timer-B while every candidate line is still masked,
     * then hand the candidate scan to hal_bgm_irq_probe_step(), which promotes a
     * line to owner only after it has actually ticked.  Which line the board
     * strapped the timer to depends on the host's DIP switch / board option
     * (devdoc 164 §4), so it is settled by observation rather than assumption.
     *
     * Timer-B registers: reload value, then LOAD + ENABLE.  $29 bit7 (SCH = 6
     * voices) is re-asserted here with the timer-enable bit ($29 D1). */
    hal_log("BGM IRQ: init enter\r\n");

#if defined(NAIZ_DOS32A)
    /* devdoc 194 (2026-10-31): DOS/32A used to return 0 here and disable the
     * ISR outright, because a Timer-B tick landing inside mag_decode()'s cli
     * region caused a code=11 failure.
     *
     * devdoc 197 §A1 (2026-11-02): three full-flow experiments passed
     * (mag_decode all OK, IRQ12 ticks normal, beach1 displayed correctly).
     * Root cause: "the P7 fix changed the hook call inside mag_decode to
     * _enable()/hook()/_disable(), and the deep hook call chain is no longer
     * inside the cli region" -- so even when the ISR lands on the application
     * stack it only interrupts a pure computation hot loop and never rewrites
     * locals below the hook frame.
     * Settled: openpack uses the ISR by default and no longer disables it here.
     *
     * To temporarily fall back to cooperative (e.g. when debugging ISR issues),
     * rebuild with NAIZ_DOS32A_COOP_FORCE=1. */
#ifdef NAIZ_DOS32A_COOP_FORCE
    hal_log("BGM IRQ: DOS/32A build -> cooperative (NAIZ_DOS32A_COOP_FORCE)\r\n");
    return 0;
#endif
#endif

    /* Ownership stays with the co-operative pump until a candidate proves it
     * fires, so the BGM is never silent while the scan runs. */
    g_irq_active = 0;
    g_irq_probing = 1;
    g_probe_cursor = 0;

    /* devdoc 198: hook+unmask FIRST, THEN start Timer-B.  Otherwise Timer-B
     * may overflow before the handler is installed, leaving a sticky overflow
     * flag and a counter running unsync'd with the first ack.  OPNA Timer-B
     * auto-reloads on overflow, so starting it late only costs at most one
     * missed period (~16ms) — negligible vs the reliability gain. */
    if (!bgm_irq_probe_advance()) {
        g_irq_probing = 0;
        hal_log("BGM IRQ: no candidate with a PM vector; co-operative pump stays active\r\n");
        return 0;
    }

    outb(FM_REG_ADDR, FM_TIMER_B);
    outb(FM_REG_DATA, (unsigned char)(FM_TIMER_B_NB));
    outb(FM_REG_ADDR, FM_TIMER_CTRL);
    outb(FM_REG_DATA, (unsigned char)(FM_CTRL_LOAD_B | FM_CTRL_ENABLE_B));
    outb(FM_REG_ADDR, FM_IRQ_ENABLE);
    outb(FM_REG_DATA, (unsigned char)(0x80 | 0x02));  /* SCH + EN_TB */

    hal_logf("BGM IRQ: Timer-B programmed (NB=%d, ~61.9Hz); scanning IRQ lines\r\n",
             FM_TIMER_B_NB);
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

/* Hand the units accumulated by the handler to the main-thread pump.  Drain =
 * (produced - consumed); the consumed cursor is main-thread-only state, so this
 * needs no interrupt masking and cannot drop a tick that lands mid-read. */
unsigned long hal_bgm_irq_take_pending_units(void)
{
    static unsigned long consumed;
    unsigned long total = g_irq_units_total;
    unsigned long units = total - consumed;

    consumed = total;

    /* devdoc 198: reassert Timer-B control from the main thread whenever the
     * hook is installed.  NP2kai's opna_settimer() calls nevent_reset(FMTIMERB)
     * whenever $27 is written with D1=0 (LOAD B low).  A race between an FM
     * register write (outb $188=addr then outb $18A=data) and the ISR's own
     * $188/$18A pair can land an FM data byte onto $27 with D1=0, which
     * permanently stops the Timer-B event that drives our IRQ.  Even with
     * cli/sti protecting hal_fm_write_reg, the event may be killed before the
     * next ISR can self-heal (because the IRQ source IS the event).  Re-writing
     * $27 from the main thread guarantees D1 stays 1 and the event restarts if
     * it ever gets reset. */
    if (g_irq_line >= 0) {
        extern void _disable(void), _enable(void);
        _disable();
        outb(FM_REG_ADDR, FM_TIMER_CTRL);
        outb(FM_REG_DATA,
             (unsigned char)(FM_CTRL_RESET_B | FM_CTRL_ENABLE_B | FM_CTRL_LOAD_B));
        _enable();
    }

    return units;
}

/* Runtime ownership toggle (devdoc 175 §11).  init() + probe_step() handle
 * Timer-B setup and candidate election; the toggle only switches the
 * ownership flag between them.
 * Parameter semantics:
 *   on = 1 -> hand over to the ISR if setup is complete (g_irq_line >= 0);
 *             otherwise print a hint
 *   on = 0 -> return to the cooperative pump; Timer-B keeps ticking in the
 *             background (no reprogramming)
 * Returns 0 = switched to cooperative, 1 = switched to ISR, -1 = ISR setup
 * incomplete (switch refused).
 * The caller must ensure no BGM state change is in flight when switching
 * (the bgm_irq_lock critical section already covers audio_bgm_start/stop
 * et al.). */
int hal_bgm_irq_set_on(int on)
{
    if (on) {
        if (g_irq_line < 0) {
            hal_log("BGM IRQ: no line hooked yet (init + probe needed)\r\n");
            return -1;
        }
        if (!g_irq_active)
            hal_logf("BGM IRQ: → ISR (line=%s)\r\n",
                     g_irq_lines[g_irq_line].name);
        g_irq_active = 1;
        return 1;
    }
    if (g_irq_active)
        hal_log("BGM IRQ: → co-operative pump\r\n");
    g_irq_active = 0;
    return 0;
}

int hal_bgm_irq_is_on(void)
{
    return g_irq_active;
}

/* Called once per frame while the candidate scan runs (devdoc 174).  A hooked
 * timer delivers ~62 ticks/s, so a short window either shows ticks or does not.
 * Only a candidate that ticked becomes the pump owner; a silent one is detached
 * (IMR and vector restored) and the next candidate takes its place. */
void hal_bgm_irq_probe_step(void)
{
    unsigned long delta;

    if (!g_irq_probing)
        return;

    g_probe_frames++;
    delta = g_isr_ticks - g_probe_base_ticks;
    if (delta >= BGM_IRQ_PROBE_MIN_TICKS) {
        g_irq_active = 1;
        g_irq_probing = 0;
        hal_logf("BGM IRQ: %s ticks (%lu in %u frames); ISR owns the pump\r\n",
                 g_irq_lines[g_irq_line].name, delta, g_probe_frames);

        /* devdoc 198: re-arm Timer-B + PIC after probe.  Probe ran with
         * LOAD+ENABLE (no RESET) to start clean; re-programming here ensures
         * Timer-B and PIC are in a known-good state before we hand the pump
         * over.  Without this, probe's final handler ack (RESET+LOAD+ENABLE)
         * sometimes leaves Timer-B stopped on NP2kai's OPNA model. */
        {
            const BgmIrqLine *line = &g_irq_lines[g_irq_line];
            outb(FM_REG_ADDR, FM_TIMER_CTRL);
            outb(FM_REG_DATA,
                 (unsigned char)(FM_CTRL_RESET_B | FM_CTRL_ENABLE_B | FM_CTRL_LOAD_B));
            /* Re-unmask: handler ack may have tickled the PIC's IRR register */
            outb(line->imr_port, (unsigned char)(g_irq_saved_imr & ~line->imr_bit));
            hal_log("BGM IRQ: re-armed Timer-B + PIC after probe\r\n");
        }
        return;
    }
    if (g_probe_frames < BGM_IRQ_PROBE_FRAMES)
        return;

    hal_logf("BGM IRQ: %s silent (%lu ticks in %u frames); next candidate\r\n",
             g_irq_lines[g_irq_line].name, delta, g_probe_frames);
    if (!bgm_irq_probe_advance()) {
        g_irq_probing = 0;
        outb(FM_REG_ADDR, FM_TIMER_CTRL);
        outb(FM_REG_DATA, FM_CTRL_RESET_B);
        hal_log("BGM IRQ: no candidate ticks; co-operative pump stays active\r\n");
    }
}

void hal_bgm_irq_shutdown(void)
{
    if (g_irq_line < 0)
        return;
    /* Stop Timer-B (drop LOAD B), then restore the line we hooked. */
    outb(FM_REG_ADDR, FM_TIMER_CTRL);
    outb(FM_REG_DATA, FM_CTRL_RESET_B);
    g_irq_active = 0;
    g_irq_probing = 0;
    bgm_irq_detach();
}

#else /* NAIZ_BGM_IRQ */

/* devdoc 194: audio.c drains the ISR's unit counter unconditionally, so the
 * gated build still needs this symbol; with the path compiled out there is
 * nothing to drain.  Before this stub existed, `EXTRA_DEFS=-DNAIZ_BGM_IRQ=0`
 * failed to link, which made the documented fallback unusable. */
unsigned long hal_bgm_irq_take_pending_units(void)
{
    return 0;
}

#endif /* NAIZ_BGM_IRQ */
