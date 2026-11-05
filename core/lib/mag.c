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
#include <i86.h>
#include <stdlib.h>
#include <string.h>

/* 199E 阶段 3: 4096 对应的 cli 窗口约 30-70ms，Timer-B 窗口内只锁存一个
 * pending，其余整拍丢失。降到 1024 先把窗口压到 ~8-17ms；仍超标时可在
 * 构建时用 -DMAG_PROGRESS_STRIDE=512 复验，无需改源。 */
#ifndef MAG_PROGRESS_STRIDE
#define MAG_PROGRESS_STRIDE 1024
#endif

/* core/lib 按 Makefile 分层规则不 include plat 头，故在此本地声明 extern. */
extern unsigned long hal_wallclock_ms(void);   /* frame-budget deadline */

static void (*g_mag_progress_hook)(void) = 0;

/* devdoc 200 §4.3: grow-only reusable action buffer for mag_decode().
 * The action buffer is pure scratch (flag-B XOR state), sized byte_width/4.
 * Reusing it across decodes eliminates one calloc/free per image.  Must be
 * zeroed before each use (the XOR logic assumes a zero initial state).
 * Lives for the lifetime of the process (no explicit teardown; the engine
 * exits right after image_close()). */
static uint8_t *g_action_buf = NULL;
static int      g_action_cap = 0;

MagDiag mag_diag;

/* devdoc 200 §5.1: resumable decode state for frame-budgeted prefetch.
 * mag_decode can yield mid-loop when the wall-clock deadline
 * (g_decode_deadline_ms) expires.  Budgeting is not wired in today -- no
 * caller sets a deadline, so decode always runs to completion -- and the
 * resume path is kept for future prefetch work.  All loop state is saved
 * here so the next mag_decode call (same image ID) resumes instead of
 * restarting. */
#define MAG_DECODE_OK       0
#define MAG_DECODE_FAIL     1
#define MAG_DECODE_YIELDED  2

typedef struct {
    int            active;
    const uint8_t *data;
    int            size;
    /* parsed header */
    int            bpp, num_colors;
    uint8_t        pal_r[256], pal_g[256], pal_b[256];
    int            pixel_width, pixel_height, output_total;
    int            byte_width, row_bytes, action_size;
    int            is_sprite_flag;
    /* stream base pointers */
    const uint8_t *flag_a, *flag_b, *color;
    int            flag_b_byte_len, color_byte_len;
    /* decode cursor */
    int            fa_bit, fa_bits;
    int            fb_pos, col_pos, out_pos, act_idx;
    int            prog;
    uint8_t       *output;
} MagDecodeState;

static MagDecodeState g_resume;
static unsigned long  g_decode_deadline_ms = 0;   /* 0 = no budget */

#define MAG_FAIL(code) do { \
    mag_diag.error = (code); \
    g_resume.active = 0; \
    return 1; \
} while (0)

void mag_set_progress_hook(void (*fn)(void))
{
    g_mag_progress_hook = fn;
}

/*=== Shared decode helpers ===============================================*/
/*
 * Strip per-row left/right padding by copying crop_width bytes from each
 * source row (at pad_px_left) into the row-strided destination.  Shared by
 * the heap (mag_decode) and pool (mag_decode_into) ownership paths so the
 * crop arithmetic cannot drift between them.
 *
 * src_w and crop_width/pad_px_left are row indices/sizes in bytes
 * (1 byte/pixel after 4bpp expansion in both call sites).
 */
static void mag_crop_rows(uint8_t *dst, const uint8_t *src,
                          int src_w, int crop_width, int pad_px_left,
                          int crop_height)
{
    int y;
    for (y = 0; y < crop_height; y++) {
        memcpy(dst + (size_t)y * crop_width,
               src + (size_t)y * src_w + pad_px_left,
               (size_t)crop_width);
    }
}

/* Fill the MagImage 256-entry palette from the decoded num_colors entries,
 * zeroing the remainder — shared between the two ownership paths. */
