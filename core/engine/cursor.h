/*
 * cursor.h — Software cursor layer (engine-side presentation overlay).
 *
 * The presentation driver (cursor_render/...) owns the cursor_saved
 * background state and feeds from the mouse HAL display coordinates in
 * hal.h; hal_mouse.c routes the engine-facing hal_mouse_*_cursor() calls
 * here.  Low-level save/restore (cursor_draw/cursor_erase) are file-local
 * in cursor.c.
 *
 * By hosting the cursor compositing here (engine/), plat/mouse.c stays a
 * pure input device and never touches VRAM or render.h.
 *
 * LAYER CONTRACT (devdoc 108): any module that writes pixels to VRAM must
 * first report its write rectangle via touch() (or the stricter
 * un-bounded invalidate()) BEFORE writing, so the layer can erase itself
 * whenever the write region overlaps the cursor.  Overlap is detected by a
 * four-way intersection test; non-overlapping writers are no-ops (no
 * erase, no vblank wait).  touch() restores the cursor background at the
 * time of the call — the screen content is still current there — and marks
 * the saved state invalid so the next cursor_render() re-captures a fresh
 * background over the new content.  Missing a touch on a VRAM writer
 * leaves a stale saved background behind: the next cursor move restores
 * old pixels over new content (devdoc 108 root cause).
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

/* Report a VRAM write rectangle (x,y,w,h).  When it overlaps the currently
 * saved cursor region, erase the cursor (restore its background, which is
 * still the current screen content before the writer runs) and mark the
 * state invalid so the next cursor_render() captures a fresh background.
 * Non-overlapping writes are pure no-ops (layer contract, devdoc 108). */
void cursor_touch(int x, int y, int w, int h);

/* Opaque variant of touch() (devdoc 109): the caller asserts its write
 * pixel-for-pixel overwrites the ENTIRE reported rect.  When the rect fully
 * contains the cursor box, the up-front erase is skipped (the write clears
 * the arrow) and the steady-position stale redraw in cursor_render()
 * re-captures the fresh background WITHOUT a VBLANK wait — eliminating the
 * full-frame arrow absence per reveal pass (typewriter cursor flicker).
 * Straddling boxes still erase.  Transparent/partial writers must keep
 * using cursor_touch(); skipping the erase for a partial write would bake
 * a live arrow into the saved background (devdoc 108 ghost). */
void cursor_touch_opaque(int x, int y, int w, int h);

/* Blend the arrow into an OPAQUE composite buffer BEFORE its single
 * vram_write (devdoc 110), adopting the pre-arrow box pixels as the saved
 * background.  The reveal/dialog write is slow through the bank-switched
 * DOS/4GW VRAM window; the pass-end stale redraw alone still leaves the
 * arrow missing for the whole write.  Splicing puts the cursor on screen
 * for the entire write — zero absence, no VBLANK, no erase, no extra VRAM
 * traffic.  Only used when the whole cursor box sits inside the composite
 * rect; straddling boxes keep cursor_touch_opaque() erase + pass-end
 * redraw, and transparent/partial buffers must NOT be spliced (a live
 * arrow would be baked into the persisted background).  Returns 1 when
 * spliced, 0 when the caller must rely on the pass-end redraw. */
int cursor_composite_splice(unsigned char *buf, int stride,
                            int fx, int fy, int fw, int fh);

/* Refresh cursor after full-screen writes (vram_blit) that overwrite
 * cursor pixels.  Saves current VRAM background and draws cursor shape.
 * No vblank_wait, no erase — the caller's vram_blit already cleared
 * the old cursor pixels. */
void cursor_refresh(void);

#endif
