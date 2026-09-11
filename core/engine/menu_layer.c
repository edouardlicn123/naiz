/*
 * menu_layer.c — reusable menu overlay layer (draw / blit / restore).
 *
 * The layer manages a region-sized RAM composite buffer and, in opaque mode,
 * a matching base snapshot of the underneath.  While open, render_set_target
 * + text_set_target route fill/pset/pattern and glyph drawing into the
 * composite; menu_layer_commit resets both.  Blits write the composite (with
 * its base, or skipping PAL_TRANSPARENT in transparent mode) back to VRAM.
 *
 * Opaque mode:  close(restore=1) writes the base back so leaving the menu
 * leaves the pre-menu screen intact (same contract as dialog_layer_hide
 * restoring under_dialog).
 * Transparent mode: no base copy; blit holes show the underneath.  close()
 * never touches VRAM.
 */
#include <stdlib.h>
#include <string.h>
#include "render.h"
#include "menu_layer.h"
#include "hal.h"

#include "debug.h"

static unsigned char *menu_layer_buf = NULL;   /* composite (w*h) */
static unsigned char *menu_layer_base = NULL;  /* opaque base snapshot */
static int menu_layer_x = 0;
static int menu_layer_y = 0;
static int menu_layer_w = 0;
static int menu_layer_h = 0;
static int menu_layer_transparent = 0;
static int menu_layer_open_flag = 0;

int menu_layer_is_open(void)
{
    return menu_layer_open_flag;
}

const uint8_t *menu_layer_pixels(void)
{
    return menu_layer_buf;
}

int menu_layer_open(int x, int y, int w, int h, int transparent)
{
    int area;
    unsigned char *comp, *base = NULL;

    /* Clamp the requested region to the screen (C6 boundary guard). */
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if (w <= 0 || h <= 0 || x >= LAYER_SCREEN_W || y >= LAYER_SCREEN_H)
        return -1;
    if (x + w > LAYER_SCREEN_W) w = LAYER_SCREEN_W - x;
    if (y + h > LAYER_SCREEN_H) h = LAYER_SCREEN_H - y;
    if (w <= 0 || h <= 0)
        return -1;

    /* Re-open semantics: drop any current layer first. */
    menu_layer_close(0);

    area = w * h;
    comp = (unsigned char *)malloc((size_t)area);
    if (!comp) {
        hal_log("[MENU_LAYER] composite alloc failed — VRAM fallback\r\n");
        return -1;
    }
    if (!transparent) {
        base = (unsigned char *)malloc((size_t)area);
        if (!base) {
            hal_log("[MENU_LAYER] base alloc failed — VRAM fallback\r\n");
            free(comp);
            return -1;
        }
    }

    /* Snapshot the underneath (opaque mode: into base, then copied to the
     * composite; transparent mode: the composite starts fully transparent). */
    if (transparent)
        memset(comp, PAL_TRANSPARENT, (size_t)area);
    else {
        vram_read(x, y, w, h, base);
        memcpy(comp, base, (size_t)area);
    }

    menu_layer_buf = comp;
    menu_layer_base = base;
    menu_layer_x = x;
    menu_layer_y = y;
    menu_layer_w = w;
    menu_layer_h = h;
    menu_layer_transparent = transparent;
    menu_layer_open_flag = 1;

    menu_layer_begin_draw();
    return 0;
}

void menu_layer_begin_draw(void)
{
    if (!menu_layer_open_flag)
        return;
    /* Route fill/pset/pattern and glyph drawing into the composite. */
    render_set_target(menu_layer_buf, menu_layer_w, menu_layer_h, menu_layer_w,
                      menu_layer_x, menu_layer_y);
    text_set_target(menu_layer_buf, menu_layer_w, menu_layer_h, menu_layer_w,
                    menu_layer_x, menu_layer_y);
}

void menu_layer_commit(void)
{
    render_set_target_vram();
    text_set_target_vram();
}

