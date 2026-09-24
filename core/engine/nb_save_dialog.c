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
#include "tr.h"
#include "strutil.h"

/* Save dialog menu: in-place UI within dialog area. */
static void save_dlg_draw_slots(int row, int col);
static void save_dlg_draw_confirm(int slot, int yes);

/* Grid: 3 rows x 6 cols; row 2 is the Back out-row.  Wrap a 3-row hop in
 * {-1, +1}, and a 6-col wrap (used only on the slot rows). */
static int save_dlg_row_hop(int row, int inc)
{
    row += inc;
    if (row >= 3) row = 0;
    else if (row < 0) row = 2;
    return row;
}

static int save_dlg_col_wrap(int col, int inc)
{
    int nc = (col + inc) % 6;
    if (nc < 0) nc += 6;
    return nc;
}

/* Hit-test the slot grid area from mouse coords.  Returns 1 when the click
 * falls inside the dialog content band, filling the row (0..2+, row 2 = Back)
 * and clamped col (0..5). */
static int save_dlg_slot_hit(int mx, int my, int *row, int *col)
{
    int r, c;
    if (my < LAYER_DIALOG_CONTENT_Y ||
        my >= LAYER_DIALOG_Y + LAYER_DIALOG_H - LAYER_DIALOG_BORDER)
        return 0;
    if (mx < LAYER_DIALOG_CONTENT_X ||
        mx >= LAYER_DIALOG_X + LAYER_DIALOG_W - LAYER_DIALOG_RIGHT_INDENT)
        return 0;
    r = (my - LAYER_DIALOG_CONTENT_Y) / 20;
    c = (mx - LAYER_DIALOG_CONTENT_X) / (LAYER_DIALOG_CONTENT_W / 6);
    if (c < 0) c = 0;
    if (c > 5) c = 5;
    *row = r;
    *col = c;
    return 1;
}

/* Confirm-mode action: overwrite the slot, then leave the dialog. */
static int save_dlg_confirm_action(int slot)
{
    save_request(SAVE_OP_SLOT_SAVE, slot);
    return 1;
}

/* Confirm geometry for the in-dialog save prompt ([Yes]/[No] text buttons). */
static const MenuConfirmCfg g_dlg_confirm_cfg = {
    .yes_x0 = LAYER_DIALOG_CONTENT_X + 80,
    .no_x0 = LAYER_DIALOG_CONTENT_X + 200,
    .y0 = LAYER_DIALOG_CONTENT_Y + 60,
    .y1 = LAYER_DIALOG_CONTENT_Y + 80,
    .mouse_yes_always = 1,
    .action = save_dlg_confirm_action
};

/* Draw the dialog "SAVE" header line (shared by the slot grid and the
 * confirm overlay, which both repaint the full dialog content area). */
static void save_dlg_draw_header(void)
{
    draw_text(tr("SAVE"), 0, LAYER_DIALOG_CONTENT_X,
              LAYER_DIALOG_Y + LAYER_DIALOG_HEADER_Y,
              LAYER_DIALOG_CONTENT_X + LAYER_DIALOG_CONTENT_W,
              LAYER_DIALOG_Y + LAYER_DIALOG_HEADER_Y + 20,
              0, PAL_WHITE);
}

