/*
 * nb_music.c — Music Room (LOAD-paradigm full-screen list).
 *
 * Reached from the Special menu ("music" -> music.nb -> musicmenu()).
 * Layout / behaviour / display conventions follow the in-game settings list
 * (nb_setting.c) and the Special menu (nb_special.c): a full-screen fixed
 * layout with embossed rows, page chrome and a bottom-left Back button, plus
 * the focus_on_back model.
 *
 * The track list is generated, not scripted: it enumerates every BGM
 * registered in ASSETS.DB (BGM_COUNT / bgm_title_map[] from nb_asset_table.h),
 * mirroring how the CG gallery enumerates CG_COUNT.  A newly registered BGM
 * therefore shows up with no script or UI change.  The display title comes
 * from the optional img_map.title column, falling back to the script key.
 *
 * Key bindings (deviating from the settings menu on purpose):
 *   Up/Down        move focus (rows <-> Back button)
 *   Enter/Space    play the focused track; pressing it again stops it
 *                  (toggle)
 *   Left/Right     turn the page (a row has no steppable value)
 *   Esc            stop playback and leave the scene
 * Playback goes through audio_bgm_start()/audio_bgm_stop() — never a PCM
 * loop (AGENTS.md §14 audio rules).  The menu does not touch prefs: when the
 * player has BGM switched off a "BGM: Off" hint is shown instead of silently
 * overriding the setting.
 */
#include <stdio.h>
#include <string.h>
#include "render.h"
#include "ui.h"
#include "scene_layers.h"
#include "menu_layer.h"
#include "audio.h"
#include "prefs.h"
#include "hal.h"
#include "nb_internal.h"
#include "nb_commands.h"
#include "nb.h"
#include "tr.h"
#include "frame.h"
#include "debug.h"
#include "input_boundary.h"
#include "nb_asset_table.h"

/*=== Layout ==============================================================*/

#define MUSIC_ROWS    4                   /* rows per page (load/special parity) */

#define MUS_BTN_X     120                 /* row button rect */
#define MUS_BTN_W     400
#define MUS_BTN_H     44
#define MUS_ROW_R     SAVE_SLOT_R
#define MUS_IND_LX    (MUS_BTN_X + 6)     /* '>' focus indicator */
#define MUS_LABEL_X   (MUS_BTN_X + 20)    /* track title, left-aligned */
#define MUS_LABEL_W   300
#define MUS_MARK_X    (MUS_BTN_X + MUS_BTN_W - 40)  /* playing indicator */
#define MUS_TITLE_Y   28
#define MUS_ARR_Y     318                 /* pager arrows y */
#define MUS_COUNT_Y   330                 /* pager counter y */
#define MUS_BACK_Y    352

static const int music_row_y[MUSIC_ROWS] = { 90, 146, 202, 258 };

/*=== Row model ===========================================================*/

/* Number of rows visible on 'page' (clamped to [1, MUSIC_ROWS]). */
static int music_rows_on_page(int page)
{
    int n = BGM_COUNT - page * MUSIC_ROWS;
    if (n > MUSIC_ROWS) n = MUSIC_ROWS;
    if (n < 1) n = 1;
    return n;
}

/* Display title of absolute BGM index: registered title, else the script key
 * (an empty img_map.title is emitted as "" by export_asset_table.py). */
static const char *music_title(int abs)
{
    const char *t;
    if (abs < 0 || abs >= BGM_COUNT)
        return "";
    t = bgm_title_map[abs].title;
    if (t != NULL && t[0] != '\0')
        return t;
    return bgm_title_map[abs].name;
}

/*=== Drawing =============================================================*/

/* Playing indicator: a small filled block in the row's right margin.  FONT.DAT
 * carries no musical-note glyph and draw_text's non-ASCII path falls back to
 * the CJK font, which has none either, so the marker is geometry rather than
 * a character. */
static void music_draw_mark(int y)
{
    fill_rect(MUS_MARK_X, y + MUS_BTN_H / 2 - 6, 12, 12, MENU_PAL_YELLOW);
}

/* One row: title + focus indicator + playing mark.  The row button is opaque,
 * so a single interior fill wipes the previous contents before the text goes
 * down again. */
