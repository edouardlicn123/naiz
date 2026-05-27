#include "hal.h"
#include "memalloc.h"
#include "pc98_egc.h"
#include "pc98_gdc.h"
#include "x86segments.h"
#include "x86strops.h"
#include "rootinfo.h"
#include "gpimage.h"
#include "graphics.h"
#include "palette.h"
#include "textengine.h"

#define VRAM_HIDDEN_OFFSET 0x7D00

ImageInfo bg_info;
ImageInfo textbox_info;
ImageInfo charnamebox_info;
ImageInfo choicebox_info;
ImageInfo sprite1_info;
ImageInfo sprite2_info;
ImageInfo sprite3_info;
ImageInfo bg_variants[4];
ImageInfo sprite1_variants[4];
ImageInfo sprite2_variants[4];
ImageInfo sprite3_variants[4];
ImageInfo* all_infos[23] = {&bg_info, &bg_variants[0], &bg_variants[1], &bg_variants[2], &bg_variants[3],
                            &sprite1_info, &sprite1_variants[0], &sprite1_variants[1], &sprite1_variants[2], &sprite1_variants[3],
                            &sprite2_info, &sprite2_variants[0], &sprite2_variants[1], &sprite2_variants[2], &sprite2_variants[3],
                            &sprite3_info, &sprite3_variants[0], &sprite3_variants[1], &sprite3_variants[2], &sprite3_variants[3],
                            &textbox_info, &charnamebox_info, &choicebox_info};

unsigned char __far* bg_image_data_plane0;
unsigned char __far* bg_image_data_plane1;
unsigned char __far* bg_image_data_plane2;
unsigned char __far* bg_image_data_plane3;

unsigned int num_bg;
unsigned int num_spr;

void unload_image(ImageInfo* img)
{
    if (img == 0 || !(img->flags & IMAGE_LOADED)) return;
    img->flags = 0;
}

ImageInfo* load_bg_image(unsigned int num)
{
    if (bg_info.flags & IMAGE_LOADED)
    {
        if (bg_info.id == num) return &bg_info;
        unload_image(&bg_info);
    }

    unsigned long curpos;
    int fh = hal_file_open(root_info.bg_path, 0);
    if (fh < 0) return (ImageInfo*)0;

    unsigned long bgdatpos;
    hal_file_read(fh, &bgdatpos, 4);
    hal_file_seek(fh, 0, bgdatpos, &curpos);
    unsigned long this_bg_dat_pos;
    hal_file_read(fh, &this_bg_dat_pos, 4);
    this_bg_dat_pos += bgdatpos + (num_bg << 2);
    hal_file_seek(fh, 0, this_bg_dat_pos, &curpos);
    unsigned long bgimgpos;
    hal_file_read(fh, &bgimgpos, 4);
    hal_file_seek(fh, 0, this_bg_dat_pos + 6, &curpos);
    unsigned short palind;
    hal_file_read(fh, &palind, 2);
    hal_file_seek(fh, 0, 8 + 24 * ((unsigned long)palind), &curpos);
    unsigned char midpal[24];
    hal_file_read(fh, midpal, 24);
    hal_file_seek(fh, 0, bgimgpos, &curpos);
    GPIInfo gpiinf;
    gpiinf.fd = fh;
    gpiinf.planes[0] = bg_image_data_plane0;
    gpiinf.planes[1] = bg_image_data_plane1;
    gpiinf.planes[2] = bg_image_data_plane2;
    gpiinf.planes[3] = bg_image_data_plane3;
    int res = open_gpi_file(&gpiinf);
    if (!res) decompress_gpi_file(&gpiinf);
    hal_file_close(fh);
    if (!res && gpiinf.has_mask) mem_free(gpiinf.mask_plane);
    ColourRGB outpal[16];
    int mpp = 0;
    for (int i = 0; i < 16; i++)
    {
        unsigned char cb = midpal[mpp++];
        outpal[i].r = (cb & 0xF) * 0x11;
        outpal[i].g = ((cb >> 4) & 0x0F) * 0x11;
        cb = midpal[mpp++];
        outpal[i].b = (cb & 0xF) * 0x11;
        i++;
        outpal[i].r = ((cb >> 4) & 0x0F) * 0x11;
        cb = midpal[mpp++];
        outpal[i].g = (cb & 0xF) * 0x11;
        outpal[i].b = ((cb >> 4) & 0x0F) * 0x11;
    }
    set_main_palette(outpal);
        copy_main_to_out();
    set_display_palette_out();

    bg_info.boundRect.pos.x = 0;
    bg_info.boundRect.pos.y = 0;
    bg_info.boundRect.size.x = 640;
    bg_info.boundRect.size.y = 400;
    bg_info.mask = 0;
    bg_info.plane0 = bg_image_data_plane0;
    bg_info.plane1 = bg_image_data_plane1;
    bg_info.plane2 = bg_image_data_plane2;
    bg_info.plane3 = bg_image_data_plane3;
    bg_info.children = bg_variants;
    bg_info.id = num;
    bg_info.layer = 0;
    bg_info.flags = IMAGE_TYPE_NORMAL | IMAGE_MEM_NORMAL | IMAGE_ALIGN_FIXED | IMAGE_LOADED;

    if (textbox_info.flags & IMAGE_DRAWN) textbox_info.flags |= IMAGE_DRAWREQ;
    if (charnamebox_info.flags & IMAGE_DRAWN) charnamebox_info.flags |= IMAGE_DRAWREQ;
    if (choicebox_info.flags & IMAGE_DRAWN) choicebox_info.flags |= IMAGE_DRAWREQ;

    return &bg_info;
}

