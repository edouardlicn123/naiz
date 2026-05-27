#ifndef TEXTENGINE_H
#define TEXTENGINE_H

#include "graphics.h"

#define FORMAT_BOLD           0x0001
#define FORMAT_ITALIC         0x0002
#define FORMAT_UNDERLINE      0x0004
#define FORMAT_SHADOW         0x0008
#define FORMAT_FADE_SET(n)   (((n) << 8) & 0x0F00)
#define FORMAT_COLOUR_SET(n) (((n) << 12) & 0xF000)
#define FORMAT_FADE_GET(f)   (((f) & 0x0F00) >> 8)
#define FORMAT_COLOUR_GET(f) (((f) & 0xF000) >> 12)
#define FORMAT_PART_MAIN    0x000F
#define FORMAT_PART_UNUSED  0x00F0
#define FORMAT_PART_FADE    0x0F00
#define FORMAT_PART_COLOUR  0xF000

typedef struct
{
    unsigned long system_text_file_ptr;
    unsigned long credits_text_file_ptr;
    unsigned long character_names_file_ptr;
    unsigned long scene_text_file_ptr;
    unsigned long cg_text_file_ptr;
    unsigned long music_text_file_ptr;
} TextInfo;

extern TextInfo text_info;
extern Rect2Int text_box_inner_bounds;
extern ImageInfo* text_box_img_info;
extern Rect2Int char_name_box_inner_bounds;
extern ImageInfo* char_name_box_img_info;
extern Rect2Int choice_box_inner_bounds;
extern ImageInfo* choice_box_img_info;

void set_shadow_colours(const unsigned char* cols);
int setup_text_info(void);
int load_current_character_name(unsigned short char_number, char* name_buffer);
int load_scene_text(unsigned short scene_number, char __far* text_data_buffer, unsigned int* text_ptrs_buffer);
void set_custom_info(unsigned short num, char* str);
void write_string(const char __far* str, short x, short y, short format, unsigned char autolb);
void start_animated_string_write(const char __far* str, short x, short y, short format);
int string_write_animation_frame(unsigned char skip);

#endif
