/*
 * nb_commands.c — NB script command handlers and dispatch table
 *
 * Extracted from nb.c: all cmd_* handlers, resolve helpers, and dispatch table.
 * Reference: devdocs/0.1版开发文档总结.html#doc-21
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include "render.h"
#include "image.h"
#include "scene_layers.h"
#include "hal.h"
#include "tr.h"
#include "nb_internal.h"
#include "nb_saveload.h"
#include "nb_dialog.h"
#include "nb_vars.h"
#include "debug.h"
#include "nb_asset_table.h"
#include "nb_anim.h"
#include "nb_commands.h"
#include "vm.h"

/*=== Asset lookup helpers ==================================================*/

static int resolve_asset(const char *key)
{
    const struct { const char *key; int id; } *p;
    for (p = asset_map; p->key; p++) {
        if (strcmp(p->key, key) == 0) {
            NB_DEBUG("resolve_asset: %s -> id=%d\r\n", key, p->id);
            return p->id;
        }
    }
    return -1;
}

/* Public asset lookup: searches image assets (asset_map), then falls back
 * to sprite assets (spr_asset_map) so SPR-type keys resolve too. */
int nb_asset_id(const char *key)
{
    int id = resolve_asset(key);
    const struct { const char *key; int id; } *p;
    if (id >= 0)
        return id;
    for (p = spr_asset_map; p->key; p++) {
        if (strcmp(p->key, key) == 0)
            return p->id;
    }
    return -1;
}

static int resolve_char_id(const char *key)
{
    const struct { const char *key; int id; const char *name; } *p;
    for (p = char_map; p->key; p++) {
        if (strcmp(p->key, key) == 0)
            return p->id;
    }
    return -1;
}

static int resolve_expr(int char_id, const char *expr)
{
    const struct { int char_id; const char *expr; int asset_id; } *p;
    for (p = expr_map; p->char_id >= 0; p++) {
        if (p->char_id == char_id && strcmp(p->expr, expr) == 0)
            return p->asset_id;
    }
    return -1;
}

static int resolve_expression(int char_id, const char *expr)
{
    int asset_id = resolve_expr(char_id, expr);
    if (asset_id >= 0)
        return asset_id;

    NB_DEBUG("WARN: char %d expr '%s' not found, fallback to 'normal'\r\n",
             char_id, expr);
    asset_id = resolve_expr(char_id, "normal");
    if (asset_id >= 0)
        return asset_id;

    NB_DEBUG("ERROR: char %d 'normal' not found either\r\n", char_id);
    return -1;
}

static const char *resolve_display_name(const char *key)
{
    const struct { const char *key; int id; const char *name; } *p;
    const char *t;

    t = tr(key);
    if (t != key) return t;

    for (p = char_map; p->key; p++) {
        if (strcmp(p->key, key) == 0)
            return p->name;
    }
    return key;
}

static int pos_to_x(char pos)
{
    switch (pos) {
    case 'l': return SPRITE_X_LEFT;
    case 'c': return SPRITE_X_CENTER;
    case 'r': return SPRITE_X_RIGHT;
    default:  return SPRITE_X_CENTER;
    }
}

/*
 * nb_next_field — Extract next comma-delimited field from segment string.
 *   *s points to start of a "f1,f2,..." segment (leading whitespace skipped).
 *   On success: copies field into buf (truncated to bufsz), null-terminated;
 *   advances *s past comma + trailing whitespace; returns 1.
 *   On failure (no comma found): *s unchanged; returns 0.
 */
int nb_next_field(const char **s, char *buf, size_t bufsz)
{
    const char *p = *s, *comma;
    size_t len;

    while (*p == ' ' || *p == '\t') p++;
    comma = strchr(p, ',');
    if (!comma) return 0;
    len = comma - p;
    if (len >= bufsz) len = bufsz - 1;
    memcpy(buf, p, len);
    buf[len] = '\0';
    *s = comma + 1;
    while (**s == ' ' || **s == '\t') (*s)++;
    return 1;
}

/*=== Command handlers ======================================================*/

