#include <stdint.h>
#include "pc98_gdc.h"
#include "stdbuffer.h"
#include "palette.h"

const short c8bpc_to_2p14_table[256] = {
    0,     64,    129,   193,   257,   321,   386,   450,   514,   578,   643,   707,   771,   835,   900,   964,
    1028,  1092,  1157,  1221,  1285,  1349,  1414,  1478,  1542,  1606,  1671,  1735,  1799,  1863,  1928,  1992,
    2056,  2120,  2185,  2249,  2313,  2377,  2442,  2506,  2570,  2634,  2699,  2763,  2827,  2891,  2956,  3020,
    3084,  3148,  3213,  3277,  3341,  3405,  3470,  3534,  3598,  3662,  3727,  3791,  3855,  3919,  3984,  4048,
    4112,  4176,  4241,  4305,  4369,  4433,  4498,  4562,  4626,  4690,  4755,  4819,  4883,  4947,  5012,  5076,
    5140,  5204,  5269,  5333,  5397,  5461,  5526,  5590,  5654,  5718,  5783,  5847,  5911,  5975,  6040,  6104,
    6168,  6232,  6297,  6361,  6425,  6489,  6554,  6618,  6682,  6746,  6811,  6875,  6939,  7003,  7068,  7132,
    7196,  7260,  7325,  7389,  7453,  7517,  7582,  7646,  7710,  7774,  7839,  7903,  7967,  8031,  8096,  8160,
    8224,  8288,  8353,  8417,  8481,  8545,  8610,  8674,  8738,  8802,  8867,  8931,  8995,  9059,  9124,  9188,
    9252,  9316,  9381,  9445,  9509,  9573,  9638,  9702,  9766,  9830,  9895,  9959,  10023, 10087, 10152, 10216,
    10280, 10344, 10409, 10473, 10537, 10601, 10666, 10730, 10794, 10858, 10923, 10987, 11051, 11115, 11180, 11244,
    11308, 11372, 11437, 11501, 11565, 11629, 11694, 11758, 11822, 11886, 11951, 12015, 12079, 12143, 12208, 12272,
    12336, 12400, 12465, 12529, 12593, 12657, 12722, 12786, 12850, 12914, 12979, 13043, 13107, 13171, 13236, 13300,
    13364, 13428, 13493, 13557, 13621, 13685, 13750, 13814, 13878, 13942, 14007, 14071, 14135, 14199, 14264, 14328,
    14392, 14456, 14521, 14585, 14649, 14713, 14778, 14842, 14906, 14970, 15035, 15099, 15163, 15227, 15292, 15356,
    15420, 15484, 15549, 15613, 15677, 15741, 15806, 15870, 15934, 15998, 16063, 16127, 16191, 16255, 16320, 16384
};

const unsigned char c5bpc_to_8bpc_table[32] = {
    0x00, 0x08, 0x10, 0x18, 0x21, 0x29, 0x31, 0x39,
    0x42, 0x4A, 0x52, 0x5A, 0x63, 0x6B, 0x73, 0x7B,
    0x84, 0x8C, 0x94, 0x9C, 0xA5, 0xAD, 0xB5, 0xBD,
    0xC6, 0xCE, 0xD6, 0xDE, 0xE7, 0xEF, 0xF7, 0xFF
};

static const ColourRGB default_palette[16] = {
    { 0x11, 0x11, 0x11 }, { 0x77, 0x77, 0x77 }, { 0xBB, 0x33, 0xBB }, { 0xFF, 0x77, 0xFF },
    { 0x77, 0x11, 0x11 }, { 0xDD, 0x44, 0x44 }, { 0xFF, 0xBB, 0x77 }, { 0xCC, 0xBB, 0x33 },
    { 0x22, 0x77, 0x33 }, { 0x55, 0xDD, 0x55 }, { 0x88, 0xFF, 0x55 }, { 0xFF, 0xFF, 0x66 },
    { 0x33, 0x33, 0xBB }, { 0x33, 0xAA, 0xFF }, { 0x99, 0xFF, 0xFF }, { 0xFF, 0xFF, 0xFF }
};

ColourRGB main_palette[16];
ColourRGB mix_palette[16];
ColourRGB out_palette[16];

typedef struct { short y; short u; short v; } ColourYUV;

