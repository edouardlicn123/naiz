/*
 * vclock.c — Smoothed virtual clock (devdoc 129/133).
 *
 * The defeat of the previous design (hal.h SMOOTH_CLOCK_MIN/MAX_MS) was that
 * it clamped the per-pass delta and let each consumer derive its beat from
 * the result.  It had no notion of how many passes a delta covers, so on
 * NP2kai — where the DOS clock is second-quantised and arrives in clusters
 * (devdoc 107 / B19 §3.1) — it emitted the 40ms floor step for the passes
 * inside a quantised second and the 100ms ceiling step on the pass where that
 * second landed.  Two step sizes in a 2.5:1 ratio, alternating, is exactly the
 * audible flutter: the clock advanced unevenly where it needed to advance
 * smoothly.
 *
 * This module holds a step size in 1/K ms units and slews it toward the rate
 * the platform actually measures.  A window is VCLOCK_WINDOW_MS of real time;
 * when it closes, the amount of time and the number of passes it covered tell
 * us the true per-pass rate, and the step size moves toward it by at most
 * VCLOCK_SLEW_UNITS per pass.  Consequences:
 *
 *   - successive advances differ by at most VCLOCK_SLEW_UNITS (steady beat);
 *   - a frozen platform clock keeps advancing at the current step (no stall);
 *   - a jump is drained across the passes it covers (no burst), because the
 *     step size approaches the true rate gradually instead of jumping;
 *   - the long-run average tracks real time (correct tempo), because every
 *     window re-measures it.
 *
 * devdoc 133 refinement.  Two defects survived the above:
 *
 *   1. The step started at a nominal 640 units and *slewed* to the measured
 *      rate, so for the first window(s) — seconds under NP2kai's cluster
 *      delivery — a song played at the wrong tempo ("starts fast then
 *      settles").  Fix: the first closed window is adopted outright.
 *   2. Because the platform's second is quantised, `want` jitters by up to
 *      ~1/passes (~5% at 20 passes); slewing after that jitter every window is
 *      itself the residual flutter, and it is audible while merely sitting on
 *      a dialogue page.  Fix: later windows move the target by only
 *      1/VCLOCK_MEAS_SMOOTH of the error, averaging the jitter out.
 *
 * devdoc 139 refinement.  One defect survived devdocs 133: a window that opens
 * during a DOS-clock stall gap and closes on the catch-up jump measures a rate
 * far above nominal (the jump covers time the window's few passes did not
 * really span), and the 0.5 ms/pass slew needs seconds to undo the excursion.
 * Fix: cap each window's measurement to VCLOCK_MAX_WINDOW_RATIO_NUM/DEN of the
 * running rate before the IIR sees it.  The first window is exempt so a
 * genuinely different machine rate still calibrates outright.
 *
 * The phase between the virtual clock and the platform reading is still not
 * controlled, and does not need to be: every consumer drives a closed loop
 * (a MIDI table, a reveal, an animation) from this clock, so only its rate
 * matters.
 *
 * Plain integer arithmetic, no floats and no I/O: the whole state machine is
 * exhaustively testable on the host.
 */
#include "vclock.h"

/* devdoc 211 §5.3: per-window diagnostic.  vclock.c is deliberately I/O-free
 * (it is unit-tested on the host), so the trace is a REGISTERED OBSERVER rather
 * than a macro: this file is compiled as its own translation unit (core/
 * Makefile LIB_SRCS globs lib/*.c), so a macro defined in core/plat/hal_clock.c
 * could never reach this code -- the first attempt at this instrumentation was
 * silently dead for exactly that reason.  hal_clock.c installs the printer in
 * hal_clock_init(); the host tests never install one.
 *
 * What it answers, and why it is the only way to settle devdoc 211:
 *   passes  — how many frames this window covered.  A correct 176 pass/s run
 *             shows a few hundred per 1000ms window; a huge number means the
 *             measurement is diluted by extra advances.
 *   accum   — how much real time those passes spanned.  Under 1000 the DOS
 *             clock barely moved; far over 1000 one delta swallowed a stall.
 *   raw_want— the measurement BEFORE the ratio clamp.  If this is already
 *             wrong, the clamp is innocent and the delta shape is the cause.
 *   want    — after the clamp, i.e. what the IIR is actually fed.
 */
static vclock_window_fn s_window_observer;

void vclock_set_window_observer(vclock_window_fn fn)
{
    s_window_observer = fn;
}

/* The counters are still live when the observer runs, so it may read them
 * straight off the clock instead of trusting the copies. */
#define VCLOCK_NOTIFY_WINDOW(vcp, raw_want, want)                          \
    do {                                                                   \
        if (s_window_observer)                                             \
            s_window_observer((vcp), (raw_want), (want),                   \
                              (vcp)->passes, (vcp)->accum);                \
    } while (0)

