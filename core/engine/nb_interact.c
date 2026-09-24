/*
 * nb_interact.c — blocking option-list interaction primitive (ui_interact).
 *
 * Stage 1 of devdoc 103: cmd_question's option blocking loop converges here
 * so the choice UI is a single reusable interaction point.  The dialog-band
 * option rendering, hit testing, keyboard navigation and 600-frame timeout
 * are preserved byte-for-byte from nb_question.c; only the "loop + input
 * read" was relocated into ui_interact().
 *
 * Labels must already be tr()'d by the caller (see UiRequest in
 * nb_internal.h); the caller owns palette save/restore around the call.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "render.h"
#include "ui.h"
#include "scene_layers.h"
#include "hal.h"
#include "nb_internal.h"
#include "tr.h"

/* Debug logging — shared macro in debug.h */
#include "debug.h"

/* Hit-test the option rows within the dialog content band.  Mirrors the
 * legacy question_hittest geometry (base_x + 448 width). */
static int interact_hittest(int mx, int my, int num_opts)
{
    int i;
    int base_x = LAYER_DIALOG_CONTENT_X + QUESTION_INDENT;
    int base_y = LAYER_DIALOG_CONTENT_Y;
    for (i = 0; i < num_opts; i++) {
        int y0 = base_y + i * MENU_ITEM_H;
        if (mx >= base_x && mx < base_x + 448 &&
            my >= y0    && my < y0 + MENU_ITEM_H)
            return i;
    }
    return -1;
}

/* Draw one option row: emboss outline + label.  Mirrors the legacy
 * question_draw_opt rendering. */
static void interact_draw_opt(const char *label, int i, int y, int mw, int highlighted)
{
    int pal = highlighted ? MENU_PAL_YELLOW : MENU_PAL_WHITE;
    int x = LAYER_DIALOG_CONTENT_X + QUESTION_INDENT;
    int opt_y = y + i * MENU_ITEM_H;
    draw_rounded_emboss_outline(x - 2, opt_y - 1, mw + 4, MENU_ITEM_H, 2,
                                BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX);
    draw_text(label, 0, x, opt_y, mw - 8, opt_y + MENU_ITEM_H, 1, pal);
}

int ui_interact(const UiRequest *req)
{
    int sel;
    int i, y, mw, n;
    int q_timeout = 600;

    if (!req || req->n < 1 || !req->labels) {
        NB_DEBUG("interact: invalid request\r\n");
        return -1;
    }

    n = req->n;
    sel = (req->focus0 >= 0 && req->focus0 < n) ? req->focus0 : 0;
    mw = LAYER_DIALOG_CONTENT_W;
    y = LAYER_DIALOG_CONTENT_Y;

    /* Initial option list render (focus highlighted). */
    for (i = 0; i < n; i++)
        interact_draw_opt(req->labels[i], i, y, mw, i == sel);

    hal_kbd_drain_advance();
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    hal_mouse_flush();

    for (;;) {
        if (--q_timeout <= 0) {
            NB_DEBUG("interact: timeout\r\n");
            return -1;
        }

        hal_kbd_update();
        hal_mouse_update();
        hal_mouse_recenter_if_idle();

        if (hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
            int hit = interact_hittest(hal_mouse_get_x(), hal_mouse_get_y(), n);
            if (hit >= 0) {
                NB_DEBUG("interact: mouse sel=%d\r\n", hit);
                return hit;
            }
        }

        if (hal_kbd_is_down(KC_UP) && sel > 0) {
            interact_draw_opt(req->labels[sel], sel, y, mw, 0);
            sel--;
            interact_draw_opt(req->labels[sel], sel, y, mw, 1);
            menu_consume_key(KC_UP);
        }
        if (hal_kbd_is_down(KC_DOWN) && sel < n - 1) {
            interact_draw_opt(req->labels[sel], sel, y, mw, 0);
            sel++;
            interact_draw_opt(req->labels[sel], sel, y, mw, 1);
            menu_consume_key(KC_DOWN);
        }
        if (hal_kbd_is_down(KC_SPACE) || hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_XFER)) {
            NB_DEBUG("interact: keyboard sel=%d\r\n", sel);
            return sel;
        }

        hal_mouse_draw_cursor();
    }
}