static void music_draw_row(int abs, int row, int focused, int playing)
{
    int y = music_row_y[row];
    int max_y = y + MUS_BTN_H - 8;
    uint8_t fg = focused ? MENU_PAL_YELLOW : PAL_WHITE;

    fill_rect(MUS_BTN_X + 4, y + 2, MUS_BTN_W - 8, MUS_BTN_H - 4, BTN_FILL_IDX);
    draw_text(music_title(abs), 0, MUS_LABEL_X, y + 14,
              MUS_LABEL_X + MUS_LABEL_W, max_y, focused, fg);
    if (playing)
        music_draw_mark(y);
    if (focused)
        draw_text(">", 0, MUS_IND_LX, y + 14, MUS_IND_LX + 16, max_y, 1,
                  MENU_PAL_YELLOW);
}

/* Single-source-of-truth draw.  full=1 (entry, page turn) repaints the title,
 * the emboss row bodies, the pager and the Back border; incremental passes
 * only relabel the rows and the Back label (AGENTS.md §14 two-stage menu
 * rendering).  'sel' is page-relative; 'playing' is an absolute index or -1. */
static void music_draw(int page, int sel, int focus_on_back, int total_pages,
                       int playing, int full)
{
    int rows = music_rows_on_page(page);
    int i;

    menu_layer_begin_draw();
    if (full) {
        const char *title = tr("MUSIC");
        vblank_wait();
        draw_title_large(title,
                         (LAYER_SCREEN_W - text_title_width(title, 4)) / 2,
                         MUS_TITLE_Y, 4, PAL_WHITE);
        for (i = 0; i < rows; i++)
            draw_rounded_emboss(MUS_BTN_X, music_row_y[i], MUS_BTN_W, MUS_BTN_H,
                                MUS_ROW_R, BTN_FILL_IDX, BTN_HIGHLIGHT_IDX,
                                BTN_SHADOW_IDX);
        /* BGM switched off in the settings menu: the play command is silent by
         * design, so say so rather than letting the player think it broke. */
        if (!prefs_get_bgm_enabled()) {
            const char *hint = tr("BGM: Off");
            unsigned hw = (unsigned)text_width(hint, 0);
            draw_text(hint, 0, LAYER_SCREEN_W - 20 - (int)hw, MUS_TITLE_Y + 8,
                      LAYER_SCREEN_W - 20, MUS_TITLE_Y + 24, 0, MENU_PAL_YELLOW);
        }
        menu_pagenav_draw(MUS_ARR_Y, MUS_COUNT_Y, PAL_WHITE, page, total_pages);
        menu_back_draw(MUS_BACK_Y, focus_on_back, 1, PAL_WHITE);
    }

    for (i = 0; i < rows; i++) {
        int abs = page * MUSIC_ROWS + i;
        music_draw_row(abs, i, !focus_on_back && i == sel, abs == playing);
    }

    menu_back_draw(MUS_BACK_Y, focus_on_back, 0, PAL_WHITE);

    menu_layer_commit();
    menu_layer_blit();
}

/*=== Routing =============================================================*/

/* Return to the menu-parent scene (set by specialmenu), falling back to the
 * main menu.  The parent is read at exit time so a stale value can never be
 * consumed across a fresh entry (mirrors nb_cggallery.c gallery_return_home). */
static void music_return_home(void)
{
    const char *ret = nb_get_menu_return();
    scene_switch(ret[0] != '\0' ? ret : "mainmenu.nb", SCENE_SWITCH_MENU);
}

/* Empty catalogue (BGM_COUNT == 0): message + wait for any dismiss input,
 * mirroring the CG gallery's empty path (nb_cggallery.c). */
static void music_empty(void)
{
    NB_DEBUG("musicmenu: BGM_COUNT=0, empty music room\r\n");
    input_drain_boundary();
    menu_save_item_palette();
    hal_mouse_erase_cursor();
    draw_text(tr("No BGM available."), 0, 200, 190, 440, 210, 1, MENU_PAL_WHITE);
    hal_mouse_draw_cursor_force();
    for (;;) {
        engine_frame_pump();  /* keep the clock + other audio ticking */
        hal_kbd_update();
        hal_mouse_update();
        if (hal_kbd_is_down(KC_ESC) || hal_kbd_is_down(KC_SPACE) ||
            hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_XFER) ||
            hal_mouse_was_clicked(HAL_MOUSE_LBUTTON))
            break;
        hal_mouse_draw_cursor();
    }
    hal_mouse_flush();
    menu_restore_item_palette();
    music_return_home();
}

/*=== Command =============================================================*/