ImageInfo* load_sprite(unsigned int num, unsigned int slot)
{
    ImageInfo* selinfo;
    ImageInfo* selchild;
    switch (slot)
    {
        case 0: selinfo = &sprite1_info; selchild = sprite1_variants; break;
        case 1: selinfo = &sprite2_info; selchild = sprite2_variants; break;
        case 2: selinfo = &sprite3_info; selchild = sprite3_variants; break;
        default: return (ImageInfo*)0;
    }
    if (selinfo->flags & IMAGE_LOADED) unload_image(selinfo);
    int into_layer = 8 + 8 * slot;
    selinfo->boundRect.pos.x = 0;
    selinfo->boundRect.pos.y = 0;
    selinfo->boundRect.size.x = 0;
    selinfo->boundRect.size.y = 0;
    selinfo->mask = 0;
    selinfo->plane0 = 0;
    selinfo->plane1 = 0;
    selinfo->plane2 = 0;
    selinfo->plane3 = 0;
    selinfo->children = selchild;
    selinfo->id = num;
    selinfo->layer = into_layer;
    selinfo->flags = IMAGE_TYPE_NORMAL | IMAGE_MEM_NORMAL | IMAGE_ALIGN_FREE | IMAGE_LOADED;
    return selinfo;
}

static const unsigned char temp_default_text_border[1152] =
{
    0b00011000,0b00000000,0b01111111,0b11111111,0b01111111,0b11111111,0b11111111,0b11000000,
    0b11111111,0b10111111,0b01111110,0b01111111,0b00111101,0b11111111,0b01011011,0b11111111,
    0b01111011,0b00000000,0b01110111,0b00000000,0b01101111,0b01111111,0b01101111,0b00000000,
    0b01101111,0b00000000,0b01101111,0b00000000,0b01101111,0b01111111,0b01101111,0b00000000,
    0b00000000,0b00000000,0b11111111,0b11111111,0b11111111,0b11111111,0b00000001,0b10000000,
    0b11111111,0b10111111,0b11111111,0b10111111,0b11111111,0b10111111,0b11111111,0b10111111,
    0b00000001,0b10000000,0b00000111,0b11100000,0b11111111,0b11111111,0b00000001,0b10000000,
    0b00000000,0b00000000,0b00000000,0b00000000,0b11111111,0b11111111,0b00000000,0b00000000,
    0b00000000,0b00011000,0b11111111,0b11111110,0b11111111,0b11111110,0b00000011,0b11111111,
    0b11111101,0b11111111,0b11111110,0b01111110,0b11111111,0b10111100,0b11111111,0b11011010,
    0b00000000,0b11111010,0b00000000,0b11111100,0b11111110,0b11111110,0b01011110,0b11111110,
    0b00000000,0b11111110,0b00000000,0b11111110,0b11111110,0b11111110,0b01011110,0b11111110,
    0b01101111,0b00000000,0b01101111,0b00000000,0b01101111,0b01111111,0b01101111,0b00000000,
    0b01101111,0b00000000,0b01101111,0b00000000,0b01101111,0b01111111,0b01101111,0b00000000,
    0b01101111,0b00000000,0b01101111,0b00000000,0b01101111,0b01111111,0b01101111,0b00000000,
    0b01101111,0b00000000,0b01100000,0b00000000,0b01101111,0b01111111,0b01101111,0b00000000,
    0b00000000,0b00000000,0b00000000,0b00000000,0b11111111,0b11111111,0b00000000,0b00000000,
    0b00000000,0b00000000,0b00000000,0b00000000,0b11111111,0b11111111,0b00000000,0b00000000,
    0b00000000,0b00000000,0b00000000,0b00000000,0b11111111,0b11111111,0b00000000,0b00000000,
    0b00000000,0b00000000,0b00000000,0b00000000,0b11111111,0b11111111,0b00000000,0b00000000,
    0b00000000,0b11111110,0b00000000,0b11111110,0b11111110,0b11111110,0b01011110,0b11111110,
    0b00000000,0b11011110,0b00000000,0b11011110,0b11111110,0b11011110,0b01011110,0b11011110,
    0b00000000,0b11110110,0b00000000,0b11011110,0b11111110,0b11011110,0b01011110,0b11011110,
    0b00000000,0b11011110,0b00000000,0b00000110,0b11111110,0b11111110,0b01011110,0b11111110,
    0b01101111,0b00000000,0b01101111,0b00000000,0b01101111,0b01111111,0b01101111,0b00000000,
    0b01101111,0b00000000,0b01101111,0b00000000,0b01101111,0b01111111,0b01101111,0b00000000,
    0b01101111,0b11111111,0b01101111,0b11111111,0b01101111,0b11111111,0b01111111,0b11111111,
    0b01111111,0b11111111,0b00111111,0b11111111,0b01001111,0b11111111,0b00000000,0b00000000,
    0b00000000,0b00000000,0b00000000,0b00000000,0b11111111,0b11111111,0b00000000,0b00000000,
    0b00000000,0b00000000,0b00000000,0b00000000,0b11111111,0b11111111,0b00000000,0b00000000,
    0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,
    0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b00000000,0b00000000,
    0b00000000,0b11111110,0b00000000,0b11111110,0b11111110,0b11111110,0b01011110,0b11111110,
    0b00000000,0b11111110,0b00000000,0b11111110,0b11111110,0b11111110,0b00000000,0b11111110,
    0b11111111,0b11111110,0b11111111,0b11111110,0b11111111,0b11111110,0b11111111,0b11111110,
    0b11111111,0b11111110,0b11111111,0b11111100,0b11111111,0b11110010,0b00000000,0b00000000,
    0b11111111,0b11111111,0b10111100,0b00111111,0b11111110,0b01111111,0b11111111,0b11000000,
    0b11111111,0b10000000,0b01111110,0b00000000,0b10111100,0b00000000,0b10011000,0b00000000,
    0b10011000,0b00000000,0b10110000,0b00000000,0b11100000,0b00000000,0b11100000,0b01111111,
    0b11100000,0b00000000,0b11100000,0b00000000,0b11100000,0b00000000,0b11100000,0b01111111,
    0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b00000001,0b10000000,
    0b00000001,0b10000000,0b00000001,0b10000000,0b00000001,0b10000000,0b00000001,0b10000000,
    0b00000001,0b10000000,0b00000111,0b11100000,0b00000011,0b11000000,0b11111111,0b11111111,
    0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b11111111,0b11111111,
    0b11111111,0b11111111,0b11111100,0b00111100,0b11111110,0b01111110,0b00000011,0b11111111,
    0b00000001,0b11111111,0b00000000,0b01111110,0b00000000,0b00111100,0b00000000,0b00011000,
    0b00000000,0b00011000,0b01011111,0b00001100,0b10101111,0b00000110,0b11111111,0b00000110,
    0b00000001,0b00000110,0b01011111,0b00000110,0b10101111,0b00000110,0b11111111,0b00000110,
    0b11100000,0b00000000,0b11100000,0b00000000,0b11100000,0b00000000,0b11101100,0b01111111,
    0b11101100,0b00000000,0b11101100,0b00000000,0b11101100,0b00000000,0b11101100,0b01111111,
    0b11101100,0b00000000,0b11101100,0b00000000,0b11101100,0b00000000,0b11101111,0b01111111,
    0b11101111,0b00000000,0b11100000,0b00000000,0b11100000,0b00000000,0b11100000,0b01111111,
    0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b11111111,0b11111111,
    0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b11111111,0b11111111,
    0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b11111111,0b11111111,
    0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b11111111,0b11111111,
    0b00000001,0b00000110,0b01011111,0b00000110,0b10101111,0b00000110,0b11111111,0b11110110,
    0b00000001,0b11011110,0b01011111,0b11011110,0b10101111,0b11011110,0b11111111,0b11011110,
    0b00000001,0b11110110,0b01011111,0b11011110,0b10101111,0b11011110,0b11111111,0b11011110,
    0b00000001,0b11011110,0b01011111,0b00000110,0b10101111,0b00000110,0b11111111,0b00000110,
    0b11100000,0b00000000,0b11100000,0b00000000,0b11100000,0b00000000,0b11100000,0b01111111,
    0b11100000,0b00000000,0b11100000,0b00000000,0b11100000,0b00000000,0b11100000,0b11111111,
    0b11100000,0b00000000,0b11100000,0b00001111,0b11100000,0b01110000,0b11111111,0b10000000,
    0b11111110,0b00000000,0b11111100,0b00000000,0b10111000,0b00000000,0b00000000,0b00000000,
    0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b11111111,0b11111111,
    0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b11111111,0b11111111,
    0b00000000,0b00000000,0b11111000,0b00011111,0b00000110,0b01100000,0b00000001,0b10000000,
    0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,
    0b00000001,0b00000110,0b01011111,0b00000110,0b10101111,0b00000110,0b11111111,0b00000110,
    0b00000001,0b00000110,0b01011111,0b00000110,0b10101111,0b00000110,0b11111111,0b00000110,
    0b00000000,0b00000110,0b11110000,0b00000110,0b00001110,0b00000110,0b00000001,0b11111110,
    0b00000000,0b00111110,0b00000000,0b00011100,0b00000000,0b00000000,0b00000000,0b00000000,
    0b00000000,0b00000000,0b00000000,0b00000000,0b00100010,0b00111111,0b00000011,0b01000000,
    0b00000111,0b10000000,0b00001110,0b00000000,0b00111100,0b00000000,0b00011000,0b00000000,
    0b00001000,0b00000000,0b00010000,0b01111111,0b00100000,0b01111111,0b00100000,0b01111111,
    0b00100000,0b00000000,0b00100000,0b01111111,0b00100000,0b01111111,0b00100000,0b01111111,
    0b00000000,0b00000000,0b00000000,0b00000000,0b11111110,0b01111111,0b00000000,0b10000000,
    0b00000000,0b10000000,0b00000000,0b10000000,0b00000000,0b10000000,0b00000000,0b10000000,
    0b00000000,0b10000000,0b11111000,0b00111111,0b11111100,0b01111111,0b11111111,0b11111111,
    0b00000000,0b00000000,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,
    0b00000000,0b00000000,0b00000000,0b00000000,0b11111100,0b00100010,0b00000010,0b00000011,
    0b00000001,0b10000111,0b00000000,0b01001110,0b00000000,0b00111100,0b00000000,0b00011000,
    0b00000000,0b00001000,0b10100000,0b00000100,0b01010000,0b00000010,0b11111110,0b00000010,
    0b00000000,0b00000010,0b10100000,0b00000010,0b01010000,0b00000010,0b11111110,0b00000010,
    0b00100000,0b00000000,0b00100000,0b01111111,0b00100000,0b01111111,0b00100100,0b01111111,
    0b00100100,0b00000000,0b00100100,0b01111111,0b00100100,0b01111111,0b00100100,0b01111111,
    0b00100100,0b00000000,0b00100100,0b01111111,0b00100100,0b01111111,0b00100000,0b01111111,
    0b00101111,0b00000000,0b00100000,0b01111111,0b00100000,0b01111111,0b00100000,0b01111111,
    0b00000000,0b00000000,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,
    0b00000000,0b00000000,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,
    0b00000000,0b00000000,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,
    0b00000000,0b00000000,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,
    0b00000000,0b00000010,0b10100000,0b00000010,0b01010000,0b00000010,0b11111110,0b00010010,
    0b00000000,0b01001010,0b10100000,0b01001010,0b01010000,0b01001010,0b11111110,0b01001010,
    0b00000000,0b00010010,0b10100000,0b01001010,0b01010000,0b01001010,0b11111110,0b01001010,
    0b00000000,0b01001010,0b10100000,0b00000010,0b01010000,0b00000010,0b11111110,0b00000010,
    0b00100000,0b00000000,0b00100000,0b01111111,0b00100000,0b01111111,0b00100000,0b01111111,
    0b00100000,0b00000000,0b00100000,0b01111111,0b00100000,0b01111111,0b00100000,0b00000000,
    0b00100000,0b00000000,0b00100000,0b00001111,0b00100000,0b01110000,0b00000001,0b10000000,
    0b01000010,0b00000000,0b00111100,0b00000000,0b00001000,0b00000000,0b00000000,0b00000000,
    0b00000000,0b00000000,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,
    0b00000000,0b00000000,0b11111111,0b11111111,0b11111111,0b11111111,0b00000000,0b00000000,
    0b00000000,0b00000000,0b11111000,0b00011111,0b00000110,0b01100000,0b00000001,0b10000000,
    0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,
    0b00000000,0b00000010,0b10100000,0b00000010,0b01010000,0b00000010,0b11111110,0b00000010,
    0b00000000,0b00000010,0b10100000,0b00000010,0b01010000,0b00000010,0b00000000,0b00000010,
    0b00000000,0b00000010,0b11110000,0b00000010,0b00001110,0b00000010,0b00000001,0b11000010,
    0b00000000,0b00100010,0b00000000,0b00011100,0b00000000,0b00000000,0b00000000,0b00000000,
    0b11111111,0b11111111,0b11111111,0b11111111,0b11111101,0b11000000,0b11111100,0b10111111,
    0b11111000,0b01111111,0b11110001,0b11111111,0b11000011,0b11111111,0b11100111,0b11111111,
    0b11110111,0b11111111,0b11101111,0b10000101,0b11011111,0b10001010,0b11011111,0b10000101,
    0b11011111,0b10000000,0b11011111,0b10000101,0b11011111,0b10001010,0b11011111,0b10000101,
    0b11111111,0b11111111,0b11111111,0b11111111,0b00000001,0b10000000,0b11111111,0b01111111,
    0b11111111,0b01111111,0b11111111,0b01111111,0b11111111,0b01111111,0b11111111,0b01111111,
    0b11111111,0b01111111,0b11111111,0b11011111,0b11111111,0b10111111,0b11111110,0b01111111,
    0b00000000,0b00000000,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,
    0b11111111,0b11111111,0b11111111,0b11111111,0b00000011,0b11111101,0b11111101,0b11111100,
    0b11111110,0b01111000,0b11111111,0b10110001,0b11111111,0b11000011,0b11111111,0b11100111,
    0b11111111,0b11110111,0b10100001,0b11111011,0b01010001,0b11111101,0b11111111,0b11111101,
    0b00000001,0b11111101,0b10100001,0b11111101,0b01010001,0b11111101,0b11111111,0b11111101,
    0b11011111,0b10000000,0b11011111,0b10000101,0b11011111,0b10001010,0b11011011,0b10000101,
    0b11011011,0b10000000,0b11011011,0b10000101,0b11011011,0b10001010,0b11011011,0b10000101,
    0b11011011,0b10000000,0b11011011,0b10000101,0b11011011,0b10001010,0b11011111,0b10000101,
    0b11010000,0b10000000,0b11011111,0b10000101,0b11011111,0b10001010,0b11011111,0b10000101,
    0b00000000,0b00000000,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,
    0b00000000,0b00000000,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,
    0b00000000,0b00000000,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,
    0b00000000,0b00000000,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,
    0b00000001,0b11111101,0b10100001,0b11111101,0b01010001,0b11111101,0b11111111,0b11101101,
    0b00000001,0b10110101,0b10100001,0b10110101,0b01010001,0b10110101,0b11111111,0b10110101,
    0b00000001,0b11101101,0b10100001,0b10110101,0b01010001,0b10110101,0b11111111,0b10110101,
    0b00000001,0b10110101,0b10100001,0b11111101,0b01010001,0b11111101,0b11111111,0b11111101,
    0b11011111,0b10000000,0b11011111,0b10000101,0b11011111,0b10001010,0b11011111,0b10000101,
    0b11011111,0b10000000,0b11011111,0b10000101,0b11011111,0b10001010,0b11011111,0b11111111,
    0b11011111,0b11111111,0b11011111,0b11111111,0b11011111,0b11110000,0b11111111,0b10000000,
    0b11111110,0b00000000,0b11111100,0b00000000,0b11111000,0b00000000,0b11100000,0b00000000,
    0b00000000,0b00000000,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,
    0b00000000,0b00000000,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,0b11111111,
    0b11111111,0b11111111,0b11111111,0b11111111,0b00000111,0b11100000,0b00000001,0b10000000,
    0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,0b00000000,
    0b00000001,0b11111101,0b10100001,0b11111101,0b01010001,0b11111101,0b11111111,0b11111101,
    0b00000001,0b11111101,0b10100001,0b11111101,0b01010001,0b11111101,0b11111111,0b11111101,
    0b11111111,0b11111101,0b11111111,0b11111101,0b00001111,0b11111101,0b00000001,0b10111101,
    0b00000000,0b00011101,0b00000000,0b00000011,0b00000000,0b00001111,0b00000000,0b00000111
};

