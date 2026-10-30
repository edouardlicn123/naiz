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
#include "preload_queue.h"
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
    int hold;               /* devdoc 185: drain-hold ticks on the black cover */
    int x, y, w, h;
    unsigned char type;
    unsigned char color;
} TransitionState;

/* devdoc 185: hard cap on the black-cover drain hold, in pump ticks.  The
 * hold always terminates on its own (a failed decode drops its job), so this
 * only bounds pathological cases (e.g. a huge queue on a very slow machine)
 * at ~10 s on 60 Hz hardware. */
#define TRANSITION_HOLD_MAX 600

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
    g_transition.hold = 0;

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

    if (g_transition.step >= g_transition.frames) {
        /* devdoc 185: drain-hold phase.  The cover is already full black;
         * the new scene's script is still held back (nb_process waits for
         * transition_active() to clear), so nothing repaints over the cover.
         * Under NP2kai one MAG decode costs 250-500 ms, so lifting the cover
         * with jobs pending turned the drain into a visible stall train
         * (185 capture #2: 77 hitches of 250-1500 ms right after scene
         * entries).  Sit on the black cover -- the pump still drains two
         * queue slots per frame while transition_active() -- until the queue
         * empties (or the cap trips), then hand over. */
        if (g_transition.hold < TRANSITION_HOLD_MAX && preload_pending() > 0) {
            g_transition.hold++;
            return;
        }
        g_transition.active = 0;
        vm_request_process();
        return;
    }

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
     * restore by the new scene's image_load cannot resurrect the old frame.
     * devdoc 185: the cover stays ARMED with step==frames -- the next tick
     * enters the drain-hold phase and lifts the cover only once the preload
     * queue has drained (or TRANSITION_HOLD_MAX tripped). */
    palette_set_all(transition_black);
    fill_rect(g_transition.x, g_transition.y,
              g_transition.w, g_transition.h, g_transition.color);
}
