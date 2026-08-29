/*
 * settings_menu.c — Pre-game settings menu (C-code rendered).
 *
 * Always shown on startup. Pure ASCII, no CJK needed.
 * Uses render.h primitives directly (draw_text_outlined, fill_rect,
 * vram_read/vram_write, mouse input).
 *
 * Visual definition:
 *   Title:    1x white text + black outline, top-left
 *   Version:  1x white text + black outline, top-right
 *   Focus:    ">" indicator (1x) before focused element
 *   Arrows:   1x white text + black outline
 *   Lang sel: 1x white text + black outline, centered between arrows
 *   StartBtn: 1x white text + black outline, left-aligned with Language label
 *
 * Anti-flicker (save_load_menu pattern):
 *   full=1: initial draw — background + all text + save all snapshots
 *   full=2: language change — restore lang_name snapshot + indicators, redraw lang name only
 *   full=0: focus change — restore indicator snapshots + redraw indicator only
 *   no change: no redraw at all
 *
 * Layout (1x text, 8x16 glyphs):
 *   Naiz Settings                              v0.2.068
 *   > Language  <    English    >              (focus=LANG)
 *     Language  <    English    >              (focus=START)
 *   > Start Game                               (focus=START)
 *     Start Game                               (focus=LANG)
 */
#include <stdio.h>
#include <string.h>
#include "render.h"
#include "ui.h"
#include "scene_layers.h"
#include "settings.h"
#include "hal.h"
#include "debug.h"
#include "image.h"

/* Language list: display names and lang codes */
static const char *LANG_NAMES[] = {
    "English", "Japanese", "Chinese (SC)", "Chinese (TC)", "Korean",
    "French", "German", "Italian", "Spanish", "Portuguese"
};
static const char *LANG_CODES[] = {
    "eng", "jpn", "chi", "cht", "kor",
    "fre", "ger", "ita", "spa", "por"
};
#define N_LANGS 10

/* Focus targets */
#define FOCUS_LANG   0
#define FOCUS_START  1

/* Layout constants (1x text) */
#define INDICATOR_X  5      /* > focus indicator (1x) */
#define MENU_X       30     /* all menu text x start */
#define SEL_Y        122    /* language selector row y (1x, 16px tall) */
#define SEL_LX       170    /* < arrow x */
#define ARROW_W      40
#define GAP          4
#define LABEL_AREA_W 200
#define LABEL_X      (SEL_LX + ARROW_W + GAP)         /* 214 */
#define LABEL_CX     (LABEL_X + LABEL_AREA_W / 2)     /* 314 */
#define START_BW     200
#define START_BH     20
#define START_X      MENU_X                             /* 30, aligned with Language */
#define START_BY     (LAYER_SCREEN_H - 68)

/* Snapshot dimensions (1x glyph: 8x16, outline ±1px → drawn 10x18) */
#define IND_SAVE_W   12
#define IND_SAVE_H   18
#define LANG_NAME_SAVE_W 110
#define LANG_NAME_SAVE_H 18

/* Saved background snapshots */
static uint8_t bg_lang_name[LANG_NAME_SAVE_H * LANG_NAME_SAVE_W];
static uint8_t bg_lang_ind[IND_SAVE_H * IND_SAVE_W];
static uint8_t bg_start_ind[IND_SAVE_H * IND_SAVE_W];

/* Draw text with 1px black outline glow (8-direction offset). */
static void draw_text_outlined(const char *s, int byte_start,
                               int x, int y, int bold, uint8_t color)
{
    int dx, dy;
    for (dy = -1; dy <= 1; dy++)
        for (dx = -1; dx <= 1; dx++) {
            if (dx == 0 && dy == 0) continue;
            draw_text(s, byte_start, x + dx, y + dy,
                      640, 400, bold, PAL_CURSOR_BLACK);
        }
    draw_text(s, byte_start, x, y, 640, 400, bold, color);
}

