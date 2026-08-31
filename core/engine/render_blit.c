/*
 * Image blitting — VRAM sprite/background blits with transparency, mirror
 * and optional clipping.  Split out of render.c so the complexity of the
 * sprited blit path (the layer ordering + dialog constraint enforced by
 * vram_blit_sprite's clip_h parameter) stays isolated in one module.
 *
 * VRAM layout and bank-switching notes shared with the other VRAM modules
 * are documented in render.c's header.
 */
#include "render.h"

/* Fast row copy into the banked VRAM window via rep movsb.
 *
 * The PEGC bank window is plain RAM (no read/write side effects), so a
 * non-volatile bulk copy is safe here.  This matters enormously under
 * interpreted emulation: one REP MOVSB keeps the emulator inside a single
 * instruction's internal loop, while per-byte volatile stores pay full
 * fetch/decode cost for every pixel (a fullscreen blit would take ~1s).
 */
static void vram_row_copy(volatile uint8_t *win, int off, const uint8_t *src, int n)
{
    if (n <= 0)
        return;
    __asm {
        push    es
        push    ds
        pop     es                  /* ES = DS: flat model, both cover linear space */
        push    edi
        push    esi
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

/* Blit an entire MagImage to VRAM at (x,y).
 * No transparency — every pixel is written.  Delegates to vram_blit_sprite. */
void vram_blit(const MagImage *img, int x, int y)
{
    vram_blit_sprite(img, x, y, PAL_NO_TRANSPARENCY, 0, 0);
}

/* Blit a sprite image to VRAM with transparency and optional mirror.
 * Optimized: processes each screen line in bank-aligned segments.
 * Within each segment, non-transparent pixels are written without per-pixel
 * bank checking.  Run detection scans the source (in regular RAM), then
 * writes contiguous pixel runs to VRAM in tight loops.
 *
 * clip_h limits the number of source rows drawn from the top; it is the
 * mechanism vram_blit_sprite enforces the sprite-above-dialog constraint
 * with (rows at/under LAYER_DIALOG_Y are not written). */
void vram_blit_sprite(const MagImage *img, int x, int y, uint8_t transparent_idx,
                      int mirror, int clip_h)
{
    int py, addr, cur_bank, bank, off, seg, remain, line_addr;
    int sx0 = 0, sy0 = 0;
    int dw = img->width, dh = img->height;
    int px, src_x, run_len, line_off, k;
    const uint8_t *src_line;
    volatile uint8_t *win = hal_vram_get_window();
    if (dw <= 0 || dh <= 0) return;
    if (clip_h > 0 && clip_h < dh) dh = clip_h;
    if (x < 0) { sx0 = -x; dw += x; x = 0; }
    if (y < 0) { sy0 = -y; dh += y; y = 0; }
    if (dw <= 0 || dh <= 0) return;
    if (x >= LAYER_SCREEN_W || y >= LAYER_SCREEN_H) return;
    if (x + dw > LAYER_SCREEN_W) dw = LAYER_SCREEN_W - x;
    if (y + dh > LAYER_SCREEN_H) dh = LAYER_SCREEN_H - y;
    cur_bank = -1;
    for (py = 0; py < dh; py++) {
        int line_off = 0;
        src_line = img->pixels + (sy0 + py) * img->width;
        line_addr = (y + py) * LAYER_SCREEN_W + x;
        remain = dw;
        addr = line_addr;
        while (remain > 0) {
            bank = addr >> 15;
            if (bank != cur_bank) {
                cur_bank = bank;
                hal_vram_bank_select(bank);
            }
            off = addr & (VRAM_BANK_SZ - 1);
            seg = VRAM_BANK_SZ - off;
            if (seg > remain) seg = remain;
            if (!mirror && transparent_idx == PAL_NO_TRANSPARENCY) {
                /* Opaque blit fast path: bulk-copy the whole bank segment.
                 * Source offset is a straight line: sx0 + line_off. */
                vram_row_copy(win, off,
                              src_line + sx0 + line_off, seg);
            } else {
            /* Scan and write non-transparent runs within this bank segment */
            px = 0;
            while (px < seg) {
                /* Skip transparent pixels */
                while (px < seg) {
                    src_x = mirror ? (img->width - 1 - (sx0 + line_off + px)) : (sx0 + line_off + px);
                    if (src_line[src_x] != transparent_idx) break;
                    px++;
                }
                if (px >= seg) break;
                /* Find length of non-transparent run */
                run_len = 0;
                while (px + run_len < seg) {
                    src_x = mirror ? (img->width - 1 - (sx0 + line_off + px + run_len)) : (sx0 + line_off + px + run_len);
                    if (src_line[src_x] == transparent_idx) break;
                    run_len++;
                }
                /* Write the run */
                for (k = 0; k < run_len; k++) {
                    src_x = mirror ? (img->width - 1 - (sx0 + line_off + px + k)) : (sx0 + line_off + px + k);
                    win[off + px + k] = src_line[src_x];
                }
                px += run_len;
            }
            }
            addr += seg;
            remain -= seg;
            line_off += seg;
        }
    }
}
