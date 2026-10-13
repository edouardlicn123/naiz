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
    hal_wallclock_smooth_advance();    /* advance virtual clock (sole writer) */
    anim_tick();                       /* advance animation frame */
    audio_tick();                      /* advance BGM cursor + pump PCM FIFO */
    nb_dialog_reveal_tick();           /* advance typewriter reveal (no-op off) */
}

/*
 * Decode-time frame step (devdoc 131 方案 B).
 *
 * A long MAG decode monopolises the CPU and used to freeze the virtual clock
 * (its progress hook only *read* the clock), so the whole BGM event table
 * stalled and then drained in one burst when the frame pump resumed — the
 * residual flutter.  This runs one pump step from inside the decode loop, but
 * gated on a real VBLANK edge: the clock steps at the DISPLAY's rate, not at
 * the decode stride count, so it neither freezes nor races.
 *
 * Deliberately non-blocking (hal_vblank_poll, not vblank_wait): a decode must
 * not wait a full frame per 4 KB stride, or loading a portrait would take
 * seconds.  (devdoc 131 方案 A's periodic vblank yield in audio_tick was
 * removed in devdoc 133 -- it hitched the main loop and this hook no longer
 * needs it.)
 */
void frame_decode_pump(void)
{
    if (hal_vblank_poll()) {           /* new displayed frame? */
        hal_wallclock_smooth_advance();/* advance clock once for that frame */
        anim_tick();                   /* keep animation flowing */
    }
    audio_tick();                      /* pump BGM/PCM (non-blocking) */
    nb_dialog_reveal_tick();           /* keep the typewriter flowing */
}
