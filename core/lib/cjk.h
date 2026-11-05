/*
 * cjk.h — CJK 16×16 点阵字形加载器接口
 *
 * 加载 CJK.DAT（CJKF 格式），提供 Unicode CJK 汉字的 16×16 点阵字形查询。
 * 字符编码为 UTF-16BE（JIS コード），字形为 1-bit 位图，打包为 32 字节。
 * 通过二分查找区间表实现 O(log N) 查询。
 */

#ifndef CJK_H
#define CJK_H

/* CJK 字形尺寸：16 像素宽 × 16 像素高，打包为 32 字节 */
#define CJK_GLYPH_W  16
#define CJK_GLYPH_H  16
#define CJK_GLYPH_BYTES 32

/* 加载 CJK.DAT 字形文件，成功返回 0，失败返回 -1 */
/* 参数 filename: CJK.DAT 文件路径 */
int  cjk_init(const char *filename);
/* 根据 Unicode 码点获取 16×16 字形数据指针，未找到返回 NULL */
/* 参数 codepoint: Unicode 码点; 返回值: 32 字节字形位图指针或 NULL */
const unsigned char *cjk_get_glyph(int codepoint);
/* 按语言码加载 CJK 文件：CJK_<lang>.DAT → CJK_EN.DAT → CJK.DAT 三级回退 */
/* 参数 lang: 3 字母语言码（"eng"/"jpn"/...），NULL 或空串视为 "eng" */
/* 返回 0 成功，-1 全部失败 */
int  cjk_load_for_lang(const char *lang);

#endif
