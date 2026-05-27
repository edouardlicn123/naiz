#include <stdint.h>
#include "hal.h"
#include "rootinfo.h"
#include "fontfile.h"

#define RANGELIST_SIZE      128
#define GLYPHCACHE_ADDRBITS 9
#define GLYPHCACHE_ADDRMASK 0x01FF
#define GLYPHCACHE_SIZE     256

typedef struct { unsigned short first; unsigned short last; } RangeEntryFile;

typedef struct
{
    unsigned short first_code;
    unsigned short first_entry;
    unsigned short length;
} RangeEntry;

static RangeEntry range_list[RANGELIST_SIZE];
static unsigned int real_range_size;
static unsigned long font_info_list_file_ptr;
static unsigned long font_glyph_data_file_ptr;
static unsigned char glyph_cache[32 * GLYPHCACHE_SIZE];
static unsigned char glyph_info_cache[GLYPHCACHE_SIZE];
static unsigned int next_glyph_index;

typedef struct
{
    unsigned short codepoint;
    unsigned short cache_index;
} IndexBufferEntry;

static IndexBufferEntry glyph_index_buf[GLYPHCACHE_SIZE];
static unsigned int next_buf_idx;

typedef struct
{
    unsigned short codepoint;
    unsigned short index_buf_pos;
} PresenceMapEntry;

static PresenceMapEntry glyph_presence_map[GLYPHCACHE_ADDRMASK + 1];

static unsigned int hash_to_presence_map(unsigned short x)
{
    return x & GLYPHCACHE_ADDRMASK;
}

void init_font_file(void)
{
    real_range_size = 0;
    next_glyph_index = 0;
    next_buf_idx = 0;
    for (int i = 0; i < GLYPHCACHE_SIZE; i++)
        glyph_index_buf[i].codepoint = 0xFFFF;
    for (int i = 0; i < GLYPHCACHE_ADDRMASK + 1; i++)
        glyph_presence_map[i].codepoint = 0xFFFF;

    int fh = hal_file_open(root_info.font_path, 0);
    if (fh < 0) return;
    hal_file_read(fh, range_list, sizeof(range_list));
    hal_file_close(fh);

    unsigned int total_chars = 0;
    RangeEntryFile* frl = (RangeEntryFile*)range_list;
    for (int i = 0; i < RANGELIST_SIZE; i++)
    {
        if (frl[i].last == 0 && frl[i].first == 0) break;
        total_chars += frl[i].last - frl[i].first + 1;
        real_range_size++;
    }
    font_info_list_file_ptr = real_range_size * 4;
    font_glyph_data_file_ptr = font_info_list_file_ptr + total_chars * 4;
    unsigned short list_ptr = 0;
    for (int i = real_range_size - 1; i >= 0; i--)
    {
        RangeEntryFile ref = frl[i];
        RangeEntry r;
        r.first_code = ref.first;
        r.length = ref.last - ref.first + 1;
        r.first_entry = list_ptr;
        range_list[i] = r;
        list_ptr += r.length;
    }

    unsigned char glyph_buf[32];
    for (int i = 0x21; i < 0x7F; i++)
    {
        unsigned char gi = load_glyph_from_file(i, glyph_buf);
        if (gi != GLYPHCACHE_INVALID)
        {
            unsigned char* acp = ascii_char_cache + 16 * (i - 0x21);
            for (int j = 0; j < 16; j++)
                acp[j] = glyph_buf[2 * j];
        }
    }
}

unsigned int utf8_decode(const unsigned char** pstr)
{
    const unsigned char* s = *pstr;
    unsigned char in = *s++;
    unsigned int out = 0;
    while (1)
    {
        if (in < 0x80) { out = in; break; }
        else if (in < 0xC0) { in = *s++; }
        else if (in < 0xE0)
        {
            out = ((unsigned int)(in & 0x1F)) << 6;
            in = *s++;
            if (in >= 0x80 && in < 0xC0) { out |= (in & 0x3F); break; }
        }
        else if (in < 0xF0)
        {
            out = ((unsigned int)(in & 0x0F)) << 12;
            in = *s++;
            if (in >= 0x80 && in < 0xC0)
            {
                out |= ((unsigned int)(in & 0x3F)) << 6;
                in = *s++;
                if (in >= 0x80 && in < 0xC0) { out |= (in & 0x3F); break; }
            }
        }
        else { in = *s++; }
    }
    *pstr = s;
    return out;
}