void vclock_init(VClock *vc)
{
    if (!vc) return;
    vc->virtual = 0;
    vc->real_prev = 0;
    vc->step = VCLOCK_INIT_STEP_UNITS;
    vc->target = VCLOCK_INIT_STEP_UNITS;
    vc->passes = 0;
    vc->accum = 0;
    vc->started = 0;
    vc->calibrated = 0;
    vc->undershoot = 0;
}

void vclock_advance(VClock *vc, unsigned long real_ms)
{
    unsigned long delta;
    unsigned long emitted;
    /* C89: declarations live at block top (WATCOM rejects mid-block ones).
     * hi/lo/diff serve the ratio clamp in the window-close branch. */
    unsigned long hi, lo;
    long diff;

    if (!vc) return;

    if (!vc->started) {
        /* Establish the origin: the first reading is the baseline, not a
         * delta, so nothing is emitted on this pass. */
        vc->real_prev = real_ms;
        vc->started = 1;
        return;
    }

    if (real_ms < vc->real_prev) {
        /* Platform wrapped (midnight) or went backwards.  Resynchronise the
         * baseline and reopen the window instead of deriving a huge unsigned
         * delta from it. */
        vc->real_prev = real_ms;
        vc->passes = 0;
        vc->accum = 0;
        vc->calibrated = 0;
        return;
    }

    delta = real_ms - vc->real_prev;   /* platform clock is monotone */
    vc->real_prev = real_ms;

    /* devdoc 173: stall protection.
     *
     * When the main thread stalls on a long VRAM blit, playanima decode, or
     * transition sweep, hal_wallclock_ms() (the REAL hardware clock) jumps by
     * the full stall duration on the next call.  Feeding that jump into
     * accum/passes corrupts the window measurement: a single 200ms delta
     * dilutes the per-pass rate into a spuriously fast step (e.g. 25ms/pass
     * instead of 5ms).  The clock then emits 25ms advances for several frames
     * and audio_tick dispatches 5x too many FM events — audible as "catching
     * up" after every sprite swap.
     *
     * The detection band is bounded on BOTH sides:
     *   - low  = VCLOCK_MAX_ADVANCE_MS (100 ms): below this the jump is within
     *     the window-clamp ceiling and cannot corrupt calibration meaningfully
     *     (the clamp at line ~106 caps any want to 100ms anyway).
     *   - high  = 500 ms: above this the delta is almost certainly a DOS-clock
     *     second-quantised jump (NP2kai clusters wall clock updates on whole
     *     seconds, producing 1000 ms deltas) — treating those as stalls would
     *     freeze the virtual clock for a full second every time the wall clock
     *     advances past a second boundary, which is worse than the original
     *     problem.  Real VRAM blits and playanima decodes are bounded by the
     *     frame budget (50-200 ms on NP2kai at ~20Hz) and never approach 500ms.
     *
     * When stall is detected: update real_prev so the NEXT normal advance has
     * a correct baseline, but do NOT include this delta in accum/passes and do
     * NOT advance virtual.  Virtual clock PAUSES during the stall and resumes
     * at the pre-stall step when the real frame loop recovers.
     *
     * The FM pipeline follows this same virtual clock (there is no separate
     * wall-clock path; devdoc 173 direction B was dropped), so the pause also
     * stops the BGM for the stall's duration -- which is exactly what the old
     * catch-up burst sounded like, minus the burst. */
    if (vc->calibrated
        && delta > VCLOCK_MAX_ADVANCE_MS
        && delta < 500UL) {
        /* Stall detected: reset the window but keep the calibrated step.
         * Virtual pauses, accum/passes are discarded. */
        vc->passes = 0;
        vc->accum = 0;
        return;
    }

    vc->accum += delta;
    vc->passes++;

    if (vc->accum >= VCLOCK_WINDOW_MS && vc->passes >= VCLOCK_MIN_WINDOW_PASSES) {
        /* The window closed: `accum` ms were really consumed across `passes`
         * frames, so that is the true per-pass rate.  Reaching for it here is
         * what keeps the long-run tempo honest. */
        unsigned long want = (vc->accum * VCLOCK_UNITS_PER_MS) / vc->passes;
        unsigned long raw_want = want;   /* pre-clamp, for the [VW] trace */
        if (want < VCLOCK_RATE_MIN_MS * VCLOCK_UNITS_PER_MS)
            want = VCLOCK_RATE_MIN_MS * VCLOCK_UNITS_PER_MS;
        if (want > VCLOCK_RATE_MAX_MS * VCLOCK_UNITS_PER_MS)
            want = VCLOCK_RATE_MAX_MS * VCLOCK_UNITS_PER_MS;

        if (!vc->calibrated) {
            /* First real measurement: adopt it outright.  Ramping from the
             * nominal constant is what made a song start off-tempo for the
             * first seconds (devdoc 133 §2.1). */
            vc->target = want;
            vc->step = want;
            vc->calibrated = 1;
        } else if (raw_want * 2 < vc->target) {
            /* devdoc 211 §7.3: SUSTAINED rate collapse — re-adopt outright.
             *
             * The 5/4 ratio clamp plus the 1/4 IIR can only move the target
             * ~5-20% per window downward.  When the pass rate jumps (Naiz
             * measured 117 pass/s at boot, then 315 pass/s on the same
             * machine — the emulator's frame pump is NOT frame-locked), the
             * true per-pass rate halves or worse, and the clamp turns a
             * one-second correction into a 30-60 s crawl during which the
             * virtual clock runs 1.5-3x fast.  That was the whole runaway
             * behind devdoc 211: `[VW]` showed raw=50 while tgt crawled
             * 136→55 over 21 windows.
             *
             * A single low window is NOT trusted (one that spans a hard
             * stall measures a too-low rate too — that is what VCLOCK_MIN_
             * WINDOW_PASSES guards only weakly); two consecutive windows
             * below half the running target means the machine's pass rate
             * genuinely changed.  Adopt raw_want (it is already clamped to
             * RATE_MIN/MAX), same contract as the first window. */
            vc->undershoot++;
            if (vc->undershoot >= 2) {
                vc->target = raw_want;
                vc->step = raw_want;
                vc->undershoot = 0;
            }
        } else {
            vc->undershoot = 0;
            /* Bound how far one window may move the rate before averaging it:
             * a window that catches a DOS-clock stall gap plus its catch-up
             * jump measures a spuriously fast rate (B19 §2.3), and following
             * it would hold the clock fast for seconds. */
            hi = vc->target * VCLOCK_MAX_WINDOW_RATIO_NUM
                 / VCLOCK_MAX_WINDOW_RATIO_DEN;
            lo = vc->target * VCLOCK_MAX_WINDOW_RATIO_DEN
                 / VCLOCK_MAX_WINDOW_RATIO_NUM;
            if (want > hi)
                want = hi;
            if (want < lo)
                want = lo;
            /* Average the quantisation jitter: move only a fraction of the
             * way to each window's reading (devdoc 133 §2.2). */
            diff = (long)want - (long)vc->target;
            vc->target = (unsigned long)((long)vc->target
                                         + diff / (long)VCLOCK_MEAS_SMOOTH);
        }
        VCLOCK_NOTIFY_WINDOW(vc, raw_want, want);
        vc->passes = 0;
        vc->accum = 0;
    } else if (vc->accum >= VCLOCK_WINDOW_MS) {
        /* Window closed but too short to trust (a hard stall ate the whole
         * span): keep the rate and start a fresh window. */
        vc->passes = 0;
        vc->accum = 0;
    }

    /* Slew the step toward the measured target.  Bounded per pass, so the
     * emitted advance never lurches — this is the flutter control. */
    if (vc->step < vc->target) {
        vc->step += VCLOCK_SLEW_UNITS;
        if (vc->step > vc->target)
            vc->step = vc->target;
    } else if (vc->step > vc->target) {
        vc->step -= VCLOCK_SLEW_UNITS;
        if (vc->step < vc->target)
            vc->step = vc->target;
    }

    emitted = vc->step;
    if (emitted > VCLOCK_MAX_ADVANCE_MS * VCLOCK_UNITS_PER_MS)
        emitted = VCLOCK_MAX_ADVANCE_MS * VCLOCK_UNITS_PER_MS;

    vc->virtual += emitted;
}

unsigned long vclock_ms(const VClock *vc)
{
    if (!vc) return 0;
    return vc->virtual / VCLOCK_UNITS_PER_MS;
}

void vclock_advance_fixed(VClock *vc, unsigned long delta_units)
{
    /* Interrupt-driven hardware time base (devdoc 165).  Pure arithmetic: a
     * Timer-B tick is a known fixed period, so no platform clock is read and
     * no DOS/BIOS call is made -- which is exactly what keeps this callable
     * from a hardware ISR.  `delta_units` is in 1/16 ms units, so a
     * non-integer-millisecond timer period (e.g. 16.154 ms -> 258 units) keeps
     * its phase instead of rounding to whole ms.  `started` is still honoured
     * so the very first tick after an origin establishes the baseline rather
     * than emitting. */
    if (!vc) return;

    if (!vc->started) {
        vc->started = 1;
        return;
    }

    vc->virtual += delta_units;
}