static ColourYUV rgb_to_yuv(ColourRGB col)
{
    ColourYUV o;
    long sr = (long)c8bpc_to_2p14_table[col.r];
    long sg = (long)c8bpc_to_2p14_table[col.g];
    long sb = (long)c8bpc_to_2p14_table[col.b];
    long ly =  3483  * sr + 11718 * sg + 1183 * sb;
    long lu = -1637  * sr - 5507  * sg + 7144 * sb;
    long lv =  10076 * sr - 9152  * sg - 924  * sb;
    o.y = (short)(ly >> 14);
    o.u = (short)(lu >> 14);
    o.v = (short)(lv >> 14);
    return o;
}

static ColourYUV rgb_to_uv(ColourRGB col)
{
    ColourYUV o;
    long sr = (long)c8bpc_to_2p14_table[col.r];
    long sg = (long)c8bpc_to_2p14_table[col.g];
    long sb = (long)c8bpc_to_2p14_table[col.b];
    long lu = -1637 * sr - 5507 * sg + 7144 * sb;
    long lv = 10076 * sr - 9152 * sg - 924 * sb;
    o.u = (short)(lu >> 14);
    o.v = (short)(lv >> 14);
    return o;
}

static ColourRGB yuv_to_rgb(ColourYUV col)
{
    ColourRGB o;
    long ly = (long)col.y << 14;
    long lu = (long)col.u;
    long lv = (long)col.v;
    long lr = ly           + 20977 * lv;
    long lg = ly - 3520 * lu - 6236 * lv;
    long lb = ly + 34865 * lu;
    lr += 526344; lg += 526344; lb += 526344;
    lr /= 1052688; lg /= 1052688; lb /= 1052688;
    short sr = (short)lr, sg = (short)lg, sb = (short)lb;
    if (sr > 0xFF) sr = 0xFF; else if (sr < 0) sr = 0;
    if (sg > 0xFF) sg = 0xFF; else if (sg < 0) sg = 0;
    if (sb > 0xFF) sb = 0xFF; else if (sb < 0) sb = 0;
    o.r = (unsigned char)sr; o.g = (unsigned char)sg; o.b = (unsigned char)sb;
    return o;
}

static void memcpy16_near(const void* src, void* dst, unsigned short words)
{
    for (unsigned short i = 0; i < words; i++)
        ((unsigned short*)dst)[i] = ((const unsigned short*)src)[i];
}

static void memset16_near(unsigned short val, void* dst, unsigned short words)
{
    for (unsigned short i = 0; i < words; i++)
        ((unsigned short*)dst)[i] = val;
}

void set_main_palette(const ColourRGB* pal)
{
    memcpy16_near(pal, main_palette, 24);
}

void set_mix_single_colour(unsigned char r, unsigned char g, unsigned char b)
{
    ColourRGB c = { r, g, b };
    for (int i = 0; i < 16; i++) mix_palette[i] = c;
}

void set_mix_single_colour_5bpc(unsigned char r, unsigned char g, unsigned char b)
{
    set_mix_single_colour(c5bpc_to_8bpc_table[r], c5bpc_to_8bpc_table[g], c5bpc_to_8bpc_table[b]);
}

void set_mix_main_add(short r, short g, short b)
{
    for (int i = 0; i < 16; i++)
    {
        ColourRGB mc = main_palette[i];
        short or = (short)mc.r + r; if (or < 0) or = 0; else if (or > 0xFF) or = 0xFF;
        short og = (short)mc.g + g; if (og < 0) og = 0; else if (og > 0xFF) og = 0xFF;
        short ob = (short)mc.b + b; if (ob < 0) ob = 0; else if (ob > 0xFF) ob = 0xFF;
        ColourRGB oc = { (unsigned char)or, (unsigned char)og, (unsigned char)ob };
        mix_palette[i] = oc;
    }
}

void set_mix_main_add_5bpc(unsigned char r, unsigned char g, unsigned char b)
{
    short sr = ((short)(r) & 0x0F) * 0x11; if (r & 0x10) sr = -0x110 + sr;
    short sg = ((short)(g) & 0x0F) * 0x11; if (g & 0x10) sg = -0x110 + sg;
    short sb = ((short)(b) & 0x0F) * 0x11; if (b & 0x10) sb = -0x110 + sb;
    set_mix_main_add(sr, sg, sb);
}

