#ifndef GDC_H
#define GDC_H

#ifndef HAL_BUILD_ALLOWED
#error "plat/gdc.h is platform-internal. Use hal.h instead."
#endif

void gdc_set_palette(int idx, unsigned char r, unsigned char g, unsigned char b);
void gdc_read_palette(int idx, unsigned char *r, unsigned char *g, unsigned char *b);

#endif
