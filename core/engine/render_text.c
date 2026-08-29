/*
 * Text rendering — ASCII/CJK glyph drawing to VRAM.
 *
 * Relies on VRAM bank-switching via hal.h and glyph
 * data from font.c (8x16 ASCII) / cjk.c (16x16 CJK).
 */
#include "render.h"
#include "font.h"
#include "cjk.h"


/* Blackletter (16x16 Latin alt glyph) flag for dialog text, injected by the
 * NB layer via text_set_blackletter(). Keeps render_text a pure function of
 * its arguments instead of reading NB interpreter global state. */
static int text_blackletter = 0;

void text_set_blackletter(int on)
{
    text_blackletter = on;
}

/* UTF-8 encoded length of the leading byte at *p (1/2/3).
 * REVIEWED: p[1]/p[2] checks rely on NUL termination; if the next byte after
 * NUL is non-zero in a non-terminated buffer this could misparse.
 * By design — all engine strings are NUL-terminated. */
static int utf8_clen(const uint8_t *p)
{
    if ((*p & 0x80) == 0)
        return 1;
    else if ((*p & 0xE0) == 0xC0 && p[1])
        return 2;
    else if ((*p & 0xF0) == 0xE0 && p[1] && p[2])
        return 3;
    else
        return 1;
}

/* Internal glyph drawing: shared by all 4 public wrappers. */
static void draw_glyph_internal(const uint8_t *g, int x, int y, uint8_t color,
                                 int glyph_w, int glyph_h, int bold)
{
    int row, col, cur_bank = -1;
    unsigned short word;
    volatile uint8_t *win = hal_vram_get_window();
    for (row = 0; row < glyph_h; row++) {
        int py = y + row;
        if (py < 0 || py >= LAYER_SCREEN_H) continue;
        word = (unsigned short)(g[row * 2] << 8) | g[row * 2 + 1];
        if (bold) word = word | (word >> 1);
        for (col = 0; col < glyph_w; col++) {
            int px;
            if (!(word & (1u << (15 - col)))) continue;
            px = x + col;
            if (px < 0 || px >= LAYER_SCREEN_W) continue;
            {
                int addr = py * LAYER_SCREEN_W + px;
                VRAM_SET_BANK(addr, cur_bank);
                win[addr & (VRAM_BANK_SZ - 1)] = color;
            }
        }
    }
}

/* Convenience wrappers for draw_glyph_internal. */
#define draw_ascii(g, x, y, c)    draw_glyph_internal(g, x, y, c, FONT_GLYPH_W, FONT_GLYPH_H, 0)
#define draw_ascii_b(g, x, y, c)  draw_glyph_internal(g, x, y, c, FONT_GLYPH_W, FONT_GLYPH_H, 1)
#define draw_cjk(g, x, y, c)      draw_glyph_internal(g, x, y, c, CJK_GLYPH_W,  CJK_GLYPH_H, 0)
#define draw_cjk_b(g, x, y, c)    draw_glyph_internal(g, x, y, c, CJK_GLYPH_W,  CJK_GLYPH_H, 1)

/* Draw mixed ASCII/CJK text to VRAM with auto-line-wrap.
 * s          — UTF-8 source string
 * byte_start — byte offset to resume from (for incremental rendering)
 * x, y       — top-left origin
 * max_width  — line wrap width (in pixels)
 * max_y      — vertical cutoff (rendering stops at this y)
 * bold       — 1 = bold glyphs, 0 = normal
 * color      — palette index for text
 * Returns: byte offset of next unwritten character, or -1 if done. */
