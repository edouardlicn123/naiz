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
