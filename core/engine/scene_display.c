/*
 * scene_display.c — Display-side scene state: narrow apply facade.
 *
 * devdoc 103 stage 2 A: commands submit display changes here; the render +
 * palette side effects (anim stop, cursor invalidation, palette reset,
 * image load/release) live in these display-side unified exits.  The layer
 * state itself (bg snapshot, sprite table, dialog projection) stays in
 * layer_bg.c / layer_sprite.c / layer_dialog.c.
 */
#include <string.h>
#include "scene_display.h"
#include "palette.h"
#include "image.h"
#include "mag.h"
#include "scene_layers.h"
#include "hal.h"
#include "nb_anim.h"
#include "nb_dialog.h"

int display_apply_bg(unsigned short asset_id)
{
    MagImage *img;

    anim_stop();          /* implicit stop: new background ends any animation */
    img = image_load(asset_id);
    if (!img)
        return -1;
    hal_mouse_invalidate_cursor();
    palette_reset_reserved();
    layer_bg_change(img);
    mag_release(img);
    return 0;
}

int display_apply_cg(unsigned short asset_id)
{
    MagImage *img;

    anim_stop();          /* implicit stop: new CG ends any animation */
    img = image_load(asset_id);
    if (!img)
        return -1;
    /* R20: a CG is a full-screen event — close the dialog and drop the paged
     * dialogue so the next text command opens a fresh page over the CG. */
    layer_dialog_hide();
    nb_dialog_reset();
    hal_mouse_invalidate_cursor();
    palette_reset_reserved();
    layer_bg_change(img);
    mag_release(img);
    return 0;
}

int display_apply_sprite(int char_id, int asset_id, int x, const char *type)
{
    if (char_id < 0 || char_id >= LAYER_MAX_SPRITES || type == NULL)
        return -1;
    if (strcmp(type, "body") == 0)
        layer_sprite_update(char_id, asset_id, x, 0, 0);
    else
        layer_sprite_face(char_id, asset_id, x, 0, 0);
    return 0;
}

int display_apply_dialog(const char *charname, const char *text)
{
    dialog_show(charname, text);
    return 0;
}
