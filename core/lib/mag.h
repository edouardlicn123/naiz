/*
 * MAG (MAKI02) 图像解码器 — PC-98 主流图像格式
 * MAKI02 格式特点：
 *   - 支持 16 色（4bpp）和 256 色（8bpp）
 *   - 使用 flag A（bitstream）+ flag B（nibble XOR）+ color index stream
 *   - action buffer 含 15 种相对复制位置（relative copy）
 *   - 调色板为 GRB 顺序，各分量位深可变（3/4/5/8 bit）
 *   - 用户字符串开头为 "sprt" 时标记为 sprite（索引 15 = 透明色）
 *
 * 参考：
 *   devdocs/0.1版开发文档总结.html#doc-01
 *   https://mooncore.eu/bunny/txt/makichan.htm
 */
#ifndef MAG_H
#define MAG_H

#include <stdint.h>

/*
 * MagImage — 解码后的 MAG 图像
 * @width, @height  实际图像尺寸（已去除 padding）
 * @pixels          8bpp 调色板索引数组（w * h 字节）
 * @palette_r/g/b   256 色调色板（分量 8-bit，不足位已做低位复制扩展）
 * @num_colors      实际颜色数（16 或 256）
 * @bpp             编码位深（4 或 8）
 * @is_sprite       1 = 精灵图（索引 15 透明），0 = 背景图
 * @refcount        引用计数（mag_decode 初始化为 1；mag_retain/mag_release 增减）
 *
 * 生命周期约定：任何调用方取得 MagImage* 后，使用完毕必须 mag_release()。
 * 缓存/解码器内部持引用时同样遵循；refcount 归 0 时释放像素与结构。
 */
typedef struct {
    int      width;
    int      height;
    uint8_t *pixels;                     /* w*h bytes, 8bpp palette indices */
    uint8_t  palette_r[256];
    uint8_t  palette_g[256];
    uint8_t  palette_b[256];
    int      num_colors;
    int      bpp;                        /* 4 or 8 */
    int      is_sprite;                  /* 1 = sprite (index 15 transparent), 0 = background */
    int      refcount;
    int      is_pool;                    /* 1 = pixels allocated from caller's work buffer (not freed) */
} MagImage;

/*
 * mag_decode — 解码 MAG 数据
 * @param data  MAG 文件数据（完整二进制内容）
 * @param size  数据大小
 * @param out   输出指针，成功时指向分配的 MagImage
 * @return 0=成功，1=失败
 */
int  mag_decode(const uint8_t *data, int size, MagImage **out);

/*
 * mag_decode_into — Decode MAG data using a pre-allocated work buffer.
 * Same as mag_decode but reuses `buf` (size `buf_size`) for the internal
 * output/action/cropped allocations, avoiding per-frame malloc/free.
 * The caller must keep `buf` alive until the MagImage is released.
 * On failure, *out is set to NULL and the buffer is NOT freed.
 * @param data     Raw MAG file data
 * @param size     Data size in bytes
 * @param buf      Pre-allocated work buffer (must be >= buf_size)
 * @param buf_size Size of work buffer in bytes
 * @param out      Output pointer
 * @return 0 on success, 1 on failure
 */
int  mag_decode_into(const uint8_t *data, int size,
                     uint8_t *buf, int buf_size, MagImage **out);

/*
 * mag_read_palette — 仅读取 MAG 调色板（不解码像素）
 * @param data  MAG 文件数据
 * @param size  数据大小
 * @param pal_r 输出 R 分量数组（[256]）
 * @param pal_g 输出 G 分量数组（[256]）
 * @param pal_b 输出 B 分量数组（[256]）
 * @return 颜色数（16 或 256），失败返回 -1
 */
int  mag_read_palette(const uint8_t *data, int size,
                      uint8_t pal_r[256], uint8_t pal_g[256], uint8_t pal_b[256]);

/*
 * mag_retain — 增加引用计数并返回同一指针
 * @param img 目标 MagImage（NULL 安全，返回 NULL）
 * @return img
 */
MagImage *mag_retain(MagImage *img);

/*
 * mag_release — 减少引用计数，归 0 时释放图像
 * @param img 目标 MagImage（NULL 安全）
 *
 * 替代旧 mag_free()：所有持有者使用完毕必须调用。
 */
void mag_release(MagImage *img);

#endif