/* Find the current language index from settings, default to English */
static int find_lang_index(void)
{
    const char *cur = settings_get_lang();
    int i;
    if (!cur || !*cur) return 0;
    for (i = 0; i < N_LANGS; i++) {
        if (strcmp(cur, LANG_CODES[i]) == 0)
            return i;
    }
    return 0;
}

/* Hit test: returns which element was clicked
 * 0 = left arrow, 1 = right arrow, 2 = start button, -1 = none */
static int menu_hittest(int mx, int my)
{
    if (mx >= SEL_LX && mx < SEL_LX + ARROW_W &&
        my >= SEL_Y && my < SEL_Y + 20)
        return 0;
    if (mx >= LABEL_X + LABEL_AREA_W + GAP &&
        mx <  LABEL_X + LABEL_AREA_W + GAP + ARROW_W &&
        my >= SEL_Y && my < SEL_Y + 20)
        return 1;
    if (mx >= START_X && mx < START_X + START_BW &&
        my >= START_BY && my < START_BY + START_BH)
        return 2;
    return -1;
}

/* Draw menu.  full=1: initial full draw + save clean snapshots.
 *            full=2: language change — restore + redraw lang name + indicators.
 *            full=0: focus change — restore + redraw indicators only.
 * Snapshots are saved BEFORE dynamic text to capture clean background. */
