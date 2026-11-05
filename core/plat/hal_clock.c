/*
 * hal_clock.c — HAL PC-98 wall clock and vertical-sync implementation
 *
 * Split out of hal_pc98.c (devdoc 200 §12.2): the wall-clock state, virtual
 * clock ownership and the vsync wait/poll all belong to the time base, so
 * they live in their own file instead of sharing one with the palette/VRAM
 * code.
 *
 * See: docs/ — HAL architecture design
 */
#include "hal.h"
#include "hal_internal.h"
#include "pc98.h"
#include "vclock.h"
#include <i86.h>

/*
 * Wall-clock milliseconds via DOS system time (INT 21h AH=2Ch).
 *
 * Clock-source history:
 *   - PIT (0.2.128/0.2.129): read-back under NP2kai is
 *     `nevent_getremain(NEVENT_ITIMER) / pccore.multiple` — driven by the
 *     emulated CPU clock (clk_mult scales it), non-monotonic samples, so
 *     the PIT cannot serve as a clock under the emulator (probe dVB/dLOOP
 *     in 0.2.130, ports 0x71/0x77 per refdocs B02).
 *   - vblank frame counter (0.2.130): NP2kai pass rate is ~20.5Hz
 *     (devdoc 82), so wallclock_frames++ once per hal_vblank_wait()
 *     advanced only ~342ms of clock per real second — a 3x slowdown.
 *   - DOS INT 21h AH=2Ch (this): 10ms granularity, maintained by DOS in
 *     the emulator and real hardware alike.  devdoc 82 §5.3 measured it
 *     exactly (guest 5000ms) under DOS/4GW DPMI; int386() reflection is
 *     the same channel already used for CRT BIOS INT 18h (video.c).
 *
 * Callers treat a decrease (midnight / counter wrap) as recalibration.
 */
static unsigned long wallclock_ms_total = 0;
static unsigned long wallclock_now_prev = 0;
static int          wallclock_inited = 0;

#define WALLCLOCK_DOS_TIME_INT  0x21
#define WALLCLOCK_DOS_AH_GET_TIME 0x2C

/* Virtual wall clock (devdoc 107 / 0.2.134, devdoc 129 follow-up).
 *
 * hal_wallclock_ms() is MACRO-accurate but its single-call delta is coarse:
 * the DOS 2Ch reading is second-quantised and delivered in clusters (frozen
 * 3-6s, then +1000..+6000ms), which froze the naive consumers and burst them
 * on catch-up.  The original answer (0.2.134) clamped the per-pass delta to
 * a fixed floor/ceiling; devdoc 129's frame pump then exposed that
 * clamp's flaw: with the advance happening once per pass, the
 * clamp alternates a 40ms floor step and a 100ms ceiling step, and that
 * uneven step size is the BGM flutter.
 *
 * The smoothing therefore lives in lib/vclock, which slews its step size
 * toward the rate the DOS clock actually measures instead of clamping it.
 * HAL's remaining job is ownership: vclock_advance() is the sole writer (the
 * frame pump) and hal_wallclock_smooth_ms() only reads.
 */
static VClock g_vclock;
static unsigned long last_advance_units = 258UL;  /* stage 3/4: default = one BGM_TIMER_B_UNIT tick */

/* devdoc 133: serial tempo probe toggle (0 = off).  Defaults on so a single
 * build is verifiable; the [VC] line is emitted every 64 advances. */
#ifndef VCLOCK_TRACE_ENABLED
#define VCLOCK_TRACE_ENABLED 1
#endif

void hal_clock_init(void)
{
    vclock_init(&g_vclock);
}

