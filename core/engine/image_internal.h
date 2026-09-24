/*
 * image_internal.h — Cross-file interfaces for the image archive subsystem.
 *
 * image.c (archive TOC + decode + palette) / image_cache.c (LRU cache)
 * are one logical subsystem split into two files.  This header exposes the
 * internal glue between them; the public image.h API remains the contract.
 */
#ifndef IMAGE_INTERNAL_H
#define IMAGE_INTERNAL_H

#include "mag.h"

/*=== Cache (implemented in image_cache.c) =================================*/

/* Initialize the LRU cache slots to empty.  Called on archive load. */
void image_cache_init(void);

/* Free all cached images and reset the cache slots. */
void image_cache_clear(void);

/* Look up a decoded image by id.  On hit returns a mag_retain'd shared
 * pointer (caller must mag_release), NULL on miss. */
MagImage *image_cache_lookup(int id);

/* Insert a decoded image into the cache.  The cache takes ownership of img
 * (no deep copy); caller must NOT mag_release on img afterwards.  Evicts the
 * least-recently-used slot when the cache is full. */
void image_cache_insert(int id, MagImage *img);

#endif
