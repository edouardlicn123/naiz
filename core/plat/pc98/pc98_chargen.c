/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#include "pc98_chargen.h"

static inline void set_jis_code(unsigned short code)
{
    __asm volatile (
        "outb %%al, $0xA1\n\t"
        "xchg %%al, %%ah\n\t"
        "outb %%al, $0xA3\n\t"
        "xchg %%al, %%ah\n\t"
    : : "a" (code));
}

static inline unsigned char read_char_ram(unsigned char addr)
{
    unsigned char data;
    __asm volatile (
        "outb %%al, $0xA5\n\t"
        "inb $0xA9, %%al\n\t"
    : "=a" (data) : "a" (addr));
    return data;
}

void chargen_get_char_data(unsigned short code, unsigned long *buffer)
{
    set_jis_code(code);
    if (code & 0x00FF)
    {
        for (unsigned char i = 0; i < 16; i++)
        {
            unsigned int row = (unsigned int)read_char_ram(i) << 8;
            row |= read_char_ram(i | 0x20);
            buffer[i] = row;
        }
    }
    else
    {
        for (unsigned char i = 0; i < 16; i++)
            buffer[i] = read_char_ram(i);
    }
}

void chargen_set_char_data(unsigned short code, const unsigned long *buffer)
{
    set_jis_code(code);
    for (unsigned char i = 0; i < 16; i++)
    {
        unsigned long row = buffer[i];
        __asm volatile (
            "movb %b0, %%al\n\toutb %%al, $0xA5\n\t"
            "movb %b1, %%al\n\toutb %%al, $0xA9\n\t"
        : : "rmi" ((unsigned char)i), "rmi" ((unsigned char)((row >> 8) & 0xFF)) : "%al");
        __asm volatile (
            "movb %b0, %%al\n\toutb %%al, $0xA5\n\t"
            "movb %b1, %%al\n\toutb %%al, $0xA9\n\t"
        : : "rmi" ((unsigned char)(i | 0x20)), "rmi" ((unsigned char)(row & 0xFF)) : "%al");
    }
}

unsigned short chargen_sjis_to_internal(unsigned short code)
{
    unsigned char first = code >> 8;
    unsigned char second = code & 0xFF;
    unsigned char is_even = second >= 0x9F;
    unsigned char out_low = second - 0x1F - (second >= 0x7F) - 0x5E * is_even;
    unsigned char out_high = (first - 0x70 - 0x40 * (first >= 0xA0)) * 2 - 0x21 + is_even;
    return ((unsigned short)out_high << 8) + out_low;
}
