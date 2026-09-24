/*
 * farchive.h — On-demand reader for TOC-archived game files.
 *
 * Shared by IMAGE.DAT and SCENE.DAT (devdoc 100).  The archive layout is
 * the single source of truth enforced by tools/naiz_lib/toc_archive.py:
 *
 *   uint32   count            number of entries
 *   count x {                 TOC entry:
 *     char  name[12]          8.3 file name, NUL padded (debug/lookup)
 *     uint32 offset           absolute byte offset of the payload
 *     uint32 size             payload size in bytes (0 = hole, no payload)
 *   }
 *   raw payload data (offsets above are absolute into the whole file)
 *
 * Design:
 *   - The 4 + count*20 byte TOC is kept resident (count <= 8192 there).
 *   - Payloads are read on demand (read_alloc / read_buf); the file stays
 *     open for streaming seeks.
 *   - Pure library: no platform headers, no logging.  Errors surface as
 *     -1/NULL return codes; engine callers (image.c etc.) add hal_log on
 *     failure paths.  This mirrors the existing silent lib/ convention
 *     (naiz_file.c, tr.c, font.c).
 */
#ifndef FARCHIVE_H
#define FARCHIVE_H

#include <stdint.h>
#include <stdio.h>

#define FARCHIVE_TOC_ENTRY 20  /* name[12] + offset[4] + size[4] */

typedef struct {
    FILE    *fp;          /* open archive stream (NULL when closed) */
    uint8_t *toc;         /* resident TOC: 4 + count*20 bytes */
    long     file_size;   /* total archive file size in bytes */
    int      count;       /* number of entries */
    int      truncated;   /* 1 = TOC count was clamped to max_entries */
} FArchive;

/* Open an archive.  Reads and validates the header + TOC; keeps the file
 * open for streaming.  `max_entries` caps the resident TOC (count is
 * clamped and `a->truncated` set).  Returns 0 on success, -1 on failure.
 * On failure `a` is left fully closed / zeroed. */
int  farchive_open(FArchive *a, const char *path, int max_entries);

/* Close an archive and free its TOC.  Safe on a zeroed / half-opened a. */
void farchive_close(FArchive *a);

/* Look up entry by sequential TOC index.  Returns 0 with *out_offset /
 * *out_size filled, -1 on bad id or out-of-range TOC.  A size of 0 is a
 * valid hole: the entry exists but carries no payload. */
int  farchive_lookup_id(const FArchive *a, int id,
                        long *out_offset, long *out_size);

/* Look up an entry by 8.3 name (case-insensitive, NUL padded in TOC).
 * Returns 0 on match (optionally filling out_offset/out_size/out_id),
 * -1 on no match.  `name` must be NUL terminated. */
int  farchive_lookup_name(const FArchive *a, const char *name,
                          long *out_offset, long *out_size, int *out_id);

/* Read an entire payload into a freshly malloc'd buffer (caller frees).
 * Returns the buffer on success (*out_read receives the byte length), or
 * NULL on failure (bad offset/size, hole, seek/read error, OOM). */
uint8_t *farchive_read_alloc(const FArchive *a, long offset, long size,
                             long *out_read);

/* Read up to `size` bytes of a payload into caller-owned `dst` (capacity
 * `dst_cap`, bytes).  Returns the number of bytes actually read, or -1 on
 * error.  Reads are clamped to dst_cap; a truncated read is the caller's
 * choice, not an error here. */
long farchive_read_buf(const FArchive *a, long offset, long size,
                       void *dst, long dst_cap);

#endif
