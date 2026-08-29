/*
 * nb_saveload.c — Save/load menu UIs (full-screen + in-dialog).
 *
 * Extracted from nb.c (encapsulation refactoring).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "vm.h"
#include "render.h"
#include "ui.h"
#include "scene_layers.h"
#include "settings.h"
#include "hal.h"
#include "nb_internal.h"
#include "nb_dialog.h"
#include "nb_commands.h"
#include "image.h"
#include "mag.h"
#include "save.h"

/* Debug logging — shared macro in debug.h */
#include "debug.h"

/* Shared save/load slot selection menu used by cmd_loadscene.
 * is_load=0 -> save mode, is_load=1 -> load mode.
 * from_mainmenu=1: Back/ESC exits via nb_load() (return to caller scene);
 * from_mainmenu=0: exits via load_game_temp() (restore temp save).
 * (All current callers pass from_mainmenu=0; kept as a parameter for
 *  future main-menu entry without a global.) */

/* Draw a transient error message to the VRAM overlay and wait for a keypress.
 * Returns with kbd drained for next input. */
static void show_error_msg(const char *msg, int x, int y)
{
    fill_rect(x, y, 120, 24, 0);
    draw_text(msg, 0, x + 10, y + 2, x + 110, y + 20, 1, MENU_PAL_YELLOW);
    hal_kbd_drain_advance();
    hal_kbd_wait_any();
    hal_kbd_drain_advance();
}

/* Draw save/load menu UI.  If full=1, draw all background elements (emboss
 * slots, page nav, Back button).  Always draws text labels (cheap text-only). */
static void save_load_draw(int is_load, int page, int slot_idx, int focus_on_back,
                           int confirm, int confirm_yes, int total_pages, int full)
{
    int i;
    char buf[128];
    SlotInfo si;
    static const int slot_y[4] = { 90, 146, 202, 258 };

    if (full) {
        vblank_wait();
        if (settings_get_blackletter_title() && !nb_lang_is_cjk()) {
            int tid = nb_asset_id(is_load ? "loadtitle" : "savetitle");
            MagImage *m = (tid >= 0) ? image_load((unsigned short)tid) : NULL;
            if (m) {
                /* Center the blackletter title over the old title spot. */
                int bx = (LAYER_SCREEN_W - m->width) / 2;
                int by = 28 + (32 - m->height) / 2;
                vram_blit_sprite(m, bx, by, PAL_TRANSPARENT, 0, 0);
                mag_release(m);
            } else {
                draw_title_large(is_load ? "LOAD" : "SAVE", 282, 28, 4, PAL_WHITE);
            }
        } else {
            draw_title_large(is_load ? "LOAD" : "SAVE", 282, 28, 4, PAL_WHITE);
        }
        for (i = 0; i < 4; i++) {
            int si_idx = page * 4 + i;
            if (si_idx >= SAVE_SLOTS) break;
            draw_rounded_emboss(80, slot_y[i], 480, 44, SAVE_SLOT_R,
                                BTN_FILL_IDX, BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX);
        }
        if (page > 0) draw_text("<", 0, 56, 318, 72, 334, 0, PAL_WHITE);
        if (page < total_pages - 1) draw_text(">", 0, 576, 318, 592, 334, 0, PAL_WHITE);
        snprintf(buf, sizeof(buf), "%d/%d", page + 1, total_pages);
        draw_text(buf, 0, 310, 330, 330, 344, 0, PAL_WHITE);
        draw_rounded_emboss(66, 352, 80, 30, 4,
                            BTN_FILL_IDX, BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX);
        if (confirm) {
            draw_rounded_emboss(250, 370, 60, 22, 2,
                                BTN_FILL_IDX, BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX);
            draw_rounded_emboss(330, 370, 60, 22, 2,
                                BTN_FILL_IDX, BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX);
        }
    }

    /* Slot text (always drawn — cheap text-only) */
    for (i = 0; i < 4; i++) {
        int si_idx = page * 4 + i, y = slot_y[i];
        if (si_idx >= SAVE_SLOTS) break;
        slot_info(si_idx, &si);
        fill_rect(86, y + 2, 12, 40, BTN_FILL_IDX);
        if (si.exists) {
            const char *chapter = si.chapter_title[0] ? si.chapter_title : si.filename;
            snprintf(buf, sizeof(buf), "%.31s \xe2\x80\x94 %.63s \xe2\x80\x94 %.19s", si.slot_name, chapter, si.timestamp);
        } else {
            snprintf(buf, sizeof(buf), "%s \xe2\x80\x94 (Empty)", si.slot_name);
        }
        if (!focus_on_back && i == slot_idx) {
            draw_text(">", 0, 86, y + 14, 98, y + 36, 1, MENU_PAL_YELLOW);
            draw_text(buf, 0, 100, y + 14, 570, y + 36, 1, MENU_PAL_YELLOW);
        } else {
            draw_text(buf, 0, 100, y + 14, 570, y + 36, 0, PAL_WHITE);
        }
    }

    /* Back button */
    draw_text("Back", 0, 90, 359, 80, 382, 1,
              focus_on_back ? MENU_PAL_YELLOW : PAL_WHITE);

    /* Confirm dialog */
    if (confirm) {
        snprintf(buf, sizeof(buf), "%s to Slot %d?",
                 is_load ? "Load" : "Save", page * 4 + slot_idx + 1);
        draw_text(buf, 0, 260, 314, 420, 330, 1, PAL_WHITE);
        draw_text("Yes", 0, 266, 373, 310, 392, 0,
                  confirm_yes ? MENU_PAL_YELLOW : PAL_WHITE);
        draw_text("No", 0, 346, 373, 390, 392, 0,
                  confirm_yes ? PAL_WHITE : MENU_PAL_YELLOW);
    }
}

