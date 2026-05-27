/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#ifndef PC98_GDC_H
#define PC98_GDC_H

#define GDC_PLANE0_SEGMENT 0xA800
#define GDC_PLANE1_SEGMENT 0xB000
#define GDC_PLANE2_SEGMENT 0xB800
#define GDC_PLANE3_SEGMENT 0xE000
#define GDC_PLANES_SEGMENT 0xA800

#define GDC_PLANE0 ((unsigned __far char*)0xA8000000)
#define GDC_PLANE1 ((unsigned __far char*)0xB0000000)
#define GDC_PLANE2 ((unsigned __far char*)0xB8000000)
#define GDC_PLANE3 ((unsigned __far char*)0xE0000000)
#define GDC_PLANES  ((unsigned __far char*)0xA8000000)

#define GDC_MODE1_COLOUR            0x02
#define GDC_MODE1_MONOCHROME        0x03
#define GDC_MODE1_LINEDOUBLE_ON     0x08
#define GDC_MODE1_LINEDOUBLE_OFF    0x09
#define GDC_MODE1_DISPLAY_ON        0x0E
#define GDC_MODE1_DISPLAY_OFF       0x0F

#define GDC_MODE2_8COLOURS      0x00
#define GDC_MODE2_16COLOURS     0x01
#define GDC_MODE2_GRCG          0x04
#define GDC_MODE2_EGC           0x05
#define GDC_MODE2_NOMODIFY      0x06
#define GDC_MODE2_MODIFY        0x07

#define GDC_COMMAND_RESET       0x00
#define GDC_COMMAND_START       0x0D
#define GDC_COMMAND_STOP        0x0C
#define GDC_COMMAND_ZOOM        0x46
#define GDC_COMMAND_SCROLL(s)   (0x70 | ((s) & 0xF))
#define GDC_COMMAND_CSRFORM     0x4B
#define GDC_COMMAND_PITCH       0x47
#define GDC_COMMAND_TEXTW       0x78
#define GDC_COMMAND_TEXTE       0x68
#define GDC_COMMAND_CSRW        0x49
#define GDC_COMMAND_MASK        0x4A
#define GDC_COMMAND_WRITE(m)    (0x20 | (m))
#define GDC_COMMAND_READ(m)     (0xA0 | (m))
#define GDC_COMMAND_VECTW       0x4C
#define GDC_COMMAND_VECTE       0x6C
#define GDC_COMMAND_SYNC_OFF    0x0E
#define GDC_COMMAND_SYNC_ON     0x0F

#define GDC_SYNC_NOCHAR         0x02
#define GDC_SYNC_REFRESH        0x04

#define GDC_VECTW_DOT           0x00
#define GDC_VECTW_LINE          0x08
#define GDC_VECTW_TILE          0x10
#define GDC_VECTW_RECT          0x40

#define GDC_MOD_REPLACE 0x00
#define GDC_MOD_XOR     0x01

#define GDC_SETDISPMODE_ERROR_ZERODIMENSION  0x01
#define GDC_SETDISPMODE_ERROR_ZEROVLBANK     0x02
#define GDC_SETDISPMODE_ERROR_VBLANKTOOSHORT 0x03
#define GDC_SETDISPMODE_ERROR_VBLANKTOOLONG  0x04
#define GDC_SETDISPMODE_ERROR_HBLANKTOOSHORT 0x05

static inline void gdc_set_mode1(unsigned char mode)
{
    __asm volatile ("outb %%al, $0x68" : : "a" (mode));
}

static inline void gdc_set_mode2(unsigned char mode)
{
    __asm volatile ("outb %%al, $0x6A" : : "a" (mode));
}

static inline void gdc_write_text_param(unsigned char param)
{
    __asm volatile ("outb %%al, $0x60" : : "a" (param));
}

static inline void gdc_write_text_cmd(unsigned char cmd)
{
    __asm volatile ("outb %%al, $0x62" : : "a" (cmd));
}

static inline void gdc_start_text(void)
{
    gdc_write_text_cmd(GDC_COMMAND_START);
}

static inline void gdc_stop_text(void)
{
    gdc_write_text_cmd(GDC_COMMAND_STOP);
}

static inline void gdc_write_gfx_param(unsigned char param)
{
    __asm volatile ("outb %%al, $0xA0" : : "a" (param));
}

static inline void gdc_write_gfx_cmd(unsigned char cmd)
{
    __asm volatile ("outb %%al, $0xA2" : : "a" (cmd));
}

static inline void gdc_start_graphics(void)
{
    gdc_write_gfx_cmd(GDC_COMMAND_START);
}

static inline void gdc_stop_graphics(void)
{
    gdc_write_gfx_cmd(GDC_COMMAND_STOP);
}

static inline void gdc_set_display_page(unsigned char page)
{
    __asm volatile ("outb %%al, $0xA4" : : "a" (page));
}

static inline void gdc_set_draw_page(unsigned char page)
{
    __asm volatile ("outb %%al, $0xA6" : : "a" (page));
}

static inline void gdc_interrupt_reset(void)
{
    __asm volatile ("outb %%al, $0x64" : : "a" (0));
}

static inline void gdc_set_palette_colour(unsigned char idx, unsigned char r, unsigned char g, unsigned char b)
{
    __asm volatile ("out %%al, $0xA8" : : "a" (idx));
    __asm volatile ("out %%al, $0xAC" : : "a" (r));
    __asm volatile ("out %%al, $0xAA" : : "a" (g));
    __asm volatile ("out %%al, $0xAE" : : "a" (b));
}

static inline void gdc_set_border_colour(unsigned char col)
{
    __asm volatile ("outb %%al, $0x6C" : : "a" (col));
}

static inline unsigned char gdc_read_gfx_status(void)
{
    unsigned char s;
    __asm volatile ("inb $0xA0, %%al" : "=a" (s));
    return s;
}

static inline unsigned char gdc_read_text_status(void)
{
    unsigned char s;
    __asm volatile ("inb $0x60, %%al" : "=a" (s));
    return s;
}

void gdc_set_display_region(unsigned int startaddr, unsigned int line_number);
void gdc_set_graphics_line_scale(unsigned char scale);
int  gdc_set_display_mode(unsigned int width, unsigned int height, unsigned int scanned_lines);
void gdc_scroll_simple_graphics(unsigned int topline);

#endif
