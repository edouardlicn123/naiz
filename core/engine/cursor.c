/*
 * cursor.c — Software cursor shape drawing, background save/restore and
 * the cursor presentation driver.
 *
 * Uses render.h VRAM primitives and the mouse HAL display coordinates.
 * The presentation functions (cursor_render/...) host the previously
 * plat/mouse.c cursor compositing so mouse.c stays a pure input device.
 * cursor_draw/cursor_erase are file-local; hal.c only sees the driver
 * entry points (cursor_render/_force/_erase_current/_invalidate).
 */
#include <string.h>
#include "cursor.h"
#include "render.h"
#include "hal.h"

/*=== Temporary drag-ghost tracing (NAIZ_TRACE_CURSOR, removed later) =========
 * Diagnostics for the 0.2.138 dialog-drag residue.  PAL_CURSOR_BLACK (254)
 * never appears in legitimate text/background pixels, so counting it inside
 * a captured/restored 24x24 region proves arrow pixels were baked into the
 * saved background or left behind by an incomplete restore. */
#ifdef NAIZ_TRACE_CURSOR
static unsigned long nz_seq;
static int nz_arrowpx(const unsigned char *buf)
{
    int i, n = 0;
    for (i = 0; i < CURSOR_SAVED_W * CURSOR_SAVED_H; i++)
        if (buf[i] == PAL_CURSOR_BLACK) n++;
    return n;
}
static void nz_capture(const char *tag, const unsigned char *buf, int x, int y)
{
    int i, wht = 0;
    for (i = 0; i < CURSOR_SAVED_W * CURSOR_SAVED_H; i++)
        if (buf[i] == PAL_WHITE) wht++;
    hal_logf("[CT]%08lX %s %d,%d %d %d\r\n", nz_seq++, tag, x, y,
             nz_arrowpx(buf), wht);
}
static void nz_erase_verify(const char *tag, int x, int y)
{
    unsigned char check[CURSOR_SAVED_W * CURSOR_SAVED_H];
    vram_read(x, y, CURSOR_SAVED_W, CURSOR_SAVED_H, check);
    nz_capture(tag, check, x, y);
}
#endif

/*=== Cursor shape bitmaps (24x24 arrow) ===================================*/

static const uint8_t cursor_black[24][3] = {
    { 0x00, 0x00, 0x00 },
    { 0x00, 0x18, 0x00 },
    { 0x00, 0x18, 0x00 },
    { 0x01, 0xE7, 0x80 },
    { 0x01, 0xE7, 0x80 },
    { 0x06, 0x66, 0x78 },
    { 0x06, 0x66, 0x78 },
    { 0x06, 0x66, 0x66 },
    { 0x06, 0x66, 0x66 },
    { 0x06, 0x66, 0x66 },
    { 0x06, 0x66, 0x66 },
    { 0x1E, 0x00, 0x66 },
    { 0x1E, 0x00, 0x06 },
    { 0x66, 0x00, 0x06 },
    { 0x66, 0x00, 0x06 },
    { 0x61, 0x80, 0x06 },
    { 0x61, 0x80, 0x06 },
    { 0x18, 0x00, 0x06 },
    { 0x18, 0x00, 0x06 },
    { 0x06, 0x00, 0x18 },
    { 0x06, 0x00, 0x18 },
    { 0x01, 0xFF, 0xE0 },
    { 0x01, 0xFF, 0xE0 },
    { 0x00, 0x00, 0x00 },
};

static const uint8_t cursor_white[24][3] = {
    { 0x00, 0x00, 0x00 },
    { 0x00, 0x00, 0x00 },
    { 0x00, 0x00, 0x00 },
    { 0x00, 0x18, 0x00 },
    { 0x00, 0x18, 0x00 },
    { 0x01, 0x99, 0x80 },
    { 0x01, 0x99, 0x80 },
    { 0x01, 0x99, 0x98 },
    { 0x01, 0x99, 0x98 },
    { 0x01, 0x99, 0x98 },
    { 0x01, 0x99, 0x98 },
    { 0x01, 0xFF, 0x98 },
    { 0x01, 0xFF, 0xF8 },
    { 0x19, 0xFF, 0xF8 },
    { 0x19, 0xFF, 0xF8 },
    { 0x1E, 0x7F, 0xF8 },
    { 0x1E, 0x7F, 0xF8 },
    { 0x07, 0xFF, 0xF8 },
    { 0x07, 0xFF, 0xF8 },
    { 0x01, 0xFF, 0xE0 },
    { 0x01, 0xFF, 0xE0 },
    { 0x00, 0x00, 0x00 },
    { 0x00, 0x00, 0x00 },
    { 0x00, 0x00, 0x00 },
};