void set_mix_luminosity_mod(short mod)
{
    if (mod >= 16384) { memset16_near(0xFFFF, mix_palette, 24); return; }
    if (mod <= -16384) { memset16_near(0x0000, mix_palette, 24); return; }
    for (int i = 0; i < 16; i++)
    {
        ColourRGB mc = main_palette[i];
        if (mod < 0)
        {
            long mul = 16384 + (long)mod;
            long lr = (long)c8bpc_to_2p14_table[mc.r] * mul;
            long lg = (long)c8bpc_to_2p14_table[mc.g] * mul;
            long lb = (long)c8bpc_to_2p14_table[mc.b] * mul;
            lr += 526344; lg += 526344; lb += 526344;
            lr /= 1052688; lg /= 1052688; lb /= 1052688;
            short sr = (short)lr, sg = (short)lg, sb = (short)lb;
            if (sr > 0xFF) sr = 0xFF; else if (sr < 0) sr = 0;
            if (sg > 0xFF) sg = 0xFF; else if (sg < 0) sg = 0;
            if (sb > 0xFF) sb = 0xFF; else if (sb < 0) sb = 0;
            mc.r = (unsigned char)sr; mc.g = (unsigned char)sg; mc.b = (unsigned char)sb;
            mix_palette[i] = mc;
        }
        else if (mod > 0)
        {
            long mul = 16384 - (long)mod;
            long lr = (long)c8bpc_to_2p14_table[mc.r];
            long lg = (long)c8bpc_to_2p14_table[mc.g];
            long lb = (long)c8bpc_to_2p14_table[mc.b];
            lr = 16384 - lr; lg = 16384 - lg; lb = 16384 - lb;
            lr *= mul; lg *= mul; lb *= mul;
            lr = 268435456 - lr; lg = 268435456 - lg; lb = 268435456 - lb;
            lr += 526344; lg += 526344; lb += 526344;
            lr /= 1052688; lg /= 1052688; lb /= 1052688;
            short sr = (short)lr, sg = (short)lg, sb = (short)lb;
            if (sr > 0xFF) sr = 0xFF; else if (sr < 0) sr = 0;
            if (sg > 0xFF) sg = 0xFF; else if (sg < 0) sg = 0;
            if (sb > 0xFF) sb = 0xFF; else if (sb < 0) sb = 0;
            mc.r = (unsigned char)sr; mc.g = (unsigned char)sg; mc.b = (unsigned char)sb;
            mix_palette[i] = mc;
        }
        else { mix_palette[i] = mc; }
    }
}

void set_mix_luminosity_mod_8bpc(unsigned char mod)
{
    short smod = ((short)(mod) & 0x7F) * 130;
    if (mod & 0x80) smod = -16640 + smod;
    set_mix_luminosity_mod(smod);
}

void set_mix_saturation_mod(short mod)
{
    if (mod == 4096) { memcpy16_near(main_palette, mix_palette, 24); return; }
    for (int i = 0; i < 16; i++)
    {
        ColourRGB mc = main_palette[i];
        ColourYUV my = rgb_to_yuv(mc);
        long nu = (long)my.u * (long)mod; nu >>= 12;
        long nv = (long)my.v * (long)mod; nv >>= 12;
        my.u = (short)nu; my.v = (short)nv;
        mix_palette[i] = yuv_to_rgb(my);
    }
}

void set_mix_saturation_mod_8bpc(unsigned char mod)
{
    set_mix_saturation_mod((short)(mod) * 32);
}

void set_mix_hue_mod(unsigned short mod)
{
    if (mod == 0) { memcpy16_near(main_palette, mix_palette, 24); return; }
    for (int i = 0; i < 16; i++)
    {
        ColourRGB mc = main_palette[i];
        ColourYUV my = rgb_to_yuv(mc);
        unsigned int hue = atan2_fixed(my.v, my.u);
        hue += mod;
        long sat = (long)my.u * (long)my.u + (long)my.v * (long)my.v;
        sat = (long)sqrt_fixed(sat);
        long nu = sat * (long)cos_fixed(hue); nu >>= 14;
        long nv = sat * (long)sin_fixed(hue); nv >>= 14;
        my.u = (short)nu; my.v = (short)nv;
        mix_palette[i] = yuv_to_rgb(my);
    }
}

void set_mix_hue_mod_8bpc(unsigned char mod)
{
    unsigned short smod = ((unsigned short)(mod) & 0x7F) * 0x80;
    if (mod & 0x80) smod = 0x4000 + smod;
    set_mix_hue_mod(smod);
}

