/*
 * hal_kbd.c — HAL keyboard forwarding for PC-98.
 *
 * Implements the keyboard abstractions declared in hal.h by delegating
 * to the internal keyboard driver (keyboard.h). Engine code must not
 * reference keyboard.h directly; porting to a new platform only requires
 * swapping the delegation targets in plat/.
 *
 * See: docs/ — HAL architecture design
 */
#include "hal.h"
#include "keyboard.h"

void hal_kbd_init(void)             { kbd_init(); }
void hal_kbd_update(void)           { kbd_update(); }
int  hal_kbd_is_down(unsigned char s)      { return kbd_is_down(s); }
void hal_kbd_flush(void)            { kbd_flush(); }
void hal_kbd_drain_advance(void)    { kbd_drain_advance(); }
void hal_kbd_wait_any(void)         { kbd_wait_any(); }
void hal_kbd_set_ignore_frames(int n)     { kbd_set_ignore_frames(n); }