unsigned char load_glyph_from_file(unsigned int code, unsigned char* buffer)
{
    unsigned int check_range = real_range_size >> 1;
    unsigned int check_lo = 0;
    unsigned int check_hi = real_range_size - 1;
    while (1)
    {
        if (check_hi < check_lo) return GLYPHCACHE_INVALID;
        RangeEntry r = range_list[check_range];
        if (code < r.first_code) check_hi = check_range - 1;
        else
        {
            unsigned short last = r.first_code + r.length - 1;
            if (code > last) check_lo = check_range + 1;
            else break;
        }
        check_range = ((check_hi - check_lo) >> 2) + check_lo;
    }

    RangeEntry r = range_list[check_range];
    unsigned short code_in_range = code - r.first_code;
    unsigned short info_ind = r.first_entry + code_in_range;
    unsigned char glyph_buf[32];
    unsigned long newpos;
    int fh = hal_file_open(root_info.font_path, 0);
    if (fh < 0) return GLYPHCACHE_INVALID;
    hal_file_seek(fh, 0, font_info_list_file_ptr + info_ind * 4, &newpos);
    unsigned long char_entry;
    hal_file_read(fh, &char_entry, 4);
    unsigned long char_addr = char_entry & 0x001FFFFF;
    unsigned int char_w = ((char_entry & 0x00800000) >> 23) + 1;
    unsigned int char_h = ((char_entry & 0xF0000000) >> 28) + 1;
    unsigned int char_yoff = (char_entry & 0x0F000000) >> 24;
    hal_file_seek(fh, 0, font_glyph_data_file_ptr + char_addr, &newpos);
    hal_file_read(fh, glyph_buf, 32);
    hal_file_close(fh);

    for (int i = 0; i < 16; i++) ((unsigned short*)buffer)[i] = 0;
    if (char_w == 1)
    {
        for (int i = 0; i < char_h; i++)
            buffer[2 * (i + char_yoff)] = glyph_buf[i];
    }
    else if (char_w == 2)
    {
        for (int i = 0; i < char_h; i++)
        {
            buffer[2 * (i + char_yoff)] = glyph_buf[2 * i];
            buffer[2 * (i + char_yoff) + 1] = glyph_buf[2 * i + 1];
        }
    }
    return ((char_w * 8) - 1) & GLYPHCACHE_WIDTHMASK;
}

int load_glyph_cache_with_char(unsigned int code)
{
    if (code < 0x80) return -1;

    unsigned int map_idx = hash_to_presence_map(code);
    PresenceMapEntry* mp = glyph_presence_map + map_idx;
    while (mp->codepoint != 0xFFFF)
    {
        if (mp->codepoint == code) break;
        map_idx++; map_idx &= GLYPHCACHE_ADDRMASK;
        mp = glyph_presence_map + map_idx;
    }
    IndexBufferEntry* nip = glyph_index_buf + next_buf_idx;
    if (mp->codepoint == 0xFFFF)
    {
        unsigned char gi = load_glyph_from_file(code, glyph_cache + (next_glyph_index * 32));
        if (gi == GLYPHCACHE_INVALID) return -1;
        mp->codepoint = code;
        glyph_info_cache[next_glyph_index] = gi;
        if (nip->codepoint != 0xFFFF)
        {
            unsigned int ec = nip->codepoint;
            unsigned int ei = hash_to_presence_map(ec);
            PresenceMapEntry* ep = glyph_presence_map + ei;
            while (ep->codepoint != ec) { ei++; ei &= GLYPHCACHE_ADDRMASK; ep = glyph_presence_map + ei; }
            ep->codepoint = 0xFFFF;
            PresenceMapEntry* fp = ep;
            ei++; ei &= GLYPHCACHE_ADDRMASK;
            ep = glyph_presence_map + ei;
            while (ep->codepoint != 0xFFFF)
            {
                unsigned int fi = hash_to_presence_map(ep->codepoint);
                if (fi != ei) { *fp = *ep; ep->codepoint = 0xFFFF; fp = ep; }
                ei++; ei &= GLYPHCACHE_ADDRMASK;
                ep = glyph_presence_map + ei;
            }
        }
        nip->codepoint = code;
        nip->cache_index = next_glyph_index;
        next_glyph_index++; next_glyph_index %= GLYPHCACHE_SIZE;
    }
    else
    {
        unsigned int bi = mp->index_buf_pos;
        IndexBufferEntry* ip = glyph_index_buf + bi;
        *nip = *ip;
        ip->codepoint = 0xFFFF;
    }
    mp->index_buf_pos = next_buf_idx;
    next_buf_idx++; next_buf_idx %= GLYPHCACHE_SIZE;
    return nip->cache_index;
}

