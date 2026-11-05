/*
 * input_boundary.h — User-input discard at script boundaries.
 *
 * A single drain entry shared by every site that starts reading input after
 * a script boundary (dialogue page yield, scene reset, blocking-menu entry).
 * Long blocking display work (cg / bg) runs without hal_kbd_update() or
 * hal_mouse_update(), so key and click events pile up in the device buffers;
 * a boundary that inherits them reinterprets stale events as input on the
 * *next* page.  See input_drain_boundary() for the three-call contract.
 */
#ifndef INPUT_BOUNDARY_H
#define INPUT_BOUNDARY_H

/* Discard all user input accumulated across a script boundary:
 *   - wait out advance keys (SPACE / ENTER / XFER) and wipe the BIOS ring
 *   - drop auto-repeat make codes still arriving from a held key
 *   - drop queued mouse click events
 * hal_mouse_drain() is deliberately not used: it only resets the dx/dy
 * accumulators and leaves mouse_click_fifo intact. */
void input_drain_boundary(void);

#endif /* INPUT_BOUNDARY_H */
