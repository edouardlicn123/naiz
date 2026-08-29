/*
 * nb_save_dialog.c — In-dialog save menu.
 *
 * Split from nb_saveload.c: independent UI within the dialog area.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "render.h"
#include "ui.h"
#include "scene_layers.h"
#include "hal.h"
#include "nb_internal.h"
#include "nb_saveload.h"
#include "nb_dialog.h"
#include "save.h"

/* Save dialog menu: in-place UI within dialog area. */
static void save_dlg_draw_slots(int row, int col);
static void save_dlg_draw_confirm(int slot, int yes);

void save_dialog_menu(void)
{
    char saved_charname[64];
    char saved_text[1024];
    int saved_offset;
    int has_text = 0;
    int row = 0, col = 0;
    int confirm = 0, confirm_yes = 1, running = 1;
    int sel_slot = 0;
    int slot_start_x = LAYER_DIALOG_X + LAYER_DIALOG_INDENT;
    int prev_row, prev_col, prev_cyes;
    SlotInfo si;
    char buf[128];

    /* Save dialog text state */
    if (nb_dialog_get_charname()) {
        strncpy(saved_charname, nb_dialog_get_charname(), sizeof(saved_charname) - 1);
        saved_charname[sizeof(saved_charname) - 1] = '\0';
    } else {
        saved_charname[0] = '\0';
    }
    {
        const char *txt = nb_dialog_get_text();
        if (txt && txt[0]) {
            strncpy(saved_text, txt, sizeof(saved_text) - 1);
            saved_text[sizeof(saved_text) - 1] = '\0';
            has_text = 1;
        } else {
            saved_text[0] = '\0';
        }
    }
    saved_offset = nb_dialog_get_offset();

    /* Restore clean dialog snapshot (no text, correct pattern/solid style) */
    hal_mouse_erase_cursor();
    layer_dialog_restore();

    menu_save_item_palette();
    hal_kbd_drain_advance();

    {
        int content_x = LAYER_DIALOG_X + LAYER_DIALOG_INDENT;
        int content_w = LAYER_DIALOG_W - LAYER_DIALOG_INDENT - LAYER_DIALOG_RIGHT_INDENT;
        draw_text("SAVE", 0, content_x, LAYER_DIALOG_Y + LAYER_DIALOG_HEADER_Y,
                  content_x + content_w, LAYER_DIALOG_Y + LAYER_DIALOG_HEADER_Y + 20,
                  0, PAL_WHITE);
    }

    save_dlg_draw_slots(row, col);
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    hal_mouse_draw_cursor_force();

    while (running) {
        prev_row = row; prev_col = col; prev_cyes = confirm_yes;

        hal_kbd_update();

        if (confirm) {
            if (hal_kbd_is_down(KC_LEFT) || hal_kbd_is_down(KC_RIGHT))
                confirm_yes = !confirm_yes;
            if (hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_SPACE) || hal_kbd_is_down(KC_XFER)) {
                if (confirm_yes) {
                    save_game_slot(sel_slot);
                    running = 0; break;
                }
                confirm = 0; confirm_yes = 1;
                save_dlg_draw_slots(row, col);
                hal_mouse_draw_cursor_force();
                continue;
            }
            if (hal_kbd_is_down(KC_ESC)) {
                confirm = 0; confirm_yes = 1;
                save_dlg_draw_slots(row, col);
                hal_mouse_draw_cursor_force();
                continue;
            }
        } else {
            if (hal_kbd_is_down(KC_UP)) {
                row = (row == 2) ? 1 : (row == 1 ? 0 : 2);
            } else if (hal_kbd_is_down(KC_DOWN)) {
                row = (row == 2) ? 0 : (row == 1 ? 2 : 1);
            } else if (hal_kbd_is_down(KC_LEFT)) {
                if (row < 2) col = (col + 5) % 6;
            } else if (hal_kbd_is_down(KC_RIGHT)) {
                if (row < 2) col = (col + 1) % 6;
            } else if (hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_SPACE) || hal_kbd_is_down(KC_XFER)) {
                if (row == 2) { running = 0; break; }
                sel_slot = row * 6 + col;
                confirm = 1; confirm_yes = 1;
                save_dlg_draw_confirm(sel_slot, confirm_yes);
                hal_mouse_draw_cursor_force();
                continue;
            } else if (hal_kbd_is_down(KC_ESC)) {
                running = 0; break;
            }
        }

        hal_mouse_update();
        hal_mouse_recenter_if_idle();

        /* Mouse input */
        {
            int mx, my;
            if (hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
                mx = hal_mouse_get_x();
                my = hal_mouse_get_y();
                if (my >= LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y && my < LAYER_DIALOG_Y + LAYER_DIALOG_H - LAYER_DIALOG_BORDER &&
                    mx >= slot_start_x && mx < LAYER_DIALOG_X + LAYER_DIALOG_W - LAYER_DIALOG_RIGHT_INDENT) {
                    int rel_y = my - (LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y);
                    int click_row = rel_y / 20;
                    int click_col = (mx - slot_start_x) / ((LAYER_DIALOG_W - LAYER_DIALOG_INDENT - LAYER_DIALOG_RIGHT_INDENT) / 6);
                    if (click_col < 0) click_col = 0;
                    if (click_col > 5) click_col = 5;
                    if (confirm) {
                        int dlg_cx = LAYER_DIALOG_X + LAYER_DIALOG_INDENT;
                        int dlg_cy = LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y;
                        int btn_y0 = dlg_cy + 60;
                        int btn_y1 = dlg_cy + 80;
                        if (my >= btn_y0 && my < btn_y1) {
                            if (mx >= dlg_cx + 80 && mx < dlg_cx + 140) {
                                save_game_slot(sel_slot);
                                running = 0; break;
                            }
                            if (mx >= dlg_cx + 200 && mx < dlg_cx + 260) {
                                confirm = 0; confirm_yes = 1;
                                save_dlg_draw_slots(row, col);
                                hal_mouse_draw_cursor_force();
                                continue;
                            }
                        }
                    } else {
                        if (click_row == 2) { running = 0; break; }
                        else if (click_row < 2) {
                            row = click_row; col = click_col;
                            sel_slot = row * 6 + col;
                            confirm = 1; confirm_yes = 1;
                            save_dlg_draw_confirm(sel_slot, confirm_yes);
                            hal_mouse_draw_cursor_force();
                            continue;
                        }
                    }
                }
            }
        }

        if (confirm) {
            if (confirm_yes != prev_cyes) {
                save_dlg_draw_confirm(sel_slot, confirm_yes);
            }
        } else {
            if (row != prev_row || col != prev_col) {
                save_dlg_draw_slots(row, col);
            }
        }

        hal_mouse_draw_cursor();
    }

    menu_restore_item_palette();
    hal_mouse_erase_cursor();

    /* Restore clean dialog snapshot, then redraw saved text */
    {
        int cx = LAYER_DIALOG_X + LAYER_DIALOG_INDENT;
        int cw = LAYER_DIALOG_W - LAYER_DIALOG_INDENT - LAYER_DIALOG_RIGHT_INDENT;
        layer_dialog_restore();
        if (has_text) {
            if (saved_charname[0])
                draw_text(saved_charname, 0,
                          cx, LAYER_DIALOG_Y + LAYER_DIALOG_HEADER_Y,
                          cw, LAYER_DIALOG_BOTTOM, 1, PAL_WHITE);
            {
                int draw_off = (saved_offset >= 0) ? saved_offset : 0;
                draw_text(saved_text, draw_off,
                          cx, LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y,
                          cw, LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y + 60, 0, PAL_WHITE);
            }
        }
    }
}

