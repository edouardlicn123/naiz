/*
 * layer_debug.c — Visual debugging: PPM export for layer diagnostics.
 *
 * Each layer's pixel content can be exported as a PPM file for offline
 * analysis.  Composite export renders the final composited frame.
 * Triggered via layer_debug_handle() (keyboard shortcut or serial).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "render.h"
#include "scene_layers.h"
#include "layer_internal.h"
#include "palette.h"
#include "hal.h"
#include "layer_debug.h"

/*==== PPM writer =========================================================*/

static int write_ppm(const char *filename, int w, int h, const uint8_t *rgb)
{
    FILE *f;
    int len;
    char msg[128];

    f = fopen(filename, "wb");
    if (!f) {
        snprintf(msg, sizeof(msg), "layer_debug: cannot open '%s'\r\n", filename);
        hal_log(msg);
        return -1;
    }

    fprintf(f, "P6\n%d %d\n255\n", w, h);
    len = w * h * 3;
    fwrite(rgb, 1, len, f);
    fclose(f);
    snprintf(msg, sizeof(msg), "layer_debug: exported '%s' (%dx%d)\r\n", filename, w, h);
    hal_log(msg);
    return 0;
}

/*==== Palette conversion =================================================*/

static void palette_to_rgb(uint8_t *rgb, const uint8_t *indices, int count)
{
    uint8_t pal[PALETTE_SIZE][3];
    int i;

    palette_get_all(pal);
    for (i = 0; i < count; i++) {
        rgb[i * 3]     = pal[indices[i]][0];
        rgb[i * 3 + 1] = pal[indices[i]][1];
        rgb[i * 3 + 2] = pal[indices[i]][2];
    }
}

/*==== Per-layer dump =====================================================*/

static int dump_bg_layer(const char *filename)
{
    const uint8_t *snap;
    uint8_t *rgb;
    int size;
    char msg[80];

    snap = layer_bg_snapshot();
    if (!snap) {
        hal_log("layer_debug: bg_snapshot not available\r\n");
        return -1;
    }

    size = LAYER_SCREEN_W * LAYER_SCREEN_H;
    rgb = (uint8_t *)malloc((size_t)size * 3);
    if (!rgb) {
        hal_log("layer_debug: OOM for bg rgb buffer\r\n");
        return -1;
    }

    palette_to_rgb(rgb, snap, size);
    write_ppm(filename, LAYER_SCREEN_W, LAYER_SCREEN_H, rgb);
    free(rgb);
    return 0;
}

static int dump_dialog_layer(const char *filename)
{
    const uint8_t *snap;
    uint8_t *rgb;
    int size;

    snap = layer_dialog_snapshot();
    if (!snap) {
        hal_log("layer_debug: dialog_snapshot not available\r\n");
        return -1;
    }

    size = LAYER_DIALOG_W * LAYER_DIALOG_H;
    rgb = (uint8_t *)malloc((size_t)size * 3);
    if (!rgb) {
        hal_log("layer_debug: OOM for dialog rgb buffer\r\n");
        return -1;
    }

    palette_to_rgb(rgb, snap, size);
    write_ppm(filename, LAYER_DIALOG_W, LAYER_DIALOG_H, rgb);
    free(rgb);
    return 0;
}

static int dump_sprite_layer(const char *filename)
{
    uint8_t *vram_buf, *bg_snap, *rgb;
    int size, i;
    uint8_t pal[PALETTE_SIZE][3];

    size = LAYER_SCREEN_W * LAYER_SCREEN_H;
    vram_buf = (uint8_t *)malloc((size_t)size);
    bg_snap = (uint8_t *)malloc((size_t)size);
    rgb = (uint8_t *)malloc((size_t)size * 3);

    if (!vram_buf || !bg_snap || !rgb) {
        free(vram_buf); free(bg_snap); free(rgb);
        hal_log("layer_debug: OOM for sprite dump\r\n");
        return -1;
    }

    vram_read(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, vram_buf);

    if (layer_bg_snapshot()) {
        memcpy(bg_snap, layer_bg_snapshot(), (size_t)size);
    } else {
        memset(bg_snap, 0, (size_t)size);
    }

    palette_get_all(pal);

    /* Diff: sprite pixels = VRAM != background; convert to RGB */
    for (i = 0; i < size; i++) {
        if (vram_buf[i] != bg_snap[i]) {
            rgb[i * 3]     = pal[vram_buf[i]][0];
            rgb[i * 3 + 1] = pal[vram_buf[i]][1];
            rgb[i * 3 + 2] = pal[vram_buf[i]][2];
        } else {
            rgb[i * 3]     = 0;
            rgb[i * 3 + 1] = 0;
            rgb[i * 3 + 2] = 0;
        }
    }

    write_ppm(filename, LAYER_SCREEN_W, LAYER_SCREEN_H, rgb);
    free(vram_buf); free(bg_snap); free(rgb);
    return 0;
}