static void save_load_menu(int is_load, int from_mainmenu)
{
    int slot_idx = 0, page = 0, confirm = 0, confirm_yes = 1, running = 1, focus_on_back = 0;
    int total_pages = (SAVE_SLOTS + 3) / 4;
    char buf[128];
    SlotInfo si;
    const char *saved_fn;
    char orig_nb[64];

    /* Snapshot caller filename before slot operations corrupt sd */
    saved_fn = save_get_filename();
    if (saved_fn)
        strncpy(orig_nb, saved_fn, sizeof(orig_nb) - 1);
    else
        orig_nb[0] = '\0';
    orig_nb[sizeof(orig_nb) - 1] = '\0';

    menu_save_item_palette();
    hal_kbd_drain_advance();

    hal_mouse_erase_cursor();
    save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    hal_mouse_draw_cursor_force();

    while (running) {
        int abs_slot = page * 4 + slot_idx;
        int prev_slot = slot_idx, prev_focus = focus_on_back, prev_cyes = confirm_yes;

        hal_kbd_update();

        if (confirm) {
            if (hal_kbd_is_down(KC_LEFT) || hal_kbd_is_down(KC_RIGHT))
                confirm_yes = !confirm_yes;
            if (hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_SPACE) || hal_kbd_is_down(KC_XFER)) {
                if (confirm_yes) {
                    if (is_load) {
                        if (load_game_slot(abs_slot) != 0) {
                            { char _b[64]; snprintf(_b, sizeof(_b), "[LOAD] load_game_slot(%d) FAILED\r\n", abs_slot); hal_log(_b); }
                            confirm = 0; confirm_yes = 1;
                            save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                            show_error_msg("Load failed.", LAYER_DIALOG_X + LAYER_DIALOG_INDENT + 168, LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y - 10);
                            save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                            hal_mouse_draw_cursor_force();
                            continue;
                        }
                        running = 0; break;
                    } else {
                        save_game_slot(abs_slot);
                    }
                }
                confirm = 0; confirm_yes = 1; focus_on_back = 0;
                save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                hal_mouse_draw_cursor_force();
                continue;
            }
            if (hal_kbd_is_down(KC_ESC)) {
                confirm = 0; confirm_yes = 1; focus_on_back = 0;
                save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                hal_mouse_draw_cursor_force();
                continue;
            }
        } else {
            int slots_on_page = SAVE_SLOTS - page * 4;
            if (slots_on_page > 4) slots_on_page = 4;
            if (slots_on_page < 1) slots_on_page = 1;

            if (focus_on_back) {
                if (hal_kbd_is_down(KC_UP)) {
                    focus_on_back = 0;
                    slot_idx = slots_on_page - 1;
                } else if (hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_SPACE) || hal_kbd_is_down(KC_XFER)) {
                    if (from_mainmenu) {
                        nb_load(orig_nb[0] ? orig_nb : "mainmenu.nb");
                    } else {
                        if (load_game_temp() != 0)
                            hal_log("[SAVELOAD] load_game_temp failed in back key\r\n");
                    }
                    running = 0; break;
                }
            } else {
                if (hal_kbd_is_down(KC_UP) && slot_idx > 0) { slot_idx--; }
                else if (hal_kbd_is_down(KC_DOWN)) {
                    if (slot_idx >= slots_on_page - 1)
                        focus_on_back = 1;
                    else
                        slot_idx++;
                }
                else if (hal_kbd_is_down(KC_LEFT) && page > 0) {
                    page--; slot_idx = 0;
                    save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                    hal_mouse_draw_cursor_force();
                    continue;
                }
                else if (hal_kbd_is_down(KC_RIGHT) && page < total_pages - 1) {
                    page++; slot_idx = 0;
                    save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                    hal_mouse_draw_cursor_force();
                    continue;
                }
                else if (hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_SPACE) || hal_kbd_is_down(KC_XFER)) {
                    slot_info(abs_slot, &si);
                    if (is_load && !si.exists) {
                        show_error_msg("No save data.", 260, 298);
                        save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                        hal_mouse_draw_cursor_force();
                        continue;
                    } else {
                        confirm = 1; focus_on_back = 0;
                        save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                        hal_mouse_draw_cursor_force();
                        continue;
                    }
                }
            }
            if (hal_kbd_is_down(KC_ESC)) {
                if (from_mainmenu) {
                    nb_load(orig_nb[0] ? orig_nb : "mainmenu.nb");
                } else {
                    if (load_game_temp() != 0)
                        hal_log("[SAVELOAD] load_game_temp failed in esc\r\n");
                }
                running = 0; break;
            }
        }

        hal_mouse_update();
        hal_mouse_recenter_if_idle();

        {  /* mouse input */
            int mx, my; const int slot_ys[4] = { 90, 146, 202, 258 };
            if (hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
                mx = hal_mouse_get_x();
                my = hal_mouse_get_y();
                if (confirm) {
                    if (mx >= 250 && mx < 310 && my >= 370 && my < 392) {
                        if (confirm_yes) {
                            if (is_load) {
                                if (load_game_slot(page * 4 + slot_idx) != 0) {
                                    { char _b[64]; snprintf(_b, sizeof(_b), "[LOAD] load_game_slot(%d) FAILED\r\n", page * 4 + slot_idx); hal_log(_b); }
                                    confirm = 0; confirm_yes = 1;
                                    save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                                    show_error_msg("Load failed.", 260, 298);
                                    save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                                    hal_mouse_draw_cursor_force();
                                    continue;
                                }
                                running = 0; break;
                            } else {
                                save_game_slot(page * 4 + slot_idx);
                            }
                        }
                        confirm = 0; confirm_yes = 1; focus_on_back = 0;
                        save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                        hal_mouse_draw_cursor_force();
                        continue;
                    }
                    if (mx >= 330 && mx < 390 && my >= 370 && my < 392) {
                        confirm = 0; confirm_yes = 1; focus_on_back = 0;
                        save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                        hal_mouse_draw_cursor_force();
                        continue;
                    }
                } else {
                    /* Back button */
                    if (mx >= 66 && mx < 146 && my >= 352 && my < 382) {
                        if (from_mainmenu) {
                            nb_load(orig_nb[0] ? orig_nb : "mainmenu.nb");
                        } else {
                            if (load_game_temp() != 0)
                                hal_log("[SAVELOAD] load_game_temp failed in mouse back\r\n");
                        }
                        running = 0; break;
                    }
                    /* Page prev */
                    if (mx >= 56 && mx < 72 && my >= 318 && my < 334 && page > 0) {
                        page--; slot_idx = 0;
                        save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                        hal_mouse_draw_cursor_force();
                        continue;
                    }
                    /* Page next */
                    if (mx >= 576 && mx < 592 && my >= 318 && my < 334 && page < total_pages - 1) {
                        page++; slot_idx = 0;
                        save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                        hal_mouse_draw_cursor_force();
                        continue;
                    }
                    /* Slot selection */
                    if (mx >= 80 && mx < 560 && my >= slot_ys[0] && my < slot_ys[3] + 44) {
                        int i;
                        int slots_on_page = SAVE_SLOTS - page * 4;
                        if (slots_on_page > 4) slots_on_page = 4;
                        for (i = 0; i < slots_on_page; i++) {
                            if (my >= slot_ys[i] && my < slot_ys[i] + 44) {
                                slot_idx = i; focus_on_back = 0;
                                slot_info(page * 4 + i, &si);
                                if (is_load && !si.exists) {
                                    show_error_msg("No save data.", 260, 298);
                                    save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                                    hal_mouse_draw_cursor_force();
                                } else {
                                    confirm = 1; focus_on_back = 0;
                                    save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                                    hal_mouse_draw_cursor_force();
                                }
                                break;
                            }
                        }
                        continue;
                    }
                }
            }
        }

        if (slot_idx != prev_slot || focus_on_back != prev_focus || confirm_yes != prev_cyes)
            save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 0);

        hal_mouse_draw_cursor();
    }
    menu_restore_item_palette();
}

/* loadscene command: open load slot selection menu */
void cmd_loadscene(int argc, const char **argv, const char *cmd_name)
{
    (void)argc; (void)argv; (void)cmd_name;
    save_load_menu(1, 0);
}
