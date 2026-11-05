/*
 * transition_pfade.c — Palette fade transition family.
 *
 * Split from transition.c: interpolates the whole live palette toward
 * black with no VRAM pixel writes, so the background survives intact.
 */
#include "palette.h"
#include "transition_internal.h"

/* Pure-black palette table: fade-out/interp target for all types. */
const uint8_t transition_black[PALETTE_SIZE][3] = { {0} };

/* Scratch buffers for palette fade-out.  Transitions are single-flight and
 * blocking, so file-scope buffers are safe and avoid large stack usage. */
static uint8_t pfade_basis[PALETTE_SIZE][3];
static uint8_t pfade_cur[PALETTE_SIZE][3];

/* Advance palette fade-out by one step.
 * Step 0 captures the live palette as the fade basis; every subsequent step
 * interpolates all 256 entries toward black and writes them to the ports. */
void transition_pfade_solid(int x, int y, int w, int h,
                            int step, int frames, unsigned char color)
{
    (void)x; (void)y; (void)w; (void)h; (void)color;
    if (step == 0) {
        palette_get_all(pfade_basis);
    }
    palette_interp(pfade_basis, transition_black, step, frames, pfade_cur);
    palette_set_all(pfade_cur);
}
