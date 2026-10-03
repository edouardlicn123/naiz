/*
 * nb_setting.c — In-game settings scene (LOAD-paradigm full-screen list).
 *
 * Reached from the main menu ("settings" -> setting.nb -> settingmenu()).
 * Layout / behaviour / display conventions follow the save-load slot menu
 * (nb_saveload.c) and the Special menu (nb_special.c): a full-screen fixed
 * layout with embossed rows, page chrome and a bottom-left Back button, plus
 * the focus_on_back model.
 *
 * Each registered setting is one row whose value is stepped in place with
 * the < > arrows — there is no second level: values apply immediately through
 * the row's commit callback (the next dialogue already runs at the new speed)
 * and prefs_save() persists once when the scene is left.
 *
 * Key bindings (deviating from the list menus on purpose):
 *   Up/Down        move focus (rows <-> Back button)
 *   Left/Right     step the focused row's value (wraps); on the Back button
 *                  or a read-only row they turn the page instead
 *   Enter/Space    inert on a setting row (nothing to confirm); leaves the
 *                  scene when the Back button has focus
 *   Esc            leave the scene
 * LEFT/RIGHT are bound to values, so paging is driven by the pager arrows
 * (mouse), by Tab (next page, wrapping), and by LEFT/RIGHT while the Back
 * button or a read-only row has focus (devdoc 118 §6.2 — 7 rows over
 * SETTING_ROWS=4).  There is no Shift-Tab: the HAL exposes no modifier
 * query, so a two-key binding could not be honoured reliably.
 *
 * Language is deliberately NOT registered here: the boot menu
 * (bootmenu.c) runs before the translation table and the CJK font are
 * loaded, so language selection must happen there and only there.
 */
#include <stdio.h>            /* debug.h's NB_DEBUG expands to snprintf */
#include "render.h"
#include "ui.h"
#include "scene_layers.h"
#include "menu_layer.h"
#include "prefs.h"
#include "save.h"
#include "nb_asset_table.h"
#include "hal.h"
#include "nb_internal.h"
#include "nb_commands.h"
#include "nb.h"
#include "tr.h"
#include "debug.h"
#include "input_boundary.h"

/*=== Settings registry ===================================================*/

/* One row of the settings list.  values/labels/commit/current form the
 * single description of a setting: adding one means adding one entry here,
 * nothing else in this file is setting-specific.  labels[i] is the tr() key
 * shown for values[i] (index-aligned, so a value's wording is data, not
 * an if-chain in a per-setting label function). */
/* A row is either a stepping enum (values/labels/current/commit) or a
 * read-only readout, which shows a live formatted string and never steps. */
#define ROW_ENUM     0
#define ROW_READOUT  1

typedef struct {
    const char *label;                   /* tr() key shown left-aligned */
    int         kind;                    /* ROW_ENUM or ROW_READOUT */
    const int  *values;                  /* selectable values, in UI order */
    int         n_values;
    const char *const *labels;           /* tr() keys, index-aligned with values */
    int         cur;                     /* current index, refreshed on entry */
    int       (*current)(void);          /* read the live setting */
    void      (*commit)(int value);      /* apply immediately */
    const char *(*text)(void);           /* ROW_READOUT: live value string */
} SettingRow;

static int text_speed_current(void)
{
    return prefs_get_text_speed();
}

static void text_speed_commit(int value)
{
    prefs_set_text_speed(value);
}

/* Switches: 1 = on, 0 = off. */
static int bgm_on_current(void)   { return prefs_get_bgm_enabled(); }
static int snd_on_current(void)   { return prefs_get_snd_enabled(); }
static int vc_on_current(void)    { return prefs_get_vc_enabled(); }

static void bgm_on_commit(int value)   { prefs_set_bgm_enabled(value); }
static void snd_on_commit(int value)   { prefs_set_snd_enabled(value); }
static void vc_on_commit(int value)    { prefs_set_vc_enabled(value); }

static int bgm_vol_current(void)  { return prefs_get_bgm_volume(); }
static int pcm_vol_current(void)  { return prefs_get_pcm_volume(); }