static void load_std_9slice_bitmap(void)
{
    egc_disable();
    unsigned short src_seg = hal_get_cs();
    unsigned short src_off = (unsigned short)&temp_default_text_border[0];
    unsigned short dst_off = VRAM_HIDDEN_OFFSET;

    __asm volatile (
        "movw $0xA800, %%ax\n\t" "movw %%ax, %%es\n\t"
        "movw %0, %%ds\n\t"
        "movw %2, %%si\n\t" "movw %3, %%di\n\t" "movw $144, %%cx\n\t" "rep movsw\n\t"
        "movw $0xB000, %%ax\n\t" "movw %%ax, %%es\n\t"
        "movw %3, %%di\n\t" "movw $144, %%cx\n\t" "rep movsw\n\t"
        "movw $0xB800, %%ax\n\t" "movw %%ax, %%es\n\t"
        "movw %3, %%di\n\t" "movw $144, %%cx\n\t" "rep movsw\n\t"
        "movw $0xE000, %%ax\n\t" "movw %%ax, %%es\n\t"
        "movw %3, %%di\n\t" "movw $144, %%cx\n\t" "rep movsw\n\t"
        "movw %1, %%ds\n\t"
    : : "rm" (src_seg), "rm" (hal_get_ss()), "rm" (src_off), "rm" (dst_off) : "%ax", "%si", "%di", "%cx", "%es", "%ds");

    egc_enable();
    egc_set_plane_access(0xF);
    egc_set_mask(0xFFFF);
    egc_set_bg_colour(0xC);
    egc_set_to_mono_draw_mode();
}

