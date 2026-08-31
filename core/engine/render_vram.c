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

/* Fast row write from buffer into VRAM window via rep movsb. */
static void vram_row_write(const uint8_t *src, volatile uint8_t *win, int off, int n)
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
