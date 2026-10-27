/*
 * transition.h — Scene transition effects (palette fade, palette blinds).
 *
 * Owned by transition.c; scene_end() (layer.c) is the caller.
 *
 * Progressive transitions are frame-driven (devdoc 177): scene_end() arms
 * one with transition_start(), engine_frame_pump() calls transition_tick()
 * once per frame, and nb_process() holds the script while transition_active().
 * The blinds family sweeps N thin parallel strips (see PBLINDS_* in
 * transition.c) that grow from thin bars to full black; only the newly
 * covered cells are written to VRAM each frame, so the scene stays visible
 * until the front covers it.  The palette fade rewrites palette entries only
 * (no VRAM pixel writes).
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

/* Arm a transition on a VRAM rectangle (frame-driven, devdoc 177).
 * Progressive types render one step per transition_tick() until the rectangle
 * is covered by 'color' (0 = black).  type TRANSITION_CUT paints 'color'
 * immediately and arms nothing. */
void transition_start(int x, int y, int w, int h,
                      unsigned char type, unsigned char frames,
                      unsigned char color);

/* Render one transition frame; the last step covers the rectangle, forces the
 * palette black and requests VM processing. */
void transition_tick(void);

/* Non-zero while a transition is armed; nb_process() holds the script then. */
int transition_active(void);

#endif