#define CURSOR_HOT_X 11
#define CURSOR_HOT_Y 1

/*=== Internal helpers =====================================================*/

static int is_cursor_pixel(int row, int col)
{
    if (row < 0 || row >= 24 || col < 0 || col >= 24) return 0;
    return (cursor_black[row][col / 8] & (0x80 >> (col % 8))) != 0;
}

static int is_fill_pixel(int row, int col)
{
    if (row < 0 || row >= 24 || col < 0 || col >= 24) return 0;
    return (cursor_white[row][col / 8] & (0x80 >> (col % 8))) != 0;
}

static void draw_shape(int x, int y)
{
    int row, col, sx, sy, addr;
    int cur_bank = -1;
    volatile uint8_t *win = hal_vram_get_window();
    for (row = 0; row < 24; row++) {
        sy = y + row;
        if (sy < 0 || sy >= LAYER_SCREEN_H) continue;
        for (col = 0; col < 24; col++) {
            sx = x + col;
            if (sx < 0 || sx >= LAYER_SCREEN_W) continue;
            addr = sy * LAYER_SCREEN_W + sx;
            VRAM_SET_BANK(addr, cur_bank);
            if (is_fill_pixel(row, col))
                win[addr & (VRAM_BANK_SZ - 1)] = PAL_WHITE;
            if (is_cursor_pixel(row, col))
                win[addr & (VRAM_BANK_SZ - 1)] = PAL_CURSOR_BLACK;
        }
    }
}

/*=== Public interface =====================================================*/

static void cursor_draw(CursorBg *bg, int x, int y)
{
    vram_read(x, y, CURSOR_SAVED_W, CURSOR_SAVED_H, bg->buf);
    bg->x = x;
    bg->y = y;
    bg->valid = 1;
#ifdef NAIZ_TRACE_CURSOR
    nz_capture("D", bg->buf, x, y);
#endif
    draw_shape(x, y);
}

static void cursor_erase(CursorBg *bg, int x, int y)
{
    (void)x;
    (void)y;
    if (bg->valid)
        vram_write(bg->buf, bg->x, bg->y, CURSOR_SAVED_W, CURSOR_SAVED_H);
    bg->valid = 0;
#ifdef NAIZ_TRACE_CURSOR
    nz_erase_verify("E", bg->x, bg->y);
#endif
}

/*=== Presentation driver ==================================================*/

/* Background of the currently drawn cursor; owned here. */
static CursorBg cursor_saved = { -1, -1, 0, {0} };

/* Draw the cursor at the current mouse display position, erasing the
 * previous one first.  No-op when the saved position already matches and
 * the cursor is available.  The erase+draw pair is sync-erased to VBLANK
 * so the scanout never shows a half-drawn cursor.
 *
 * Exception — steady-position stale redraw (devdoc 109): when an opaque
 * writer touched this same position this pass (saved state invalid, draw
 * position unchanged), the erase already happened or the writer covered the
 * whole box, and the fresh background is already in VRAM.  Redraw then must
 * NOT wait for the next VBLANK: deferring to the VBLANK leaves the arrow
 * missing from the scanout for up to a full frame per reveal pass, which the
 * eye sees as a ~20 Hz blend of the typewriter cursor.  Drawing immediately
 * shrinks the gap to microseconds, so the scanout never shows a full-frame
 * absence.  Moves / teleports / force keep the VBLANK-synced pair. */
