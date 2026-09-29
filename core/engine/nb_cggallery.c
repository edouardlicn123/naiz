/*
 * nb_cggallery.c — NB CG gallery grid menu.
 *
 * Split from nb_mainmenu.c (devdoc: CG gallery is a self-contained feature
 * track: grid geometry, cell drawing, fullscreen preview, paging).  Only
 * cmd_cgvmenu is public (declared in nb_commands.h, registered in
 * nb_commands.c cmd_table); all grid helpers are file-local static.
 *
 * Stage 5 (devdoc 92): full grid browsing + fullscreen preview + locked
 * placeholder cells.  Bridged from mainmenu via cgview.nb which ends here.
 * Layout: 4 cols x 3 rows, cell 144x84 at x=20/168/316/464, y=44/132/220.
 */
#include <stdio.h>
#include <string.h>
#include "render.h"
#include "image.h"
#include "scene_layers.h"
#include "hal.h"
#include "save.h"
#include "nb.h"
#include "nb_internal.h"
#include "nb_commands.h"
#include "ui.h"
#include "debug.h"
#include "nb_asset_table.h"
#include "tr.h"
#include "input_boundary.h"

/* Cell grid geometry.  GAL_CELL_W/GAL_CELL_H are the thumbnail pixel size
 * generated at build time by tools/naiz_build/cg_thumb.py — the two must
 * stay in sync or the grid blits a mis-sized image (guarded by
 * tools/tests/test_cg_thumb_size.py).  Cell height is sized so the grid
 * bottom clears the standard page-nav arrow band (318) with margin, keeping
 * the gallery footer identical to saveload/special/setting. */
#define GAL_COLS        4
#define GAL_ROWS        3
#define GAL_CELLS       (GAL_COLS * GAL_ROWS)      /* 12 per page */
#define GAL_ORIGIN_X    20
#define GAL_ORIGIN_Y    44
#define GAL_CELL_W      144
#define GAL_CELL_H      84
#define GAL_STEP_X      148     /* cell 144 + 4 gap */
#define GAL_STEP_Y      88      /* cell 84 + 4 gap */
#define GAL_GRID_BOTTOM (GAL_ORIGIN_Y + (GAL_ROWS - 1) * GAL_STEP_Y + GAL_CELL_H)
/* Footer chrome — same y as every other system menu.  Named because
 * gallery_draw_grid and gallery_draw_cells_range both place them. */
#define GAL_ARROWS_Y    318
#define GAL_COUNT_Y     330
#define GAL_BACK_Y      352
/* Last in-grid cell index (0..GAL_CELLS-1); named to keep the repeated
 * GAL_CELLS - 1 centering/pivot arithmetic a single source of truth. */
#define GAL_LAST_CELL_IDX   (GAL_CELLS - 1)

/* Gallery widget colors.  Drawn with the engine-reserved high palette
 * slots (248-255), which belong to the UI subsystems and are never
 * touched by image palettes (image.c: image_set_palette() skips that
 * range for every image type), so they stay valid no matter which
 * background or thumbnail is loaded behind the grid.
 *   GAL_FILL_UNLOCKED (255): the unlock-blue tile fallback fill.
 *   GAL_FILL_LOCKED / GAL_BADGE_BG: PAL_CURSOR_BLACK (engine-reserved
 *     black).  Locked-cell fill, page/footer text color and the index badge
 *     backing plate — the badge needs an opaque plate because the gallery
 *     artwork and the CG thumbnails are light, so bare text is unreadable.
 *   GAL_FG: MENU_PAL_WHITE (menu palette, set by menu_save_item_palette). */
#define GAL_FILL_UNLOCKED   255
#define GAL_FILL_LOCKED     PAL_CURSOR_BLACK
#define GAL_BADGE_BG        PAL_CURSOR_BLACK
#define GAL_FG              MENU_PAL_WHITE

enum { GAL_VIEW_GRID = 0, GAL_VIEW_CG = 1 };

/* Unlock state cache: rebuilt once per gallery entry so cell drawing never
 * re-reads SYSTEM.SAV on every frame / cell (file I/O).  Rebuilt at
 * cmd_cgvmenu entry so CGs unlocked earlier in the session show instantly.
 * Sized defensively: a project with zero registered CG assets (CG_COUNT=0)
 * must still compile (all indexers below are guarded on i < CG_COUNT). */
