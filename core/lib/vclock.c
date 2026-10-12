/*
 * vclock.c — Smoothed virtual clock (devdoc 129).
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
 * This module instead holds a step size in 1/K ms units and slews it toward
 * the rate the platform actually measures.  A window is the run of passes
 * between two platform clock movements; when the platform finally jumps, the
 * jump size and the number of passes it covered tell us the true per-pass
 * rate, and the step size moves toward it by at most VCLOCK_SLEW_UNITS per
 * pass.  Consequences:
 *
 *   - successive advances differ by at most VCLOCK_SLEW_UNITS (steady beat);
 *   - a frozen platform clock keeps advancing at the current step (no stall);
 *   - a jump is drained across the passes it covers (no burst), because the
 *     step size approaches the true rate gradually instead of jumping;
 *   - the long-run average tracks real time (correct tempo), because every
 *     window re-measures it.
 *
 * The phase between the virtual clock and the platform reading is not
 * controlled, and does not need to be: every consumer drives a closed loop
 * (a MIDI table, a reveal, an animation) from this clock, so only its rate
 * matters.  That freedom is what allows the step to change smoothly rather
 * than being forced to chase instantaneous phase error.
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
    vc->started = 0;
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
         * baseline instead of deriving a huge unsigned delta from it. */
        vc->real_prev = real_ms;
        vc->passes = 0;
        return;
    }

    delta = real_ms - vc->real_prev;   /* platform clock is monotone */
    vc->real_prev = real_ms;
    vc->passes++;

    if (delta > 0) {
        /* The platform moved: window closed.  `delta` ms were really consumed
         * across `passes` frames, so that is the true per-pass rate.  Reaching
         * for it here is what keeps the long-run tempo honest. */
        unsigned long want = (delta * VCLOCK_UNITS_PER_MS) / vc->passes;
        if (want < VCLOCK_RATE_MIN_MS * VCLOCK_UNITS_PER_MS)
            want = VCLOCK_RATE_MIN_MS * VCLOCK_UNITS_PER_MS;
        if (want > VCLOCK_RATE_MAX_MS * VCLOCK_UNITS_PER_MS)
            want = VCLOCK_RATE_MAX_MS * VCLOCK_UNITS_PER_MS;
        vc->target = want;
        vc->passes = 0;
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
