/*
 * palette.h — Palette read/write/interpolate primitives.
 *
 * Bulk access to the shared 256-entry color palette through the GDC
 * palette ports (via hal_read_palette / hal_set_palette).  Pure data
 * helpers with no frame loop or blocking logic; reusable by scene
 * transitions and the NAIZ_ANIM palette track.
 *
 * Layout: uint8_t pal[256][3] = { {r,g,b}, ... } indexed by palette index.
 */
#ifndef PALETTE_H
#define PALETTE_H

#include <stdint.h>

#define PALETTE_SIZE 256

/* Read all 256 palette entries from the hardware palette ports. */
void palette_get_all(uint8_t pal[PALETTE_SIZE][3]);

/* Write all 256 palette entries to the hardware palette ports. */
void palette_set_all(const uint8_t pal[PALETTE_SIZE][3]);

/* Per-entry linear interpolation: out = from + (to - from) * step / div.
 * Integer math, clamped to [0,255]; out updated in place. */
void palette_interp(const uint8_t from[PALETTE_SIZE][3],
                    const uint8_t to[PALETTE_SIZE][3],
                    int step, int div, uint8_t out[PALETTE_SIZE][3]);

#endif /* PALETTE_H */