/* musicmenu — music room (script: music.nb). */
void cmd_musicmenu(int argc, const char **argv, const char *cmd_name)
{
    int page = 0, sel = 0, focus_on_back = 0, running = 1, total_pages;
    int playing = -1;                 /* absolute BGM index, or -1 */
    int prev_sel, prev_fb, prev_page, prev_play;

    (void)argv;
    (void)cmd_name;
    if (argc > 0)
        NB_DEBUG("musicmenu: takes no arguments, ignoring %d\r\n", argc);

    if (BGM_COUNT == 0) {
        music_empty();
        return;
    }

    total_pages = menu_pagecount(BGM_COUNT, MUSIC_ROWS);

    menu_save_item_palette();
    input_drain_boundary();

    hal_mouse_erase_cursor();
    menu_layer_open(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
    music_draw(page, sel, focus_on_back, total_pages, playing, 1);
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    hal_mouse_draw_cursor_force();

    while (running) {
        int rows = music_rows_on_page(page);
        int abs = page * MUSIC_ROWS + sel;

        prev_sel = sel; prev_fb = focus_on_back;
        prev_page = page; prev_play = playing;

        engine_frame_pump();  /* keep the FM/MIDI pump + clock ticking */
        hal_kbd_update();

        if (focus_on_back) {
            if (hal_kbd_is_down(KC_UP)) {
                focus_on_back = 0;
                sel = rows - 1;
            } else if (hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_SPACE) ||
                       hal_kbd_is_down(KC_XFER)) {
                running = 0;
            } else if (hal_kbd_is_down(KC_LEFT) && page > 0) {
                page--; sel = 0;
            } else if (hal_kbd_is_down(KC_RIGHT) && page < total_pages - 1) {
                page++; sel = 0;
            }
        } else {
            if (hal_kbd_is_down(KC_UP)) {
                if (sel > 0) sel--;
            } else if (hal_kbd_is_down(KC_DOWN)) {
                if (sel >= rows - 1) focus_on_back = 1;
                else sel++;
            } else if (hal_kbd_is_down(KC_LEFT)) {
                if (page > 0) { page--; sel = 0; }
            } else if (hal_kbd_is_down(KC_RIGHT)) {
                if (page < total_pages - 1) { page++; sel = 0; }
            } else if (hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_SPACE) ||
                       hal_kbd_is_down(KC_XFER)) {
                if (playing == abs) {
                    audio_bgm_stop();
                    playing = -1;
                } else {
                    audio_bgm_start(bgm_title_map[abs].name);
                    playing = abs;
                }
            }
        }
        if (hal_kbd_is_down(KC_ESC))
            running = 0;

        hal_mouse_update();
        hal_mouse_recenter_if_idle();

        if (hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
            int mx = hal_mouse_get_x();
            int my = hal_mouse_get_y();
            int hit;

            if (menu_back_hit(MUS_BACK_Y, mx, my)) {
                running = 0;
            } else if ((hit = menu_page_hit(MUS_ARR_Y, mx, my)) == 1 && page > 0) {
                page--; sel = 0;
            } else if ((hit = menu_page_hit(MUS_ARR_Y, mx, my)) == 2 &&
                       page < total_pages - 1) {
                page++; sel = 0;
            } else if (mx >= MUS_BTN_X && mx < MUS_BTN_X + MUS_BTN_W &&
                       my >= music_row_y[0] &&
                       my < music_row_y[MUSIC_ROWS - 1] + MUS_BTN_H) {
                int i;
                for (i = 0; i < rows; i++) {
                    if (my >= music_row_y[i] && my < music_row_y[i] + MUS_BTN_H) {
                        int clicked = page * MUSIC_ROWS + i;
                        sel = i;
                        focus_on_back = 0;
                        if (playing == clicked) {
                            audio_bgm_stop();
                            playing = -1;
                        } else {
                            audio_bgm_start(bgm_title_map[clicked].name);
                            playing = clicked;
                        }
                        break;
                    }
                }
            }
        }

        /* A page turn changes which rows are on screen, so redraw fully. */
        if (page != prev_page) {
            rows = music_rows_on_page(page);
            if (focus_on_back) sel = rows - 1;
            else if (sel >= rows) sel = rows - 1;
            music_draw(page, sel, focus_on_back, total_pages, playing, 1);
            hal_mouse_draw_cursor_force();
        } else if (sel != prev_sel || focus_on_back != prev_fb ||
                   playing != prev_play) {
            music_draw(page, sel, focus_on_back, total_pages, playing, 0);
        }

        hal_mouse_draw_cursor();
    }

    if (playing >= 0)
        audio_bgm_stop();
    menu_finish();
    music_return_home();
}
