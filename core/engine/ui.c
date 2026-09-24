/*
 * ui.c — UI rendering primitives (rounded rects, emboss, title text).
 *
 * Extracted from render.c (encapsulation refactoring).
 * Depends on VRAM primitives declared in render.h.
 */
#include "render.h"
#include "ui.h"

/* Integer square root (floor) — used by rounded-rect arc calculations.
 * Brute-force O(sqrt(n)), fine for r ≤ 256. */
static int isqrt(int n)
{
    int i;
    if (n > 46340) n = 46340;
    for (i = 0; i * i <= n; i++);
    return i - 1;
}

/* Draw rounded rectangle emboss border only (no body fill). */
void draw_rounded_emboss_outline(int x, int y, int w, int h, int r,
                                  uint8_t highlight, uint8_t shadow)
{
    int y_off, dy, dx;

    if (r > w / 2) r = w / 2;
    if (r > h / 2) r = h / 2;

    if (w > 2 * r)
        fill_rect(x + r, y, w - 2 * r, 1, highlight);
    for (y_off = 0; y_off < r; y_off++) {
        dy = r - y_off;
        dx = isqrt(r * r - dy * dy);
        vram_pset_addr((y + y_off) * LAYER_SCREEN_W + (x + r - dx), highlight);
    }
    for (y_off = h - r; y_off < h; y_off++) {
        dy = y_off - (h - r);
        dx = isqrt(r * r - dy * dy);
        vram_pset_addr((y + y_off) * LAYER_SCREEN_W + (x + r - dx), highlight);
    }

    if (w > 2 * r)
        fill_rect(x + r, y + h - 1, w - 2 * r, 1, shadow);
    for (y_off = 0; y_off < r; y_off++) {
        dy = r - y_off;
        dx = isqrt(r * r - dy * dy);
        vram_pset_addr((y + y_off) * LAYER_SCREEN_W + (x + w - 1 - r + dx), shadow);
    }
    for (y_off = h - r; y_off < h; y_off++) {
        dy = y_off - (h - r);
        dx = isqrt(r * r - dy * dy);
        vram_pset_addr((y + y_off) * LAYER_SCREEN_W + (x + w - 1 - r + dx), shadow);
    }
}

/* Draw a filled rounded rectangle with 3D embossed border.
 * r — corner radius (clamped to min(w/2, h/2))
 * fill      — body color
 * highlight — top/left edge (light source)
 * shadow    — bottom/right edge
 * Uses isqrt to compute arc profiles. */
void draw_rounded_emboss(int x, int y, int w, int h, int r,
                          uint8_t fill, uint8_t highlight, uint8_t shadow)
{
    int y_off, dy, dx;

    if (r > w / 2) r = w / 2;
    if (r > h / 2) r = h / 2;

    /* 3-band fill body */
    fill_rect(x + r, y, w - 2 * r, r, fill);
    fill_rect(x + r, y + h - r, w - 2 * r, r, fill);
    fill_rect(x, y + r, w, h - 2 * r, fill);

    /* Top arc — fill remaining arc margin beyond 3-band */
    for (y_off = 0; y_off < r; y_off++) {
        dy = r - y_off;
        dx = isqrt(r * r - dy * dy);
        if (dx > 0) {
            fill_rect(x + r - dx, y + y_off, dx, 1, fill);
            fill_rect(x + w - r, y + y_off, dx, 1, fill);
        }
    }
    /* Bottom arc — fill remaining arc margin beyond 3-band */
    for (y_off = h - r; y_off < h; y_off++) {
        dy = y_off - (h - r);
        dx = isqrt(r * r - dy * dy);
        if (dx > 0) {
            fill_rect(x + r - dx, y + y_off, dx, 1, fill);
            fill_rect(x + w - r, y + y_off, dx, 1, fill);
        }
    }

    /* Emboss: highlight on top edge + left arc perimeter */
    if (w > 2 * r)
        fill_rect(x + r, y, w - 2 * r, 1, highlight);
    for (y_off = 0; y_off < r; y_off++) {
        dy = r - y_off;
        dx = isqrt(r * r - dy * dy);
        vram_pset_addr((y + y_off) * LAYER_SCREEN_W + (x + r - dx), highlight);
    }
    for (y_off = h - r; y_off < h; y_off++) {
        dy = y_off - (h - r);
        dx = isqrt(r * r - dy * dy);
        vram_pset_addr((y + y_off) * LAYER_SCREEN_W + (x + r - dx), highlight);
    }

    /* Emboss: shadow on bottom edge + right arc perimeter */
    if (w > 2 * r)
        fill_rect(x + r, y + h - 1, w - 2 * r, 1, shadow);
    for (y_off = 0; y_off < r; y_off++) {
        dy = r - y_off;
        dx = isqrt(r * r - dy * dy);
        vram_pset_addr((y + y_off) * LAYER_SCREEN_W + (x + w - 1 - r + dx), shadow);
    }
    for (y_off = h - r; y_off < h; y_off++) {
        dy = y_off - (h - r);
        dx = isqrt(r * r - dy * dy);
        vram_pset_addr((y + y_off) * LAYER_SCREEN_W + (x + w - 1 - r + dx), shadow);
    }
}