void menu_layer_blit(void)
{
    if (!menu_layer_open_flag)
        return;
    if (menu_layer_transparent)
        render_blit_transparent(menu_layer_buf, menu_layer_w,
                                0, 0, menu_layer_w, menu_layer_h,
                                menu_layer_x, menu_layer_y, PAL_TRANSPARENT);
    else
        vram_write(menu_layer_buf, menu_layer_x, menu_layer_y,
                   menu_layer_w, menu_layer_h);
}

void menu_layer_blit_rect(int x, int y, int w, int h)
{
    int bx, by;
    if (!menu_layer_open_flag)
        return;
    /* Clip the screen rect to the open layer region. */
    if (x < menu_layer_x) { w -= menu_layer_x - x; x = menu_layer_x; }
    if (y < menu_layer_y) { h -= menu_layer_y - y; y = menu_layer_y; }
    if (x + w > menu_layer_x + menu_layer_w) w = menu_layer_x + menu_layer_w - x;
    if (y + h > menu_layer_y + menu_layer_h) h = menu_layer_y + menu_layer_h - y;
    if (w <= 0 || h <= 0)
        return;
    bx = x - menu_layer_x;
    by = y - menu_layer_y;
    if (menu_layer_transparent)
        render_blit_transparent(menu_layer_buf, menu_layer_w,
                                bx, by, w, h,
                                menu_layer_x, menu_layer_y, PAL_TRANSPARENT);
    else
        vram_write(menu_layer_buf + by * menu_layer_w + bx, x, y, w, h);
}

void menu_layer_erase_to_base(int x, int y, int w, int h)
{
    int bx, by, py;
    if (!menu_layer_open_flag || menu_layer_transparent || !menu_layer_base)
        return;
    /* Clip the screen rect to the open layer region. */
    if (x < menu_layer_x) { w -= menu_layer_x - x; x = menu_layer_x; }
    if (y < menu_layer_y) { h -= menu_layer_y - y; y = menu_layer_y; }
    if (x + w > menu_layer_x + menu_layer_w) w = menu_layer_x + menu_layer_w - x;
    if (y + h > menu_layer_y + menu_layer_h) h = menu_layer_y + menu_layer_h - y;
    if (w <= 0 || h <= 0)
        return;
    bx = x - menu_layer_x;
    by = y - menu_layer_y;
    for (py = 0; py < h; py++) {
        memcpy(menu_layer_buf + (by + py) * menu_layer_w + bx,
               menu_layer_base + (by + py) * menu_layer_w + bx, (size_t)w);
    }
}

void menu_layer_blit_sprite(const MagImage *img, int x, int y, uint8_t transparent_idx)
{
    int sx, sy, bx, by, img_w, img_h;
    if (!menu_layer_open_flag) {
        vram_blit_sprite(img, x, y, transparent_idx, 0, 0);
        return;
    }
    img_w = img->width;
    img_h = img->height;
    for (sy = 0; sy < img_h; sy++) {
        by = y + sy - menu_layer_y;
        if (by < 0 || by >= menu_layer_h) continue;
        for (sx = 0; sx < img_w; sx++) {
            uint8_t c = img->pixels[sy * img_w + sx];
            if (c == transparent_idx) continue;
            bx = x + sx - menu_layer_x;
            if (bx < 0 || bx >= menu_layer_w) continue;
            menu_layer_buf[by * menu_layer_w + bx] = c;
        }
    }
}

void menu_layer_close(int restore)
{
    if (!menu_layer_open_flag)
        return;
    if (restore && !menu_layer_transparent && menu_layer_base)
        vram_write(menu_layer_base, menu_layer_x, menu_layer_y,
                   menu_layer_w, menu_layer_h);
    menu_layer_commit();
    if (menu_layer_buf) { free(menu_layer_buf); menu_layer_buf = NULL; }
    if (menu_layer_base) { free(menu_layer_base); menu_layer_base = NULL; }
    menu_layer_open_flag = 0;
}
