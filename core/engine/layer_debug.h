/*
 * layer_debug.h — Visual debugging: per-layer PPM export + composite preview.
 *
 * Provides dump:bg / dump:sprite / dump:dialog / dump:anim / dump:all /
 * dump:status commands for diagnosing layer composition issues.
 * All exports write PPM files to the current directory (DOS CWD).
 */
#ifndef LAYER_DEBUG_H
#define LAYER_DEBUG_H

#include "scene_layers.h"

/* Export a single layer's content as a PPM image.
 * z_order: LAYER_Z_BG / LAYER_Z_SPRITE / LAYER_Z_ANIM / LAYER_Z_DIALOG
 * filename: output filename (without path prefix)
 * Returns: 0=success, -1=failure */
int layer_dump(int z_order, const char *filename);

/* Export the composited result (all layers blended in Z-order).
 * Returns: 0=success, -1=failure */
int layer_dump_composite(const char *filename);

/* Export all layers (per-layer + composite).
 * prefix: filename prefix (e.g. "layer")
 * Returns: number of files exported */
int layer_dump_all(const char *prefix);

/* Handle a debug dump command string (e.g. "bg", "all", "status").
 * Called from keyboard shortcut or future serial command handler. */
void layer_debug_handle(const char *arg);

#endif