static void cmd_bg(int argc, const char **argv, const char *cmd_name)
{
    int id;
    MagImage *img;

    (void)cmd_name;
    if (argc < 1) { NB_DEBUG("bg: no args\r\n"); return; }

    if (argc == 1 && strcmp(argv[0], "hidedialog") == 0) {
        NB_DEBUG("bg: hidedialog\r\n");
        layer_dialog_hide();
        nb_dialog_reset();
        return;
    }

    id = resolve_asset(argv[0]);
    if (id < 0) {
        NB_DEBUG("bg: unknown asset '%s'\r\n", argv[0]);
        return;
    }
    anim_stop();          /* implicit stop: new background ends any animation */
    img = image_load((unsigned short)id);
    if (!img) {
        NB_DEBUG("bg: image_load(%d) failed\r\n", id);
        return;
    }
    hal_mouse_invalidate_cursor();
    hal_set_palette(PAL_WHITE, 0xFF, 0xFF, 0xFF);
    hal_set_palette(PAL_TRANSPARENT, 0xFF, 0xFF, 0xFF);
    hal_set_palette(PAL_CURSOR_BLACK, 0x00, 0x00, 0x00);
    layer_bg_change(img);
    mag_release(img);
    NB_DEBUG("bg: id=%d key=%s\r\n", id, argv[0]);
}

static void cmd_host(int argc, const char **argv, const char *cmd_name)
{
    (void)cmd_name;
    if (argc < 1) return;
    dialog_show(NULL, tr(argv[0]));
}

static void cmd_char(int argc, const char **argv, const char *cmd_name)
{
    int char_id, asset_id, x;
    const char *expr, *type;

    (void)cmd_name;
    if (argc == 1 && strcmp(argv[0], "hideall") == 0) {
        layer_sprite_hide_all();
        layer_dialog_hide();
        nb_dialog_reset();
        NB_DEBUG("char: hideall\r\n");
        return;
    }
    if (argc < 2) { NB_DEBUG("char: not enough args\r\n"); return; }
    if (argv[1][0] == '\0') { NB_DEBUG("char: empty pos\r\n"); return; }

    char_id = resolve_char_id(argv[0]);
    if (char_id < 0) {
        NB_DEBUG("char: unknown character '%s'\r\n", argv[0]);
        return;
    }
    if (char_id >= LAYER_MAX_SPRITES) {
        NB_DEBUG("WARN: char_id=%d exceeds LAYER_MAX_SPRITES (%d)\r\n", char_id, LAYER_MAX_SPRITES);
        return;
    }

    x = pos_to_x(argv[1][0]);

    expr = (argc >= 3 && argv[2][0]) ? argv[2] : "normal";

    asset_id = resolve_expression(char_id, expr);
    if (asset_id < 0) {
        NB_DEBUG("char: no asset for char '%s' expr '%s'\r\n", argv[0], expr);
        return;
    }

    type = (argc >= 4 && argv[3][0]) ? argv[3] : NULL;
    if (type == NULL) {
        type = layer_has_sprite(char_id) ? "face" : "body";
    }

    NB_DEBUG("char: id=%d asset=%d x=%d type=%s\r\n", char_id, asset_id, x, type);

    if (strcmp(type, "body") == 0) {
        layer_sprite_update(char_id, asset_id, x, 0, 0);
    } else {
        layer_sprite_face(char_id, asset_id, x, 0, 0);
    }
}

static void cmd_dialogue(int argc, const char **argv, const char *cmd_name)
{
    const char *display_name;
    if (argc < 1) return;

    display_name = resolve_display_name(cmd_name);
    NB_DEBUG("dialog: %s -> %s\r\n", cmd_name, display_name);
    dialog_show(display_name, tr(argv[0]));
}


/* Scene configuration: title + type.
 *   sceneconf(){Title, type}   text form: {..} is a single arg "Title, type"
 *   sceneconf(Title, type)     paren form: parsed as two separate args
 * type: normal (default) / cg / menu */
static void cmd_sceneconf(int argc, const char **argv, const char *cmd_name)
{
    char title[NB_LINE_MAX];
    char type[16];
    const char *p;

    (void)cmd_name;
    if (argc < 1) return;

    title[0] = '\0';
    type[0] = '\0';

    if (argc >= 2) {
        /* Paren form: title and type are already separate args. */
        strncpy(title, argv[0], sizeof(title) - 1);
        title[sizeof(title) - 1] = '\0';
        strncpy(type, argv[1], sizeof(type) - 1);
        type[sizeof(type) - 1] = '\0';
    } else {
        /* Text form: {Title, type} arrives as one arg; split on ','. */
        p = argv[0];
        if (nb_next_field(&p, title, sizeof(title))) {
            /* title read; p points to type (may be empty). */
            if (*p) {
                strncpy(type, p, sizeof(type) - 1);
                type[sizeof(type) - 1] = '\0';
            }
        } else {
            /* No comma: entire arg is the title, type defaults to NULL. */
            strncpy(title, argv[0], sizeof(title) - 1);
            title[sizeof(title) - 1] = '\0';
        }
    }

    nb_set_scene_conf(tr(title), type[0] ? type : NULL);
}

