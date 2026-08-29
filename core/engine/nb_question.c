/*
 * nb_question.c — NB question/choice command (cmd_question) and helpers.
 *
 * Split from nb_commands.c: question menu hit testing, option drawing and
 * the question command handler.  Registered in nb_commands.c cmd_table.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include "vm.h"
#include "render.h"
#include "ui.h"
#include "scene_layers.h"
#include "hal.h"
#include "tr.h"
#include "nb_internal.h"
#include "nb_vars.h"
#include "debug.h"
#include "nb_commands.h"

static int question_hittest(int mx, int my, int num_opts)
{
    int i;
    int base_x = LAYER_DIALOG_X + LAYER_DIALOG_INDENT + QUESTION_INDENT;
    int base_y = LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y;
    for (i = 0; i < num_opts; i++) {
        int y0 = base_y + i * MENU_ITEM_H;
        if (mx >= base_x && mx < base_x + 448 &&
            my >= y0    && my < y0 + MENU_ITEM_H)
            return i;
    }
    return -1;
}

static void question_draw_opt(const char *label, int i, int y, int mw, int highlighted)
{
    int pal = highlighted ? MENU_PAL_YELLOW : MENU_PAL_WHITE;
    int x = LAYER_DIALOG_X + LAYER_DIALOG_INDENT + QUESTION_INDENT;
    int opt_y = y + i * MENU_ITEM_H;
    draw_rounded_emboss_outline(x - 2, opt_y - 1, mw + 4, MENU_ITEM_H, 2,
                                BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX);
    draw_text(tr(label), 0,
              x, opt_y,
              mw - 8, opt_y + MENU_ITEM_H, 1, pal);
}

void cmd_question(int argc, const char **argv, const char *cmd_name)
{
    int sel = 0;
    int i, y, mw, num_opts, valid_opts, total_opts, display_opts;
    char opt_labels[10][64];
    char opt_vars[10][32];
    char opt_ops[10][4];
    int  opt_deltas[10];

    (void)cmd_name;
    if (argc < 2) { NB_DEBUG("question: not enough args\r\n"); return; }

    /* Parse option segments: each argv[1..N] is "opt,var,deltar" */
    num_opts = argc - 1;
    if (num_opts > 10) {
        NB_DEBUG("WARN: question options=%d truncated to 10\r\n", num_opts);
        num_opts = 10;
    }

    memset(opt_labels, 0, sizeof(opt_labels));
    memset(opt_vars, 0, sizeof(opt_vars));
    memset(opt_ops, 0, sizeof(opt_ops));
    memset(opt_deltas, 0, sizeof(opt_deltas));
    valid_opts = 0;

    for (i = 0; i < num_opts; i++) {
        const char *p = argv[i + 1];

        if (!nb_next_field(&p, opt_labels[valid_opts], sizeof(opt_labels[0])))
            continue;
        if (!nb_next_field(&p, opt_vars[valid_opts], sizeof(opt_vars[0])))
            continue;
        if (!nb_next_field(&p, opt_ops[valid_opts], sizeof(opt_ops[0])))
            continue;
        while (*p == ' ' || *p == '\t') p++;
        opt_deltas[valid_opts] = atoi(p);
        valid_opts++;
    }

    total_opts = valid_opts;
    if (total_opts < 1) { NB_DEBUG("question: no valid options\r\n"); return; }

    display_opts = total_opts;
    if (display_opts > 4) {
        NB_DEBUG("WARN: question: %d options, displaying 4\r\n", total_opts);
        display_opts = 4;
    }

    mw = LAYER_DIALOG_W - LAYER_DIALOG_INDENT - LAYER_DIALOG_RIGHT_INDENT;
    NB_DEBUG("question: %s (%d valid, %d displayed)\r\n", argv[0], total_opts, display_opts);

    layer_dialog_show();
    hal_mouse_erase_cursor();

    menu_save_item_palette();

    draw_text(tr(argv[0]), 0,
              LAYER_DIALOG_X + LAYER_DIALOG_INDENT, LAYER_DIALOG_Y + LAYER_DIALOG_HEADER_Y,
              mw, LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y, 1, MENU_PAL_WHITE);

    y = LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y;
    for (i = 0; i < display_opts; i++)
        question_draw_opt(opt_labels[i], i, y, mw, i == sel);

    hal_kbd_drain_advance();
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    hal_mouse_flush();

    {
        int q_timeout = 600;

        for (;;) {
            if (--q_timeout <= 0) {
                NB_DEBUG("question: timeout\r\n");
                menu_restore_item_palette();
                hal_mouse_flush();
                nb_set_last_choice(-1);
                return;
            }

            hal_kbd_update();
            hal_mouse_update();
            hal_mouse_recenter_if_idle();

            if (hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
                int hit, var_idx;
                hit = question_hittest(hal_mouse_get_x(), hal_mouse_get_y(), display_opts);
                if (hit >= 0) {
                    NB_DEBUG("question: mouse sel=%d\r\n", hit);
                    menu_restore_item_palette();
                    hal_mouse_flush();
                    nb_set_last_choice(hit);
                    var_idx = nb_var_lookup(opt_vars[hit]);
                    if (var_idx >= 0) {
                        if (opt_ops[hit][0] == '=')
                            nb_var_set(var_idx, opt_deltas[hit]);
                        else if (opt_ops[hit][0] == '-') {
                            /* -(INT_MIN) is UB; pass INT_MIN through and let
                             * nb_var_add clamp with 64-bit arithmetic. */
                            int d = (opt_deltas[hit] == INT_MIN)
                                        ? INT_MIN : -opt_deltas[hit];
                            nb_var_add(var_idx, d);
                        } else
                            nb_var_add(var_idx, opt_deltas[hit]);
                    }
                    return;
                }
            }

            if (hal_kbd_is_down(KC_UP) && sel > 0) {
                question_draw_opt(opt_labels[sel], sel, y, mw, 0);
                sel--;
                question_draw_opt(opt_labels[sel], sel, y, mw, 1);
                menu_consume_key(KC_UP);
            }
            if (hal_kbd_is_down(KC_DOWN) && sel < display_opts - 1) {
                question_draw_opt(opt_labels[sel], sel, y, mw, 0);
                sel++;
                question_draw_opt(opt_labels[sel], sel, y, mw, 1);
                menu_consume_key(KC_DOWN);
            }
            if (hal_kbd_is_down(KC_SPACE) || hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_XFER)) {
                int var_idx;
                NB_DEBUG("question: keyboard sel=%d\r\n", sel);
                menu_restore_item_palette();
                hal_mouse_flush();
                nb_set_last_choice(sel);
                var_idx = nb_var_lookup(opt_vars[sel]);
                if (var_idx >= 0) {
                    if (opt_ops[sel][0] == '=')
                        nb_var_set(var_idx, opt_deltas[sel]);
                    else if (opt_ops[sel][0] == '-') {
                        /* -(INT_MIN) is UB; pass INT_MIN through and let
                         * nb_var_add clamp with 64-bit arithmetic. */
                        int d = (opt_deltas[sel] == INT_MIN)
                                    ? INT_MIN : -opt_deltas[sel];
                        nb_var_add(var_idx, d);
                    } else
                        nb_var_add(var_idx, opt_deltas[sel]);
                }
                return;
            }

            hal_mouse_draw_cursor();
        }
    }
}
