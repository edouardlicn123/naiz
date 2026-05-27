#ifndef GPIMAGE_H
#define GPIMAGE_H

#include "hal.h"

#define GPI_HEADER_SIZE 0x0E

#define GPI_COMPRESSION      0x01
#define GPI_COMPRESSION_LZ4  0x00
#define GPI_ENDIAN           0x04
#define GPI_ENDIAN_LITTLE    0x04
#define GPI_BPC              0x08
#define GPI_BPC_8            0x08

typedef struct
{
    unsigned char __far* planes[4];
    unsigned char __far* mask_plane;
    unsigned long bytes_per_plane;
    unsigned long dec_height;
    int fd;
    unsigned short width;
    unsigned short byte_width;
    unsigned short height;
    unsigned short num_tiles;
    unsigned short filt_planes;
    unsigned char flags;
    unsigned char has_mask;
    unsigned char num_planes;
} GPIInfo;

int open_gpi_file(GPIInfo* info);
void decompress_gpi_file(GPIInfo* info);

#endif
