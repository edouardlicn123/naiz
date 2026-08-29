/*
 * Dialog state machine — part of the scene layer subsystem.
 * Extracted from layer.c (refactor): snapshot, restore, hide, lazy snap
 * plus the dialog/button style + palette block.
 * Implements the dialog half of C04-图层渲染与换装机制.md.
 */
#include <stdlib.h>
#include "render.h"
#include "scene_layers.h"
#include "layer_internal.h"
#include "hal.h"

/* Dialog area snapshot: detects corruption from face sprites. */
static unsigned char *dialog_snapshot = NULL;
/* Non-zero when dialog snapshot holds valid data. */
static unsigned char dialog_snapshot_valid = 0;
/* Non-zero when dialog area is currently drawn on screen. */
static unsigned char dialog_drawn = 0;
/* Non-zero when dialog content changed and needs lazy re-snapshot. */
static unsigned char dialog_dirty = 0;

/*
 * Dialog style: 0-9
 * bits: [dither_bit][color_idx<<1]
 *   bit 0 = dither enable (0=solid fill_rect, 1=PAT75 dither)
 *   bits 1-3 = background color index (0=black,1=blue,2=dark red,3=green,4=purple)
 */
static unsigned char g_dialog_style = 0;

/* Shared color schemes: black, blue, dark red, green, purple (5 schemes).
 * Used by both dialog background and button fill. */
static const uint8_t COLOR_SCHEMES[COLOR_SCHEME_COUNT][3] = {
    {0x00, 0x00, 0x00},   /* black   */
    {0x00, 0x00, 0xFF},   /* blue    */
    {0x80, 0x00, 0x00},   /* dark red */
    {0x00, 0x80, 0x00},   /* green   */
    {0x80, 0x00, 0x80},   /* purple  */
};

/* Button color scheme selection (0-4, indexes into COLOR_SCHEMES). */
static unsigned char g_button_style = 0;

/* 8×8 Bayer ordered dither pattern for the semi-transparent dialog
 * background (used when dialog style bit 0 is set).  Private to the
 * layer subsystem — render.c only fills with the caller-supplied pattern. */
static const uint8_t PAT75[8] = { 0xEE, 0x77, 0xBB, 0xDD, 0xEE, 0x77, 0xBB, 0xDD };

/*
 * Update dialog background palette (index 248).
 * Color index = g_dialog_style >> 1; dither bit used in scene_draw_dialog.
 */
void dlg_update_palette(void)
{
    unsigned char ci = g_dialog_style >> 1;
    if (ci >= COLOR_SCHEME_COUNT) ci = 0;
    hal_set_palette(PAL_DIALOG_FILL, COLOR_SCHEMES[ci][0], COLOR_SCHEMES[ci][1], COLOR_SCHEMES[ci][2]);
}

/*
 * Update button palette: fill / highlight / shadow colors.
 *   BTN_FILL_IDX (249) = solid fill color
 *   BTN_HIGHLIGHT_IDX (252) = 75% fill + 25% white
 *   BTN_SHADOW_IDX (253) = 75% fill + 25% black
 */
void btn_update_palette(void)
{
    unsigned char ci = g_button_style;
    int fr, fg, fb;
    if (ci >= COLOR_SCHEME_COUNT) ci = 0;
    fr = COLOR_SCHEMES[ci][0];
    fg = COLOR_SCHEMES[ci][1];
    fb = COLOR_SCHEMES[ci][2];
    hal_set_palette(BTN_FILL_IDX, (uint8_t)fr, (uint8_t)fg, (uint8_t)fb);
    hal_set_palette(BTN_HIGHLIGHT_IDX,
                    (uint8_t)((fr * 3 + 255) / 4),
                    (uint8_t)((fg * 3 + 255) / 4),
                    (uint8_t)((fb * 3 + 255) / 4));
    hal_set_palette(BTN_SHADOW_IDX,
                    (uint8_t)(fr * 3 / 4),
                    (uint8_t)(fg * 3 / 4),
                    (uint8_t)(fb * 3 / 4));
}

/* Set dialog style (0-9) and refresh the dialog palette. */
void dlg_set_style(unsigned char s)
{
    if (s > 9) s = 0;
    g_dialog_style = s;
    dlg_update_palette();
}

/* Return current dialog style (0-9). */
unsigned char dlg_get_style(void)
{
    return g_dialog_style;
}

/* Set button style (0-4) and refresh the button palette. */
void btn_set_style(unsigned char s)
{
    if (s >= COLOR_SCHEME_COUNT) s = 0;
    g_button_style = s;
    btn_update_palette();
}

/* Fill rectangle with dialog background style (solid or dither). */
void fill_dialog_bg(int x, int y, int w, int h)
{
    if (g_dialog_style & 1)
        fill_rect_pattern(x, y, w, h, PAT75, PAL_DIALOG_FILL);
    else
        fill_rect(x, y, w, h, PAL_DIALOG_FILL);
}

/*
 * Draw dialog background to VRAM.
 * Draws white (index 7) border.
 */
