/*
 * nb_special.c — Special menu (LOAD-style full-screen list).
 *
 * Sub-menu reached from the main menu ("special" button).  Rendered with the
 * same layout / behaviour / display conventions as the save-load slot menu
 * (nb_saveload.c): a full-screen fixed layout with embossed list rows, page
 * navigation, a bottom-left Back button and the focus_on_back model.  Up to
 * SPECIAL_ROWS entries share one page; pagination mirrors the load menu so
 * the list can grow later without a UI change.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "vm.h"
#include "render.h"
#include "ui.h"
#include "scene_layers.h"
#include "menu_layer.h"
#include "hal.h"
#include "nb_internal.h"
#include "nb_commands.h"
#include "nb_saveload.h"
#include "nb.h"
#include "tr.h"
#include "debug.h"

#define SPECIAL_ROWS 4

/* Entry buttons: half-width (240) row centered on screen; the focus '>'
 * indicator sits at the button's inner left edge and the label is centered. */
#define SPECIAL_BTN_X  200
#define SPECIAL_BTN_W  240
#define SPECIAL_LABEL_LX 206

/* Row Y coordinates (SPECIAL_ROWS rows, mirroring the load menu slots). */
static const int special_row_y[SPECIAL_ROWS] = { 90, 146, 202, 258 };

/* Number of entries visible on 'page' (clamped to [1, SPECIAL_ROWS]). */
static int special_rows_on_page(int argc, int page)
{
    int n = argc - page * SPECIAL_ROWS;
    if (n > SPECIAL_ROWS) n = SPECIAL_ROWS;
    if (n < 1) n = 1;
    return n;
}

/* Single-source-of-truth draw: full pass (entry / page change) repaints the
 * title, emboss rows, pager and Back border; incremental passes relabel rows
 * and the Back label only (AGENTS.md §14 two-stage menu rendering). */
static void special_draw(int argc, const char **argv, int page, int sel,
                         int focus_on_back, int total_pages, int full)
{
    int i;

    menu_layer_begin_draw();
    if (full) {
        const char *title = tr("SPECIAL");
        vblank_wait();
        draw_title_large(title, (LAYER_SCREEN_W - text_title_width(title, 4)) / 2,
                         28, 4, PAL_WHITE);
        for (i = 0; i < special_rows_on_page(argc, page); i++)
            draw_rounded_emboss(SPECIAL_BTN_X, special_row_y[i], SPECIAL_BTN_W, 44,
                                SAVE_SLOT_R, BTN_FILL_IDX, BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX);
        /* Conditional UI elements (pager arrows/counter) repainted every full
         * pass so nothing lingers as ghosts across page changes. */
        menu_pagenav_draw(318, 330, PAL_WHITE, page, total_pages);
        menu_back_draw(352, focus_on_back, 1, PAL_WHITE);
    }

    /* Entry text (label centered in its button; focus row: '>' + yellow). */
    for (i = 0; i < special_rows_on_page(argc, page); i++) {
        int abs = page * SPECIAL_ROWS + i, y = special_row_y[i];
        const char *label = tr(argv[abs]);
        int lw = text_width(label, 0);
        int lx = SPECIAL_BTN_X + (SPECIAL_BTN_W - lw) / 2;
        if (lx < SPECIAL_BTN_X) lx = SPECIAL_BTN_X;
        fill_rect(SPECIAL_LABEL_LX, y + 2, 12, 40, BTN_FILL_IDX);
        if (!focus_on_back && i == sel) {
            draw_text(">", 0, SPECIAL_LABEL_LX, y + 14,
                      SPECIAL_LABEL_LX + 12, y + 36, 1, MENU_PAL_YELLOW);
            draw_text(label, 0, lx, y + 14, SPECIAL_BTN_X + SPECIAL_BTN_W,
                      y + 36, 1, MENU_PAL_YELLOW);
        } else {
            draw_text(label, 0, lx, y + 14, SPECIAL_BTN_X + SPECIAL_BTN_W,
                      y + 36, 0, PAL_WHITE);
        }
    }

    /* Back button: only the label on incremental redraws (emboss repainted
     * by the full draw above). */
    menu_back_draw(352, focus_on_back, 0, PAL_WHITE);

    menu_layer_commit();
    menu_layer_blit();
}

static void special_route(int sel_key, const char *key)
{
    if (strcmp(key, "gallery") == 0) {
        nb_set_menu_return("special.nb");
        scene_switch("cgview.nb", SCENE_SWITCH_MENU);
    } else if (strcmp(key, "scenes") == 0) {
        save_request(SAVE_OP_CAPTURE_TEMP, -1);
        save_request(SAVE_OP_OPEN_LOAD, -1);
    } else if (strcmp(key, "music") == 0) {
        hal_log("TODO: music room\r\n");
    } else {
        NB_DEBUG("specialmenu: unknown entry '%s' (idx %d)\r\n", key, sel_key);
    }
}

