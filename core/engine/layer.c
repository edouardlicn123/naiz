/*
 * Scene layers core — cross-layer lifecycle.
 * Background snapshots moved to layer_bg.c; dialog state machine and
 * dialog/button style to layer_dialog.c; sprite registry to
 * layer_sprite.c.  Cross-file glue in layer_internal.h.
 * Implements C04-图层渲染与换装机制.md design.
 */
#include "render.h"
#include "scene_layers.h"
#include "layer_internal.h"
#include "nb_anim.h"
#include "hal.h"

/*=== Lifecycle ===========================================================*/

static void layer_init(void);

static int g_layer_active[LAYER_Z_COUNT] = {0};

/* Unify scene-end cleanup: sprites, audio, cursor, screen, layers.
 * Called on every scene transition (before loading new .nb).
 * Must be called before any VRAM writes in the new scene.
 * When skip_transition is non-zero, paints solid black immediately
 * (used for logo/op scenes where animated transition is undesirable). */
void scene_end(int skip_transition)
{
    hal_mouse_invalidate_cursor();
    hal_bgm_stop();
    hal_sound_stop();
    hal_voice_stop();
    anim_stop();          /* implicit stop: scene change ends any animation */
    layer_init();
    layer_sprite_hide_all();
    hal_set_palette(0, 0, 0, 0);
    if (skip_transition) {
        fill_rect(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
    } else {
        transition_run(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H,
                       NAIZ_TRANSITION_TYPE, NAIZ_TRANSITION_FRAMES, 0);
        /* Palette fade leaves old VRAM pixels intact; blank them immediately
         * so the screen stays black (even if the palette gets restored by the
         * next scene's image_load) until the new background is blitted. */
        fill_rect(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
    }
    hal_kbd_drain_advance();
    hal_kbd_set_ignore_frames(2);
}

/* Initialize/reset the layer system.
 * Frees all snapshots and clears state.
 * Sprite table reset is handled below (layer_sprite_hide_all).
 * Called on scene transitions and at engine startup. */
static void layer_init(void)
{
    int i;
    for (i = 0; i < LAYER_Z_COUNT; i++)
        g_layer_active[i] = 0;
    layer_bg_reset();
    layer_dialog_reset();
}

/*==== Layer Z-order state management ======================================*/

int layer_is_active(int z_order)
{
    if (z_order < 0 || z_order >= LAYER_Z_COUNT)
        return 0;
    return g_layer_active[z_order];
}

void layer_set_active(int z_order, int active)
{
    if (z_order >= 0 && z_order < LAYER_Z_COUNT)
        g_layer_active[z_order] = active;
}

LayerBounds layer_get_bounds(int z_order)
{
    LayerBounds b = {0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H};
    switch (z_order) {
    case LAYER_Z_BG:
        break;  /* full screen */
    case LAYER_Z_SPRITE:
    case LAYER_Z_ANIM:
        if (layer_is_active(LAYER_Z_DIALOG))
            b.h = LAYER_DIALOG_Y;  /* clip above dialog */
        break;
    case LAYER_Z_DIALOG:
        b.x = LAYER_DIALOG_X;
        b.y = LAYER_DIALOG_Y;
        b.w = LAYER_DIALOG_W;
        b.h = LAYER_DIALOG_H;
        break;
    case LAYER_Z_TEXT:
        b.x = LAYER_DIALOG_X + 16;
        b.y = LAYER_DIALOG_Y + 16;
        b.w = LAYER_DIALOG_W - 32;
        b.h = LAYER_DIALOG_H - 32;
        break;
    case LAYER_Z_CURSOR:
        break;  /* full screen */
    }
    return b;
}

int layer_can_blit_at(int z_order, int y)
{
    if (z_order == LAYER_Z_CURSOR)
        return 1;
    if (z_order == LAYER_Z_DIALOG || z_order == LAYER_Z_TEXT)
        return (y >= LAYER_DIALOG_Y);
    if (z_order == LAYER_Z_ANIM || z_order == LAYER_Z_SPRITE)
        return (!layer_is_active(LAYER_Z_DIALOG) || y < LAYER_DIALOG_Y);
    return 1;
}
