/*
 * nb_menu.c — NB menu UI: button rendering, palette save/restore, input loop.
 *
 * Split from nb.c (Phase 4 refactoring).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "render.h"
#include "ui.h"
#include "scene_layers.h"
#include "settings.h"

#include "hal.h"
#include "tr.h"
#include "font.h"
#include "nb_internal.h"

/*=== Debug ================================================================*/

#include "debug.h"

/*=== Palette ===============================================================*/

static uint8_t menu_pal_save[6];

void menu_save_item_palette(void)
{
    hal_read_palette(MENU_PAL_WHITE, &menu_pal_save[0], &menu_pal_save[1], &menu_pal_save[2]);
    hal_read_palette(MENU_PAL_YELLOW, &menu_pal_save[3], &menu_pal_save[4], &menu_pal_save[5]);
    hal_set_palette(MENU_PAL_WHITE, 0xFF, 0xFF, 0xFF);
    hal_set_palette(MENU_PAL_YELLOW, 0xFF, 0xFF, 0x00);
}

void menu_restore_item_palette(void)
{
    hal_set_palette(MENU_PAL_WHITE, menu_pal_save[0], menu_pal_save[1], menu_pal_save[2]);
    hal_set_palette(MENU_PAL_YELLOW, menu_pal_save[3], menu_pal_save[4], menu_pal_save[5]);
}

/*=== Button positioning ===================================================*/

static void btn_pos(int mx, int my, int cols, int i, const char *text,
                    int btn_w, int btn_h, int *px, int *py, int *tx, int *ty)
{
    int col = i % cols;
    int row = i / cols;
    if (strcmp(text, "exit") == 0) {
        *px = 10;
        *py = LAYER_SCREEN_H - btn_h - 10;
    } else {
        *px = mx + col * (btn_w + BTN_COL_GAP);
        *py = my + 8 + row * (btn_h + BTN_GAP);
    }
    *tx = *px + (btn_w - text_width(tr(text), 1)) / 2;
    if (*tx < *px) *tx = *px;
    *ty = *py + (btn_h - FONT_GLYPH_H) / 2;
}

/*=== Button drawing =======================================================*/

static void menu_draw_item(int mx, int my, int cols, int i, const char *text,
                           int btn_w, int btn_h, uint8_t fg)
{
    int px, py, tx, ty;
    btn_pos(mx, my, cols, i, text, btn_w, btn_h, &px, &py, &tx, &ty);
    draw_rounded_emboss(px, py, btn_w, btn_h, BTN_R,
                        BTN_FILL_IDX, BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX);
    draw_text(tr(text), 0, tx, ty, btn_w, py + btn_h, 1, fg);
}

static void menu_draw(int mx, int my, int cols, int btn_w, int btn_h,
                      int argc, const char **argv, int sel)
{
    int i;
    menu_save_item_palette();
    for (i = 0; i < argc; i++)
        menu_draw_item(mx, my, cols, i, argv[i], btn_w, btn_h,
                       (i == sel) ? MENU_PAL_YELLOW : MENU_PAL_WHITE);
}

/*=== Input helpers ========================================================*/

void menu_consume_key(uint8_t key)
{
    int timeout = HAL_KBD_WAIT_MAX_ITER / 20;
    while (hal_kbd_is_down(key) && --timeout > 0) hal_kbd_update();
}

static void menu_label_draw(int mx, int my, int cols, int btn_w, int btn_h,
                            int i, const char *text, uint8_t fg)
{
    int px, py, tx, ty;
    btn_pos(mx, my, cols, i, text, btn_w, btn_h, &px, &py, &tx, &ty);
    draw_text(tr(text), 0, tx, ty, btn_w, py + btn_h, 1, fg);
}

/*=== Hit testing ==========================================================*/

static int btn_hittest(int mx, int my, int cols, int argc, const char **argv,
                       int btn_w, int btn_h, int px, int py)
{
    int i;
    for (i = 0; i < argc; i++) {
        int bx, by, tx, ty;
        btn_pos(mx, my, cols, i, argv[i], btn_w, btn_h, &bx, &by, &tx, &ty);
        if (px >= bx && px < bx + btn_w && py >= by && py < by + btn_h)
            return i;
    }
    return -1;
}

/*=== Main input loop ======================================================*/