static void save_dlg_draw_slots(int row, int col)
{
    int r, c;
    int content_x = LAYER_DIALOG_X + LAYER_DIALOG_INDENT;
    int content_y = LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y;
    int content_w = LAYER_DIALOG_W - LAYER_DIALOG_INDENT - LAYER_DIALOG_RIGHT_INDENT;
    int content_h = LAYER_DIALOG_H - LAYER_DIALOG_TEXT_Y - LAYER_DIALOG_BORDER;
    int slot_w = content_w / 6;
    char buf[16];

    fill_dialog_bg(content_x, content_y, content_w, content_h);
    for (r = 0; r < 2; r++) {
        for (c = 0; c < 6; c++) {
            int sn = r * 6 + c + 1;
            int sx = content_x + c * slot_w;
            int sy = content_y + r * 20;
            uint8_t clr = (r == row && c == col) ? MENU_PAL_YELLOW : PAL_WHITE;
            snprintf(buf, sizeof(buf), "%2d", sn);
            draw_text(buf, 0, sx + 4, sy, sx + slot_w - 4, sy + 20, 0, clr);
        }
    }
    {
        int by = content_y + 40;
        uint8_t clr = (row == 2) ? MENU_PAL_YELLOW : PAL_WHITE;
        draw_text("Back", 0, content_x + 200, by, content_x + 256, by + 20, 0, clr);
    }
}

static void save_dlg_draw_confirm(int slot, int yes)
{
    char buf[128];
    SlotInfo si;
    int content_x = LAYER_DIALOG_X + LAYER_DIALOG_INDENT;
    int content_y = LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y;
    int content_w = LAYER_DIALOG_W - LAYER_DIALOG_INDENT - LAYER_DIALOG_RIGHT_INDENT;
    int content_h = LAYER_DIALOG_H - LAYER_DIALOG_TEXT_Y - LAYER_DIALOG_BORDER;

    hal_mouse_erase_cursor();
    layer_dialog_restore();
    draw_text("SAVE", 0, content_x, LAYER_DIALOG_Y + LAYER_DIALOG_HEADER_Y,
              content_x + content_w, LAYER_DIALOG_Y + LAYER_DIALOG_HEADER_Y + 20,
              0, PAL_WHITE);

    snprintf(buf, sizeof(buf), "Overwrite Slot %d?", slot + 1);
    draw_text(buf, 0, content_x + 4, content_y, content_x + content_w, content_y + 20, 0, PAL_WHITE);

    slot_info(slot, &si);
    if (si.exists) {
        const char *label = si.chapter_title[0] ? si.chapter_title : si.filename;
        draw_text(label, 0, content_x + 4, content_y + 20,
                  content_x + content_w, content_y + 40, 0, PAL_WHITE);
        draw_text(si.timestamp, 0, content_x + 4, content_y + 40,
                  content_x + content_w, content_y + 60, 0, PAL_WHITE);
    }

    /* Yes / No */
    draw_text("[Yes]", 0, content_x + 80, content_y + 60,
              content_x + 140, content_y + 80, 0, yes ? MENU_PAL_YELLOW : PAL_WHITE);
    draw_text("[No]", 0, content_x + 200, content_y + 60,
              content_x + 260, content_y + 80, 0, yes ? PAL_WHITE : MENU_PAL_YELLOW);
}
