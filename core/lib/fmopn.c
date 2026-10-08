/*
 * fmopn.c — Pure OPNA register model (devdocs/123 §四 M1).
 *
 * No hardware access.  Frequencies derive from the YM2608 master clock
 * 7.9872 MHz (F03 §3.8); register encodings match F03 §3.2/§3.3 and the
 * NP2kai register decoder (sound/opna.c, opngenc.c).
 */
#include <math.h>

#include "fmopn.h"

/* File order = 1-3-2-4 (PMD .FF / MUCOM88 .DAT); chip slot for each. */
const uint8_t fmopn_op_slot[FMOPN_OPS_PER_VOICE] = { 0, 2, 1, 3 };

/* freq = (fnum << block) * MCLK / (144 * 2^20);  MCLK = 7987200.
 *   fnum<<block = freq * 150994944 / 7987200 = freq * 18432 / 975.        */
#define FMOPN_FNUM_SCALE_N 18432
#define FMOPN_FNUM_SCALE_D 975

static double fmopn_note_freq(int note)
{
    double f;

    if (note < 0)
        note = 0;
    if (note > 127)
        note = 127;
    f = 440.0 * pow(2.0, (note - 69) / 12.0);
    return f;
}

/* Encode an absolute frequency (Hz) into block/fnum.  Rounds the per-block
 * quotient so the canonical anchors land exactly: A4 (440) -> 520/4,
 * C4 (261.63) -> 618/3. */
static void fmopn_freq_ratio(double freq, int *block, int *fnum)
{
    double full;
    int b = 0, fn;

    if (freq <= 0.0)
        freq = 1.0;
    full = freq * FMOPN_FNUM_SCALE_N / FMOPN_FNUM_SCALE_D;
    /* Keep the per-block quotient in fnum range: divide until round(full)
     * fits 0..1023 (a 1023.5+ quotient would round to 1024 and clamp, which
     * would silently lose half a semitone). */
    while (full > 1023.0 && b < FMOPN_BLOCK_MAX) {
        full *= 0.5;
        b++;
    }
    fn = (int)(full + 0.5);
    if (fn > FMOPN_FNUM_MAX)
        fn = FMOPN_FNUM_MAX;
    *block = b;
    *fnum = fn;
}

void fmopn_note_ratio(int note, int *block, int *fnum)
{
    fmopn_freq_ratio(fmopn_note_freq(note), block, fnum);
}

void fmopn_bend_ratio(int bend, int *block, int *fnum)
{
    /* Linear approx of 2^(+/-2 semitones): factor = 1 + d * (2^(1/6)-1),
     * d = (bend - 8192) / 8192.  2^(1/6) - 1 = 0.122462...  Fixed-point
     * with 4096 units: 0.122462 * 4096 = 501.6 -> 502. */
    double freq;
    long fh;
    int b = *block, fn = *fnum;

    if (bend < 0)
        bend = 0;
    if (bend > 16383)
        bend = 16383;

    /* Recover the pre-block frequency from the stored ratio. */
    fh = ((long)fn << b);
    freq = ((double)fh) * 7987200.0 / 150994944.0;

    /* Apply the bend factor, fixed-point to stay in [0.88, 1.12]. */
    {
        long factor = 4096L + ((bend - 8192L) * 502L) / 8192L;
        if (factor < 0)
            factor = 0;
        freq = freq * ((double)factor) / 4096.0;
    }

    fmopn_freq_ratio(freq, &b, &fn);
    *block = b;
    *fnum = fn;
}

uint8_t fmopn_keyon_value(int ch, int keymask)
{
    uint8_t sel;

    if (ch < 0)
        ch = 0;
    if (ch >= FMOPN_FM_CHANNELS)
        ch = FMOPN_FM_CHANNELS - 1;
    sel = (ch < 3) ? (uint8_t)ch : (uint8_t)(0x04 + (ch - 3));
    return (uint8_t)(((keymask & 0x0F) << 4) | sel);
}

uint8_t fmopn_ssg_period_fine(int period)
{
    if (period < 0)
        period = 0;
    if (period > FMOPN_SSG_PERIOD_MAX)
        period = FMOPN_SSG_PERIOD_MAX;
    return (uint8_t)(period & 0xFF);
}

