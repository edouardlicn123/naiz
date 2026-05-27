#include <stdint.h>
#include "hal.h"
#include "memalloc.h"
#include "lz4.h"
#include "gpimage.h"

static const char gpi_magic[3] = {'G', 'P', 'I'};
static unsigned char filter_buf[1024];

int open_gpi_file(GPIInfo* info)
{
    unsigned char header[GPI_HEADER_SIZE];
    int br = hal_file_read(info->fd, header, GPI_HEADER_SIZE);
    if (br < GPI_HEADER_SIZE) return -1;
    for (int i = 0; i < 3; i++)
        if (header[i] != gpi_magic[i]) return -1;

    info->flags       = header[0x03];
    unsigned short w  = *((unsigned short*)(&header[0x04])) + 1;
    unsigned short h  = *((unsigned short*)(&header[0x06])) + 1;
    unsigned short nt = *((unsigned short*)(&header[0x08])) + 1;
    unsigned short pm  = *((unsigned short*)(&header[0x0A]));
    unsigned short pfm = *((unsigned short*)(&header[0x0C]));
    info->width = w;
    info->height = h;
    info->num_tiles = nt;
    unsigned short bw = (w + 7) / 8;
    info->byte_width = bw;
    unsigned long dh = (unsigned long)h * (unsigned long)nt;
    info->dec_height = dh;
    unsigned long bpp = (unsigned long)bw * dh;
    info->bytes_per_plane = bpp;

    int np = 0;
    unsigned short filt = 0;
    unsigned short fbit = 0x01;
    unsigned short test = 0x0001;
    for (int i = 0; i < 4; i++)
    {
        if (pm & test)
        {
            if (!info->planes[np]) info->planes[np] = mem_alloc(bpp);
            if (pfm & test) filt |= fbit;
            fbit <<= 1;
            np++;
        }
        test <<= 1;
    }
    if (pm & 0x0100)
    {
        info->has_mask = 1;
        if (!info->mask_plane) info->mask_plane = mem_alloc(bpp);
        if (pfm & 0x0100) filt |= 0x0100;
        np++;
    }
    else info->has_mask = 0;
    info->filt_planes = filt;
    info->num_planes = np;
    return 0;
}

void decompress_gpi_file(GPIInfo* info)
{
    unsigned short h = info->height;
    unsigned short pw = info->byte_width;
    unsigned short dh = (unsigned short)info->dec_height;
    unsigned short filt = info->filt_planes;
    unsigned short fc = 0x01;

    for (int i = 0; i < info->num_planes; i++)
    {
        unsigned char __far* ptr;
        unsigned char is_filt;
        if (info->has_mask)
        {
            if (i == 0) { ptr = info->mask_plane; is_filt = (filt & 0x0100) ? 1 : 0; }
            else { ptr = info->planes[i - 1]; is_filt = (filt & (fc >> 1)) ? 1 : 0; }
        }
        else { ptr = info->planes[i]; is_filt = (filt & fc) ? 1 : 0; }

        if (is_filt) hal_file_read(info->fd, filter_buf, (dh + 1) / 2);

        unsigned long comp_size;
        hal_file_read(info->fd, &comp_size, 4);

        unsigned char __far* db = mem_alloc(comp_size + 4);
        *((unsigned long __far*)db) = comp_size;
        { unsigned long fa = (unsigned long)(db + 4);
          hal_file_read_far(info->fd, fa >> 16, fa & 0xFFFF, comp_size); }
        lz4_decompress(db, ptr, info->bytes_per_plane);
        mem_free(db);
        fc <<= 1;
        if (!is_filt) continue;

        unsigned char __far *p1, *p2, *p3, *p4;
        if (info->has_mask)
        {
            if (i == 0) ptr = info->mask_plane;
            else ptr = info->planes[i - 1];
            p1 = (i <= 1) ? info->mask_plane : info->planes[i - 2];
            p2 = (i <= 2) ? info->mask_plane : info->planes[i - 3];
            p3 = (i <= 3) ? info->mask_plane : info->planes[i - 4];
            p4 = info->mask_plane;
        }
        else
        {
            ptr = info->planes[i];
            p1 = info->planes[i - 1];
            p2 = info->planes[i - 2];
            p3 = info->planes[i - 3];
            p4 = 0;
        }

        for (int j = 0; j < dh; j++)
        {
            int fs = filter_buf[j >> 1];
            fs = (j & 1 ? fs >> 4 : fs) & 0xF;
            int row = j * pw;
            unsigned char carry;
            switch (fs)
            {
            case 0x0: break;
            case 0x1:
                carry = 0;
                for (int k = 0; k < pw; k++)
                {
                    unsigned char v = ptr[k + row];
                    v ^= carry; v ^= v >> 1; v ^= v >> 2; v ^= v >> 4;
                    carry = (v & 0x01) << 7;
                    ptr[k + row] = v;
                }
                break;
            case 0x2:
                for (int k = 0; k < pw; k++) ptr[k + row] ^= ptr[k + row - pw];
                break;
            case 0x3:
                for (int k = 0; k < pw; k++) ptr[k + row] ^= ptr[k + row - pw * h];
                break;
            case 0x4:
                for (int k = 0; k < pw; k++) ptr[k + row] ^= p1[k + row];
                break;
            case 0x5:
                for (int k = 0; k < pw; k++) ptr[k + row] ^= p2[k + row];
                break;
            case 0x6:
                for (int k = 0; k < pw; k++) ptr[k + row] ^= p3[k + row];
                break;
            case 0x7:
                for (int k = 0; k < pw; k++) ptr[k + row] ^= p4[k + row];
                break;
            case 0x8:
                for (int k = 0; k < pw; k++) ptr[k + row] = ~ptr[k + row];
                break;
            case 0x9:
                carry = 0;
                for (int k = 0; k < pw; k++)
                {
                    unsigned char v = ~ptr[k + row];
                    v ^= carry; v ^= v >> 1; v ^= v >> 2; v ^= v >> 4;
                    carry = (v & 0x01) << 7;
                    ptr[k + row] = v;
                }
                break;
            case 0xA:
                for (int k = 0; k < pw; k++) ptr[k + row] ^= ~ptr[k + row - pw];
                break;
            case 0xB:
                for (int k = 0; k < pw; k++) ptr[k + row] ^= ~ptr[k + row - pw * h];
                break;
            case 0xC:
                for (int k = 0; k < pw; k++) ptr[k + row] ^= ~p1[k + row];
                break;
            case 0xD:
                for (int k = 0; k < pw; k++) ptr[k + row] ^= ~p2[k + row];
                break;
            case 0xE:
                for (int k = 0; k < pw; k++) ptr[k + row] ^= ~p3[k + row];
                break;
            case 0xF:
                for (int k = 0; k < pw; k++) ptr[k + row] ^= ~p4[k + row];
                break;
            }
        }
    }
    if (info->has_mask)
    {
        unsigned char __far* mp = info->mask_plane;
        for (unsigned long i = 0; i < (unsigned long)dh * pw; i++)
            mp[i] = ~mp[i];
    }
}
