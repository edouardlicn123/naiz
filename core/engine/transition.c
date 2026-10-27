/*
 * transition.c — Scene transition dispatcher.
 *
 * Split from scene_layers.c: armed by transition_start() from scene_end()
 * (layer.c) and stepped once per frame by transition_tick() from the frame
 * pump (devdoc 177).  The effect families live in transition_pfade.c
 * (palette fade), transition_blinds.c (strip sweep) and transition_checker.c
 * (checkered wipe).
 *
 * devdoc 177: the transition no longer blocks for 'frames' frames.  The old
 * for-loop owned a hal_vblank_wait() per step, which meant the engine could
 * neither preload the next scene nor drain audio from the normal frame path.
 * start() only arms the state, tick() renders exactly one step per frame, and
 * the last frame hands the covered rectangle to the next scene in black.
 */
#include <stdio.h>
#include "render.h"
#include "transition.h"
#include "transition_internal.h"
#include "debug.h"
#include "palette.h"
#include "vm.h"

/* One armed transition.  Only one can be in flight: scene_end() starts a
 * transition right before the new script is swapped in, and nb_process() holds
 * the script until transition_active() clears. */
typedef struct {
    int active;
    int step;
    int frames;
    int x, y, w, h;
    unsigned char type;
    unsigned char color;
} TransitionState;

static TransitionState g_transition;

/* Arm a transition on a VRAM rectangle (frame-driven).
 * type TRANSITION_CUT paints 'color' immediately and leaves nothing armed. */
void transition_start(int x, int y, int w, int h,
                      unsigned char type, unsigned char frames,
                      unsigned char color)
{
    if (frames < 1) frames = 1;

    g_transition.x = x;
    g_transition.y = y;
    g_transition.w = w;
    g_transition.h = h;
    g_transition.type = type;
    g_transition.color = color;
    g_transition.step = 0;
    g_transition.frames = frames;

    if (type == TRANSITION_CUT) {
        fill_rect(x, y, w, h, color);
        g_transition.active = 0;
        return;
    }
    g_transition.active = 1;
}

int transition_active(void)
{
    return g_transition.active;
}

/* Advance the armed transition by one frame (called from engine_frame_pump).
 * The final step forces the palette black and fills the rectangle, replacing
 * the two calls scene_end() used to make after its blocking loop. */
void transition_tick(void)
{
    if (!g_transition.active)
        return;

    switch (g_transition.type) {
    case TRANSITION_PFADE:
        transition_pfade_solid(g_transition.x, g_transition.y,
                               g_transition.w, g_transition.h,
                               g_transition.step, g_transition.frames,
                               g_transition.color);
        break;
    case TRANSITION_VBLINDS:
    case TRANSITION_HBLINDS:
    case TRANSITION_DBLINDS:
    case TRANSITION_RDBLINDS:
        transition_pblinds_wipe(g_transition.x, g_transition.y,
                                g_transition.w, g_transition.h,
                                g_transition.type,
                                g_transition.step, g_transition.frames,
                                g_transition.color);
        break;
    case TRANSITION_CHECKER:
        transition_checker_wipe(g_transition.x, g_transition.y,
                                g_transition.w, g_transition.h,
                                g_transition.step, g_transition.frames,
                                g_transition.color);
        break;
    default:
        NB_DEBUG("WARN: transition_tick: unknown type %d\r\n",
                 g_transition.type);
        break;
    }

    if (++g_transition.step < g_transition.frames)
        return;

    /* The sweep families may stop just short of the far edge with integer
     * rounding; the palette fade interpolates toward near-black.  Force full
     * black for a clean hand-over, then blank the covered pixels so a palette
     * restore by the new scene's image_load cannot resurrect the old frame. */
    palette_set_all(transition_black);
    fill_rect(g_transition.x, g_transition.y,
              g_transition.w, g_transition.h, g_transition.color);
    g_transition.active = 0;
    vm_request_process();
}
