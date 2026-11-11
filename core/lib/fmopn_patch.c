/*
 * fmopn_patch.c — OPNA patch-record model (devdocs/123 §四 M1, §五; F03 §5.2).
 *
 * The 32-byte patch record and its register-slot accessors, split out of
 * fmopn.c so the pure "patch layout" concern sits apart from the note/time
 * encoders and register addressing.  No hardware access: core/lib is
 * host-testable (tools/tests/test_fmopn.py compiles this file too).
 *
 * The four operators are stored in algorithm-operator order (file idx k =
 * operator k+1), which is not the chip's register order — fmopn_op_slot maps
 * operator index -> register slot.
 */
#include "fmopn.h"

/* Register slot for each algorithm operator index (op1->0x30, op2->0x38,
 * op3->0x34, op4->0x3C).  Masked to 0..3 for 4-op algorithms. */
const uint8_t fmopn_op_slot[FMOPN_OPS_PER_VOICE] = { 0, 2, 1, 3 };

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

/* One byte of an operator block: the op block is 6 bytes per operator
 * (DT/MUL, TL, KS/AR, AM/D1R, D2R, SL/RR) in the order the chip registers
 * use.  Every per-operator accessor below differs only in the byte index,
 * so the addressing lives here once. */
static uint8_t fmopn_op_byte(const FmopnPatch *p, int regslot, int idx)
{
    return p->data[fmopn_file_slot(regslot) * 6 + idx];
}

uint8_t fmopn_op_dt_mul(const FmopnPatch *p, int regslot)
{
    return fmopn_op_byte(p, regslot, 0);
}

uint8_t fmopn_op_tl(const FmopnPatch *p, int regslot)
{
    return fmopn_op_byte(p, regslot, 1);
}

uint8_t fmopn_op_ks_ar(const FmopnPatch *p, int regslot)
{
    return fmopn_op_byte(p, regslot, 2);
}

uint8_t fmopn_op_am_d1r(const FmopnPatch *p, int regslot)
{
    return fmopn_op_byte(p, regslot, 3);
}

uint8_t fmopn_op_d2r(const FmopnPatch *p, int regslot)
{
    return fmopn_op_byte(p, regslot, 4);
}

uint8_t fmopn_op_sl_rr(const FmopnPatch *p, int regslot)
{
    return fmopn_op_byte(p, regslot, 5);
}
