#ifndef FONTFILE_H
#define FONTFILE_H

#define GLYPHCACHE_WIDTHMASK 0x0F
#define GLYPHCACHE_INVALID   0xFF

extern unsigned char ascii_char_cache[94 * 16];

void init_font_file(void);

unsigned int utf8_decode(const unsigned char** pstr);

unsigned char load_glyph_from_file(unsigned int code, unsigned char* buffer);

int load_glyph_cache_with_char(unsigned int code);

int unicode_get_char_width(unsigned int code);

int unicode_get_char_data(unsigned int code, unsigned long* buffer);

void swap_char_data_formats(unsigned long* buffer, int bits32);

#endif