static unsigned char gal_unlock_cache[CG_COUNT > 0 ? CG_COUNT : 1];

static void gallery_cache_unlocks(void)
{
    int i;
    for (i = 0; i < CG_COUNT; i++)
        gal_unlock_cache[i] = sys_save_is_cg_unlocked(i + 1) ? 1 : 0;
}

/* Saved value of the 255 slot (unlocked-cell blue fill), restored on exit. */
static uint8_t gal_blue_save[3];

static void gallery_palette_save(void)
{
    hal_read_palette(GAL_FILL_UNLOCKED, &gal_blue_save[0], &gal_blue_save[1], &gal_blue_save[2]);
    hal_set_palette(GAL_FILL_UNLOCKED, 0x00, 0x00, 0xFF);
}

static void gallery_palette_restore(void)
{
    hal_set_palette(GAL_FILL_UNLOCKED, gal_blue_save[0], gal_blue_save[1], gal_blue_save[2]);
}

/* Set the reserved slots the gallery *owns* outright.
 *
 * The button scheme (249/252/253) and the dialog fill (248) are left to
 * their real owners (btn_update_palette / dlg_update_palette) — the
 * gallery does not restate them, so the Back button follows the global
 * btnstyle setting.  What this does own is 250/251 (menu text) and
 * 254/255 (badge plate and unlock-blue tile), which the gallery forces to
 * fixed values rather than inheriting.  Image loads leave the whole
 * 248-255 range alone (image.c), so calling this once at entry is enough
 * for the whole visit; the exit-preview call site keeps the background
 * swap self-contained. */
static void gallery_apply_widget_palette(void)
{
    hal_set_palette(MENU_PAL_WHITE,     0xFF, 0xFF, 0xFF);
    hal_set_palette(MENU_PAL_YELLOW,    0xFF, 0xFF, 0x00);
    hal_set_palette(GAL_FILL_UNLOCKED,  0x00, 0x00, 0xFF);
    hal_set_palette(GAL_BADGE_BG,       0x00, 0x00, 0x00);
}

/* Map in-cell-index (0..11) to screen coordinates. */
static void gallery_cell_xy(int i, int *px, int *py)
{
    *px = GAL_ORIGIN_X + (i % GAL_COLS) * GAL_STEP_X;
    *py = GAL_ORIGIN_Y + (i / GAL_COLS) * GAL_STEP_Y;
}

/* Draw the index badge ("01") on an opaque plate.  The plate is required:
 * the gallery artwork and the CG thumbnails are both light, so bare white
 * text over them is unreadable.  Plate width follows the measured text
 * width instead of a hard-coded pixel count. */
static void gallery_draw_badge(int abs_idx, int x, int y)
{
    char label[16];
    int tw;

    snprintf(label, sizeof(label), "%02d", abs_idx + 1);
    tw = text_width(label, 1);
    fill_rect(x + 8, y + 6, tw + 8, 20, GAL_BADGE_BG);
    draw_text(label, 0, x + 12, y + 8, x + GAL_CELL_W - 8, y + 24, 1, GAL_FG);
}

/* Draw a single grid cell. abs_idx is the absolute CG index (0-based;
 * cg_id for the unlock flag is abs_idx+1 per the devdoc 89/92 contract). */
