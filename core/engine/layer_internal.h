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

/* Pristine dialog-area background (480x115, no dialog overlay). NULL when
 * not captured. */
const unsigned char *layer_bg_dialog_snapshot(void);

/* Capture dialog-area background from a MagImage pixel buffer directly
 * (RAM-to-RAM copy, no VRAM readback).  src_x/src_y = blit origin. */
void layer_capture_bg_dialog_from_image(const uint8_t *pixels, int img_w,
                                        int src_x, int src_y);

/*=== Sprite (implemented in layer_sprite.c) ================================*/

/* Return 1 if at least one sprite is active in the table. */
int layer_has_any_sprite(void);

/*=== Dialog (implemented in layer_dialog.c) ================================*/

/* Redraw dialog content (text, name, etc.) without re-snapshotting.
 * Called after sprite changes that may overlap the dialog area. */
void layer_dialog_refresh(void);

/* Mark the dialog content as needing a lazy re-snapshot. */
void layer_dialog_mark_dirty(void);

/* Clear dialog flags only (used by layer_capture_bg: the background changed,
 * so the dialog reopens on next text). Does not free the snapshot. */
void layer_dialog_clear(void);

/* Full reset: free the dialog snapshot and clear all dialog state.
 * Called from layer_init on scene transitions and engine startup. */
void layer_dialog_reset(void);

/* Current dialog-area pixels (480x115). NULL when not captured.
 * Used by sprite face NAIZ_DEBUG corruption checks. */
const unsigned char *layer_dialog_snapshot(void);

#endif
