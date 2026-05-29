#include "hal.h"
#include "memalloc.h"
#include "pc98_egc.h"
#include "pc98_gdc.h"
#include "x86segments.h"
#include "x86strops.h"
#include "lz4.h"
#include "fontfile.h"
#include "stdbuffer.h"
#include "rootinfo.h"
#include "graphics.h"
#include "scenevm.h"
#include "textengine.h"

TextInfo text_info;

unsigned long charbuf[16];
unsigned long anim_char_buf[16 * 16];
short char_xs[16];
short char_ys[16];
char char_colours[16];
char char_flags[16];
unsigned char char_fade[16];
unsigned short ch_buf_start_num;
const char* string_to_anim_write;
const char* cur_anim_string_pos;
short current_anim_write_x;
short current_anim_write_y;
short current_anim_next_write_x;
short current_anim_next_write_y;
short current_anim_default_format;
short current_anim_format;
unsigned char anim_reached_end_of_string;
short anim_length;
short wait_frames;
short wait_per_char;

Rect2Int text_box_inner_bounds;
ImageInfo* text_box_img_info;
Rect2Int char_name_box_inner_bounds;
ImageInfo* char_name_box_img_info;
Rect2Int choice_box_inner_bounds;
ImageInfo* choice_box_img_info;

unsigned char shadow_colours[16];

const unsigned short bayer4x4masks[64] =
{
    0x8888, 0x0000, 0x0000, 0x0000,
    0x8888, 0x0000, 0x2222, 0x0000,
    0x8888, 0x0000, 0xAAAA, 0x0000,
    0xAAAA, 0x0000, 0xAAAA, 0x0000,
    0xAAAA, 0x4444, 0xAAAA, 0x0000,
    0xAAAA, 0x4444, 0xAAAA, 0x1111,
    0xAAAA, 0x4444, 0xAAAA, 0x5555,
    0xAAAA, 0x5555, 0xAAAA, 0x5555,
    0xAAAA, 0xDDDD, 0xAAAA, 0x5555,
    0xAAAA, 0xDDDD, 0xAAAA, 0x7777,
    0xAAAA, 0xDDDD, 0xAAAA, 0xFFFF,
    0xAAAA, 0xFFFF, 0xAAAA, 0xFFFF,
    0xEEEE, 0xFFFF, 0xAAAA, 0xFFFF,
    0xEEEE, 0xFFFF, 0xBBBB, 0xFFFF,
    0xEEEE, 0xFFFF, 0xFFFF, 0xFFFF,
    0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF
};

char* custom_infos[16];
char string_buffer1[512];
char string_buffer2[512];

void set_shadow_colours(const unsigned char* cols)
{
    hal_memcpy16_near(cols, shadow_colours, 8);
}

int setup_text_info(void)
{
    int fh = hal_file_open(root_info.cur_text_path, 0);
    if (fh < 0)
    {
        write_string("Error! Could not find text data file!", 172, 184, FORMAT_SHADOW | FORMAT_COLOUR_SET(0xF), 0);
        return -1;
    }
    hal_file_read(fh, small_file_buffer, 0x18);
    text_info.system_text_file_ptr = *((unsigned long*)(small_file_buffer));
    text_info.credits_text_file_ptr = *((unsigned long*)(small_file_buffer + 4));
    text_info.character_names_file_ptr = *((unsigned long*)(small_file_buffer + 8));
    text_info.scene_text_file_ptr = *((unsigned long*)(small_file_buffer + 0x0C));
    text_info.cg_text_file_ptr = *((unsigned long*)(small_file_buffer + 0x10));
    text_info.music_text_file_ptr = *((unsigned long*)(small_file_buffer + 0x14));
    hal_file_close(fh);
    return 0;
}

