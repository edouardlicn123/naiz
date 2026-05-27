/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 *
 * LZ4 decompression C wrapper — calls Trixter's 8086 assembly routine.
 * The assembly expects DS:SI = source (4-byte size prefix + LZ4 tokens),
 * ES:DI = destination, returns decompressed size in AX.
 */

#include "lz4.h"
#include "x86segments.h"

int lz4_decompress(const unsigned char __far *src,
                   unsigned char __far *dst,
                   unsigned int dst_size)
{
    (void)dst_size;

    unsigned short src_off = (unsigned short)((unsigned long)src & 0xFFFF);
    unsigned short src_seg = (unsigned short)((unsigned long)src >> 16);
    unsigned short dst_off = (unsigned short)((unsigned long)dst & 0xFFFF);
    unsigned short dst_seg = (unsigned short)((unsigned long)dst >> 16);
    unsigned int result;

    hal_set_es(dst_seg);
    hal_set_ds(src_seg);

    __asm volatile (
        "push %%bp\n\t"
        "push %%bx\n\t"
        "push %%cx\n\t"
        "push %%dx\n\t"
        "call lz4_decompress_asm\n\t"
        "pop %%dx\n\t"
        "pop %%cx\n\t"
        "pop %%bx\n\t"
        "pop %%bp\n\t"
        : "=a" (result), "+D" (dst_off), "+S" (src_off)
        :
        : "memory"
    );

    hal_set_ds(hal_get_ss());
    return (int)result;
}
