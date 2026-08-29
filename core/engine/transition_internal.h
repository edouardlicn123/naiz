/*
 * transition_internal.h — Cross-file interfaces for the transition family.
 *
 * transition.c (dispatcher) / transition_pfade.c / transition_blinds.c /
 * transition_checker.c are one subsystem split by effect family.  This
 * header exposes the internal glue; the public transition.h API is the
 * external contract.
 */
#ifndef TRANSITION_INTERNAL_H
#define TRANSITION_INTERNAL_H

#include <stdint.h>
#include "palette.h"

/* Pure-black palette table: fade-out/interp target and final-frame
 * force-black.  Defined in transition_pfade.c. */
extern const uint8_t transition_black[PALETTE_SIZE][3];

/* Advance the palette fade-out by one step (transition_pfade.c). */
void transition_pfade_solid(int x, int y, int w, int h,
                            int step, int frames, unsigned char color);

/* Advance the blinds black-front sweep by one step (transition_blinds.c). */
void transition_pblinds_wipe(int x, int y, int w, int h, unsigned char type,
                             int step, int frames, unsigned char color);

/* Advance the checkered staggered wipe by one step (transition_checker.c). */
void transition_checker_wipe(int x, int y, int w, int h,
                             int step, int frames, unsigned char color);

#endif
