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
#include "scene_layers.h"
#include "hal.h"
#include "tr.h"
#include "nb_internal.h"
#include "nb_vars.h"
#include "debug.h"
#include "nb_commands.h"

/* Apply a chosen option's variable operation: '=' assign, '-' subtract
 * (INT_MIN-safe, clamped by nb_var_add), anything else adds. */
static void apply_option(int idx, char (*vars)[32], char (*ops)[4], const int *deltas)
{
    int var_idx = nb_var_lookup(vars[idx]);
    if (var_idx < 0) return;
    if (ops[idx][0] == '=')
        nb_var_set(var_idx, deltas[idx]);
    else if (ops[idx][0] == '-') {
        /* -(INT_MIN) is UB; pass INT_MIN through and let nb_var_add clamp
         * with 64-bit arithmetic. */
        int d = (deltas[idx] == INT_MIN) ? INT_MIN : -deltas[idx];
        nb_var_add(var_idx, d);
    } else
        nb_var_add(var_idx, deltas[idx]);
}

void cmd_question(int argc, const char **argv, const char *cmd_name)
{
    int i, mw, num_opts, valid_opts, total_opts, display_opts;
    int sel;
    char opt_labels[10][64];
    char opt_vars[10][32];
    char opt_ops[10][4];
    int  opt_deltas[10];
    const char *ui_labels[10];
    UiRequest req;

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

    mw = LAYER_DIALOG_CONTENT_W;
    NB_DEBUG("question: %s (%d valid, %d displayed)\r\n", argv[0], total_opts, display_opts);

    layer_dialog_clear();
    hal_mouse_erase_cursor();

    menu_save_item_palette();

    draw_text(tr(argv[0]), 0,
              LAYER_DIALOG_CONTENT_X, LAYER_DIALOG_Y + LAYER_DIALOG_HEADER_Y,
              mw, LAYER_DIALOG_CONTENT_Y, 1, MENU_PAL_WHITE);

    /* Labels handed to ui_interact() must already be tr()'d. */
    for (i = 0; i < display_opts; i++)
        ui_labels[i] = tr(opt_labels[i]);

    req.labels    = ui_labels;
    req.n         = display_opts;
    req.focus0    = 0;
    sel = ui_interact(&req);

    menu_restore_item_palette();
    hal_mouse_flush();
    nb_set_last_choice(sel);
    if (sel >= 0)
        apply_option(sel, opt_vars, opt_ops, opt_deltas);
}
