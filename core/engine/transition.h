/*
 * transition.h — Scene transition effects (palette fade, palette blinds).
 *
 * Owned by transition.c; scene_end() (layer.c) is the caller.
 *
 * All progressive transitions block for 'frames' frames.  The blinds
 * family sweeps N thin parallel strips (see PBLINDS_* in transition.c)
 * that grow from thin bars to full black; only the newly covered cells
 * are written to VRAM each frame, so the scene stays visible until the
 * front covers it.  The palette fade rewrites palette entries only (no
 * VRAM pixel writes).
 */
#ifndef TRANSITION_H
#define TRANSITION_H

/* Transition types.  Index 0 is a hard cut; the rest are progressive. */
#define TRANSITION_CUT       0
#define TRANSITION_VBLINDS   1  /* vertical strips: thin bars grow to black  */
#define TRANSITION_HBLINDS   2  /* horizontal strips: thin bars grow to black */
#define TRANSITION_DBLINDS   3  /* forward-diagonal strip sweep              */
#define TRANSITION_RDBLINDS  4  /* reverse-diagonal strip sweep              */
#define TRANSITION_PFADE     5  /* palette fade: interpolate live palette to a color */
#define TRANSITION_CHECKER   6  /* checkered staggered wipe: alternating cells sweep to black */

/* Global transition settings (from config.toml via nb_config.h) */
#include "nb_config.h"

#ifndef NAIZ_TRANSITION_TYPE
#define NAIZ_TRANSITION_TYPE TRANSITION_VBLINDS
#endif
#ifndef NAIZ_TRANSITION_FRAMES
#define NAIZ_TRANSITION_FRAMES 16
#endif

/* Run a transition on a VRAM rectangle (blocking, multi-frame).
 * Progressive types transition toward solid 'color' (0 = black) and the
 * rectangle is fully covered by the final frame.  type TRANSITION_CUT
 * paints 'color' immediately and returns. */
void transition_run(int x, int y, int w, int h,
                    unsigned char type, unsigned char frames,
                    unsigned char color);

#endif
