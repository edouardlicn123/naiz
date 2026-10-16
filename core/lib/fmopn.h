/*
 * fmopn.h — Pure OPNA register model (devdocs/123 §四 M1).
 *
 * Zero outb(): every function here is deterministic, host-testable logic
 * (core/lib cannot touch hardware; that is hal_fm_*'s job, core/plat).  The
 * engine builds FM/SSG register writes out of these encoders; tests drive
 * them directly (tools/tests/test_fmopn.py).
 *
 * Register layout per docs/refdocs/F03 §3.2/§3.3/§3.8:
 *   - op slot r (0..3) at base 0x30 + r*4 + (ch % 3), bank 0 for ch 0..2
 *     else bank 1; channel-level regs 0xA0/0xA4/0xB0/0xB4 likewise.
 *   - melody note -> block/fnum from F03 §3.8.
 */
#ifndef LIB_FMOPN_H
#define LIB_FMOPN_H

#include <stdint.h>

#define FMOPN_FM_CHANNELS      6   /* YM2608 FM voices */
#define FMOPN_SSG_CHANNELS     3   /* YM2608 SSG voices */
#define FMOPN_OPS_PER_VOICE    4

/* Patch record: 32 bytes (devdocs/123 §五, F03 §5.2).  The four operators
 * are stored in algorithm-operator order (file idx k = operator k+1), which
 * is not the chip's register order — fmopn_op_slot maps operator index ->
 * register slot.  Bytes:
 *   0..23   ops, 6 bytes each: DT/MUL, TL, KS/AR, AM/D1R, D2R, SL/RR
 *   24      FB<<3 | AL
 *   25      PANL<<6|PANR<<4|AMS<<4|PMS (default 0xC0: L/R full, no LFO)
 *           bits7-6 = pan L/R, bits5-4 = LFO AM sensitivity (AMS 0-3),
 *           bit3 reserved, bits2-0 = LFO PM sensitivity (PMS 0-7).  Written
 *           verbatim to reg $B4 (F03 §3.3; NP2kai fmgen decodes pan from
 *           data>>6, AMS from (ms>>4)&3, PMS from ms&7).
 *   26..31  reserved, must be 0
 */
#define FMOPN_PATCH_BYTES  32
#define FMOPN_FNUM_MAX     1023   /* 10-bit, block 0..7 */
#define FMOPN_BLOCK_MAX      7
#define FMOPN_SSG_PERIOD_MAX 4095

/* Patch validation error bits (fmopn_patch_validate). */
#define FMOPN_E_RESERVED 0x01
#define FMOPN_E_DT       0x02
#define FMOPN_E_TL       0x04
#define FMOPN_E_KSAR     0x08
#define FMOPN_E_AMD1R    0x10
#define FMOPN_E_D2R      0x20
#define FMOPN_E_SLRR     0x40
#define FMOPN_E_FBALG    0x80
#define FMOPN_E_PAN      0x100

typedef struct {
    uint8_t data[FMOPN_PATCH_BYTES];
} FmopnPatch;

/* Algorithm operator index -> chip register slot.  The OPN core addresses
 * operators in slot order 1-3-2-4: algorithm op 1 -> 0x30, op 2 -> 0x38,
 * op 3 -> 0x34, op 4 -> 0x3C (so alg=4's pairs are op1->op2 / op3->op4).
 * Confirmed against ymfm operator_map and NP2kai fmgen slottable.  Pin once
 * here, once in the compiler and once in the tests (mis-ordering mutes the
 * pitch, silently wrong). */
extern const uint8_t fmopn_op_slot[FMOPN_OPS_PER_VOICE];

/* --- note / bend / keyon encoders -------------------------------------- */

/* MIDI note 0..127 -> chip block/fnum.  Exact fnum<<block = freq*36864/975
 * rounding at the final per-block step (A4 -> block 5 fnum 520, C4 -> block 4
 * fnum 618).  Clamps to fnum 1023 / block 7 at the top of MIDI range. */
void fmopn_note_ratio(int note, int *block, int *fnum);

/* Frequency (Hz) represented by a (block, fnum) pair.  Inverse of the note
 * encoder; used by the SSG-percussion path and pitch bend. */
double fmopn_ratio_freq(int block, int fnum);

/* Pitch bend 0..16383 (8192 centred) applied to an existing block/fnum.
 * Linear approximation of +-2 semitones, block unchanged, fnum clamped. */
void fmopn_bend_ratio(int bend, int *block, int *fnum);

/* $28 KEYON value: channel 0..5, keymask 0..15 (bits 4-7).  Channels 3..5
 * are selected with bit2 set (FM4-6 live in the extended bank). */
uint8_t fmopn_keyon_value(int ch, int keymask);

/* SSG tone-period register halves (period 0..4095). */
uint8_t fmopn_ssg_period_fine(int period);
uint8_t fmopn_ssg_period_coarse(int period);

/* --- patch field accessors (register-slot addressed, chip semantic) ------- */

/* 0 on success, else a bitwise OR of FMOPN_E_* (missing/invalid fields). */
int fmopn_patch_validate(const FmopnPatch *p);

/* $B0 / $B4 register values for a channel.  fmopn_patch_pan returns the pan
 * field only (bits 7-6); fmseq packs pan | AMS<<4 | PMS back into $B4. */
uint8_t fmopn_patch_fb_alg(const FmopnPatch *p);
uint8_t fmopn_patch_pan(const FmopnPatch *p);

/* LFO sensitivity fields packed in $B4 (byte 25). */
uint8_t fmopn_patch_ams(const FmopnPatch *p);
uint8_t fmopn_patch_pms(const FmopnPatch *p);

/* Per-slot op register values; regslot is the CHIP slot 0..3. */
uint8_t fmopn_op_dt_mul(const FmopnPatch *p, int regslot);
uint8_t fmopn_op_tl(const FmopnPatch *p, int regslot);
uint8_t fmopn_op_ks_ar(const FmopnPatch *p, int regslot);
uint8_t fmopn_op_am_d1r(const FmopnPatch *p, int regslot);
uint8_t fmopn_op_d2r(const FmopnPatch *p, int regslot);
uint8_t fmopn_op_sl_rr(const FmopnPatch *p, int regslot);

/* --- register addressing -------------------------------------------------- */

/* (bank, addr) for an operator register base of a channel.  reg is the op
 * register base (0x30/0x40/0x50/0x60/0x70/0x80/0x90).  bank 0 -> 0x188/0x18A,
 * bank 1 -> 0x18C/0x18E (F03 §3.8). */
void fmopn_op_addr(int ch, uint8_t reg, int *bank, uint8_t *addr);

/* (bank, addr) for a channel-level register (0xA0/0xA4/0xB0/0xB4). */
void fmopn_ch_addr(int ch, uint8_t reg, int *bank, uint8_t *addr);

#endif /* LIB_FMOPN_H */