static void bgm_vol_commit(int value) { prefs_set_bgm_volume(value); }
static void pcm_vol_commit(int value) { prefs_set_pcm_volume(value); }

/* Shared On/Off.  Labels are resolved through tr() at draw time. */
static const int  g_onoff_values[2] = { 1, 0 };
static const char *const g_onoff_labels[2] = { "On", "Off" };

/* Read progress: unlocked CGs over the total the bitmap can hold.  The unlock
 * bitmap is CG_TOTAL bits wide while the asset table may hold more entries,
 * so the numerator is clamped to the bitmap (C6/C29).  Pure numbers, so no
 * tr() — AGENTS.md §14.2 exempts format strings. */
static char g_progress_text[24];

static const char *setting_progress_text(void)
{
    int unlocked = 0;
    int total = CG_COUNT;
    int limit;
    int i;

    if (total > CG_TOTAL)
        total = CG_TOTAL;

    for (i = 1; i <= total; i++)
        if (sys_save_is_cg_unlocked(i))
            unlocked++;

    snprintf(g_progress_text, sizeof(g_progress_text), "%d / %d", unlocked, total);
    return g_progress_text;
}

/* Volume ladders, index-aligned with their label arrays.  BGM is MIDI CC7
 * 0-127 (0% / 50% / 100%); PCM is the A466 attenuation 0-15, REVERSED, so
 * the ladder is ordered loudest-first and its labels are worded, not
 * percentage-based (devdoc 118 §6.4, F02 §4.2). */
static const int  g_bgm_vol_values[PREFS_BGM_VOL_N] = PREFS_BGM_VOL_LADDER;
static const int  g_pcm_vol_values[PREFS_PCM_VOL_N] = PREFS_PCM_VOL_LADDER;
static const char *const g_bgm_vol_labels[PREFS_BGM_VOL_N] = {
    "0%", "50%", "100%"
};
static const char *const g_pcm_vol_labels[PREFS_PCM_VOL_N] = {
    "Max", "High", "Mid", "Low"
};

static SettingRow g_rows[] = {
    { "Text Speed", ROW_ENUM, PREFS_TEXT_SPEEDS, PREFS_TEXT_SPEED_N,
      PREFS_TEXT_SPEED_LABELS, 0, text_speed_current, text_speed_commit, NULL },
    { "BGM", ROW_ENUM, g_onoff_values, 2,
      g_onoff_labels, 0, bgm_on_current, bgm_on_commit, NULL },
    { "Sound Effect", ROW_ENUM, g_onoff_values, 2,
      g_onoff_labels, 0, snd_on_current, snd_on_commit, NULL },
    { "Voice", ROW_ENUM, g_onoff_values, 2,
      g_onoff_labels, 0, vc_on_current, vc_on_commit, NULL },
    { "BGM Volume", ROW_ENUM, g_bgm_vol_values, PREFS_BGM_VOL_N,
      g_bgm_vol_labels, 0, bgm_vol_current, bgm_vol_commit, NULL },
    { "Sound & Voice Vol", ROW_ENUM, g_pcm_vol_values, PREFS_PCM_VOL_N,
      g_pcm_vol_labels, 0, pcm_vol_current, pcm_vol_commit, NULL },
    { "Read Progress", ROW_READOUT, NULL, 0,
      NULL, 0, NULL, NULL, setting_progress_text },
};

#define N_SETTING_ROWS ((int)(sizeof(g_rows) / sizeof(g_rows[0])))

/*=== Layout ==============================================================*/

#define SETTING_ROWS  4                   /* rows per page (load/special parity) */

#define SET_BTN_X     120                 /* row button rect */
#define SET_BTN_W     400
#define SET_BTN_H     44
#define SET_ROW_R     SAVE_SLOT_R
#define SET_IND_LX    (SET_BTN_X + 6)     /* '>' focus indicator */
#define SET_LABEL_X   (SET_BTN_X + 20)    /* setting name, left-aligned */
#define SET_LABEL_W   170
#define SET_ARR_LX    330                 /* '<' arrow */
#define SET_VAL_X     350                 /* value, centered in SET_VAL_W */
#define SET_VAL_W     80
#define SET_ARR_RX    450                 /* '>' arrow */
#define SET_ARR_HIT_W 20                  /* click width around each arrow */
#define SET_TITLE_Y   28
#define SET_ARR_Y     318                 /* pager arrows y */
#define SET_COUNT_Y   330                 /* pager counter y */
#define SET_BACK_Y    352

