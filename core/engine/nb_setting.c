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
 * and settings_save() persists once when the scene is left.
 *
 * Key bindings (deviating from the list menus on purpose):
 *   Up/Down        move focus (rows <-> Back button)
 *   Left/Right     step the focused row's value (wraps)
 *   Enter/Space    inert on a setting row (nothing to confirm); leaves the
 *                  scene when the Back button has focus
 *   Esc            leave the scene
 * There is no paging: LEFT/RIGHT are bound to values and the list is one page
 * short, so the pager draws only its "1/1" counter (visual parity with the
 * load/special menus) and its arrows stay hidden.  Growing the table past
 * SETTING_ROWS means adding a paging state here first.
 *
 * Language is deliberately NOT registered here: the boot menu
 * (settings_menu.c) runs before the translation table and the CJK font are
 * loaded, so language selection must happen there and only there.
 */
#include <stdio.h>            /* debug.h's NB_DEBUG expands to snprintf */
#include "render.h"
#include "ui.h"
#include "scene_layers.h"
#include "menu_layer.h"
#include "settings.h"
#include "hal.h"
#include "nb_internal.h"
#include "nb_commands.h"
#include "nb.h"
#include "tr.h"
#include "debug.h"

/*=== Settings registry ===================================================*/

/* One row of the settings list.  values/labels/commit/current form the
 * single description of a setting: adding one means adding one entry here,
 * nothing else in this file is setting-specific.  labels[i] is the tr() key
 * shown for values[i] (index-aligned, so a value's wording is data, not
 * an if-chain in a per-setting label function). */
typedef struct {
    const char *label;                   /* tr() key shown left-aligned */
    const int  *values;                  /* selectable values, in UI order */
    int         n_values;
    const char *const *labels;           /* tr() keys, index-aligned with values */
    int         cur;                     /* current index, refreshed on entry */
    int       (*current)(void);          /* read the live setting */
    void      (*commit)(int value);      /* apply immediately */
} SettingRow;

static int text_speed_current(void)
{
    return settings_get_text_speed();
}

static void text_speed_commit(int value)
{
    settings_set_text_speed(value);
}