static void register_std_9slice_box(unsigned char layer, ImageInfo* img, const Rect2Int* rect)
{
    img->boundRect = *rect;
    img->mask = 0;
    img->plane0 = (0xA8000000 + VRAM_HIDDEN_OFFSET);
    img->plane1 = (0xB0000000 + VRAM_HIDDEN_OFFSET);
    img->plane2 = (0xB8000000 + VRAM_HIDDEN_OFFSET);
    img->plane3 = (0xE0000000 + VRAM_HIDDEN_OFFSET);
    img->children = (ImageInfo*)0;
    img->layer = layer;
    img->flags = IMAGE_TYPE_9SLICE | IMAGE_MEM_VRAM | IMAGE_ALIGN_FIXED | IMAGE_LOADED;
}

ImageInfo* register_text_box(const Rect2Int* rect)
{
    register_std_9slice_box(128, &textbox_info, rect);
    return &textbox_info;
}

ImageInfo* register_char_name_box(const Rect2Int* rect)
{
    register_std_9slice_box(129, &charnamebox_info, rect);
    return &charnamebox_info;
}

ImageInfo* register_choice_box(const Rect2Int* rect)
{
    register_std_9slice_box(130, &choicebox_info, rect);
    return &choicebox_info;
}

static void draw_normal_image(ImageInfo* img, Rect2Int* out_rect)
{
    int dx = img->boundRect.pos.x;
    int dy = img->boundRect.pos.y;
    int sw = img->boundRect.size.x;
    int sh = img->boundRect.size.y;
    int x, y, w, h, sx, sy;
    if (out_rect == 0)
    {
        x = dx; y = dy; w = sw; h = sh;
        sx = 0; sy = 0;
    }
    else
    {
        x = out_rect->pos.x;
        y = out_rect->pos.y;
        w = out_rect->size.x;
        h = out_rect->size.y;
        if (x + w > dx + sw) w = dx + sw - x;
        if (x < dx) x = dx;
        if (y + h > dy + sh) h = dy + sh - y;
        if (y < dy) y = dy;
        sx = x - dx; sy = y - dy;
    }
    int dbytex = ((x + 0xF) & 0xFFF0) >> 3;
    int dwordw = ((w + 0xF) & 0xFFF0) >> 4;
    int dsttlpos = dbytex + 80 * y;
    int dstaddamt = 2 * (40 - dwordw);
    int sbytex = ((sx + 0xF) & 0xFFF0) >> 3;
    int swordw = ((sw + 0xF) & 0xFFF0) >> 4;
    int srctlpos = sbytex + 2 * swordw * sy;
    int srcaddamt = 2 * (swordw - dwordw);
    int xinblock = x & 0xF;

    if (xinblock) return;
    if (img->mask != 0) return;

    egc_disable();

    if (img->plane0 != 0)
    {
        unsigned short po = ((unsigned short)img->plane0) + srctlpos;
        unsigned short ps = ((unsigned long)img->plane0) >> 16;
        __asm volatile (
            "movw $0xA800, %%ax\n\t" "movw %%ax, %%es\n\t"
            "movw %0, %%si\n\t" "movw %1, %%di\n\t"
            "movw %2, %%dx\n\t" "movw %3, %%bx\n\t"
            "movw %5, %%ax\n\t" "movw %%ax, %%cs:.add1%=+2\n\t"
            "movw %6, %%ax\n\t" "movw %%ax, %%cs:.add2%=+2\n\t"
            "movw %4, %%ax\n\t" "movw %%ax, %%ds\n\t"
            ".loop%=: movw %%dx, %%cx\n\t" "rep movsw\n\t"
            ".add1%=: addw $0x6969, %%si\n\t"
            ".add2%=: addw $0x6969, %%di\n\t"
            "decw %%bx\n\t" "jnz .loop%=\n\t"
        : : "m" (po), "m" (dsttlpos), "m" (dwordw), "m" (h), "m" (ps), "m" (srcaddamt), "m" (dstaddamt) : "%ax", "%cx", "%dx", "%bx", "%si", "%di", "%ds", "%es");
    }
    if (img->plane1 != 0)
    {
        unsigned short po = ((unsigned short)img->plane1) + srctlpos;
        unsigned short ps = ((unsigned long)img->plane1) >> 16;
        __asm volatile (
            "movw $0xB000, %%ax\n\t" "movw %%ax, %%es\n\t"
            "movw %0, %%si\n\t" "movw %1, %%di\n\t"
            "movw %2, %%dx\n\t" "movw %3, %%bx\n\t"
            "movw %5, %%ax\n\t" "movw %%ax, %%cs:.add1%=+2\n\t"
            "movw %6, %%ax\n\t" "movw %%ax, %%cs:.add2%=+2\n\t"
            "movw %4, %%ax\n\t" "movw %%ax, %%ds\n\t"
            ".loop%=: movw %%dx, %%cx\n\t" "rep movsw\n\t"
            ".add1%=: addw $0x6969, %%si\n\t"
            ".add2%=: addw $0x6969, %%di\n\t"
            "decw %%bx\n\t" "jnz .loop%=\n\t"
        : : "m" (po), "m" (dsttlpos), "m" (dwordw), "m" (h), "m" (ps), "m" (srcaddamt), "m" (dstaddamt) : "%ax", "%cx", "%dx", "%bx", "%si", "%di", "%ds", "%es");
    }
    if (img->plane2 != 0)
    {
        unsigned short po = ((unsigned short)img->plane2) + srctlpos;
        unsigned short ps = ((unsigned long)img->plane2) >> 16;
        __asm volatile (
            "movw $0xB800, %%ax\n\t" "movw %%ax, %%es\n\t"
            "movw %0, %%si\n\t" "movw %1, %%di\n\t"
            "movw %2, %%dx\n\t" "movw %3, %%bx\n\t"
            "movw %5, %%ax\n\t" "movw %%ax, %%cs:.add1%=+2\n\t"
            "movw %6, %%ax\n\t" "movw %%ax, %%cs:.add2%=+2\n\t"
            "movw %4, %%ax\n\t" "movw %%ax, %%ds\n\t"
            ".loop%=: movw %%dx, %%cx\n\t" "rep movsw\n\t"
            ".add1%=: addw $0x6969, %%si\n\t"
            ".add2%=: addw $0x6969, %%di\n\t"
            "decw %%bx\n\t" "jnz .loop%=\n\t"
        : : "m" (po), "m" (dsttlpos), "m" (dwordw), "m" (h), "m" (ps), "m" (srcaddamt), "m" (dstaddamt) : "%ax", "%cx", "%dx", "%bx", "%si", "%di", "%ds", "%es");
    }
    if (img->plane3 != 0)
    {
        unsigned short po = ((unsigned short)img->plane3) + srctlpos;
        unsigned short ps = ((unsigned long)img->plane3) >> 16;
        __asm volatile (
            "movw $0xE000, %%ax\n\t" "movw %%ax, %%es\n\t"
            "movw %0, %%si\n\t" "movw %1, %%di\n\t"
            "movw %2, %%dx\n\t" "movw %3, %%bx\n\t"
            "movw %5, %%ax\n\t" "movw %%ax, %%cs:.add1%=+2\n\t"
            "movw %6, %%ax\n\t" "movw %%ax, %%cs:.add2%=+2\n\t"
            "movw %4, %%ax\n\t" "movw %%ax, %%ds\n\t"
            ".loop%=: movw %%dx, %%cx\n\t" "rep movsw\n\t"
            ".add1%=: addw $0x6969, %%si\n\t"
            ".add2%=: addw $0x6969, %%di\n\t"
            "decw %%bx\n\t" "jnz .loop%=\n\t"
        : : "m" (po), "m" (dsttlpos), "m" (dwordw), "m" (h), "m" (ps), "m" (srcaddamt), "m" (dstaddamt) : "%ax", "%cx", "%dx", "%bx", "%si", "%di", "%ds", "%es");
    }

    egc_enable();
    egc_set_plane_access(0xF);
    egc_set_mask(0xFFFF);
    egc_set_bg_colour(0xC);
    egc_set_to_mono_draw_mode();
}

