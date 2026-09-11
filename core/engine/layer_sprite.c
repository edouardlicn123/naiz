/*
 * Sprite registry + operations — part of the scene layer subsystem.
 * Extracted from layer.c (refactor): show/face/replace/hide/redraw.
 * Implements the sprite half of C04-图层渲染与换装机制.md.
 *
 * R20 pseudo-transparency (revokes the Option X clipping): while the dialog
 * is open sprites are drawn at full body (extending into the dialog rect,
 * under it in z-order).  After every sprite change the live dialog occluder
 * (underneath + sprites) is rebuilt and the dialog composite recomposed over
 * it, so the dialog dither holes keep the actors visible.  Closing the
 * dialog restores the underneath and redraws sprites at full body.
 */
#include <stdlib.h>
#include "render.h"
#include "scene_layers.h"
#include "layer_internal.h"
#include "image.h"
#include "hal.h"
#include "debug.h"

/* Sprite registry tracking all active sprites. */
static SpriteEntry sprite_table[LAYER_MAX_SPRITES];

/*=== Helpers =============================================================*/

/* Update all fields of a sprite entry in one call. */
static void sprite_entry_update(SpriteEntry *se, int id, int asset_id,
                                  int x, int y, int mirror)
{
    se->id = id;
    se->asset_id = asset_id;
    se->x = x;
    se->y = y;
    se->mirror = mirror;
}

/* Find a sprite by ID. Returns NULL if not found or inactive. */
static SpriteEntry *find_sprite(int id)
{
    int i;
    for (i = 0; i < LAYER_MAX_SPRITES; i++) {
        if (sprite_table[i].active && sprite_table[i].id == id)
            return &sprite_table[i];
    }
    return NULL;
}

/* Allocate or reuse a sprite slot for the given ID.
 * If the ID already exists, returns the existing entry (replaces).
 * Otherwise finds the first free (inactive) slot.
 * Returns NULL if all MAX_SPRITES slots are full. */
static SpriteEntry *alloc_sprite(int id)
{
    int i;
    SpriteEntry *se = find_sprite(id);
    if (se) return se;
    for (i = 0; i < LAYER_MAX_SPRITES; i++) {
        if (!sprite_table[i].active) {
            sprite_table[i].active = 1;
            return &sprite_table[i];
        }
    }
    return NULL;
}

/* Forward declaration (mutual recursion between show and replace). */
static void layer_sprite_replace(int sprite_id, int asset_id, int x, int y, int mirror);

/* Write a sprite's pixels that overlap the dialog rect into the live dialog
 * occluder (PAL_TRANSPARENT skipped, mirror supported).  The occluder is the
 * composite seed for the dialog box, so its dither holes keep the actors
 * visible under the box (pseudo-transparency, R20). */
static void dialog_occluder_sprite_blit(const MagImage *img, int x, int y, int mirror)
{
    uint8_t *occ;
    int y0, y1, sy, sx;

    if (!img) return;
    occ = layer_dialog_occluder();
    if (!occ) return;
    /* Reject the sprite outright when it cannot reach the dialog rect. */
    y0 = y;
    y1 = y + img->height;
    if (y1 <= LAYER_DIALOG_Y || y0 >= LAYER_DIALOG_Y + LAYER_DIALOG_H) return;
    if (x + img->width <= LAYER_DIALOG_X || x >= LAYER_DIALOG_X + LAYER_DIALOG_W) return;

    for (sy = 0; sy < img->height; sy++) {
        int ry = y + sy;
        int buf_y;
        int xs, xe, sxx;
        if (ry < LAYER_DIALOG_Y) continue;
        if (ry >= LAYER_DIALOG_Y + LAYER_DIALOG_H) break;
        buf_y = ry - LAYER_DIALOG_Y;
        xs = x < LAYER_DIALOG_X ? LAYER_DIALOG_X : x;
        xe = x + img->width > LAYER_DIALOG_X + LAYER_DIALOG_W
             ? LAYER_DIALOG_X + LAYER_DIALOG_W : x + img->width;
        for (sxx = xs; sxx < xe; sxx++) {
            int src_x = mirror ? (img->width - 1 - (sxx - x)) : (sxx - x);
            uint8_t c = img->pixels[sy * img->width + src_x];
            if (c != PAL_TRANSPARENT)
                occ[buf_y * LAYER_DIALOG_W + (sxx - LAYER_DIALOG_X)] = c;
        }
    }
}

/* Rebuild the live dialog occluder (pristine underneath + every active
 * sprite) and recompose the dialog over it.  Called after each sprite change
 * while the dialog is open and at dialog open, so the box shows the actors
 * through its dither holes. */