/* specialmenu <entry1> <entry2> ... — full-screen LOAD-style list. */
void cmd_specialmenu(int argc, const char **argv, const char *cmd_name)
{
    int page = 0, sel = 0, focus_on_back = 0, running = 1, total_pages;
    int sel_key = -1, back_to_main = 0;

    (void)cmd_name;
    if (argc < 1) { NB_DEBUG("specialmenu: no entries\r\n"); return; }
    if (argc > NB_ARGS_MAX) {
        NB_DEBUG("WARN: specialmenu args=%d exceeds NB_ARGS_MAX (%d), truncated\r\n",
                 argc, NB_ARGS_MAX);
        argc = NB_ARGS_MAX;
    }

    total_pages = menu_pagecount(argc, SPECIAL_ROWS);

    menu_save_item_palette();
    hal_kbd_drain_advance();

    hal_mouse_erase_cursor();
    menu_layer_open(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
    special_draw(argc, argv, page, sel, focus_on_back, total_pages, 1);
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    hal_mouse_draw_cursor_force();

    while (running) {
        int abs = page * SPECIAL_ROWS + sel;
        int prev_sel = sel, prev_focus = focus_on_back;

        hal_kbd_update();

        if (focus_on_back) {
            if (hal_kbd_is_down(KC_UP)) {
                focus_on_back = 0;
                sel = special_rows_on_page(argc, page) - 1;
            } else if (hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_SPACE) ||
                       hal_kbd_is_down(KC_XFER)) {
                back_to_main = 1; running = 0; break;
            }
        } else {
            if (hal_kbd_is_down(KC_UP) && sel > 0) {
                sel--;
            } else if (hal_kbd_is_down(KC_DOWN)) {
                if (sel >= special_rows_on_page(argc, page) - 1)
                    focus_on_back = 1;
                else
                    sel++;
            } else if (hal_kbd_is_down(KC_LEFT) && page > 0) {
                page--; sel = 0;
                special_draw(argc, argv, page, sel, focus_on_back, total_pages, 1);
                hal_mouse_draw_cursor_force();
                continue;
            } else if (hal_kbd_is_down(KC_RIGHT) && page < total_pages - 1) {
                page++; sel = 0;
                special_draw(argc, argv, page, sel, focus_on_back, total_pages, 1);
                hal_mouse_draw_cursor_force();
                continue;
            } else if (hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_SPACE) ||
                       hal_kbd_is_down(KC_XFER)) {
                sel_key = abs; running = 0; break;
            }
        }
        if (hal_kbd_is_down(KC_ESC)) {
            back_to_main = 1; running = 0; break;
        }

        hal_mouse_update();
        hal_mouse_recenter_if_idle();

        { /* mouse input */
            int mx, my;
            if (hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
                int i;
                mx = hal_mouse_get_x();
                my = hal_mouse_get_y();
                /* Back button */
                if (menu_back_hit(352, mx, my)) {
                    back_to_main = 1; running = 0; break;
                }
                /* Page prev / next */
                if (menu_page_hit(318, mx, my) == 1 && page > 0) {
                    page--; sel = 0;
                    special_draw(argc, argv, page, sel, focus_on_back, total_pages, 1);
                    hal_mouse_draw_cursor_force();
                    continue;
                }
                if (menu_page_hit(318, mx, my) == 2 && page < total_pages - 1) {
                    page++; sel = 0;
                    special_draw(argc, argv, page, sel, focus_on_back, total_pages, 1);
                    hal_mouse_draw_cursor_force();
                    continue;
                }
                /* Entry selection */
                if (mx >= SPECIAL_BTN_X && mx < SPECIAL_BTN_X + SPECIAL_BTN_W &&
                    my >= special_row_y[0] && my < special_row_y[SPECIAL_ROWS - 1] + 44) {
                    int rows = special_rows_on_page(argc, page);
                    for (i = 0; i < rows; i++) {
                        if (my >= special_row_y[i] && my < special_row_y[i] + 44) {
                            sel = i; focus_on_back = 0;
                            sel_key = page * SPECIAL_ROWS + sel;
                            running = 0;
                            break;
                        }
                    }
                    continue;
                }
            }
        }

        if (sel != prev_sel || focus_on_back != prev_focus)
            special_draw(argc, argv, page, sel, focus_on_back, total_pages, 0);

        hal_mouse_draw_cursor();
    }
    menu_finish();

    if (back_to_main)
        scene_switch("mainmenu.nb", SCENE_SWITCH_MENU);
    else if (sel_key >= 0 && sel_key < argc)
        special_route(sel_key, argv[sel_key]);
}