void save_dialog_menu(void)
{
    char saved_charname[64];
    char saved_text[1024];
    int saved_offset;
    int has_text = 0;
    int row = 0, col = 0;
    int confirm = 0, confirm_yes = 1, running = 1;
    int sel_slot = 0;
    int prev_row, prev_col;

    /* Save dialog text state */
    if (nb_dialog_get_charname()) {
        str_copy(saved_charname, sizeof(saved_charname), nb_dialog_get_charname());
    } else {
        saved_charname[0] = '\0';
    }
    {
        const char *txt = nb_dialog_get_text();
        if (txt && txt[0]) {
            str_copy(saved_text, sizeof(saved_text), txt);
            has_text = 1;
        } else {
            saved_text[0] = '\0';
        }
    }
    saved_offset = nb_dialog_get_offset();

    /* Use a clean dialog box (no story text) as the menu backdrop. */
    hal_mouse_erase_cursor();
    layer_dialog_clear();

    menu_save_item_palette();
    hal_kbd_drain_advance();

    save_dlg_draw_header();

    save_dlg_draw_slots(row, col);
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    hal_mouse_draw_cursor_force();

    while (running) {
        prev_row = row; prev_col = col;

        hal_kbd_update();

        if (confirm) {
            int r = menu_confirm_input(&confirm_yes, sel_slot, &g_dlg_confirm_cfg);
            if (r == MENU_CONFIRM_TOGGLE) {
                save_dlg_draw_confirm(sel_slot, confirm_yes);
                hal_mouse_draw_cursor_force();
            } else if (r == MENU_CONFIRM_CLOSED) {
                confirm = 0; confirm_yes = 1;
                save_dlg_draw_slots(row, col);
                hal_mouse_draw_cursor_force();
            } else if (r == MENU_CONFIRM_EXIT) {
                running = 0; break;
            }
            hal_mouse_draw_cursor();
            continue;
        } else {
            if (hal_kbd_is_down(KC_UP)) {
                row = save_dlg_row_hop(row, -1);
            } else if (hal_kbd_is_down(KC_DOWN)) {
                row = save_dlg_row_hop(row, 1);
            } else if (hal_kbd_is_down(KC_LEFT)) {
                if (row < 2) col = save_dlg_col_wrap(col, -1);
            } else if (hal_kbd_is_down(KC_RIGHT)) {
                if (row < 2) col = save_dlg_col_wrap(col, 1);
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

        /* Mouse input (list mode only — confirm mode is handled above) */
        if (hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
            int mx = hal_mouse_get_x(), my = hal_mouse_get_y();
            int click_row, click_col;
            if (save_dlg_slot_hit(mx, my, &click_row, &click_col)) {
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

        if (row != prev_row || col != prev_col)
            save_dlg_draw_slots(row, col);

        hal_mouse_draw_cursor();
    }

    menu_restore_item_palette();
    hal_mouse_erase_cursor();

    /* Rebuild the dialog composite (box repaint clears the menu overlay and
     * any stale in-buffer text), then render the saved text into the buffer
     * and blit once — the dialog composite is the persistent layer (devdoc
     * 96), the save menu was a transient VRAM overlay. */
    layer_dialog_show();
    if (has_text) {
        int draw_off = (saved_offset >= 0) ? saved_offset : 0;
        layer_dialog_render_page(saved_charname, saved_text, draw_off);
        dialog_layer_store_render(saved_charname, saved_text, draw_off);
        dialog_layer_blit();
    } else {
        dialog_layer_blit();
    }
}

static void save_dlg_draw_slots(int row, int col)
{
    int r, c;
    int content_x = LAYER_DIALOG_CONTENT_X;
    int content_y = LAYER_DIALOG_CONTENT_Y;
    int content_w = LAYER_DIALOG_CONTENT_W;
    int content_h = LAYER_DIALOG_CONTENT_H;
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
        draw_text(tr("Back"), 0, content_x + 200, by, content_x + 256, by + 20, 0, clr);
    }
}

static void save_dlg_draw_confirm(int slot, int yes)
{
    char buf[128];
    SlotInfo si;
    int content_x = LAYER_DIALOG_CONTENT_X;
    int content_y = LAYER_DIALOG_CONTENT_Y;
    int content_w = LAYER_DIALOG_CONTENT_W;
    int content_h = LAYER_DIALOG_CONTENT_H;

    hal_mouse_erase_cursor();
    layer_dialog_clear();
    save_dlg_draw_header();

    snprintf(buf, sizeof(buf), tr("Overwrite Slot %d?"), slot + 1);
    draw_text(buf, 0, content_x + 4, content_y, content_x + content_w, content_y + 20, 0, PAL_WHITE);

    slot_info(slot, &si);
    if (si.exists) {
        const char *label = slot_chapter_label(&si);
        draw_text(label, 0, content_x + 4, content_y + 20,
                  content_x + content_w, content_y + 40, 0, PAL_WHITE);
        draw_text(si.timestamp, 0, content_x + 4, content_y + 40,
                  content_x + content_w, content_y + 60, 0, PAL_WHITE);
    }

    /* Yes / No */
    draw_text(tr("[Yes]"), 0, content_x + 80, content_y + 60,
              content_x + 140, content_y + 80, 0, yes ? MENU_PAL_YELLOW : PAL_WHITE);
    draw_text(tr("[No]"), 0, content_x + 200, content_y + 60,
              content_x + 260, content_y + 80, 0, yes ? PAL_WHITE : MENU_PAL_YELLOW);
}