int load_current_character_name(unsigned short char_number, char* name_buffer)
{
    unsigned long curpos;
    unsigned short charnamepos;
    int fh = hal_file_open(root_info.cur_text_path, 0);
    if (fh < 0)
    {
        write_string("Error! Could not find text data file!", 172, 184, FORMAT_SHADOW | FORMAT_COLOUR_SET(0xF), 0);
        return -1;
    }
    hal_file_seek(fh, 0, text_info.character_names_file_ptr + 2 * char_number, &curpos);
    hal_file_read(fh, &charnamepos, 2);
    hal_file_seek(fh, 0, text_info.character_names_file_ptr + 2 * scene_info.num_chars + charnamepos, &curpos);
    hal_file_read(fh, name_buffer, 64);
    hal_file_close(fh);
    return 0;
}

int load_scene_text(unsigned short scene_number, char __far* text_data_buffer, unsigned int* text_ptrs_buffer)
{
    unsigned long curpos;
    unsigned long scenedatpos;
    unsigned short num_texts;
    int fh = hal_file_open(root_info.cur_text_path, 0);
    if (fh < 0)
    {
        write_string("Error! Could not find text data file!", 172, 184, FORMAT_SHADOW | FORMAT_COLOUR_SET(0xF), 0);
        return -1;
    }
    hal_file_seek(fh, 0, text_info.scene_text_file_ptr + 4 * scene_number, &curpos);
    hal_file_read(fh, &scenedatpos, 4);
    hal_file_seek(fh, 0, text_info.scene_text_file_ptr + 4 * scene_info.num_scenes, &curpos);
    hal_file_read(fh, &num_texts, 2);
    hal_file_read(fh, small_file_buffer, sizeof(small_file_buffer));
    for (int i = 0; i < num_texts; i++)
    {
        text_ptrs_buffer[i] = *((unsigned short*)(small_file_buffer) + i) + (unsigned int)(((unsigned long)text_data_buffer) & 0x0000FFFF);
    }
    hal_file_seek(fh, 0, text_info.scene_text_file_ptr + 4 * scene_info.num_scenes + 2 * (num_texts + 1), &curpos);
    unsigned long comp_size;
    hal_file_read(fh, &comp_size, 4);
    unsigned char __far* cmp_data = mem_alloc(comp_size + 4);
    *((unsigned long __far*)cmp_data) = comp_size;
    { unsigned long fa = (unsigned long)(cmp_data + 4);
      hal_file_read_far(fh, fa >> 16, fa & 0xFFFF, comp_size); }
    lz4_decompress(cmp_data, text_data_buffer, comp_size);
    mem_free(cmp_data);
    hal_file_close(fh);
    return 0;
}

void set_custom_info(unsigned short num, char* str)
{
    custom_infos[num] = str;
}

static void bolden_char_left(unsigned long* charb, int bits32)
{
    if (!bits32)
    {
        for (unsigned short i = 0; i < 16; i++)
        {
            unsigned short a = ((unsigned short*)charb)[2*i + 1];
            unsigned short b = a << 1;
            b |= a; a ^= b; b &= ~(a << 1);
            ((unsigned short*)charb)[2*i + 1] = b;
        }
    }
    else
    {
        for (unsigned short i = 0; i < 16; i++)
        {
            unsigned long a = charb[i];
            unsigned long b = a << 1;
            b |= a; a ^= b; b &= ~(a << 1);
            charb[i] = b;
        }
    }
}

static void bolden_char_right(unsigned long* charb, int bits32)
{
    if (!bits32)
    {
        for (unsigned short i = 0; i < 16; i++)
        {
            unsigned short a = ((unsigned short*)charb)[2*i + 1];
            unsigned short b = a >> 1;
            b |= a; a ^= b; b &= ~(a >> 1);
            ((unsigned short*)charb)[2*i + 1] = b;
        }
    }
    else
    {
        for (unsigned short i = 0; i < 16; i++)
        {
            unsigned long a = charb[i];
            unsigned long b = a >> 1;
            b |= a; a ^= b; b &= ~(a >> 1);
            charb[i] = b;
        }
    }
}