static SettingRow g_rows[] = {
    { "Text Speed", SETTINGS_TEXT_SPEEDS, SETTINGS_TEXT_SPEED_N,
      SETTINGS_TEXT_SPEED_LABELS, 0, text_speed_current, text_speed_commit },
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

/* Step row 'idx' by +1/-1 (wrapping) and apply the new value at once. */
static void setting_step(int idx, int step)
{
    SettingRow *r = &g_rows[idx];
    r->cur = (r->cur + step + r->n_values) % r->n_values;
    r->commit(r->values[r->cur]);
}

/* Refresh every row's current index from the live settings. */
static void setting_load_current(void)
{
    int i;
    for (i = 0; i < N_SETTING_ROWS; i++)
        g_rows[i].cur = setting_value_index(i, g_rows[i].current());
}

/*=== Drawing =============================================================*/

/* One row: label + < value >.  The row button is opaque, so a single interior
 * fill wipes label, value and indicator before the text goes down again —
 * no per-widget clean-background snapshots are needed. */
static void setting_draw_row(int idx, int focused)
{
    const SettingRow *r = &g_rows[idx];
    const char *value = tr(r->labels[r->cur]);
    int y = setting_row_y[idx];
    int vw = text_width(value, 0);
    int vx = SET_VAL_X + (SET_VAL_W - vw) / 2;
    int max_y = y + SET_BTN_H - 8;       /* draw_text's 6th arg is a max_y */
    uint8_t fg = focused ? MENU_PAL_YELLOW : PAL_WHITE;

    if (vx < SET_VAL_X) vx = SET_VAL_X;

    fill_rect(SET_BTN_X + 4, y + 2, SET_BTN_W - 8, SET_BTN_H - 4, BTN_FILL_IDX);
    draw_text(tr(r->label), 0, SET_LABEL_X, y + 14,
              SET_LABEL_X + SET_LABEL_W, max_y, focused, fg);
    draw_text("<", 0, SET_ARR_LX, y + 14, SET_ARR_LX + 16, max_y, 0, PAL_WHITE);
    draw_text(value, 0, vx, y + 14, SET_VAL_X + SET_VAL_W, max_y, focused, fg);
    draw_text(">", 0, SET_ARR_RX, y + 14, SET_ARR_RX + 16, max_y, 0, PAL_WHITE);
    if (focused)
        draw_text(">", 0, SET_IND_LX, y + 14, SET_IND_LX + 16, max_y, 1,
                  MENU_PAL_YELLOW);
}

/* Single-source-of-truth draw.  full=1 (entry) repaints the title, the emboss
 * row bodies, the pager and the Back border; incremental passes only relabel
 * the rows and the Back label (AGENTS.md §14 two-stage menu rendering). */
static void setting_draw(int sel, int focus_on_back, int total_pages, int full)
{
    int i;

    menu_layer_begin_draw();
    if (full) {
        const char *title = tr("SETTINGS");
        vblank_wait();
        draw_title_large(title,
                         (LAYER_SCREEN_W - text_title_width(title, 4)) / 2,
                         SET_TITLE_Y, 4, PAL_WHITE);
        for (i = 0; i < N_SETTING_ROWS; i++)
            draw_rounded_emboss(SET_BTN_X, setting_row_y[i], SET_BTN_W, SET_BTN_H,
                                SET_ROW_R, BTN_FILL_IDX, BTN_HIGHLIGHT_IDX,
                                BTN_SHADOW_IDX);
        menu_pagenav_draw(SET_ARR_Y, SET_COUNT_Y, PAL_WHITE, 0, total_pages);
        menu_back_draw(SET_BACK_Y, focus_on_back, 1, PAL_WHITE);
    }

    for (i = 0; i < N_SETTING_ROWS; i++)
        setting_draw_row(i, !focus_on_back && i == sel);

    menu_back_draw(SET_BACK_Y, focus_on_back, 0, PAL_WHITE);

    menu_layer_commit();
    menu_layer_blit();
}

/*=== Input ===============================================================*/

/* Row index under my, or -1. */
static int setting_row_at(int my)
{
    int i;
    for (i = 0; i < N_SETTING_ROWS; i++) {
        if (my >= setting_row_y[i] && my < setting_row_y[i] + SET_BTN_H)
            return i;
    }
    return -1;
}

/* Hit-test the row band: 0 none / 1 focus row / 2 step back / 3 step forward.
 * *prow receives the row index for any hit inside the band. */
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
    int sel = 0, focus_on_back = 0, running = 1, dirty = 0, total_pages;
    int prev_cur[SETTING_ROWS];
    int i, changed;

    (void)argv;
    (void)cmd_name;
    if (argc > 0)
        NB_DEBUG("settingmenu: takes no arguments, ignoring %d\r\n", argc);
    if (N_SETTING_ROWS > SETTING_ROWS) {
        NB_DEBUG("ERROR: settingmenu: %d settings exceed %d rows per page\r\n",
                 N_SETTING_ROWS, SETTING_ROWS);
        return;
    }

    total_pages = menu_pagecount(N_SETTING_ROWS, SETTING_ROWS);
    setting_load_current();

    menu_save_item_palette();
    hal_kbd_drain_advance();

    hal_mouse_erase_cursor();
    menu_layer_open(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
    setting_draw(sel, focus_on_back, total_pages, 1);
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    hal_mouse_draw_cursor_force();

    while (running) {
        int prev_sel = sel, prev_fb = focus_on_back;

        for (i = 0; i < N_SETTING_ROWS; i++) prev_cur[i] = g_rows[i].cur;

        hal_kbd_update();

        if (focus_on_back) {
            if (hal_kbd_is_down(KC_UP)) {
                focus_on_back = 0;
                sel = N_SETTING_ROWS - 1;
            } else if (hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_SPACE) ||
                       hal_kbd_is_down(KC_XFER)) {
                running = 0;
            }
            /* Enter/Space stay inert on a setting row: values apply in place,
             * so there is nothing to confirm. */
        } else {
            if (hal_kbd_is_down(KC_UP)) {
                if (sel > 0) sel--;
            } else if (hal_kbd_is_down(KC_DOWN)) {
                if (sel >= N_SETTING_ROWS - 1) focus_on_back = 1;
                else sel++;
            } else if (hal_kbd_is_down(KC_LEFT)) {
                setting_step(sel, -1);
                dirty = 1;
            } else if (hal_kbd_is_down(KC_RIGHT)) {
                setting_step(sel, 1);
                dirty = 1;
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
            } else if ((hit = setting_hittest(mx, my, &row)) != 0) {
                focus_on_back = 0;
                sel = row;
                if (hit == 2) {
                    setting_step(sel, -1);
                    dirty = 1;
                } else if (hit == 3) {
                    setting_step(sel, 1);
                    dirty = 1;
                }
            }
        }

        changed = (sel != prev_sel) || (focus_on_back != prev_fb);
        for (i = 0; i < N_SETTING_ROWS; i++) {
            if (g_rows[i].cur != prev_cur[i])
                changed = 1;
        }
        if (changed)
            setting_draw(sel, focus_on_back, total_pages, 0);

        hal_mouse_draw_cursor();
    }
    menu_finish();

    if (dirty && settings_save() != 0)
        NB_DEBUG("WARN: settingmenu: settings_save failed\r\n");
    setting_return_home();
}
