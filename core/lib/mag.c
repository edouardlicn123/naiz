/*
 * MAG (MAKI02) image decoder — PC-98 dominant image format.
 * Per spec: flag A (bitstream) + flag B (nibble XOR) + color index stream
 *           + action buffer with 15 relative-copy positions.
 *
 * Reference: devdocs/0.1版开发文档总结.html#doc-01
 */
#include "mag.h"
#include "mag_format.h"
#include "endian.h"
#include <stdlib.h>
#include <string.h>

/*=== Helpers =============================================================*/

/*
 * BitReader — Bit-level reader that extracts bits from a byte array (MSB first).
 * @base     Byte array base
 * @byte_len Total byte count
 * @byte_pos Current byte position
 * @bit_mask Current bit mask (0x80 -> 0x40 -> ... -> 0x01)
 */
typedef struct { const uint8_t *base; int byte_len; int byte_pos; int bit_mask; } BitReader;

/*
 * br_init — Initialize a BitReader.
 * @r     Target BitReader
 * @base Source data
 * @len  Data length in bytes
 */
static void br_init(BitReader *r, const uint8_t *base, int len) {
    r->base = base; r->byte_len = len; r->byte_pos = 0; r->bit_mask = 0x80;
}

/*
 * br_read — Read 1 bit from the BitReader.
 * @param r  BitReader instance
 * @return 0 or 1; -1 on overflow
 */
static int br_read(BitReader *r) {
    int b;
    if (r->byte_pos >= r->byte_len) return -1;
    b = (r->base[r->byte_pos] & r->bit_mask) ? 1 : 0;
    r->bit_mask >>= 1;          /* 移到下一位 */
    if (!r->bit_mask) {         /* 当前字节已读完 */
        r->bit_mask = 0x80;    /* 重置掩码到最高位 */
        r->byte_pos++;          /* 前进到下一字节 */
    }
    return b;
}

/*
 * expand_comp — Expand a bit-limited color component to 8 bits.
 * Strategy: replicate low bits into high bits (e.g. 5-bit -> 5<<3 | 5>>2).
 * @param v     Raw component value
 * @param bits  Effective bit depth (3/4/5/8)
 * @return 8-bit expanded value
 */
static uint8_t expand_comp(uint8_t v, int bits) {
    uint8_t mask;
    int shift, rshift;
    if (bits >= 8) return v;
    mask = (1u << bits) - 1;    /* 取低位掩码 */
    v &= mask;
    if (bits == 0) return 0;
    shift = 8 - bits;           /* 左移位数 */
    rshift = bits - shift;      /* 右移位数（若 bits < 4 时为负） */
    if (rshift > 0)
        return (uint8_t)((v << shift) | (v >> rshift));  /* 低位复制到高位 */
    /* bits < 4: single shift cannot fill the low bits, so replicate the
     * whole n-bit pattern MSB-first (matches the Python codec). */
    {
        uint8_t result = 0;
        int i;
        for (i = 0; i < 8; i++) {
            int bit_idx = (bits - 1) - (i % bits);
            result = (uint8_t)((result << 1) | ((v >> bit_idx) & 1));
        }
        return result;
    }
}

/*=== Main decoder ========================================================*/

/*
 * mag_decode — Decode a MAKI02 image.
 * Complete pipeline:
 *   1) Validate MAKI02 signature and fixed header
 *   2) Parse palette (GRB order, variable bit depth)
 *   3) Decompress pixel data using flag A/B + color stream + action buffer
 *   4) Convert 4bpp -> 8bpp
 *   5) Strip left/right padding
 *   6) Build MagImage struct
 * @param data Raw MAG file data
 * @param size Data size in bytes
 * @param out  Output pointer (points to allocated MagImage on success)
 * @return 0 on success, 1 on failure (bad format / OOM / bounds error)
 */
