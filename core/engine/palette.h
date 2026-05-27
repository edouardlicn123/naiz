#ifndef PALETTE_H
#define PALETTE_H

typedef struct
{
    unsigned char r;
    unsigned char g;
    unsigned char b;
} ColourRGB;

extern ColourRGB main_palette[16];
extern ColourRGB mix_palette[16];
extern ColourRGB out_palette[16];

void set_main_palette(const ColourRGB* pal);
void set_mix_single_colour(unsigned char r, unsigned char g, unsigned char b);
void set_mix_single_colour_5bpc(unsigned char r, unsigned char g, unsigned char b);
void set_mix_main_add(short r, short g, short b);
void set_mix_main_add_5bpc(unsigned char r, unsigned char g, unsigned char b);
void set_mix_luminosity_mod(short mod);
void set_mix_luminosity_mod_8bpc(unsigned char mod);
void set_mix_saturation_mod(short mod);
void set_mix_saturation_mod_8bpc(unsigned char mod);
void set_mix_hue_mod(unsigned short mod);
void set_mix_hue_mod_8bpc(unsigned char mod);
void set_mix_colourised(unsigned char r, unsigned char g, unsigned char b);
void set_mix_colourised_5bpc(unsigned char r, unsigned char g, unsigned char b);
void set_mix_invert(void);
void copy_main_to_out(void);
void mix_palettes(short mix_amt);
void set_display_palette_out(void);
void set_display_palette_out_brightness(short add);
void set_display_palette_out_hue_rotate(unsigned short mod);
void set_default_palette(void);

#endif
