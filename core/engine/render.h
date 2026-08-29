/*
 * VRAM primitives — 256-color Packed-Pixel via PEGC bank switching.
 *
 * PC-98 EGC/PEGC 硬件抽象层：
 *   VRAM 线性 640×400，每个像素 1 byte（调色板索引）
 *   32KB Bank 通过端口 0xE0004 切换，窗口 0xA8000–0xAFFFF
 *
 * 所有渲染原语均自动处理 Bank 切换和裁剪。
 */
#ifndef RENDER_H
#define RENDER_H

#include <stdint.h>
#include "hal.h"
#include "mag.h"

/*=== Constants ============================================================*/

#define PAL_WHITE       7    /* 白色调色板索引（引擎保留色） */
#define PAL_TRANSPARENT 15   /* 透明色调色板索引（sprite 跳过此色） */
#define PAL_BLUE         1    /* Blue (initial palette) */
#define PAL_GREEN        2    /* Green (initial palette) */
#define PAL_RED          3    /* Red (initial palette) */
#define PAL_DIALOG_FILL      248  /* Dialog background fill color */
#define PAL_CURSOR_BLACK     254  /* Cursor hand outline color (black) */
#define PAL_NO_TRANSPARENCY  255  /* Sentinel: vram_blit skips no pixels */
#define TEXT_LINE_HEIGHT  20  /* Line height for text rendering */

/* Screen dimensions */
#define LAYER_SCREEN_W    640
#define LAYER_SCREEN_H    400

/*=== Constants ============================================================*/

/* Inline VRAM bank-select wrapper for performance-critical loops.
 * Tracks cur_bank state to avoid redundant port writes. */
#define VRAM_SET_BANK(addr, cur_bank) \
    do { \
        int _bank = (addr) >> 15; \
        if (_bank != (cur_bank)) { \
            (cur_bank) = _bank; \
            hal_vram_bank_select(_bank); \
        } \
    } while(0)

/*=== Functions ============================================================*/
/* 填充矩形区域 */
void fill_rect(int x, int y, int w, int h, uint8_t color);
/* 绘制矩形边框（t = 边框厚度） */
void draw_rect(int x, int y, int w, int h, int t, uint8_t color);
/* 文字渲染函数在 render_text.c 中实现 */
/* 设置对话框文字是否使用黑花体（16x16 Latin alt 字形） */
void text_set_blackletter(int on);
/* 绘制文本，返回下一字符字节偏移 */
int  draw_text(const char *s, int byte_start, int x, int y,
               int max_width, int max_y, int bold, uint8_t color);
/* 计算文本像素宽度 */
int  text_width(const char *s, int bold);
/* 将 MagImage 整图 blit 到 VRAM */
void vram_blit(const MagImage *img, int x, int y);
/* 将精灵 blit 到 VRAM，支持透明色、镜像和裁剪高度 */
void vram_blit_sprite(const MagImage *img, int x, int y, uint8_t transparent_idx,
                      int mirror, int clip_h);
/* 用 8×8 图案填充矩形（用于抖动效果） */
void fill_rect_pattern(int x, int y, int w, int h,
                       const uint8_t pattern[8], uint8_t color);
/* 从 VRAM 读取矩形区域到缓冲区 */
void vram_read(int x, int y, int w, int h, uint8_t *buf);
/* 将缓冲区数据写入 VRAM 矩形区域 */
void vram_write(const uint8_t *buf, int x, int y, int w, int h);
/* 在像素地址 addr 处画一点 */
void vram_pset_addr(int addr, uint8_t color);
/* 对角百叶窗条带填充: paints 'color' on every pixel whose diagonal
 * coordinate u = (col) + (row), or (col) + (h-1-row) when 'reverse' is
 * true, satisfies (u mod period) in [lo, hi).  Single full-screen pass
 * with bank tracking carried across the call, so the dblinds/rdblinds
 * transition draws per frame with one call instead of thousands. */
void fill_diag_sweep(int x, int y, int w, int h, uint8_t color,
                     int lo, int hi, int period, int reverse);
/* 等待 GDC VSYNC（垂直回扫开始后返回，用于防撕裂） */
void vblank_wait(void);
/* 绘制 2× 大标题（16×32 每字）带黑色外发光 */
void draw_title_large(const char *s, int x, int y, int spacing, uint8_t color);
/* 绘制 2× 文字带黑色外发光（spacing=1，public 版本） */
void draw_text_outlined_2x(const char *s, int byte_start,
                           int x, int y, uint8_t color);

#endif