static void italicise_char(unsigned long* charb, int bits32)
{
    if (!bits32)
    {
        for (unsigned short i = 0; i < 16; i++)
        {
            unsigned long c = ((unsigned short*)charb)[2*i + 1];
            c >>= 7 - (i >> 1);
            ((unsigned short*)charb)[2*i + 1] = c;
        }
    }
    else
    {
        for (unsigned short i = 0; i < 16; i++)
        {
            unsigned long c = charb[i];
            c >>= 7 - (i >> 1);
            charb[i] = c;
        }
    }
}

static void underline_char(unsigned long* charb, short underline_len)
{
    long ul = 0x80000000;
    if (underline_len > 32) underline_len = 32;
    underline_len--;
    ul >>= underline_len;
    charb[14] |= ul;
}

static void mask_char(unsigned long* charb, const unsigned short* chosen_mask, int bits32)
{
    if (!bits32)
    {
        for (unsigned short i = 0; i < 16; i++)
        {
            unsigned short c = ((unsigned short*)charb)[2*i + 1];
            c &= chosen_mask[i & 3];
            ((unsigned short*)charb)[2*i + 1] = c;
        }
    }
    else
    {
        for (unsigned short i = 0; i < 16; i++)
        {
            unsigned long m = chosen_mask[i & 3];
            charb[i] &= m | (m << 16);
        }
    }
}

static void draw_char(const unsigned long* charb, short x, short y, int bits32)
{
    unsigned short* planeptr = (unsigned short*)(y * 80 + ((x >> 3) & 0xFFFE));
    unsigned short xinblock = x & 0x000F;
    egc_set_to_mono_draw_mode();
    egc_set_bit_addr_dir(EGC_BLOCKTRANSFER_FORWARD | EGC_BITADDRESS_DEST(xinblock));
    hal_set_es(GDC_PLANES_SEGMENT);
    if (!bits32)
    {
        egc_set_bit_length(16);
        if (xinblock)
        {
            __asm volatile (
                "lea 0x500(%%di), %%bx\n"
                ".loop%=: movsw\n\t" "stosw\n\t"
                "addw $76, %w1\n\t"
                "movsw\n\t" "stosw\n\t"
                "addw $76, %w1\n\t"
                "movsw\n\t" "stosw\n\t"
                "addw $76, %w1\n\t"
                "movsw\n\t" "stosw\n\t"
                "addw $76, %w1\n\t"
                "cmpw %%bx, %w1\n\t"
                "jne .loop%=\n\t"
            : "+S" (charb), "+D" (planeptr) : : "%bx", "memory");
        }
        else
        {
            __asm volatile (
                "lea 0x500(%%di), %%bx\n"
                ".loop%=: movsw\n\t"
                "addw $78, %w1\n\t"
                "movsw\n\t"
                "addw $78, %w1\n\t"
                "movsw\n\t"
                "addw $78, %w1\n\t"
                "movsw\n\t"
                "addw $78, %w1\n\t"
                "cmpw %%bx, %w1\n\t"
                "jne .loop%=\n\t"
            : "+S" (charb), "+D" (planeptr) : : "%bx", "memory");
        }
    }
    else
    {
        egc_set_bit_length(32);
        if (xinblock)
        {
            __asm volatile (
                "lea 0x500(%%di), %%bx\n"
                ".loop%=: movsw\n\t" "movsw\n\t" "stosw\n\t"
                "addw $74, %w1\n\t"
                "movsw\n\t" "movsw\n\t" "stosw\n\t"
                "addw $74, %w1\n\t"
                "movsw\n\t" "movsw\n\t" "stosw\n\t"
                "addw $74, %w1\n\t"
                "movsw\n\t" "movsw\n\t" "stosw\n\t"
                "addw $74, %w1\n\t"
                "cmpw %%bx, %w1\n\t"
                "jne .loop%=\n\t"
            : "+S" (charb), "+D" (planeptr) : : "%bx", "memory");
        }
        else
        {
            __asm volatile (
                "lea 0x500(%%di), %%bx\n"
                ".loop%=: movsw\n\t" "movsw\n\t"
                "addw $76, %w1\n\t"
                "movsw\n\t" "movsw\n\t"
                "addw $76, %w1\n\t"
                "movsw\n\t" "movsw\n\t"
                "addw $76, %w1\n\t"
                "movsw\n\t" "movsw\n\t"
                "addw $76, %w1\n\t"
                "cmpw %%bx, %w1\n\t"
                "jne .loop%=\n\t"
            : "+S" (charb), "+D" (planeptr) : : "%bx", "memory");
        }
    }
}