static void draw_9slice_box_vram(ImageInfo* img)
{
    int x = img->boundRect.pos.x;
    int y = img->boundRect.pos.y;
    int w = img->boundRect.size.x;
    int h = img->boundRect.size.y;
    egc_set_to_vram_blit();
    egc_set_bit_length(16);
    int bytex = ((x + 0xF) & 0xFFF0) >> 3;
    int bytew = ((w + 0xF) & 0xFFF0) >> 3;
    int wordw = ((w + 0xF) & 0xFFF0) >> 4;
    int trueh = (h + 0xF) & 0xFFF0;
    int tileh = trueh >> 4;
    int tlpos = bytex + 80 * y;
    int trpos = tlpos + bytew - 2;
    int blpos = bytex + 80 * (y + trueh - 16);
    int brpos = blpos + bytew - 2;
    int tpos = tlpos + 2;
    int bpos = blpos + 2;
    int lpos = tlpos + 1280;
    int rpos = trpos + 1280;
    int cpos = lpos + 2;
    int unrolled_iter = ((tileh - 3) >> 2) + 1;
    int jump_amt = (3 - ((tileh - 3) & 0x3)) * 5;
    int centerh = tileh - 2;
    int centerw = wordw - 2;
    int addamt = 2 * (40 - centerw);
    int ext_addamt = addamt + 1200;
    int vert_sub_amt = 1280 * centerh - 80;

    unsigned short tileaddr[9];
    tileaddr[0] = (unsigned short)img->plane0;
    for (int i = 1; i < 9; i++) tileaddr[i] = tileaddr[0] + i * 0x20;

    __asm volatile (
        "movw $0xA800, %%ax\n\t" "movw %%ax, %%ds\n\t" "movw %%ax, %%es\n\t"
        "movw %16, %%si\n\t" "movw %0, %%di\n\t"
        "leaw 0x500(%%di), %%bx\n\t" "movw $78, %%dx\n\t"
        ".loop1%=: movsw\n\t" "addw %%dx, %%di\n\t" "movsw\n\t"
        "addw %%dx, %%di\n\t" "movsw\n\t" "addw %%dx, %%di\n\t"
        "movsw\n\t" "addw %%dx, %%di\n\t" "cmpw %%bx, %%di\n\t" "jne .loop1%=\n\t"
        "movw %18, %%si\n\t" "movw %1, %%di\n\t"
        "leaw 0x500(%%di), %%bx\n\t"
        ".loop2%=: movsw\n\t" "addw %%dx, %%di\n\t" "movsw\n\t"
        "addw %%dx, %%di\n\t" "movsw\n\t" "addw %%dx, %%di\n\t"
        "movsw\n\t" "addw %%dx, %%di\n\t" "cmpw %%bx, %%di\n\t" "jne .loop2%=\n\t"
        "movw %22, %%si\n\t" "movw %2, %%di\n\t"
        "leaw 0x500(%%di), %%bx\n\t"
        ".loop3%=: movsw\n\t" "addw %%dx, %%di\n\t" "movsw\n\t"
        "addw %%dx, %%di\n\t" "movsw\n\t" "addw %%dx, %%di\n\t"
        "movsw\n\t" "addw %%dx, %%di\n\t" "cmpw %%bx, %%di\n\t" "jne .loop3%=\n\t"
        "movw %24, %%si\n\t" "movw %3, %%di\n\t"
        "leaw 0x500(%%di), %%bx\n\t"
        ".loop4%=: movsw\n\t" "addw %%dx, %%di\n\t" "movsw\n\t"
        "addw %%dx, %%di\n\t" "movsw\n\t" "addw %%dx, %%di\n\t"
        "movsw\n\t" "addw %%dx, %%di\n\t" "cmpw %%bx, %%di\n\t" "jne .loop4%=\n\t"
        "movw %19, %%si\n\t" "movw %4, %%di\n\t"
        "movw $.loop51%=, %%bx\n\t" "addw %10, %%bx\n\t" "movw $16, %%dx\n\t"
        ".loop5%=: lodsw\n\t" "movw %9, %%cx\n\t" "jmp *%%bx\n\t"
        ".loop51%=: stosw\n\t" "addw $1278, %%di\n\t" "stosw\n\t"
        "addw $1278, %%di\n\t" "stosw\n\t" "addw $1278, %%di\n\t"
        "stosw\n\t" "addw $1278, %%di\n\t" "decw %%cx\n\t" "jnz .loop51%=\n\t"
        "subw %13, %%di\n\t" "decw %%dx\n\t" "jnz .loop5%=\n\t"
        "movw %21, %%si\n\t" "movw %5, %%di\n\t"
        "movw $.loop61%=, %%bx\n\t" "addw %10, %%bx\n\t" "movw $16, %%dx\n\t"
        ".loop6%=: lodsw\n\t" "movw %9, %%cx\n\t" "jmp *%%bx\n\t"
        ".loop61%=: stosw\n\t" "addw $1278, %%di\n\t" "stosw\n\t"
        "addw $1278, %%di\n\t" "stosw\n\t" "addw $1278, %%di\n\t"
        "stosw\n\t" "addw $1278, %%di\n\t" "decw %%cx\n\t" "jnz .loop61%=\n\t"
        "subw %13, %%di\n\t" "decw %%dx\n\t" "jnz .loop6%=\n\t"
        "movw %17, %%si\n\t" "movw %6, %%di\n\t"
        "leaw 0x500(%%di), %%bx\n\t" "movw %12, %%dx\n\t"
        "push %%bp\n\t" "movw %11, %%bp\n\t"
        ".loop7%=: lodsw\n\t" "movw %%bp, %%cx\n\t" "rep stosw\n\t"
        "addw %%dx, %%di\n\t" "cmpw %%bx, %%di\n\t" "jne .loop7%=\n\t" "pop %%bp\n\t"
        "movw %23, %%si\n\t" "movw %7, %%di\n\t"
        "leaw 0x500(%%di), %%bx\n\t" "movw %12, %%dx\n\t"
        "push %%bp\n\t" "movw %11, %%bp\n\t"
        ".loop8%=: lodsw\n\t" "movw %%bp, %%cx\n\t" "rep stosw\n\t"
        "addw %%dx, %%di\n\t" "cmpw %%bx, %%di\n\t" "jne .loop8%=\n\t" "pop %%bp\n\t"
        "movw %20, %%si\n\t" "movw %8, %%di\n\t"
        "movw $16, %%dx\n\t" "movw %13, %%ax\n\t"
        "movw %%ax, %%cs:.sub1%=+2\n\t" "movw %14, %%ax\n\t"
        "movw %%ax, %%cs:.mov1%=+1\n\t" "movw %15, %%ax\n\t"
        "movw %%ax, %%cs:.add1%=+2\n\t" "push %%bp\n\t" "movw %11, %%bp\n\t"
        ".loop91%=: lodsw\n\t"
        ".mov1%=: movw $0x6969, %%bx\n\t"
        ".loop9%=: movw %%bp, %%cx\n\t" "rep stosw\n\t"
        ".add1%=: addw $0x6969, %%di\n\t" "decw %%bx\n\t" "jnz .loop9%=\n\t"
        ".sub1%=: subw $0x6969, %%di\n\t" "decw %%dx\n\t" "jnz .loop91%=\n\t" "pop %%bp\n\t"
    : : "m" (tlpos), "m" (trpos), "m" (blpos), "m" (brpos), "m" (lpos), "m" (rpos), "m" (tpos), "m" (bpos), "m" (cpos), "m" (unrolled_iter), "m" (jump_amt), "m" (centerw), "m" (addamt), "m" (vert_sub_amt), "m" (centerh), "m" (ext_addamt), "m" (tileaddr[0]), "m" (tileaddr[1]), "m" (tileaddr[2]), "m" (tileaddr[3]), "m" (tileaddr[4]), "m" (tileaddr[5]), "m" (tileaddr[6]), "m" (tileaddr[7]), "m" (tileaddr[8]) : "%ax", "%cx", "%dx", "%bx", "%si", "%di", "%ds", "%es");

    egc_set_to_mono_draw_mode();
}

