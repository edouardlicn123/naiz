/*
 * hal_pc98.c — HAL PC-98 platform implementation (init / palette / VRAM)
 *
 * Implements the base platform abstraction declared in hal.h and delegates
 * each call to its concrete module:
 *   - hal_init()          -> serial_init() + hal_clock_init()
 *   - hal_set_palette()   -> gdc_set_palette()
 *   - hal_read_palette()  -> gdc_read_palette()
 *   - hal_vram_*()        -> PEGC bank window
 *
 * Wall clock and vsync were split into plat/hal_clock.c, debug logging into
 * plat/hal_log.c, and the interrupt-capability probes into plat/hal_probe.c
 * (devdoc 200 §12.2).  The audio HAL lives in plat/hal_audio.c (MPU-401 MIDI
 * + 86-board PCM, devdoc 101).  Keyboard/mouse/video implementations live
 * directly in keyboard.c / mouse.c / video.c.
 *
 * When porting to a new platform, only the delegation targets inside plat/
 * need to change.
 *
 * See: docs/ — HAL architecture design
 */
#include "hal.h"
#include "hal_internal.h"
#include "pc98.h"
#include "serial.h"
#include "gdc.h"

/*
 * Platform initialization.
 *
 * PC-98 implementation: initializes uPD8251 serial port (COM1, 9600 8N1)
 * as the debug log output channel, and the virtual wall clock.
 */
void hal_init(void) { serial_init(); hal_clock_init(); }

/*
 * Set RGB values for a palette index.
 *
 * Delegates to gdc_set_palette() via GDC PEGC ports 0xA8-0xAE.
 *
 * @param idx  Palette index (0-255)
 * @param r    Red component (0-255)
 * @param g    Green component (0-255)
 * @param b    Blue component (0-255)
 */
void hal_set_palette(int idx, uint8_t r, uint8_t g, uint8_t b) {
    gdc_set_palette(idx, r, g, b);
}

/*
 * Read RGB values for a palette index.
 *
 * Delegates to gdc_read_palette() via GDC PEGC ports 0xA8-0xAE.
 *
 * @param idx  Palette index (0-255)
 * @param r    Output pointer for red component
 * @param g    Output pointer for green component
 * @param b    Output pointer for blue component
 */
void hal_read_palette(int idx, uint8_t *r, uint8_t *g, uint8_t *b) {
    gdc_read_palette(idx, (unsigned char *)r, (unsigned char *)g, (unsigned char *)b);
}

/*
 * VRAM banked access — abstract PEGC bank port and window address
 * so engine rendering code does not reference hardware addresses.
 */
void hal_vram_bank_select(int bank)
{
    *PEGC_BANK_PORT = (uint16_t)bank;
}

volatile uint8_t *hal_vram_get_window(void)
{
    return (volatile uint8_t *)0xA8000L;
}
