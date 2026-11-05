/*
 * naiz_file.c — Shared file I/O helpers.
 */
#include <stdio.h>
#include <stdlib.h>
#include "naiz_file.h"

void *file_read_all(const char *path, long *out_size)
{
    FILE *f;
    long fsize;
    void *buf;

    f = fopen(path, "rb");
    if (!f) return NULL;

    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return NULL; }
    fsize = ftell(f);
    if (fsize < 0) { fclose(f); return NULL; }
    if (fseek(f, 0, SEEK_SET) != 0) { fclose(f); return NULL; }
    buf = malloc(fsize);
    if (!buf) { fclose(f); return NULL; }
    if (fread(buf, 1, fsize, f) != (size_t)fsize) {
        free(buf); fclose(f); return NULL;
    }
    fclose(f);

    if (out_size) *out_size = fsize;
    return buf;
}
