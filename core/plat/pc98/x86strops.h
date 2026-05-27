/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#ifndef X86STROPS_H
#define X86STROPS_H

#include "x86segments.h"

static inline void hal_memcpy16_near(const void *src, void *dst, unsigned short words)
{
    unsigned short s = hal_get_ss();
    hal_set_ds(s);
    hal_set_es(s);
    __asm volatile (
        "rep movsw"
    : "+c" (words), "+S" (src), "+D" (dst) : );
}

static inline void hal_memset16_near(unsigned short val, void *dst, unsigned short words)
{
    hal_set_es(hal_get_ss());
    __asm volatile (
        "rep stosw"
    : "+c" (words), "+D" (dst) : "a" (val));
}

static inline void hal_memset8_near(unsigned char val, void *dst, unsigned short count)
{
    hal_set_es(hal_get_ss());
    __asm volatile (
        "rep stosb"
    : "+c" (count), "+D" (dst) : "a" (val));
}

static inline void hal_memset16_far(unsigned short val, __far void *dst, unsigned short words)
{
    unsigned short dsto = (unsigned short)((unsigned long)dst);
    unsigned short dsts = ((unsigned long)dst) >> 16;
    __asm volatile (
        "mov %3, %%es\n\t"
        "rep stosw"
    : "+c" (words), "+D" (dsto) : "a" (val), "rm" (dsts) : "%es");
}

static inline void hal_memcpy16_far(__far const void *src, __far void *dst, unsigned short words)
{
    unsigned short srco = (unsigned short)((unsigned long)src);
    unsigned short dsto = (unsigned short)((unsigned long)dst);
    unsigned short srcs = ((unsigned long)src) >> 16;
    unsigned short dsts = ((unsigned long)dst) >> 16;
    __asm volatile (
        "mov %3, %%ds\n\t"
        "mov %4, %%es\n\t"
        "rep movsw"
    : "+c" (words), "+S" (srco), "+D" (dsto) : "rm" (srcs), "rm" (dsts) : "%ds", "%es");
}

#endif
