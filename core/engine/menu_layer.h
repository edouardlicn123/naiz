/*
 * menu_layer.h — reusable menu overlay layer (draw / blit / restore).
 *
 * A self-contained rendering layer for menu UIs, modeled on dialog_layer
 * (layer_dialog.c): menu widgets draw into a RAM composite buffer instead of
 * scattering VRAM writes through per-frame code, then the whole area is
 * blitted atomically.  The layer knows nothing about any specific menu — it
 * only manages the buffer lifecycle, the render/text write targets, and the
 * blit/restore operations.
 *
 * Two modes (selected per open):
 *   OPAQUE (transparent=0):  open() snapshots the region from VRAM into a
 *       base buffer and copies it into the composite.  Draws land on top of
 *       the snapshot, blit is a plain vram_write (the composite already
 *       contains the underneath), and close(restore=1) writes the base back
 *       for a pixel-faithful clean exit.  Suited for full-screen/menu-scene
 *       menus (main menu, load slots, settings, gallery grid).
 *   TRANSPARENT (transparent=1): composite is cleared to PAL_TRANSPARENT and
 *       blit skips those pixels (render_blit_transparent), letting the
 *       underneath show through the holes — an overlay floating above the
 *       dialog/background.  No base buffer is kept (halves memory) and
 *       close() never restores: the caller must rebuild/clear the screen.
 *       Content must avoid palette index PAL_TRANSPARENT (15), same
 *       constraint as vram_blit_sprite.
 *
 * Lifecycle is owned by the calling menu.  This layer is a transient overlay:
 * it does not register a LAYER_Z_* entry nor touch g_layer_active (the
 * active flag block is reserved for persistent scene layers).
 *
* Minimal usage (opaque):
 *     if (menu_layer_open(0, 0, 640, 400, 0) != 0) {
 *         // OOM: draws fall back to plain VRAM, menu still works
 *     }
 *     ...draw with existing primitives (fill_rect/emboss/draw_text/...) --
 *         they are routed into the composite while the layer is open...
 *     menu_layer_commit();    // restore VRAM draw targets
 *     menu_layer_blit();      // make the region visible
 *     // in the input loop, on change: redraw the affected widgets into the
 *     //   composite (idempotent, the buffer already holds the base) then
 *     //   menu_layer_blit_rect(x, y, w, h);
 *     menu_layer_close(1);    // exit: restore the base snapshot
 *
 * Every open() closes any previously open layer first (re-open = rebuild).
 * menu_layer_open returns -1 and keeps VRAM targets untouched on allocation
 * failure, so callers can degrade to legacy direct-VRAM drawing.
 */
#ifndef MENU_LAYER_H
#define MENU_LAYER_H

#include "render.h"

/* Open a menu layer over screen rect (x,y,w,h). 'transparent' selects the
 * mode above.  Clamps the region to the screen; re-open rebuilds.  Returns 0
 * on success, -1 on allocation failure (no targets switched, VRAM fallback
 * intact). */
int  menu_layer_open(int x, int y, int w, int h, int transparent);
/* Reroute the render/text write targets onto the composite after a
 * menu_layer_commit — starts an incremental redraw session.  Draw primitives
 * called afterwards land in the composite buffer again; finish with
 * menu_layer_commit() then publish with menu_layer_blit_rect().  No-op when
 * not open. */
void menu_layer_begin_draw(void);
/* Reset the render/text write targets back to VRAM.  Call after drawing a
 * batch of widgets into the composite. */
void menu_layer_commit(void);
/* Blit the whole layer region to VRAM (opaque: vram_write; transparent:
 * PAL_TRANSPARENT-skipping blit).  No-op when not open. */
void menu_layer_blit(void);
/* Blit a screen-space sub-rectangle of the layer (clipped to the open
 * region).  Idempotent — safe to call repeatedly. */
void menu_layer_blit_rect(int x, int y, int w, int h);
/* Restore a screen-space rect of the composite back to the base snapshot,
 * erasing any widgets previously drawn there (opaque mode only; transparent
 * mode has no base and this is a no-op).  Lets a menu redraw a changed
 * widget without keeping its own clean-background snapshots. */
void menu_layer_erase_to_base(int x, int y, int w, int h);
/* Blit a sprite image into the composite, skipping pixels equal to
 * transparent_idx (same key as vram_blit_sprite).  When the layer is not
 * open this degrades to a plain VRAM sprite blit, so callers can use it
 * unconditionally inside a menu draw session. */
void menu_layer_blit_sprite(const MagImage *img, int x, int y, uint8_t transparent_idx);
/* Close the layer.  restore=1 writes the base snapshot back to VRAM
 * (opaque mode only; transparent mode never restores — the caller rebuilds
 * the screen).  Frees both buffers, resets targets, idempotent. */
void menu_layer_close(int restore);
/* Non-zero while a layer is open. */
int  menu_layer_is_open(void);
/* Current composite pixels (w*h bytes, row stride = region width) for
 * diagnostics/tests.  NULL when not open. */
const uint8_t *menu_layer_pixels(void);

#endif
