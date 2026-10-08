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
 * are stored in FILE order 1-3-2-4 (PMD .FF / MUCOM88 .DAT compat), which
 * is not the chip's register order — fmopn_op_slot maps file slot -> chip
 * slot.  Bytes:
 *   0..23   ops, 6 bytes each: DT/MUL, TL, KS/AR, AM/D1R, D2R, SL/RR
 *   24      FB<<3 | AL
 *   25      PANL<<6 | PANR<<4  (default 0xC0: L full, R full)
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

/* File-order op slot -> chip register slot.  Files store 1-3-2-4; the chip
 * numbers operators 1-2-3-4.  Pin once here, once in the compiler and once
 * in the tests (mis-ordering mutes the pitch, silently wrong). */
extern const uint8_t fmopn_op_slot[FMOPN_OPS_PER_VOICE];

/* --- note / bend / keyon encoders -------------------------------------- */

/* MIDI note 0..127 -> chip block/fnum.  Exact fnum<<block = freq*18432/975
 * rounding at the final per-block step (A4 -> block 4 fnum 520, C4 -> 618).
 * Clamps to fnum 1023 / block 7 at the top of MIDI range. */
void fmopn_note_ratio(int note, int *block, int *fnum);

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

/* $B0 / $B4 register values for a channel. */
uint8_t fmopn_patch_fb_alg(const FmopnPatch *p);
uint8_t fmopn_patch_pan(const FmopnPatch *p);

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