static void scene_draw_dialog(void)
{
    fill_dialog_bg(LAYER_DIALOG_X, LAYER_DIALOG_Y, LAYER_DIALOG_W, LAYER_DIALOG_H);
    draw_rect(LAYER_DIALOG_X, LAYER_DIALOG_Y, LAYER_DIALOG_W, LAYER_DIALOG_H, LAYER_DIALOG_BORDER, PAL_WHITE);
}

/* Forward declaration */
static void dialog_snapshot_capture(void);

/* Open and draw the VN dialog box.
 * 1. Draws the dialog frame via scene_draw_dialog()
 * 2. Captures dialog pixels into dialog_snapshot for corruption detection
 * Sets dialog_drawn = 1. */
void layer_dialog_open(void)
{
    hal_mouse_invalidate_cursor();
    scene_draw_dialog();
    if (!dialog_snapshot) {
        dialog_snapshot = (unsigned char *)malloc(LAYER_DIALOG_W * LAYER_DIALOG_H);
    }
    if (dialog_snapshot) {
        dialog_snapshot_capture();
        dialog_drawn = 1;
        layer_set_active(LAYER_Z_DIALOG, 1);
        layer_set_active(LAYER_Z_TEXT, 1);
    } else {
        dialog_drawn = 0;
    }
    dialog_dirty = 0;
}

/* Redraw dialog content (text, name, etc.) without re-snapshotting.
 * Called after sprite changes that may overlap the dialog area. */
void layer_dialog_refresh(void)
{
    scene_draw_dialog();
}

/* Capture the dialog area from VRAM into dialog_snapshot and mark valid. */
static void dialog_snapshot_capture(void)
{
    vram_read(LAYER_DIALOG_X, LAYER_DIALOG_Y, LAYER_DIALOG_W, LAYER_DIALOG_H, dialog_snapshot);
    dialog_snapshot_valid = 1;
}

/* Restore dialog from snapshot (used after bg_restore clears the area). */
void layer_dialog_restore(void)
{
    if (!dialog_snapshot_valid) return;
    if (dialog_snapshot) {
        vram_write(dialog_snapshot, LAYER_DIALOG_X, LAYER_DIALOG_Y, LAYER_DIALOG_W, LAYER_DIALOG_H);
    }
}

/* Lazy dialog snapshot: when dialog_dirty, re-captures dialog pixels.
 * Sequence: restore bg under dialog -> redraw sprites -> redraw dialog -> snapshot.
 * Keeps the dialog snapshot synchronized after sprite changes. */
void layer_dialog_snap(void)
{
    if (!dialog_dirty) return;
    hal_mouse_invalidate_cursor();
    layer_bg_restore_rect(LAYER_DIALOG_X, LAYER_DIALOG_Y, LAYER_DIALOG_W, LAYER_DIALOG_H, 0);
    layer_redraw_sprites();
    layer_dialog_refresh();
    if (dialog_snapshot) {
        vram_read(LAYER_DIALOG_X, LAYER_DIALOG_Y,
                  LAYER_DIALOG_W, LAYER_DIALOG_H, dialog_snapshot);
    }
    dialog_dirty = 0;
}

/* Hide the dialog: restore the background behind it and clear flags.
 * Uses bg_dialog_snapshot (pure background without dialog). */
void layer_dialog_hide(void)
{
    const unsigned char *bg_snap;
    hal_mouse_invalidate_cursor();
    bg_snap = layer_bg_dialog_snapshot();
    if (bg_snap) {
        vram_write(bg_snap, LAYER_DIALOG_X, LAYER_DIALOG_Y,
                   LAYER_DIALOG_W, LAYER_DIALOG_H);
    }
    dialog_snapshot_valid = 0;
    dialog_drawn = 0;
    dialog_dirty = 0;
    layer_set_active(LAYER_Z_DIALOG, 0);
    layer_set_active(LAYER_Z_TEXT, 0);
}

/* Return whether the dialog is currently drawn on screen. */
int layer_dialog_drawn(void)
{
    return dialog_drawn;
}

/* Mark the dialog content as needing a lazy re-snapshot. */
void layer_dialog_mark_dirty(void)
{
    dialog_dirty = 1;
}

/* Clear dialog flags only (used by layer_capture_bg). */
void layer_dialog_clear(void)
{
    dialog_drawn = 0;
    dialog_dirty = 0;
}

/* Full reset: free the dialog snapshot and clear all dialog state. */
void layer_dialog_reset(void)
{
    if (dialog_snapshot) { free(dialog_snapshot); dialog_snapshot = NULL; }
    dialog_snapshot_valid = 0;
    dialog_drawn = 0;
    dialog_dirty = 0;
}

/* Current dialog-area pixels (480x115). NULL when not captured. */
const unsigned char *layer_dialog_snapshot(void)
{
    return dialog_snapshot;
}

/*==== Unified entry point ================================================*/

/* Unified dialog show: auto-selects open/snap + restore based on state. */
void layer_dialog_show(void)
{
    if (!layer_dialog_drawn())
        layer_dialog_open();
    else
        layer_dialog_snap();
    layer_dialog_restore();
}

/* Unified dialog hide: hide dialog + redraw sprites that may be overlapped. */
void layer_dialog_hide_clean(void)
{
    if (!layer_dialog_drawn())
        return;
    layer_dialog_hide();
    layer_redraw_sprites();
}
