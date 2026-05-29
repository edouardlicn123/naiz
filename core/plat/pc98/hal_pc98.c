/*
 * 来源项目：MHVNVisualNovelEngine (compatibility check, mode init logic)
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#include "hal.h"
#include "pc98_gdc.h"
#include "pc98_interrupt.h"
#include "x86interrupt.h"
#include "pc98_keyboard.h"
#include "x86segments.h"

extern volatile unsigned char vsynced;
extern volatile unsigned short vsync_counter;
extern void vsync_isr(void);

int hal_check_compatibility(void)
{
    unsigned int outres;
    __asm volatile (
        "mov $0x1000, %0\n\t"
        "clc\n\t"
        "mov $0x1000, %%ax\n\t"
        "int $0x1A\n\t"
        "jc .buggyIBM%=\n\t"
        "mov %%ax, %0\n\t"
        ".buggyIBM%=:"
    : "=rm" (outres) : : "%ax");
    if (outres == 0x1000)
        return 1;

    gdc_set_mode2(GDC_MODE2_8COLOURS);
    __asm volatile ("mov $8, %%ax\n\t1: dec %%ax\n\tjnz 1b" : : : "%ax");
    gdc_set_mode2(GDC_MODE2_16COLOURS);

    return 1;
}

void hal_video_init(void)
{
    hal_cli();

    //gdc_set_display_mode(640, 400, 440);
    gdc_start_graphics();
    gdc_set_graphics_line_scale(1);

    gdc_set_mode1(GDC_MODE1_LINEDOUBLE_ON);
    gdc_set_mode1(GDC_MODE1_COLOUR);
    gdc_set_display_page(0);
    gdc_set_draw_page(0);
    gdc_set_mode2(GDC_MODE2_16COLOURS);
    gdc_set_display_region(0, 400);
    gdc_scroll_simple_graphics(0);
    gdc_write_text_cmd(GDC_COMMAND_SYNC_ON);
    gdc_write_gfx_cmd(GDC_COMMAND_SYNC_ON);

    gdc_set_palette_colour(0, 0x00, 0x00, 0x00);
    gdc_set_palette_colour(1, 0x33, 0x33, 0xBB);

    hal_interrupt_set(INTERRUPT_VECTOR_VSYNC, vsync_isr);
    pic_enable_irqs(INTERRUPT_MASK_VSYNC);
    gdc_interrupt_reset();
    vsynced = 1;

    hal_sti();
}

void hal_video_set_palette(int idx, unsigned char r, unsigned char g, unsigned char b)
{
    gdc_set_palette_colour((unsigned char)idx, r, g, b);
}

static void fill_plane(unsigned long seg_off, unsigned short fill_word, unsigned int words)
{
    unsigned short seg = (unsigned short)(seg_off >> 16);
    unsigned short off = (unsigned short)(seg_off & 0xFFFF);
    __asm volatile (
        "mov %3, %%es\n\t"
        "rep stosw\n\t"
        : "+c" (words), "+D" (off)
        : "a" (fill_word), "rm" (seg)
        : "%es");
}

void hal_video_fill_rect(int x, int y, int w, int h, int color)
{
    (void)x; (void)y; (void)w; (void)h;
    unsigned short v[4];
    v[0] = (color & 1) ? 0xFFFF : 0x0000;
    v[1] = (color & 2) ? 0xFFFF : 0x0000;
    v[2] = (color & 4) ? 0xFFFF : 0x0000;
    v[3] = (color & 8) ? 0xFFFF : 0x0000;
    fill_plane(0xA8000000L, v[0], 16000);
    fill_plane(0xB0000000L, v[1], 16000);
    fill_plane(0xB8000000L, v[2], 16000);
    fill_plane(0xE0000000L, v[3], 16000);
}

void hal_video_vsync_wait(void)
{
    unsigned int timeout = 0;
    while (!vsynced)
    {
        __asm volatile ("nop");
        if (++timeout > 1000) break;
    }
    vsynced = 0;
}

void hal_video_clear_screen(void)
{
    hal_video_fill_rect(0, 0, 640, 400, 1);
}

#define TEXT_VRAM_SEG 0xA000
#define TEXT_COLS 80
#define TEXT_ROWS 25
#define TEXT_ATTR_DEFAULT 0x07

void hal_video_write_text_char(int row, int col, unsigned char ch, unsigned char attr)
{
    unsigned short __far *vram = (unsigned short __far *)0xA0000000L;
    vram[row * TEXT_COLS + col] = (unsigned short)(((unsigned short)attr << 8) | ch);
}

void hal_video_scroll_text(void)
{
    unsigned short __far *vram = (unsigned short __far *)0xA0000000L;
    unsigned short space = (unsigned short)(((unsigned short)TEXT_ATTR_DEFAULT << 8) | ' ');
    int r, c;
    for (r = 1; r < TEXT_ROWS; r++)
    {
        for (c = 0; c < TEXT_COLS; c++)
        {
            vram[(r - 1) * TEXT_COLS + c] = vram[r * TEXT_COLS + c];
        }
    }
    for (c = 0; c < TEXT_COLS; c++)
    {
        vram[(TEXT_ROWS - 1) * TEXT_COLS + c] = space;
    }
}

void hal_video_clear_text(void)
{
    unsigned short __far *vram = (unsigned short __far *)0xA0000000L;
    unsigned short space = (unsigned short)(((unsigned short)TEXT_ATTR_DEFAULT << 8) | ' ');
    int i;
    for (i = 0; i < TEXT_COLS * TEXT_ROWS; i++)
    {
        vram[i] = space;
    }
}

void hal_video_deinit(void)
{
    gdc_interrupt_reset();
}

void hal_input_init(void)
{
}

int hal_input_poll(void)
{
    return 0;
}

int hal_input_state(int scancode)
{
    unsigned char __far *key_status = (unsigned char __far *)0x052A;
    int byte = scancode >> 3;
    int bit = scancode & 7;
    return (key_status[byte] >> bit) & 1;
}

int hal_file_open(const char *path, unsigned char mode)
{
    unsigned char ok_flag;
    unsigned short result;
    if (mode == 0)
    {
        __asm volatile (
            "mov $0x3D00, %%ax\n\t"
            "int $0x21\n\t"
            "jc .Lfail%=\n\t"
            "movb $1, %0\n\t"
            "movw %%ax, %1\n\t"
            "jmp .Ldone%=\n\t"
            ".Lfail%=:\n\t"
            "movb $0, %0\n\t"
            ".Ldone%=:"
            : "=rm" (ok_flag), "=rm" (result)
            : "d" (path)
            : "%ax");
    }
    else if (mode == 1)
    {
        __asm volatile (
            "xor %%cx, %%cx\n\t"
            "mov $0x3C00, %%ax\n\t"
            "int $0x21\n\t"
            "jc .Lfail%=\n\t"
            "movb $1, %0\n\t"
            "movw %%ax, %1\n\t"
            "jmp .Ldone%=\n\t"
            ".Lfail%=:\n\t"
            "movb $0, %0\n\t"
            ".Ldone%=:"
            : "=rm" (ok_flag), "=rm" (result)
            : "d" (path)
            : "%ax", "%cx");
    }
    else if (mode == 2)
    {
        __asm volatile (
            "mov $0x3D01, %%ax\n\t"
            "int $0x21\n\t"
            "jc .Lfail%=\n\t"
            "movb $1, %0\n\t"
            "movw %%ax, %1\n\t"
            "jmp .Ldone%=\n\t"
            ".Lfail%=:\n\t"
            "movb $0, %0\n\t"
            ".Ldone%=:"
            : "=rm" (ok_flag), "=rm" (result)
            : "d" (path)
            : "%ax");
        if (!ok_flag) return -1;
        int fd = (int)result;
        __asm volatile (
            "xor %%cx, %%cx\n\t"
            "xor %%dx, %%dx\n\t"
            "mov $0x4202, %%ax\n\t"
            "int $0x21\n\t"
            "jc .Lfail%=\n\t"
            "movb $1, %0\n\t"
            "jmp .Ldone%=\n\t"
            ".Lfail%=:\n\t"
            "movb $0, %0\n\t"
            ".Ldone%=:"
            : "=rm" (ok_flag)
            : "b" (fd)
            : "%ax", "%cx", "%dx");
        if (!ok_flag) { hal_file_close(fd); return -1; }
        return fd;
    }
    else return -1;
    return ok_flag ? (int)result : -1;
}

int hal_file_read(int fd, void *buf, int count)
{
    unsigned short result;
    unsigned short flags;
    __asm volatile (
        "mov %4, %%bx\n\t"
        "mov %3, %%cx\n\t"
        "mov $0x3F00, %%ax\n\t"
        "int $0x21\n\t"
        "pushf\n\t"
        "pop %0\n\t"
        : "=rm" (flags), "=a" (result)
        : "d" (buf), "rm" (count), "rm" ((unsigned short)fd)
        : "%bx", "%cx", "cc");
    if (flags & 1) return -1;
    return (int)result;
}

int hal_file_write(int fd, void const *buf, int count)
{
    unsigned short result;
    unsigned short flags;
    __asm volatile (
        "mov %4, %%bx\n\t"
        "mov %3, %%cx\n\t"
        "mov $0x4000, %%ax\n\t"
        "int $0x21\n\t"
        "pushf\n\t"
        "pop %0\n\t"
        : "=rm" (flags), "=a" (result)
        : "d" (buf), "rm" (count), "rm" ((unsigned short)fd)
        : "%bx", "%cx", "cc");
    if (flags & 1) return -1;
    return (int)result;
}

int hal_file_read_far(int fd, unsigned short seg, unsigned short off, int count)
{
    unsigned short result;
    unsigned short flags;
    __asm volatile (
        "push %%ds\n\t"
        "mov %4, %%ds\n\t"
        "mov %3, %%bx\n\t"
        "mov %5, %%cx\n\t"
        "mov $0x3F00, %%ax\n\t"
        "int $0x21\n\t"
        "pop %%ds\n\t"
        "pushf\n\t"
        "pop %0\n\t"
        : "=rm" (flags), "=a" (result)
        : "d" (off), "rm" ((unsigned short)fd), "rm" (seg), "rm" (count)
        : "%bx", "%cx", "cc");
    if (flags & 1) return -1;
    return (int)result;
}

int hal_file_write_far(int fd, unsigned short seg, unsigned short off, int count)
{
    unsigned short result;
    unsigned short flags;
    __asm volatile (
        "push %%ds\n\t"
        "mov %4, %%ds\n\t"
        "mov %3, %%bx\n\t"
        "mov %5, %%cx\n\t"
        "mov $0x4000, %%ax\n\t"
        "int $0x21\n\t"
        "pop %%ds\n\t"
        "pushf\n\t"
        "pop %0\n\t"
        : "=rm" (flags), "=a" (result)
        : "d" (off), "rm" ((unsigned short)fd), "rm" (seg), "rm" (count)
        : "%bx", "%cx", "cc");
    if (flags & 1) return -1;
    return (int)result;
}

int hal_file_close(int fd)
{
    unsigned short flags;
    __asm volatile (
        "mov %1, %%bx\n\t"
        "mov $0x3E00, %%ax\n\t"
        "int $0x21\n\t"
        "pushf\n\t"
        "pop %0\n\t"
        : "=rm" (flags)
        : "rm" ((unsigned short)fd)
        : "%ax", "%bx", "cc");
    return (flags & 1) ? -1 : 0;
}

int hal_file_seek(int fd, unsigned char method, unsigned long len, unsigned long *newpos)
{
    unsigned short hi = (unsigned short)(len >> 16);
    unsigned short dx_io = (unsigned short)(len & 0xFFFF);
    unsigned short ax_val = (unsigned short)(0x4200 | method);
    unsigned short result_ax;
    unsigned char ok_flag;
    __asm volatile (
        "mov %4, %%bx\n\t"
        "mov %3, %%ax\n\t"
        "int $0x21\n\t"
        "jc .Lfail%=\n\t"
        "movb $1, %0\n\t"
        "movw %%ax, %1\n\t"
        "jmp .Ldone%=\n\t"
        ".Lfail%=:\n\t"
        "movb $0, %0\n\t"
        ".Ldone%=:"
        : "=rm" (ok_flag), "=a" (result_ax), "+d" (dx_io)
        : "rm" (ax_val), "rm" ((unsigned short)fd),
          "c" (hi));
    if (!ok_flag) return -1;
    if (newpos) *newpos = ((unsigned long)dx_io << 16) | result_ax;
    return 0;
}

void __far *hal_mem_alloc(unsigned short segments)
{
    unsigned short as;
    unsigned char errored;
    __asm volatile (
        "movb $0x48, %%ah\n\t"
        "int $0x21\n\t"
        "sbbb %b1, %b1"
    : "=a" (as), "=r" (errored) : "b" (segments));
    if (errored) return (void __far *)0;
    return (void __far *)(((unsigned long)as) << 16);
}

void hal_mem_free(void __far *ptr)
{
    unsigned short p = (unsigned short)((unsigned long)ptr >> 16);
    __asm volatile (
        "mov %0, %%es\n\t"
        "movb $0x49, %%ah\n\t"
        "int $0x21\n\t"
        : : "rm" (p) : "%es", "%ax");
}

void hal_interrupt_set(unsigned char vector, void (*handler)(void))
{
    unsigned short __far *ivt = (unsigned short __far *)0x0;
    ivt[vector * 2]     = (unsigned short)handler;
    ivt[vector * 2 + 1] = hal_get_cs();
}

void hal_interrupt_get(unsigned char vector, void (**handler)(void))
{
    unsigned short __far *ivt = (unsigned short __far *)0x0;
    void __far *far_ptr = (void __far *)(((unsigned long)ivt[vector * 2 + 1] << 16) | ivt[vector * 2]);
    *handler = (void (*)(void))far_ptr;
}

void hal_vsync_enable(void)
{
    hal_interrupt_set(INTERRUPT_VECTOR_VSYNC, vsync_isr);
    pic_enable_irqs(INTERRUPT_MASK_VSYNC);
}

void hal_vsync_disable(void)
{
    pic_disable_irqs(INTERRUPT_MASK_VSYNC);
}

int hal_vsync_count(void)
{
    unsigned short c = vsync_counter;
    vsync_counter = 0;
    return (int)c;
}

int hal_serial_init(int port, unsigned long baud)
{
    unsigned char param;
    if (baud <= 150) param = 0x00;
    else if (baud <= 300) param = 0x20;
    else if (baud <= 600) param = 0x40;
    else if (baud <= 1200) param = 0x60;
    else if (baud <= 2400) param = 0x80;
    else if (baud <= 4800) param = 0xA0;
    else param = 0xE0;

    param |= 0x03;

    __asm volatile (
        "movb $0x00, %%ah\n\t"
        "int $0x14\n\t"
        : : "a" (param), "d" ((unsigned short)port)
        : "cc");
    return 0;
}

void hal_serial_write_char(unsigned char c)
{
    unsigned short tries = 0;
    unsigned short result;
    for (;;)
    {
        __asm volatile (
            "movb $0x01, %%ah\n\t"
            "int $0x14\n\t"
            : "=a" (result)
            : "d" ((unsigned short)0), "a" ((unsigned short)c)
            : "cc");
        if (result & 0x8000) break;
        if (++tries > 10000) break;
    }
}

void hal_serial_write(const char *s)
{
    while (*s)
    {
        hal_serial_write_char((unsigned char)*s);
        s++;
    }
}