int mag_decode(const uint8_t *data, int size, MagImage **out) {
    int pos, hdr_start, start_marker, model_code, model_flags, screen_mode;
    int left, top, right, bottom;
    int flag_a_off, flag_b_off, flag_b_size_s, color_off, color_size_s;
    int bpp, palette_end, palette_bytes, num_colors, pbits;
    uint32_t u_flag_a_off, u_flag_b_off, u_flag_b_size_s, u_color_off, u_color_size_s;
    uint8_t pal_r[256], pal_g[256], pal_b[256];
    const uint8_t *flag_a, *flag_b, *color;
    int color_byte_len, flag_b_byte_len;
    int px_per_byte, pad_left, pad_right, byte_width, pixel_width, pixel_height;
    int output_total, action_size;
    uint8_t *output, *action;
    BitReader fa;               /* flag A 位读取器 */
    int fb_pos, col_pos, out_pos, act_idx;
    int row_bytes;
    int pad_px_left, pad_px_right, crop_width, crop_height;
    uint8_t *cropped;
    MagImage *img;
    int is_sprite_flag;
    int i;

    *out = NULL;
    if (size < 40) return 1;

    pos = 0;

    /* -- 签名: 8 字节 "MAKI02  "（含 2 空格） -- */
    if (pos + MAG_SIGNATURE_LEN > size) return 1;
    if (memcmp(data + pos, MAG_SIGNATURE, MAG_SIGNATURE_LEN) != 0) return 1;
    pos += MAG_SIGNATURE_LEN;

    /* -- 机型 ID: 4 字节 ASCII -- */
    if (pos + 4 > size) return 1;
    pos += 4;

    /* -- 检查用户字符串是否以 "sprt" 开头 → 标记为精灵图 -- */
    is_sprite_flag = (pos + 4 <= size && data[pos] == 's' && data[pos + 1] == 'p'
                      && data[pos + 2] == 'r' && data[pos + 3] == 't');

    /* -- Shift-JIS 用户字符串，以 MAG_USER_TERM (0x1A) 结尾 -- */
    while (pos < size && data[pos] != MAG_USER_TERM) pos++;
    if (pos >= size) return 1;
    pos++; /* 跳过 0x1A */

    /* -- 固定头 32 字节 -- */
    hdr_start = pos;
    if (hdr_start + MAG_HEADER_SIZE > size) return 1;
    start_marker  = data[pos]; pos++;  /* 应为 0x00 */
    model_code    = data[pos]; pos++;  /* 决定调色板位深 */
    model_flags   = data[pos]; pos++;  /* PC-98 暂不使用 */
    screen_mode   = data[pos]; pos++;  /* bit7=1 → 8bpp, else 4bpp */
    left          = read16_le(data + pos); pos += 2;
    top           = read16_le(data + pos); pos += 2;
    right         = read16_le(data + pos); pos += 2;
    bottom        = read16_le(data + pos); pos += 2;
    u_flag_a_off    = read32_le(data + pos); pos += 4;  /* flag A 相对 hdr_start 偏移 */
    u_flag_b_off    = read32_le(data + pos); pos += 4;  /* flag B 偏移 */
    u_flag_b_size_s = read32_le(data + pos); pos += 4;  /* flag B 大小 */
    u_color_off     = read32_le(data + pos); pos += 4;  /* color stream 偏移 */
    u_color_size_s  = read32_le(data + pos); pos += 4;  /* color stream 大小 */

    flag_a_off    = (int)u_flag_a_off;
    flag_b_off    = (int)u_flag_b_off;
    flag_b_size_s = (int)u_flag_b_size_s;
    color_off     = (int)u_color_off;
    color_size_s  = (int)u_color_size_s;

    if (flag_a_off < 0 || flag_b_off < 0 || color_off < 0) return 1;
    if (flag_b_size_s < 0 || color_size_s < 0) return 1;

    (void)model_flags; /* unused for PC-98 */
    if (start_marker != 0x00) return 1;

    /* -- 从 screen_mode 确定位深 -- */
    bpp = (screen_mode & 0x80) ? 8 : 4;

    /* -- 调色板：GRB 三字节组，从当前位置到 flag A 偏移之间 -- */
    if (flag_a_off > size - hdr_start) return 1;
    palette_end   = hdr_start + flag_a_off;
    palette_bytes = palette_end - pos;
    num_colors    = palette_bytes / 3;  /* 每个颜色 GRB 各 1 字节 */
    if (num_colors < 16 || num_colors > 256) return 1;
    if (pos + palette_bytes > size) return 1;

    /* -- 根据 model_code 决定调色板各分量的有效位深 -- */
    pbits = 4;
    if (model_code == MAG_MODEL_3BIT)  pbits = 3;   /* 3-bit 分量 */
    else if (model_code == MAG_MODEL_5BIT) pbits = 5;   /* 5-bit 分量 */
    else if (model_code == MAG_MODEL_8BIT) pbits = 8;   /* 8-bit 分量 */
    /* 256 色时除特定 model 外一律为 8-bit */
    if (num_colors == 256 && model_code != MAG_MODEL_3BIT && model_code != MAG_MODEL_8BIT2) pbits = 8;

    for (i = 0; i < num_colors; i++) {
        pal_g[i] = expand_comp(data[pos++], pbits);  /* G 在前 */
        pal_r[i] = expand_comp(data[pos++], pbits);  /* R 中间 */
        pal_b[i] = expand_comp(data[pos++], pbits);  /* B 最后 */
    }

    /* -- 指向三个数据流 -- */
    if ((unsigned long)(hdr_start + flag_b_off) + (unsigned long)flag_b_size_s > (unsigned long)size) return 1;
    if ((unsigned long)(hdr_start + color_off) + (unsigned long)color_size_s > (unsigned long)size) return 1;
    flag_a          = data + hdr_start + flag_a_off;
    flag_b          = data + hdr_start + flag_b_off;
    color           = data + hdr_start + color_off;
    color_byte_len  = color_size_s;
    flag_b_byte_len = flag_b_size_s;

    /*
     * -- 计算填充后的尺寸 --
     * MAKI02 行宽以 4 字节对齐（quad-byte aligned）。
     * 每字节的像素数 = 8 / bpp（4bpp→2px/byte, 8bpp→1px/byte）。
     */
    px_per_byte  = 8 / bpp;
    pad_left     = (left / px_per_byte) & ~3;        /* 左边界 4 字节对齐 */
    pad_right    = (right / px_per_byte + 4) & ~3;   /* 右边界 4 字节对齐 */
    byte_width   = pad_right - pad_left;              /* 对齐后行宽（字节） */
    pixel_width  = byte_width * px_per_byte;          /* 对齐后像素宽 */
    pixel_height = bottom - top + 1;                  /* 实际像素高 */
    if (left > right || top > bottom) return 1;
    {
        long tmp_total = (long)byte_width * (long)pixel_height;
        if (tmp_total <= 0 || tmp_total > 1024 * 1024) return 1;
        output_total = (int)tmp_total;
    }

    /* action buffer 大小为行宽的 1/4（每 4 字节 1 个 action） */
    if (flag_b_off <= flag_a_off) return 1;
    action_size = byte_width / 4;
    if (action_size <= 0) return 1;

    /* -- 分配缓冲区 -- */
    output = (uint8_t *)calloc(1, output_total + 16);
    action = (uint8_t *)calloc(1, action_size + 4);
    if (!output || !action) { free(output); free(action); return 1; }

    /*
     * -- 解压主循环 --
     *
     * 核心思想：每次处理 2 像素（2 字节输出）。
     * 1) flag A 提供 bitstream，每位控制是否用 flag B XOR 更新 action buffer
     * 2) action buffer 的当前半字节（高/低 4 位）= n
     * 3) n=0 时：从 color stream 读取 2 字节直接写入输出
     * 4) n>0 时：从已解压区域相对位置复制 2 字节
     *    n=1~3:  本行内向左偏移
     *    n=4~7:  上行某位置
     *    n=8~11: 上两行某位置
     *    n=12~15:上三行某位置
     */
    br_init(&fa, flag_a, flag_b_off - flag_a_off);
    fb_pos   = 0;
    col_pos  = 0;
    out_pos  = 0;
    act_idx  = 0;
    row_bytes = byte_width;

    {
        int decode_ok = 1;

    while (out_pos + 1 < output_total) {
        int a, ab, nib, n, ref_off, src;
        uint16_t v;

        /* 从 flag A 读取 1 bit */
        a = br_read(&fa);
        if (a < 0) { decode_ok = 0; break; }

        /* flag A=1: 用 flag B 的当前字节与 action buffer 当前元素异或 */
        if (a == 1) {
            if (fb_pos < flag_b_byte_len) {
                action[act_idx % action_size] ^= flag_b[fb_pos++];
            }
        }

        /* 取出 action buffer 当前值 */
        ab = action[act_idx % action_size];
        act_idx++;

        /*
         * 每个 action 字节处理 2 个 nibble（高 4 位先，低 4 位后），
         * 对应 2 组像素（每组 2 字节 = 2 像素 in 8bpp, 4 像素 in 4bpp）。
         */
        for (nib = 0; nib < 2; nib++) {
            if (out_pos + 1 >= output_total) break;
            n = (nib == 0) ? (ab >> 4) : (ab & 0x0F);

            if (n == 0) {
                /* n=0: 从 color stream 读取新像素数据 */
                v = 0;
                if (col_pos + 1 < color_byte_len) {
                    v = (uint16_t)(color[col_pos] | ((uint16_t)color[col_pos + 1] << 8));
                    col_pos += 2;
                } else {
                    decode_ok = 0;
                    break;
                }
                output[out_pos]     = (uint8_t)(v & 0xFF);      /* 低字节 */
                output[out_pos + 1] = (uint8_t)(v >> 8);        /* 高字节 */
            } else {
                /*
                 * n>0: 从已解压区域相对位置复制 2 字节
                 * 15 种偏移模式（n=1~15）：
                 *   n=1~3    → 本行向左偏移 -2* n
                 *   n=4~7    → 上行偏移 -(row_bytes) + -2*(n-4)
                 *   n=8~11   → 上两行偏移 -2*row_bytes + -2*(n-8)
                 *   n=12~15  → 上三行偏移 -3*row_bytes + -2*(n-12)
                 */
                if (n <= 3) {
                    ref_off = -2 * (int)n;                          /* 本行内同行的水平偏移 */
                } else if (n <= 7) {
                    ref_off = -(int)row_bytes + (-2 * ((int)n - 4)); /* 上一行 */
                } else if (n <= 11) {
                    ref_off = -2 * (int)row_bytes + (-2 * ((int)n - 8));  /* 上两行 */
                } else {
                    ref_off = -3 * (int)row_bytes + (-2 * ((int)n - 12)); /* 上三行 */
                }
                src = out_pos + ref_off;
                if ((unsigned int)src < (unsigned int)output_total - 1) {
                    output[out_pos]     = output[src];
                    output[out_pos + 1] = output[src + 1];
                } else {
                    free(output);
                    free(action);
                    return 1;
                }
            }
            out_pos += 2;  /* 前进 2 字节（对应 2/4 像素） */
        }
    }

    if (!decode_ok) { free(output); free(action); return 1; }

    } /* end decode block */

    /*
     * -- 4bpp → 8bpp 转换 --
     * 4bpp 时每个字节含 2 个像素（高 4 位+低 4 位），
     * 转换为每个像素 1 字节的平面格式。
     */
    if (bpp == 4) {
        int final_size;
        uint8_t *final_pixels;
        if (pixel_width <= 0 || pixel_height <= 0) { free(output); free(action); return 1; }
        final_size = pixel_width * pixel_height;
        final_pixels = (uint8_t *)malloc(final_size);
        if (!final_pixels) { free(output); free(action); return 1; }
        for (i = 0; i < pixel_width * pixel_height; i++) {
            int byte_idx = i / 2;
            final_pixels[i] = (i & 1) ? (output[byte_idx] >> 4) : (output[byte_idx] & 0x0F);
        }
        free(output);
        output = final_pixels;
    }

    /*
     * -- 去除左右 padding --
     * 恢复实际裁剪尺寸（header 中的 left/right 为实际边界）。
     */
    pad_px_left  = left - (pad_left * px_per_byte);
    pad_px_right = (pad_right * px_per_byte) - 1 - right;
    crop_width   = right - left + 1;
    crop_height  = pixel_height;

    if (pad_px_left > 0 || pad_px_right > 0 || crop_width != pixel_width) {
        int y;
        /* Pixel buffer is always 1 byte/pixel here (8bpp direct, 4bpp already
         * expanded), so cropping is a per-row memcpy of crop_width bytes. */
        cropped = (uint8_t *)malloc(crop_width * crop_height);
        if (!cropped) { free(output); free(action); return 1; }
        for (y = 0; y < crop_height; y++) {
            memcpy(cropped + (size_t)y * crop_width,
                   output + (size_t)y * pixel_width + pad_px_left,
                   (size_t)crop_width);
        }
        free(output);
        output = cropped;
        pixel_width  = crop_width;
        pixel_height = crop_height;
    }

    /* -- 构建 MagImage 结构 -- */
    img = (MagImage *)malloc(sizeof(MagImage));
    if (!img) { free(output); free(action); return 1; }
    img->width      = pixel_width;
    img->height     = pixel_height;
    img->pixels     = output;
    img->bpp        = bpp;
    img->num_colors = num_colors;
    img->is_sprite  = is_sprite_flag;
    img->refcount   = 1;
    for (i = 0; i < num_colors; i++) {
        img->palette_r[i] = pal_r[i];
        img->palette_g[i] = pal_g[i];
        img->palette_b[i] = pal_b[i];
    }
    for (; i < 256; i++) {
        img->palette_r[i] = img->palette_g[i] = img->palette_b[i] = 0;
    }

    free(action);
    *out = img;
    return 0;
}