static void draw_char_mask(const unsigned long* charb, short x, short y, const unsigned short* chosen_mask, int bits32)
{
    unsigned short* planeptr = (unsigned short*)(y * 80 + ((x >> 3) & 0xFFFE));
    unsigned short xinblock = x & 0x000F;
    egc_set_to_mono_draw_mode();
    egc_set_bit_addr_dir(EGC_BLOCKTRANSFER_FORWARD | EGC_BITADDRESS_DEST(xinblock));
    hal_set_es(GDC_PLANES_SEGMENT);
    if (!bits32)
    {
        egc_set_bit_length(16);
        if (xinblock)
        {
            __asm volatile (
                "xor %%cx, %%cx\n\t" "push %%bp\n\t"
                "movw %w2, %%bp\n\t"
                ".loop%=: movw %%bp, %w2\n\t" "addw %%cx, %w2\n\t"
                "movw (%w2), %%dx\n\t" "lodsw\n\t" "andw %%dx, %%ax\n\t"
                "stosw\n\t" "stosw\n\t"
                "addw $6, %0\n\t" "addw $316, %1\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t"
                "stosw\n\t" "stosw\n\t"
                "addw $6, %0\n\t" "addw $316, %1\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t"
                "stosw\n\t" "stosw\n\t"
                "addw $6, %0\n\t" "addw $316, %1\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t"
                "stosw\n\t" "stosw\n\t"
                "subw $24, %0\n\t" "subw $884, %1\n\t"
                "addw $2, %%cx\n\t" "cmpw $8, %%cx\n\t" "jne .loop%=\n\t"
                "pop %%bp"
            : "+S" (charb), "+D" (planeptr) : "b" (chosen_mask) : "%ax", "%dx", "%cx", "memory");
        }
        else
        {
            __asm volatile (
                "xor %%cx, %%cx\n\t" "push %%bp\n\t"
                "movw %w2, %%bp\n\t"
                ".loop%=: movw %%bp, %w2\n\t" "addw %%cx, %w2\n\t"
                "movw (%w2), %%dx\n\t" "lodsw\n\t" "andw %%dx, %%ax\n\t"
                "stosw\n\t"
                "addw $6, %0\n\t" "addw $318, %1\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t"
                "stosw\n\t"
                "addw $6, %0\n\t" "addw $318, %1\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t"
                "stosw\n\t"
                "addw $6, %0\n\t" "addw $318, %1\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t"
                "stosw\n\t"
                "subw $24, %0\n\t" "subw $882, %1\n\t"
                "addw $2, %%cx\n\t" "cmpw $8, %%cx\n\t" "jne .loop%=\n\t"
                "pop %%bp"
            : "+S" (charb), "+D" (planeptr) : "b" (chosen_mask) : "%ax", "%dx", "%cx", "memory");
        }
    }
    else
    {
        egc_set_bit_length(32);
        if (xinblock)
        {
            __asm volatile (
                "xor %%cx, %%cx\n\t" "push %%bp\n\t"
                "movw %w2, %%bp\n\t"
                ".loop%=: movw %%bp, %w2\n\t" "addw %%cx, %w2\n\t"
                "movw (%w2), %%dx\n\t" "lodsw\n\t" "andw %%dx, %%ax\n\t" "stosw\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t" "stosw\n\t" "stosw\n\t"
                "addw $12, %0\n\t" "addw $314, %1\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t" "stosw\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t" "stosw\n\t" "stosw\n\t"
                "addw $12, %0\n\t" "addw $314, %1\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t" "stosw\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t" "stosw\n\t" "stosw\n\t"
                "addw $12, %0\n\t" "addw $314, %1\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t" "stosw\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t" "stosw\n\t" "stosw\n\t"
                "subw $48, %0\n\t" "subw $886, %1\n\t"
                "addw $2, %%cx\n\t" "cmpw $8, %%cx\n\t" "jne .loop%=\n\t"
                "pop %%bp"
            : "+S" (charb), "+D" (planeptr) : "b" (chosen_mask) : "%ax", "%dx", "%cx", "memory");
        }
        else
        {
            __asm volatile (
                "xor %%cx, %%cx\n\t" "push %%bp\n\t"
                "movw %w2, %%bp\n\t"
                ".loop%=: movw %%bp, %w2\n\t" "addw %%cx, %w2\n\t"
                "movw (%w2), %%dx\n\t" "lodsw\n\t" "andw %%dx, %%ax\n\t" "stosw\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t" "stosw\n\t"
                "addw $12, %0\n\t" "addw $316, %1\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t" "stosw\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t" "stosw\n\t"
                "addw $12, %0\n\t" "addw $316, %1\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t" "stosw\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t" "stosw\n\t"
                "addw $12, %0\n\t" "addw $316, %1\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t" "stosw\n\t"
                "lodsw\n\t" "andw %%dx, %%ax\n\t" "stosw\n\t"
                "subw $48, %0\n\t" "subw $884, %1\n\t"
                "addw $2, %%cx\n\t" "cmpw $8, %%cx\n\t" "jne .loop%=\n\t"
                "pop %%bp"
            : "+S" (charb), "+D" (planeptr) : "b" (chosen_mask) : "%ax", "%dx", "%cx", "memory");
        }
    }
}

