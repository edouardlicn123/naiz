#ifndef PLAT_HAL_AUDIO_REGS_H
#define PLAT_HAL_AUDIO_REGS_H

/*
 * hal_audio_regs.h — 86-board register block shared by the PCM FIFO path
 * (hal_audio.c) and the OPNA FM path (hal_fm.c).
 *
 * A460 selects the OPNA and is written by BOTH halves; A466 is the
 * electronic-volume register for PCM (VOL6) and FM (VOL1) and also carries
 * the FIFO-full status bit.  Keeping the shared ports and fields here is the
 * single source of truth — duplicating the magic numbers across the two
 * halves is exactly the drift class AGENTS §十七 C34/C35 forbids.
 *
 * Register semantics: docs/refdocs/F02_86pcm_registers.md §3/§4.
 */

/* A460: bit0 = select OPNA, bit1 = force OPNA silent.  0x01 = OPNA selected
 * and not muted (F02 §3.2).  hal_pcm_play() and the FM path both write it. */
#define PCM_ID_PORT      0xA460
#define PCM_OPNA_SELECT  0x01

/* A466: write = electronic volume (path field | attenuation); read bit7 =
 * FIFO full. */
#define PCM_STATUS_PORT      0xA466
#define PCM_STATUS_FIFO_FULL 0x80

/* A466 path field (bits7-5): VOL6 = PCM direct output, VOL1 = FM direct. */
#define PCM_VOL_PATH_PCM  0xA0
#define FM_VOL_PATH_VOL1  0x00

/* A466 attenuation is a reversed 4-bit field: 0 = loudest, 15 still audible.
 * True PCM mute is A66E bit0, not this register. */
#define PCM_VOL_ATTEN_MAX 15

#endif /* PLAT_HAL_AUDIO_REGS_H */
