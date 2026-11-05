/*
 * render_internal.h — shared internal helpers for the VRAM primitive modules.
 *
 * clip_rect is shared between render.c (rect/pattern fills) and
 * render_vram.c (block read/write). Kept as a static inline in a header
 * (precedent: pc98.h outb/inb, lib/endian.h read16_le) so neither module
 * exports it as public API and the two copies cannot drift.
 *
 * vram_fill_row / vram_row_write are the banked-window primitives shared by
 * render.c (fill), render_vram.c (snapshot write) and render_blit.c (opaque
 * blit copy).  Each is a single REP instruction: under interpreted emulation
 * this keeps the emulator inside one instruction's internal loop, whereas
 * per-byte volatile stores pay full fetch/decode per pixel.
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

/* Fast row fill in the banked VRAM window via rep stosb.
 * Fills 'n' bytes at win[off] with 'color'. */
static inline void vram_fill_row(volatile uint8_t *win, int off, uint8_t color, int n)
{
    if (n <= 0)
        return;
    __asm {
        push    es
        push    edi
        mov     edi, dword ptr [win]
        add     edi, dword ptr [off]
        mov     al, byte ptr [color]
        mov     ecx, dword ptr [n]
        cld
        rep     stosb
        pop     edi
        pop     es
    }
}

/* Fast row write from a buffer into the banked VRAM window via rep movsb.
 * The PEGC bank window is plain RAM (no read/write side effects), so a
 * non-volatile bulk copy is safe here.  Shared by the opaque blit path
 * (render_blit.c) and the snapshot-restore path (render_vram.c). */
static inline void vram_row_write(const uint8_t *src, volatile uint8_t *win, int off, int n)
{
    if (n <= 0)
        return;
    __asm {
        push    es
        push    edi
        push    esi
        push    ds
        pop     es                  /* ES = DS for flat model */
        mov     edi, dword ptr [win]
        add     edi, dword ptr [off]
        mov     esi, dword ptr [src]
        mov     ecx, dword ptr [n]
        cld
        rep     movsb
        pop     esi
        pop     edi
        pop     es
    }
}

#endif
