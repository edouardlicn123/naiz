/*
 * farchive.c — On-demand reader for TOC-archived game files.
 *
 * See farchive.h for the archive layout and usage contract.
 * Pure library (core/lib): no platform headers, no logging; failures are
 * signalled via return codes and reported by engine callers.
 */
#include <stdlib.h>
#include <string.h>
#include "farchive.h"
#include "endian.h"

/* Upper bound for a resident TOC: 4 + 8192*20 = 163844 bytes. */
#define FARCHIVE_MAX_RESIDENT (4 + 8192 * FARCHIVE_TOC_ENTRY)

/* 199E §3.3: 单次 fread 超过这个长度时拆块，块间调一次进度 hook，让解码期
 * 之外的读盘段也能泵音频。16KB 与 image.c 的 I/O 粒度一致。 */
#ifndef FARCHIVE_READ_CHUNK
#define FARCHIVE_READ_CHUNK 16384
#endif

static void (*g_read_progress_hook)(void) = 0;

void farchive_set_progress_hook(void (*fn)(void))
{
    g_read_progress_hook = fn;
}

/* Compare a caller name (NUL terminated) against a TOC name (12 bytes,
 * NUL padded) case-insensitively.  Stops at the first NUL on either side:
 * both NUL => match, exactly one NUL => mismatch. */
static int farchive_name_match(const char *name, const uint8_t *tname)
{
    int k;
    for (k = 0; k < 12; k++) {
        uint8_t c = (uint8_t)name[k];
        uint8_t t = tname[k];

        if (c >= 'a' && c <= 'z') c = (uint8_t)(c - 'a' + 'A');
        if (t >= 'a' && t <= 'z') t = (uint8_t)(t - 'a' + 'A');

        if (c == 0 || t == 0)
            return (c == t);
        if (c != t)
            return 0;
    }
    return 1;
}

int farchive_open(FArchive *a, const char *path, int max_entries)
{
    uint8_t hdr[4];
    long    fsize;
    long    header_bytes;
    uint32_t count;

    if (!a)
        return -1;
    memset(a, 0, sizeof(*a));

    a->fp = fopen(path, "rb");
    /* Audit C2 false positive: the result is checked on the next line. */
    if (!a->fp)
        return -1;

    if (fseek(a->fp, 0, SEEK_END) != 0)
        goto fail;
    fsize = ftell(a->fp);
    if (fsize < 4)
        goto fail;
    if (fseek(a->fp, 0, SEEK_SET) != 0)
        goto fail;
    if (fread(hdr, 1, 4, a->fp) != 4)
        goto fail;

    count = read32_le(hdr);
    if (max_entries > 0 && count > (uint32_t)max_entries) {
        a->truncated = 1;
        count = (uint32_t)max_entries;
    }
    header_bytes = 4 + (long)count * FARCHIVE_TOC_ENTRY;
    if (header_bytes > FARCHIVE_MAX_RESIDENT || header_bytes > fsize)
        goto fail;
    a->file_size = fsize;

    a->toc = (uint8_t *)malloc((size_t)header_bytes);
    /* Audit C1 false positive: the result is checked on the next line. */
    if (!a->toc)
        goto fail;
    if (fseek(a->fp, 0, SEEK_SET) != 0)
        goto fail;
    if (fread(a->toc, 1, (size_t)header_bytes, a->fp) != (size_t)header_bytes)
        goto fail;

    a->count = (int)count;
    return 0;

fail:
    farchive_close(a);
    return -1;
}

void farchive_close(FArchive *a)
{
    if (!a)
        return;
    if (a->fp) {
        fclose(a->fp);
        a->fp = NULL;
    }
    if (a->toc) {
        free(a->toc);
        a->toc = NULL;
    }
    a->count = 0;
    a->file_size = 0;
    a->truncated = 0;
}

int farchive_lookup_id(const FArchive *a, int id,
                       long *out_offset, long *out_size)
{
    long entry_off;

    if (!a || !a->toc)
        return -1;
    if (id < 0 || id >= a->count)
        return -1;
    entry_off = 4 + (long)id * FARCHIVE_TOC_ENTRY;
    if (entry_off + FARCHIVE_TOC_ENTRY > a->file_size)
        return -1;

    if (out_offset)
        *out_offset = (long)read32_le(a->toc + entry_off + 12);
    if (out_size)
        *out_size = (long)read32_le(a->toc + entry_off + 16);
    return 0;
}

int farchive_lookup_name(const FArchive *a, const char *name,
                         long *out_offset, long *out_size, int *out_id)
{
    int i;

    if (!a || !a->toc || !name)
        return -1;
    for (i = 0; i < a->count; i++) {
        const uint8_t *tname = a->toc + (size_t)(4 + (long)i * FARCHIVE_TOC_ENTRY);
        if (farchive_name_match(name, tname)) {
            if (out_offset)
                *out_offset = (long)read32_le(tname + 12);
            if (out_size)
                *out_size = (long)read32_le(tname + 16);
            if (out_id)
                *out_id = i;
            return 0;
        }
    }
    return -1;
}

uint8_t *farchive_read_alloc(const FArchive *a, long offset, long size,
                             long *out_read)
{
    uint8_t *buf;

    if (out_read)
        *out_read = 0;
    if (!a || !a->fp || !a->toc)
        return NULL;
    if (offset < 0 || offset > a->file_size)
        return NULL;
    if (size < 0 || size > a->file_size - offset)
        return NULL;
    if (size == 0)
        return NULL;

    buf = (uint8_t *)malloc((size_t)size);
    if (!buf)
        return NULL;
    if (fseek(a->fp, offset, SEEK_SET) != 0) {
        free(buf);
        return NULL;
    }
    {
        long remaining = size;
        uint8_t *p = buf;

        while (remaining > 0) {
            size_t chunk = remaining > FARCHIVE_READ_CHUNK
                         ? (size_t)FARCHIVE_READ_CHUNK : (size_t)remaining;

            if (fread(p, 1, chunk, a->fp) != chunk) {
                free(buf);
                return NULL;
            }
            p += chunk;
            remaining -= (long)chunk;
            if (g_read_progress_hook)
                g_read_progress_hook();
        }
    }
    if (out_read)
        *out_read = size;
    return buf;
}

long farchive_read_buf(const FArchive *a, long offset, long size,
                       void *dst, long dst_cap)
{
    long n;

    if (!a || !a->fp || !a->toc)
        return -1;
    if (offset < 0 || offset > a->file_size)
        return -1;
    if (size < 0 || size > a->file_size - offset)
        return -1;
    if (size == 0)
        return 0;
    if (!dst || dst_cap <= 0)
        return -1;

    n = size;
    if (n > dst_cap)
        n = dst_cap;
    if (fseek(a->fp, offset, SEEK_SET) != 0)
        return -1;
    if (fread(dst, 1, (size_t)n, a->fp) != (size_t)n)
        return -1;
    return n;
}
