/*
 * font.h — ASCII 8×16 点阵字形加载器接口
 *
 * 从 FONT.DAT（MHVN98 兼容格式）加载 ASCII 字符的 1-bit 点阵字形，
 * 提供 8×16 像素（32 字节）的字形查询。
 * 仅支持 ASCII（0-127），CJK 部分见 cjk.h。
 */

#ifndef FONT_H
#define FONT_H

/* ASCII 字形尺寸：8 像素宽 × 16 像素高，打包为 32 字节 */
#define FONT_GLYPH_W 8
#define FONT_GLYPH_H 16
#define FONT_GLYPH_BYTES 32

/* 加载 FONT.DAT 字形文件，成功返回 0，失败返回 -1 */
/* 参数 filename: FONT.DAT 文件路径 */
int  font_init(const char *filename);
/* 获取 ASCII 字符 ch（0-127）的 8×16 字形数据指针，ch>127 返回 NULL */
/* 返回值: 指向 32 字节字形位图的只读指针，失败返回 NULL */
const unsigned char *font_get_glyph(unsigned char ch);

/* 加载备选字形表（BLACK.DAT，黑花体 16×16 拉丁字形），成功返回 0，失败返回 -1 */
/* 非致命：文件缺失时备选表不可用，正文自动回退默认 8×16 字形 */
int  font_load_alt(const char *filename);
/* 获取备选字形（黑花体 16×16）字符 ch 的 32 字节位图，未加载或越界返回 NULL */
const unsigned char *font_get_glyph_alt(unsigned char ch);

#endif
