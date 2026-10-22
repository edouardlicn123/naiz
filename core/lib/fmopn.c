/*
 * fmopn.c — Pure OPNA register model (devdocs/123 §四 M1).
 *
 * No hardware access.  Frequencies derive from the YM2608 master clock
 * 7.9872 MHz (F03 §3.8); register encodings match F03 §3.2/§3.3 and the
 * NP2kai register decoder (sound/opna.c, opngenc.c).
 *
 * No floating point on the note/bend/SSG path (devdoc 165 §3.3 B2): the
 * interrupt-driven BGM pump runs these from a hardware ISR, where Watcom's
 * __interrupt does not preserve the x87 stack and pow()/double math would
 * clobber a computation the main loop had in flight.  Note->(block,fnum) is a
 * precomputed table; the remaining encoders are integer.
 */
#include "fmopn.h"

/* Register slot for each algorithm operator index (op1->0x30, op2->0x38,
 * op3->0x34, op4->0x3C).  Masked to 0..3 for 4-op algorithms. */
const uint8_t fmopn_op_slot[FMOPN_OPS_PER_VOICE] = { 0, 2, 1, 3 };

/* YM2608 Application Manual: the F-Number for a note is
 *   fnum = (144 * freq * 2^20 / MCLK) / 2^(block-1)
 * i.e.  freq = (fnum << (block-1)) * MCLK / (144 * 2^20).
 * Writing the shift as the raw register block:
 *   freq = (fnum << block) * MCLK / (288 * 2^20)
 *   fnum<<block = freq * 288 * 2^20 / MCLK = freq * 301989888 / 7987200
 *               = freq * 36864 / 975.
 * (An earlier revision omitted the 2^(block-1) halving, so every note was
 * encoded one block low and the chip rendered it an octave flat; devdocs/138.) */
#define FMOPN_FNUM_SCALE_N 36864
#define FMOPN_FNUM_SCALE_D 975

/*
 * note -> packed (block << 10 | fnum), one entry per MIDI note 0..127.
 * fmopn_note_ratio() is on the ISR path (note-on events), so the pow()/double
 * encoding is precomputed here rather than evaluated at runtime (devdoc 165
 * B2).  Regenerate with the formula in the header comment above; the anchors
 * A4 -> 5/520 (0x1608) and C4 -> 4/618 (0x126A) are pinned by test_fmopn.
 * Entries from note 110 up hit the block-7/fnum-1023 ceiling (0x1FFF).
 */
static const uint16_t fmopn_note_table[128] = {
    0x0135, 0x0148, 0x015B, 0x0170, 0x0185, 0x019D, 0x01B5, 0x01CF,
    0x01EB, 0x0208, 0x0227, 0x0248, 0x026A, 0x028F, 0x02B6, 0x02DF,
    0x030B, 0x0339, 0x036A, 0x039E, 0x03D5, 0x0608, 0x0627, 0x0648,
    0x066A, 0x068F, 0x06B6, 0x06DF, 0x070B, 0x0739, 0x076A, 0x079E,
    0x07D5, 0x0A08, 0x0A27, 0x0A48, 0x0A6A, 0x0A8F, 0x0AB6, 0x0ADF,
    0x0B0B, 0x0B39, 0x0B6A, 0x0B9E, 0x0BD5, 0x0E08, 0x0E27, 0x0E48,
    0x0E6A, 0x0E8F, 0x0EB6, 0x0EDF, 0x0F0B, 0x0F39, 0x0F6A, 0x0F9E,
    0x0FD5, 0x1208, 0x1227, 0x1248, 0x126A, 0x128F, 0x12B6, 0x12DF,
    0x130B, 0x1339, 0x136A, 0x139E, 0x13D5, 0x1608, 0x1627, 0x1648,
    0x166A, 0x168F, 0x16B6, 0x16DF, 0x170B, 0x1739, 0x176A, 0x179E,
    0x17D5, 0x1A08, 0x1A27, 0x1A48, 0x1A6A, 0x1A8F, 0x1AB6, 0x1ADF,
    0x1B0B, 0x1B39, 0x1B6A, 0x1B9E, 0x1BD5, 0x1E08, 0x1E27, 0x1E48,
    0x1E6A, 0x1E8F, 0x1EB6, 0x1EDF, 0x1F0B, 0x1F39, 0x1F6A, 0x1F9E,
    0x1FD5, 0x1FFF, 0x1FFF, 0x1FFF, 0x1FFF, 0x1FFF, 0x1FFF, 0x1FFF,
    0x1FFF, 0x1FFF, 0x1FFF, 0x1FFF, 0x1FFF, 0x1FFF, 0x1FFF, 0x1FFF,
    0x1FFF, 0x1FFF, 0x1FFF, 0x1FFF, 0x1FFF, 0x1FFF, 0x1FFF, 0x1FFF,
};

