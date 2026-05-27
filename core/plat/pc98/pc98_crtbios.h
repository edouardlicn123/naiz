/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#ifndef PC98_CRTBIOS_H
#define PC98_CRTBIOS_H

#define CRT_MODE_TEXT_25_ROWS    0x00
#define CRT_MODE_TEXT_20_ROWS    0x01
#define CRT_MODE_TEXT_80_COLUMNS 0x00
#define CRT_MODE_TEXT_40_COLUMNS 0x02
#define CRT_MODE_TEXT_KANJI      0x00
#define CRT_MODE_TEXT_GRAPHIC    0x04
#define CRT_MODE_TEXT_CGACCESS_CODE 0x00
#define CRT_MODE_TEXT_CGACCESS_DOT  0x08

#define CRT_MODE_GRAPHIC_COLOUR     0x00
#define CRT_MODE_GRAPHIC_MONOCHROME 0x20
#define CRT_MODE_GRAPHIC_640x400    0xC0

static inline void crt_bios_text_set_mode(unsigned char mode)
{
    __asm volatile (
        "movb $0x0A, %%ah\n\tint $0x18\n\t"
    : : "a" (mode) : "%ah");
}

static inline unsigned char crt_bios_text_get_mode(void)
{
    unsigned char mode;
    __asm volatile (
        "movb $0x0B, %%ah\n\tint $0x18\n\t"
    : "=a" (mode) : : "%ah");
    return mode;
}

static inline void crt_bios_text_on(void)
{
    __asm volatile ("movb $0x0C, %%ah\n\tint $0x18\n\t" : : : "%ah");
}

static inline void crt_bios_text_off(void)
{
    __asm volatile ("movb $0x0D, %%ah\n\tint $0x18\n\t" : : : "%ah");
}

static inline void crt_bios_graphics_on(void)
{
    __asm volatile ("movb $0x40, %%ah\n\tint $0x18\n\t" : : : "%ah");
}

static inline void crt_bios_graphics_off(void)
{
    __asm volatile ("movb $0x41, %%ah\n\tint $0x18\n\t" : : : "%ah");
}

static inline void crt_bios_graphics_set_mode(unsigned char mode)
{
    __asm volatile (
        "movb $0x42, %%ah\n\tint $0x18\n\t"
    : : "c" (mode) : "%ah");
}

#endif