int unicode_get_char_width(unsigned int code)
{
    if (code < 0x80)
    {
        if (code >= 0x21 && code < 0x7F) return 8;
        else return -1;
    }
    int gci = load_glyph_cache_with_char(code);
    if (gci < 0) return -1;
    unsigned char gi = glyph_info_cache[gci];
    if (gi == GLYPHCACHE_INVALID) return -1;
    return (gi & GLYPHCACHE_WIDTHMASK) + 1;
}

int unicode_get_char_data(unsigned int code, unsigned long* buffer)
{
    if (code < 0x80)
    {
        if (code >= 0x21 && code < 0x7F)
        {
            unsigned char* cc = ascii_char_cache + (code - 0x21) * 16;
            for (int i = 0; i < 16; i++)
                buffer[i] = ((unsigned long)cc[i]) << 24;
            return 8;
        }
        else return -1;
    }
    int gci = load_glyph_cache_with_char(code);
    if (gci < 0) return -1;
    unsigned char* cc = glyph_cache + gci * 32;
    unsigned char gi = glyph_info_cache[gci];
    if (gi == GLYPHCACHE_INVALID) return -1;
    for (int i = 0; i < 16; i++)
    {
        unsigned short row = cc[2*i + 1];
        row |= (unsigned short)(cc[2*i]) << 8;
        ((unsigned short*)buffer)[2*i] = 0;
        ((unsigned short*)buffer)[2*i + 1] = row;
    }
    return (gi & GLYPHCACHE_WIDTHMASK) + 1;
}

static unsigned char bit_reverse_byte(unsigned char b)
{
    b = ((b >> 4) & 0x0F) | ((b << 4) & 0xF0);
    b = ((b >> 2) & 0x33) | ((b << 2) & 0xCC);
    b = ((b >> 1) & 0x55) | ((b << 1) & 0xAA);
    return b;
}

void swap_char_data_formats(unsigned long* buffer, int bits32)
{
    if (!bits32)
    {
        for (int i = 0; i < 16; i++)
        {
            unsigned short row = ((unsigned short*)buffer)[2*i + 1];
            unsigned short sw = ((row & 0x00FF) << 8) | ((row & 0xFF00) >> 8);
            ((unsigned short*)buffer)[i] = (bit_reverse_byte(sw >> 8) << 8) | bit_reverse_byte(sw & 0xFF);
        }
    }
    else
    {
        for (int i = 0; i < 16; i++)
        {
            unsigned long row = buffer[i];
            unsigned long tr = (row & 0x000000FF) << 24;
            tr |= (row & 0x0000FF00) << 8;
            tr |= (row & 0x00FF0000) >> 8;
            tr |= (row & 0xFF000000) >> 24;
            buffer[i] = ((unsigned long)bit_reverse_byte(tr >> 24) << 24)
                      | ((unsigned long)bit_reverse_byte((tr >> 16) & 0xFF) << 16)
                      | ((unsigned long)bit_reverse_byte((tr >> 8) & 0xFF) << 8)
                      | (unsigned long)bit_reverse_byte(tr & 0xFF);
        }
    }
}