/*
 * Encode an absolute frequency (Hz, fixed-point 1/256) into block/fnum using
 * integer math only.  Inverse of fmopn_ratio_freq_hz.  Mirrors the old double
 * path exactly: quotient = freq*36864/975, halve until it fits 0..1023,
 * round, clamp.  freq_hz_x256 is freq*256 to keep sub-Hz precision without FP.
 */
static void fmopn_freq_ratio_fixed(uint32_t freq_hz_x256, int *block, int *fnum)
{
    /* fnum<<block in 1/256 Hz units: freq_hz_x256 * 36864 / 975. */
    uint64_t full = ((uint64_t)freq_hz_x256 * FMOPN_FNUM_SCALE_N)
                    / (FMOPN_FNUM_SCALE_D * 256u);
    int b = 0;
    int fn;

    if (freq_hz_x256 == 0)
        freq_hz_x256 = 256u;
    while (full > 1023u && b < FMOPN_BLOCK_MAX) {
        full = (full + 1u) >> 1;      /* halve, rounding up like the double path */
        b++;
    }
    fn = (int)full;
    if (fn > FMOPN_FNUM_MAX)
        fn = FMOPN_FNUM_MAX;
    *block = b;
    *fnum = fn;
}

/* Frequency (Hz * 256, integer) represented by a (block, fnum) register pair.
 * Inverse of fmopn_freq_ratio_fixed; shared so pitch bend and the SSG path
 * recover the ratio in fixed point instead of via a double round-trip. */
uint32_t fmopn_ratio_freq_x256(int block, int fnum)
{
    /* freq = (fnum << block) * 975 / 36864; scale by 256 for precision. */
    return (uint32_t)(((uint64_t)((uint32_t)fnum << block) * FMOPN_FNUM_SCALE_D
                       * 256u) / FMOPN_FNUM_SCALE_N);
}

void fmopn_note_ratio(int note, int *block, int *fnum)
{
    uint16_t packed;

    if (note < 0)
        note = 0;
    if (note > 127)
        note = 127;
    packed = fmopn_note_table[note];
    *block = (packed >> 10) & 0x07;
    *fnum = packed & 0x03FF;
}

void fmopn_bend_ratio(int bend, int *block, int *fnum)
{
    /* Linear approx of 2^(+/-2 semitones): factor = 1 + d * (2^(1/6)-1),
     * d = (bend - 8192) / 8192.  2^(1/6) - 1 = 0.122462...  Fixed-point
     * with 4096 units: 0.122462 * 4096 = 501.6 -> 502.
     * Integer path (devdoc 165 B2): scale the recovered frequency by the
     * bend factor in fixed point, then re-encode. */
    uint32_t freq;
    int b, fn;

    if (bend < 0)
        bend = 0;
    if (bend > 16383)
        bend = 16383;

    freq = fmopn_ratio_freq_x256(*block, *fnum);

    {
        long factor = 4096L + ((long)(bend - 8192) * 502L) / 8192L;
        if (factor < 0)
            factor = 0;
        freq = (uint32_t)(((uint64_t)freq * (uint32_t)factor) / 4096u);
    }

    fmopn_freq_ratio_fixed(freq, &b, &fn);
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

/* Index into data[] for the register slot's op block: the algorithm operator
 * whose register slot is regslot (inverse of fmopn_op_slot). */
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
    if ((b & 0x08) != 0)      /* bit3 reserved; 7-6 PAN, 5-4 AMS, 2-0 PMS */
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
    return (uint8_t)(p->data[25] & 0xC0);   /* pan L/R field (bits 7-6) */
}

uint8_t fmopn_patch_ams(const FmopnPatch *p)
{
    return (uint8_t)((p->data[25] >> 4) & 0x03);   /* AMS field (bits 5-4) */
}

uint8_t fmopn_patch_pms(const FmopnPatch *p)
{
    return (uint8_t)(p->data[25] & 0x07);          /* PMS field (bits 2-0) */
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
