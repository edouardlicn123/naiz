/*
 * Background snapshots — captured from the source image (never VRAM
 * readback) so the pristine background can be restored on sprite hide and
 * dialog close.  Extracted from layer.c (refactor): full-screen + dialog
 * underneath captures.  Internal glue (layer_bg_*) is exposed via
 * layer_internal.h; the public capture API lives in scene_layers.h.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "render.h"
#include "scene_layers.h"
#include "layer_internal.h"
#include "hal.h"

/* Background snapshot (640x400): pristine source image, captured from the
 * blitted MagImage pixels — never VRAM — so it cannot be contaminated by
 * sprites (devdoc 96 fixes the legacy capture-after-redraw order bug). */
static unsigned char *bg_snapshot = NULL;
/* Non-zero when bg_snapshot holds valid data. */
static unsigned char  snapshot_valid = 0;
/* Background behind the dialog rect (480x115), pure source pixels (bg image
 * or animation frame).  Renamed from bg_dialog_snapshot to under_dialog: the
 * dialog composite seeds its dither holes from here and dialog close
 * restores it over the rect. */
static unsigned char *under_dialog = NULL;

/*=== Helpers =============================================================*/

/* Restore a rectangular region from bg_snapshot to VRAM.
 * When clip_dialog is nonzero and dialog is drawn, pixels within the dialog
 * area are skipped — erasing a sprite (or restoring under a replaced sprite)
 * must not overwrite the dialog composite, which sits above the sprites
 * (R20 z-order: dialog box over full-body sprites). */
void layer_bg_restore_rect(int x, int y, int w, int h, int clip_dialog)
{
    int py, px, addr;
    int ry, rx;
    unsigned char c;

    if (!snapshot_valid || !bg_snapshot) return;

    for (py = 0; py < h; py++) {
        ry = y + py;
        if (ry < 0 || ry >= LAYER_SCREEN_H) continue;
        for (px = 0; px < w; px++) {
            rx = x + px;
            if (rx < 0 || rx >= LAYER_SCREEN_W) continue;

            if (clip_dialog && layer_dialog_drawn()) {
                if (rx >= LAYER_DIALOG_X && rx < LAYER_DIALOG_X + LAYER_DIALOG_W &&
                    ry >= LAYER_DIALOG_Y && ry < LAYER_DIALOG_Y + LAYER_DIALOG_H)
                    continue;
            }

            c = bg_snapshot[ry * LAYER_SCREEN_W + rx];
            addr = ry * LAYER_SCREEN_W + rx;
            vram_pset_addr(addr, c);
        }
    }
}

/*=== Background ==========================================================*/

/* Capture the full-screen background from a MagImage pixel buffer directly
 * (RAM-to-RAM copy, no VRAM readback).  The image is opaque and covers the
 * screen, leaving bg_snapshot pristine by construction.  Out-of-bounds rows
 * (image smaller than the screen) are zeroed so no stale pixels survive. */
static void layer_capture_bg_from_image(const uint8_t *pixels, int img_w, int img_h)
{
    int y, row_w;

    if (!pixels || !img_w || !img_h) return;
    if (!bg_snapshot) {
        bg_snapshot = (unsigned char *)malloc(LAYER_SCREEN_W * LAYER_SCREEN_H);
        if (!bg_snapshot) {
            hal_log("OOM: bg_snapshot malloc fail\r\n");
            return;
        }
    }
    memset(bg_snapshot, 0, (size_t)LAYER_SCREEN_W * LAYER_SCREEN_H);
    for (y = 0; y < LAYER_SCREEN_H && y < img_h; y++) {
        row_w = img_w < LAYER_SCREEN_W ? img_w : LAYER_SCREEN_W;
        memcpy(bg_snapshot + y * LAYER_SCREEN_W, pixels + y * img_w, (size_t)row_w);
    }
    snapshot_valid = 1;
    layer_set_active(LAYER_Z_BG, 1);
}

/* Capture the dialog-area underneath background directly from a MagImage
 * pixel buffer (RAM-to-RAM copy, no VRAM readback).  Used on background
 * change and during animation playback: the image is already in RAM, so this
 * avoids a 55KB VRAM readback per capture.  src_x/src_y = blit origin. */
void layer_capture_bg_dialog_from_image(const uint8_t *pixels, int img_w, int img_h,
                                        int src_x, int src_y)
{
    int dy, src_row;
    int row_start, copy_len;

    if (!pixels || !img_w || !img_h) return;
    if (!under_dialog) {
        under_dialog = layer_snapshot_alloc_dialog("under_dialog");
        if (!under_dialog) {
            return;
        }
    }
    /* Zero first so rows the image does not cover (cine 640x280 case) keep
     * no stale pixels; guarded rows are skipped below. */
    memset(under_dialog, 0, (size_t)LAYER_DIALOG_W * LAYER_DIALOG_H);
    row_start = src_x + LAYER_DIALOG_X;
    if (row_start >= img_w) return;
    copy_len = LAYER_DIALOG_W;
    if (row_start + copy_len > img_w) copy_len = img_w - row_start;
    if (copy_len <= 0) return;
    for (dy = 0; dy < LAYER_DIALOG_H; dy++) {
        /* Image row index the blit maps onto screen row (src_y+img_row). */
        src_row = LAYER_DIALOG_Y + dy;
        if (src_row - src_y < 0 || src_row - src_y >= img_h) continue;
        /* Row-clamped copy (copy_len <= remaining image columns), so the
         * memcpy never reads across into the next image row (C9/C28). */
        memcpy(under_dialog + dy * LAYER_DIALOG_W,
               pixels + (src_row - src_y) * img_w + row_start,
               (size_t)copy_len);
    }
}

/* Free both snapshots and clear the valid flag.
 * Called from layer.c layer_init on scene transitions and engine startup. */
void layer_bg_reset(void)
{
    if (bg_snapshot) { free(bg_snapshot); bg_snapshot = NULL; }
    if (under_dialog) { free(under_dialog); under_dialog = NULL; }
    snapshot_valid = 0;
    layer_set_active(LAYER_Z_BG, 0);
}

/*=== Background accessors (layer_internal.h) =============================*/

/* Non-zero when the background snapshot holds valid data. */
int layer_bg_snapshot_valid(void)
{
    return snapshot_valid;
}

/* Full-screen pristine background snapshot (640x400). NULL when not captured. */
const unsigned char *layer_bg_snapshot(void)
{
    return bg_snapshot;
}

/* Pristine underneath dialog rect (480x115, source pixels). NULL when not
 * captured.  Sprite restore must not touch this (Option X). */
const unsigned char *layer_bg_under_dialog(void)
{
    return under_dialog;
}

/*==== Unified entry point ================================================*/

/* Unified background change (devdoc 96 phase C, R20): blit -> capture both
 * snapshots from the source image (no VRAM readback anywhere) -> redraw
 * sprites at full body.  layer_redraw_sprites ends with
 * layer_sprite_sync_dialog_base(), which re-bases the live occluder to the
 * fresh underneath, redraws the sprites into it, and recomposes the dialog
 * over it when open (pseudo-transparency survival). */
void layer_bg_change(MagImage *img)
{
    if (!img) return;
    vram_blit(img, 0, 0);
    layer_capture_bg_from_image(img->pixels, img->width, img->height);
    layer_capture_bg_dialog_from_image(img->pixels, img->width, img->height, 0, 0);
    layer_redraw_sprites();
    dlg_update_palette();
    btn_update_palette();
}
