/*
 * Dialog state machine — part of the scene layer subsystem.
 * Extracted from layer.c (refactor): snapshot, restore, hide, lazy snap
 * plus the dialog/button style + palette block.
 * Implements the dialog half of C04-图层渲染与换装机制.md.
 */
#include <stdlib.h>
#include <string.h>
#include "render.h"
#include "scene_layers.h"
#include "layer_internal.h"
#include "hal.h"

/* Dialog composite buffer (480 x LAYER_DIALOG_H): box + current page text,
 * opaque.  The underneath pixels are seeded at open so dither holes stay
 * optically transparent (the animation/blit clip paths keep the dialog rect
 * untouched, so a static base is pixel-faithful).  The box is re-painted per
 * page to erase the previous page's text (paging shows one page at a time,
 * matching the legacy VRAM semantics). */
static unsigned char *dialog_layer = NULL;
/* Non-zero when dialog area is currently drawn on screen. */
static unsigned char dialog_drawn = 0;

/* Live dialog-area base (480x115): pristine underneath + the sprites that
 * overlap the dialog rect.  The dialog composite seeds its dither holes from
 * here so the actors stay visible under the box (pseudo-transparency, R20
 * revokes the Option X sprite clipping).  Maintained by layer_sprite.c via
 * layer_sprite_sync_dialog_base(); reset to the pristine underneath after a
 * background change via dialog_occluder_reset_base(). Lives as long as
 * dialog_layer. */
static unsigned char *dialog_occluder = NULL;

/* Render projection of the current page (dialog layer's own copy of the
 * last dialog_show's text parameters, ~1KB static — no heap, no OOM).
 * layer_dialog_recompose redraws the current page from this projection on
 * the fresh underneath after a background change, so the dialog (box + text)
 * survives bg(){x}/cg(){x} (devdoc 96 ruling A, R19). */
static char dialog_render_name[64];
static char dialog_render_text[1024];
static int  dialog_render_off = 0;
static unsigned char dialog_render_valid = 0;

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
 * Compose the dialog box into a 480x115 buffer (buf != NULL, stride = row
 * stride) or directly to VRAM (buf == NULL).  The caller pre-seeds the
 * buffer with the underneath pixels so dither holes keep the background;
 * VRAM mode matches the legacy scene_draw_dialog pixel-for-pixel. */
static void dialog_paint_box(uint8_t *buf, int stride)
{
    int y, x;
    if (!buf) {
        fill_dialog_bg(LAYER_DIALOG_X, LAYER_DIALOG_Y, LAYER_DIALOG_W, LAYER_DIALOG_H);
        draw_rect(LAYER_DIALOG_X, LAYER_DIALOG_Y, LAYER_DIALOG_W, LAYER_DIALOG_H,
                  LAYER_DIALOG_BORDER, PAL_WHITE);
        return;
    }
    for (y = 0; y < LAYER_DIALOG_H; y++) {
        uint8_t rowmask = 0xFF;
        if (g_dialog_style & 1)
            rowmask = PAT75[(LAYER_DIALOG_Y + y) & 7];
        for (x = 0; x < LAYER_DIALOG_W; x++) {
            int on_border = (y < LAYER_DIALOG_BORDER ||
                             y >= LAYER_DIALOG_H - LAYER_DIALOG_BORDER ||
                             x < LAYER_DIALOG_BORDER ||
                             x >= LAYER_DIALOG_W - LAYER_DIALOG_BORDER);
            if (on_border) {
                buf[y * stride + x] = PAL_WHITE;
            } else if (rowmask & (0x80 >> (x & 7))) {
                buf[y * stride + x] = PAL_DIALOG_FILL;
            }
            /* dither hole: keep the pre-seeded underneath pixel */
        }
    }
}

/* Re-base the live occluder to the pristine underneath (drops any stored
 * sprite pixels).  Skipped when the occluder is not allocated. */
void dialog_occluder_reset_base(void)
{
    const unsigned char *under;
    if (!dialog_occluder) return;
    under = layer_bg_under_dialog();
    if (under)
        memcpy(dialog_occluder, under, LAYER_DIALOG_W * LAYER_DIALOG_H);
    else
        memset(dialog_occluder, 0, LAYER_DIALOG_W * LAYER_DIALOG_H);
}