uint8_t fmopn_ssg_period_coarse(int period)
{
    if (period < 0)
        period = 0;
    if (period > FMOPN_SSG_PERIOD_MAX)
        period = FMOPN_SSG_PERIOD_MAX;
    return (uint8_t)((period >> 8) & 0x0F);
}

/* --- patch layout helpers ---------------------------------------------- */

/* Index into data[] for the register slot's op block (file order inverse). */
static int fmopn_file_slot(int regslot)
{
    int k;

    for (k = 0; k < FMOPN_OPS_PER_VOICE; k++)
        if (fmopn_op_slot[k] == regslot)
            return k;
    return 0;
}

int fmopn_patch_validate(const FmopnPatch *p)
{
    int err = 0, k, i;
    uint8_t b;

    if (!p)
        return FMOPN_E_RESERVED;

    for (k = 0; k < FMOPN_OPS_PER_VOICE; k++) {
        i = k * 6;
        if ((p->data[i] >> 4) > 0x07)
            err |= FMOPN_E_DT;
        if ((p->data[i + 1] & 0x80) != 0)
            err |= FMOPN_E_TL;
        if ((p->data[i + 2] & 0x20) != 0)      /* bit5 unused in KS/AR */
            err |= FMOPN_E_KSAR;
        if ((p->data[i + 3] & 0x60) != 0)      /* bits6-5 unused in AM/D1R */
            err |= FMOPN_E_AMD1R;
        if ((p->data[i + 4] & 0xE0) != 0)      /* D2R is 5 bits */
            err |= FMOPN_E_D2R;
        /* SL/RR use all 8 bits (4+4); no unused bit to check. */
    }

    b = p->data[24];
    if ((b & 0xC0) != 0)      /* FB is bits5-3, AL bits2-0 */
        err |= FMOPN_E_FBALG;
    b = p->data[25];
    if ((b & 0x0F) != 0)      /* PAN uses bits7-4 only */
        err |= FMOPN_E_PAN;
    for (i = 26; i < FMOPN_PATCH_BYTES; i++)
        if (p->data[i] != 0)
            err |= FMOPN_E_RESERVED;

    return err;
}

uint8_t fmopn_patch_fb_alg(const FmopnPatch *p)
{
    return p->data[24];
}

uint8_t fmopn_patch_pan(const FmopnPatch *p)
{
    return p->data[25];
}

uint8_t fmopn_op_dt_mul(const FmopnPatch *p, int regslot)
{
    return p->data[fmopn_file_slot(regslot) * 6 + 0];
}

uint8_t fmopn_op_tl(const FmopnPatch *p, int regslot)
{
    return p->data[fmopn_file_slot(regslot) * 6 + 1];
}

uint8_t fmopn_op_ks_ar(const FmopnPatch *p, int regslot)
{
    return p->data[fmopn_file_slot(regslot) * 6 + 2];
}

uint8_t fmopn_op_am_d1r(const FmopnPatch *p, int regslot)
{
    return p->data[fmopn_file_slot(regslot) * 6 + 3];
}

uint8_t fmopn_op_d2r(const FmopnPatch *p, int regslot)
{
    return p->data[fmopn_file_slot(regslot) * 6 + 4];
}

uint8_t fmopn_op_sl_rr(const FmopnPatch *p, int regslot)
{
    return p->data[fmopn_file_slot(regslot) * 6 + 5];
}

/* --- register addressing ------------------------------------------------ */

void fmopn_op_addr(int ch, uint8_t reg, int *bank, uint8_t *addr)
{
    if (ch < 0)
        ch = 0;
    if (ch >= FMOPN_FM_CHANNELS)
        ch = FMOPN_FM_CHANNELS - 1;
    *bank = (ch >= 3) ? 1 : 0;
    *addr = (uint8_t)(reg + (ch % 3));
}

void fmopn_ch_addr(int ch, uint8_t reg, int *bank, uint8_t *addr)
{
    if (ch < 0)
        ch = 0;
    if (ch >= FMOPN_FM_CHANNELS)
        ch = FMOPN_FM_CHANNELS - 1;
    *bank = (ch >= 3) ? 1 : 0;
    *addr = (uint8_t)(reg + (ch % 3));
}