void cursor_render(void)
{
    int x, y, draw_x, draw_y;
    int stale_same_pos;

    if (!hal_mouse_available()) return;

    x = hal_mouse_get_display_x();
    y = hal_mouse_get_display_y();
    draw_x = x - CURSOR_HOT_X;
    draw_y = y - CURSOR_HOT_Y;

    if (cursor_saved.valid && draw_x == cursor_saved.x && draw_y == cursor_saved.y)
        return;

    stale_same_pos = (!cursor_saved.valid &&
                      draw_x == cursor_saved.x && draw_y == cursor_saved.y);
    if (stale_same_pos) {
        cursor_draw(&cursor_saved, draw_x, draw_y);
        return;
    }

    hal_vblank_wait();

    if (cursor_saved.valid)
        cursor_erase(&cursor_saved, draw_x, draw_y);

    cursor_draw(&cursor_saved, draw_x, draw_y);
}

/* Force a full erase+draw of the cursor at the display position. */
void cursor_render_force(void)
{
    int x, y, draw_x, draw_y;
    if (!hal_mouse_available()) return;
    x = hal_mouse_get_display_x();
    y = hal_mouse_get_display_y();
    draw_x = x - CURSOR_HOT_X;
    draw_y = y - CURSOR_HOT_Y;

    hal_vblank_wait();

    if (cursor_saved.valid)
        cursor_erase(&cursor_saved, cursor_saved.x, cursor_saved.y);
    cursor_draw(&cursor_saved, draw_x, draw_y);
}

/* Erase the currently saved cursor (restore its background). */
void cursor_erase_current(void)
{
    if (cursor_saved.valid)
        cursor_erase(&cursor_saved, cursor_saved.x, cursor_saved.y);
}

/* Erase the currently saved cursor and mark the saved state invalid. */
void cursor_invalidate(void)
{
    if (cursor_saved.valid)
        cursor_erase(&cursor_saved, cursor_saved.x, cursor_saved.y);
    cursor_saved.valid = 0;
}

/* Four-way intersection: does rect (x,y,w,h) overlap the saved cursor
 * region?  A writer touching ANY pixel of the saved background must erase
 * the whole cursor up front (devdoc 108), including the overlap case at a
 * region boundary — no partial background may go stale. */
static int cursor_overlap_rect(const CursorBg *bg, int x, int y, int w, int h)
{
    if (!bg->valid) return 0;
    return x < bg->x + CURSOR_SAVED_W && bg->x < x + w &&
           y < bg->y + CURSOR_SAVED_H && bg->y < y + h;
}

/* Is the whole saved cursor box strictly inside the written rect?  When an
 * OPAQUE writer's rect fully contains the 24x24 cursor box, its pixels
 * overwrite every cursor pixel, so restoring the old background up front is
 * wasted work (devdoc 109): the writer does the clearing.  Boxes that
 * straddle the rect border keep the erase so no stale half is ever shown. */
static int cursor_covered_fully(const CursorBg *bg, int x, int y, int w, int h)
{
    return x <= bg->x && bg->x + CURSOR_SAVED_W <= x + w &&
           y <= bg->y && bg->y + CURSOR_SAVED_H <= y + h;
}

/* Report a VRAM write rectangle (layer contract, devdoc 108).  Overlap
 * detects the erase+invalidate of the saved cursor; non-overlapping writes
 * are no-ops so the reveal/dialog hot path only pays when the cursor is
 * actually inside the written region. */
void cursor_touch(int x, int y, int w, int h)
{
    if (hal_mouse_available() && cursor_overlap_rect(&cursor_saved, x, y, w, h)) {
        cursor_erase(&cursor_saved, cursor_saved.x, cursor_saved.y);
        cursor_saved.valid = 0;
    }
}

/* Opaque variant of cursor_touch (devdoc 109): the caller asserts its write
 * will pixel-for-pixel overwrite the WHOLE reported rect (composite
 * vram_write, not a transparent/partial draw).  When the rect fully covers
 * the cursor box the up-front erase is skipped — the writer's pixels clear
 * the arrow — and the steady-position stale redraw (cursor_render) then
 * re-captures the fresh background with no VBLANK-gated full-frame absence.
 * Straddling boxes still erase first.  Transparent/partial writers MUST use
 * cursor_touch, never this, or a live arrow would be baked into the saved
 * background. */
