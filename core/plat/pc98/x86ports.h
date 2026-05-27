/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#ifndef X86PORTS_H
#define X86PORTS_H

static inline void hal_outb(unsigned short port, unsigned char val)
{
    __asm volatile ("outb %%al, %w1" : : "a" (val), "d" (port));
}

static inline unsigned char hal_inb(unsigned short port)
{
    unsigned char val;
    __asm volatile ("inb %w1, %%al" : "=a" (val) : "d" (port));
    return val;
}

static inline void hal_outw(unsigned short port, unsigned short val)
{
    __asm volatile ("outw %%ax, %w1" : : "a" (val), "d" (port));
}

static inline unsigned short hal_inw(unsigned short port)
{
    unsigned short val;
    __asm volatile ("inw %w1, %%ax" : "=a" (val) : "d" (port));
    return val;
}

#endif
