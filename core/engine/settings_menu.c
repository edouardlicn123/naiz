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
 *   full=3: text speed change — restore speed value snapshot + indicators, redraw value only
 *   full=0: focus change — restore indicator snapshots + redraw indicator only
 *   no change: no redraw at all
 *
 * Layout (1x text, 8x16 glyphs):
 *   Naiz Settings                              v0.2.068
 *   > Language  <    English    >              (focus=LANG)
 *   > Text Speed  <  32/s      >               (focus=SPEED)
 *   > Start Game                               (focus=START)
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
#include "tr.h"

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
#define FOCUS_SPEED  1
#define FOCUS_START  2

/* Typewriter speed values (chars/sec; 0 = Instant). Kept in sync with
 * settings.c TEXT_SPEED_* parsing. */
static const int SPD_VALUES[] = { 0, 16, 32, 64 };
#define N_SPEEDS 4

/* Layout constants (1x text) */
#define INDICATOR_X  5      /* > focus indicator (1x) */
#define MENU_X       30     /* all menu text x start */
#define SEL_Y        122    /* language selector row y (1x, 16px tall) */
#define SPD_Y        (SEL_Y + 30)   /* text speed row y (between Lang and Start) */
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

/* Dynamic-content erase regions (matching the old snapshot rectangles).
 * The menu layer's base snapshot doubles as the clean background for these,
 * so no per-widget save buffers are needed (menu_layer_erase_to_base). */
#define IND_SAVE_W   12
#define IND_SAVE_H   18
#define LANG_NAME_SAVE_W 110
#define LANG_NAME_SAVE_H 18
#define SPD_NAME_SAVE_W  128
#define SPD_NAME_SAVE_H  18
#define IND_CLEAR_X  (INDICATOR_X - 2)
#define IND_CLEAR_Y_FIELD  (SEL_Y - 1)    /* language indicator row */
#define IND_CLEAR_Y_SPD    (SPD_Y - 1)    /* text speed indicator row */
#define IND_CLEAR_Y_START  (START_BY - 1) /* start indicator row */
#define LANG_CLEAR_X (LABEL_CX - LANG_NAME_SAVE_W / 2)
#define LANG_CLEAR_Y (SEL_Y - 1)
#define SPD_CLEAR_X  (LABEL_CX - SPD_NAME_SAVE_W / 2)
#define SPD_CLEAR_Y  (SPD_Y - 1)

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