int draw_text(const char *s, int byte_start, int x, int y,
              int max_width, int max_y, int bold, uint8_t color)
{
    int cx = x;
    int byte_off = 0;
    const uint8_t *p = (const uint8_t *)s;

    /* Skip ahead to byte_start.
     * byte_start is always a clean character boundary (dialog pagination
     * stores the draw_text() return value, never arbitrary byte offsets).
     * Skipping by whole UTF-8 sequences therefore never lands mid-glyph;
     * if a caller ever passed a mid-sequence offset it would round up to
     * the next boundary rather than reading garbage. */
    while (*p && byte_off < byte_start) {
        int clen = utf8_clen(p);
        p += clen;
        byte_off += clen;
    }

    while (*p) {
        if (y >= max_y)
            return byte_off;
        if (y >= LAYER_SCREEN_H)
            break;

        /* Handle explicit newline */
        if (*p == '\n') {
            cx = x;
            y += TEXT_LINE_HEIGHT;
            p++;
            byte_off++;
            continue;
        }

        /* ASCII (single-byte) character */
        if (*p < 0x80) {
            /* Blackletter subpath: 16x16 Latin glyphs when enabled and the
             * runtime language is not CJK. Wrap/advance use 16 px here. */
            if (text_blackletter) {
                const uint8_t *bg = font_get_glyph_alt(*p);
                if (bg) {
                    if (cx + 16 > x + max_width && cx > x) {
                        cx = x;
                        y += TEXT_LINE_HEIGHT;
                        if (y >= max_y)
                            return byte_off;
                    }
                    if (bold) draw_cjk_b(bg, cx, y, color);
                    else      draw_cjk(bg, cx, y, color);
                    cx += 16;
                    p++;
                    byte_off++;
                    continue;
                }
                /* no alt glyph: fall through to default 8px path */
            }
            /* Wrap if next char exceeds max_width and we've started a word */
            if (cx + 8 > x + max_width && cx > x) {
                cx = x;
                y += TEXT_LINE_HEIGHT;
                if (y >= max_y)
                    return byte_off;
            }
            {
                const uint8_t *g = font_get_glyph(*p);
                if (g) {
                    if (bold) draw_ascii_b(g, cx, y, color);
                    else      draw_ascii(g, cx, y, color);
                }
            }
            cx += 8;
            p++;
            byte_off++;
        } else {
            /* Multi-byte UTF-8: decode code point */
            int cp;
            const uint8_t *g;
            int save_off = byte_off;
            int clen = utf8_clen(p);

            /* REVIEWED: same NUL-termination assumption as skip loop above */
            if (clen == 2) {
                cp = (*p & 0x1F) << 6;
                cp |= p[1] & 0x3F;
            /* 3-byte UTF-8 (0xE0–0xEF) */
            } else if (clen == 3) {
                cp = (*p & 0x0F) << 12;
                cp |= (p[1] & 0x3F) << 6;
                cp |= p[2] & 0x3F;
            } else {
                p++;
                byte_off++;
                continue;
            }
            p += clen;
            byte_off += clen;

            /* CJK wrap (16px per glyph) */
            if (cx + 16 > x + max_width && cx > x) {
                cx = x;
                y += TEXT_LINE_HEIGHT;
                if (y >= max_y)
                    return save_off;
            }
            g = cjk_get_glyph(cp);
            if (g) {
                if (bold) draw_cjk_b(g, cx, y, color);
                else      draw_cjk(g, cx, y, color);
                cx += 16;
            } else {
                cx += 16;
            }
        }
    }
    return -1;
}

/* Calculate the pixel width of a UTF-8 string.
 * ASCII: 8px per char, CJK: 16px per char.  bold param reserved. */
int text_width(const char *s, int bold)
{
    int w = 0;
    (void)bold;
    while (*s) {
        if (*s & 0x80) {
            int clen = utf8_clen((const uint8_t *)s);
            s += clen;
            w += CJK_GLYPH_W;
        } else {
            w += FONT_GLYPH_W;
            s++;
        }
    }
    return w;
}

