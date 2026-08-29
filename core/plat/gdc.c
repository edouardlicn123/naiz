/*
 * gdc.c — GDC（μPD7220）256 色 PEGC 调色板接口
 *
 * PC-98 的 GDC（Graphics Display Controller, μPD7220）通过以下
 * 端口控制调色板：
 *   0xA8 — 调色板索引寄存器（写索引）
 *   0xAA — 绿色分量（8-bit）
 *   0xAC — 红色分量（8-bit）
 *   0xAE — 蓝色分量（8-bit）
 *
 * 16 色模式的 GDC 调色板端口为 0xA8-0xAE，PEGC（256 色扩展）
 * 复用同一组端口但支持完整的 8-bit 位深（而非 4-bit DAC）。
 *
 * 显示模式设置由 CRT BIOS INT 18h AH=30h 完成（见 video.c 的
 * video_init()），本模块仅负责调色板的读写操作。
 *
 * 参考：docs/refdocs/ — PC-98 GDC 规范
 *       devdocs/0.1版开发文档总结.html#doc-19 — NP2kai 调色板自检系统
 */
#include "pc98.h"

/*
 * Set the R/G/B values for a palette index.
 *
 * Write order: index -> green -> red -> blue (per GDC hardware timing).
 * Each component is a full 8-bit value (0-255); PEGC DAC accepts 8-bit.
 *
 * @param idx  Palette index (0-255)
 * @param r    Red component (0-255)
 * @param g    Green component (0-255)
 * @param b    Blue component (0-255)
 */
void gdc_set_palette(int idx, unsigned char r, unsigned char g, unsigned char b)
{
    /* PEGC ports are the same as 16-color mode (0xA8/AA/AC/AE), but values are 8-bit. */
    outb(0xA8, (unsigned char)idx);  /* Write index */
    outb(0xAA, g);                   /* Green */
    outb(0xAC, r);                   /* Red */
    outb(0xAE, b);                   /* Blue */
}

/*
 * Read the R/G/B values for a palette index.
 *
 * Read-back order matches write order: write index, then read components.
 *
 * @param idx  Palette index (0-255)
 * @param r    Output pointer for red component
 * @param g    Output pointer for green component
 * @param b    Output pointer for blue component
 */
void gdc_read_palette(int idx, unsigned char *r, unsigned char *g, unsigned char *b)
{
    outb(0xA8, (unsigned char)idx);  /* Strobe index */
    *g = inb(0xAA);                  /* Read green */
    *r = inb(0xAC);                  /* Read red */
    *b = inb(0xAE);                  /* Read blue */
}
