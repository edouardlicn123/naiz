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

/* Handle a debug dump command string (e.g. "bg", "all", "status").
 * Called from keyboard shortcut or future serial command handler. */
void layer_debug_handle(const char *arg);

#endif