void cursor_touch_opaque(int x, int y, int w, int h)
{
    if (!hal_mouse_available()) return;
    if (!cursor_overlap_rect(&cursor_saved, x, y, w, h)) return;
    if (!cursor_covered_fully(&cursor_saved, x, y, w, h))
        cursor_erase(&cursor_saved, cursor_saved.x, cursor_saved.y);
    cursor_saved.valid = 0;
}

/* Blend the arrow into an OPAQUE composite buffer and adopt the pre-arrow
 * box pixels as the saved background (devdoc 110).  The revealing dialog
 * writes the whole 480x115 composite through the bank-switched DOS/4GW VRAM
 * window every pass; the arrow is gone from the scanout from the moment the
 * write reaches its box until the pass-end redraw.  When the whole cursor
 * box sits inside the composite rect, splicing the arrow into the buffer
 * BEFORE the single vram_write puts the cursor on screen for the entire
 * write — zero absence window, no VBLANK, no erase, no extra VRAM traffic.
 * The caller keeps the touch/erase contract for boxes that straddle the
 * composite rect; returns 1 when spliced, 0 when the caller must rely on
 * the pass-end redraw.  Transparent/partial buffer content is NOT spliced
 * (a live arrow would be baked into the persisted background). */
int cursor_composite_splice(unsigned char *buf, int stride,
                            int fx, int fy, int fw, int fh)
{
    int x, y, draw_x, draw_y, row, col;
    int ox, oy;

    if (!hal_mouse_available()) return 0;

    x = hal_mouse_get_display_x();
    y = hal_mouse_get_display_y();
    draw_x = x - CURSOR_HOT_X;
    draw_y = y - CURSOR_HOT_Y;

    if (!(fx <= draw_x && draw_x + CURSOR_SAVED_W <= fx + fw &&
          fy <= draw_y && draw_y + CURSOR_SAVED_H <= fy + fh))
        return 0;

    ox = draw_x - fx;
    oy = draw_y - fy;

    /* Background = the composite pixels under the box (dialog text), saved
     * BEFORE the arrow is blended in so a later erase restores clean text. */
    memcpy(cursor_saved.buf, buf + oy * stride + ox,
           CURSOR_SAVED_W * CURSOR_SAVED_H);
#ifdef NAIZ_TRACE_CURSOR
    nz_capture("S", cursor_saved.buf, draw_x, draw_y);
#endif
    for (row = 0; row < CURSOR_SAVED_H; row++) {
        for (col = 0; col < CURSOR_SAVED_W; col++) {
            uint8_t *p = buf + (oy + row) * stride + (ox + col);
            if (is_fill_pixel(row, col))
                *p = PAL_WHITE;
            else if (is_cursor_pixel(row, col))
                *p = PAL_CURSOR_BLACK;
        }
    }
    cursor_saved.x = draw_x;
    cursor_saved.y = draw_y;
    cursor_saved.valid = 1;

    return 1;
}

/* Refresh cursor after full-screen writes (e.g. anim vram_blit) that
 * overwrote cursor pixels.  Saves the current VRAM background and
 * redraws the cursor shape.  No vblank_wait (caller already paces)
 * and no erase (vram_blit already cleared old cursor pixels). */
void cursor_refresh(void)
{
    int x, y, draw_x, draw_y;

    if (!hal_mouse_available()) return;

    x = hal_mouse_get_display_x();
    y = hal_mouse_get_display_y();
    draw_x = x - CURSOR_HOT_X;
    draw_y = y - CURSOR_HOT_Y;

    vram_read(draw_x, draw_y, CURSOR_SAVED_W, CURSOR_SAVED_H, cursor_saved.buf);
    cursor_saved.x = draw_x;
    cursor_saved.y = draw_y;
    cursor_saved.valid = 1;
#ifdef NAIZ_TRACE_CURSOR
    nz_capture("F", cursor_saved.buf, draw_x, draw_y);
#endif
    draw_shape(draw_x, draw_y);
}