/*
 * cmd_var — Variable read/write command.
 *   var(id, =, value)   -> nb_var_set(lookup(id), value)
 *   var(id, +, delta)   -> nb_var_add(lookup(id), delta)
 *   var(id, -, delta)   -> nb_var_add(lookup(id), -delta)
 */
static void cmd_var(int argc, const char **argv, const char *cmd_name)
{
    int idx, val;

    (void)cmd_name;
    if (argc < 3) {
        NB_DEBUG("var: need 3 args (id, op, value)\r\n");
        return;
    }

    idx = nb_var_lookup(argv[0]);
    if (idx < 0) {
        char _b[80];
        snprintf(_b, sizeof(_b), "WARN: var: unknown variable '%s'\r\n", argv[0]);
        hal_log(_b);
        return;
    }

    val = atoi(argv[2]);

    if (strcmp(argv[1], "=") == 0) {
        nb_var_set(idx, val);
        NB_DEBUG("var: set %s=%d\r\n", argv[0], val);
    } else if (strcmp(argv[1], "+") == 0) {
        nb_var_add(idx, val);
        NB_DEBUG("var: add %s+=%d\r\n", argv[0], val);
    } else if (strcmp(argv[1], "-") == 0) {
        /* -(INT_MIN) is UB; pass INT_MIN through and let nb_var_add
         * clamp with 64-bit arithmetic. */
        int d = (val == INT_MIN) ? INT_MIN : -val;
        nb_var_add(idx, d);
        NB_DEBUG("var: add %s-=%d\r\n", argv[0], val);
    } else {
        char _b[80];
        snprintf(_b, sizeof(_b), "WARN: var: unknown op '%s' (use =/+/ -)\r\n", argv[1]);
        hal_log(_b);
    }
}

static void cmd_delay(int argc, const char **argv, const char *cmd_name)
{
    const char *p;
    int neg, whole, frac, ndig, frames;
    double sec;
    (void)cmd_name;
    if (argc < 1 || !argv[0][0]) { NB_DEBUG("delay: no args\r\n"); return; }
    p = argv[0];
    neg = 0; whole = 0; frac = 0; ndig = 0;
    if (*p == '-') { neg = 1; p++; }
    while (*p >= '0' && *p <= '9') { whole = whole * 10 + (*p - '0'); p++; }
    if (*p == '.') { p++; while (*p >= '0' && *p <= '9') { frac = frac * 10 + (*p - '0'); ndig++; p++; } }
    sec = (double)whole + (double)frac;
    { int i; for (i = 0; i < ndig; i++) sec /= 10.0; }
    if (neg) sec = -sec;
    frames = (int)(sec * 60.0 + 0.5);
    if (frames <= 0) frames = 1;
    if (frames > DELAY_FRAMES_MAX) frames = DELAY_FRAMES_MAX;
    vm_set_delay(frames);
    vm_pause_process();
    NB_DEBUG("delay: %.2fs = %d frames\r\n", sec, frames);
}

/*=== Command dispatch table ===============================================*/

typedef void (*CmdHandler)(int argc, const char **argv, const char *cmd_name);

typedef struct {
    const char *name;
    CmdHandler  handler;
} CmdEntry;

static const CmdEntry cmd_table[] = {
    {"bg",           cmd_bg},
    {"char",         cmd_char},
    {"scene",        cmd_scene},
    {"sceneconf",    cmd_sceneconf},
    {"mainmenu",     cmd_mainmenu},
    {"startsetting", cmd_startsetting},
    {"question",     cmd_question},
    {"settingmenu",  cmd_settingmenu},
    {"cgvmenu",      cmd_cgvmenu},
    {"musicmenu",    cmd_musicmenu},
    {"bgm",          cmd_bgm},
    {"sound",        cmd_sound},
    {"voice",        cmd_voice},
    {"host",         cmd_host},
    {"loadscene",    cmd_loadscene},
    {"var",          cmd_var},
    {"fei",          cmd_dialogue},
    {"ira",          cmd_dialogue},
    {"neon",         cmd_dialogue},
    {"playanima",    cmd_playanima},
    {"waitanima",    cmd_waitanima},
    {"stopanima",    cmd_stopanima},
    {"delay",        cmd_delay},
    {NULL, NULL}
};

/*=== Dispatch function ====================================================*/

void nb_commands_dispatch(const char *cmd_name, int argc, const char **argv)
{
    const CmdEntry *entry = cmd_table;
    while (entry->name) {
        if (strcmp(entry->name, cmd_name) == 0) {
            NB_DEBUG("nb_process: executing command '%s'\r\n", cmd_name);
            entry->handler(argc, argv, cmd_name);
            return;
        }
        entry++;
    }
    NB_DEBUG("WARN: unknown command '%s'\r\n", cmd_name);
}
