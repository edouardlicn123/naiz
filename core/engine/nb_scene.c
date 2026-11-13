/*
 * nb_scene.c — NB scene-jump command (cmd_scene) and its helpers.
 *
 * Split from nb_commands.c: scene resolution, condition evaluation and
 * the scene command handler.  Registered in nb_commands.c cmd_table.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "vm.h"
#include "render.h"
#include "scene_layers.h"
#include "hal.h"
#include "tr.h"
#include "nb_internal.h"
#include "nb_vars.h"
#include "debug.h"
#include "nb_commands.h"

/*
 * scene_target_name — Normalize a scene target to a .nb filename.
 * Shared by scene and jumpscene (devdoc 203 §3.3):
 *   "end"                    -> mainmenu.nb (scenes.nb during gallery playback)
 *   "logo"/"op"/"mainmenu"   -> {name}.nb
 *   "003"/"nb003"/"nbook003"/"nbook003.nb" -> nbook003.nb
 *   other numeric target     -> nbook{target}.nb
 * Returns 1 when the target resolved to the scene gallery (playback end), so
 * the caller can switch with SCENE_SWITCH_MENU and end playback mode.
 */
static int scene_target_name(const char *target, char *fname, size_t fsize)
{
    char base[64];
    size_t n;

    if (strcmp(target, "end") == 0) {
        /* devdoc 209: a scene started from the gallery returns there, not to
         * the main menu; the menu switch reason clears playback mode. */
        if (nb_get_playback_mode()) {
            snprintf(fname, fsize, "scenes.nb");
            return 1;
        }
        snprintf(fname, fsize, "mainmenu.nb");
        return 0;
    }

    if (strcmp(target, "logo") == 0 ||
        strcmp(target, "op") == 0 ||
        strcmp(target, "mainmenu") == 0) {
        snprintf(fname, fsize, "%s.nb", target);
        return 0;
    }

    snprintf(base, sizeof(base), "%s", target);
    n = strlen(base);
    if (n > 3 && strcmp(base + n - 3, ".nb") == 0)
        base[n - 3] = '\0';

    if (strncmp(base, "nbook", 5) == 0)
        snprintf(fname, fsize, "%s.nb", base);
    else if (strncmp(base, "nb", 2) == 0)
        snprintf(fname, fsize, "nbook%s.nb", base + 2);
    else
        snprintf(fname, fsize, "nbook%s.nb", base);
    return 0;
}

/* scene_jump — Resolve and jump to a scene target. */
static void scene_jump(const char *target)
{
    char fname[NB_FILENAME_MAX];
    int to_gallery;

    to_gallery = scene_target_name(target, fname, sizeof(fname));
    NB_DEBUG("scene: %s -> %s\r\n", target, fname);
    scene_switch(fname, to_gallery ? SCENE_SWITCH_MENU : SCENE_SWITCH_SCRIPT);
}

/* Trim trailing blanks in place (option tails are taken verbatim). */
static void tail_trim(char *s)
{
    size_t n = strlen(s);
    while (n > 0 && (s[n - 1] == ' ' || s[n - 1] == '\t'))
        s[--n] = '\0';
}

/* eval_cond — Compare cur against val using op string.
 *   Supports: == != > >= < <=
 *   Returns 0 for unknown op.
 */
static int eval_cond(int cur, const char *op, int val)
{
    if (strcmp(op, "==") == 0) return cur == val;
    if (strcmp(op, "!=") == 0) return cur != val;
    if (strcmp(op, ">")  == 0) return cur >  val;
    if (strcmp(op, ">=") == 0) return cur >= val;
    if (strcmp(op, "<")  == 0) return cur <  val;
    if (strcmp(op, "<=") == 0) return cur <= val;
    NB_DEBUG("WARN: eval_cond: unknown op '%s'\r\n", op);
    return 0;
}