static const int setting_row_y[SETTING_ROWS] = { 90, 146, 202, 258 };

/*=== Row model ===========================================================*/

/* Index of 'value' in row 'idx' (0 when the setting holds a value outside the
 * list, matching the engine's fall-back-to-default contract). */
static int setting_value_index(int idx, int value)
{
    int i;
    for (i = 0; i < g_rows[idx].n_values; i++) {
        if (g_rows[idx].values[i] == value)
            return i;
    }
    return 0;
}

/* True when the focused row can be stepped; a read-only row cannot, and its
 * LEFT/RIGHT fall through to paging (devdoc 118 §6.5). */
static int setting_row_steppable(int idx)
{
    return g_rows[idx].kind == ROW_ENUM && g_rows[idx].n_values > 0;
}

/* Step row 'idx' by +1/-1 (wrapping) and apply the new value at once. */
static void setting_step(int idx, int step)
{
    SettingRow *r = &g_rows[idx];

    if (!setting_row_steppable(idx))
        return;
    r->cur = (r->cur + step + r->n_values) % r->n_values;
    r->commit(r->values[r->cur]);
}

/* Refresh every row's current index from the live settings. */
static void setting_load_current(void)
{
    int i;
    for (i = 0; i < N_SETTING_ROWS; i++) {
        if (setting_row_steppable(i))
            g_rows[i].cur = setting_value_index(i, g_rows[i].current());
    }
}

/*=== Drawing =============================================================*/

/* One row: label + < value >.  The row button is opaque, so a single interior
 * fill wipes label, value and indicator before the text goes down again —
 * no per-widget clean-background snapshots are needed. */
static void setting_draw_row(int idx, int focused)
{
    const SettingRow *r = &g_rows[idx];
    /* A read-only row shows its live string; an enum row shows a tr()'d key. */
    const char *value = (r->kind == ROW_READOUT) ? r->text() : tr(r->labels[r->cur]);
    int y = setting_row_y[idx];
    int vw = text_width(value, 0);
    int vx = SET_VAL_X + (SET_VAL_W - vw) / 2;
    int max_y = y + SET_BTN_H - 8;       /* draw_text's 6th arg is a max_y */
    uint8_t fg = focused ? MENU_PAL_YELLOW : PAL_WHITE;

    if (vx < SET_VAL_X) vx = SET_VAL_X;

    fill_rect(SET_BTN_X + 4, y + 2, SET_BTN_W - 8, SET_BTN_H - 4, BTN_FILL_IDX);
    draw_text(tr(r->label), 0, SET_LABEL_X, y + 14,
              SET_LABEL_X + SET_LABEL_W, max_y, focused, fg);
    /* No arrows on a read-only row: there is nothing to step. */
    if (r->kind == ROW_ENUM) {
        draw_text("<", 0, SET_ARR_LX, y + 14, SET_ARR_LX + 16, max_y, 0, PAL_WHITE);
        draw_text(">", 0, SET_ARR_RX, y + 14, SET_ARR_RX + 16, max_y, 0, PAL_WHITE);
    }
    draw_text(value, 0, vx, y + 14, SET_VAL_X + SET_VAL_W, max_y, focused, fg);
    if (focused)
        draw_text(">", 0, SET_IND_LX, y + 14, SET_IND_LX + 16, max_y, 1,
                  MENU_PAL_YELLOW);
}

/* Row index at absolute position 'abs' (paging), or -1 past the end. */
static int setting_row_count(int page)
{
    int n = N_SETTING_ROWS - page * SETTING_ROWS;
    if (n > SETTING_ROWS) n = SETTING_ROWS;
    if (n < 1) n = 1;
    return n;
}

/* Absolute index of the row drawn at page-relative 'row'. */
static int setting_row_abs(int page, int row)
{
    return page * SETTING_ROWS + row;
}

