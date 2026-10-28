/*
 * frame.c — Unified per-frame heartbeat (devdoc 129).
 * See frame.h for the ownership rule.
 */
#include "frame.h"
#include "render.h"      /* vblank_wait */
#include "hal.h"         /* hal_wallclock_smooth_advance */
#include "nb_anim.h"     /* anim_tick */
#include "audio.h"       /* audio_tick */
#include "nb_dialog.h"   /* nb_dialog_reveal_tick */
#include "transition.h"   /* transition_tick (devdoc 177) */
#include "preload_queue.h"

void engine_frame_pump(void)
{
    vblank_wait();                     /* pace the frame */
#if NAIZ_BGM_IRQ
    /* devdoc 174: while the candidate scan runs, the co-operative pump still
     * owns the clock and the audio -- this call just watches the hooked line's
     * tick counter and moves on to the next candidate when it stays silent. */
    hal_bgm_irq_probe_step();
    /* devdoc 164 / 168 / 176: the Timer-B handler owns the CLOCK only (fixed
     * 258-unit steps, ISR-safe: globals only).  The audio pump itself runs
     * below on this thread via audio_tick_isr_pending() -- DOS/4GW delivers
     * the IRQ on its own stack segment, where pointer-to-stack-local writes
     * silently miss (devdoc 176).  anim_tick/reveal stay display-paced. */
    if (!hal_bgm_irq_active()) {
        hal_wallclock_smooth_advance();
        audio_tick();
    } else {
        /* devdoc 165: the handler cannot log (not ISR-safe).  Sample its tick
         * count here, every ~2s, so a silent Timer-B (installed but not
         * firing) is visible from a serial capture instead of looking like a
         * working-but-frozen BGM. */
        static unsigned long shown;
        static unsigned frame_ctr;
        /* devdoc 176: the handler only advances the clock; the pump runs here,
         * on the main stack, for every unit it accumulated. */
        audio_tick_isr_pending();
        if (++frame_ctr >= 64) {
            unsigned long now = hal_bgm_irq_ticks();
            frame_ctr = 0;
            if (now != shown) {
                /* devdoc 167: v is produced solely by the handler (fixed
                 * 129-unit advance per tick), so v vs the real wall clock w
                 * says whether the ISR is actually keeping time or silently
                 * dropping ticks. */
                hal_logf("[ISR] ticks=%lu v=%lu w=%lu\r\n",
                         now, hal_wallclock_smooth_ms(), hal_wallclock_ms());
                shown = now;
            }
        }
    }
#else
    hal_wallclock_smooth_advance();    /* advance virtual clock (sole writer) */
    audio_tick();                      /* advance BGM cursor + pump PCM FIFO */
#endif
    anim_tick();                       /* advance animation frame */
    nb_dialog_reveal_tick();           /* advance typewriter reveal (no-op off) */
    transition_tick();                 /* devdoc 177: one transition step/frame */
    /* devdoc 177: decode one queued scene asset per frame; while the
     * transition covers the screen, take a second slot.  A failed decode drops
     * the job and stops this frame's consumption (Tier 1 heap guard).
     * devdoc 180: a 30-50 ms decode must never land on a typewriter frame --
     * the reveal tick already spends most of the frame budget on the dialog
     * composite, so hold the queue while a page is revealing; leftover jobs
     * drain over the static screen afterwards (a one-frame cursor jump,
     * imperceptible while reading). */
    if (!nb_dialog_reveal_active()) {
        if (preload_step() && transition_active())
            preload_step();
    }
}

/*
 * Decode-time frame step (devdoc 131 方案 B, devdoc 163 Phase 2 B2).
 *
 * A long MAG decode monopolises the CPU and used to freeze the virtual clock
 * (its progress hook only *read* the clock), so the whole BGM event table
 * stalled and then drained in one burst when the frame pump resumed — the
 * residual flutter.  This runs one pump step from inside the decode loop.
 *
 * devdoc 163 B2: the clock advance is now UNCONDITIONAL.  Gating it on a
 * VBLANK edge was wrong in both directions: on a platform where the GDC poll
 * never fires the clock froze for the whole decode, and where it does fire
 * the decode-stride call rate multiplied the main-loop-calibrated step (up to
 * ~2x).  vclock self-measures its per-call rate (window: want = accum*16/
 * passes), so advancing at stride rate is rate-correct by construction.
 * anim_tick() stays display-paced on purpose: animation must not run at
 * decode-stride rate.
 *
 * Deliberately non-blocking (hal_vblank_poll, not vblank_wait): a decode must
 * not wait a full frame per 4 KB stride, or loading a portrait would take
 * seconds.  (devdoc 131 方案 A's periodic vblank yield in audio_tick was
 * removed in devdoc 133 -- it hitched the main loop and this hook no longer
 * needs it.)
 */
void frame_decode_pump(void)
{
#if NAIZ_BGM_IRQ
    /* Stage 3: ISR active owns clock + audio pump (unit-based, devdoc 168).
     * audio_tick() handles delta_units internally; no extra count needed.
     * Animation tick stays (display-paced).  Pump count = 0 here. */
    if (!hal_bgm_irq_active()) {
        hal_wallclock_smooth_advance();/* self-measuring clock: call-rate safe */
        audio_tick();                  /* pump BGM/PCM (non-blocking) */
    } else {
        audio_tick_isr_pending();      /* devdoc 176: pump on the main stack */
    }
#else
    hal_wallclock_smooth_advance();/* self-measuring clock: call-rate safe */
    audio_tick();                  /* pump BGM/PCM (non-blocking) */
#endif
    if (hal_vblank_poll())         /* animation stays display-paced */
        anim_tick();
    nb_dialog_reveal_tick();       /* keep the typewriter flowing */
}