void cmd_scene(int argc, const char **argv, const char *cmd_name)
{
    int has_explicit_default;
    int cond_count;
    const char *first_target = NULL;

    (void)cmd_name;
    if (argc < 1) { NB_DEBUG("scene: no args\r\n"); return; }

    if (argc == 1) {
        /* Unconditional jump */
        if (nb_has_field_delim(argv[0])) {
            NB_DEBUG("WARN: scene: single arg '%s' contains ',' "
                     "(missing ';' separator?)\r\n", argv[0]);
        }
        scene_jump(argv[0]);
        return;
    }

    has_explicit_default = !nb_has_field_delim(argv[argc - 1]);
    cond_count = has_explicit_default ? argc - 1 : argc;

    /* Conditional chain (OR: first matching segment wins).
     * Each condition segment: 1+ (var,op,target) triples AND'd together,
     * last field = target. */
    {
        int i;
#define SCENE_MAX_CONDS 8
        for (i = 0; i < cond_count; i++) {
            const char *p, *target;
            char cond_vars[SCENE_MAX_CONDS][32];
            char cond_ops[SCENE_MAX_CONDS][4];
            int  cond_vals[SCENE_MAX_CONDS];
            int nt, j, all_true;

            p = argv[i];

            /* Read 1+ (var,op,val) triples */
            nt = 0;
            while (nt < SCENE_MAX_CONDS) {
                char buf[16];
                if (!nb_next_field(&p, cond_vars[nt], sizeof(cond_vars[nt]))) break;
                if (!nb_next_field(&p, cond_ops[nt], sizeof(cond_ops[nt]))) break;
                if (!nb_next_field(&p, buf, sizeof(buf))) break;
                cond_vals[nt] = atoi(buf);
                nt++;
                /* If remaining has no comma, what's left is the target */
                {
                    const char *tp = p;
                    while (*tp == ' ' || *tp == '\t') tp++;
                    if (!nb_has_field_delim(tp)) break;
                }
            }
            if (nt == 0) {
                NB_DEBUG("WARN: scene: bad segment '%s' (no conditions)\r\n", argv[i]);
                continue;
            }
            while (*p == ' ' || *p == '\t') p++;
            target = p;
            if (i == 0) first_target = target;

            /* AND all conditions in this segment */
            all_true = 1;
            for (j = 0; j < nt; j++) {
                int idx = nb_var_lookup(cond_vars[j]);
                if (idx < 0) {
                    hal_logf("WARN: scene: unknown var '%s'\r\n", cond_vars[j]);
                    all_true = 0;
                    break;
                }
                if (!eval_cond(nb_var_get(idx), cond_ops[j], cond_vals[j])) {
                    all_true = 0;
                    break;
                }
            }

            if (all_true) {
                NB_DEBUG("scene: segment %d ALL TRUE -> %s\r\n", i, target);
                scene_jump(target);
                return;
            }
        }
#undef SCENE_MAX_CONDS
    }

    if (has_explicit_default) {
        NB_DEBUG("scene: no cond matched, default -> %s\r\n", argv[argc - 1]);
        scene_jump(argv[argc - 1]);
    } else {
        if (!first_target) {
            NB_DEBUG("WARN: scene: no valid conditions, cannot fallback\r\n");
            return;
        }
        NB_DEBUG("scene: no cond matched, fallback first target -> %s\r\n", first_target);
        scene_jump(first_target);
    }
}

/*=== devdoc 203: choice-driven jumps ======================================*/

/* Parse "label,tag" segments of jump().  Returns the valid option count. */
static int jump_parse_options(int argc, const char **argv, int opt_max,
                              char labels[][64], char tags[][32])
{
    int i, n = 0;

    for (i = 1; i < argc && n < opt_max; i++) {
        const char *p = argv[i];
        char label[64];
        char tail[32];

        if (!nb_next_field(&p, label, sizeof(label))) {
            hal_logf("WARN: jump: option '%s' missing tag (label,tag)\r\n",
                     argv[i]);
            continue;
        }
        snprintf(tail, sizeof(tail), "%s", p);
        tail_trim(tail);
        if (!tail[0] || nb_has_field_delim(tail)) {
            hal_logf("WARN: jump: option '%s' needs exactly one tag\r\n",
                     argv[i]);
            continue;
        }

        snprintf(labels[n], 64, "%s", label);
        snprintf(tags[n], 32, "%s", tail);
        n++;
    }
    return n;
}