void draw_9slice_box_inner_region(ImageInfo* img)
{
    int x = img->boundRect.pos.x;
    int y = img->boundRect.pos.y;
    int w = img->boundRect.size.x;
    int h = img->boundRect.size.y;
    egc_set_to_vram_blit();
    egc_set_bit_length(16);
    int bytex = ((x + 0xF) & 0xFFF0) >> 3;
    int bytew = ((w + 0xF) & 0xFFF0) >> 3;
    int wordw = ((w + 0xF) & 0xFFF0) >> 4;
    int trueh = (h + 0xF) & 0xFFF0;
    int tileh = trueh >> 4;
    int tlpos = bytex + 80 * y;
    int blpos = bytex + 80 * (y + trueh - 16);
    int bpos = blpos + 2;
    int cpos = tlpos + 1282;
    int centerh = tileh - 2;
    int centerw = wordw - 2;
    int ext_addamt = 2 * (40 - centerw) + 1200;
    int vert_sub_amt = 1280 * centerh - 80;

    unsigned short tileaddr[2];
    tileaddr[0] = (unsigned short)img->plane0 + 0x80;
    tileaddr[1] = tileaddr[0] + 0x60;

    __asm volatile (
        "movw $0xA800, %%ax\n\t" "movw %%ax, %%ds\n\t" "movw %%ax, %%es\n\t"
        "movw %6, %%si\n\t" "movw %0, %%di\n\t"
        "movw $16, %%dx\n\t" "movw %3, %%ax\n\t"
        "movw %%ax, %%cs:.sub1%=+2\n\t" "movw %4, %%ax\n\t"
        "movw %%ax, %%cs:.mov1%=+1\n\t" "movw %5, %%ax\n\t"
        "movw %%ax, %%cs:.add1%=+2\n\t" "push %%bp\n\t" "movw %2, %%bp\n\t"
        ".loop1%=: lodsw\n\t"
        ".mov1%=: movw $0x6969, %%bx\n\t"
        ".loop0%=: movw %%bp, %%cx\n\t" "rep stosw\n\t"
        ".add1%=: addw $0x6969, %%di\n\t" "decw %%bx\n\t" "jnz .loop0%=\n\t"
        ".sub1%=: subw $0x6969, %%di\n\t" "decw %%dx\n\t" "jnz .loop1%=\n\t" "pop %%bp\n\t"
        "movw %7, %%si\n\t" "movw %1, %%di\n\t"
        "lodsw\n\t" "movw %2, %%cx\n\t" "rep stosw\n\t"
    : : "m" (cpos), "m" (bpos), "m" (centerw), "m" (vert_sub_amt), "m" (centerh), "m" (ext_addamt), "m" (tileaddr[0]), "m" (tileaddr[1]) : "%ax", "%cx", "%dx", "%bx", "%si", "%di", "%ds", "%es");

    egc_set_to_mono_draw_mode();
}

