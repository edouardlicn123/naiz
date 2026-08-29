/*
 * hal_mouse.c — HAL mouse forwarding for PC-98.
 *
 * Implements the mouse abstractions declared in hal.h by delegating
 * input to the internal mouse driver (mouse.h) and cursor presentation
 * to the engine cursor driver (cursor.h).  Engine code must not
 * reference mouse.h directly; porting to a new platform only requires
 * swapping the delegation targets in plat/.
 *
 * See: docs/ — HAL architecture design
 */
#include "hal.h"
#include "mouse.h"
#include "cursor.h"

void hal_mouse_init(void)             { mouse_init(); }
void hal_mouse_update(void)           { mouse_update(); }
int  hal_mouse_get_x(void)            { return mouse_get_x(); }
int  hal_mouse_get_y(void)            { return mouse_get_y(); }
int  hal_mouse_was_clicked(int btn)   { return mouse_was_clicked(btn); }
/*
 * Teleporting invalidates the saved cursor background: the coordinates
 * the snapshot was taken for are gone, so the next cursor_render()
 * must treat the screen as clean.  mouse_recenter_if_idle() teleports
 * too but deliberately does NOT invalidate -- it fires mid-menu where
 * the stale save must stay valid for the erase-then-redraw pass.
 */
void hal_mouse_set_pos(int x, int y)
{
    mouse_set_pos(x, y);
    cursor_invalidate();
}
void hal_mouse_flush(void)            { mouse_flush(); }
void hal_mouse_drain(void)            { mouse_drain(); }
void hal_mouse_invalidate_cursor(void) { cursor_invalidate(); }
void hal_mouse_erase_cursor(void)      { cursor_erase_current(); }
void hal_mouse_draw_cursor(void)       { cursor_render(); }
void hal_mouse_draw_cursor_force(void) { cursor_render_force(); }
void hal_mouse_recenter_if_idle(void)  { mouse_recenter_if_idle(); }
int  hal_mouse_available(void)         { return mouse_available(); }
int  hal_mouse_get_display_x(void)     { return mouse_get_display_x(); }
int  hal_mouse_get_display_y(void)     { return mouse_get_display_y(); }