void layer_sprite_sync_dialog_base(void)
{
    int i;

    if (!layer_dialog_occluder() || !layer_dialog_drawn()) return;
    dialog_occluder_reset_base();
    for (i = 0; i < LAYER_MAX_SPRITES; i++) {
        SpriteEntry *se = &sprite_table[i];
        if (se->active) {
            MagImage *img = image_load((unsigned short)se->asset_id);
            if (img) {
                dialog_occluder_sprite_blit(img, se->x, se->y, se->mirror);
                mag_release(img);
            }
        }
    }
    layer_dialog_recompose();
}

/* Calculate sprite clip height: limit output to rows above the dialog area.
 * Returns positive rows to clip (LAYER_DIALOG_Y - y) when sprite partially
 * extends into dialog area, 0 when fully above (no clip needed) or when
 * fully below dialog (caller must skip). */
static int calc_sprite_clip_h(int y, int img_h)
{
    if (y + img_h > LAYER_DIALOG_Y)
        return (y < LAYER_DIALOG_Y) ? (LAYER_DIALOG_Y - y) : 0;
    return 0;
}

/* Load a sprite image and draw it to VRAM at full body (clip 0; an open
 * dialog recomposes over the sprite in z-order, R20).  Missing assets are
 * skipped silently — image_load already logs the failure. */
static void sprite_blit_full(int asset_id, int x, int y, int mirror)
{
    MagImage *img = image_load((unsigned short)asset_id);
    if (img) {
        vram_blit_sprite(img, x, y, PAL_TRANSPARENT, mirror, 0);
        mag_release(img);
    }
}

/*=== Sprite operations ===================================================*/

/* Show a sprite (full body) — first-time display or full replacement.
 * Drawn at full height even while the dialog is open — it sits under the
 * dialog composite in z-order; layer_sprite_sync_dialog_base() rebuilds the
 * occluder and recomposes the dialog over it (pseudo-transparency, R20). */
static void layer_sprite_show(int sprite_id, int asset_id, int x, int y, int mirror)
{
    SpriteEntry *se;

    hal_mouse_invalidate_cursor();

    sprite_blit_full(asset_id, x, y, mirror);

    se = alloc_sprite(sprite_id);
    if (se) {
        sprite_entry_update(se, sprite_id, asset_id, x, y, mirror);
    }

    layer_set_active(LAYER_Z_SPRITE, 1);
    layer_sprite_sync_dialog_base();
}

/*
 * Face-only sprite replace — updates only the upper body (clipped to
 * y < LAYER_DIALOG_Y) so the dialog rect pixels stay untouched; the full
 * body below comes from the last show/replace and stays visible through the
 * dialog box.  Use layer_sprite_replace() (full body) when the pose must
 * change below the dialog boundary.
 */
void layer_sprite_face(int sprite_id, int asset_id, int x, int y, int mirror)
{
    SpriteEntry *se;
    MagImage *img;
    int dialog_drawn;

    hal_mouse_invalidate_cursor();
    dialog_drawn = layer_dialog_drawn();

    /*
     * No dialog yet: fall back to full-body sprite (no clip_h).
     * Once the dialog opens, face sprites clip to y < LAYER_DIALOG_Y.
     */
    if (!dialog_drawn) {
        layer_sprite_show(sprite_id, asset_id, x, y, mirror);
        return;
    }

    se = find_sprite(sprite_id);
    if (se) {
        /* Restore background under old sprite (above dialog only, clip_dialog=1). */
        layer_bg_restore_rect(se->x, se->y, LAYER_SPRITE_W,
                              LAYER_DIALOG_Y - se->y, 1);
    }

    img = image_load((unsigned short)asset_id);
    if (img) {
        int clip_h = 0;
        /* Sprite entirely inside dialog area: discard.  Note this is a
         * script-authoring error (face position must stay above the
         * dialog); we still deactivate any tracked entry so a later
         * face/replace can't resurrect pixels, but a caller that never
         * registered the sprite (se==NULL) has no background restore —
         * that path relies on the sprite not having been drawn yet. */
        if (y >= LAYER_DIALOG_Y) {
            mag_release(img);
            if (se) { se->active = 0; }
            return;
        }
        /* Clip to dialog boundary to avoid overwriting dialog pixels. */
        clip_h = calc_sprite_clip_h(y, img->height);
        vram_blit_sprite(img, x, y, PAL_TRANSPARENT, mirror, clip_h);
#ifdef NAIZ_DEBUG
        if (layer_dialog_snapshot() && clip_h > 0) {
            int ox = x < LAYER_DIALOG_X ? LAYER_DIALOG_X : x;
            int ow = (x + LAYER_SPRITE_W > LAYER_DIALOG_X + LAYER_DIALOG_W)
                     ? (LAYER_DIALOG_X + LAYER_DIALOG_W - ox) : (x + LAYER_SPRITE_W - ox);
            if (ow > 0) {
                unsigned char row[256];
                const unsigned char *snap = layer_dialog_snapshot();
                int i;
                int check_w = ow > 256 ? 256 : ow;
                vram_read(ox, LAYER_DIALOG_Y, check_w, 1, row);
                for (i = 0; i < check_w; i++) {
                    if (row[i] != snap[(ox - LAYER_DIALOG_X) + i]) {
                        hal_log("WARN: face corrupted dialog area\r\n");
                        break;
                    }
                }
            }
        }
#endif
        mag_release(img);
    }

    if (!se) se = alloc_sprite(sprite_id);
    if (se) sprite_entry_update(se, sprite_id, asset_id, x, y, mirror);
}