/* Seed the composite buffer with the live occluder (underneath + sprites) so
 * dither holes show the actors through the box (pseudo-transparency).
 * Degrades to the pristine underneath, then to black, when the occluder is
 * unavailable (never allocated / OOM). */
static void dialog_seed_base(void)
{
    if (dialog_occluder) {
        memcpy(dialog_layer, dialog_occluder, LAYER_DIALOG_W * LAYER_DIALOG_H);
        return;
    }
    {
        const unsigned char *under = layer_bg_under_dialog();
        if (under)
            memcpy(dialog_layer, under, LAYER_DIALOG_W * LAYER_DIALOG_H);
        else
            memset(dialog_layer, 0, LAYER_DIALOG_W * LAYER_DIALOG_H);
    }
}

/* Live dialog-area base (underneath + sprites). NULL when not allocated. */
uint8_t *layer_dialog_occluder(void)
{
    return dialog_occluder;
}

/* Blit the dialog composite buffer (box + current page text) to VRAM. */
void dialog_layer_blit(void)
{
    if (dialog_layer) {
        vram_write(dialog_layer, LAYER_DIALOG_X, LAYER_DIALOG_Y,
                   LAYER_DIALOG_W, LAYER_DIALOG_H);
    }
}

/* Unified dialog show: ensure the composite buffer holds the box, then let
 * the caller render the current page into it (layer_dialog_render_page) and
 * blit (dialog_layer_blit).  The box is re-painted per page so a fresh text
 * page starts from the clean box (one page at a time, legacy paging
 * semantics). */
void layer_dialog_show(void)
{
    if (!dialog_layer) {
        dialog_layer = layer_snapshot_alloc_dialog("dialog_layer");
        dialog_occluder = layer_snapshot_alloc_dialog("dialog_occluder");
    }
    if (!dialog_layer) {
        /* OOM degraded path: paint the box straight to VRAM (legacy). */
        dialog_paint_box(NULL, 0);
        return;
    }
    if (!dialog_drawn) {
        dialog_drawn = 1;
        layer_set_active(LAYER_Z_DIALOG, 1);
        layer_set_active(LAYER_Z_TEXT, 1);
        /* Populate the live base (pristine underneath + sprites already on
         * screen) so the box seeds over the actors (pseudo-transparency). */
        layer_sprite_sync_dialog_base();
    }
    dialog_paint_box(dialog_layer, LAYER_DIALOG_W);
}

/* Render one dialog page into the composite buffer: seed the underneath,
 * paint the box (erasing the previous page), then route the charname and
 * body text into the buffer via text_set_target.  Returns the body
 * draw_text() continuation offset (draw_text paging contract) or -1 when
 * fully displayed; recompose ignores the return value.  Does not blit. */
int layer_dialog_render_page(const char *name, const char *text, int off)
{
    int w = LAYER_DIALOG_W - LAYER_DIALOG_INDENT - LAYER_DIALOG_RIGHT_INDENT;
    int next;

    if (!dialog_layer) {
        /* OOM degraded path: no composite buffer — text writes straight to
         * VRAM (legacy), the box was already painted by layer_dialog_show. */
        if (name && name[0])
            draw_text(name, 0,
                      LAYER_DIALOG_X + LAYER_DIALOG_INDENT, LAYER_DIALOG_Y + LAYER_DIALOG_HEADER_Y,
                      w, LAYER_DIALOG_BOTTOM, 1, PAL_WHITE);
        return draw_text(text ? text : "", off,
                         LAYER_DIALOG_X + LAYER_DIALOG_INDENT, LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y,
                         w, LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y + 60, 0, PAL_WHITE);
    }
    dialog_seed_base();
    dialog_paint_box(dialog_layer, LAYER_DIALOG_W);
    text_set_target(dialog_layer, LAYER_DIALOG_W, LAYER_DIALOG_H, LAYER_DIALOG_W,
                    LAYER_DIALOG_X, LAYER_DIALOG_Y);
    if (name && name[0])
        draw_text(name, 0,
                  LAYER_DIALOG_X + LAYER_DIALOG_INDENT, LAYER_DIALOG_Y + LAYER_DIALOG_HEADER_Y,
                  w, LAYER_DIALOG_BOTTOM, 1, PAL_WHITE);
    next = draw_text(text ? text : "", off,
                     LAYER_DIALOG_X + LAYER_DIALOG_INDENT, LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y,
                     w, LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y + 60, 0, PAL_WHITE);
    text_set_target_vram();
    return next;
}

