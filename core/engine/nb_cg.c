/*
 * nb_cg.c -- CG fullscreen display command (cmd_cg).
 *
 * Shows an event CG (type='CG' asset) using the same rendering path as
 * bg, then permanently unlocks it in SYSTEM.SAV (devdoc 89/90).
 * Syntax:
 *   cg(){<asset_key>}   show the CG; the brace payload carries the asset key.
 *                       Parens are reserved for future parameter settings
 *                       and NEVER load the asset.
 *   cg(hidedialog)      close the dialog and restore the background area.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "render.h"
#include "palette.h"
#include "image.h"
#include "scene_layers.h"
#include "hal.h"
#include "save.h"
#include "debug.h"
#include "nb_asset_table.h"
#include "nb_anim.h"
#include "nb_commands.h"
#include "nb_internal.h"
#include "nb_dialog.h"

void cmd_cg(int argc, const char **argv, const char *cmd_name)
{
    const struct { const char *key; int id; } *p;
    int cg_id = -1;
    int id = -1;
    MagImage *img;

    (void)cmd_name;

    /* cg(hidedialog): keyword directive, no payload (parallel to bg(...)). */
    if (argc == 1 && strcmp(argv[0], "hidedialog") == 0) {
        NB_DEBUG("cg: hidedialog\r\n");
        layer_dialog_hide();
        nb_dialog_reset();
        return;
    }

    /* Hard gate: the asset key must arrive via the brace payload
     * cg(){key}.  Parens are reserved for future parameters and never load
     * the asset, so the legacy paren form cg(key) is rejected. */
    if (argc != 1 || nb_get_last_brace_arg() != argc - 1) {
        NB_DEBUG("cg: usage cg(){asset_key} (parens reserved for params)\r\n");
        return;
    }

    /* Resolve key in cg_map.  cg_id is the 1-based array index (devdoc 89
     * contract); the gallery (devdoc 92) must traverse with the same rule. */
    for (p = cg_map; p->key != NULL; p++) {
        if (strcmp(p->key, argv[0]) == 0) {
            id = p->id;
            cg_id = (int)(p - cg_map) + 1;
            break;
        }
    }
    if (id < 0) {
        NB_DEBUG("cg: unknown asset '%s'\r\n", argv[0]);
        return;
    }
    if (cg_id < 1 || cg_id > CG_TOTAL) {
        NB_DEBUG("cg: logical id %d out of range (CG_TOTAL=%d)\r\n",
                 cg_id, CG_TOTAL);
        return;
    }

    anim_stop();          /* implicit stop: new CG ends any animation */

    img = image_load((unsigned short)id);
    if (!img) {
        NB_DEBUG("cg: image_load(%d) failed\r\n", id);
        return;
    }

    /* Unlock BEFORE drawing: persist even if a later panic cuts us off. */
    sys_save_unlock_cg(cg_id);

    hal_mouse_invalidate_cursor();
    palette_reset_reserved();
    layer_bg_change(img);
    mag_release(img);

    NB_DEBUG("cg: id=%d cg_id=%d key=%s\r\n", id, cg_id, argv[0]);
}
