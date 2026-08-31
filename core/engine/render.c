/*
 * VRAM primitives — 256-color Packed-Pixel via PEGC bank switching.
 *
 * VRAM layout (256-color mode):
 *   Linear frame buffer: 640x400 bytes, pixel = 1 byte (palette index)
 *   Bank size: 32KB (32768 bytes), selected via register at 0xE0004
 *   VRAM window: 0xA8000–0xAFFFF mirrors the active 32KB bank
 *
 * Optimization: hal_vram_bank_select() is a slow hardware port write (outw).
 * All inner loops track the current bank and only switch when needed.
 * VRAM window pointer is cached once per function via hal_vram_get_window().
 *
 * This module holds the rectangle/pattern filling primitives and the
 * vblank synchronization helper.  Image blits live in render_blit.c and
 * bulk VRAM reads/writes live in render_vram.c; clip_rect is shared via
 * render_internal.h.
 */
#include "render.h"
#include "render_internal.h"

/* Forward declaration for the static bulk fill helper */
static void vram_fill_row(volatile uint8_t *win, int off, uint8_t color, int n);

/* Set a single pixel at a linear pixel address (y * LAYER_SCREEN_W + x).
 * Selects the correct bank and writes to the VRAM window.
 * Silently returns if addr is out of valid VRAM range [0, 256000). */
void vram_pset_addr(int addr, uint8_t color)
{
    volatile uint8_t *win = hal_vram_get_window();
    if (addr < 0 || addr >= LAYER_SCREEN_W * LAYER_SCREEN_H) return;
    hal_vram_bank_select(addr >> 15);
    win[addr & (VRAM_BANK_SZ - 1)] = color;
}

/* Fill a rectangular region with a solid color.
 * Optimized: processes VRAM in bank-aligned segments with minimal
 * bank switches. Each screen line may cross at most one bank boundary. */
void fill_rect(int x, int y, int w, int h, uint8_t color)
{
    int py, addr, remain, bank, off, seg;
    int cur_bank = -1;
    volatile uint8_t *win = hal_vram_get_window();
    if (!clip_rect(&x, &y, &w, &h, LAYER_SCREEN_W, LAYER_SCREEN_H)) return;
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
            vram_fill_row(win, off, color, seg);
            addr += seg;
            remain -= seg;
        }
    }
}

/* Fill the diagonal blind-sweep pattern: pixels whose diagonal coordinate
 * u = (col-x) + row (forward) or (col-x) + (h-1-row) (reverse) satisfy
 * (u mod period) in [lo, hi) are painted 'color'.  This is the exact
 * coverage set the blinds transition family draws, emitted as one
 * single-pass walk with bank tracking kept across the whole call (each
 * row may carry a dozen separated runs; per-call fill_rect would cost a
 * bank select each). */
void fill_diag_sweep(int x, int y, int w, int h, uint8_t color,
                     int lo, int hi, int period, int reverse)
{
    int cur_bank = -1, row;
    volatile uint8_t *win = hal_vram_get_window();
    if (!clip_rect(&x, &y, &w, &h, LAYER_SCREEN_W, LAYER_SCREEN_H)) return;
    if (period < 1) return;
    if (hi <= lo) return;

    for (row = 0; row < h; row++) {
        int phase = reverse ? (h - 1 - row) : row;
        int per;
        for (per = 0; ; per++) {
            int s, e, remain;
            int lo_pos = per * period + lo;
            int hi_pos = per * period + hi;
            if (lo_pos - phase >= w) break;
            if (hi_pos - phase <= 0) continue;
            s = lo_pos - phase;
            e = hi_pos - phase;
            if (s < 0) s = 0;
            if (e > w) e = w;
            if (e <= s) continue;
            {
                int addr = (y + row) * LAYER_SCREEN_W + x + s;
                remain = e - s;
                while (remain > 0) {
                    int off, seg;
                    VRAM_SET_BANK(addr, cur_bank);
                    off = addr & (VRAM_BANK_SZ - 1);
                    seg = VRAM_BANK_SZ - off;
                    if (seg > remain) seg = remain;
                    vram_fill_row(win, off, color, seg);
                    addr += seg;
                    remain -= seg;
                }
            }
        }
    }
}
void draw_rect(int x, int y, int w, int h, int t, uint8_t color)
{
    int i;
    for (i = 0; i < t; i++) {
        fill_rect(x, y + i, w, 1, color);
        fill_rect(x, y + h - 1 - i, w, 1, color);
        fill_rect(x + i, y, 1, h, color);
        fill_rect(x + w - 1 - i, y, 1, h, color);
    }
}

/* Fast row fill in the banked VRAM window via rep stosb.
 * Fills 'n' bytes at win[off] with 'color'. */
static void vram_fill_row(volatile uint8_t *win, int off, uint8_t color, int n)
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

/* Fill a rectangle with a dither pattern.
 * pattern[8] — 8-byte vertical pattern (e.g. PAT75 for 75% dither)
 * Each byte is a bitmask; pattern[(y + py) & 7] selects the row mask,
 * then bit (px & 7) enables/disables the pixel.
 * Used for semi-transparent dialog background (g_dialog_style bit 0).
 * OPT-12: row-aligned bulk fill — 8-pixel groups with a single mask test
 * and rep stosb, eliminating the per-pixel branch. */
void fill_rect_pattern(int x, int y, int w, int h,
                       const uint8_t pattern[8], uint8_t color)
{
    int px, py, addr, cur_bank = -1;
    uint8_t byte;
    volatile uint8_t *win = hal_vram_get_window();
    if (!clip_rect(&x, &y, &w, &h, LAYER_SCREEN_W, LAYER_SCREEN_H)) return;
    for (py = 0; py < h; py++) {
        byte = pattern[(y + py) & 7];
        addr = (y + py) * LAYER_SCREEN_W + x;
        /* Process leading partial group (px < 8 alignment boundary) */
        px = 0;
        while (px < w && (px & 7)) {
            if (byte & (0x80 >> (px & 7))) {
                VRAM_SET_BANK(addr, cur_bank);
                win[addr & (VRAM_BANK_SZ - 1)] = color;
            }
            addr++;
            px++;
        }
        /* Process full 8-pixel groups: replicate mask byte via lookup */
        while (px + 8 <= w) {
            if (byte) {
                /* At least one bit set: process each set bit as a run */
                int bi;
                for (bi = 0; bi < 8; bi++) {
                    if (byte & (0x80 >> bi)) {
                        int a2 = addr + bi;
                        VRAM_SET_BANK(a2, cur_bank);
                        win[a2 & (VRAM_BANK_SZ - 1)] = color;
                    }
                }
            }
            addr += 8;
            px += 8;
        }
        /* Process trailing partial group */
        while (px < w) {
            if (byte & (0x80 >> (px & 7))) {
                VRAM_SET_BANK(addr, cur_bank);
                win[addr & (VRAM_BANK_SZ - 1)] = color;
            }
            addr++;
            px++;
        }
    }
}

/* Wait for next VBLANK (vertical retrace start).
 * Delegates to HAL for platform-specific port I/O. */
void vblank_wait(void)
{
    hal_vblank_wait();
}
