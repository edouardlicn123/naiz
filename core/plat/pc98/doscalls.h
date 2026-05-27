/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#ifndef DOSCALLS_H
#define DOSCALLS_H

#include "x86segments.h"

#define DOS_ERR_BADFUNC     0x0001
#define DOS_ERR_FNOTFOUND   0x0002
#define DOS_ERR_PNOTFOUND   0x0003
#define DOS_ERR_TOOMANYFILES 0x0004
#define DOS_ERR_ACCESSDENIED 0x0005
#define DOS_ERR_BADHANDLE   0x0006
#define DOS_ERR_NOMEMCTRL   0x0007
#define DOS_ERR_OUTOFMEM    0x0008
#define DOS_ERR_BADMEMBLOCK 0x0009
#define DOS_ERR_BADENV      0x000A
#define DOS_ERR_BADFORMAT   0x000B
#define DOS_ERR_BADACCESS   0x000C

#define DOS_OPEN_READ      0x00
#define DOS_OPEN_WRITE     0x01
#define DOS_OPEN_READWRITE 0x02

#define DOS_SEEK_ABS  0x00
#define DOS_SEEK_REL  0x01
#define DOS_SEEK_END  0x02

typedef unsigned short dos_handle;

static inline void dos_write_str(char *str)
{
    hal_set_ds(hal_get_ss());
    __asm volatile (
        "movb $0x09, %%ah\n\t"
        "int $0x21"
    : : "d" (str) : "%ah");
}

static inline int dos_open_file(const char *path, unsigned char mode, dos_handle *handle)
{
    hal_set_ds(hal_get_ss());
    unsigned char errored;
    dos_handle h;
    __asm volatile (
        "movb $0x3D, %%ah\n\t"
        "int $0x21\n\t"
        "sbbb %b1, %b1"
    : "=a" (h), "=r" (errored) : "d" (path), "a" (mode));
    if (errored) return h;
    *handle = h;
    return 0;
}

static inline int dos_close_file(dos_handle handle)
{
    unsigned short err;
    __asm volatile (
        "movb $0x3E, %%ah\n\t"
        "int $0x21\n\t"
        "jc .end%=\n\t"
        "xorw %%ax, %%ax\n\t"
        ".end%=: "
    : "=a" (err) : "b" (handle));
    return err;
}

static inline int dos_read_file(dos_handle handle, unsigned short len, __far void *buf, unsigned short *read)
{
    unsigned short ps = ((unsigned long)buf) >> 16;
    unsigned char errored;
    unsigned short r;
    __asm volatile (
        "mov %5, %%ds\n\t"
        "movb $0x3F, %%ah\n\t"
        "int $0x21\n\t"
        "sbbb %b1, %b1"
    : "=a" (r), "=r" (errored) : "b" (handle), "c" (len), "d" ((unsigned short)((unsigned long)buf)), "rm" (ps) : "%ds");
    if (errored) return r;
    *read = r;
    return 0;
}

static inline int dos_write_file(dos_handle handle, unsigned short len, __far const void *buf, unsigned short *written)
{
    unsigned short ps = ((unsigned long)buf) >> 16;
    unsigned char errored;
    unsigned short w;
    __asm volatile (
        "mov %5, %%ds\n\t"
        "movb $0x40, %%ah\n\t"
        "int $0x21\n\t"
        "sbbb %b1, %b1"
    : "=a" (w), "=r" (errored) : "b" (handle), "c" (len), "d" ((unsigned short)((unsigned long)buf)), "rm" (ps) : "%ds");
    if (errored) return w;
    *written = w;
    return 0;
}

static inline int dos_seek_file(dos_handle handle, unsigned char method, unsigned long len, unsigned long *newpos)
{
    unsigned char errored;
    unsigned short pl, pu;
    __asm volatile (
        "movb $0x42, %%ah\n\t"
        "int $0x21\n\t"
        "sbbb %b2, %b2"
    : "=a" (pl), "=d" (pu), "=r" (errored) : "b" (handle), "a" (method), "c" ((unsigned short)(len >> 16)), "d" ((unsigned short)len));
    if (errored) return pl;
    *newpos = ((unsigned long)pl) | (((unsigned long)pu) << 16);
    return 0;
}

static inline __far void *dos_mem_alloc(unsigned short paras)
{
    unsigned short as;
    unsigned char errored;
    __asm volatile (
        "movb $0x48, %%ah\n\t"
        "int $0x21\n\t"
        "sbbb %b1, %b1"
    : "=a" (as), "=r" (errored) : "b" (paras));
    if (errored) return (__far void *)0;
    return (__far void *)(((unsigned long)as) << 16);
}

static inline int dos_mem_free(const __far void *ptr)
{
    unsigned short p = ((unsigned long)ptr) >> 16;
    unsigned short err;
    __asm volatile (
        "mov %1, %%es\n\t"
        "movb $0x49, %%ah\n\t"
        "int $0x21\n\t"
        "jc .end%=\n\t"
        "xorw %%ax, %%ax\n\t"
        ".end%=: "
    : "=a" (err) : "rm" (p) : "%es");
    return err;
}

#endif