unsigned long hal_wallclock_ms(void)
{
    union REGS regs;
    unsigned long now;   /* ms since midnight (folded) */

    /* DOS system time via int386() (DPMI-reflected INT 21h AH=2Ch):
     * returns CH=hour, CL=minute, DH=second, DL=hundredths of a second.
     * Fold into a monotonic-ish ms-since-midnight for clean deltas. */
    regs.h.ah = WALLCLOCK_DOS_AH_GET_TIME;
    int386(WALLCLOCK_DOS_TIME_INT, &regs, &regs);

    now = ((unsigned long)regs.h.ch * 3600UL
         + (unsigned long)regs.h.cl * 60UL
         + (unsigned long)regs.h.dh) * 1000UL
        + (unsigned long)regs.h.dl * 10UL;

    if (!wallclock_inited) {
        wallclock_now_prev = now;
        wallclock_inited = 1;
        return wallclock_ms_total;
    }

    if (now >= wallclock_now_prev) {
        wallclock_ms_total += now - wallclock_now_prev;
    } else {
        /* Midnight wrap (now < prev): recalibrate, keep accumulated total. */
    }
    wallclock_now_prev = now;

    return wallclock_ms_total;
}

unsigned long hal_wallclock_smooth_ms(void)
{
    return vclock_ms(&g_vclock);
}

void hal_wallclock_smooth_advance(void)
{
    vclock_advance(&g_vclock, hal_wallclock_ms());
#if VCLOCK_TRACE_ENABLED
    {
        static unsigned trace_ctr = 0;
        if (++trace_ctr >= 64) {
            trace_ctr = 0;
            hal_logf("[VC] v=%lu w=%lu step=%lu tgt=%lu cal=%d\n",
                     vclock_ms(&g_vclock), hal_wallclock_ms(),
                     g_vclock.step, g_vclock.target,
                     g_vclock.calibrated);
        }
    }
#endif
    last_advance_units = 258UL;
}

/* devdoc 165: fixed-step clock advance for the Timer-B ISR.  No DOS call
 * (int 21h is not reentrant from a hardware handler), no window/step logic --
 * the hardware timer period IS the time source, so the ISR just adds the
 * known per-tick delta. */
void hal_wallclock_fixed_advance(unsigned long delta_units)
{
    vclock_advance_fixed(&g_vclock, delta_units);
    last_advance_units = delta_units;
}
unsigned long hal_wallclock_last_advance_units(void)
{
    return last_advance_units;  /* stage 4: last emitted clock step in 1/16 ms units */
}


/*
 * Vertical-retrace sync and frame-boundary detection (devdoc 131 A/B).
 *
 * GDC graphics status port 0xA0 bit 5 is the VSYNC flag (refdocs C01).
 *
 * `g_vs_level` tracks the last sampled level so a caller that cannot afford
 * to block (the MAG decode inner loop, devdoc 131 §6 approach B) can still detect
 * that the display advanced one frame — the virtual clock must step at the
 * DISPLAY's rate, not at the decode loop's stride count, or the BGM races.
 * Frame counting is deliberately used ONLY as a boundary detector, never as a
 * time source: B19 §2.3 retired it as a CLOCK because NP2kai runs it at
 * ~20.5Hz (a 3x-slow time base).  A boundary is just a boundary.
 */
static int g_vs_level = -1;   /* last sampled VSYNC level, -1 = uninitialised */

void hal_vblank_wait(void)
{
    int timeout = 100000;
    while (!(inb(GDC_GFX_PARAM) & GDC_VSYNC) && --timeout > 0);
    /* Returning at the start of a VBLANK:  the flag is asserted here. */
    g_vs_level = 1;
}

/*
 * Non-blocking VSYNC sampling for long CPU-bound paths (devdoc 131 approach B).
 *
 * Returns 1 exactly once per rising edge (VBLANK start); 0 otherwise.  Cheap
 * enough to call on every MAG decode stride.  The baseline is set by the first
 * call, and hal_vblank_wait() keeps it fresh after a blocking sync, so a
 * blocking pump and a polling decode loop never double-count the same frame.
 */
int hal_vblank_poll(void)
{
    int now = (inb(GDC_GFX_PARAM) & GDC_VSYNC) ? 1 : 0;
    int prev = g_vs_level;
    g_vs_level = now;
    if (prev < 0)
        return 0;            /* establish baseline */
    return (prev == 0 && now == 1);
}