static void draw_image(ImageInfo* img)
{
    if (img == 0) return;
    unsigned char fl = img->flags;
    if (!(fl & IMAGE_LOADED) || fl & IMAGE_DRAWN) return;
    if (fl & IMAGE_ALIGN_FIXED) img->boundRect.pos.x &= 0xFFF0;

    if (fl & IMAGE_TYPE_9SLICE)
    {
        if (fl & IMAGE_MEM_VRAM) draw_9slice_box_vram(img);
    }
    else
    {
        if (!(fl & IMAGE_MEM_VRAM)) draw_normal_image(img, (Rect2Int*)0);
    }
    img->flags |= IMAGE_DRAWN;
}

static void undraw_image(ImageInfo* img)
{
    if (img == 0) return;
    unsigned char fl = img->flags;
    if (!(fl & IMAGE_LOADED) || !(fl & IMAGE_DRAWN)) return;

    Rect2Int overdraw_rect = img->boundRect;
    int lx = overdraw_rect.pos.x;
    int rx = lx + overdraw_rect.size.x;
    lx &= 0xFFF0;
    rx = ((rx + 0xF) & 0xFFF0);
    overdraw_rect.size.x = rx - lx;
    overdraw_rect.pos.x = lx;
    draw_normal_image(&bg_info, &overdraw_rect);

    img->flags &= ~IMAGE_DRAWN;
}

