#ifndef GRAPHICS_H
#define GRAPHICS_H

typedef struct { int x, y; } Vector2Int;

typedef struct { Vector2Int pos, size; } Rect2Int;

#define IMAGE_TYPE_NORMAL 0x00
#define IMAGE_TYPE_9SLICE 0x01
#define IMAGE_MEM_NORMAL  0x00
#define IMAGE_MEM_VRAM    0x02
#define IMAGE_ALIGN_FREE  0x00
#define IMAGE_ALIGN_FIXED 0x04
#define IMAGE_LOADED      0x80
#define IMAGE_DRAWN       0x40
#define IMAGE_DRAWREQ     0x20

typedef struct imginf
{
    Rect2Int boundRect;
    unsigned char __far* mask;
    unsigned char __far* plane0;
    unsigned char __far* plane1;
    unsigned char __far* plane2;
    unsigned char __far* plane3;
    struct imginf* children;
    unsigned short id;
    unsigned char layer;
    unsigned char flags;
} ImageInfo;

extern ImageInfo bg_info;
extern ImageInfo textbox_info;
extern ImageInfo charnamebox_info;
extern ImageInfo choicebox_info;

void unload_image(ImageInfo* img);
ImageInfo* load_bg_image(unsigned int num);
void do_draw_requests(void);
void redraw_everything(void);
void load_std_9slice_box_into_vram(void);
ImageInfo* register_text_box(const Rect2Int* rect);
ImageInfo* register_char_name_box(const Rect2Int* rect);
ImageInfo* register_choice_box(const Rect2Int* rect);
void draw_9slice_box_inner_region(ImageInfo* img);
int init_graphics_system(void);
void free_graphics_system(void);

#endif
