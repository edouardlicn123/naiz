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
 */
#include "render.h"

/* Forward declarations for static bulk helpers */
static void vram_fill_row(volatile uint8_t *win, int off, uint8_t color, int n);
static void vram_row_read(volatile uint8_t *win, int off, uint8_t *dst, int n);
static void vram_row_write(const uint8_t *src, volatile uint8_t *win, int off, int n);

/* Clip a rectangle to [0, max_w) x [0, max_h).
 * Mutates (x,y,w,h) in-place.  Returns 0 if fully clipped (nothing to draw). */
static int clip_rect(int *x, int *y, int *w, int *h, int max_w, int max_h)
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

/* Blit an entire MagImage to VRAM at (x,y).
 * No transparency — every pixel is written.  Delegates to vram_blit_sprite. */
void vram_blit(const MagImage *img, int x, int y)
{
    vram_blit_sprite(img, x, y, PAL_NO_TRANSPARENCY, 0, 0);
}

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

/* Blit a sprite image to VRAM with transparency and optional mirror.
 * Optimized: processes each screen line in bank-aligned segments.
 * Within each segment, non-transparent pixels are written without per-pixel
 * bank checking.  Run detection scans the source (in regular RAM), then
 * writes contiguous pixel runs to VRAM in tight loops. */
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

/* Wait for next VBLANK (vertical retrace start).
 * Delegates to HAL for platform-specific port I/O. */
void vblank_wait(void)
{
    hal_vblank_wait();
}
