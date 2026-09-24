/*
 * transition.c — Scene transition dispatcher.
 *
 * Split from scene_layers.c: driven by transition_run(), referenced only
 * by scene_end() (layer.c).  The effect families live in
 * transition_pfade.c (palette fade), transition_blinds.c (strip sweep)
 * and transition_checker.c (checkered wipe).
 *
 * Every progressive transition blocks for 'frames' frames and ends with
 * the whole rectangle black (normally 0).
 */
#include <stdio.h>
#include "render.h"
#include "transition.h"
#include "transition_internal.h"
#include "hal.h"
#include "debug.h"
#include "palette.h"

/* Run a transition effect (blocking, multi-frame).
 * type TRANSITION_CUT paints 'color' immediately and returns.
 * Progressive types finish with the whole rectangle covered by 'color'
 * (normally 0); the final palette black is forced for safety. */
void transition_run(int x, int y, int w, int h,
                    unsigned char type, unsigned char frames,
                    unsigned char color)
{
    int step;

    if (frames < 1) frames = 1;

    if (type == TRANSITION_CUT) {
        fill_rect(x, y, w, h, color);
        return;
    }

    for (step = 0; step < frames; step++) {
        switch (type) {
        case TRANSITION_PFADE:
            transition_pfade_solid(x, y, w, h, step, frames, color);
            break;
        case TRANSITION_VBLINDS:
        case TRANSITION_HBLINDS:
        case TRANSITION_DBLINDS:
        case TRANSITION_RDBLINDS:
            transition_pblinds_wipe(x, y, w, h, type, step, frames, color);
            break;
        case TRANSITION_CHECKER:
            transition_checker_wipe(x, y, w, h, step, frames, color);
            break;
        default:
            NB_DEBUG("WARN: transition_run: unknown type %d\r\n", type);
            break;
        }

        hal_vblank_wait();
        hal_mouse_update();
        hal_mouse_draw_cursor();
    }

    /* The sweep families may stop just short of the far edge with integer
     * rounding; the palette fade interpolates toward near-black.  Force
     * full black for a clean hand-over to the next scene. */
    palette_set_all(transition_black);
}
