#ifndef STDBUFFER_H
#define STDBUFFER_H

extern unsigned char small_file_buffer[1024];

short sin_fixed(unsigned int x);
short cos_fixed(unsigned int x);
unsigned int atan2_fixed(short y, short x);
unsigned short sqrt_fixed(unsigned long x);

#endif