static void gallery_draw_cell(int abs_idx, int x, int y, int is_sel)
{
    int unlocked = gal_unlock_cache[abs_idx];
    int drew_thumb = 0;

    (void)is_sel;
    if (unlocked) {
        /* cg_thumb_map is index-parallel to cg_map; id 0 means the build
         * produced no thumbnail for this CG (blue-tile fallback). */
        if (abs_idx < CG_THUMB_COUNT && cg_thumb_map[abs_idx].id != 0) {
            MagImage *thumb = image_load((unsigned short)cg_thumb_map[abs_idx].id);
            if (thumb) {
                /* menu_layer_blit_sprite, not vram_blit: the grid is drawn
                 * into the menu-layer composite, and vram_blit writes VRAM
                 * directly — the composite publish would paint over it. */
                menu_layer_blit_sprite(thumb, x, y, PAL_NO_TRANSPARENCY);
                mag_release(thumb);
                drew_thumb = 1;
            } else {
                NB_DEBUG("[CGALLERY] thumbnail load failed idx=%d\r\n", abs_idx);
            }
        } else {
            NB_DEBUG("[CGALLERY] no thumbnail asset for idx=%d\r\n", abs_idx);
        }
        if (!drew_thumb)
            fill_rect(x, y, GAL_CELL_W, GAL_CELL_H, GAL_FILL_UNLOCKED);
        gallery_draw_badge(abs_idx, x, y);
        draw_rect(x, y, GAL_CELL_W, GAL_CELL_H, 1, GAL_FG);
    } else {
        fill_rect(x, y, GAL_CELL_W, GAL_CELL_H, GAL_FILL_LOCKED);
        draw_text(tr("[LOCKED]"), 0, x + 30, y + GAL_CELL_H / 2 - 8,
                  x + GAL_CELL_W - 30, y + GAL_CELL_H / 2 + 8, 0, GAL_FG);
        draw_rect(x, y, GAL_CELL_W, GAL_CELL_H, 1, GAL_FG);
    }
}

/* Full redraw of the grid screen (title + cells + back + paging). */
static void gallery_draw_grid(int page, int sel, int focus_on_back)
{
    int total_pages = menu_pagecount(CG_COUNT, GAL_CELLS);
    int page_start = page * GAL_CELLS;
    int tw;
    int i;

    /* Draw into the menu layer composite (opened by cmd_cgvmenu); commit +
     * blit at the end publishes the grid.  Degrades to direct VRAM when the
     * layer is not open (e.g. blank preview exit path). */
    menu_layer_begin_draw();

    vblank_wait();
    /* No full black wash: the composite holds the gallery artwork base
     * snapshot, so only the three widget bands need clearing back to base
     * (title / grid / footer) before they are redrawn.  The backdrop stays
     * visible for the whole visit — the original whole-page black mask was
     * why the artwork only appeared after leaving the gallery. */
    menu_layer_erase_to_base(0, 0, LAYER_SCREEN_W, GAL_ORIGIN_Y);
    menu_layer_erase_to_base(0, GAL_ORIGIN_Y, LAYER_SCREEN_W,
                             GAL_GRID_BOTTOM - GAL_ORIGIN_Y);
    menu_layer_erase_to_base(0, GAL_GRID_BOTTOM, LAYER_SCREEN_W,
                             LAYER_SCREEN_H - GAL_GRID_BOTTOM);

    tw = text_title_width(tr("CG GALLERY"), 3);
    draw_title_large(tr("CG GALLERY"), (LAYER_SCREEN_W - tw) / 2, 4, 3, GAL_FG);

    for (i = 0; i < GAL_CELLS; i++) {
        int abs_idx = page_start + i;
        int x, y;
        if (abs_idx >= CG_COUNT) break;
        gallery_cell_xy(i, &x, &y);
        gallery_draw_cell(abs_idx, x, y, (i == sel) && !focus_on_back);
    }

    menu_back_draw(GAL_BACK_Y, focus_on_back, 1, GAL_FG);
    menu_pagenav_draw(GAL_ARROWS_Y, GAL_COUNT_Y, GAL_FILL_LOCKED, page, total_pages);

    menu_layer_commit();
    menu_layer_blit();
}

/* Incremental redraw: only the two cells whose focus changed (old de-emphasised,
 * new emphasised). Back button focus handled explicitly. from/to are in-cell idx. */
static void gallery_draw_cells_range(int page, int from_sel, int to_sel, int focus_on_back)
{
    int x, y, abs_idx;

    menu_layer_begin_draw();

    if (!focus_on_back) {
        /* Back loses focus (was possibly highlighted): repaint idle color. */
        menu_back_draw(GAL_BACK_Y, 0, 0, GAL_FG);

        /* Old cell loses focus */
        gallery_cell_xy(from_sel, &x, &y);
        abs_idx = page * GAL_CELLS + from_sel;
        if (abs_idx < CG_COUNT)
            gallery_draw_cell(abs_idx, x, y, 0);

        /* New cell gains focus */
        gallery_cell_xy(to_sel, &x, &y);
        abs_idx = page * GAL_CELLS + to_sel;
        if (abs_idx < CG_COUNT)
            gallery_draw_cell(abs_idx, x, y, 1);
    } else {
        /* Focus moved onto Back: de-emphasise old cell, highlight Back. */
        gallery_cell_xy(from_sel, &x, &y);
        abs_idx = page * GAL_CELLS + from_sel;
        if (abs_idx < CG_COUNT)
            gallery_draw_cell(abs_idx, x, y, 0);
        menu_back_draw(GAL_BACK_Y, 1, 0, GAL_FG);
    }

    menu_layer_commit();
    menu_layer_blit();
}