static void mag_fill_palette(MagImage *img, const uint8_t *pal_r,
                             const uint8_t *pal_g, const uint8_t *pal_b,
                             int num_colors)
{
    int i;
    for (i = 0; i < num_colors; i++) {
        img->palette_r[i] = pal_r[i];
        img->palette_g[i] = pal_g[i];
        img->palette_b[i] = pal_b[i];
    }
    for (; i < 256; i++) {
        img->palette_r[i] = img->palette_g[i] = img->palette_b[i] = 0;
    }
}

/*=== Data reader =========================================================*/

/*
 * devdoc 195 F1: flag A is read through a plain local bit index, not through a
 * BitReader struct behind a pointer.
 *
 * 194 moved the reader to a canary-wrapped heap object to rule out stack
 * corruption.  The 195 evidence (deterministic failure per binary,
 * layout-dependent failure point, unchanged under cli/sti, gcc decoding the
 * same source and blob cleanly) instead points at the struct-field loads
 * themselves: br_read() rejected a read while memory still held
 * byte_pos=1591 and byte_len=8000.  A bit index in a local int cannot produce
 * that, and it also removes the file-level decode state, so mag_decode() and
 * mag_decode_into() no longer destroy each other when a progress hook reaches
 * the decoder again.
 *
 * Order is MSB first: bit k lives in flag_a[k >> 3], mask 0x80 >> (k & 7).
 * The total bit count is known up front (flag B offset minus flag A offset).
 */

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
 *   5) Build MagImage struct
 * (left/right padding strip removed in devdoc 200 §4.3: never triggers)
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
    /* devdoc 195 F1: flag A is read with a local bit index (see Data reader). */
    int fa_bit, fa_bits;
    int fb_pos, col_pos, out_pos, act_idx;
    int row_bytes;
    /* devdoc 200 §4.3: cropped path removed.  All naiz-packed MAG images
     * have left=0, right=width-1, and width aligned to 4 bytes, so
     * pad_px_left == pad_px_right == 0 and crop_width == pixel_width.
     * Verified against demo-a2 (20/20 images: zero padding). */
    MagImage *img;
    int is_sprite_flag;
    int i;

    *out = NULL;
    memset(&mag_diag, 0, sizeof(mag_diag));

    /* -- Resume a previously-yielded decode (devdoc 200 §5.1) -- */
    if (g_resume.active && g_resume.data == data && g_resume.size == size) {
        bpp            = g_resume.bpp;
        num_colors     = g_resume.num_colors;
        memcpy(pal_r, g_resume.pal_r, 256);
        memcpy(pal_g, g_resume.pal_g, 256);
        memcpy(pal_b, g_resume.pal_b, 256);
        pixel_width    = g_resume.pixel_width;
        pixel_height   = g_resume.pixel_height;
        output_total   = g_resume.output_total;
        byte_width     = g_resume.byte_width;
        row_bytes      = g_resume.row_bytes;
        action_size    = g_resume.action_size;
        is_sprite_flag = g_resume.is_sprite_flag;
        flag_a         = g_resume.flag_a;
        flag_b         = g_resume.flag_b;
        color          = g_resume.color;
        flag_b_byte_len = g_resume.flag_b_byte_len;
        color_byte_len = g_resume.color_byte_len;
        fa_bit         = g_resume.fa_bit;
        fa_bits        = g_resume.fa_bits;
        fb_pos         = g_resume.fb_pos;
        col_pos        = g_resume.col_pos;
        out_pos        = g_resume.out_pos;
        act_idx        = g_resume.act_idx;
        output         = g_resume.output;
        action         = g_action_buf;   /* reusable global, never freed mid-decode */
        goto mag_decode_loop;
    }

    /* Stale resume from a different image: free its output buffer. */
    if (g_resume.active && g_resume.output) {
        free(g_resume.output);
        g_resume.output = NULL;
    }
    g_resume.active = 0;
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

    mag_diag.bpp          = bpp;
    mag_diag.byte_width   = byte_width;
    mag_diag.pixel_height = pixel_height;
    mag_diag.output_total = output_total;
    mag_diag.flag_a_bits  = (flag_b_off - flag_a_off) * 8;
    mag_diag.color_len    = color_size_s;

    /* -- 分配缓冲区 -- */
    /* output: owned by the returned MagImage, allocated fresh each decode.
     * action: pure scratch, reused from g_action_buf (grow-only, zeroed). */
    output = (uint8_t *)calloc(1, output_total + 16);
    if (!output) {
        mag_diag.progress = output_total;
        MAG_FAIL(10);
    }
    if (g_action_cap < action_size + 4) {
        free(g_action_buf);
        g_action_buf = (uint8_t *)calloc(1, action_size + 4);
        g_action_cap = g_action_buf ? (action_size + 4) : 0;
    }
    if (!g_action_buf) {
        mag_diag.progress = output_total;
        free(output);
        MAG_FAIL(10);
    }
    memset(g_action_buf, 0, action_size + 4);
    action = g_action_buf;

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
    fa_bit   = 0;
    fa_bits  = (flag_b_off - flag_a_off) * 8;
    mag_diag.fa_len0 = flag_b_off - flag_a_off;
    mag_diag.fa_hdr_off = hdr_start + flag_a_off;
    fb_pos   = 0;
    col_pos  = 0;
    out_pos  = 0;
    act_idx  = 0;
    row_bytes = byte_width;

    /* Persist parsed state for frame-budgeted resume (devdoc 200 §5.1). */
    g_resume.active         = 1;
    g_resume.data           = data;
    g_resume.size           = size;
    g_resume.bpp            = bpp;
    g_resume.num_colors     = num_colors;
    /* Audit C9 false positive: pal_r/pal_g/pal_b are uint8_t[256],
     * exactly the 256-byte destination arrays. */
    memcpy(g_resume.pal_r, pal_r, 256);
    memcpy(g_resume.pal_g, pal_g, 256);
    memcpy(g_resume.pal_b, pal_b, 256);
    g_resume.pixel_width    = pixel_width;
    g_resume.pixel_height   = pixel_height;
    g_resume.output_total   = output_total;
    g_resume.byte_width     = byte_width;
    g_resume.row_bytes      = row_bytes;
    g_resume.action_size    = action_size;
    g_resume.is_sprite_flag = is_sprite_flag;
    g_resume.flag_a         = flag_a;
    g_resume.flag_b         = flag_b;
    g_resume.color          = color;
    g_resume.flag_b_byte_len = flag_b_byte_len;
    g_resume.color_byte_len  = color_byte_len;
    g_resume.fa_bit         = fa_bit;
    g_resume.fa_bits        = fa_bits;
    g_resume.fb_pos         = fb_pos;
    g_resume.col_pos        = col_pos;
    g_resume.out_pos        = out_pos;
    g_resume.act_idx        = act_idx;
    g_resume.prog           = 0;
    g_resume.output         = output;

