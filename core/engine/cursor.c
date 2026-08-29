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
#include "cursor.h"
#include "render.h"
#include "hal.h"

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
    draw_shape(x, y);
}

static void cursor_erase(CursorBg *bg, int x, int y)
{
    (void)x;
    (void)y;
    if (bg->valid)
        vram_write(bg->buf, bg->x, bg->y, CURSOR_SAVED_W, CURSOR_SAVED_H);
    bg->valid = 0;
}

/*=== Presentation driver ==================================================*/

/* Background of the currently drawn cursor; owned here. */
static CursorBg cursor_saved = { -1, -1, 0, {0} };

/* Draw the cursor at the current mouse display position, erasing the
 * previous one first.  No-op when the saved position already matches and
 * the cursor is available.  The erase+draw pair is sync-erased to VBLANK
 * so the scanout never shows a half-drawn cursor. */
void cursor_render(void)
{
    int x, y, draw_x, draw_y;

    if (!hal_mouse_available()) return;

    x = hal_mouse_get_display_x();
    y = hal_mouse_get_display_y();
    draw_x = x - CURSOR_HOT_X;
    draw_y = y - CURSOR_HOT_Y;

    if (cursor_saved.valid && draw_x == cursor_saved.x && draw_y == cursor_saved.y)
        return;

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
    draw_shape(draw_x, draw_y);
}


