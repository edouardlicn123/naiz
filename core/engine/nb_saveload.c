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
#include "tr.h"
#include "strutil.h"

/* Debug logging — shared macro in debug.h */
#include "debug.h"

#define SLOTS_PER_PAGE 4

/* Shared save/load slot selection menu used by cmd_loadscene.
 * is_load=0 -> save mode, is_load=1 -> load mode.
 * from_mainmenu=1: Back/ESC exits via nb_load() (return to caller scene);
 * from_mainmenu=0: exits via load_game_temp() (restore temp save).
 * (All current callers pass from_mainmenu=0; kept as a parameter for
 *  future main-menu entry without a global.) */

/* Draw a transient error message to the VRAM overlay and wait for a keypress.
 * Returns with kbd drained for next input.  Message goes through tr() so the
 * system UI stays translatable.  The box is PAL_WHITE and the glyphs use the
 * reserved PAL_CURSOR_BLACK: palette index 0 is NOT reliably black in the
 * menu/background palette, so it would render as white-on-white.  Box width
 * grows with the translated text (text_width) so long CJK/European strings
 * are not clipped by a fixed 120px box. */
static void show_error_msg(const char *msg, int x, int y)
{
    const char *t = tr(msg);
    int tw = text_width(t, 0);
    int w = tw + 24;
    if (w < 120) w = 120;
    if (x + w > LAYER_SCREEN_W) x = LAYER_SCREEN_W - w;
    fill_rect(x, y, w, 24, PAL_WHITE);
    draw_text(t, 0, x + 12, y + 2, x + w - 12, y + 20, 1, PAL_CURSOR_BLACK);
    hal_kbd_drain_advance();
    hal_kbd_wait_any();
    hal_kbd_drain_advance();
}

/*=== Page slot cache ======================================================*/

/* Slot text labels + existence flags for the current page, so focus/confirm
 * redraws never re-read the save headers from disk (slot_info does file I/O).
 * Rebuilt only when page changes (or invalidated after a save writes a slot).
 * 4 rows of "%.31s - %.63s - %.19s" (max 119 chars) fit in 128 bytes. */
static char slot_label_cache[SLOTS_PER_PAGE][128];
static char slot_exists_cache[SLOTS_PER_PAGE];
static int  slot_cache_page = -1;

/* Slot row Y coordinates (SLOTS_PER_PAGE rows, single source of truth). */
static const int slot_y[SLOTS_PER_PAGE] = { 90, 146, 202, 258 };

/* Convert page-relative slot index to absolute slot number. */
static int slot_abs(int page, int row) { return page * SLOTS_PER_PAGE + row; }

/* Number of visible slots on 'page' (clamped to [1, SLOTS_PER_PAGE]). */
static int save_load_slots_on_page(int page)
{
    int n = SAVE_SLOTS - page * SLOTS_PER_PAGE;
    if (n > SLOTS_PER_PAGE) n = SLOTS_PER_PAGE;
    if (n < 1) n = 1;
    return n;
}

/* Display label for a save slot: prefers the chapter title, falls back to
 * the filename when the save was taken outside any defined chapter. */
const char *slot_chapter_label(const SlotInfo *si)
{
    return si->chapter_title[0] ? si->chapter_title : si->filename;
}

/* Confirm-mode action: executes the save/load for the confirmed slot.
 * g_confirm_is_load mirrors the is_load arg of the running save_load_menu
 * (menus are non-reentrant, so a single flag is safe).  Returns 1 on load
 * success (leave the menu), 0 after a save (stay + refresh the list), -1 on
 * load failure (caller shows an error box). */
static int g_confirm_is_load = 0;

static int save_load_confirm_action(int slot)
{
    if (g_confirm_is_load) {
        if (load_game_slot(slot) != 0) {
            hal_logf("[LOAD] load_game_slot(%d) FAILED\r\n", slot);
            return -1;
        }
        return 1;
    }
    save_game_slot(slot);
    slot_cache_page = -1;   /* slot data changed */
    return 0;
}

/* Confirm UI geometry for the full-screen save/load menu. */
static const MenuConfirmCfg g_sl_confirm_cfg = {
    .yes_x0 = 250, .no_x0 = 330, .y0 = 370, .y1 = 392,
    .mouse_yes_always = 0,
    .action = save_load_confirm_action
};