/* Single-source-of-truth draw.  full=1 (entry, page turn) repaints the title,
 * the emboss row bodies, the pager and the Back border; incremental passes
 * only relabel the rows and the Back label (AGENTS.md §14 two-stage menu
 * rendering).  'sel' is page-relative. */
static void setting_draw(int page, int sel, int focus_on_back, int total_pages, int full)
{
    int rows = setting_row_count(page);
    int i;

    menu_layer_begin_draw();
    if (full) {
        const char *title = tr("SETTINGS");
        vblank_wait();
        draw_title_large(title,
                         (LAYER_SCREEN_W - text_title_width(title, 4)) / 2,
                         SET_TITLE_Y, 4, PAL_WHITE);
        for (i = 0; i < rows; i++)
            draw_rounded_emboss(SET_BTN_X, setting_row_y[i], SET_BTN_W, SET_BTN_H,
                                SET_ROW_R, BTN_FILL_IDX, BTN_HIGHLIGHT_IDX,
                                BTN_SHADOW_IDX);
        /* Arrows are drawn only once there is a second page to reach. */
        menu_pagenav_draw(SET_ARR_Y, SET_COUNT_Y, PAL_WHITE, page, total_pages);
        menu_back_draw(SET_BACK_Y, focus_on_back, 1, PAL_WHITE);
    }

    for (i = 0; i < rows; i++) {
        int abs = setting_row_abs(page, i);
        setting_draw_row(abs, !focus_on_back && i == sel);
    }

    menu_back_draw(SET_BACK_Y, focus_on_back, 0, PAL_WHITE);

    menu_layer_commit();
    menu_layer_blit();
}

/*=== Input ===============================================================*/

/* Page-relative row index under my, or -1. */
static int setting_row_at(int my)
{
    int i;
    for (i = 0; i < SETTING_ROWS; i++) {
        if (my >= setting_row_y[i] && my < setting_row_y[i] + SET_BTN_H)
            return i;
    }
    return -1;
}

/* Hit-test the row band: 0 none / 1 focus row / 2 step back / 3 step forward.
 * *prow receives the page-relative row index for any hit inside the band. */
static int setting_hittest(int mx, int my, int *prow)
{
    int row = setting_row_at(my);
    *prow = -1;
    if (row < 0) return 0;
    if (mx < SET_BTN_X || mx >= SET_BTN_X + SET_BTN_W) return 0;
    *prow = row;
    if (mx >= SET_ARR_LX - SET_ARR_HIT_W / 2 &&
        mx < SET_ARR_LX + SET_ARR_HIT_W / 2)
        return 2;
    if (mx >= SET_ARR_RX - SET_ARR_HIT_W / 2 &&
        mx < SET_ARR_RX + SET_ARR_HIT_W / 2)
        return 3;
    return 1;
}

/* Return to the menu-parent scene, falling back to the main menu.  The parent
 * is read at exit time so a stale value can never be consumed across a fresh
 * entry (mirrors nb_cggallery.c gallery_return_home). */
static void setting_return_home(void)
{
    const char *ret = nb_get_menu_return();
    scene_switch(ret[0] != '\0' ? ret : "mainmenu.nb", SCENE_SWITCH_MENU);
}

/*=== Command =============================================================*/