/* Draw a glyph at 2x scale (16x32 from 8x16 source). */
static void draw_glyph_scaled(const uint8_t *g, int x, int y, uint8_t color)
{
    int row, col, bit, px, py, addr, addr2, cur_bank = -1;
    unsigned short word;
    volatile uint8_t *win = hal_vram_get_window();
    if (x >= LAYER_SCREEN_W || y >= LAYER_SCREEN_H) return;
    for (row = 0; row < FONT_GLYPH_H; row++) {
        word = (unsigned short)(g[row * 2] << 8) | g[row * 2 + 1];
        for (col = 0; col < FONT_GLYPH_W; col++) {
            bit = 15 - col;
            if (!(word & (1u << bit))) continue;
            px = x + col * 2;
            py = y + row * 2;
            if (px < 0 || py < 0) continue;
            if (px >= LAYER_SCREEN_W || py >= LAYER_SCREEN_H) continue;
            addr = py * LAYER_SCREEN_W + px;
            VRAM_SET_BANK(addr, cur_bank);
            win[addr & (VRAM_BANK_SZ - 1)] = color;
            if (px + 1 < LAYER_SCREEN_W) {
                VRAM_SET_BANK(addr + 1, cur_bank);
                win[(addr + 1) & (VRAM_BANK_SZ - 1)] = color;
            }
            if (py + 1 < LAYER_SCREEN_H) {
                addr2 = addr + LAYER_SCREEN_W;
                VRAM_SET_BANK(addr2, cur_bank);
                win[addr2 & (VRAM_BANK_SZ - 1)] = color;
                if (px + 1 < LAYER_SCREEN_W) {
                    VRAM_SET_BANK(addr2 + 1, cur_bank);
                    win[(addr2 + 1) & (VRAM_BANK_SZ - 1)] = color;
                }
            }
        }
    }
}

/* Draw text at 2x scale (16x32 per char) with black outline glow.
 * Each char is 16px wide, 32px tall. Outline uses PAL_CURSOR_BLACK (254). */
void draw_title_large(const char *s, int x, int y, int spacing, uint8_t color)
{
    int i, cx;
    const uint8_t *g;
    for (i = 0; s[i]; i++) {
        g = font_get_glyph((uint8_t)s[i]);
        if (!g) continue;
        cx = x + i * (FONT_GLYPH_W * 2 + spacing);
        draw_glyph_scaled(g, cx - 2, y - 2, PAL_CURSOR_BLACK);
        draw_glyph_scaled(g, cx    , y - 2, PAL_CURSOR_BLACK);
        draw_glyph_scaled(g, cx + 2, y - 2, PAL_CURSOR_BLACK);
        draw_glyph_scaled(g, cx - 2, y    , PAL_CURSOR_BLACK);
        draw_glyph_scaled(g, cx + 2, y    , PAL_CURSOR_BLACK);
        draw_glyph_scaled(g, cx - 2, y + 2, PAL_CURSOR_BLACK);
        draw_glyph_scaled(g, cx    , y + 2, PAL_CURSOR_BLACK);
        draw_glyph_scaled(g, cx + 2, y + 2, PAL_CURSOR_BLACK);
        draw_glyph_scaled(g, cx, y, color);
    }
}

/* Draw text at 2x scale (16x32 per char) with black outline glow.
 * Like draw_title_large but spacing=1 and public for settings_menu use. */
void draw_text_outlined_2x(const char *s, int byte_start,
                           int x, int y, uint8_t color)
{
    int i, cx;
    const uint8_t *g;
    (void)byte_start;
    for (i = 0; s[i]; i++) {
        g = font_get_glyph((uint8_t)s[i]);
        if (!g) continue;
        cx = x + i * (FONT_GLYPH_W * 2 + 1);
        draw_glyph_scaled(g, cx - 2, y - 2, PAL_CURSOR_BLACK);
        draw_glyph_scaled(g, cx    , y - 2, PAL_CURSOR_BLACK);
        draw_glyph_scaled(g, cx + 2, y - 2, PAL_CURSOR_BLACK);
        draw_glyph_scaled(g, cx - 2, y    , PAL_CURSOR_BLACK);
        draw_glyph_scaled(g, cx + 2, y    , PAL_CURSOR_BLACK);
        draw_glyph_scaled(g, cx - 2, y + 2, PAL_CURSOR_BLACK);
        draw_glyph_scaled(g, cx    , y + 2, PAL_CURSOR_BLACK);
        draw_glyph_scaled(g, cx + 2, y + 2, PAL_CURSOR_BLACK);
        draw_glyph_scaled(g, cx, y, color);
    }
}