static void settings_menu_draw(int lang_idx, int focus, int full)
{
    int tw;

    if (full == 1) {
        vblank_wait();
        /* Background */
        {
            MagImage *bg_img = image_load(13);
            if (bg_img) {
                vram_blit(bg_img, 0, 0);
                mag_release(bg_img);
            } else {
                fill_rect(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
            }
        }
        /* Title: 1x, top-left */
        draw_text_outlined("Naiz Settings", 0, 20, 10, 1, PAL_WHITE);
        /* Version: 1x, top-right */
        {
            const char *ver = settings_get_version();
            if (ver && *ver)
                draw_text_outlined(ver, 0, 580, 10, 0, PAL_WHITE);
        }
        /* Static menu text (does NOT overlap snapshot areas) */
        draw_text_outlined("Language", 0, MENU_X, SEL_Y, 0, PAL_WHITE);
        draw_text_outlined("<", 0, SEL_LX + 10, SEL_Y, 0, PAL_WHITE);
        draw_text_outlined(">", 0,
                           LABEL_X + LABEL_AREA_W + GAP + 10, SEL_Y, 0, PAL_WHITE);
        draw_text_outlined("Start Game", 0, START_X, START_BY, 0, PAL_WHITE);

        /* Save CLEAN snapshots BEFORE drawing dynamic content */
        vram_read(LABEL_CX - LANG_NAME_SAVE_W / 2, SEL_Y - 1,
                  LANG_NAME_SAVE_W, LANG_NAME_SAVE_H, bg_lang_name);
        vram_read(INDICATOR_X - 2, SEL_Y - 1, IND_SAVE_W, IND_SAVE_H, bg_lang_ind);
        vram_read(INDICATOR_X - 2, START_BY - 1, IND_SAVE_W, IND_SAVE_H, bg_start_ind);

        /* Draw dynamic content (language name + focus indicator) */
        tw = text_width(LANG_NAMES[lang_idx], 0);
        draw_text_outlined(LANG_NAMES[lang_idx], 0,
                           LABEL_CX - tw / 2, SEL_Y, 0, PAL_WHITE);
        if (focus == FOCUS_LANG)
            draw_text_outlined(">", 0, INDICATOR_X, SEL_Y, 0, PAL_WHITE);
        else if (focus == FOCUS_START)
            draw_text_outlined(">", 0, INDICATOR_X, START_BY, 0, PAL_WHITE);
    }

    if (full == 2) {
        /* Language change: restore CLEAN snapshots, redraw dynamic content */
        vram_write(bg_lang_name, LABEL_CX - LANG_NAME_SAVE_W / 2, SEL_Y - 1,
                   LANG_NAME_SAVE_W, LANG_NAME_SAVE_H);
        vram_write(bg_lang_ind, INDICATOR_X - 2, SEL_Y - 1, IND_SAVE_W, IND_SAVE_H);
        vram_write(bg_start_ind, INDICATOR_X - 2, START_BY - 1, IND_SAVE_W, IND_SAVE_H);
        tw = text_width(LANG_NAMES[lang_idx], 0);
        draw_text_outlined(LANG_NAMES[lang_idx], 0,
                           LABEL_CX - tw / 2, SEL_Y, 0, PAL_WHITE);
        if (focus == FOCUS_LANG)
            draw_text_outlined(">", 0, INDICATOR_X, SEL_Y, 0, PAL_WHITE);
        else if (focus == FOCUS_START)
            draw_text_outlined(">", 0, INDICATOR_X, START_BY, 0, PAL_WHITE);
    }

    if (full == 0) {
        /* Focus change: restore indicator snapshots, redraw indicator */
        vram_write(bg_lang_ind, INDICATOR_X - 2, SEL_Y - 1, IND_SAVE_W, IND_SAVE_H);
        vram_write(bg_start_ind, INDICATOR_X - 2, START_BY - 1, IND_SAVE_W, IND_SAVE_H);
        if (focus == FOCUS_LANG)
            draw_text_outlined(">", 0, INDICATOR_X, SEL_Y, 0, PAL_WHITE);
        else if (focus == FOCUS_START)
            draw_text_outlined(">", 0, INDICATOR_X, START_BY, 0, PAL_WHITE);
    }
}

void settings_menu_run(void)
{
    int lang_idx = find_lang_index();
    int focus = FOCUS_LANG;
    int prev_lang, prev_focus;

    NB_DEBUG("settings_menu: enter (default lang=%s)\r\n", LANG_CODES[lang_idx]);

    hal_kbd_drain_advance();
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    hal_mouse_flush();

    /* Initial full draw */
    settings_menu_draw(lang_idx, focus, 1);
    hal_mouse_draw_cursor_force();

    for (;;) {
        hal_kbd_update();
        hal_mouse_update();

        prev_lang = lang_idx;
        prev_focus = focus;

        /* Keyboard */
        if (hal_kbd_is_down(KC_LEFT)) {
            lang_idx = (lang_idx - 1 + N_LANGS) % N_LANGS;
            hal_kbd_drain_advance();
        }
        if (hal_kbd_is_down(KC_RIGHT)) {
            lang_idx = (lang_idx + 1) % N_LANGS;
            hal_kbd_drain_advance();
        }
        if (hal_kbd_is_down(KC_DOWN) && focus == FOCUS_LANG) {
            focus = FOCUS_START;
            hal_kbd_drain_advance();
        }
        if (hal_kbd_is_down(KC_UP) && focus == FOCUS_START) {
            focus = FOCUS_LANG;
            hal_kbd_drain_advance();
        }
        if (hal_kbd_is_down(KC_SPACE) || hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_XFER)) {
            break;
        }

        /* Mouse click */
        if (hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
            int hit = menu_hittest(hal_mouse_get_x(), hal_mouse_get_y());
            if (hit == 0) {
                lang_idx = (lang_idx - 1 + N_LANGS) % N_LANGS;
            } else if (hit == 1) {
                lang_idx = (lang_idx + 1) % N_LANGS;
            } else if (hit == 2) {
                break;
            }
            hal_mouse_flush();
        }

        /* Redraw: full=2 on language change, full=0 on focus change */
        if (lang_idx != prev_lang) {
            settings_menu_draw(lang_idx, focus, 2);
            hal_mouse_draw_cursor_force();
        } else if (focus != prev_focus) {
            settings_menu_draw(lang_idx, focus, 0);
            hal_mouse_draw_cursor_force();
        }

        hal_mouse_draw_cursor();
    }

    settings_set_lang(LANG_CODES[lang_idx]);
    NB_DEBUG("settings_menu: selected lang=%s (%s)\r\n",
             LANG_NAMES[lang_idx], LANG_CODES[lang_idx]);
}

int settings_file_exists(void)
{
    FILE *f = fopen("settings.txt", "r");
    if (f) {
        fclose(f);
        return 1;
    }
    return 0;
}