/*
 * mag_read_palette — Read palette data from a MAG file without decoding pixels.
 * Useful for quick preview or pre-loading the palette.
 * @param data  MAG file data
 * @param size  Data size in bytes
 * @param pal_r Output R component array [256]
 * @param pal_g Output G component array [256]
 * @param pal_b Output B component array [256]
 * @return Number of colors (16 or 256), or -1 on failure
 */
int mag_read_palette(const uint8_t *data, int size,
                     uint8_t pal_r[256], uint8_t pal_g[256], uint8_t pal_b[256]) {
    int pos, hdr_start, model_code, flag_a_off;
    int palette_bytes, num_colors, pbits;
    int i;

    if (size < 40) return -1;

    pos = 0;
    if (pos + MAG_SIGNATURE_LEN > size) return -1;
    if (memcmp(data + pos, MAG_SIGNATURE, MAG_SIGNATURE_LEN) != 0) return -1;
    pos += MAG_SIGNATURE_LEN;

    if (pos + 4 > size) return -1;
    pos += 4;  /* machine ID */

    while (pos < size && data[pos] != MAG_USER_TERM) pos++;
    if (pos >= size) return -1;
    pos++;  /* MAG_USER_TERM */

    hdr_start = pos;
    if (hdr_start + MAG_HEADER_SIZE > size) return -1;
    pos++;  /* start_marker (0x00) */
    model_code = data[pos]; pos++;
    pos++;  /* model_flags */
    pos++;  /* screen_mode */
    pos += 2; pos += 2; pos += 2; pos += 2;  /* left, top, right, bottom */
    flag_a_off = read32_le(data + pos); pos += 4;
    /* 跳过头剩余字段直接到调色板开始处 */
    pos = hdr_start + 32;

    palette_bytes = (hdr_start + flag_a_off) - pos;
    num_colors = palette_bytes / 3;
    if (num_colors < 16 || num_colors > 256) return -1;
    if (pos + palette_bytes > size) return -1;

    pbits = 4;
    if (model_code == MAG_MODEL_3BIT)  pbits = 3;
    else if (model_code == MAG_MODEL_5BIT) pbits = 5;
    else if (model_code == MAG_MODEL_8BIT) pbits = 8;
    if (num_colors == 256 && model_code != MAG_MODEL_3BIT && model_code != MAG_MODEL_8BIT2) pbits = 8;

    for (i = 0; i < num_colors; i++) {
        pal_g[i] = expand_comp(data[pos++], pbits);
        pal_r[i] = expand_comp(data[pos++], pbits);
        pal_b[i] = expand_comp(data[pos++], pbits);
    }
    for (; i < 256; i++) {
        pal_r[i] = pal_g[i] = pal_b[i] = 0;
    }

    return num_colors;
}

