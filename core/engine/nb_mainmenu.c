/*
 * nb_mainmenu.c — NB main-menu flow commands.
 *
 * Split from nb_commands.c: the main-menu command (continue/load/start
 * routing) and its placeholder menu stubs form a distinct feature track.
 * Registered in nb_commands.c cmd_table.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "vm.h"
#include "render.h"
#include "nb_internal.h"
#include "nb_commands.h"
#include "nb_vars.h"
#include "save.h"
#include "nb.h"
#include "debug.h"
#include "cjk.h"
#include "settings.h"
#include "tr.h"
#include "image.h"
#include "scene_layers.h"
#include "ui.h"
#include "nb_asset_table.h"

void cmd_mainmenu(int argc, const char **argv, const char *cmd_name)
{
    int mx, my, mw, sel;

    (void)cmd_name;
    if (argc < 5) { NB_DEBUG("mainmenu: not enough args (need x,y,w,h,opt...)\r\n"); return; }
    if (argc > NB_ARGS_MAX) {
        NB_DEBUG("WARN: mainmenu args=%d exceeds NB_ARGS_MAX (%d), truncated\r\n", argc, NB_ARGS_MAX);
        argc = NB_ARGS_MAX;
    }

    mx = atoi(argv[0]);
    my = atoi(argv[1]);
    mw = atoi(argv[2]);
    if (mw < 1) mw = 1;
    if (mx < 0 || mx >= LAYER_SCREEN_W || my < 0 || my >= LAYER_SCREEN_H) {
        NB_DEBUG("WARN: mainmenu coords (%d,%d) out of range, defaulting\r\n", mx, my);
        mx = 400; my = 200;
    }
    NB_DEBUG("mainmenu: pos=(%d,%d) cols=%d %d items argc=%d\r\n", mx, my, mw, argc - 4, argc);

    sel = menu_show(mx, my, mw, argc - 4, argv + 4);
    if (sel < 0 || sel >= argc - 4) return;
    NB_DEBUG("mainmenu: selected=%d (%s)\r\n", sel, argv[sel + 4]);

    if (strcmp(argv[sel + 4], "continue") == 0) {
        int slot, best_slot = -1;
        char best_ts[20] = "";
        SlotInfo si;
        for (slot = 0; slot < SAVE_SLOTS; slot++) {
            slot_info(slot, &si);
            if (si.exists && strcmp(si.timestamp, best_ts) > 0) {
                best_slot = slot;
                strncpy(best_ts, si.timestamp, sizeof(best_ts) - 1);
                best_ts[sizeof(best_ts) - 1] = '\0';
            }
        }
        if (best_slot >= 0)
            load_game_slot(best_slot);
        else
            { nb_var_init(); nb_load("nbook001.nb"); }
    } else if (strcmp(argv[sel + 4], "load") == 0) {
        save_game_temp();
        nb_load("loadscene.nb");
    } else if (strcmp(argv[sel + 4], "start") == 0) {
        nb_var_init();
        nb_load("nbook001.nb");
    } else if (strcmp(argv[sel + 4], "scenes") == 0) {
        hal_log("TODO: scene select\r\n");
    } else if (strcmp(argv[sel + 4], "special") == 0) {
        hal_log("TODO: special menu\r\n");
    } else if (strcmp(argv[sel + 4], "music") == 0) {
        hal_log("TODO: music room\r\n");
    } else if (strcmp(argv[sel + 4], "gallery") == 0) {
        nb_load("cgview.nb");
    } else if (strcmp(argv[sel + 4], "settings") == 0) {
        hal_log("TODO: settings menu\r\n");
    } else if (strcmp(argv[sel + 4], "exit") == 0) {
        vm_set_finalend();
    }
}

void cmd_startsetting(int argc, const char **argv, const char *cmd_name)
{
    const char *old_lang;
    (void)argc; (void)argv; (void)cmd_name;

    old_lang = settings_get_lang();
    settings_menu_run();
    settings_save();

    if (strcmp(old_lang, settings_get_lang()) != 0) {
        cjk_load_for_lang(settings_get_lang());
        nb_set_lang(settings_get_lang());
        text_set_blackletter(settings_get_blackletter_dialog() && !nb_lang_is_cjk());
    }
}

void cmd_settingmenu(int argc, const char **argv, const char *cmd_name)
{
    (void)argc; (void)argv; (void)cmd_name;
    NB_DEBUG("settingmenu: not implemented yet\r\n");
}

/* =========================================================================
 * CG gallery grid menu (cmd_cgvmenu).
 *
 * Stage 5 (devdoc 92): full grid browsing + fullscreen preview + locked
 * placeholder cells.  Bridged from mainmenu via cgview.nb which ends here.
 * Layout: 4 cols x 3 rows, cell 144x100 at x=20/168/316/464, y=32/136/240.
 * ========================================================================= */