/* Rebuild the label/existence cache for the given page. */
static void save_load_cache_build(int page)
{
    int i;
    for (i = 0; i < SLOTS_PER_PAGE; i++) {
        slot_label_cache[i][0] = '\0';
        slot_exists_cache[i] = 0;
    }
    for (i = 0; i < SLOTS_PER_PAGE; i++) {
        int si_idx = slot_abs(page, i);
        SlotInfo si;
        if (si_idx >= SAVE_SLOTS) break;
        slot_info(si_idx, &si);
        slot_exists_cache[i] = si.exists;
        if (si.exists) {
            const char *chapter = slot_chapter_label(&si);
            snprintf(slot_label_cache[i], sizeof(slot_label_cache[i]),
                     "%.31s - %.63s - %.19s",
                     si.slot_name, chapter, si.timestamp);
        } else {
            snprintf(slot_label_cache[i], sizeof(slot_label_cache[i]),
                     "Slot %d - (%s)", si_idx + 1, tr("Empty"));
        }
    }
    slot_cache_page = page;
}

/* Draw save/load menu UI.  If full=1, draw all background elements (emboss
 * slots, page nav, Back button).  Always draws text labels (cheap text-only). */
static void save_load_draw(int is_load, int page, int slot_idx, int focus_on_back,
                           int confirm, int confirm_yes, int total_pages, int full)
{
    int i;
    char buf[128];

    /* Draw into the menu layer composite (see save_load_menu for open);
     * commit + full-region blit publishes every state change atomically.
     * Degrades to direct VRAM drawing when the layer is not open. */
    menu_layer_begin_draw();

    /* Page slot text is cached; only re-read the save headers on page
     * change (focus/confirm redraws reuse the cached labels, no disk I/O). */
    if (page != slot_cache_page)
        save_load_cache_build(page);

    if (full) {
        vblank_wait();
        {
            int drawn = 0;
            if (settings_get_blackletter_title() && !nb_lang_is_cjk()) {
                int tid = nb_asset_id(is_load ? "loadtitle" : "savetitle");
                MagImage *m = (tid >= 0) ? image_load((unsigned short)tid) : NULL;
                if (m) {
                    /* Center the blackletter title over the old title spot. */
                    int bx = (LAYER_SCREEN_W - m->width) / 2;
                    int by = 28 + (32 - m->height) / 2;
                    menu_layer_blit_sprite(m, bx, by, PAL_TRANSPARENT);
                    mag_release(m);
                    drawn = 1;
                }
            }
            if (!drawn)
                draw_title_large(tr(is_load ? "LOAD" : "SAVE"),
                                 (LAYER_SCREEN_W - text_title_width(tr(is_load ? "LOAD" : "SAVE"), 4)) / 2,
                                 28, 4, PAL_WHITE);
        }
        for (i = 0; i < SLOTS_PER_PAGE; i++) {
            int si_idx = slot_abs(page, i);
            if (si_idx >= SAVE_SLOTS) break;
            draw_rounded_emboss(80, slot_y[i], 480, 44, SAVE_SLOT_R,
                                BTN_FILL_IDX, BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX);
        }
        /* Conditional UI elements (nav arrows, page counter) clear their
         * strips back to the layer base first: the composite persists
         * between redraws, so an arrow dropping out at the first/last page
         * or digits changing width would otherwise linger as ghosts. */
        menu_pagenav_draw(318, 330, PAL_WHITE, page, total_pages);
        menu_back_draw(352, focus_on_back, 1, PAL_WHITE);
        /* The confirm layer (prompt + Yes/No buttons) is conditional too:
         * erase its strips so leaving confirm mode does not leave ghosts. */
        menu_layer_erase_to_base(260, 314, 160, 16);
        menu_layer_erase_to_base(250, 370, 140, 22);
        if (confirm) {
            draw_rounded_emboss(250, 370, 60, 22, 2,
                                BTN_FILL_IDX, BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX);
            draw_rounded_emboss(330, 370, 60, 22, 2,
                                BTN_FILL_IDX, BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX);
        }
    }

    /* Slot text (reuse cached labels; relabel + refocus only) */
    for (i = 0; i < SLOTS_PER_PAGE; i++) {
        int si_idx = slot_abs(page, i), y = slot_y[i];
        if (si_idx >= SAVE_SLOTS) break;
        fill_rect(86, y + 2, 12, 40, BTN_FILL_IDX);
        if (!focus_on_back && i == slot_idx) {
            draw_text(">", 0, 86, y + 14, 98, y + 36, 1, MENU_PAL_YELLOW);
            draw_text(slot_label_cache[i], 0, 100, y + 14, 570, y + 36, 1, MENU_PAL_YELLOW);
        } else {
            draw_text(slot_label_cache[i], 0, 100, y + 14, 570, y + 36, 0, PAL_WHITE);
        }
    }

    /* Back button: only the label on incremental redraws (emboss repainted
     * by the full draw above). */
    menu_back_draw(352, focus_on_back, 0, PAL_WHITE);

    /* Confirm dialog */
    if (confirm) {
        snprintf(buf, sizeof(buf), tr(is_load ? "Load to Slot %d?" : "Save to Slot %d?"),
                 slot_abs(page, slot_idx) + 1);
        draw_text(buf, 0, 260, 314, 420, 330, 1, PAL_WHITE);
        draw_text(tr("Yes"), 0, 266, 373, 310, 392, 0,
                  confirm_yes ? MENU_PAL_YELLOW : PAL_WHITE);
        draw_text(tr("No"), 0, 346, 373, 390, 392, 0,
                  confirm_yes ? PAL_WHITE : MENU_PAL_YELLOW);
    }

    /* Publish the composite to VRAM (full and incremental draws alike). */
    menu_layer_commit();
    menu_layer_blit();
}

