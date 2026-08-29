#ifndef SERIAL_H
#define SERIAL_H

#ifndef HAL_BUILD_ALLOWED
#error "plat/serial.h is platform-internal. Use hal.h instead."
#endif

void serial_init(void);
void serial_puts(const char *s);

#endif