int menu_show(int mx, int my, int cols, int argc, const char **argv)
{
    int sel = 0;
    int prev_sel = 0;
    int btn_w = BTN_W;
    int btn_h = BTN_H;

#ifdef AUTOEXIT
    sel = argc - 1;
    menu_draw(mx, my, cols, btn_w, btn_h, argc, argv, sel);
    hal_log("[NB] menu auto-select exit\r\n");
    { volatile unsigned int d; for (d = 0; d < 200000; d++) {} }
    return sel;
#endif

    NB_DEBUG("menu: cols=%d pos=(%d,%d) wait...\r\n", cols, mx, my);
    NB_DEBUG("menu: pre_reset x=%d y=%d\r\n", hal_mouse_get_x(), hal_mouse_get_y());

    hal_kbd_drain_advance();
    hal_mouse_erase_cursor();
    menu_draw(mx, my, cols, btn_w, btn_h, argc, argv, sel);
    if (settings_get_version()[0])
        draw_text(settings_get_version(), 0, 544, 2, 96, 16, 0, PAL_RED);
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    hal_mouse_flush();

    for (;;) {
            hal_kbd_update();
            hal_mouse_update();

            if (hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
                int hit = btn_hittest(mx, my, cols, argc, argv, btn_w, btn_h,
                                      hal_mouse_get_x(), hal_mouse_get_y());
                if (hit >= 0) {
                    NB_DEBUG("menu: mouse sel=%d (%s)\r\n", hit, argv[hit]);
                    menu_restore_item_palette();
                    hal_mouse_flush();
                    return hit;
                }
            }

            /* Wrap last item back.  Safe for argc==1: the outer
             * sel>0 guard keeps us out when sel==0==argc-1. */
            if (hal_kbd_is_down(KC_UP) && sel > 0) {
                if (sel == argc - 1) {
                    prev_sel = sel;
                    sel = argc - 2;
                } else if (sel >= cols) {
                    prev_sel = sel;
                    sel -= cols;
                } else {
                    menu_consume_key(KC_UP);
                    continue;
                }
                menu_label_draw(mx, my, cols, btn_w, btn_h, sel, argv[sel], MENU_PAL_YELLOW);
                menu_label_draw(mx, my, cols, btn_w, btn_h, prev_sel, argv[prev_sel], MENU_PAL_WHITE);
                menu_consume_key(KC_UP);
            }
            if (hal_kbd_is_down(KC_DOWN) && sel < argc - 1) {
                /* sel < argc-1 guard: a 1-item menu never enters here, so
                 * argv access stays in-bounds (sel = argc-1 max). */
                if (sel + cols >= argc - 1) {
                    prev_sel = sel;
                    sel = argc - 1;
                } else {
                    prev_sel = sel;
                    sel += cols;
                }
                menu_label_draw(mx, my, cols, btn_w, btn_h, sel, argv[sel], MENU_PAL_YELLOW);
                menu_label_draw(mx, my, cols, btn_w, btn_h, prev_sel, argv[prev_sel], MENU_PAL_WHITE);
                menu_consume_key(KC_DOWN);
            }
            if (hal_kbd_is_down(KC_LEFT) && sel > 0) {
                int target = -1;
                if (sel == argc - 1) {
                    target = argc - 2;
                } else if (sel == ((argc - 2) / cols) * cols) {
                    target = argc - 1;
                } else if (sel < argc - 1 && (sel % cols) > 0) {
                    target = sel - 1;
                }
                /* target initialized to -1; only assigned a valid index or
                 * left invalid, so the target>=0 gate keeps argv[] in-bounds
                 * even for single-item menus (argc==1 never sets target). */
                if (target >= 0) {
                    prev_sel = sel;
                    sel = target;
                    menu_label_draw(mx, my, cols, btn_w, btn_h, sel, argv[sel], MENU_PAL_YELLOW);
                    menu_label_draw(mx, my, cols, btn_w, btn_h, prev_sel, argv[prev_sel], MENU_PAL_WHITE);
                    menu_consume_key(KC_LEFT);
                }
            }
            if (hal_kbd_is_down(KC_RIGHT)) {
                int target = -1;
                if (sel == argc - 1) {
                    target = argc - 2;
                } else if (sel < argc - 1 && (sel % cols) < cols - 1 && sel + 1 < argc - 1) {
                    target = sel + 1;
                }
                /* Same -1-sentinel pattern: rightmost/last items keep target
                 * invalid and skip redraw; no argv[-1] can be reached. */
                if (target >= 0) {
                    prev_sel = sel;
                    sel = target;
                    menu_label_draw(mx, my, cols, btn_w, btn_h, sel, argv[sel], MENU_PAL_YELLOW);
                    menu_label_draw(mx, my, cols, btn_w, btn_h, prev_sel, argv[prev_sel], MENU_PAL_WHITE);
                    menu_consume_key(KC_RIGHT);
                }
            }
            if (hal_kbd_is_down(KC_SPACE) || hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_XFER)) {
                NB_DEBUG("menu: keyboard sel=%d (%s)\r\n", sel, argv[sel]);
                menu_restore_item_palette();
                hal_mouse_flush();
                return sel;
            }

            hal_mouse_draw_cursor();
        }
}
