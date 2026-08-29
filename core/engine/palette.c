/*
 * palette.c — Palette read/write/interpolate primitives.
 *
 * See palette.h for API semantics.  These helpers are pure data access:
 * no vblank waits, no mouse handling, no logging — callers (transition
 * fade-out, NAIZ_ANIM palette track) own the frame/timing loop.
 */
#include "palette.h"
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