mag_decode_loop:
    {
        int decode_ok = 1;
        int _prog = g_resume.prog;
        int _top = 0;        /* out_pos at the top of the current iteration */
        int _fb0 = 0, _col0 = 0;
    /* devdoc 195 F6: run the hot loop with interrupts masked.  A resident
     * real-mode TSR (QMOUSE.COM) reflects its hardware IRQ handler through
     * DPMI; the reflected frame lands on the client's stack and overwrites
     * this loop's locals (measured: 4/4 identical failures with QMOUSE,
     * 2/2 successes without).
     *
     * P7 FINAL (devdoc 196 §4.0, 2026-11-02): cli is KEPT, but the progress
     * pump must escape it -- see the call site below (`_enable(); hook();
     * _disable();`).  DOS/32A virtualizes IF, so running the pump's deep call
     * chain inside the cli region lets the deferred IRQ reflection land on
     * this decode frame and clobber the loop locals (one "short" iteration,
     * then flag A runs out early).  The hot loop itself stays masked. */
    _disable();
    while (out_pos + 1 < output_total) {
        int a, ab, nib, n, ref_off, src;
        uint16_t v;

        _top = out_pos; _fb0 = fb_pos; _col0 = col_pos;
        mag_diag.iters++;
        /* 从 flag A 读取 1 bit（devdoc 195 F1: 本地 bit 索引） */
        if (fa_bit >= fa_bits) {
            mag_diag.error = 11; mag_diag.progress = out_pos;
            mag_diag.fa_byte_pos = fa_bit >> 3;
            mag_diag.fa_mask = 0x80 >> (fa_bit & 7);
            mag_diag.fa_byte_len = fa_bits >> 3;
            mag_diag.fa_base_off = (int)(flag_a - data);
            mag_diag.data_size = size;
            mag_diag.fb_pos = fb_pos; mag_diag.col_pos = col_pos;
            mag_diag.br_rej_pos = mag_diag.fa_byte_pos;
            mag_diag.br_rej_len = mag_diag.fa_byte_len;
            mag_diag.br_rej_cnt++;
            decode_ok = 0; break;
        }
        a = (flag_a[fa_bit >> 3] >> (7 - (fa_bit & 7))) & 1;
        fa_bit++;

        /* flag A=1: 用 flag B 的当前字节与 action buffer 当前元素异或 */
        if (a == 1) {
            if (fb_pos < flag_b_byte_len) {
                int ai = act_idx % action_size;
                action[ai] ^= flag_b[fb_pos++];
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
                    mag_diag.error = 12;
                    mag_diag.progress = out_pos;
                    /* devdoc 194 S2: without this record the early-out below
                     * left the caller unable to tell a real code=12 from the
                     * code=11 that the continued loop later reported. */
                    mag_diag.err12_it   = mag_diag.iters;
                    mag_diag.err12_nib  = nib;
                    mag_diag.err12_n    = n;
                    mag_diag.err12_ab   = ab;
                    mag_diag.err12_act  = act_idx;
                    mag_diag.err12_asize = action_size;
                    mag_diag.err12_fb   = fb_pos;
                    mag_diag.err12_col  = col_pos;
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
                    mag_diag.error = 13;
                    mag_diag.progress = out_pos;
                    _enable();
                    free(output);
                    /* action is the reusable g_action_buf; do not free */
                    return 1;
                }
            }
            out_pos += 2;  /* 前进 2 字节（对应 2/4 像素） */
            _prog += 2;
            if (g_mag_progress_hook && _prog >= MAG_PROGRESS_STRIDE) {
                /* Save decode cursor for resume (devdoc 200 §5.1). */
                g_resume.fa_bit  = fa_bit;
                g_resume.fb_pos  = fb_pos;
                g_resume.col_pos = col_pos;
                g_resume.out_pos = out_pos;
                g_resume.act_idx = act_idx;
                g_resume.prog    = 0;

                /* P7 (devdoc 196 §4.5): the pump must NOT run with IF=0.
                 * Under DOS/32A the virtual-IF cli region defers hardware
                 * IRQs; running the pump's deep call chain inside that
                 * region lets the deferred reflection land on the decode
                 * stack and clobber a loop local (one "short" iteration:
                 * out_pos advances 0/2 bytes instead of 4, then flag A runs
                 * out early).  Opening interrupts only for the pump keeps
                 * the hot loop masked while the reflection lands inside the
                 * pump's own frame instead of the decode frame. */
                _enable();
                g_mag_progress_hook();
                /* Frame-budget yield: if the deadline expired, stop here and
                 * let the next preload_step resume from g_resume. */
                if (g_decode_deadline_ms != 0 &&
                    hal_wallclock_ms() >= g_decode_deadline_ms)
                    return MAG_DECODE_YIELDED;
                _disable();
                _prog = 0;
            }
        }
        /* devdoc 194 S2: keep the last 8 iterations so a tail-scoped failure
         * can be reconstructed without a per-bit trace. */
        {
            int k = mag_diag.tail_cnt & 7;
            mag_diag.tail_pos0[k] = _top;
            mag_diag.tail_pos1[k] = out_pos;
            mag_diag.tail_it[k]  = mag_diag.iters;
            mag_diag.tail_fb[k]  = _fb0;
            mag_diag.tail_col[k] = _col0;
            mag_diag.tail_cnt++;
        }
        /* devdoc 195 S3: an iteration must advance exactly 4 bytes (2 nibbles
         * x 2 bytes).  Record the first one that does not. */
        if (out_pos - _top != 4) {
            if (mag_diag.short_cnt == 0) {
                mag_diag.short_it  = mag_diag.iters;
                mag_diag.short_top = _top;
                mag_diag.short_end = out_pos;
                mag_diag.short_ab  = ab;
                mag_diag.short_fb  = fb_pos;
                mag_diag.short_col = col_pos;
            }
            mag_diag.short_cnt++;
        }
        /* devdoc 194 S2: the loop must stop on the first failure.  Before this
         * check a colour-stream failure only exited the nibble loop, and the
         * outer loop kept consuming flag A until it ran dry, so every failure
         * was finally reported as code=11 at a stale out_pos. */
        if (!decode_ok) break;
    }
    _enable();
    if (!decode_ok) { free(output); output = NULL; MAG_FAIL(mag_diag.error ? mag_diag.error : 11); }
    /* Decode complete: release the resume slot so the next call starts fresh. */
    g_resume.active = 0;
    g_decode_deadline_ms = 0;

    } /* end decode block */

    /*
     * -- 4bpp → 8bpp 转换 --
     * 4bpp 时每个字节含 2 个像素（高 4 位+低 4 位），
     * 转换为每个像素 1 字节的平面格式。
     */
    if (bpp == 4) {
        int final_size;
        uint8_t *final_pixels;
        /* Audit C23 false positive: this branch returns immediately, so it
         * never reaches the free(output) on the img-allocation failure below.
         * MAG_FAIL keeps the error code in mag_diag like every other path. */
        if (pixel_width <= 0 || pixel_height <= 0) { free(output); output = NULL; MAG_FAIL(14); }
        final_size = pixel_width * pixel_height;
        final_pixels = (uint8_t *)malloc(final_size);
        if (!final_pixels) { free(output); output = NULL; MAG_FAIL(14); }
        for (i = 0; i < pixel_width * pixel_height; i++) {
            int byte_idx = i / 2;
            final_pixels[i] = (i & 1) ? (output[byte_idx] >> 4) : (output[byte_idx] & 0x0F);
            if (g_mag_progress_hook && (i % MAG_PROGRESS_STRIDE) == (MAG_PROGRESS_STRIDE - 1)) {
                g_mag_progress_hook();
            }
        }
        free(output);
        output = final_pixels;
    }

    /*
     * devdoc 200 §4.3: left/right padding strip removed.
     * All naiz-packed MAG images have left=0, right=width-1 and width
     * aligned to 4 bytes, so pad_px_left == pad_px_right == 0 and
     * crop_width == pixel_width.  The cropped path never triggers
     * (verified: demo-a2 20/20 images have zero padding).
     */

    /* -- 构建 MagImage 结构 -- */
    img = (MagImage *)malloc(sizeof(MagImage));
    /* Audit C23 false positive: mutually exclusive with the branches above --
     * both of them return, and MAG_FAIL only returns, so `output` is freed
     * exactly once on this path. */
    if (!img) { free(output); output = NULL; MAG_FAIL(16); }
    img->width      = pixel_width;
    img->height     = pixel_height;
    img->pixels     = output;
    img->bpp        = bpp;
    img->num_colors = num_colors;
    img->is_sprite  = is_sprite_flag;
    img->refcount   = 1;
    mag_fill_palette(img, pal_r, pal_g, pal_b, num_colors);

    /* action is the reusable g_action_buf; do not free here. */
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
        if (!img->is_pool) {
            free(img->pixels);  /* Free pixel buffer (unless pool-allocated) */
            free(img);          /* Free struct itself */
        }
        /* is_pool: struct + pixels live inside the caller's work buffer
         * (see mag_decode_into); the caller owns and frees that buffer. */
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
    /* devdoc 195 F1: local bit index, same read as mag_decode. */
    int fa_bit, fa_bits;
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

    off_img = off_cropped + cropped_size;

    /* struct spans [off_img, off_img+sizeof): bound must cover its end. */
    if (off_img > buf_size ||
        (size_t)off_img + sizeof(MagImage) > (size_t)buf_size) return 1;

    output = buf + off_output;
    action = buf + off_action;
    memset(output, 0, output_total + 16);
    memset(action, 0, action_size + 4);

    /* -- Decompression loop (identical to mag_decode) -- */
    fa_bit   = 0;
    fa_bits  = (flag_b_off - flag_a_off) * 8;
    fb_pos   = 0;
    col_pos  = 0;
    out_pos  = 0;
    act_idx  = 0;
    row_bytes = byte_width;

    {
        int decode_ok = 1;
        int _prog = 0;
    /* devdoc 195 F6: same IRQ-mask guard as mag_decode -- a resident
     * real-mode TSR's reflected IRQ frame would otherwise overwrite the
     * loop locals (see the mag_decode call site).
     *
     * P7 FIX: cli kept for same reason as mag_decode above. */
    _disable();
    while (out_pos + 1 < output_total) {
        int a, ab, nib, n, ref_off, src;
        uint16_t v;

        if (fa_bit >= fa_bits) { decode_ok = 0; break; }
        a = (flag_a[fa_bit >> 3] >> (7 - (fa_bit & 7))) & 1;
        fa_bit++;

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
                    /* Same cleanup as the normal exit; the caller's
                     * buffers are not freed here. */
                    _enable();
                    return 1;
                }
            }
            out_pos += 2;
            _prog += 2;
            if (g_mag_progress_hook && _prog >= MAG_PROGRESS_STRIDE) {
                /* Same P7 rule as mag_decode: pump with IF=1, hot loop masked. */
                _enable();
                g_mag_progress_hook();
                _disable();
                _prog = 0;
            }
        }
        /* devdoc 194: same first-failure rule as mag_decode -- without it a
         * colour-stream failure was masked by a later bitstream-exhausted
         * report from the still-running outer loop. */
        if (!decode_ok) break;
    }
    _enable();

    if (!decode_ok) return 1;

    } /* end decode block */

    /* -- 4bpp -> 8bpp -- */
    if (bpp == 4) {
        uint8_t *final_pixels = buf + off_final;
        if (pixel_width <= 0 || pixel_height <= 0) return 1;
        for (i = 0; i < pixel_width * pixel_height; i++) {
            int byte_idx = i / 2;
            final_pixels[i] = (i & 1) ? (output[byte_idx] >> 4) : (output[byte_idx] & 0x0F);
            if (g_mag_progress_hook && (i % MAG_PROGRESS_STRIDE) == (MAG_PROGRESS_STRIDE - 1)) {
                g_mag_progress_hook();
            }
        }
        output = final_pixels;
    } else {
        output = buf + off_output;
    }

    /* -- Strip padding -- */
    if (pad_px_left > 0 || pad_px_right > 0 || crop_width != pixel_width) {
        cropped = buf + off_cropped;
        mag_crop_rows(cropped, output, pixel_width, crop_width,
                      pad_px_left, crop_height);
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
    mag_fill_palette(img, pal_r, pal_g, pal_b, num_colors);

    *out = img;
    return 0;
}
