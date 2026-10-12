/*
 * vclock.h — Smoothed virtual clock for micro-beat consumers (devdoc 129).
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
 * per-pass progress stays continuous — while still letting the rate follow a
 * 20Hz->28Hz pass-rate change inside about a second.
 */
#define VCLOCK_SLEW_UNITS 8UL

/*
 * Nominal step, in units per pass, before the platform has said anything.
 * 40 ms matches NP2kai's ~25Hz pass rate (devdoc 107's calibration note).
 */
#define VCLOCK_INIT_STEP_UNITS 640UL

typedef struct {
    unsigned long virtual;    /* current virtual time, in units */
    unsigned long real_prev;  /* real ms seen at the previous advance */
    unsigned long step;       /* current step size, units per pass */
    unsigned long target;     /* step size the measurement wants */
    unsigned long passes;     /* passes since the platform last moved */
    int           started;
} VClock;

/* Establish the origin.  Must be called before the first advance. */
void vclock_init(VClock *vc);

/*
 * Feed one frame of real elapsed time (ms) and step the clock once.
 *
 * Passing the same value repeatedly (frozen clock) keeps a steady beat at the
 * current step size.  A jump after a frozen stretch re-measures the pass rate
 * over the passes the jump covers and slews the step size toward it, so the
 * surplus is drained across those passes instead of appearing in one of them.
 */
void vclock_advance(VClock *vc, unsigned long real_ms);

/* Current virtual time in whole milliseconds. */
unsigned long vclock_ms(const VClock *vc);

#endif /* VCLOCK_H */
