/*
 * IMAGE.DAT loader — MMAP-style archive for MAG images.
 *
 * Format:
 *   uint32   count
 *   N x { char name[12], uint32 offset, uint32 size }
 *   raw MAG data concatenated
 *
 * Palette invariant (verified at init):
 *   All images share the same 256-color palette.
 *   Index 7 and 15 are always white (engine reserve for text/transparency).
 */
#ifndef IMAGE_H
#define IMAGE_H

#include "mag.h"

/* 加载 IMAGE.DAT 归档，成功返回 0 */
int       image_init(const char *path);
/* 按 ID 加载图片，返回引用计数 +1 的 MagImage（调用者负责 mag_release） */
MagImage *image_load(unsigned short id);
/* Fetch raw archive bytes of entry id without decoding (e.g. .ANI
 * containers). Pointer is valid until next image_init/image_close;
 * *out_size (optional) receives byte length. NULL on bad id/TOC. */
const unsigned char *image_raw_blob(unsigned short id, long *out_size);

#endif
