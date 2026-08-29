/*
 * save_io.c — Shared save-file I/O helpers for save.c and save_sys.c.
 *
 * Both modules previously duplicated the same checksum computation and
 * the write path (set magic/version/checksum, fopen, fwrite, fclose).
 * This module provides the common primitives; the version-dependent read
 * sizing in save_read stays in save.c.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
#include "save.h"
#include "hal.h"

/*
 * save_checksum — Sum all bytes of the buffer (used for save file checksum).
 * The checksum field must be zeroed by the caller before calling.
 */
static unsigned int save_checksum(const void *data, size_t sz)
{
    unsigned int sum = 0;
    size_t i;
    const unsigned char *p = (const unsigned char *)data;
    for (i = 0; i < sz; i++)
        sum += p[i];
    return sum;
}

/*
 * save_file_write — Set magic (offset 0) / version (offset 4) / checksum
 * (at cs_offset), then write the struct to path.
 * Callers pass offsetof(SaveData, checksum) / offsetof(SystemSave, checksum)
 * because the two structs place the checksum field at different offsets
 * (SaveData@60, SystemSave@8).  Hardcoding one offset breaks the other.
 * Returns 0 on success, -1 on failure.
 */
int save_file_write(const char *path, void *data, size_t sz,
                    unsigned int magic, unsigned int version,
                    size_t cs_offset, const char *tag)
{
    FILE *f;
    unsigned char *p = (unsigned char *)data;
    char b[96];

    f = fopen(path, "wb");
    if (!f) {
        snprintf(b, sizeof(b), "%s fopen fail\r\n", tag);
        hal_log(b);
        return -1;
    }
    memcpy(p + 0, &magic, sizeof(magic));
    memcpy(p + 4, &version, sizeof(version));
    {
        unsigned int cs;
        memset(p + cs_offset, 0, sizeof(cs));
        cs = save_checksum(p, sz);
        memcpy(p + cs_offset, &cs, sizeof(cs));
    }
    if (fwrite(data, sz, 1, f) != 1) {
        snprintf(b, sizeof(b), "%s fwrite fail\r\n", tag);
        hal_log(b);
        fclose(f);
        return -1;
    }
    fclose(f);
    return 0;
}

/*
 * save_file_read — Read a save file, validating magic / version / checksum.
 * Fills buf with up to bufsz bytes.  When the stored version is lower than
 * max_version, only min_size bytes are read (older, smaller layout).
 * cs_offset is the caller struct's checksum field offset
 * (offsetof(SaveData, checksum) / offsetof(SystemSave, checksum)).
 * Returns 0 on success, -1 on failure (with hal_log diagnostics).
 */
int save_file_read(const char *path, void *buf, size_t bufsz, size_t min_size,
                   unsigned int expected_magic, unsigned int max_version,
                   size_t cs_offset, const char *tag)
{
    FILE *f;
    unsigned char *p = (unsigned char *)buf;
    unsigned int magic, ver;
    size_t read_sz;
    unsigned int saved_cs, sum;
    char b[96];

    f = fopen(path, "rb");
    if (!f) {
        snprintf(b, sizeof(b), "%s fopen fail\r\n", tag);
        hal_log(b);
        return -1;
    }
    if (fread(&magic, sizeof(magic), 1, f) != 1) {
        snprintf(b, sizeof(b), "%s fread magic fail\r\n", tag);
        hal_log(b);
        fclose(f);
        return -1;
    }
    if (fread(&ver, sizeof(ver), 1, f) != 1) {
        snprintf(b, sizeof(b), "%s fread version fail\r\n", tag);
        hal_log(b);
        fclose(f);
        return -1;
    }
    if (magic != expected_magic) {
        snprintf(b, sizeof(b), "%s magic fail\r\n", tag);
        hal_log(b);
        fclose(f);
        return -1;
    }
    if (ver > max_version) {
        snprintf(b, sizeof(b), "%s unsupported version\r\n", tag);
        hal_log(b);
        fclose(f);
        return -1;
    }
    read_sz = (ver < max_version) ? min_size : bufsz;
    if (read_sz > bufsz) read_sz = bufsz;
    memset(p, 0, bufsz);
    rewind(f);
    if (fread(buf, read_sz, 1, f) != 1) {
        snprintf(b, sizeof(b), "%s fread body fail\r\n", tag);
        hal_log(b);
        fclose(f);
        return -1;
    }
    fclose(f);
    memcpy(&saved_cs, p + cs_offset, sizeof(saved_cs));
    memset(p + cs_offset, 0, sizeof(sum));
    sum = save_checksum(buf, read_sz);
    memcpy(p + cs_offset, &saved_cs, sizeof(saved_cs));
    if (sum != saved_cs) {
        snprintf(b, sizeof(b), "%s checksum fail\r\n", tag);
        hal_log(b);
        return -1;
    }
    snprintf(b, sizeof(b), "%s read ok\r\n", tag);
    hal_log(b);
    return 0;
}