/*
 * mag_release — Decrement refcount; free pixels + struct at zero.
 * @param img  MagImage to release (NULL-safe)
 */
void mag_release(MagImage *img) {
    if (img && --img->refcount <= 0) {
        if (!img->is_pool)
            free(img->pixels);  /* Free pixel buffer (unless pool-allocated) */
        free(img);          /* Free struct itself */
    }
}

/*
 * mag_retain — Increment refcount, return same pointer.
 * @param img  MagImage (NULL-safe)
 */
MagImage *mag_retain(MagImage *img) {
    if (img) img->refcount++;
    return img;
}

/*
 * mag_decode_into — Decode MAG using a pre-allocated work buffer.
 * Same logic as mag_decode but all internal allocations (output, action,
 * cropped, 4bpp expansion) come from the caller-provided buffer.
 * On success the MagImage.pixels points into `buf`; is_pool=1 tells
 * mag_release not to free the pixel data.
 */
int mag_decode_into(const uint8_t *data, int size,
                    uint8_t *buf, int buf_size, MagImage **out) {
    int pos, hdr_start, start_marker, model_code, model_flags, screen_mode;
    int left, top, right, bottom;
    int flag_a_off, flag_b_off, flag_b_size_s, color_off, color_size_s;
    int bpp, palette_end, palette_bytes, num_colors, pbits;
    uint32_t u_flag_a_off, u_flag_b_off, u_flag_b_size_s, u_color_off, u_color_size_s;
    uint8_t pal_r[256], pal_g[256], pal_b[256];
    const uint8_t *flag_a, *flag_b, *color;
    int color_byte_len, flag_b_byte_len;
    int px_per_byte, pad_left, pad_right, byte_width, pixel_width, pixel_height;
    int output_total, action_size;
    uint8_t *output, *action;
    BitReader fa;
    int fb_pos, col_pos, out_pos, act_idx;
    int row_bytes;
    int pad_px_left, pad_px_right, crop_width, crop_height;
    uint8_t *cropped;
    MagImage *img;
    int is_sprite_flag;
    int i;

    /* Pool allocation offsets */
    int off_output, off_action, off_final, off_cropped, off_img;
    int final_size, cropped_size;

    *out = NULL;
    if (size < 40) return 1;

    pos = 0;

    if (pos + MAG_SIGNATURE_LEN > size) return 1;
    if (memcmp(data + pos, MAG_SIGNATURE, MAG_SIGNATURE_LEN) != 0) return 1;
    pos += MAG_SIGNATURE_LEN;

    if (pos + 4 > size) return 1;
    pos += 4;

    is_sprite_flag = (pos + 4 <= size && data[pos] == 's' && data[pos + 1] == 'p'
                      && data[pos + 2] == 'r' && data[pos + 3] == 't');

    while (pos < size && data[pos] != MAG_USER_TERM) pos++;
    if (pos >= size) return 1;
    pos++;

    hdr_start = pos;
    if (hdr_start + MAG_HEADER_SIZE > size) return 1;
    start_marker  = data[pos]; pos++;
    model_code    = data[pos]; pos++;
    model_flags   = data[pos]; pos++;
    screen_mode   = data[pos]; pos++;
    left          = read16_le(data + pos); pos += 2;
    top           = read16_le(data + pos); pos += 2;
    right         = read16_le(data + pos); pos += 2;
    bottom        = read16_le(data + pos); pos += 2;
    u_flag_a_off    = read32_le(data + pos); pos += 4;
    u_flag_b_off    = read32_le(data + pos); pos += 4;
    u_flag_b_size_s = read32_le(data + pos); pos += 4;
    u_color_off     = read32_le(data + pos); pos += 4;
    u_color_size_s  = read32_le(data + pos); pos += 4;

    flag_a_off    = (int)u_flag_a_off;
    flag_b_off    = (int)u_flag_b_off;
    flag_b_size_s = (int)u_flag_b_size_s;
    color_off     = (int)u_color_off;
    color_size_s  = (int)u_color_size_s;

    if (flag_a_off < 0 || flag_b_off < 0 || color_off < 0) return 1;
    if (flag_b_size_s < 0 || color_size_s < 0) return 1;

    (void)model_flags;
    if (start_marker != 0x00) return 1;

    bpp = (screen_mode & 0x80) ? 8 : 4;

    if (flag_a_off > size - hdr_start) return 1;
    palette_end   = hdr_start + flag_a_off;
    palette_bytes = palette_end - pos;
    num_colors    = palette_bytes / 3;
    if (num_colors < 16 || num_colors > 256) return 1;
    if (pos + palette_bytes > size) return 1;

    pbits = 4;
    if (model_code == MAG_MODEL_3BIT)  pbits = 3;
    else if (model_code == MAG_MODEL_5BIT) pbits = 5;
    else if (model_code == MAG_MODEL_8BIT) pbits = 8;
    if (num_colors == 256 && model_code != MAG_MODEL_3BIT && model_code != MAG_MODEL_8BIT2) pbits = 8;

    for (i = 0; i < num_colors; i++) {
        pal_g[i] = expand_comp(data[pos++], pbits);
        pal_r[i] = expand_comp(data[pos++], pbits);
        pal_b[i] = expand_comp(data[pos++], pbits);
    }

    if ((unsigned long)(hdr_start + flag_b_off) + (unsigned long)flag_b_size_s > (unsigned long)size) return 1;
    if ((unsigned long)(hdr_start + color_off) + (unsigned long)color_size_s > (unsigned long)size) return 1;
    flag_a          = data + hdr_start + flag_a_off;
    flag_b          = data + hdr_start + flag_b_off;
    color           = data + hdr_start + color_off;
    color_byte_len  = color_size_s;
    flag_b_byte_len = flag_b_size_s;

    px_per_byte  = 8 / bpp;
    pad_left     = (left / px_per_byte) & ~3;
    pad_right    = (right / px_per_byte + 4) & ~3;
    byte_width   = pad_right - pad_left;
    pixel_width  = byte_width * px_per_byte;
    pixel_height = bottom - top + 1;
    if (left > right || top > bottom) return 1;
    {
        long tmp_total = (long)byte_width * (long)pixel_height;
        if (tmp_total <= 0 || tmp_total > 1024 * 1024) return 1;
        output_total = (int)tmp_total;
    }

    if (flag_b_off <= flag_a_off) return 1;
    action_size = byte_width / 4;
    if (action_size <= 0) return 1;

    /* -- Compute pool layout -- */
    off_output = 0;
    off_action = off_output + output_total + 16;
    off_final  = off_action + action_size + 4;
    final_size = (bpp == 4) ? pixel_width * pixel_height : 0;
    off_cropped = off_final + final_size;

    pad_px_left  = left - (pad_left * px_per_byte);
    pad_px_right = (pad_right * px_per_byte) - 1 - right;
    crop_width   = right - left + 1;
    crop_height  = pixel_height;
    cropped_size = (pad_px_left > 0 || pad_px_right > 0 || crop_width != pixel_width)
                   ? crop_width * crop_height : 0;

    off_img = off_cropped + cropped_size + sizeof(MagImage);

    if (off_img > buf_size) return 1;

    output = buf + off_output;
    action = buf + off_action;
    memset(output, 0, output_total + 16);
    memset(action, 0, action_size + 4);

    /* -- Decompression loop (identical to mag_decode) -- */
    br_init(&fa, flag_a, flag_b_off - flag_a_off);
    fb_pos   = 0;
    col_pos  = 0;
    out_pos  = 0;
    act_idx  = 0;
    row_bytes = byte_width;

    {
        int decode_ok = 1;

    while (out_pos + 1 < output_total) {
        int a, ab, nib, n, ref_off, src;
        uint16_t v;

        a = br_read(&fa);
        if (a < 0) { decode_ok = 0; break; }

        if (a == 1) {
            if (fb_pos < flag_b_byte_len) {
                action[act_idx % action_size] ^= flag_b[fb_pos++];
            }
        }

        ab = action[act_idx % action_size];
        act_idx++;

        for (nib = 0; nib < 2; nib++) {
            if (out_pos + 1 >= output_total) break;
            n = (nib == 0) ? (ab >> 4) : (ab & 0x0F);

            if (n == 0) {
                v = 0;
                if (col_pos + 1 < color_byte_len) {
                    v = (uint16_t)(color[col_pos] | ((uint16_t)color[col_pos + 1] << 8));
                    col_pos += 2;
                } else {
                    decode_ok = 0;
                    break;
                }
                output[out_pos]     = (uint8_t)(v & 0xFF);
                output[out_pos + 1] = (uint8_t)(v >> 8);
            } else {
                if (n <= 3) {
                    ref_off = -2 * (int)n;
                } else if (n <= 7) {
                    ref_off = -(int)row_bytes + (-2 * ((int)n - 4));
                } else if (n <= 11) {
                    ref_off = -2 * (int)row_bytes + (-2 * ((int)n - 8));
                } else {
                    ref_off = -3 * (int)row_bytes + (-2 * ((int)n - 12));
                }
                src = out_pos + ref_off;
                if ((unsigned int)src < (unsigned int)output_total - 1) {
                    output[out_pos]     = output[src];
                    output[out_pos + 1] = output[src + 1];
                } else {
                    return 1;
                }
            }
            out_pos += 2;
        }
    }

    if (!decode_ok) return 1;

    } /* end decode block */

    /* -- 4bpp -> 8bpp -- */
    if (bpp == 4) {
        uint8_t *final_pixels = buf + off_final;
        if (pixel_width <= 0 || pixel_height <= 0) return 1;
        for (i = 0; i < pixel_width * pixel_height; i++) {
            int byte_idx = i / 2;
            final_pixels[i] = (i & 1) ? (output[byte_idx] >> 4) : (output[byte_idx] & 0x0F);
        }
        output = final_pixels;
    } else {
        output = buf + off_output;
    }

    /* -- Strip padding -- */
    if (pad_px_left > 0 || pad_px_right > 0 || crop_width != pixel_width) {
        int y;
        cropped = buf + off_cropped;
        for (y = 0; y < crop_height; y++) {
            memcpy(cropped + (size_t)y * crop_width,
                   output + (size_t)y * pixel_width + pad_px_left,
                   (size_t)crop_width);
        }
        output = cropped;
        pixel_width  = crop_width;
        pixel_height = crop_height;
    }

    /* -- Build MagImage in the pool (at the end) -- */
    img = (MagImage *)(buf + off_img);
    img->width      = pixel_width;
    img->height     = pixel_height;
    img->pixels     = output;
    img->bpp        = bpp;
    img->num_colors = num_colors;
    img->is_sprite  = is_sprite_flag;
    img->refcount   = 1;
    img->is_pool    = 1;
    for (i = 0; i < num_colors; i++) {
        img->palette_r[i] = pal_r[i];
        img->palette_g[i] = pal_g[i];
        img->palette_b[i] = pal_b[i];
    }
    for (; i < 256; i++) {
        img->palette_r[i] = img->palette_g[i] = img->palette_b[i] = 0;
    }

    *out = img;
    return 0;
}