static const char* preprocess_string(const char __far* str, unsigned char autolb, short lx, short rx, short ty, short by)
{
    char ch = *str++;
    char* pch = string_buffer1;
    while (ch)
    {
        if (ch == 0x1B)
        {
            ch = *str++;
            if ((ch & 0xF0) == 0x50)
            {
                char* ich = custom_infos[ch & 0x0F];
                ch = *ich++;
                while (ch) { *pch++ = ch; ch = *ich++; }
            }
            else
            {
                *pch++ = 0x1B; *pch++ = ch;
            }
        }
        else *pch++ = ch;
        ch = *str++;
    }
    *pch = 0;
    if (!autolb) return string_buffer1;
    pch = string_buffer2;
    char* sspch = string_buffer1;
    char* bpp = 0;
    unsigned int uch = utf8_decode((const unsigned char**)&sspch);
    short curX = lx;
    short curY = ty;
    while (uch)
    {
        if (uch < 0x21)
        {
            switch (uch)
            {
                case 0x09:
                    bpp = pch;
                    { short dx = curX - lx + 32; dx &= 0xFFE0; curX = lx + dx; }
                    break;
                case 0x0A: curY += 16; break;
                case 0x0D: curX = lx; bpp = 0; break;
                case 0x1B:
                    sspch++;
                    uch = 0x0420;
                    break;
                case 0x20: bpp = pch; curX += 8; break;
            }
        }
        else
        {
            int cw = unicode_get_char_width(uch);
            if (cw > 0) curX += cw;
        }
        if (curY >= by) break;
        else if (curX >= rx)
        {
            if (!bpp) bpp = pch;
            else sspch -= pch - bpp;
            *bpp++ = 0x0D; *bpp++ = 0x0A;
            pch = bpp; bpp = 0;
            curX = lx; curY += 16;
        }
        else
        {
            char* ucsp = sspch;
            if (uch < 0x0080) ucsp -= 1;
            else if (uch < 0x0800) ucsp -= 2;
            else ucsp -= 3;
            while (ucsp < sspch) *pch++ = *ucsp++;
        }
        uch = utf8_decode((const unsigned char**)&sspch);
    }
    *pch = 0;
    return string_buffer2;
}

static void preload_glyphs(const char* str)
{
    const unsigned char* pstr = (const unsigned char*)str;
    while (1)
    {
        unsigned int ch = utf8_decode(&pstr);
        if (ch) load_glyph_cache_with_char(ch);
        else break;
    }
}

