/*
 * cjk — CJK 16×16 点阵字形加载器
 *
 * 加载 CJK.DAT（CJKF 格式），解析 Unicode 区间表和 16×16 点阵字形数据。
 * 通过二分查找 Unicode 码点所属区间，返回对应字形数据指针。
 * 可选日志回调用于报告加载时错误信息。
 * 无平台依赖，属于 core/lib/ 平台无关库。
 *
 * CJKF 格式：
 *   [0-3]  魔数 "CJKF"
 *   [4-5]  区间数（LE uint16）
 *   [6-9]  保留
 *   [10+]  区间表（每 entry 16 字节：start/end/glyph_offset 各 4 字节 LE）
 *   区间表后紧跟字形数据（每字形 32 字节 = 16×16 1-bit）
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cjk.h"
#include "naiz_file.h"
#include "endian.h"

/* Maximum number of CJK Unicode ranges. */
#define MAX_CJK_RANGES 128
/* Maximum safe offset value for range bounds check. */
#define CJK_OFFSET_MAX 0xFFFFFFFFUL

/* CJK Unicode range: inclusive [start, end], glyph_offset points to first glyph data. */
typedef struct {
    unsigned long start_cp;      /* 区间起始 Unicode 码点 */
    unsigned long end_cp;        /* 区间终止 Unicode 码点（含） */
    unsigned long glyph_offset;  /* 区间首字形在 cjk_data 中的字节偏移 */
} CjkRange;

/* Loaded CJK glyph data buffer. */
static unsigned char *cjk_data;
/* Total size of the loaded CJK.DAT file. */
static long cjk_data_size;
/* Parsed Unicode range table. */
static CjkRange cjk_ranges[MAX_CJK_RANGES];
/* Number of valid ranges in cjk_ranges. */
static int cjk_range_count;
/* Non-zero after successful load. */
static int cjk_loaded;

/* Load and parse CJK.DAT: validate magic "CJKF", parse range table, check glyph_offset consistency.
 * @param filename  Path to CJK.DAT
 * @return 0 on success, -1 on failure (file not found / bad format / version mismatch) */
int cjk_init(const char *filename)
{
    long fsize;
    unsigned char *buf;
    int i;

    buf = (unsigned char *)file_read_all(filename, &fsize);
    if (!buf) return -1;

    /* 验证魔数 "CJKF"（4 字节）和最小文件大小（10 字节：魔数 4 + 区间数 2 + 保留 4） */
    if (fsize < 10 || buf[0] != 'C' || buf[1] != 'J' || buf[2] != 'K' || buf[3] != 'F') {
        free(buf);
        return -1;
    }

    /* 读取区间数（LE uint16，偏移 4），上限 MAX_CJK_RANGES */
    cjk_range_count = (int)read16_le(buf + 4);
    if (cjk_range_count > MAX_CJK_RANGES) {
        free(buf);
        return -1;
    }

    /* 解析区间表：每个 entry 16 字节，偏移 10 处开始 */
    for (i = 0; i < cjk_range_count; i++) {
        int off = 10 + i * 16;
        if (off + 15 > fsize) {
            free(buf);
            return -1;
        }
        cjk_ranges[i].start_cp     = read32_le(buf + off);
        cjk_ranges[i].end_cp       = read32_le(buf + off + 4);
        cjk_ranges[i].glyph_offset = read32_le(buf + off + 8);
    }

    /* 校验一致性：首个区间的 glyph_offset 必须等于 header 总大小 */
    /* header = 10 + range_count * 16，若不一致说明文件生成工具有 bug */
    if (cjk_range_count > 0) {
        unsigned long expected_header = 10UL + (unsigned long)cjk_range_count * 16UL;
        /* Header layout mismatch means the generating tool has a bug.
         * The return code already surfaces the failure to the caller. */
        if (cjk_ranges[0].glyph_offset != expected_header) {
            free(buf);
            return -1;
        }
    }

    if (cjk_data) free(cjk_data);
    cjk_data = buf;
    cjk_data_size = fsize;
    cjk_loaded = 1;
    return 0;
}

/* Load CJK with three-level fallback: CJK_<lang>.DAT → CJK_EN.DAT → CJK.DAT.
 * @param lang  3-letter language code ("eng","jpn",...), NULL/empty treated as "eng"
 * @return 0 on success, -1 if all attempts fail */
int cjk_load_for_lang(const char *lang)
{
    char cjk_file[16];
    int i;
    if (!lang || !*lang) lang = "eng";
    snprintf(cjk_file, sizeof(cjk_file), "CJK_%s.DAT", lang);
    for (i = 4; cjk_file[i] && cjk_file[i] != '.'; i++)
        if (cjk_file[i] >= 'a' && cjk_file[i] <= 'z')
            cjk_file[i] = cjk_file[i] - 'a' + 'A';
    if (cjk_init(cjk_file) == 0) return 0;
    if (cjk_init("CJK_EN.DAT") == 0) return 0;
    if (cjk_init("CJK.DAT") == 0) return 0;
    return -1;
}

/* Look up a 16x16 CJK glyph by Unicode codepoint (binary search).
 * @param codepoint  Unicode codepoint
 * @return Read-only pointer to 32-byte glyph bitmap, or NULL if not loaded/found/out of range */
const unsigned char *cjk_get_glyph(int codepoint)
{
    int lo, hi, mid;
    unsigned long cp = (unsigned long)codepoint;
    CjkRange *r;

    if (!cjk_loaded) return NULL;

    /* 二分查找：CJK 区间表按 start_cp 升序排列 */
    lo = 0;
    hi = cjk_range_count - 1;
    while (lo <= hi) {
        mid = (lo + hi) / 2;
        r = &cjk_ranges[mid];
        if (cp < r->start_cp) {
            hi = mid - 1;
        } else if (cp > r->end_cp) {
            lo = mid + 1;
        } else {
            /* 命中区间：计算字形偏移 = glyph_offset + idx * CJK_GLYPH_BYTES */
            unsigned long idx, offset;
            idx = cp - r->start_cp;
            /* 防溢出：idx * CJK_GLYPH_BYTES 不会超过 0xFFFFFFFF */
            if (idx > CJK_OFFSET_MAX / CJK_GLYPH_BYTES) return NULL;
            offset = r->glyph_offset + idx * CJK_GLYPH_BYTES;
            /* bounds check: offset + 32 bytes within file range */
            if (offset > (unsigned long)cjk_data_size) return NULL;
            if ((unsigned long)cjk_data_size - offset < CJK_GLYPH_BYTES) return NULL;
            return cjk_data + offset;
        }
    }
    return NULL;
}