/* Store a copy of the current page render parameters in the dialog layer
 * (render projection).  Called by the NB layer at the end of dialog_show so
 * a later recompose can redraw the page on a fresh underneath. */
void dialog_layer_store_render(const char *name, const char *text, int off)
{
    if (name) {
        strncpy(dialog_render_name, name, sizeof(dialog_render_name) - 1);
        dialog_render_name[sizeof(dialog_render_name) - 1] = '\0';
    } else {
        dialog_render_name[0] = '\0';
    }
    if (text) {
        strncpy(dialog_render_text, text, sizeof(dialog_render_text) - 1);
        dialog_render_text[sizeof(dialog_render_text) - 1] = '\0';
    } else {
        dialog_render_text[0] = '\0';
    }
    dialog_render_off = off;
    dialog_render_valid = 1;
}

/* Restore the dialog composite to VRAM (covers a menu overlay under it). */
void layer_dialog_restore(void)
{
    dialog_layer_blit();
}

/* Hide the dialog: restore the pristine underneath pixels over the rect,
 * clear the flags, then redraw the sprite layer at full body (the dialog no
 * longer masks y >= 280, so sprites may extend below the dialog boundary —
 * Option X close semantics). */
void layer_dialog_hide(void)
{
    const unsigned char *under;
    hal_mouse_invalidate_cursor();
    if (!dialog_drawn) {
        /* No dialog on screen: VRAM already shows the pure background — the
         * restore write would be redundant and could clobber sprite pixels. */
        layer_set_active(LAYER_Z_DIALOG, 0);
        layer_set_active(LAYER_Z_TEXT, 0);
        return;
    }
    under = layer_bg_under_dialog();
    if (under) {
        vram_write(under, LAYER_DIALOG_X, LAYER_DIALOG_Y,
                   LAYER_DIALOG_W, LAYER_DIALOG_H);
    }
    dialog_drawn = 0;
    layer_set_active(LAYER_Z_DIALOG, 0);
    layer_set_active(LAYER_Z_TEXT, 0);
    /* Full-body redraw now that the dialog rect is no longer masked. */
    layer_redraw_sprites();
}

/* Return whether the dialog is currently drawn on screen. */
int layer_dialog_drawn(void)
{
    return dialog_drawn;
}

/* Re-seed the composite base from the fresh underneath, re-paint the box and
 * the current page text, then blit.  Called from layer_bg_change after the
 * background changed while a dialog is open: the dialog (box + current page
 * text) persists over the fresh underneath (survival, ruling A).  Without a
 * render projection the text would be lost, so recompose redraws the page
 * from dialog_render_* when available. */
void layer_dialog_recompose(void)
{
    if (dialog_drawn && dialog_layer) {
        if (dialog_render_valid) {
            layer_dialog_render_page(dialog_render_name, dialog_render_text,
                                     dialog_render_off);
        } else {
            dialog_seed_base();
            dialog_paint_box(dialog_layer, LAYER_DIALOG_W);
        }
        dialog_layer_blit();
    }
}

/* Full reset: free the dialog composite buffer and clear all state. */
void layer_dialog_reset(void)
{
    if (dialog_layer) { free(dialog_layer); dialog_layer = NULL; }
    if (dialog_occluder) { free(dialog_occluder); dialog_occluder = NULL; }
    dialog_drawn = 0;
    dialog_render_valid = 0;
    dialog_render_name[0] = '\0';
    dialog_render_text[0] = '\0';
    dialog_render_off = 0;
}

/* Current dialog composite pixels (480x115) for debug/corruption checks.
 * NULL when not allocated (dialog never opened since last reset). */
const unsigned char *layer_dialog_snapshot(void)
{
    return dialog_layer;
}
