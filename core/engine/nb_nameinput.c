/*
 * nb_nameinput.c — Name-entry page (NB command `nameinput`, devdoc 205).
 *
 * Mirrors the menu-UIs (nb_saveload / nb_setting): a blocking command that
 * owns its input loop, draws into an opaque menu layer (two-phase: expensive
 * emboss once, increments afterwards) and performs its own scene switch.
 *
 * The page edits the "myname" string variable with a physical keyboard and
 * an on-screen ASCII / kana keyboard.  Kana keys are stored as codepoints
 * and converted to UTF-8 at draw time so this source file needs no non-ASCII
 * literals (Watcom source-encoding independent).
 */
#include <stdio.h>
#include <string.h>
#include "render.h"
#include "ui.h"
#include "scene_layers.h"
#include "menu_layer.h"
#include "hal.h"
#include "tr.h"
#include "font.h"
#include "nb_internal.h"
#include "nb_commands.h"
#include "nb_vars.h"
#include "nb.h"
#include "frame.h"
#include "input_boundary.h"
#include "strutil.h"
#include "debug.h"

/*=== Geometry (devdoc 205 §10.1) ==========================================*/

#define NI_TITLE_Y      28
#define NI_SLOT_X       80
#define NI_SLOT_Y       90
#define NI_SLOT_W       480
#define NI_SLOT_H       44
#define NI_NAME_X       100
#define NI_NAME_Y       (NI_SLOT_Y + (NI_SLOT_H - FONT_GLYPH_H) / 2)
#define NI_PROMPT_X     100
#define NI_PROMPT_Y     146

#define NI_KEY_X0       80
#define NI_KEY_Y0       172
#define NI_KEY_W        36
#define NI_KEY_H        28
#define NI_KEY_GAP      3
#define NI_ROW_GAP      4
#define NI_KEY_COLS     12   /* unified grid cols (EN and JP share geometry) */

/* Kana-page codepoint markers reserved for function keys; real kana never
 * reaches these non-characters.  Used only in kana_p*[][10] (SPACE) and
 * kana_p*[][11] (DEL) so every language layout has both actions. */
#define NI_KANA_SPACE_CP 0xFFFEu
#define NI_KANA_DEL_CP   0xFFFFu

#define NI_BTN_Y        330
#define NI_BTN_H        30
#define NI_EN_X         158
#define NI_EN_W         96
#define NI_PAGE_X       266
#define NI_PAGE_W       96
#define NI_VOICE_X      374
#define NI_VOICE_W      96
#define NI_OK_X         494
#define NI_OK_W         80

#define NI_KEYS_BLIT_X  78
#define NI_KEYS_BLIT_Y  170
#define NI_KEYS_BLIT_W  484
#define NI_KEYS_BLIT_H  130

#define NI_MAXLEN_FALLBACK 12

/*=== Keyboard layout tables ===============================================*/

