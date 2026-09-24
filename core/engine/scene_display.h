#ifndef SCENE_DISPLAY_H
#define SCENE_DISPLAY_H

/*
 * scene_display.h — Narrow display-submission interface (devdoc 103 stage 2).
 *
 * Command handlers and engine entry points submit display-state changes
 * through these single entry points instead of poking layer/render/image/
 * palette internals directly.  All background/CG side effects (implicit anim
 * stop, mouse-cursor invalidation, reserved-palette reset, image load and
 * release) live in these display-side unified exits; the per-layer state
 * itself stays in layer_bg.c / layer_sprite.c / layer_dialog.c (single
 * source of truth, no duplicated "current display" ledger).
 *
 * All functions return 0 on success, -1 on failure.
 */

/* Show a background asset (bg command path).  Stops any animation, loads the
 * image, resets reserved palette colors and swaps the background layer. */
int display_apply_bg(unsigned short asset_id);

/* Show a full-screen event CG: same rendering path as display_apply_bg, plus
 * the R20 dialog teardown (close dialog + drop paged dialogue) so the next
 * text opens a fresh page over the CG. */
int display_apply_cg(unsigned short asset_id);

/* Place a character sprite.  type "body" -> full body (layer_sprite_update),
 * anything else -> upper-body face (layer_sprite_face, clipped above the
 * dialog band).  char_id must be in [0, LAYER_MAX_SPRITES). */
int display_apply_sprite(int char_id, int asset_id, int x, const char *type);

/* Display one text page in the dialog box (paging state machine; yields via
 * nb_dialog_pending, see nb_dialog.h). */
int display_apply_dialog(const char *charname, const char *text);

#endif
