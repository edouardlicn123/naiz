/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#include "pc98_gdc.h"

static unsigned int display_region_start = 0;
static unsigned char base_scale = 1;
static unsigned short display_lines = 400;
static unsigned short display_pitch = 40;

void gdc_set_display_region(unsigned int startaddr, unsigned int line_number)
{
    display_region_start = startaddr >> 1;
}

void gdc_set_graphics_line_scale(unsigned char scale)
{
    gdc_write_gfx_cmd(GDC_COMMAND_CSRFORM);
    gdc_write_gfx_param(scale - 1);
    base_scale = scale;
}

int gdc_set_display_mode(unsigned int width, unsigned int height, unsigned int scanned_lines)
{
    if (width == 0 || height == 0) return GDC_SETDISPMODE_ERROR_ZERODIMENSION;
    if (scanned_lines <= height) return GDC_SETDISPMODE_ERROR_ZEROVLBANK;
    if ((scanned_lines - height) < 40) return GDC_SETDISPMODE_ERROR_VBLANKTOOSHORT;
    if ((scanned_lines - height) > 134) return GDC_SETDISPMODE_ERROR_VBLANKTOOLONG;
    if (width > 640) return GDC_SETDISPMODE_ERROR_HBLANKTOOSHORT;

    unsigned char is5mhz;
    __asm (
        "inb $0x31, %%al\n\t"
        "movb %%al, %0"
    : "=rm" (is5mhz) : : "%al");
    is5mhz = (~is5mhz) & 0x80;

    width = (width + 0xF) & 0xFFF0;
    unsigned int pitch = width >> 4;
    unsigned int hfp = 5;
    unsigned int hs = 4;
    unsigned int hbp = 44 - pitch;
    if (hbp > 32)
    {
        unsigned int fpp = hbp - 32;
        hfp += fpp;
        hbp = 32;
    }

    unsigned int pitch5 = 2 * pitch;
    unsigned int spitch5 = pitch5 - 2;
    unsigned int hfp5 = 2 * hfp - 1;
    unsigned int hs5 = 2 * hs - 1;
    unsigned int hbp5 = 2 * hbp - 1;
    unsigned int spitch = pitch - 2;
    hfp--; hs--; hbp--;

    unsigned int vfp = 7;
    unsigned int vs = 8;
    unsigned int vbp = scanned_lines - 15 - height;
    if (vbp > 63)
    {
        unsigned int fpp = vbp - 63;
        vfp += fpp;
        vbp = 63;
    }

    gdc_write_text_cmd(GDC_COMMAND_SYNC_OFF);
    gdc_write_text_param(0x10);
    gdc_write_text_param((unsigned char)spitch5);
    gdc_write_text_param(((unsigned char)hs5) | (((unsigned char)vs) << 5));
    gdc_write_text_param((((unsigned char)vs) >> 3) | (((unsigned char)hfp5) << 2));
    gdc_write_text_param((unsigned char)hbp5);
    gdc_write_text_param((unsigned char)vfp);
    gdc_write_text_param((unsigned char)height);
    gdc_write_text_param(((unsigned char)(height >> 8)) | (((unsigned char)vbp) << 2));
    gdc_write_text_cmd(GDC_COMMAND_PITCH);
    gdc_write_text_param((unsigned char)pitch5);

    gdc_write_gfx_cmd(GDC_COMMAND_SYNC_OFF);
    gdc_write_gfx_param(GDC_SYNC_NOCHAR | GDC_SYNC_REFRESH);
    if (is5mhz)
    {
        gdc_write_gfx_param((unsigned char)spitch5);
        gdc_write_gfx_param(((unsigned char)hs5) | (((unsigned char)vs) << 5));
        gdc_write_gfx_param((((unsigned char)vs) >> 3) | (((unsigned char)hfp5) << 2));
        gdc_write_gfx_param((unsigned char)hbp5);
        gdc_write_gfx_param((unsigned char)vfp);
        gdc_write_gfx_param((unsigned char)height);
        gdc_write_gfx_param(((unsigned char)(height >> 8)) | (((unsigned char)vbp) << 2));
        gdc_write_gfx_cmd(GDC_COMMAND_PITCH);
        gdc_write_gfx_param((unsigned char)pitch);
    }
    else
    {
        gdc_write_gfx_param((unsigned char)spitch);
        gdc_write_gfx_param(((unsigned char)hs) | (((unsigned char)vs) << 5));
        gdc_write_gfx_param((((unsigned char)vs) >> 3) | (((unsigned char)hfp) << 2));
        gdc_write_gfx_param((unsigned char)hbp);
        gdc_write_gfx_param((unsigned char)vfp);
        gdc_write_gfx_param((unsigned char)height);
        gdc_write_gfx_param(((unsigned char)(height >> 8)) | (((unsigned char)vbp) << 2));
        gdc_write_gfx_cmd(GDC_COMMAND_PITCH);
        gdc_write_gfx_param((unsigned char)pitch);
    }

    display_lines = height;
    display_pitch = pitch;
    return 0;
}

void gdc_scroll_simple_graphics(unsigned int topline)
{
    unsigned short startaddr = display_region_start + display_pitch * topline;
    unsigned short numlinestop = display_lines - topline;
    unsigned char p0 = (unsigned char)startaddr;
    unsigned char p1 = (unsigned char)(startaddr >> 8);
    unsigned char p2 = (unsigned char)(numlinestop << 4);
    unsigned char p3 = (unsigned char)(numlinestop >> 4) & 0x3F;
    unsigned char p4 = (unsigned char)display_region_start;
    unsigned char p5 = (unsigned char)(display_region_start >> 8);
    unsigned char p6 = 0x00;
    unsigned char p7 = 0x20;
    gdc_write_gfx_cmd(GDC_COMMAND_SCROLL(0));
    gdc_write_gfx_param(p0);
    gdc_write_gfx_param(p1);
    gdc_write_gfx_param(p2);
    gdc_write_gfx_param(p3);
    gdc_write_gfx_param(p4);
    gdc_write_gfx_param(p5);
    gdc_write_gfx_param(p6);
    gdc_write_gfx_param(p7);
}
