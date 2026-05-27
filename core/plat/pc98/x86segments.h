/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#ifndef X86SEGMENTS_H
#define X86SEGMENTS_H

static inline unsigned short hal_get_cs(void)
{
    unsigned short seg;
    __asm("mov %%cs, %0" : "=rm" (seg));
    return seg;
}

static inline unsigned short hal_get_ds(void)
{
    unsigned short seg;
    __asm("mov %%ds, %0" : "=rm" (seg));
    return seg;
}

static inline unsigned short hal_get_es(void)
{
    unsigned short seg;
    __asm("mov %%es, %0" : "=rm" (seg));
    return seg;
}

static inline unsigned short hal_get_ss(void)
{
    unsigned short seg;
    __asm("mov %%ss, %0" : "=rm" (seg));
    return seg;
}

static inline void hal_set_ds(unsigned short seg)
{
    __asm volatile ("mov %0, %%ds" : : "rm" (seg) : "%ds");
}

static inline void hal_set_es(unsigned short seg)
{
    __asm volatile ("mov %0, %%es" : : "rm" (seg) : "%es");
}

static inline void hal_set_ss(unsigned short seg)
{
    __asm volatile ("mov %0, %%ss" : : "rm" (seg) : "%ss");
}

#endif
