/*
 * ui.h — UI rendering primitives (rounded rects, emboss).
 *
 * Depends on VRAM primitives declared in render.h.
 * Implemented in ui.c.
 */
#ifndef UI_H
#define UI_H

#include <stdint.h>

/* Draw a filled rounded rectangle with 3D embossed border. */
void draw_rounded_emboss(int x, int y, int w, int h, int r,
                          uint8_t fill, uint8_t highlight, uint8_t shadow);

/* Draw rounded rectangle 3D emboss border only (highlight top/left, shadow bottom/right). */
void draw_rounded_emboss_outline(int x, int y, int w, int h, int r,
                                  uint8_t highlight, uint8_t shadow);

#endif