void set_mix_colourised(unsigned char r, unsigned char g, unsigned char b)
{
    ColourRGB crgb = { r, g, b };
    ColourYUV cy = rgb_to_uv(crgb);
    for (int i = 0; i < 16; i++)
    {
        ColourRGB mc = main_palette[i];
        ColourYUV my = rgb_to_yuv(mc);
        my.u = cy.u; my.v = cy.v;
        mix_palette[i] = yuv_to_rgb(my);
    }
}

void set_mix_colourised_5bpc(unsigned char r, unsigned char g, unsigned char b)
{
    set_mix_colourised(c5bpc_to_8bpc_table[r], c5bpc_to_8bpc_table[g], c5bpc_to_8bpc_table[b]);
}

void set_mix_invert(void)
{
    for (int i = 0; i < 16; i++)
    {
        ColourRGB mc = main_palette[i];
        ColourRGB oc = { (unsigned char)(0xFF - mc.r), (unsigned char)(0xFF - mc.g), (unsigned char)(0xFF - mc.b) };
        mix_palette[i] = oc;
    }
}

void copy_main_to_out(void)
{
    memcpy16_near(main_palette, out_palette, 24);
}

void mix_palettes(short mix_amt)
{
    if (mix_amt <= 0) { memcpy16_near(main_palette, out_palette, 24); return; }
    if (mix_amt >= 0xFF) { memcpy16_near(mix_palette, out_palette, 24); return; }
    short main_amt = 0xFF - mix_amt;
    for (int i = 0; i < 16; i++)
    {
        ColourRGB mc = main_palette[i];
        ColourRGB mxc = mix_palette[i];
        out_palette[i].r = (unsigned char)((main_amt * (short)mc.r + mix_amt * (short)mxc.r) / 0xFF);
        out_palette[i].g = (unsigned char)((main_amt * (short)mc.g + mix_amt * (short)mxc.g) / 0xFF);
        out_palette[i].b = (unsigned char)((main_amt * (short)mc.b + mix_amt * (short)mxc.b) / 0xFF);
    }
}

void set_display_palette_out(void)
{
    for (int i = 0; i < 16; i++)
    {
        ColourRGB c = out_palette[i];
        unsigned short r = ((unsigned short)c.r + 0x08) / 0x11;
        unsigned short g = ((unsigned short)c.g + 0x08) / 0x11;
        unsigned short b = ((unsigned short)c.b + 0x08) / 0x11;
        gdc_set_palette_colour((unsigned char)i, (unsigned char)r, (unsigned char)g, (unsigned char)b);
    }
}

void set_display_palette_out_brightness(short add)
{
    for (int i = 0; i < 16; i++)
    {
        ColourRGB c = out_palette[i];
        short r = (short)c.r + 0x08 + add; if (r < 0) r = 0; else if (r > 0x0F) r = 0x0F;
        short g = (short)c.g + 0x08 + add; if (g < 0) g = 0; else if (g > 0x0F) g = 0x0F;
        short b = (short)c.b + 0x08 + add; if (b < 0) b = 0; else if (b > 0x0F) b = 0x0F;
        gdc_set_palette_colour((unsigned char)i, (unsigned char)r, (unsigned char)g, (unsigned char)b);
    }
}

void set_display_palette_out_hue_rotate(unsigned short mod)
{
    for (int i = 0; i < 16; i++)
    {
        ColourRGB c = out_palette[i];
        ColourYUV cy = rgb_to_yuv(c);
        unsigned int hue = atan2_fixed(cy.v, cy.u);
        hue += mod;
        long sat = (long)cy.u * (long)cy.u + (long)cy.v * (long)cy.v;
        sat = (long)sqrt_fixed(sat);
        long nu = sat * (long)cos_fixed(hue); nu >>= 14;
        long nv = sat * (long)sin_fixed(hue); nv >>= 14;
        cy.u = (short)nu; cy.v = (short)nv;
        c = yuv_to_rgb(cy);
        short r = (short)c.r + 0x08; r /= 0x11; if (r < 0) r = 0; else if (r > 0x0F) r = 0x0F;
        short g = (short)c.g + 0x08; g /= 0x11; if (g < 0) g = 0; else if (g > 0x0F) g = 0x0F;
        short b = (short)c.b + 0x08; b /= 0x11; if (b < 0) b = 0; else if (b > 0x0F) b = 0x0F;
        gdc_set_palette_colour((unsigned char)i, (unsigned char)r, (unsigned char)g, (unsigned char)b);
    }
}

void set_default_palette(void)
{
    set_main_palette(default_palette);
    copy_main_to_out();
    set_display_palette_out();
}