static void write_string_internal(const char* str, short x, short y, short format)
{
    unsigned int ch;
    const unsigned char* pstr = (const unsigned char*)str;
    short curX = x;
    short curY = y;
    const short defFormat = format;
    while (1)
    {
        ch = utf8_decode(&pstr);
        if (ch)
        {
            if (ch <= 0x20)
            {
                switch (ch)
                {
                    case 0x09:
                    {
                        short dx = curX - x + 32; dx &= 0xFFE0; curX = x + dx;
                        break;
                    }
                    case 0x0A: curY += 16; break;
                    case 0x0D: curX = x; break;
                    case 0x1B:
                        ch = *pstr++;
                        switch ((ch & 0xF0) >> 4)
                        {
                            case 0x00: if (ch & 0x0F) break; else return;
                            case 0x01: format = (format & (~FORMAT_PART_MAIN)) | (ch & 0x0F); break;
                            case 0x02: format = (format & (~FORMAT_PART_UNUSED)) | ((ch & 0x0F) << 4); break;
                            case 0x03: format = (format & (~FORMAT_PART_FADE)) | ((ch & 0x0F) << 8); break;
                            case 0x04: format = (format & (~FORMAT_PART_COLOUR)) | ((ch & 0x0F) << 12); break;
                            case 0x05: case 0x06: case 0x07: case 0x08:
                            case 0x09: case 0x0A: case 0x0B: case 0x0C:
                            case 0x0D: case 0x0E: break;
                            case 0x0F:
                                format = (format & (~FORMAT_PART_MAIN))  | ((ch & 0x1 ? defFormat : format) & FORMAT_PART_MAIN);
                                format = (format & (~FORMAT_PART_UNUSED)) | ((ch & 0x2 ? defFormat : format) & FORMAT_PART_UNUSED);
                                format = (format & (~FORMAT_PART_FADE))   | ((ch & 0x4 ? defFormat : format) & FORMAT_PART_FADE);
                                format = (format & (~FORMAT_PART_COLOUR)) | ((ch & 0x8 ? defFormat : format) & FORMAT_PART_COLOUR);
                                break;
                        }
                        break;
                    case 0x20:
                        hal_memset16_near(0, charbuf, 32);
                        if (format & FORMAT_UNDERLINE)
                        {
                            underline_char(charbuf, 8);
                            if (format & FORMAT_PART_FADE) mask_char(charbuf, &bayer4x4masks[60 - (FORMAT_FADE_GET(format) << 2)], 0);
                            swap_char_data_formats(charbuf, 0);
                            if (format & FORMAT_SHADOW)
                            {
                                egc_set_fg_colour(shadow_colours[FORMAT_COLOUR_GET(format)]);
                                draw_char(charbuf, curX + 1, curY + 1, 0);
                            }
                            egc_set_fg_colour(FORMAT_COLOUR_GET(format));
                            draw_char(charbuf, curX, curY, 0);
                        }
                        curX += 8;
                        break;
                }
            }
            else
            {
                int charWidth = unicode_get_char_data(ch, charbuf);
                if (charWidth < 0) continue;
                char drawWidth = charWidth;
                if (format & FORMAT_ITALIC) { italicise_char(charbuf, (drawWidth + 7) > 16); drawWidth += 7; }
                if (format & FORMAT_BOLD) { bolden_char_right(charbuf, (drawWidth + 1) > 16); drawWidth += 1; }
                if (format & FORMAT_UNDERLINE) underline_char(charbuf, charWidth);
                char is32 = drawWidth > 16;
                if (format & FORMAT_PART_FADE) mask_char(charbuf, &bayer4x4masks[60 - (FORMAT_FADE_GET(format) << 2)], is32);
                swap_char_data_formats(charbuf, is32);
                if (format & FORMAT_SHADOW)
                {
                    egc_set_fg_colour(shadow_colours[FORMAT_COLOUR_GET(format)]);
                    draw_char(charbuf, curX + 1, curY + 1, is32);
                }
                egc_set_fg_colour(FORMAT_COLOUR_GET(format));
                draw_char(charbuf, curX, curY, is32);
                curX += charWidth;
            }
        }
        else break;
    }
}

