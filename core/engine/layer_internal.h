/*
 * layer_internal.h — Cross-file interfaces for the scene layer subsystem.
 *
 * layer.c (lifecycle) / layer_bg.c (background snapshots) /
 * layer_dialog.c (dialog state machine + style) / layer_sprite.c are one
 * logical subsystem split into four files. This header exposes the
 * internal glue between them; the public scene_layers.h API remains the
 * external contract.
 */
#ifndef LAYER_INTERNAL_H
#define LAYER_INTERNAL_H

#include <stdlib.h>
#include "hal.h"

/* Allocate a dialog-area buffer (LAYER_DIALOG_W x LAYER_DIALOG_H).
 * Shared by layer_bg.c (under_dialog snapshot) and layer_dialog.c
 * (dialog_layer composite) so the malloc size and OOM log stay in one
 * place.  Returns NULL on OOM (after logging via tag). */
static inline unsigned char *layer_snapshot_alloc_dialog(const char *tag)
{
    unsigned char *buf = (unsigned char *)malloc(LAYER_DIALOG_W * LAYER_DIALOG_H);
    if (!buf) hal_logf("OOM: %s malloc fail\r\n", tag);
    return buf;
}

/*=== Background (implemented in layer_bg.c) ===============================*/

/* Free both background snapshots and clear the valid flag.
 * Called from layer.c layer_init on scene transitions and engine startup. */
void layer_bg_reset(void);

/* Restore a rectangular region from the background snapshot to VRAM.
 * When clip_dialog is nonzero and the dialog is drawn, pixels within the
 * dialog area are skipped (face sprites must not overwrite the dialog). */
void layer_bg_restore_rect(int x, int y, int w, int h, int clip_dialog);

/* Non-zero when the background snapshot holds valid data. */
int layer_bg_snapshot_valid(void);

/* Full-screen background snapshot (640x400). NULL when not captured. */
const unsigned char *layer_bg_snapshot(void);

/* Pristine underneath dialog rect (480x115, source pixels, no dialog
 * overlay). NULL when not captured. */
const unsigned char *layer_bg_under_dialog(void);

/* Capture dialog-area underneath background from a MagImage pixel buffer
 * directly (RAM-to-RAM copy, no VRAM readback).  src_x/src_y = blit origin. */
void layer_capture_bg_dialog_from_image(const uint8_t *pixels, int img_w, int img_h,
                                        int src_x, int src_y);

/*=== Sprite (implemented in layer_sprite.c) ================================*/

/* Reset the dialog occluder to the pristine underneath, redraw all active
 * sprites into it, then recompose the dialog.  Called after every sprite
 * change (show/replace/redraw/hide) while the dialog is open, so the dialog
 * dither holes keep the fresh actor pixels (pseudo-transparency). */
void layer_sprite_sync_dialog_base(void);

/*=== Dialog (implemented in layer_dialog.c) ================================*/

/* Re-seed the dialog composite base from the fresh underneath, re-paint the
 * box and blit.  Called from layer_bg_change after the background changed
 * while a dialog is open (survival): the box persists, content follows the
 * next text command. */
void layer_dialog_recompose(void);

/* Live dialog-area base (480x115): pristine underneath + the sprites that
 * overlap the dialog rect — the seed source for the dialog composite, so
 * dither holes keep the actors visible (pseudo-transparency).  NULL when
 * not allocated (dialog never opened). */
uint8_t *layer_dialog_occluder(void);

/* Re-base the occluder to the pristine underneath, dropping any stored
 * sprite pixels.  Called when the background changes (layer_bg_change)
 * before the sprite layer is redrawn into it. */
void dialog_occluder_reset_base(void);

/* Full reset: free the dialog composite buffer and clear all dialog state.
 * Called from layer_init on scene transitions and engine startup. */
void layer_dialog_reset(void);

/* Current dialog composite pixels (480x115). NULL when not allocated.
 * Used by sprite face NAIZ_DEBUG corruption checks. */
const unsigned char *layer_dialog_snapshot(void);

#endif
