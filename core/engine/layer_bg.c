/*
 * Background snapshots — captured before sprites/dialog are drawn so the
 * pristine background can be restored on sprite hide / dialog restore.
 * Extracted from layer.c (refactor): full-screen + dialog-area captures.
 * Internal glue (layer_bg_*) is exposed via layer_internal.h; the public
 * capture API lives in scene_layers.h.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "render.h"
#include "scene_layers.h"
#include "layer_internal.h"
#include "hal.h"

/* Background snapshot: full-screen VRAM copy before sprites drawn. */
static unsigned char *bg_snapshot = NULL;
/* Non-zero when bg_snapshot holds valid data. */
static unsigned char  snapshot_valid = 0;
/* Background behind dialog area (captured before first sprite show). */
static unsigned char *bg_dialog_snapshot = NULL;

/*=== Helpers =============================================================*/

/* Restore a rectangular region from bg_snapshot to VRAM.
 * When clip_dialog is nonzero and dialog is drawn, pixels within the dialog
 * area are skipped (used by face sprites to avoid overwriting the dialog). */
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

/* Capture the full VRAM screen into bg_snapshot.
 * Called after loading a new background image (e.g. cmd_bg).
 * Resets dialog_drawn/dialog_dirty; dialog reopens on next text. */
void layer_capture_bg(void)
{
    if (!bg_snapshot) {
        bg_snapshot = (unsigned char *)malloc(LAYER_SCREEN_W * LAYER_SCREEN_H);
        if (!bg_snapshot)
            hal_log("OOM: bg_snapshot malloc fail\r\n");
    }
    if (bg_snapshot) {
        vram_read(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, bg_snapshot);
        snapshot_valid = 1;
        layer_set_active(LAYER_Z_BG, 1);
    }
    layer_dialog_clear();
}

/* Reconstruct bg_dialog_snapshot from bg_snapshot (pure background,
 * no dialog overlay). Used when the last sprite is removed after
 * dialog_refresh has drawn the overlay on VRAM. */
void layer_capture_bg_dialog_from_bg(void)
{
    int y;
    if (!bg_snapshot || !snapshot_valid) {
        layer_capture_bg_dialog();
        return;
    }
    if (!bg_dialog_snapshot) {
        bg_dialog_snapshot = (unsigned char *)malloc(LAYER_DIALOG_W * LAYER_DIALOG_H);
        if (!bg_dialog_snapshot) {
            hal_log("OOM: bg_dialog_snapshot malloc fail\r\n");
            return;
        }
    }
    for (y = 0; y < LAYER_DIALOG_H; y++)
        memcpy(bg_dialog_snapshot + y * LAYER_DIALOG_W,
               bg_snapshot + (LAYER_DIALOG_Y + y) * LAYER_SCREEN_W + LAYER_DIALOG_X,
               LAYER_DIALOG_W);
}

/* Capture only the dialog-area background from VRAM.
 * Used when the last sprite is removed to restore the pristine dialog background. */
void layer_capture_bg_dialog(void)
{
    if (!bg_dialog_snapshot) {
        bg_dialog_snapshot = (unsigned char *)malloc(LAYER_DIALOG_W * LAYER_DIALOG_H);
        if (!bg_dialog_snapshot)
            hal_log("OOM: bg_dialog_snapshot malloc fail\r\n");
    }
    if (bg_dialog_snapshot) {
        vram_read(LAYER_DIALOG_X, LAYER_DIALOG_Y, LAYER_DIALOG_W, LAYER_DIALOG_H, bg_dialog_snapshot);
    }
}

/* Capture dialog-area background directly from a MagImage pixel buffer
 * instead of reading back from VRAM.  Used during animation playback:
 * the image is already in RAM (just decoded), so this avoids a 55KB
 * VRAM readback per frame.  src_x/src_y is the blit origin on screen. */
void layer_capture_bg_dialog_from_image(const uint8_t *pixels, int img_w,
                                        int src_x, int src_y)
{
    int dy, src_row;

    if (!bg_dialog_snapshot) {
        bg_dialog_snapshot = (unsigned char *)malloc(LAYER_DIALOG_W * LAYER_DIALOG_H);
        if (!bg_dialog_snapshot) {
            hal_log("OOM: bg_dialog_snapshot malloc fail\r\n");
            return;
        }
    }
    for (dy = 0; dy < LAYER_DIALOG_H; dy++) {
        src_row = src_y + LAYER_DIALOG_Y + dy;
        if (src_row < 0 || src_row >= LAYER_SCREEN_H) continue;
        memcpy(bg_dialog_snapshot + dy * LAYER_DIALOG_W,
               pixels + src_row * img_w + src_x + LAYER_DIALOG_X,
               LAYER_DIALOG_W);
    }
}

/* Free both snapshots and clear the valid flag.
 * Called from layer.c layer_init on scene transitions and engine startup. */
void layer_bg_reset(void)
{
    if (bg_snapshot) { free(bg_snapshot); bg_snapshot = NULL; }
    if (bg_dialog_snapshot) { free(bg_dialog_snapshot); bg_dialog_snapshot = NULL; }
    snapshot_valid = 0;
    layer_set_active(LAYER_Z_BG, 0);
}

/*=== Background accessors (layer_internal.h) =============================*/

/* Non-zero when the background snapshot holds valid data. */
int layer_bg_snapshot_valid(void)
{
    return snapshot_valid;
}

/* Full-screen background snapshot (640x400). NULL when not captured. */
const unsigned char *layer_bg_snapshot(void)
{
    return bg_snapshot;
}

/* Pristine dialog-area background (480x115, no dialog overlay). */
const unsigned char *layer_bg_dialog_snapshot(void)
{
    return bg_dialog_snapshot;
}

/*==== Unified entry point ================================================*/

/* Unified background change: blit + conditional capture + redraw + palette + snapshot.
 * Encapsulates the 7-step ritual previously inlined in cmd_bg(). */
void layer_bg_change(MagImage *img)
{
    if (!img) return;
    vram_blit(img, 0, 0);
    if (!layer_dialog_drawn())
        layer_capture_bg_dialog();
    layer_redraw_sprites();
    dlg_update_palette();
    btn_update_palette();
    layer_capture_bg();
}