void write_string(const char __far* str, short x, short y, short format, unsigned char autolb)
{
    const char* pstr = preprocess_string(str, autolb, x, x + text_box_inner_bounds.size.x, y, y + text_box_inner_bounds.size.y);
    preload_glyphs(pstr);
    write_string_internal(pstr, x, y, format);
}

void start_animated_string_write(const char __far* str, short x, short y, short format)
{
    const char* pstr = preprocess_string(str, 1, x, x + text_box_inner_bounds.size.x, y, y + text_box_inner_bounds.size.y);
    preload_glyphs(pstr);
    string_to_anim_write = pstr;
    cur_anim_string_pos = pstr;
    current_anim_write_x = x;
    current_anim_write_y = y;
    current_anim_next_write_x = x;
    current_anim_next_write_y = y;
    current_anim_default_format = format;
    current_anim_format = format;
    ch_buf_start_num = 0;
    anim_reached_end_of_string = 0;
    anim_length = 16;
    wait_frames = 0;
    wait_per_char = 0;
    hal_memset16_near(0, anim_char_buf, 512);
    hal_memset16_near(0xFFFF, char_fade, 8);
}

int string_write_animation_frame(unsigned char skip)
{
    if (skip)
    {
        anim_reached_end_of_string = 1;
        anim_length = 0;
        write_string_internal(string_to_anim_write, current_anim_write_x, current_anim_write_y, current_anim_default_format);
        return 1;
    }
    unsigned int ch;
    const unsigned char* str = (const unsigned char*)cur_anim_string_pos;
    short defFormat = current_anim_default_format;
    short format = current_anim_format;
    short x = current_anim_write_x;
    short y = current_anim_write_y;
    short curX = current_anim_next_write_x;
    short curY = current_anim_next_write_y;
    char nullTerm = anim_reached_end_of_string;
    unsigned long* nextCharBuf = anim_char_buf + 16 * ch_buf_start_num;
    if (wait_frames <= 0)
    {
        while (!nullTerm)
        {
            ch = utf8_decode(&str);
            if (ch)
            {
                if (ch <= 0x20)
                {
                    switch (ch)
                    {
                        case 0x09:
                        {
                            short dx = curX - x + 32; dx &= 0xFFE0; curX = x + dx;
                            wait_frames = wait_per_char;
                            break;
                        }
                        case 0x0A: curY += 16; break;
                        case 0x0D: curX = x; wait_frames = wait_per_char; break;
                        case 0x1B:
                            ch = *str++;
                            switch ((ch & 0xF0) >> 4)
                            {
                                case 0x00: if (ch & 0x0F) break; else { nullTerm = 1; break; }
                                case 0x01: format = (format & (~FORMAT_PART_MAIN)) | (ch & 0x0F); break;
                                case 0x02: format = (format & (~FORMAT_PART_UNUSED)) | ((ch & 0x0F) << 4); break;
                                case 0x03: format = (format & (~FORMAT_PART_FADE)) | ((ch & 0x0F) << 8); break;
                                case 0x04: format = (format & (~FORMAT_PART_COLOUR)) | ((ch & 0x0F) << 12); break;
                                case 0x05: break;
                                case 0x06: wait_frames += 10 * ((ch & 0x0F) + 1); goto LdrawT;
                                case 0x07: wait_per_char = ch & 0x0F; break;
                                case 0x08: case 0x09: case 0x0A: case 0x0B:
                                case 0x0C: case 0x0D: case 0x0E: break;
                                case 0x0F:
                                    format = (format & (~FORMAT_PART_MAIN))  | ((ch & 0x1 ? defFormat : format) & FORMAT_PART_MAIN);
                                    format = (format & (~FORMAT_PART_UNUSED)) | ((ch & 0x2 ? defFormat : format) & FORMAT_PART_UNUSED);
                                    format = (format & (~FORMAT_PART_FADE))   | ((ch & 0x4 ? defFormat : format) & FORMAT_PART_FADE);
                                    format = (format & (~FORMAT_PART_COLOUR)) | ((ch & 0x8 ? defFormat : format) & FORMAT_PART_COLOUR);
                                    break;
                            }
                            break;
                        case 0x20:
                            hal_memset16_near(0, nextCharBuf, 32);
                            if (format & FORMAT_UNDERLINE)
                            {
                                if (format & FORMAT_SHADOW) char_flags[ch_buf_start_num] = 1;
                                underline_char(nextCharBuf, 8);
                                if (format & FORMAT_PART_FADE) mask_char(nextCharBuf, &bayer4x4masks[60 - (FORMAT_FADE_GET(format) << 2)], 0);
                                swap_char_data_formats(nextCharBuf, 0);
                            }
                            char_colours[ch_buf_start_num] = FORMAT_COLOUR_GET(format);
                            char_xs[ch_buf_start_num] = curX;
                            char_ys[ch_buf_start_num] = curY;
                            char_fade[ch_buf_start_num] = 0;
                            curX += 8;
                            wait_frames = wait_per_char;
                            goto LdrawT;
                    }
                }
                else
                {
                    int charWidth = unicode_get_char_data(ch, nextCharBuf);
                    if (charWidth < 0) continue;
                    if (format & FORMAT_SHADOW) char_flags[ch_buf_start_num] = 1;
                    char drawWidth = charWidth;
                    if (format & FORMAT_ITALIC) { italicise_char(nextCharBuf, (drawWidth + 7) > 16); drawWidth += 7; }
                    if (format & FORMAT_BOLD) { bolden_char_right(nextCharBuf, (drawWidth + 1) > 16); drawWidth += 1; }
                    if (format & FORMAT_UNDERLINE) underline_char(nextCharBuf, charWidth);
                    char is32 = (drawWidth > 16) << 1;
                    if (format & FORMAT_PART_FADE) mask_char(nextCharBuf, &bayer4x4masks[60 - (FORMAT_FADE_GET(format) << 2)], is32);
                    swap_char_data_formats(nextCharBuf, is32);
                    char_flags[ch_buf_start_num] |= is32;
                    char_colours[ch_buf_start_num] = FORMAT_COLOUR_GET(format);
                    char_xs[ch_buf_start_num] = curX;
                    char_ys[ch_buf_start_num] = curY;
                    char_fade[ch_buf_start_num] = 0;
                    curX += charWidth;
                    wait_frames = wait_per_char;
                    break;
                }
            }
            else { nullTerm = 1; break; }
        }
    }
    else wait_frames--;
    LdrawT:
    cur_anim_string_pos = str;
    current_anim_format = format;
    current_anim_next_write_x = curX;
    current_anim_next_write_y = curY;
    anim_reached_end_of_string = nullTerm;
    if (nullTerm)
    {
        ch_buf_start_num--;
        ch_buf_start_num &= 0xF;
        anim_length--;
    }
    for (unsigned short i = 0; i < anim_length; i++)
    {
        unsigned short chBufNum = (ch_buf_start_num - i) & 0xF;
        unsigned short fadeStart = char_fade[chBufNum] * 4;
        if (fadeStart < 64)
        {
            char_fade[chBufNum]++;
            unsigned short curcol = char_colours[chBufNum];
            if (char_flags[chBufNum] & 0x01)
            {
                egc_set_fg_colour(shadow_colours[curcol]);
                draw_char_mask(&anim_char_buf[16 * chBufNum], char_xs[chBufNum] + 1, char_ys[chBufNum] + 1, bayer4x4masks + fadeStart, char_flags[chBufNum] & 0x02);
            }
            egc_set_fg_colour(curcol);
            draw_char_mask(&anim_char_buf[16 * chBufNum], char_xs[chBufNum], char_ys[chBufNum], bayer4x4masks + fadeStart, char_flags[chBufNum] & 0x02);
        }
    }
    ch_buf_start_num++;
    ch_buf_start_num &= 0xF;
    if (anim_length <= 0) return 1;
    return 0;
}