static void save_load_menu(int is_load, int from_mainmenu)
{
    int slot_idx = 0, page = 0, confirm = 0, confirm_yes = 1, running = 1, focus_on_back = 0;
    int total_pages = menu_pagecount(SAVE_SLOTS, SLOTS_PER_PAGE);
    char buf[128];
    SlotInfo si;
    const char *saved_fn;
    char orig_nb[64];

    g_confirm_is_load = is_load;

    /* Snapshot caller filename before slot operations corrupt sd */
    saved_fn = save_get_filename();
    if (saved_fn)
        str_copy(orig_nb, sizeof(orig_nb), saved_fn);
    else
        orig_nb[0] = '\0';

    menu_save_item_palette();
    hal_kbd_drain_advance();

    hal_mouse_erase_cursor();
    /* All save/load UI drawing routes into the menu layer composite; each
     * save_load_draw call commits + blits.  On OOM the layer stays closed
     * and drawing degrades to direct VRAM (legacy behavior). */
    menu_layer_open(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
    save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    hal_mouse_draw_cursor_force();

    while (running) {
        int abs_slot = slot_abs(page, slot_idx);
        int prev_slot = slot_idx, prev_focus = focus_on_back, prev_cyes = confirm_yes;

        hal_kbd_update();

        if (confirm) {
            int r = menu_confirm_input(&confirm_yes, abs_slot, &g_sl_confirm_cfg);
            if (r == MENU_CONFIRM_TOGGLE) {
                save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 0);
                hal_mouse_draw_cursor_force();
            } else if (r == MENU_CONFIRM_CLOSED) {
                confirm = 0; confirm_yes = 1; focus_on_back = 0;
                save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                hal_mouse_draw_cursor_force();
            } else if (r == MENU_CONFIRM_FAILED) {
                confirm = 0; confirm_yes = 1; focus_on_back = 0;
                save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                show_error_msg("Load failed.", 260, 346);
                save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                hal_mouse_draw_cursor_force();
            } else if (r == MENU_CONFIRM_EXIT) {
                running = 0; break;
            }
            hal_mouse_draw_cursor();
            continue;
        } else {
            int slots_on_page = save_load_slots_on_page(page);

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
                        show_error_msg("No save data.", 260, 346);
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

        {  /* mouse input (list mode only — confirm mode is handled above) */
            int mx, my;
            if (hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
                mx = hal_mouse_get_x();
                my = hal_mouse_get_y();
                /* Back button */
                if (menu_back_hit(352, mx, my)) {
                    if (from_mainmenu) {
                        nb_load(orig_nb[0] ? orig_nb : "mainmenu.nb");
                    } else {
                        if (load_game_temp() != 0)
                            hal_log("[SAVELOAD] load_game_temp failed in mouse back\r\n");
                    }
                    running = 0; break;
                }
                /* Page prev */
                if (menu_page_hit(318, mx, my) == 1 && page > 0) {
                    page--; slot_idx = 0;
                    save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                    hal_mouse_draw_cursor_force();
                    continue;
                }
                /* Page next */
                if (menu_page_hit(318, mx, my) == 2 && page < total_pages - 1) {
                    page++; slot_idx = 0;
                    save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 1);
                    hal_mouse_draw_cursor_force();
                    continue;
                }
                /* Slot selection */
                if (mx >= 80 && mx < 560 && my >= slot_y[0] && my < slot_y[SLOTS_PER_PAGE - 1] + 44) {
                    int i;
                    int slots_on_page = save_load_slots_on_page(page);
                    for (i = 0; i < slots_on_page; i++) {
                        if (my >= slot_y[i] && my < slot_y[i] + 44) {
                            slot_idx = i; focus_on_back = 0;
                            slot_info(slot_abs(page, i), &si);
                            if (is_load && !si.exists) {
                                show_error_msg("No save data.", 260, 346);
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

        if (slot_idx != prev_slot || focus_on_back != prev_focus || confirm_yes != prev_cyes)
            save_load_draw(is_load, page, slot_idx, focus_on_back, confirm, confirm_yes, total_pages, 0);

        hal_mouse_draw_cursor();
    }
    menu_finish();
}

/* loadscene command: open load slot selection menu */
void cmd_loadscene(int argc, const char **argv, const char *cmd_name)
{
    (void)argc; (void)argv; (void)cmd_name;
    save_load_menu(1, 0);
}
