/*
 * input_boundary.c — User-input discard at script boundaries.
 *
 * The keyboard half alone is not sufficient.  hal_kbd_drain_advance() wipes
 * the BIOS ring through kbd_bios_reset(), so a key pressed during a long
 * blocking display op is discarded — but it returns after a fixed delay
 * without waiting for a physical release, so auto-repeat make codes from a
 * still-held key survive it.  On the mouse side hal_mouse_was_clicked()
 * consumes from mouse_click_fifo, hal_mouse_drain() only clears the dx/dy
 * accumulators, and the only FIFO reset is hal_mouse_flush().  A leftover
 * click is therefore consumed as a reveal-jump and a second one turns the
 * page, which is why a line can appear fully drawn for a single frame.
 */
#include "hal.h"
#include "input_boundary.h"

void input_drain_boundary(void)
{
    hal_kbd_drain_advance();
    hal_kbd_set_ignore_frames(2);
    hal_mouse_flush();
}