static int dump_composite_layer(const char *filename)
{
    uint8_t *vram_buf, *rgb;
    int size;

    size = LAYER_SCREEN_W * LAYER_SCREEN_H;
    vram_buf = (uint8_t *)malloc((size_t)size);
    rgb = (uint8_t *)malloc((size_t)size * 3);

    if (!vram_buf || !rgb) {
        free(vram_buf); free(rgb);
        return -1;
    }

    vram_read(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, vram_buf);
    palette_to_rgb(rgb, vram_buf, size);
    write_ppm(filename, LAYER_SCREEN_W, LAYER_SCREEN_H, rgb);
    free(vram_buf); free(rgb);
    return 0;
}

/*==== Public API =========================================================*/

static int layer_dump(int z_order, const char *filename)
{
    char msg[80];
    switch (z_order) {
    case LAYER_Z_BG:      return dump_bg_layer(filename);
    case LAYER_Z_SPRITE:  return dump_sprite_layer(filename);
    case LAYER_Z_DIALOG:  return dump_dialog_layer(filename);
    case LAYER_Z_ANIM:
        /* Animation uses the same VRAM as bg; export composite instead */
        return dump_composite_layer(filename);
    default:
        snprintf(msg, sizeof(msg), "layer_debug: unsupported z_order %d\r\n", z_order);
        hal_log(msg);
        return -1;
    }
}

static int layer_dump_composite(const char *filename)
{
    return dump_composite_layer(filename);
}

static int layer_dump_all(const char *prefix)
{
    char fname[64];
    int count = 0;

    snprintf(fname, sizeof(fname), "%s_bg.ppm", prefix);
    if (layer_dump(LAYER_Z_BG, fname) == 0) count++;

    snprintf(fname, sizeof(fname), "%s_sprite.ppm", prefix);
    if (layer_dump(LAYER_Z_SPRITE, fname) == 0) count++;

    snprintf(fname, sizeof(fname), "%s_dialog.ppm", prefix);
    if (layer_dump(LAYER_Z_DIALOG, fname) == 0) count++;

    snprintf(fname, sizeof(fname), "%s_composite.ppm", prefix);
    if (layer_dump_composite(fname) == 0) count++;

    return count;
}

static void debug_dump_status(void)
{
    char msg[80];
    hal_log("layer status:\r\n");
    snprintf(msg, sizeof(msg), "  bg:      %s\r\n", layer_is_active(LAYER_Z_BG) ? "active" : "inactive");
    hal_log(msg);
    snprintf(msg, sizeof(msg), "  sprite:  %s\r\n", layer_is_active(LAYER_Z_SPRITE) ? "active" : "inactive");
    hal_log(msg);
    snprintf(msg, sizeof(msg), "  anim:    %s\r\n", layer_is_active(LAYER_Z_ANIM) ? "active" : "inactive");
    hal_log(msg);
    snprintf(msg, sizeof(msg), "  dialog:  %s\r\n", layer_is_active(LAYER_Z_DIALOG) ? "active" : "inactive");
    hal_log(msg);
    snprintf(msg, sizeof(msg), "  text:    %s\r\n", layer_is_active(LAYER_Z_TEXT) ? "active" : "inactive");
    hal_log(msg);
    hal_log("  cursor:  always active\r\n");
}

void layer_debug_handle(const char *arg)
{
    if (!arg || !*arg) {
        hal_log("dump usage: bg|sprite|dialog|anim|all|status\r\n");
        return;
    }

    if (strcmp(arg, "bg") == 0)
        layer_dump(LAYER_Z_BG, "dump_bg.ppm");
    else if (strcmp(arg, "sprite") == 0)
        layer_dump(LAYER_Z_SPRITE, "dump_sprite.ppm");
    else if (strcmp(arg, "dialog") == 0)
        layer_dump(LAYER_Z_DIALOG, "dump_dialog.ppm");
    else if (strcmp(arg, "anim") == 0)
        layer_dump(LAYER_Z_ANIM, "dump_anim.ppm");
    else if (strcmp(arg, "all") == 0)
        layer_dump_all("dump");
    else if (strcmp(arg, "status") == 0)
        debug_dump_status();
    else
        hal_log("dump usage: bg|sprite|dialog|anim|all|status\r\n");
}
