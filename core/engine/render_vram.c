/*
 * VRAM block I/O — rectangular read/write between the banked VRAM window
 * and regular buffers (background/dialog snapshots, cursor save/restore).
 * Split out of render.c; shares clip_rect via render_internal.h.
 *
 * VRAM layout and bank-switching notes shared with the other VRAM modules
 * are documented in render.c's header.
 */
#include "render.h"
#include "render_internal.h"

/* Fast row read from VRAM window into a buffer via rep movsb. */
static void vram_row_read(volatile uint8_t *win, int off, uint8_t *dst, int n)
{
    if (n <= 0)
        return;
    __asm {
        push    es
        push    edi
        push    esi
        push    ds
        pop     es                  /* ES = DS for flat model */
        mov     edi, dword ptr [dst]
        mov     esi, dword ptr [win]
        add     esi, dword ptr [off]
        mov     ecx, dword ptr [n]
        cld
        rep     movsb
        pop     esi
        pop     edi
        pop     es
    }
}

/* Read a rectangular region from VRAM into a pre-allocated buffer.
 * Used for background/dialog snapshots.
 * Optimized: processes each row in bank-aligned segments via rep movsb. */
void vram_read(int x, int y, int w, int h, uint8_t *buf)
{
    int py, addr, remain, bank, off, seg;
    int cur_bank = -1;
    int orig_w = w, orig_x = x, orig_y = y;
    volatile uint8_t *win = hal_vram_get_window();
    if (!clip_rect(&x, &y, &w, &h, LAYER_SCREEN_W, LAYER_SCREEN_H)) return;
    {
        int skip_x = x - orig_x;
        int skip_y = y - orig_y;
        for (py = 0; py < h; py++) {
            addr = (y + py) * LAYER_SCREEN_W + x;
            remain = w;
            while (remain > 0) {
                bank = addr >> 15;
                if (bank != cur_bank) {
                    cur_bank = bank;
                    hal_vram_bank_select(bank);
                }
                off = addr & (VRAM_BANK_SZ - 1);
                seg = VRAM_BANK_SZ - off;
                if (seg > remain) seg = remain;
                vram_row_read(win, off,
                              buf + (skip_y + py) * orig_w + skip_x + (w - remain), seg);
                addr += seg;
                remain -= seg;
            }
        }
    }
}

/* Write a rectangular buffer back to VRAM.
 * Used for restoring dialog/background snapshots.
 * Optimized: processes each row in bank-aligned segments via rep movsb. */
void vram_write(const uint8_t *buf, int x, int y, int w, int h)
{
    int py, addr, remain, bank, off, seg;
    int cur_bank = -1;
    int orig_w = w, orig_x = x, orig_y = y;
    volatile uint8_t *win = hal_vram_get_window();
    if (!clip_rect(&x, &y, &w, &h, LAYER_SCREEN_W, LAYER_SCREEN_H)) return;
    {
        int skip_x = x - orig_x;
        int skip_y = y - orig_y;
        for (py = 0; py < h; py++) {
            addr = (y + py) * LAYER_SCREEN_W + x;
            remain = w;
            while (remain > 0) {
                bank = addr >> 15;
                if (bank != cur_bank) {
                    cur_bank = bank;
                    hal_vram_bank_select(bank);
                }
                off = addr & (VRAM_BANK_SZ - 1);
                seg = VRAM_BANK_SZ - off;
                if (seg > remain) seg = remain;
                vram_row_write(buf + (skip_y + py) * orig_w + skip_x + (w - remain),
                               win, off, seg);
                addr += seg;
                remain -= seg;
            }
        }
    }
}

/* Blit a RAM buffer rectangle to VRAM, skipping pixels equal to
 * transparent_idx (sprite-blit transparency semantics).  (x,y,w,h) are in
 * buffer coordinates; the rect is written at screen (offx+x, offy+y).
 * Per-pixel skip test means no rep movsb bulk path — acceptable because the
 * menu layer content is sparse (buttons/labels over a static base). */
void render_blit_transparent(const uint8_t *buf, int stride,
                             int x, int y, int w, int h,
                             int offx, int offy, uint8_t transparent_idx)
{
    int py, px, cur_bank = -1, vx, vy;
    volatile uint8_t *win = hal_vram_get_window();
    if (w <= 0 || h <= 0) return;
    vx = offx + x;
    vy = offy + y;
    for (py = 0; py < h; py++) {
        int sy = vy + py;
        int rowoff;
        if (sy < 0 || sy >= LAYER_SCREEN_H) continue;
        rowoff = (y + py) * stride + x;
        for (px = 0; px < w; px++) {
            int sx = vx + px;
            int addr;
            if (sx < 0 || sx >= LAYER_SCREEN_W) continue;
            if (buf[rowoff + px] == transparent_idx) continue;
            addr = sy * LAYER_SCREEN_W + sx;
            VRAM_SET_BANK(addr, cur_bank);
            win[addr & (VRAM_BANK_SZ - 1)] = buf[rowoff + px];
        }
    }
}