/* Replace a sprite (full body): restore the background under the old sprite
 * rect (dialog rect untouched — clip_dialog=1), then draw the new sprite at
 * full height.  The dialog composite is then rebuilt over the fresh occluder
 * via layer_sprite_sync_dialog_base() (pseudo-transparency, R20). */
static void layer_sprite_replace(int sprite_id, int asset_id, int x, int y, int mirror)
{
    SpriteEntry *se;
    int ux1, uy1, ux2, uy2;

    hal_mouse_invalidate_cursor();

    if (!layer_dialog_drawn()) {
        layer_sprite_show(sprite_id, asset_id, x, y, mirror);
        return;
    }

    se = find_sprite(sprite_id);

    /* Compute dirty rect = union of old and new sprite rects. */
    if (se) {
        ux1 = se->x < x ? se->x : x;
        uy1 = se->y < y ? se->y : y;
        ux2 = (se->x + LAYER_SPRITE_W) > (x + LAYER_SPRITE_W) ?
              (se->x + LAYER_SPRITE_W) : (x + LAYER_SPRITE_W);
        uy2 = (se->y + LAYER_SPRITE_H) > (y + LAYER_SPRITE_H) ?
              (se->y + LAYER_SPRITE_H) : (y + LAYER_SPRITE_H);
    } else {
        ux1 = x; uy1 = y;
        ux2 = x + LAYER_SPRITE_W; uy2 = y + LAYER_SPRITE_H;
    }

    layer_bg_restore_rect(ux1, uy1, ux2 - ux1, uy2 - uy1, 1);

    sprite_blit_full(asset_id, x, y, mirror);

    if (!se) se = alloc_sprite(sprite_id);
    if (se) sprite_entry_update(se, sprite_id, asset_id, x, y, mirror);
    layer_sprite_sync_dialog_base();
}

/* Hide a specific sprite by ID: restore the background under its rect
 * (dialog rect untouched — clip_dialog=1), drop it from the occluder and
 * recompose the dialog (R20). */
static void layer_sprite_hide(int id)
{
    SpriteEntry *se = find_sprite(id);
    if (!se) return;
    hal_mouse_invalidate_cursor();
    layer_bg_restore_rect(se->x, se->y, LAYER_SPRITE_W, LAYER_SPRITE_H, 1);
    se->active = 0;
    layer_sprite_sync_dialog_base();
}

/* Hide all active sprites. */
void layer_sprite_hide_all(void)
{
    int i;
    for (i = 0; i < LAYER_MAX_SPRITES; i++) {
        if (sprite_table[i].active) {
            layer_sprite_hide(sprite_table[i].id);
        }
    }
    layer_set_active(LAYER_Z_SPRITE, 0);
    hal_mouse_invalidate_cursor();
}

/* Check if a sprite with the given ID exists. */
int layer_has_sprite(int id)
{
    return find_sprite(id) != NULL;
}

/* Redraw all active sprites on top of the background at full body (the
 * dialog, when open, is recomposed over them afterwards — R20). */
void layer_redraw_sprites(void)
{
    int i;
    for (i = 0; i < LAYER_MAX_SPRITES; i++) {
        SpriteEntry *se = &sprite_table[i];
        if (se->active) {
            sprite_blit_full(se->asset_id, se->x, se->y, se->mirror);
        }
    }
    layer_sprite_sync_dialog_base();
}

/*==== Unified entry point ================================================*/

/* Unified sprite update: auto-selects show/replace based on current state. */
void layer_sprite_update(int sprite_id, int asset_id, int x, int y, int mirror)
{
    if (!layer_has_sprite(sprite_id))
        layer_sprite_show(sprite_id, asset_id, x, y, mirror);
    else
        layer_sprite_replace(sprite_id, asset_id, x, y, mirror);
}
