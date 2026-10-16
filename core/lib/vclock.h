/*
 * vclock.h — Smoothed virtual clock for micro-beat consumers (devdoc 129/133).
 *
 * The BGM scheduler, the typewriter reveal and anim_tick all derive their
 * per-pass progress from a virtual clock, and any unevenness in that clock is
 * audible (BGM) or visible (reveal) even though the clock never stops.
 *
 * Contract: call vclock_advance() exactly once per frame (the frame pump is
 * the sole owner, devdoc 129) with the platform's real elapsed time in ms,
 * and read the virtual time with vclock_ms().  Three guarantees, in order of
 * what the ear actually hears:
 *
 *   1. Steady beat.  Successive advances differ by at most VCLOCK_SLEW_UNITS,
 *      so a consumer's per-pass progress is continuous.  This is the property
 *      the old floor/ceiling clamp violated: it alternated a 40ms floor step
 *      and a 100ms ceiling step, and that 2.5:1 ratio was the audible flutter.
 *   2. No stall and no burst.  A frozen platform clock keeps a steady beat
 *      (the previous problem: blocking ops froze the clock entirely), and a
 *      platform jump is drained gradually rather than dumped in one pass
 *      (bounded by VCLOCK_MAX_ADVANCE_MS).
 *   3. Correct long-run tempo.  The step size is slewed toward the rate the
 *      platform actually measured, so the average matches real time and a
 *      song neither creeps nor races.
 *
 * devdoc 133 refinement: the platform clock is second-quantised (DOS 2Ch under
 * NP2kai returns DL=0 and delivers whole seconds in clusters, B19 §2.6), so a
 * single window's `want = delta/passes` jitters by up to ~1/passes — at ~20
 * passes that is ~5%, and chasing it with the slew is itself the residual
 * flutter.  Two additions fix that without weakening guarantee 1:
 *
 *   - the first closed window adopts its measurement outright (no ramp from a
 *     nominal constant, which made a song "start fast then settle"), and
 *   - every later window only moves the target by 1/VCLOCK_MEAS_SMOOTH of the
 *     error, so quantisation jitter is averaged out.
 *
 * A note on what "correct tempo" means here: the BGM is a closed loop — it
 * replays a table from t=0 to t=end against this clock with no external
 * reference — so only the clock's *rate* matters, never its phase against the
 * platform's reading.  That is what lets the step size change smoothly
 * instead of being forced to correct phase error instantly.
 */
#ifndef VCLOCK_H
#define VCLOCK_H

/* Virtual time is held in 1/K ms units so the step size can be tuned without
 * losing the whole-millisecond resolution every consumer wants. */
#define VCLOCK_UNITS_PER_MS 16UL

/* Largest single advance, in ms.  One nominal 60Hz frame: enough that a
 * caught-up burst drains over a few passes, small enough that no single step
 * is audible as a discontinuity. */
#define VCLOCK_MAX_ADVANCE_MS 100UL

/* Step size bounds, in ms per pass.  MIN keeps the clock from crawling to a
 * halt; MAX is the same ceiling as VCLOCK_MAX_ADVANCE_MS, so a clamp on the
 * step size and a clamp on the emitted advance can never disagree. */
#define VCLOCK_RATE_MIN_MS 1UL
#define VCLOCK_RATE_MAX_MS 100UL

/*
 * How fast the step size may move, in units per pass.  This is the flutter
 * control: it bounds how different two successive advances can be.  8 units
 * is 0.5 ms per pass — under 1.5% of a nominal 40 ms step, so a consumer's
 * per-pass progress stays continuous.  devdoc 133 proved the step does not
 * need to chase jitter quickly (the measurement is smoothed, §VCLOCK_MEAS_
 * SMOOTH), so the bound stays tight rather than being widened.
 */
#define VCLOCK_SLEW_UNITS 8UL

/*
 * Nominal step, in units per pass, before the platform has said anything.
 * 40 ms matches NP2kai's ~25Hz pass rate (devdoc 107's calibration note).  It
 * is only a priming fallback: the first closed window overwrites it outright
 * (devdoc 133), so a wrong constant can no longer make a song start fast.
 */
#define VCLOCK_INIT_STEP_UNITS 640UL

/*
 * A measurement window closes once this much real time has accumulated, in
 * ms.  One DOS second: it matches NP2kai's cluster delivery exactly and gives
 * a ~60Hz machine enough passes (tens) to average its 10 ms hundredths
 * quantisation.  Recomputing the rate faster than this only re-measures noise.
 */
#define VCLOCK_WINDOW_MS 1000UL

/*
 * IIR factor for the measured rate: the target moves 1/N of the way to each
 * new window's reading.  Averaging N quantised windows removes the ~1/passes
 * jitter (devdoc 133) while still following a genuine, sustained rate change
 * within a few seconds.  Too large a value keeps jitter; too small lags.
 */
#define VCLOCK_MEAS_SMOOTH 4UL

/*
 * Windows covering fewer than this many passes are rejected.  A single pass
 * that swallowed a whole second (a hard stall) measures a rate of one pass per
 * second, which is real but not representative of the passes that follow —
 * adopting it would wrongly slow the clock.  Normal windows carry tens of
 * passes on both NP2kai and a 60Hz machine.
 */
#define VCLOCK_MIN_WINDOW_PASSES 2UL

/*
 * A measurement window may not move the rate by more than NUM/DEN up, nor
 * below DEN/NUM down, in one step.  The DOS second is delivered in clusters
 * (B19 §2.3): a window that happens to start during a stall gap and closes on
 * the catch-up jump measures a spuriously fast rate (up to RATE_MAX, ~2.5x
 * nominal) over the few passes it actually covered.  Left unclamped, the IIR
 * would follow it and the 0.5 ms/pass slew would take seconds to undo — an
 * audible fast stretch.  Genuine pass-rate changes are gradual, so bounding
 * each window's correction loses nothing; the first (adopted) window is exempt
 * so a machine whose real rate differs from the priming constant still
 * calibrates outright.
 */
#define VCLOCK_MAX_WINDOW_RATIO_NUM 5UL
#define VCLOCK_MAX_WINDOW_RATIO_DEN 4UL

typedef struct {
    unsigned long virtual;    /* current virtual time, in units */
    unsigned long real_prev;  /* real ms seen at the previous advance */
    unsigned long step;       /* current step size, units per pass */
    unsigned long target;     /* smoothed measured rate, units per pass */
    unsigned long passes;     /* passes in the current measurement window */
    unsigned long accum;      /* real ms accumulated in the window */
    int           started;
    int           calibrated; /* first window adopted? */
} VClock;

/* Establish the origin.  Must be called before the first advance. */
void vclock_init(VClock *vc);

/*
 * Feed one frame of real elapsed time (ms) and step the clock once.
 *
 * Passing the same value repeatedly (frozen clock) keeps a steady beat at the
 * current step size.  Once VCLOCK_WINDOW_MS of real time has accumulated the
 * window closes: the first one adopts its measured rate outright, later ones
 * smooth the target toward it.  The surplus is drained across the passes the
 * window covers, never dumped into one pass.
 */
void vclock_advance(VClock *vc, unsigned long real_ms);

/* Current virtual time in whole milliseconds. */
unsigned long vclock_ms(const VClock *vc);

#endif /* VCLOCK_H */
