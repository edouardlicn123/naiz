/*
 * naiz_file.h — Shared file I/O helpers.
 *
 * Eliminates the repeated fopen/fseek/ftell/fread pattern across font.c,
 * cjk.c, image.c, and nb.c.
 */
#ifndef NAIZ_FILE_H
#define NAIZ_FILE_H

#include <stddef.h>

/* Read an entire file into a malloc'd buffer.
 * Returns NULL on failure (fopen/malloc/fread error).
 * The caller owns the returned buffer and must free() it.
 * @param path     File path
 * @param out_size If non-NULL, receives the file size on success
 */
void *file_read_all(const char *path, long *out_size);

#endif
