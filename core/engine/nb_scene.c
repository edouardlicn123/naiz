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
#include "save.h"
#include "debug.h"
#include "nb_commands.h"

/*
 * scene_jump — Resolve and jump to a scene target.
 *
 * Resolution:
 *   "end"      -> mainmenu.nb
 *   "logo"/"op"/"mainmenu" -> {name}.nb
 *   number     -> nbook{number}.nb  (unlock current scene)
 */
static void scene_jump(const char *target)
{
    char fname[NB_FILENAME_MAX];

    if (strcmp(target, "end") == 0) {
        NB_DEBUG("scene: end -> mainmenu\r\n");
        nb_load("mainmenu.nb");
        return;
    }

    if (strcmp(target, "logo") == 0 ||
        strcmp(target, "op") == 0 ||
        strcmp(target, "mainmenu") == 0) {
        snprintf(fname, sizeof(fname), "%s.nb", target);
        NB_DEBUG("scene: %s -> %s\r\n", target, fname);
        nb_load(fname);
        return;
    }

    {
        unsigned int cur_id;
        if (sscanf(nb_get_filename(), "nbook%u.nb", &cur_id) == 1)
            sys_save_unlock_scene((int)cur_id);
    }
    snprintf(fname, sizeof(fname), "nbook%s.nb", target);
    NB_DEBUG("scene: %s -> %s\r\n", target, fname);
    nb_load(fname);
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
        if (strchr(argv[0], ',')) {
            NB_DEBUG("WARN: scene: single arg '%s' contains ',' "
                     "(missing ';' separator?)\r\n", argv[0]);
        }
        scene_jump(argv[0]);
        return;
    }

    has_explicit_default = (strchr(argv[argc - 1], ',') == NULL);
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
                    if (!strchr(tp, ',')) break;
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
                    char _b[80];
                    snprintf(_b, sizeof(_b), "WARN: scene: unknown var '%s'\r\n", cond_vars[j]);
                    hal_log(_b);
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
