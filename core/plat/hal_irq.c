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
 * Never go back to 129 -- that is the half-period value (devdocs/168).
 * The constant itself lives in hal.h now (devdoc 177): the engine's split
 * drain steps by one period and must agree with the handler. */

#define FM_CTRL_LOAD_B   0x02   /* D1: start Timer B */
#define FM_CTRL_ENABLE_B 0x08   /* D3: overflow sets the flag / asserts IRQ */
#define FM_CTRL_RESET_B  0x20   /* D5: clear the Timer-B flag (self-clearing) */

/* Candidate IRQ lines for the 86-board timer (devdoc 164 §四, devdoc 174).
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
#define BGM_IRQ_PROBE_FRAMES   8
#define BGM_IRQ_PROBE_MIN_TICKS 6

static int g_irq_active = 0;         /* ISR owns the clock/audio pump */
static int g_irq_probing = 0;        /* candidate scan in progress */
static int g_irq_line = -1;          /* index hooked now, -1 = none */
static unsigned long g_probe_base_ticks = 0;
static unsigned g_probe_frames = 0;
static int g_probe_cursor = 0;       /* next candidate index to try */
static unsigned char g_irq_saved_imr = 0;
static void (_WCINTERRUPT _WCFAR *g_saved_vect[BGM_IRQ_LINE_COUNT])(void);

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

/* Hook one candidate: install the handler, remember the vector it displaced,
 * then unmask that line.  Returns 0 if the line has no protected-mode vector at
 * all (not a real IRQ path on this host). */
static int bgm_irq_attach(int idx)
{
    const BgmIrqLine *line = &g_irq_lines[idx];
    unsigned short sel = 0;
    unsigned long off;

    hal_logf("BGM IRQ: probing INT %02Xh (%s)\r\n", line->vector, line->name);
    off = dpmi_get_pm_vector(line->vector, &sel);
    hal_logf("BGM IRQ: 0204 -> %lx:%04x\r\n", off, (unsigned)sel);
    if (off == 0 && sel == 0) {
        hal_logf("BGM IRQ: no PM vector for INT %02Xh (%s); skipping\r\n",
                 line->vector, line->name);
        return 0;
    }

    /* In the DOS/4GW flat model a far code pointer is a plain 32-bit offset
     * (no real selector), so DPMI 0205's CX:EDX sel:off split is wrong here --
     * it would pass the offset's high word as a bogus selector and fault on the
     * first IRQ.  _dos_setvect() takes the handler directly and, for the
     * auto-passup range 8-2Eh (INT 14h qualifies), DOS/4GW routes both PM and
     * RM to it (DOS/4GW FAQ 4a). */
    g_saved_vect[idx] = _dos_getvect(line->vector);
    _dos_setvect(line->vector,
                 (void (_WCINTERRUPT _WCFAR *)())bgm_irq_handler);

    g_irq_saved_imr = (unsigned char)inb(line->imr_port);
    hal_logf("BGM IRQ: unmask %s (imr %02x -> %02x)\r\n",
             line->name, (unsigned)g_irq_saved_imr,
             (unsigned)(g_irq_saved_imr & ~line->imr_bit));
    outb(line->imr_port, (unsigned char)(g_irq_saved_imr & ~line->imr_bit));

    g_irq_line = idx;
    return 1;
}

/* Undo bgm_irq_attach(): mask the line again, restore the displaced vector. */
static void bgm_irq_detach(void)
{
    if (g_irq_line < 0)
        return;
    {
        const BgmIrqLine *line = &g_irq_lines[g_irq_line];
        outb(line->imr_port, g_irq_saved_imr);
        _dos_setvect(line->vector, g_saved_vect[g_irq_line]);
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
     * (devdoc 164 四), so it is settled by observation rather than assumption.
     *
     * Timer-B registers: reload value, then LOAD + ENABLE.  $29 bit7 (SCH = 6
     * voices) is re-asserted here with the timer-enable bit ($29 D1). */
    hal_log("BGM IRQ: init enter\r\n");

    outb(FM_REG_ADDR, FM_TIMER_B);
    outb(FM_REG_DATA, (unsigned char)(FM_TIMER_B_NB));
    outb(FM_REG_ADDR, FM_TIMER_CTRL);
    outb(FM_REG_DATA, (unsigned char)(FM_CTRL_LOAD_B | FM_CTRL_ENABLE_B));
    outb(FM_REG_ADDR, FM_IRQ_ENABLE);
    outb(FM_REG_DATA, (unsigned char)(0x80 | 0x02));  /* SCH + EN_TB */

    /* Ownership stays with the co-operative pump until a candidate proves it
     * fires, so the BGM is never silent while the scan runs. */
    g_irq_active = 0;
    g_irq_probing = 1;
    g_probe_cursor = 0;

    if (!bgm_irq_probe_advance()) {
        g_irq_probing = 0;
        outb(FM_REG_ADDR, FM_TIMER_CTRL);
        outb(FM_REG_DATA, FM_CTRL_RESET_B);
        hal_log("BGM IRQ: no candidate with a PM vector; co-operative pump stays active\r\n");
        return 0;
    }

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
    return units;
}

/* Runtime ownership toggle (devdoc 175 §十一).  init() + probe_step() 负责
 * setup Timer-B 与选举正确候选；toggle 只在两者之间切所有权标志。
 * 参数语义：
 *   on = 1 → 若 setup 已完成（g_irq_line >= 0）则移交 ISR；否则打印提示
 *   on = 0 → 回到协作泵，Timer-B 继续在后台 tick（不重新编程）
 * 返回 0 = 切到协作泵，1 = 切到 ISR，-1 = ISR setup 未完成（拒绝切换）。
 * 调用者负责保证切换时没有正在进行的 BGM 状态变更（bgm_irq_lock 临界区
 * 已覆盖 audio_bgm_start/stop 等）。 */
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

#endif /* NAIZ_BGM_IRQ */
