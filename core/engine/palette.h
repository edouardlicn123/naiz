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

/* Reset the reserved VN palette slots (WHITE/TRANSPARENT/CURSOR_BLACK) to
 * their canonical values.  Shared by the bg/cg full-screen render paths so
 * the three entries cannot drift between call sites. */
void palette_reset_reserved(void);

/* Dirty-diff palette update: compare source RGB against prev, skip unchanged
 * entries and entries where prot[i] != 0 (e.g. VN dialog border colours).
 * hal_set_palette() is called only for changed entries; prev arrays are
 * updated in place.  pass prot = NULL to skip the protection check.
 *
 * _rgb variant: three separate 256-byte source arrays (Image struct).
 * _pal variant: interleaved uint8_t pal[count][3] (ANIM palette track). */
void palette_apply_dirty_rgb(const uint8_t src_r[256],
                             const uint8_t src_g[256],
                             const uint8_t src_b[256],
                             const uint8_t prot[256], int count,
                             uint8_t prev_r[256],
                             uint8_t prev_g[256],
                             uint8_t prev_b[256]);

void palette_apply_dirty_pal(const uint8_t pal[][3],
                             const uint8_t prot[256], int count,
                             uint8_t prev_r[256],
                             uint8_t prev_g[256],
                             uint8_t prev_b[256]);

#endif /* PALETTE_H */