/* Cell grid geometry */
#define GAL_COLS        4
#define GAL_ROWS        3
#define GAL_CELLS       (GAL_COLS * GAL_ROWS)      /* 12 per page */
#define GAL_ORIGIN_X    20
#define GAL_ORIGIN_Y    32
#define GAL_CELL_W      144
#define GAL_CELL_H      100
#define GAL_STEP_X      148     /* cell 144 + 4 gap */
#define GAL_STEP_Y      104     /* cell 100 + 4 gap */

/* Gallery main-menu color indexes */
#define GAL_GRID_BORDER_SEL  7        /* PAL_WHITE: focused unlocked border */
#define GAL_GRID_BORDER      7        /* unlocked idle border */
#define GAL_BG_UNLOCKED      PAL_BLUE /* cell background when unlocked */
#define GAL_LOCK_FG_IDLE     7        /* [LOCKED] idle text */
#define GAL_LOCK_FG_SEL      15       /* [LOCKED] focused text */
#define GAL_LOCK_BORDER_IDLE 12       /* locked idle border */
#define GAL_LOCK_BORDER_SEL  15       /* locked focused border */

enum { GAL_VIEW_GRID = 0, GAL_VIEW_CG = 1 };

/* Map in-cell-index (0..11) to screen coordinates. */
static void gallery_cell_xy(int i, int *px, int *py)
{
    *px = GAL_ORIGIN_X + (i % GAL_COLS) * GAL_STEP_X;
    *py = GAL_ORIGIN_Y + (i / GAL_COLS) * GAL_STEP_Y;
}

/* Draw a single grid cell. abs_idx is the absolute CG index (0-based;
 * cg_id for the unlock flag is abs_idx+1 per the devdoc 89/92 contract). */
static void gallery_draw_cell(int abs_idx, int x, int y, int is_sel)
{
    char label[16];
    int unlocked = sys_save_is_cg_unlocked(abs_idx + 1);

    if (unlocked) {
        fill_rect(x, y, GAL_CELL_W, GAL_CELL_H, GAL_BG_UNLOCKED);
        snprintf(label, sizeof(label), "CG %02d", abs_idx + 1);
        draw_text(label, 0, x + 12, y + 10, x + GAL_CELL_W - 12, y + 26, 1, PAL_WHITE);
        draw_rect(x, y, GAL_CELL_W, GAL_CELL_H, 1, GAL_GRID_BORDER);
    } else {
        fill_rect(x, y, GAL_CELL_W, GAL_CELL_H, 0);
        draw_text("[LOCKED]", 0, x + 30, y + 42, x + GAL_CELL_W - 30, y + 58, 0,
                  is_sel ? GAL_LOCK_FG_SEL : GAL_LOCK_FG_IDLE);
        draw_rect(x, y, GAL_CELL_W, GAL_CELL_H, 1,
                  is_sel ? GAL_LOCK_BORDER_SEL : GAL_LOCK_BORDER_IDLE);
    }
}