/* Display name for a typewriter speed: Instant (i18n) or "N/s" format. */
static const char *speed_label(int speed)
{
    if (speed == 16) return "16/s";
    if (speed == 32) return "32/s";
    if (speed == 64) return "64/s";
    return tr("Instant");
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

/* Find the current text speed index from settings (default Instant-safe). */
static int find_speed_index(void)
{
    int cur = settings_get_text_speed();
    int i;
    for (i = 0; i < N_SPEEDS; i++) {
        if (SPD_VALUES[i] == cur)
            return i;
    }
    return N_SPEEDS - 1;   /* 32 default */
}

/* Hit test: returns which element was clicked
 * 0 = lang left arrow, 1 = lang right arrow, 2 = start button,
 * 3 = speed left arrow, 4 = speed right arrow, -1 = none */
static int menu_hittest(int mx, int my)
{
    if (mx >= SEL_LX && mx < SEL_LX + ARROW_W &&
        my >= SEL_Y && my < SEL_Y + 20)
        return 0;
    if (mx >= SEL_LX && mx < SEL_LX + ARROW_W &&
        my >= SPD_Y && my < SPD_Y + 20)
        return 3;
    if (mx >= LABEL_X + LABEL_AREA_W + GAP &&
        mx <  LABEL_X + LABEL_AREA_W + GAP + ARROW_W &&
        my >= SEL_Y && my < SEL_Y + 20)
        return 1;
    if (mx >= LABEL_X + LABEL_AREA_W + GAP &&
        mx <  LABEL_X + LABEL_AREA_W + GAP + ARROW_W &&
        my >= SPD_Y && my < SPD_Y + 20)
        return 4;
    if (mx >= START_X && mx < START_X + START_BW &&
        my >= START_BY && my < START_BY + START_BH)
        return 2;
    return -1;
}

/* Draw menu.  full=1: initial full draw — the background is already blitted
 * to VRAM (settings_menu_run, before menu_layer_open) so it lands in the
 * layer's base snapshot; title/static/dynamic content goes into the
 * composite.  full=2: language change — erase the dynamic areas back to the
 * base then redraw.  full=3: text speed change — same for the speed value row.
 * full=0: focus change — erase + redraw indicators only.
 * Every change commits and blits the whole region. */
static void settings_menu_draw(int lang_idx, int speed, int focus, int full)
{
    int tw;

    /* All drawing below routes into the menu layer composite; the base
     * snapshot provides the clean background for the erase step. */
    menu_layer_begin_draw();

    if (full == 1) {
        /* Title: 1x, top-left */
        draw_text_outlined(tr("Naiz Settings"), 0, 20, 10, 1, PAL_WHITE);
        /* Version: 1x, top-right */
        {
            const char *ver = settings_get_version();
            if (ver && *ver)
                draw_text_outlined(ver, 0, 580, 10, 0, PAL_WHITE);
        }
        /* Static menu text (does NOT overlap the dynamic erase areas) */
        draw_text_outlined(tr("Language"), 0, MENU_X, SEL_Y, 0, PAL_WHITE);
        draw_text_outlined("<", 0, SEL_LX + 10, SEL_Y, 0, PAL_WHITE);
        draw_text_outlined(">", 0,
                           LABEL_X + LABEL_AREA_W + GAP + 10, SEL_Y, 0, PAL_WHITE);
        draw_text_outlined(tr("Text Speed"), 0, MENU_X, SPD_Y, 0, PAL_WHITE);
        draw_text_outlined("<", 0, SEL_LX + 10, SPD_Y, 0, PAL_WHITE);
        draw_text_outlined(">", 0,
                           LABEL_X + LABEL_AREA_W + GAP + 10, SPD_Y, 0, PAL_WHITE);
        draw_text_outlined(tr("Start Game"), 0, START_X, START_BY, 0, PAL_WHITE);

        /* Dynamic content (language name / speed value + focus indicator) */
        tw = text_width(LANG_NAMES[lang_idx], 0);
        draw_text_outlined(LANG_NAMES[lang_idx], 0,
                           LABEL_CX - tw / 2, SEL_Y, 0, PAL_WHITE);
        tw = text_width(speed_label(speed), 0);
        draw_text_outlined(speed_label(speed), 0, LABEL_CX - tw / 2, SPD_Y, 0,
                           PAL_WHITE);
        if (focus == FOCUS_LANG)
            draw_text_outlined(">", 0, INDICATOR_X, SEL_Y, 0, PAL_WHITE);
        else if (focus == FOCUS_SPEED)
            draw_text_outlined(">", 0, INDICATOR_X, SPD_Y, 0, PAL_WHITE);
        else if (focus == FOCUS_START)
            draw_text_outlined(">", 0, INDICATOR_X, START_BY, 0, PAL_WHITE);
    }

    if (full == 2) {
        /* Language change: erase the dynamic areas plus all indicators,
         * then redraw the language name with the current focus indicator. */
        menu_layer_erase_to_base(LANG_CLEAR_X, LANG_CLEAR_Y,
                                 LANG_NAME_SAVE_W, LANG_NAME_SAVE_H);
        menu_layer_erase_to_base(IND_CLEAR_X, IND_CLEAR_Y_FIELD, IND_SAVE_W, IND_SAVE_H);
        menu_layer_erase_to_base(IND_CLEAR_X, IND_CLEAR_Y_SPD, IND_SAVE_W, IND_SAVE_H);
        menu_layer_erase_to_base(IND_CLEAR_X, IND_CLEAR_Y_START, IND_SAVE_W, IND_SAVE_H);
        tw = text_width(LANG_NAMES[lang_idx], 0);
        draw_text_outlined(LANG_NAMES[lang_idx], 0,
                           LABEL_CX - tw / 2, SEL_Y, 0, PAL_WHITE);
        if (focus == FOCUS_LANG)
            draw_text_outlined(">", 0, INDICATOR_X, SEL_Y, 0, PAL_WHITE);
        else if (focus == FOCUS_SPEED)
            draw_text_outlined(">", 0, INDICATOR_X, SPD_Y, 0, PAL_WHITE);
        else if (focus == FOCUS_START)
            draw_text_outlined(">", 0, INDICATOR_X, START_BY, 0, PAL_WHITE);
    }

    if (full == 3) {
        /* Text speed change: erase the speed value area plus all indicators,
         * then redraw the value with the current focus indicator. */
        menu_layer_erase_to_base(SPD_CLEAR_X, SPD_CLEAR_Y,
                                 SPD_NAME_SAVE_W, SPD_NAME_SAVE_H);
        menu_layer_erase_to_base(IND_CLEAR_X, IND_CLEAR_Y_FIELD, IND_SAVE_W, IND_SAVE_H);
        menu_layer_erase_to_base(IND_CLEAR_X, IND_CLEAR_Y_SPD, IND_SAVE_W, IND_SAVE_H);
        menu_layer_erase_to_base(IND_CLEAR_X, IND_CLEAR_Y_START, IND_SAVE_W, IND_SAVE_H);
        tw = text_width(speed_label(speed), 0);
        draw_text_outlined(speed_label(speed), 0, LABEL_CX - tw / 2, SPD_Y, 0,
                           PAL_WHITE);
        if (focus == FOCUS_LANG)
            draw_text_outlined(">", 0, INDICATOR_X, SEL_Y, 0, PAL_WHITE);
        else if (focus == FOCUS_SPEED)
            draw_text_outlined(">", 0, INDICATOR_X, SPD_Y, 0, PAL_WHITE);
        else if (focus == FOCUS_START)
            draw_text_outlined(">", 0, INDICATOR_X, START_BY, 0, PAL_WHITE);
    }

    if (full == 0) {
        /* Focus change: erase all indicators, redraw the focused one. */
        menu_layer_erase_to_base(IND_CLEAR_X, IND_CLEAR_Y_FIELD, IND_SAVE_W, IND_SAVE_H);
        menu_layer_erase_to_base(IND_CLEAR_X, IND_CLEAR_Y_SPD, IND_SAVE_W, IND_SAVE_H);
        menu_layer_erase_to_base(IND_CLEAR_X, IND_CLEAR_Y_START, IND_SAVE_W, IND_SAVE_H);
        if (focus == FOCUS_LANG)
            draw_text_outlined(">", 0, INDICATOR_X, SEL_Y, 0, PAL_WHITE);
        else if (focus == FOCUS_SPEED)
            draw_text_outlined(">", 0, INDICATOR_X, SPD_Y, 0, PAL_WHITE);
        else if (focus == FOCUS_START)
            draw_text_outlined(">", 0, INDICATOR_X, START_BY, 0, PAL_WHITE);
    }

    menu_layer_commit();
    menu_layer_blit();
}

void settings_menu_run(void)
{
    int lang_idx = find_lang_index();
    int spd_idx = find_speed_index();
    int focus = FOCUS_LANG;
    int prev_lang, prev_spd, prev_focus;

    NB_DEBUG("settings_menu: enter (default lang=%s)\r\n", LANG_CODES[lang_idx]);

    hal_kbd_drain_advance();
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    hal_mouse_flush();

    /* Background onto VRAM first, so the menu layer's base snapshot captures
     * it (menu widget drawing then composites above the clean background). */
    vblank_wait();
    {
        MagImage *bg_img = image_load(13);
        if (bg_img) {
            vram_blit(bg_img, 0, 0);
            mag_release(bg_img);
        } else {
            fill_rect(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
        }
    }
    menu_layer_open(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);

    /* Initial full draw */
    settings_menu_draw(lang_idx, SPD_VALUES[spd_idx], focus, 1);
    hal_mouse_draw_cursor_force();

    for (;;) {
        hal_kbd_update();
        hal_mouse_update();

        prev_lang = lang_idx;
        prev_spd = spd_idx;
        prev_focus = focus;

        /* Keyboard */
        if (hal_kbd_is_down(KC_LEFT)) {
            if (focus == FOCUS_LANG)
                lang_idx = (lang_idx - 1 + N_LANGS) % N_LANGS;
            else if (focus == FOCUS_SPEED)
                spd_idx = (spd_idx - 1 + N_SPEEDS) % N_SPEEDS;
            hal_kbd_drain_advance();
        }
        if (hal_kbd_is_down(KC_RIGHT)) {
            if (focus == FOCUS_LANG)
                lang_idx = (lang_idx + 1) % N_LANGS;
            else if (focus == FOCUS_SPEED)
                spd_idx = (spd_idx + 1) % N_SPEEDS;
            hal_kbd_drain_advance();
        }
        if (hal_kbd_is_down(KC_DOWN)) {
            if (focus == FOCUS_LANG)
                focus = FOCUS_SPEED;
            else if (focus == FOCUS_SPEED)
                focus = FOCUS_START;
            hal_kbd_drain_advance();
        }
        if (hal_kbd_is_down(KC_UP)) {
            if (focus == FOCUS_START)
                focus = FOCUS_SPEED;
            else if (focus == FOCUS_SPEED)
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
            } else if (hit == 3) {
                spd_idx = (spd_idx - 1 + N_SPEEDS) % N_SPEEDS;
            } else if (hit == 4) {
                spd_idx = (spd_idx + 1) % N_SPEEDS;
            } else if (hit == 2) {
                break;
            }
            hal_mouse_flush();
        }

        /* Redraw: full=2 on language change, full=3 on speed change,
         * full=0 on focus change */
        if (lang_idx != prev_lang) {
            settings_menu_draw(lang_idx, SPD_VALUES[spd_idx], focus, 2);
            hal_mouse_draw_cursor_force();
        } else if (spd_idx != prev_spd) {
            settings_menu_draw(lang_idx, SPD_VALUES[spd_idx], focus, 3);
            hal_mouse_draw_cursor_force();
        } else if (focus != prev_focus) {
            settings_menu_draw(lang_idx, SPD_VALUES[spd_idx], focus, 0);
            hal_mouse_draw_cursor_force();
        }

        hal_mouse_draw_cursor();
    }

    settings_set_lang(LANG_CODES[lang_idx]);
    settings_set_text_speed(SPD_VALUES[spd_idx]);
    menu_layer_close(1);
    NB_DEBUG("settings_menu: selected lang=%s (%s), speed=%d\r\n",
             LANG_NAMES[lang_idx], LANG_CODES[lang_idx], SPD_VALUES[spd_idx]);
}
