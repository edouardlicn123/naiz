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
}

void vclock_advance(VClock *vc, unsigned long real_ms)
{
    unsigned long delta;
    unsigned long emitted;

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
    vc->accum += delta;
    vc->passes++;

    if (vc->accum >= VCLOCK_WINDOW_MS && vc->passes >= VCLOCK_MIN_WINDOW_PASSES) {
        /* The window closed: `accum` ms were really consumed across `passes`
         * frames, so that is the true per-pass rate.  Reaching for it here is
         * what keeps the long-run tempo honest. */
        unsigned long want = (vc->accum * VCLOCK_UNITS_PER_MS) / vc->passes;
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
        } else {
            /* Bound how far one window may move the rate before averaging it:
             * a window that catches a DOS-clock stall gap plus its catch-up
             * jump measures a spuriously fast rate (B19 §2.3), and following
             * it would hold the clock fast for seconds. */
            unsigned long hi = vc->target * VCLOCK_MAX_WINDOW_RATIO_NUM
                               / VCLOCK_MAX_WINDOW_RATIO_DEN;
            unsigned long lo = vc->target * VCLOCK_MAX_WINDOW_RATIO_DEN
                               / VCLOCK_MAX_WINDOW_RATIO_NUM;
            long diff;
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
