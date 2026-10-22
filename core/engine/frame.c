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

void engine_frame_pump(void)
{
    vblank_wait();                     /* pace the frame */
#if NAIZ_BGM_IRQ
    /* devdoc 164 phase 1: when the Timer-B ISR owns the beat it is also the
     * sole virtual-clock writer (hal.h contract).  Advancing here too would
     * double-step the clock.  audio_tick() is likewise the ISR's job; skip it
     * so the pump does not race the handler.  anim_tick/reveal stay here:
     * they are display-paced, not audio-paced. */
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
    /* ISR active: it owns the clock advance and the audio pump, so this hook
     * must not double-step them.  Animation still needs its display-paced
     * tick, which stays here. */
    if (!hal_bgm_irq_active()) {
        hal_wallclock_smooth_advance();/* self-measuring clock: call-rate safe */
        audio_tick();                  /* pump BGM/PCM (non-blocking) */
    }
#else
    hal_wallclock_smooth_advance();/* self-measuring clock: call-rate safe */
    audio_tick();                  /* pump BGM/PCM (non-blocking) */
#endif
    if (hal_vblank_poll())         /* animation stays display-paced */
        anim_tick();
    nb_dialog_reveal_tick();       /* keep the typewriter flowing */
}