/* settingmenu — in-game settings list (script: setting.nb). */
void cmd_settingmenu(int argc, const char **argv, const char *cmd_name)
{
    int page = 0, sel = 0, focus_on_back = 0, running = 1, dirty = 0, total_pages;
    int prev_cur[SETTING_ROWS];
    int rows, i, changed;

    (void)argv;
    (void)cmd_name;
    if (argc > 0)
        NB_DEBUG("settingmenu: takes no arguments, ignoring %d\r\n", argc);

    total_pages = menu_pagecount(N_SETTING_ROWS, SETTING_ROWS);
    rows = setting_row_count(0);
    setting_load_current();

    menu_save_item_palette();
    input_drain_boundary();

    hal_mouse_erase_cursor();
    menu_layer_open(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
    setting_draw(page, sel, focus_on_back, total_pages, 1);
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    hal_mouse_draw_cursor_force();

    while (running) {
        int prev_sel = sel, prev_fb = focus_on_back, prev_page = page;

        for (i = 0; i < rows; i++)
            prev_cur[i] = g_rows[setting_row_abs(page, i)].cur;

        hal_kbd_update();

        if (focus_on_back) {
            if (hal_kbd_is_down(KC_UP)) {
                focus_on_back = 0;
                sel = rows - 1;
            } else if (hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_SPACE) ||
                       hal_kbd_is_down(KC_XFER)) {
                running = 0;
            } else if (hal_kbd_is_down(KC_LEFT) && page > 0) {
                page--;
                sel = 0;
            } else if (hal_kbd_is_down(KC_RIGHT) && page < total_pages - 1) {
                page++;
                sel = 0;
            }
            /* Enter/Space stay inert on a setting row: values apply in place,
             * so there is nothing to confirm. */
        } else {
            if (hal_kbd_is_down(KC_UP)) {
                if (sel > 0) sel--;
            } else if (hal_kbd_is_down(KC_DOWN)) {
                if (sel >= rows - 1) focus_on_back = 1;
                else sel++;
            } else if (hal_kbd_is_down(KC_LEFT)) {
                if (setting_row_steppable(setting_row_abs(page, sel))) {
                    setting_step(setting_row_abs(page, sel), -1);
                    dirty = 1;
                } else if (page > 0) {
                    /* read-only row: LEFT turns the page instead */
                    page--;
                    sel = setting_row_count(page) - 1;
                }
            } else if (hal_kbd_is_down(KC_RIGHT)) {
                if (setting_row_steppable(setting_row_abs(page, sel))) {
                    setting_step(setting_row_abs(page, sel), 1);
                    dirty = 1;
                } else if (page < total_pages - 1) {
                    page++;
                    sel = 0;
                }
            } else if (hal_kbd_is_down(KC_TAB)) {
                /* Tab advances one page and wraps to the first. */
                page = (page + 1) % total_pages;
                sel = 0;
            }
        }
        if (hal_kbd_is_down(KC_ESC))
            running = 0;

        hal_mouse_update();
        hal_mouse_recenter_if_idle();

        if (hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
            int mx = hal_mouse_get_x();
            int my = hal_mouse_get_y();
            int row = -1;
            int hit;

            if (menu_back_hit(SET_BACK_Y, mx, my)) {
                running = 0;
            } else if ((hit = menu_page_hit(SET_ARR_Y, mx, my)) == 1 && page > 0) {
                page--;
                sel = 0;
                rows = setting_row_count(page);
                setting_draw(page, sel, focus_on_back, total_pages, 1);
                hal_mouse_draw_cursor_force();
            } else if ((hit = menu_page_hit(SET_ARR_Y, mx, my)) == 2 &&
                       page < total_pages - 1) {
                page++;
                sel = 0;
                rows = setting_row_count(page);
                setting_draw(page, sel, focus_on_back, total_pages, 1);
                hal_mouse_draw_cursor_force();
            } else if ((hit = setting_hittest(mx, my, &row)) != 0) {
                focus_on_back = 0;
                sel = row;
                if (hit == 2) {
                    setting_step(setting_row_abs(page, sel), -1);
                    dirty = 1;
                } else if (hit == 3) {
                    setting_step(setting_row_abs(page, sel), 1);
                    dirty = 1;
                }
            }
        }

        /* A page turn changes which rows are on screen, so redraw fully. */
        if (page != prev_page) {
            rows = setting_row_count(page);
            if (focus_on_back) sel = rows - 1;
            else if (sel >= rows) sel = rows - 1;
            setting_draw(page, sel, focus_on_back, total_pages, 1);
            hal_mouse_draw_cursor_force();
        } else {
            changed = (sel != prev_sel) || (focus_on_back != prev_fb);
            for (i = 0; i < rows; i++) {
                if (g_rows[setting_row_abs(page, i)].cur != prev_cur[i])
                    changed = 1;
            }
            if (changed)
                setting_draw(page, sel, focus_on_back, total_pages, 0);
        }

        hal_mouse_draw_cursor();
    }
    menu_finish();

    if (dirty && prefs_save() != 0)
        NB_DEBUG("WARN: settingmenu: prefs_save failed\r\n");
    setting_return_home();
}