void do_draw_requests(void)
{
    for (int i = 0; i < 23; i++)
    {
        ImageInfo* img = all_infos[i];
        unsigned char fl = img->flags;
        if (!(fl & IMAGE_LOADED)) continue;
        fl ^= img->flags >> 1;
        if (!(fl & IMAGE_DRAWREQ)) continue;
        fl = img->flags & IMAGE_DRAWREQ;
        if (fl) draw_image(img);
        else undraw_image(img);
    }
}

void redraw_everything(void)
{
    for (int i = 0; i < 23; i++)
    {
        ImageInfo* img = all_infos[i];
        unsigned char fl = img->flags;
        if (!(fl & IMAGE_LOADED)) continue;
        if (fl & IMAGE_DRAWREQ) img->flags |= IMAGE_DRAWN;
        fl = img->flags & IMAGE_DRAWN;
        if (fl)
        {
            img->flags &= ~IMAGE_DRAWN;
            draw_image(img);
        }
    }
}

int init_graphics_system(void)
{
    unsigned long curpos;
    int fh = hal_file_open(root_info.bg_path, 0);
    if (fh < 0) return -1;
    hal_file_seek(fh, 0, 4, &curpos);
    hal_file_read(fh, &num_bg, 2);
    hal_file_close(fh);
    fh = hal_file_open(root_info.sprite_path, 0);
    if (fh < 0) return -1;
    hal_file_read(fh, &num_spr, 2);
    hal_file_close(fh);

    load_std_9slice_bitmap();
    bg_image_data_plane0 = mem_alloc(32000);
    bg_image_data_plane1 = mem_alloc(32000);
    bg_image_data_plane2 = mem_alloc(32000);
    bg_image_data_plane3 = mem_alloc(32000);

    bg_info.flags = 0; bg_info.id = 0xFFFF;
    textbox_info.flags = 0; charnamebox_info.flags = 0; choicebox_info.flags = 0;
    sprite1_info.flags = 0; sprite1_info.id = 0xFFFF;
    sprite2_info.flags = 0; sprite2_info.id = 0xFFFF;
    sprite3_info.flags = 0; sprite3_info.id = 0xFFFF;
    for (int i = 0; i < 4; i++)
    {
        bg_variants[i].flags = 0; bg_variants[i].id = 0xFFFF;
        sprite1_variants[i].flags = 0; sprite1_variants[i].id = 0xFFFF;
        sprite2_variants[i].flags = 0; sprite2_variants[i].id = 0xFFFF;
        sprite3_variants[i].flags = 0; sprite3_variants[i].id = 0xFFFF;
    }
    return 0;
}

void free_graphics_system(void)
{
    mem_free(bg_image_data_plane0);
    mem_free(bg_image_data_plane1);
    mem_free(bg_image_data_plane2);
    mem_free(bg_image_data_plane3);
}
