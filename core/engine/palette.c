/*
 * palette.c — Palette read/write/interpolate primitives.
 *
 * See palette.h for API semantics.  These helpers are pure data access:
 * no vblank waits, no mouse handling, no logging — callers (transition
 * fade-out, NAIZ_ANIM palette track) own the frame/timing loop.
 */
#include "palette.h"
#include "render.h"
#include "hal.h"

/* Read all 256 palette entries from the hardware palette ports. */
void palette_get_all(uint8_t pal[PALETTE_SIZE][3])
{
    int i;
    for (i = 0; i < PALETTE_SIZE; i++) {
        hal_read_palette(i, &pal[i][0], &pal[i][1], &pal[i][2]);
    }
}

/* Write all 256 palette entries to the hardware palette ports. */
void palette_set_all(const uint8_t pal[PALETTE_SIZE][3])
{
    int i;
    for (i = 0; i < PALETTE_SIZE; i++) {
        hal_set_palette(i, pal[i][0], pal[i][1], pal[i][2]);
    }
}

/* Per-entry linear interpolation toward 'to' with factor step/div.
 * Integer math avoids float; div/2 rounding converges to 'to' at step==div.
 * step is clamped to [0,div] so out never overshoots the endpoints. */
void palette_interp(const uint8_t from[PALETTE_SIZE][3],
                    const uint8_t to[PALETTE_SIZE][3],
                    int step, int div, uint8_t out[PALETTE_SIZE][3])
{
    int i, c;
    if (div < 1) div = 1;
    if (step < 0) step = 0;
    if (step > div) step = div;
    for (i = 0; i < PALETTE_SIZE; i++) {
        for (c = 0; c < 3; c++) {
            int f = from[i][c];
            int t = to[i][c];
            int v = (f * (div - step) + t * step + div / 2) / div;
            if (v < 0) v = 0;
            else if (v > 255) v = 255;
            out[i][c] = (uint8_t)v;
        }
    }
}

/* Canonical values for the reserved VN palette slots (see render.h). */
void palette_reset_reserved(void)
{
    hal_set_palette(PAL_WHITE, 0xFF, 0xFF, 0xFF);
    hal_set_palette(PAL_TRANSPARENT, 0xFF, 0xFF, 0xFF);
    hal_set_palette(PAL_CURSOR_BLACK, 0x00, 0x00, 0x00);
}

/* Dirty-diff from separate R/G/B arrays (Image struct path). */
void palette_apply_dirty_rgb(const uint8_t src_r[256],
                             const uint8_t src_g[256],
                             const uint8_t src_b[256],
                             const uint8_t prot[256], int count,
                             uint8_t prev_r[256],
                             uint8_t prev_g[256],
                             uint8_t prev_b[256])
{
    int i;
    for (i = 0; i < count && i < 256; i++) {
        uint8_t r = src_r[i], g = src_g[i], b = src_b[i];
        if (prot && prot[i]) continue;
        if (r == prev_r[i] && g == prev_g[i] && b == prev_b[i]) continue;
        hal_set_palette(i, r, g, b);
        prev_r[i] = r;
        prev_g[i] = g;
        prev_b[i] = b;
    }
}

/* Dirty-diff from interleaved pal[count][3] (ANIM palette track path). */
void palette_apply_dirty_pal(const uint8_t pal[][3],
                             const uint8_t prot[256], int count,
                             uint8_t prev_r[256],
                             uint8_t prev_g[256],
                             uint8_t prev_b[256])
{
    int i;
    for (i = 0; i < count && i < 256; i++) {
        uint8_t r = pal[i][0], g = pal[i][1], b = pal[i][2];
        if (prot && prot[i]) continue;
        if (r == prev_r[i] && g == prev_g[i] && b == prev_b[i]) continue;
        hal_set_palette(i, r, g, b);
        prev_r[i] = r;
        prev_g[i] = g;
        prev_b[i] = b;
    }
}