static const char *const en_rows[4][12] = {
    {"A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"},
    {"M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X"},
    {"Y", "Z", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"},
    {"'", "-", "?", "!", "@", "#", NULL, NULL, NULL, NULL, "SPACE", "DEL"}
};

/* Kana pages as Unicode codepoints; 0 = empty cell, 0xFFFE = SPACE,
 * 0xFFFF = DEL (NI_KANA_SPACE_CP / NI_KANA_DEL_CP).  Every page carries
 * SPACE and DEL in row 4, cols 10/11 so both actions are reachable in
 * every layout (devdoc 205 实机反馈). */

static const unsigned short kana_p1[4][12] = {
    {0x3042, 0x3044, 0x3046, 0x3048, 0x304A, 0x304B, 0x304D, 0x304F, 0x3051, 0x3053, 0x3055, 0x3057},
    {0x3059, 0x305B, 0x305D, 0x305F, 0x3061, 0x3064, 0x3066, 0x3068, 0x306A, 0x306B, 0x306C, 0x306D},
    {0x306E, 0x306F, 0x3072, 0x3075, 0x3078, 0x307B, 0x307E, 0x307F, 0x3080, 0x3081, 0x3082, 0x3084},
    {0x3086, 0x3088, 0x3089, 0x308A, 0x308B, 0x308C, 0x308D, 0x308F, 0x3092, 0x3093, NI_KANA_SPACE_CP, NI_KANA_DEL_CP}
};

static const unsigned short kana_p2[4][12] = {
    {0x304C, 0x304E, 0x3050, 0x3052, 0x3054, 0x3056, 0x3058, 0x305A, 0x305C, 0x305E, 0x3060, 0x3062},
    {0x3065, 0x3067, 0x3069, 0x3070, 0x3073, 0x3076, 0x3079, 0x307C, 0x3071, 0x3074, 0x3077, 0x307A},
    {0x307D, 0x3041, 0x3043, 0x3045, 0x3047, 0x3049, 0x3063, 0x3083, 0x3085, 0x3087, 0x3089, 0x308A},
    {0x308B, 0x308C, 0x308D, 0x308F, 0x3092, 0x3093, 0x0000, 0x0000, 0x0000, 0x0000, NI_KANA_SPACE_CP, NI_KANA_DEL_CP}
};

static const unsigned short kana_p3[4][12] = {
    {0x30A2, 0x30A4, 0x30A6, 0x30A8, 0x30AA, 0x30AB, 0x30AD, 0x30AF, 0x30B1, 0x30B3, 0x30B5, 0x30B7},
    {0x30B9, 0x30BB, 0x30BD, 0x30BF, 0x30C1, 0x30C4, 0x30C6, 0x30C8, 0x30CA, 0x30CB, 0x30CC, 0x30CD},
    {0x30CE, 0x30CF, 0x30D2, 0x30D5, 0x30D8, 0x30DB, 0x30DE, 0x30DF, 0x30E0, 0x30E1, 0x30E2, 0x30E4},
    {0x30E6, 0x30E8, 0x30E9, 0x30EA, 0x30EB, 0x30EC, 0x30ED, 0x30EF, 0x30F2, 0x30F3, NI_KANA_SPACE_CP, NI_KANA_DEL_CP}
};

static const unsigned short kana_p4[4][12] = {
    {0x30AC, 0x30AE, 0x30B0, 0x30B2, 0x30B4, 0x30B6, 0x30B8, 0x30BA, 0x30BC, 0x30BE, 0x30C0, 0x30C2},
    {0x30C5, 0x30C7, 0x30C9, 0x30D0, 0x30D3, 0x30D6, 0x30D9, 0x30DC, 0x30D1, 0x30D4, 0x30D7, 0x30DA},
    {0x30DD, 0x30A1, 0x30A3, 0x30A5, 0x30A7, 0x30A9, 0x30C3, 0x30E3, 0x30E5, 0x30E7, 0x30E9, 0x30EA},
    {0x30EB, 0x30EC, 0x30ED, 0x30EF, 0x30F2, 0x30F3, 0x0000, 0x0000, 0x0000, 0x0000, NI_KANA_SPACE_CP, NI_KANA_DEL_CP}
};

/* Page button glyphs: あ / が / ア / ガ */
static const unsigned short kana_page_label[4] = {
    0x3042, 0x304C, 0x30A2, 0x30AC
};

static const unsigned short *const kana_pages[4] = {
    kana_p1[0], kana_p2[0], kana_p3[0], kana_p4[0]
};

/*=== State ================================================================*/

typedef struct {
    char name[NB_VAR_STR_MAX];
    int  layout;    /* 0 = ASCII, 1 = kana */
    int  page;      /* 0..3 */
    int  sel_row;
    int  sel_col;
} NameInputState;

/*=== Helpers ==============================================================*/

static void ni_cp_to_utf8(unsigned short cp, char out[4])
{
    if (cp < 0x80) {
        out[0] = (char)cp;
        out[1] = '\0';
    } else if (cp < 0x800) {
        out[0] = (char)(0xC0 | (cp >> 6));
        out[1] = (char)(0x80 | (cp & 0x3F));
        out[2] = '\0';
    } else {
        out[0] = (char)(0xE0 | (cp >> 12));
        out[1] = (char)(0x80 | ((cp >> 6) & 0x3F));
        out[2] = (char)(0x80 | (cp & 0x3F));
        out[3] = '\0';
    }
}

static int ni_in_rect(int px, int py, int x, int y, int w, int h)
{
    return px >= x && px < x + w && py >= y && py < y + h;
}

static int ni_cols(const NameInputState *st)
{
    (void)st;
    return NI_KEY_COLS;
}

static void ni_reset_sel(NameInputState *st)
{
    st->sel_row = 0;
    st->sel_col = 0;
}

/* Cell text.  ASCII cells return their static label; kana cells are encoded
 * into buf.  NULL = empty cell. */
static const char *ni_cell_text(const NameInputState *st, int row, int col, char buf[4])
{
    unsigned short cp;

    if (row < 0 || row >= 4 || col < 0 || col >= NI_KEY_COLS)
        return NULL;
    if (st->layout == 0)
        return en_rows[row][col];

    cp = kana_pages[st->page][row * NI_KEY_COLS + col];
    if (cp == 0) return NULL;
    if (cp == NI_KANA_SPACE_CP) return "SPACE";
    if (cp == NI_KANA_DEL_CP)   return "DEL";
    ni_cp_to_utf8(cp, buf);
    return buf;
}

static void ni_key_rect(const NameInputState *st, int row, int col,
                        int *x, int *y, int *w, int *h)
{
    (void)st;
    *x = NI_KEY_X0 + col * (NI_KEY_W + NI_KEY_GAP);
    *w = NI_KEY_W;
    *y = NI_KEY_Y0 + row * (NI_KEY_H + NI_ROW_GAP);
    *h = NI_KEY_H;
}

/* Append one UTF-8 string if it fits both the codepoint and byte budget. */
static int ni_append(NameInputState *st, const char *s, int maxlen)
{
    int cur, add_cps, cur_bytes, add_bytes;

    if (!s || s[0] == '\0') return 0;
    cur = utf8_len_cps(st->name);
    add_cps = utf8_len_cps(s);
    cur_bytes = (int)strlen(st->name);
    add_bytes = (int)strlen(s);
    if (cur + add_cps > maxlen) {
        NB_DEBUG("nameinput: maxlen %d reached\r\n", maxlen);
        return 0;
    }
    if (cur_bytes + add_bytes >= NB_VAR_STR_MAX) return 0;
    memcpy(st->name + cur_bytes, s, (size_t)add_bytes);
    st->name[cur_bytes + add_bytes] = '\0';
    return 1;
}

/* Delete the last codepoint (not just the last byte). */
static int ni_backspace(NameInputState *st)
{
    int n = (int)strlen(st->name);

    if (n <= 0) return 0;
    n--;
    while (n > 0 && ((unsigned char)st->name[n] & 0xC0) == 0x80) n--;
    st->name[n] = '\0';
    return 1;
}

/* Trim ASCII spaces at both ends; an all-space name becomes empty. */
static void ni_trim(char *s)
{
    int start = 0;
    int n = (int)strlen(s);

    while (start < n && s[start] == ' ') start++;
    while (n > start && s[n - 1] == ' ') n--;
    if (start > 0) memmove(s, s + start, (size_t)(n - start));
    s[n - start] = '\0';
}

/* Activate the highlighted cell.  Returns 1 when the name buffer changed. */
static int ni_activate(NameInputState *st, int maxlen)
{
    char buf[4];
    const char *label = ni_cell_text(st, st->sel_row, st->sel_col, buf);

    if (!label) return 0;
    if (strcmp(label, "DEL") == 0)
        return ni_backspace(st);
    if (strcmp(label, "SPACE") == 0)
        return ni_append(st, " ", maxlen);
    return ni_append(st, label, maxlen);
}

/*=== Drawing ==============================================================*/

static void ni_draw_btn_frame(int x, int w)
{
    draw_rounded_emboss(x, NI_BTN_Y, w, NI_BTN_H, 4,
                        BTN_FILL_IDX, BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX);
}

static void ni_draw_btn_label(int x, int w, const char *label, int bold)
{
    /* Match menu_back_draw: text is drawn directly over the rounded-emboss
     * bevel (BTN_FILL_IDX inner area + BTN_HIGHLIGHT_IDX/BTN_SHADOW_IDX rim
     * show through).  The earlier version added a fill_rect that covered the
     * bevel with flat color, making these buttons look unrelated to the Back
     * button which sits next to them on the same row (devdoc 205 实机反馈). */
    int tw, tx;

    if (!label || label[0] == '\0') return;
    tw = text_width(label, bold);
    tx = x + (w - tw) / 2;
    if (tx < x + 2) tx = x + 2;
    draw_text(label, 0, tx, NI_BTN_Y + 7, x + w - 2, NI_BTN_Y + NI_BTN_H,
              bold, MENU_PAL_WHITE);
}

static void ni_draw_name(const NameInputState *st)
{
    int tw;

    fill_rect(NI_SLOT_X + 5, NI_SLOT_Y + 5,
              NI_SLOT_W - 10, NI_SLOT_H - 10, BTN_FILL_IDX);
    draw_text(st->name, 0, NI_NAME_X, NI_NAME_Y,
              NI_SLOT_X + NI_SLOT_W - 8, NI_SLOT_Y + NI_SLOT_H,
              1, PAL_WHITE);
    tw = text_width(st->name, 1);
    if (NI_NAME_X + tw < NI_SLOT_X + NI_SLOT_W - 12)
        draw_text("_", 0, NI_NAME_X + tw, NI_NAME_Y,
                  NI_SLOT_X + NI_SLOT_W - 6, NI_SLOT_Y + NI_SLOT_H,
                  0, MENU_PAL_YELLOW);
}

static void ni_draw_key(const NameInputState *st, int row, int col)
{
    char buf[4];
    const char *label = ni_cell_text(st, row, col, buf);
    int x, y, w, h, focus, tw, tx;

    ni_key_rect(st, row, col, &x, &y, &w, &h);
    focus = (row == st->sel_row && col == st->sel_col);
    fill_rect(x, y, w, h, BTN_FILL_IDX);
    draw_rect(x, y, w, h, 1,
              focus ? MENU_PAL_YELLOW : BTN_HIGHLIGHT_IDX);
    if (!label) return;
    tw = text_width(label, 0);
    tx = x + (w - tw) / 2;
    if (tx < x + 1) tx = x + 1;
    draw_text(label, 0, tx, y + (h - FONT_GLYPH_H) / 2,
              x + w - 1, y + h, 0,
              focus ? MENU_PAL_YELLOW : MENU_PAL_WHITE);
}

static void ni_draw_keyboard(const NameInputState *st)
{
    int r, c;
    int cols = ni_cols(st);

    for (r = 0; r < 4; r++)
        for (c = 0; c < cols; c++)
            ni_draw_key(st, r, c);
}

static void ni_draw_bottom_labels(const NameInputState *st)
{
    char buf[4];

    ni_draw_btn_label(NI_EN_X, NI_EN_W, st->layout == 0 ? "EN" : "JP", 0);
    if (st->layout == 0) {
        ni_draw_btn_label(NI_PAGE_X, NI_PAGE_W, "", 0);
        ni_draw_btn_label(NI_VOICE_X, NI_VOICE_W, "", 0);
    } else {
        ni_cp_to_utf8(kana_page_label[st->page], buf);
        ni_draw_btn_label(NI_PAGE_X, NI_PAGE_W, buf, 1);
        ni_draw_btn_label(NI_VOICE_X, NI_VOICE_W, tr("VOICE"), 0);
    }
    /* OK label is redrawn here too — publish_bottom erase_to_base wipes the
     * whole bottom strip, so every label (including OK) must be repainted
     * or it vanishes after the first EN↔JP toggle (devdoc 205 实机 bug). */
    ni_draw_btn_label(NI_OK_X, NI_OK_W, tr("OK"), 1);
}

static void ni_draw_static(const NameInputState *st)
{
    const char *title = tr("NAME");
    int tw = text_title_width(title, 4);
    int tx = (LAYER_SCREEN_W - tw) / 2;

    if (tx < 0) tx = 0;
    draw_title_large(title, tx, NI_TITLE_Y, 4, PAL_WHITE);

    draw_rounded_emboss(NI_SLOT_X, NI_SLOT_Y, NI_SLOT_W, NI_SLOT_H,
                        SAVE_SLOT_R, BTN_FILL_IDX,
                        BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX);
    ni_draw_name(st);

    draw_text(tr("Enter your name"), 0, NI_PROMPT_X, NI_PROMPT_Y,
              560, NI_PROMPT_Y + FONT_GLYPH_H, 0, PAL_WHITE);

    ni_draw_keyboard(st);

    menu_back_draw(NI_BTN_Y, 0, 1, PAL_WHITE);
    ni_draw_btn_frame(NI_EN_X, NI_EN_W);
    ni_draw_btn_frame(NI_PAGE_X, NI_PAGE_W);
    ni_draw_btn_frame(NI_VOICE_X, NI_VOICE_W);
    ni_draw_btn_frame(NI_OK_X, NI_OK_W);
    ni_draw_bottom_labels(st);
}

/*=== Incremental publishers (two-phase rule, AGENTS §14) =================*/

static void ni_publish_name(const NameInputState *st)
{
    /* invalidate_cursor = erase saved arrow + mark invalid.  The layer write
     * below blits over this region, so a stale saved background would
     * otherwise be restored by the next cursor_render.  cursor_render itself
     * (main-loop tail) re-captures whenever valid==0, so no force-redraw
     * needed here — forcing would block on vblank_wait and stack on top of
     * engine_frame_pump's own vblank, stalling click bursts (devdoc 205
     * 实机: 快速连点 layout 切换卡成 ~20fps). */
    hal_mouse_invalidate_cursor();
    menu_layer_begin_draw();
    ni_draw_name(st);
    menu_layer_commit();
    menu_layer_blit_rect(NI_SLOT_X + 4, NI_SLOT_Y + 4,
                         NI_SLOT_W - 8, NI_SLOT_H - 8);
}

static void ni_publish_keys(const NameInputState *st)
{
    hal_mouse_invalidate_cursor();
    menu_layer_begin_draw();
    menu_layer_erase_to_base(NI_KEYS_BLIT_X, NI_KEYS_BLIT_Y,
                             NI_KEYS_BLIT_W, NI_KEYS_BLIT_H);
    ni_draw_keyboard(st);
    menu_layer_commit();
    menu_layer_blit_rect(NI_KEYS_BLIT_X, NI_KEYS_BLIT_Y,
                         NI_KEYS_BLIT_W, NI_KEYS_BLIT_H);
}

static void ni_publish_bottom(const NameInputState *st)
{
    /* Width = 426 covers EN(96) + gap + PAGE(96) + gap + VOICE(96) + gap
     * + OK(80) = 426 starting at 158.  The full strip is erased so stale
     * labels (EN→JP switch clears PAGE/VOICE) and stale frame bevels never
     * ghost; frame bevels are redrawn here too because erase_to_base wipes
     * the rounded-emboss drawn once in ni_draw_static (devdoc 205 实机:
     * toggle EN↔JP → OK/PAGE/VOICE/EN frames vanish, only click hitboxes
     * remain — Back frame survived because its x=66 lies outside the erase
     * rect starting at 156). */
    hal_mouse_invalidate_cursor();
    menu_layer_begin_draw();
    menu_layer_erase_to_base(NI_EN_X - 2, NI_BTN_Y - 2, 426, NI_BTN_H + 4);
    ni_draw_btn_frame(NI_EN_X, NI_EN_W);
    ni_draw_btn_frame(NI_PAGE_X, NI_PAGE_W);
    ni_draw_btn_frame(NI_VOICE_X, NI_VOICE_W);
    ni_draw_btn_frame(NI_OK_X, NI_OK_W);
    ni_draw_bottom_labels(st);
    menu_layer_commit();
    menu_layer_blit_rect(NI_EN_X - 2, NI_BTN_Y - 2, 426, NI_BTN_H + 4);
}

/*=== Exits ================================================================*/

/* OK: trim, fall back to the variable default (never an empty name), save,
 * close the menu layer, drain the click, then switch scenes. */
static void ni_exit_start(int myname_idx, const char *name)
{
    char final_name[NB_VAR_STR_MAX];

    str_copy(final_name, sizeof(final_name), name);
    ni_trim(final_name);
    if (final_name[0] == '\0')
        str_copy(final_name, sizeof(final_name),
                 myname_idx >= 0 ? nb_var_default_str(myname_idx) : "me");
    if (myname_idx >= 0)
        nb_var_set_str(myname_idx, final_name);
    NB_DEBUG("nameinput: accepted name '%s'\r\n", final_name);
    menu_finish();
    input_drain_boundary();
    scene_switch("nbook001.nb", SCENE_SWITCH_MENU);
}

/* Back: keep the variable untouched and return to the main menu. */
static void ni_exit_back(void)
{
    NB_DEBUG("nameinput: cancelled\r\n");
    menu_finish();
    input_drain_boundary();
    scene_switch("mainmenu.nb", SCENE_SWITCH_MENU);
}

/*=== Command handler ======================================================*/

void cmd_nameinput(int argc, const char **argv, const char *cmd_name)
{
    NameInputState st;
    int myname_idx;
    int maxlen;

    (void)argv;
    (void)cmd_name;
    if (argc > 0)
        NB_DEBUG("nameinput: arguments ignored (argc=%d)\r\n", argc);

    myname_idx = nb_var_lookup("myname");
    maxlen = NB_VAR_MAXLEN > 0 ? NB_VAR_MAXLEN : NI_MAXLEN_FALLBACK;

    str_copy(st.name, sizeof(st.name),
             myname_idx >= 0 ? nb_var_get_str(myname_idx) : "");
    if (st.name[0] == '\0')
        str_copy(st.name, sizeof(st.name),
                 myname_idx >= 0 ? nb_var_default_str(myname_idx) : "me");
    utf8_truncate_cps(st.name, maxlen, NB_VAR_STR_MAX - 1);
    st.layout = 0;
    st.page = 0;
    ni_reset_sel(&st);

#ifdef AUTOEXIT
    NB_DEBUG("nameinput: auto-accept\r\n");
    ni_exit_start(myname_idx, st.name);
    return;
#endif

    input_drain_boundary();
    hal_mouse_erase_cursor();
    menu_save_item_palette();
    menu_layer_open(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
    ni_draw_static(&st);
    menu_layer_commit();
    menu_layer_blit();
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    hal_mouse_flush();

    for (;;) {
        unsigned char ch;
        int redraw_name = 0;
        int redraw_keys = 0;
        int redraw_bottom = 0;
        int used_char = 0;

        engine_frame_pump();
        hal_kbd_update();
        hal_mouse_update();

        /* Physical typing.  '%' is reserved for the %myname% token. */
        while ((ch = hal_kbd_get_char()) != 0) {
            char one[2];
            if (ch == '%') continue;
            one[0] = (char)ch;
            one[1] = '\0';
            if (ni_append(&st, one, maxlen)) redraw_name = 1;
            used_char = 1;
        }

        /* Scan-key semantics are skipped on frames that already consumed a
         * character, so a typed space never also activates the highlighted
         * key (Space is both a character and a confirm key). */
        if (!used_char) {
            if (hal_kbd_is_down(KC_BS)) {
                if (ni_backspace(&st)) redraw_name = 1;
            }
            if (hal_kbd_is_down(KC_TAB)) {
                st.layout = !st.layout;
                st.page = 0;
                ni_reset_sel(&st);
                redraw_keys = 1;
                redraw_bottom = 1;
            }
            if (st.layout && hal_kbd_is_down(KC_HOME)) {
                st.page = (st.page + 1) % 4;
                ni_reset_sel(&st);
                redraw_keys = 1;
                redraw_bottom = 1;
            }
            if (hal_kbd_is_down(KC_UP) && st.sel_row > 0) {
                st.sel_row--;
                redraw_keys = 1;
            }
            if (hal_kbd_is_down(KC_DOWN) && st.sel_row < 3) {
                st.sel_row++;
                redraw_keys = 1;
            }
            if (hal_kbd_is_down(KC_LEFT) && st.sel_col > 0) {
                st.sel_col--;
                redraw_keys = 1;
            }
            if (hal_kbd_is_down(KC_RIGHT) && st.sel_col < ni_cols(&st) - 1) {
                st.sel_col++;
                redraw_keys = 1;
            }
            if (hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_XFER)) {
                if (ni_activate(&st, maxlen)) redraw_name = 1;
            }
        }

        if (hal_kbd_is_down(KC_ESC)) {
            ni_exit_back();
            return;
        }

        if (hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
            int mx = hal_mouse_get_x();
            int my = hal_mouse_get_y();
            int r, c;
            int hit_key = 0;

            if (menu_back_hit(NI_BTN_Y, mx, my)) {
                ni_exit_back();
                return;
            }
            if (ni_in_rect(mx, my, NI_OK_X, NI_BTN_Y, NI_OK_W, NI_BTN_H)) {
                ni_exit_start(myname_idx, st.name);
                return;
            }
            if (ni_in_rect(mx, my, NI_EN_X, NI_BTN_Y, NI_EN_W, NI_BTN_H)) {
                st.layout = !st.layout;
                st.page = 0;
                ni_reset_sel(&st);
                redraw_keys = 1;
                redraw_bottom = 1;
            } else if (st.layout &&
                       ni_in_rect(mx, my, NI_PAGE_X, NI_BTN_Y, NI_PAGE_W, NI_BTN_H)) {
                st.page = (st.page + 1) % 4;
                ni_reset_sel(&st);
                redraw_keys = 1;
                redraw_bottom = 1;
            } else if (st.layout &&
                       ni_in_rect(mx, my, NI_VOICE_X, NI_BTN_Y, NI_VOICE_W, NI_BTN_H)) {
                st.page ^= 1;          /* unvoiced <-> voiced, same kana type */
                ni_reset_sel(&st);
                redraw_keys = 1;
                redraw_bottom = 1;
            } else {
                for (r = 0; r < 4 && !hit_key; r++) {
                    for (c = 0; c < ni_cols(&st); c++) {
                        int kx, ky, kw, kh;
                        ni_key_rect(&st, r, c, &kx, &ky, &kw, &kh);
                        if (!ni_in_rect(mx, my, kx, ky, kw, kh)) continue;
                        st.sel_row = r;
                        st.sel_col = c;
                        if (ni_activate(&st, maxlen)) redraw_name = 1;
                        redraw_keys = 1;
                        hit_key = 1;
                        break;
                    }
                }
            }
        }

        if (redraw_name) ni_publish_name(&st);
        if (redraw_keys) ni_publish_keys(&st);
        if (redraw_bottom) ni_publish_bottom(&st);

        /* Shared menu-loop contract (AGENTS §14 — menu UI): repaint the
         * software cursor every frame so it follows unidle mouse movement.
         * menu_show() does this unconditionally; omitting it here lets the
         * arrow stay frozen while the user drags, then snaps only on the
         * next publish trigger (keyboard input / button toggle). */
        hal_mouse_draw_cursor();
    }
}
