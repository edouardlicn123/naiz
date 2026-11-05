/*
 * hal_log.c — HAL PC-98 debug logging
 *
 * Split out of hal_pc98.c (devdoc 200 §12.2): serial log output and the
 * formatting buffer are independent of init/palette/VRAM.
 *
 * See: docs/ — HAL architecture design
 */
#include "hal.h"
#include "serial.h"
#include <stdarg.h>
#include <stdio.h>

/*
 * Debug log output.
 *
 * PC-98 implementation: outputs string via serial port.
 * In DPMI protected mode, DOS printf/text layer is invisible;
 * serial is the most reliable debug output path.
 *
 * @param s  NUL-terminated string
 */
void hal_log(const char *s) { serial_puts(s); }

/*
 * Formatted debug log output.
 *
 * printf-style convenience wrapper: formats into a stack buffer then calls
 * hal_log().  Replaces the ad-hoc snprintf+hal_log two-liner scattered across
 * the engine, giving one uniform buffer size and truncation policy.
 */
void hal_logf(const char *fmt, ...)
{
    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    hal_log(buf);
}