/* Fullscreen preview of one CG. Returns 1 on success (with focus held). */
static int gallery_preview(int abs_idx)
{
    MagImage *img;

    if (!gal_unlock_cache[abs_idx]) {
        NB_DEBUG("[CGALLERY] cg_id=%d locked, preview blocked\r\n", abs_idx + 1);
        return 0;
    }
    img = image_load((unsigned short)cg_map[abs_idx].id);
    if (!img) {
        NB_DEBUG("[CGALLERY] image_load failed for id=%d\r\n", cg_map[abs_idx].id);
        return 0;
    }
    NB_DEBUG("[CGALLERY] preview cg_id=%d\r\n", abs_idx + 1);
    hal_mouse_erase_cursor();
    /* The fullscreen CG replaces the grid: drop the menu layer (no restore —
     * the CG paints over everything) before swapping the background. */
    menu_layer_close(0);
    layer_bg_change(img);
    mag_release(img);          /* snapshot already captured by layer_bg_change */
    hal_mouse_draw_cursor_force();
    return 1;
}

/* Exit preview: restore bg asset then redraw the grid. */
static void gallery_exit_preview(int page, int sel, int focus_on_back)
{
    MagImage *bg = image_load((unsigned short)nb_asset_id("gallery"));
    hal_mouse_erase_cursor();
    if (bg) {
        layer_bg_change(bg);
        mag_release(bg);
    } else {
        fill_rect(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
    }
    /* layer_bg_change refreshed the dialog/button palettes from the global
     * settings; re-state the gallery's own slots so the redrawn title and
     * cell fills keep the gallery values rather than whatever the preview
     * left behind. */
    gallery_apply_widget_palette();
    /* Re-open the grid menu layer over the restored background, then redraw
     * and publish the grid. */
    menu_layer_open(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
    gallery_draw_grid(page, sel, focus_on_back);
    hal_mouse_draw_cursor_force();
}

/* Return to the menu-parent scene (set by specialmenu), falling back to the
 * main menu.  The parent is read at exit time so a stale value can never be
 * consumed across a fresh entry. */
static void gallery_return_home(void)
{
    const char *ret = nb_get_menu_return();
    scene_switch(ret[0] != '\0' ? ret : "mainmenu.nb", SCENE_SWITCH_MENU);
}

/* cmd_cgvmenu — CG gallery browsing menu (bridging script cgview.nb ends). */
void cmd_cgvmenu(int argc, const char **argv, const char *cmd_name)
{
    int running = 1, total_pages, page = 0, sel = 0, focus_on_back = 0, view = GAL_VIEW_GRID;
    (void)argc; (void)argv; (void)cmd_name;

    if (CG_COUNT == 0) {
        NB_DEBUG("cgvmenu: CG_COUNT=0, empty gallery\r\n");
        input_drain_boundary();
        hal_mouse_erase_cursor();
        draw_text(tr("No CGs available."), 0, 200, 190, 440, 210, 1, GAL_FG);
        hal_mouse_draw_cursor_force();
        for (;;) {
            hal_kbd_update();
            hal_mouse_update();
            if (hal_kbd_is_down(KC_ESC) || hal_kbd_is_down(KC_SPACE) ||
                hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_XFER) ||
                hal_mouse_was_clicked(HAL_MOUSE_LBUTTON))
                break;
            hal_mouse_draw_cursor();
        }
        hal_mouse_flush();
        gallery_return_home();
        return;
    }

    total_pages = menu_pagecount(CG_COUNT, GAL_CELLS);

    input_drain_boundary();
    hal_mouse_erase_cursor();
    menu_save_item_palette();
    gallery_palette_save();          /* force slot 255 to the unlock-blue */
    gallery_apply_widget_palette();  /* state the gallery's own 250/251/254/255 */
    gallery_cache_unlocks();
    menu_layer_open(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
    gallery_draw_grid(page, sel, focus_on_back);
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    hal_mouse_draw_cursor_force();

    while (running) {
        int prev_sel = sel, prev_fb = focus_on_back;
        int abs_sel = page * GAL_CELLS + sel;

        hal_kbd_update();

        if (view == GAL_VIEW_GRID) {
            int last_idx = CG_COUNT - page * GAL_CELLS - 1;   /* last valid in-cell idx on this page */

            if (focus_on_back) {
                if (hal_kbd_is_down(KC_UP)) {
                    focus_on_back = 0;
                    sel = (last_idx < GAL_LAST_CELL_IDX) ? last_idx : GAL_LAST_CELL_IDX;
                } else if (hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_SPACE) ||
                           hal_kbd_is_down(KC_XFER)) {
                    running = 0;
                    continue;
                }
            } else {
                if (hal_kbd_is_down(KC_UP) && sel / GAL_COLS > 0) {
                    sel -= GAL_COLS;
                } else if (hal_kbd_is_down(KC_DOWN)) {
                    if (sel + GAL_COLS > last_idx) {
                        focus_on_back = 1;
                    } else {
                        sel += GAL_COLS;
                    }
                } else if (hal_kbd_is_down(KC_LEFT)) {
                    if (sel % GAL_COLS > 0) sel--;
                    else if (page > 0) { page--; sel = 0; gallery_draw_grid(page, sel, focus_on_back); hal_mouse_draw_cursor_force(); continue; }
                } else if (hal_kbd_is_down(KC_RIGHT)) {
                    if (sel % GAL_COLS < GAL_COLS - 1 && page * GAL_CELLS + sel + 1 < CG_COUNT) sel++;
                    else if (page < total_pages - 1) { page++; sel = 0; gallery_draw_grid(page, sel, focus_on_back); hal_mouse_draw_cursor_force(); continue; }
                } else if (hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_SPACE) ||
                           hal_kbd_is_down(KC_XFER)) {
                    if (abs_sel < CG_COUNT) {
                        view = gallery_preview(abs_sel) ? GAL_VIEW_CG : GAL_VIEW_GRID;
                        continue;
                    }
                }
            }
            if (hal_kbd_is_down(KC_ESC)) { running = 0; continue; }

            hal_mouse_update();
            if (hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
                int mx = hal_mouse_get_x(), my = hal_mouse_get_y(), i;

                if (menu_back_hit(GAL_BACK_Y, mx, my)) { running = 0; continue; }
                if (menu_page_hit(GAL_ARROWS_Y, mx, my) == 1 && page > 0) {
                    page--; sel = 0; gallery_draw_grid(page, sel, focus_on_back); hal_mouse_draw_cursor_force(); continue;
                }
                if (menu_page_hit(GAL_ARROWS_Y, mx, my) == 2 && page < total_pages - 1) {
                    page++; sel = 0; gallery_draw_grid(page, sel, focus_on_back); hal_mouse_draw_cursor_force(); continue;
                }
                for (i = 0; i < GAL_CELLS; i++) {
                    int gx, gy;
                    if (page * GAL_CELLS + i >= CG_COUNT) break;
                    gallery_cell_xy(i, &gx, &gy);
                    if (mx >= gx && mx < gx + GAL_CELL_W && my >= gy && my < gy + GAL_CELL_H) {
                        sel = i; focus_on_back = 0;
                        if (gallery_preview(page * GAL_CELLS + i)) { view = GAL_VIEW_CG; continue; }
                    }
                }
            }
        } else {   /* GAL_VIEW_CG: fullscreen preview */
            hal_mouse_update();
            if (hal_kbd_is_down(KC_ESC) || hal_kbd_is_down(KC_SPACE) ||
                hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_XFER) ||
                hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
                gallery_exit_preview(page, sel, focus_on_back);
                view = GAL_VIEW_GRID;
                continue;
            }
        }

        if (view == GAL_VIEW_GRID && (sel != prev_sel || focus_on_back != prev_fb))
            gallery_draw_cells_range(page, prev_sel, sel, focus_on_back);

        hal_mouse_draw_cursor();
    }

    menu_finish();
    gallery_palette_restore();
    gallery_return_home();
}