/* Full redraw of the grid screen (title + cells + back + paging). */
static void gallery_draw_grid(int page, int sel, int focus_on_back)
{
    int total_pages = (CG_COUNT + GAL_CELLS - 1) / GAL_CELLS;
    int page_start = page * GAL_CELLS;
    char buf[32];
    int i;

    vblank_wait();
    fill_rect(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
    draw_title_large("CG GALLERY", 20, 12, 3, PAL_WHITE);

    for (i = 0; i < GAL_CELLS; i++) {
        int abs_idx = page_start + i;
        int x, y;
        if (abs_idx >= CG_COUNT) break;
        gallery_cell_xy(i, &x, &y);
        gallery_draw_cell(abs_idx, x, y, (i == sel) && !focus_on_back);
    }

    draw_rounded_emboss(66, 356, 80, 30, 4, BTN_FILL_IDX, BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX);
    draw_text("Back", 0, 76, 363, 136, 379, 1, focus_on_back ? MENU_PAL_YELLOW : PAL_WHITE);

    if (page > 0)              draw_text("<", 0, 56, 370, 72, 386, 0, PAL_WHITE);
    if (page < total_pages - 1) draw_text(">", 0, 576, 370, 592, 386, 0, PAL_WHITE);
    snprintf(buf, sizeof(buf), "%d/%d", page + 1, total_pages);
    draw_text(buf, 0, 308, 370, 332, 386, 0, PAL_WHITE);
}

/* Incremental redraw: only the two cells whose focus changed (old de-emphasised,
 * new emphasised). Back button focus handled explicitly. from/to are in-cell idx. */
static void gallery_draw_cells_range(int page, int from_sel, int to_sel, int focus_on_back)
{
    int x, y, abs_idx;

    if (!focus_on_back) {
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
        draw_text("Back", 0, 76, 363, 136, 379, 1, MENU_PAL_YELLOW);
    }
}

/* Fullscreen preview of one CG. Returns 1 on success (with focus held). */
static int gallery_preview(int abs_idx)
{
    MagImage *img;

    if (!sys_save_is_cg_unlocked(abs_idx + 1)) {
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
    layer_bg_change(img);
    mag_release(img);          /* snapshot already captured by layer_bg_change */
    hal_mouse_draw_cursor_force();
    return 1;
}

/* Exit preview: restore bg asset then redraw the grid. */
static void gallery_exit_preview(int page, int sel, int focus_on_back)
{
    MagImage *bg = image_load((unsigned short)nb_asset_id("yellow_grid"));
    hal_mouse_erase_cursor();
    if (bg) {
        layer_bg_change(bg);
        mag_release(bg);
    } else {
        fill_rect(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
    }
    gallery_draw_grid(page, sel, focus_on_back);
    hal_mouse_draw_cursor_force();
}

/* cmd_cgvmenu — CG gallery browsing menu (bridging script cgview.nb ends). */
void cmd_cgvmenu(int argc, const char **argv, const char *cmd_name)
{
    int running = 1, total_pages, page = 0, sel = 0, focus_on_back = 0, view = GAL_VIEW_GRID;
    (void)argc; (void)argv; (void)cmd_name;

    if (CG_COUNT == 0) {
        NB_DEBUG("cgvmenu: CG_COUNT=0, empty gallery\r\n");
        hal_kbd_drain_advance();
        hal_mouse_erase_cursor();
        draw_text("No CGs available.", 0, 200, 190, 440, 210, 1, PAL_WHITE);
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
        nb_load("mainmenu.nb");
        return;
    }

    total_pages = (CG_COUNT + GAL_CELLS - 1) / GAL_CELLS;

    hal_kbd_drain_advance();
    hal_mouse_erase_cursor();
    menu_save_item_palette();
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
                    sel = (last_idx < GAL_CELLS - 1) ? last_idx : GAL_CELLS - 1;
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

                if (mx >= 66 && mx < 146 && my >= 356 && my < 386) { running = 0; continue; }
                if (mx >= 56 && mx < 72 && my >= 370 && my < 386 && page > 0) {
                    page--; sel = 0; gallery_draw_grid(page, sel, focus_on_back); hal_mouse_draw_cursor_force(); continue;
                }
                if (mx >= 576 && mx < 592 && my >= 370 && my < 386 && page < total_pages - 1) {
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

    menu_restore_item_palette();
    hal_mouse_flush();
    nb_load("mainmenu.nb");
}

void cmd_musicmenu(int argc, const char **argv, const char *cmd_name)
{
    (void)argc; (void)argv; (void)cmd_name;
    NB_DEBUG("musicmenu: not implemented yet\r\n");
}
