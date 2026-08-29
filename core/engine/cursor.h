/*
 * cursor.h — Software cursor presentation interface.
 *
 * The presentation driver (cursor_render/...) owns the cursor_saved
 * background state and feeds from the mouse HAL display coordinates in
 * hal.h; hal_mouse.c routes the engine-facing hal_mouse_*_cursor() calls
 * here.  Low-level save/restore (cursor_draw/cursor_erase) are file-local
 * in cursor.c.
 *
 * By hosting the cursor compositing here (engine/), plat/mouse.c stays a
 * pure input device and never touches VRAM or render.h.
 */
#ifndef CURSOR_H
#define CURSOR_H

#define CURSOR_SAVED_W  24
#define CURSOR_SAVED_H  24

typedef struct {
    int x, y;
    int valid;
    unsigned char buf[CURSOR_SAVED_W * CURSOR_SAVED_H];
} CursorBg;

/* Draw the cursor at the mouse display position, erasing any previous one
 * first (no-op when the position is unchanged).  VSYNC-paced. */
void cursor_render(void);

/* Force a full erase+draw of the cursor at the display position. */
void cursor_render_force(void);

/* Erase the currently saved cursor (restore background). */
void cursor_erase_current(void);

/* Erase the currently saved cursor and mark the saved state invalid. */
void cursor_invalidate(void);

/* Refresh cursor after full-screen writes (vram_blit) that overwrite
 * cursor pixels.  Saves current VRAM background and draws cursor shape.
 * No vblank_wait, no erase — the caller's vram_blit already cleared
 * the old cursor pixels. */
void cursor_refresh(void);

#endif
