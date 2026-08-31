/*
 * Sprite registry + operations — part of the scene layer subsystem.
 * Extracted from layer.c (refactor): show/face/replace/hide/redraw.
 * Implements the sprite half of C04-图层渲染与换装机制.md.
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

/* Return 1 if at least one sprite is active in the table. */
static int layer_has_any_sprite(void)
{
    int i;
    for (i = 0; i < LAYER_MAX_SPRITES; i++) {
        if (sprite_table[i].active) return 1;
    }
    return 0;
}

/*=== Sprite operations ===================================================*/

/* Show a sprite (full body) — first-time display or full replacement.
 * If dialog is drawn and no other sprites exist, saves the dialog background first.
 * Always draws the sprite at full height (no clip_h).
 * Registers the sprite for subsequent face/replace/hide operations. */
static void layer_sprite_show(int sprite_id, int asset_id, int x, int y, int mirror)
{
    SpriteEntry *se;
    MagImage *img;
    const unsigned char *bg_snap;

    hal_mouse_invalidate_cursor();

    if (layer_dialog_drawn()) {
        bg_snap = layer_bg_dialog_snapshot();
        if (!layer_has_any_sprite() && bg_snap) {
            /* First sprite: restore pristine dialog background before drawing. */
            vram_write(bg_snap, LAYER_DIALOG_X, LAYER_DIALOG_Y,
                       LAYER_DIALOG_W, LAYER_DIALOG_H);
        } else {
            /* Sprite already exists: delegate to replace (handles dirty rect). */
            layer_sprite_replace(sprite_id, asset_id, x, y, mirror);
            return;
        }
    }

    img = image_load((unsigned short)asset_id);
    if (img) {
        vram_blit_sprite(img, x, y, PAL_TRANSPARENT, mirror, 0);
        mag_release(img);
    }

    se = alloc_sprite(sprite_id);
    if (se) {
        sprite_entry_update(se, sprite_id, asset_id, x, y, mirror);
    }

    layer_set_active(LAYER_Z_SPRITE, 1);

    if (layer_dialog_drawn()) {
        layer_dialog_refresh();
        layer_dialog_mark_dirty();
    }
}

/*
 * Face-only sprite replace — does NOT touch the dialog area.
 *
 * INVARIANT: sprite blit is clipped to y < LAYER_DIALOG_Y to avoid
 * overwriting dialog pixels.  The sprite's lower portion (under dialog)
 * is never visible and must be pixel-identical across expressions.
 *
 * If dialog refresh is needed, use layer_sprite_replace() instead.
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
        if (dialog_drawn) {
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
        }
        vram_blit_sprite(img, x, y, PAL_TRANSPARENT, mirror, clip_h);
#ifdef NAIZ_DEBUG
        if (dialog_drawn && layer_dialog_snapshot() && clip_h > 0) {
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

    if (se) {
        sprite_entry_update(se, sprite_id, asset_id, x, y, mirror);
    } else {
        se = alloc_sprite(sprite_id);
        if (se) {
            se->id = sprite_id;
            se->asset_id = asset_id;
            se->x = x;
            se->y = y;
            se->mirror = mirror;
        }
    }
}

/* Replace a sprite (full body + dialog refresh).
 * Unlike layer_sprite_show(), this restores the background under the old sprite rect,
 * draws the new sprite, then refreshes the dialog on top.
 * Used when a new sprite may have different content in the dialog area. */
static void layer_sprite_replace(int sprite_id, int asset_id, int x, int y, int mirror)
{
    SpriteEntry *se;
    MagImage *img;
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

    layer_bg_restore_rect(ux1, uy1, ux2 - ux1, uy2 - uy1, 0);

    img = image_load((unsigned short)asset_id);
    if (img) {
        vram_blit_sprite(img, x, y, PAL_TRANSPARENT, mirror, 0);
        mag_release(img);
    }

    layer_dialog_refresh();
    layer_dialog_mark_dirty();

    if (se) {
        sprite_entry_update(se, sprite_id, asset_id, x, y, mirror);
    } else {
        se = alloc_sprite(sprite_id);
        if (se) {
            se->id = sprite_id;
            se->asset_id = asset_id;
            se->x = x;
            se->y = y;
            se->mirror = mirror;
        }
    }
}

/* Hide a specific sprite by ID.
 * Restores background under the sprite. If the sprite extended into the dialog area,
 * refreshes the dialog.  If this was the last sprite, restores full background
 * and recaptures the dialog background. */
static void layer_sprite_hide(int id)
{
    SpriteEntry *se;

    if (!layer_dialog_drawn()) {
        se = find_sprite(id);
        if (se) se->active = 0;
        return;
    }

    hal_mouse_invalidate_cursor();
    se = find_sprite(id);
    if (se) {
        layer_bg_restore_rect(se->x, se->y, LAYER_SPRITE_W, LAYER_SPRITE_H, 0);

        /* If sprite overlapped dialog, refresh the dialog overlay. */
        if (se->y + LAYER_SPRITE_H > LAYER_DIALOG_Y) {
            layer_dialog_refresh();
            layer_dialog_mark_dirty();
        }

        se->active = 0;

        /*
         * Last sprite removed: restore background above dialog only,
         * then recapture dialog region.  Full restore would overwrite
         * the dialog overlay, corrupting the dialog snapshot.
         */
        if (!layer_has_any_sprite() && layer_bg_snapshot_valid() && layer_bg_snapshot()) {
            layer_bg_restore_rect(0, 0, LAYER_SCREEN_W, LAYER_DIALOG_Y, 0);
            layer_capture_bg_dialog_from_bg();
            layer_dialog_mark_dirty();
        }
    }
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

/* Redraw all active sprites on top of the background.
 * Each sprite respects clip_h when dialog is drawn (no writes below dialog).
 * Used during dialog_snap and scene transitions. */
void layer_redraw_sprites(void)
{
    int i;
    for (i = 0; i < LAYER_MAX_SPRITES; i++) {
        SpriteEntry *se = &sprite_table[i];
        if (se->active) {
            MagImage *img;
            int clip_h;
            img = image_load((unsigned short)se->asset_id);
            if (img) {
                if (layer_dialog_drawn() && se->y >= LAYER_DIALOG_Y) {
                    mag_release(img);
                    continue;
                }
                clip_h = layer_dialog_drawn() ? calc_sprite_clip_h(se->y, img->height) : 0;
                vram_blit_sprite(img, se->x, se->y, PAL_TRANSPARENT, se->mirror, clip_h);
                mag_release(img);
            }
        }
    }
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
