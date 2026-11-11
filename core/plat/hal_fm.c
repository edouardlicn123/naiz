/*
 * hal_fm.c — 86-board OPNA FM register interface (devdocs/123 M3, F03 §3.8).
 *
 * The FM half of the PC-98 audio HAL.  The A460/A466 86-board registers it
 * shares with the PCM FIFO path (hal_audio.c) live in hal_audio_regs.h.
 *
 * A460 bit0 selects the OPNA and must be raised before touching 0188/018A
 * (and before the extended window 018C/018E routes); bit1=0 keeps the FM
 * voice unmuted.  Every register write goes through hal_fm_write_reg(),
 * which owns the outb() port pair.
 */
#include "hal.h"
#include "pc98.h"
#include "hal_audio_regs.h"

/* Port pair for the ordinary register group (SSG / RHYTHM / system / FM
 * ch1-3).  A write to the address latch selects a register for the next
 * data access; the data port both writes that register and reads it back. */
#define FM_ADDR_LATCH       0x0188
#define FM_DATA_PORT        0x018A

/* Port pair for the extended register group (FM ch4-6, ADPCM).  It only
 * routes through when A460 bit0 selects the OPNA (hal_fm_init below, and
 * hal_pcm_play already raises it). */
#define FM_EXT_ADDR_LATCH   0x018C
#define FM_EXT_DATA_PORT    0x018E

#define FM_FM_CHANNELS      6   /* YM2608 FM voices (F03 §3.3) */
#define FM_SSG_MIX_SILENT   0x3F  /* reg7: every bit 0 disables that output */

/* LFO rate index (reg $22 bits2-0, LFRQ).  Rate rises as the index grows;
 * index 2 is roughly 6.6 Hz, a natural vibrato/tremolo speed.  Only channels
 * whose patch leaves AMS/PMS > 0 react, so this is inert for the rest. */
#define FM_LFO_RATE         2

/* Per-write register trace (devdocs/123 §1.5 判据 5): audit every
 * (port, addr, val) on the serial channel.  Compile-time switch — a 60Hz
 * register pump would spam the trace during normal use, so flip this to 1
 * and rebuild (then ./makegame.sh make) only for a trace session. */
#define FM_TRACE_ENABLED 0

int hal_fm_detect(void)
{
    /* Capability ID read (F03 §3.8 fact 3): latch 0xFF, then read back.
     * An OPNA answers 1; an empty bus reads 0xFF.
     *
     * Must raise A460 bit0 (select OPNA) BEFORE touching 0188/018A, because
     * the OPNA's register window is only routed when OPNA is selected
     * (F03 §3.8 fact 1 — same gate that protects the 018C/018E extended
     * window).  Without this the detect always fails on cold boot, before
     * any hal_pcm_play() or hal_fm_init() has set A460.
     *
     * bit1 = 0 is critical too: A460 bit1 forces OPNA silent (F02 §3.2),
     * and hal_pcm_play writes 0x01 for exactly this reason.  We mirror it
     * here so the detect sequence itself never mutes the chip. */
    outb(PCM_ID_PORT, PCM_OPNA_SELECT);
    outb(FM_ADDR_LATCH, 0xFF);
    return inb(FM_DATA_PORT) == 1;
}

void hal_fm_init(void)
{
    /* A460 bit0 selects the OPNA; without it the extended window
     * 0x18C/0x18E never routes (F03 §3.8 fact 1).  bit1=0 keeps the FM
     * voice unmuted (AGENTS §十四 音频通路 note 3). */
    outb(PCM_ID_PORT, PCM_OPNA_SELECT);
    /* Prime FM VOL1 at full loudness (attenuation 0). */
    outb(PCM_STATUS_PORT, (uint8_t)(FM_VOL_PATH_VOL1 | 0x00));
    /* Enable all six FM voices (reg $29 bit7 = SCH).  YM2608 wakes up with
     * SCH=0, where channels 4-6 are simply not assigned (manual: "Channel 4-6
     * is not good at assign"); the datasheet says to set bit 7 first to use
     * the chip's six-voice mode.  Without this the fmseq allocator silently
     * drops any note it places on voice 3-5 (devdoc 156).  bits 0-5 are the
     * timer IRQ enables, left 0 (the engine polls, it takes no OPNA IRQ). */
    hal_fm_write_reg(0, 0x29, 0x80);
    /* Enable the LFO (reg $22): bit3 on, bits2-0 = rate (F03 §3.3).  This is
     * the chip-wide oscillator that $B4 AMS/PMS depths modulate; with those
     * bits 0 the register has no audible effect. */
    hal_fm_write_reg(0, 0x22, (uint8_t)(0x08 | FM_LFO_RATE));
}

void hal_fm_set_volume(int atten)
{
    /* A466 VOL1 (FM direct) attenuation, reversed 0 (loudest) .. 15. */
    if (atten < 0)
        atten = 0;
    if (atten > PCM_VOL_ATTEN_MAX)
        atten = PCM_VOL_ATTEN_MAX;
    outb(PCM_STATUS_PORT, (uint8_t)(FM_VOL_PATH_VOL1 | (atten & 0x0F)));
}

void hal_fm_shutdown(void)
{
    int ch;

#if NAIZ_BGM_IRQ
    { extern void _disable(void); _disable(); }
#endif
    /* Key off every FM voice: $28 carries the channel bits (bit2 selects
     * FM4-6, F03 §3.8 fact 2) and a zero key mask. */
    for (ch = 0; ch < FM_FM_CHANNELS; ch++)
        hal_fm_write_reg(0, 0x28, (uint8_t)((ch >= 3 ? 4 : 0) | (ch % 3)));
    /* SSG: disable every mixer output. */
    hal_fm_write_reg(0, 0x07, FM_SSG_MIX_SILENT);
#if NAIZ_BGM_IRQ
    { extern void _enable(void); _enable(); }
#endif
}

void hal_fm_write_reg(int bank, uint8_t addr, uint8_t val)
{
    /* devdoc 198: the OPNA port pair ($188/$18A or $18C/$18E) is not atomic --
     * if the Timer-B ISR fires between outb(addr_latch) and outb(data), the
     * handler's FM_TIMER_CTRL write clobbers the address latch, and the main
     * thread's data byte lands on $27 (Timer-B control).  If that data has
     * D3==0 (ENABLE_B), the timer is permanently disabled.  Protect the pair
     * with cli/sti.  Skip cli if we're already inside the ISR (IF=0 already,
     * and sti would let the ISR re-enter itself). */
#if NAIZ_BGM_IRQ
    int in_isr = hal_bgm_irq_in_isr();
    if (!in_isr) { extern void _disable(void); _disable(); }
#endif
    if (bank == 0) {
        outb(FM_ADDR_LATCH, addr);
        outb(FM_DATA_PORT, val);
    } else {
        outb(FM_EXT_ADDR_LATCH, addr);
        outb(FM_EXT_DATA_PORT, val);
    }
#if NAIZ_BGM_IRQ
    if (!in_isr) { extern void _enable(void); _enable(); }
#endif
}
