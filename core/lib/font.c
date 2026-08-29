/*
 * font — ASCII 8×16 点阵字形加载器
 *
 * 加载 FONT.DAT（MHVN98 兼容格式），解析区间列表和 info 条目，
 * 提取 1-bit 字形位图并缓存到 glyph_cache[256][32]。
 * 仅支持 ASCII（0-127），每个字符 8×16 像素，打包为 32 字节。
 * 无平台依赖，属于 core/lib/ 平台无关库。
 *
 * FONT.DAT 格式：
 *   - 区间列表：128 个 entry，每 entry 4 字节（start/end LE uint16）
 *   - info 列表：每 entry 4 字节（offset/gw/gh）
 *   - 字形数据：1-bit 位图，每行 (gw+7)/8 字节，行间 2 字节对齐
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "font.h"
#include "naiz_file.h"
#include "endian.h"

#define RANGE_COUNT    128
#define RANGE_ENTRY_SZ 4
#define INFO_ENTRY_SZ  4

static unsigned char glyph_cache[256][FONT_GLYPH_BYTES];
static int font_loaded;

/* Parse a FONT.DAT buffer into the given 256-entry glyph cache.
 * Same layout as font_init: range list, info list, 1-bit glyph bitmaps.
 * Returns 0 on success, -1 if the buffer contains no usable glyphs. */
static int parse_font_data(const unsigned char *buf, long fsize,
                           unsigned char (*cache)[FONT_GLYPH_BYTES])
{
    int i, num_chars;
    int info_base, char_idx, n, cp, roff;
    unsigned short r_start, r_end;

    /* First pass: count characters across all range slots. */
    num_chars = 0;
    for (i = 0; i < RANGE_COUNT; i++) {
        int off = i * RANGE_ENTRY_SZ;
        if (off + 4 > fsize) break;
        r_start = read16_le(buf + off);
        r_end   = read16_le(buf + off + 2);
        if (r_start == 0xFFFF) continue;
        num_chars += r_end - r_start + 1;
    }
    if (num_chars == 0)
        return -1;

    /* Second pass: fill cache from each range's info + glyph data. */
    info_base = RANGE_COUNT * RANGE_ENTRY_SZ;
    char_idx = 0;
    for (i = 0; i < RANGE_COUNT; i++) {
        roff = i * RANGE_ENTRY_SZ;
        if (roff + 4 > fsize) break;
        r_start = read16_le(buf + roff);
        r_end   = read16_le(buf + roff + 2);
        if (r_start == 0xFFFF) continue;

        n = r_end - r_start + 1;
        for (cp = r_start; cp <= r_end && char_idx < 256 && cp < 256; cp++, char_idx++) {
            int ioff, gaddr, gw, gh;
            int src_off, bytes_per_row, row_bytes, row, dst_row;

            ioff = info_base + char_idx * INFO_ENTRY_SZ;
            if (ioff + 4 > fsize) break;
            gaddr = (int)read16_le(buf + ioff);
            gw    = buf[ioff+2];
            gh    = buf[ioff+3];

            if (gaddr >= fsize) continue;

            src_off = gaddr;
            bytes_per_row = (gw + 7) / 8;
            row_bytes = bytes_per_row * 2;
            for (row = 0; row < gh && row < FONT_GLYPH_H; row++) {
                dst_row = row * 2;
                if (src_off + 2 <= fsize && dst_row + 1 < FONT_GLYPH_BYTES) {
                    cache[cp][dst_row]   = buf[src_off];
                    cache[cp][dst_row+1] = buf[src_off + 1];
                }
                src_off += row_bytes;
            }
        }
    }
    return 0;
}

/* Load FONT.DAT, parse range list and 1-bit glyph bitmaps, cache results in glyph_cache[256][32].
 * @param filename  Path to FONT.DAT
 * @return 0 on success, -1 on failure (file not found / OOM / bad format) */
int font_init(const char *filename)
{
    unsigned char *buf;
    long fsize;

    buf = (unsigned char *)file_read_all(filename, &fsize);
    if (!buf) return -1;

    memset(glyph_cache, 0, sizeof(glyph_cache));
    if (parse_font_data(buf, (int)fsize, glyph_cache) != 0) {
        free(buf);
        return -1;
    }

    free(buf);
    font_loaded = 1;
    return 0;
}

/* Get the 8x16 glyph bitmap for ASCII character ch.
 * @param ch  ASCII codepoint (0-127), returns NULL for values > 127
 * @return Read-only pointer to 32-byte glyph bitmap, or NULL if not loaded or out of range */
const unsigned char *font_get_glyph(unsigned char ch)
{
    if (!font_loaded || ch > 127) return NULL;
    return glyph_cache[(int)ch];
}

/* Alternate (blackletter 16x16 Latin) glyph cache. Loaded from BLACK.DAT. */
static unsigned char alt_glyph_cache[256][FONT_GLYPH_BYTES];
static int alt_loaded;

/* Load an alternate glyph table (BLACK.DAT, blackletter 16x16 Latin glyphs)
 * into alt_glyph_cache.  Non-fatal: parse failures just leave the table empty.
 * @param filename  Path to BLACK.DAT
 * @return 0 on success, -1 on failure (file not found / no glyphs) */
int font_load_alt(const char *filename)
{
    unsigned char *buf;
    long fsize;

    buf = (unsigned char *)file_read_all(filename, &fsize);
    if (!buf) return -1;

    memset(alt_glyph_cache, 0, sizeof(alt_glyph_cache));
    if (parse_font_data(buf, (int)fsize, alt_glyph_cache) != 0) {
        free(buf);
        return -1;
    }

    free(buf);
    alt_loaded = 1;
    return 0;
}

/* Get the 16x16 blackletter glyph bitmap for ASCII character ch.
 * @param ch  ASCII codepoint (0-127), returns NULL for values > 127
 * @return Read-only pointer to 32-byte glyph bitmap, or NULL if not loaded/out of range */
const unsigned char *font_get_glyph_alt(unsigned char ch)
{
    if (!alt_loaded || ch > 127) return NULL;
    return alt_glyph_cache[(int)ch];
}


