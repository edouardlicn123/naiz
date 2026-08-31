/*
 * render_internal.h — shared internal helpers for the VRAM primitive modules.
 *
 * clip_rect is shared between render.c (rect/pattern fills) and
 * render_vram.c (block read/write). Kept as a static inline in a header
 * (precedent: pc98.h outb/inb, lib/endian.h read16_le) so neither module
 * exports it as public API and the two copies cannot drift.
 */
#ifndef RENDER_INTERNAL_H
#define RENDER_INTERNAL_H

/* Clip a rectangle to [0, max_w) x [0, max_h).
 * Mutates (x,y,w,h) in-place.  Returns 0 if fully clipped (nothing to draw). */
static inline int clip_rect(int *x, int *y, int *w, int *h, int max_w, int max_h)
{
    if (*w <= 0 || *h <= 0) return 0;
    if (*x < 0) { *w += *x; *x = 0; }
    if (*y < 0) { *h += *y; *y = 0; }
    if (*x >= max_w || *y >= max_h) return 0;
    if (*x + *w > max_w) *w = max_w - *x;
    if (*y + *h > max_h) *h = max_h - *y;
    if (*w <= 0 || *h <= 0) return 0;
    return 1;
}

#endif