/* jump(prompt;label,tag;...) — choose an option, then seek to that tag inside
 * the CURRENT scene.  Cross-scene jumps use jumpscene (devdoc 203 §3.2). */
void cmd_jump(int argc, const char **argv, const char *cmd_name)
{
    char labels[10][64];
    char tags[10][32];
    const char *ui_labels[10];
    int i, n, sel;

    (void)cmd_name;
    if (argc < 2) { hal_logf("WARN: jump: not enough args\r\n"); return; }
    if (argc - 1 > 10)
        hal_logf("WARN: jump: %d options truncated to 10\r\n", argc - 1);

    n = jump_parse_options(argc, argv, 10, labels, tags);
    if (n < 1) { NB_DEBUG("jump: no valid options\r\n"); return; }

    for (i = 0; i < n; i++)
        ui_labels[i] = labels[i];

    sel = nb_prompt_options(argv[0], ui_labels, n);
    if (sel < 0)
        return;   /* timeout: continue after the jump line, like question */

    /* nb_seek_tag logs the WARN and leaves pc unchanged when the tag is
     * missing, so the script continues after this line. */
    (void)nb_seek_tag(tags[sel]);
}

/* jumpscene(prompt;label,scene[,tag];...) — choose an option, then discard
 * the rest of this scene and switch.  An optional third field lands on a tag
 * in the target scene (devdoc 203 §3.3). */
void cmd_jumpscene(int argc, const char **argv, const char *cmd_name)
{
    char labels[10][64];
    char scenes[10][64];
    char tags[10][32];
    const char *ui_labels[10];
    char fname[NB_FILENAME_MAX];
    int to_gallery;
    int i, n = 0, sel;

    (void)cmd_name;
    if (argc < 2) { hal_logf("WARN: jumpscene: not enough args\r\n"); return; }
    if (argc - 1 > 10)
        hal_logf("WARN: jumpscene: %d options truncated to 10\r\n", argc - 1);

    for (i = 1; i < argc && n < 10; i++) {
        const char *p = argv[i];
        char label[64];
        char scene[64];
        char tag[32];

        if (!nb_next_field(&p, label, sizeof(label))) {
            hal_logf("WARN: jumpscene: option '%s' missing scene "
                     "(label,scene)\r\n", argv[i]);
            continue;
        }

        tag[0] = '\0';
        if (nb_next_field(&p, scene, sizeof(scene))) {
            /* Third field present (may be empty = no tag). */
            snprintf(tag, sizeof(tag), "%s", p);
            tail_trim(tag);
        } else {
            /* No second comma: the whole remainder is the scene. */
            snprintf(scene, sizeof(scene), "%s", p);
            tail_trim(scene);
        }
        tail_trim(scene);
        if (!scene[0]) {
            hal_logf("WARN: jumpscene: option '%s' missing scene "
                     "(label,scene)\r\n", argv[i]);
            continue;
        }

        snprintf(labels[n], 64, "%s", label);
        snprintf(scenes[n], 64, "%s", scene);
        snprintf(tags[n], 32, "%s", tag);
        n++;
    }
    if (n < 1) { NB_DEBUG("jumpscene: no valid options\r\n"); return; }

    for (i = 0; i < n; i++)
        ui_labels[i] = labels[i];

    sel = nb_prompt_options(argv[0], ui_labels, n);
    if (sel < 0)
        return;   /* timeout: stay in this scene, continue after the line */

    to_gallery = scene_target_name(scenes[sel], fname, sizeof(fname));
    NB_DEBUG("jumpscene: %s -> %s tag='%s'\r\n",
             scenes[sel], fname, tags[sel]);
    if (tags[sel][0])
        nb_scene_switch_tagged(fname, to_gallery ? SCENE_SWITCH_MENU
                                                 : SCENE_SWITCH_SCRIPT,
                               tags[sel]);
    else
        scene_switch(fname, to_gallery ? SCENE_SWITCH_MENU
                                       : SCENE_SWITCH_SCRIPT);
}
