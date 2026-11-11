/*
 * hal_audio.c — PC-98 audio HAL: MPU-401 (MIDI) + 86-board PCM (devdoc 101).
 *
 * The OPNA FM half of the audio HAL lives in hal_fm.c; the A460/A466
 * registers the two halves share are in hal_audio_regs.h.
 *
 * MIDI (MPU-PC98 / MPU-98II, ports 0xC0D0/0xC0D2):
 *   - hal_audio_detect(): reset (0xFF) then UART (0x3F), each acknowledged
 *     by 0xFE on the data port.  On a real machine without a card, or an
 *     NP2kai build with MIDI disabled, the status port reads back 0xFF and
 *     the probe times out -> 0.
 *   - hal_midi_out(): poll status bit6 (MIDIOUT_BUSY) clear, then write a
 *     byte to the data port (UART passthrough).
 *
 * PCM (86-board YM3433B FIFO, fixed ports):
 *   - A460: bit0 selects OPNA, bit1 set forces FM silent (init writes 0x01)
 *   - A468: bit7 output enable, bit5 A46A-select (1=fifosize, 0=dactrl),
 *           bit3 buffer reset, bits2-0 PCM rate code
 *   - A46A: fifosize ((val+1)<<7; 0xFF -> 0x7FFC) or dactrl (0x50=8bit mono R)
 *   - A46C: one FIFO data byte per write
 *   - A466: read bit7 = buffer full; write 0xA0.. = volume
 *
 * The emulator (and real hardware) exposes no fine-grained fill count, so
 * the pump writes one byte per "not full" poll, bounded per tick.
 */
#include <stddef.h>  /* NULL */
#include "hal.h"
#include "pc98.h"
#include "hal_audio_regs.h"

/* --- MPU-401 / MPU-PC98 --- */

#define MPU_DATA_PORT   0xC0D0
#define MPU_STATUS_PORT 0xC0D2

#define MPU_STATUS_OUT_BUSY   0x40  /* bit6: MIDI out busy */
#define MPU_STATUS_RX_PENDING 0x80  /* bit7: cleared when a byte is ready */
#define MPU_ACK               0xFE
#define MPU_CMD_UART          0x3F
#define MPU_CMD_RESET         0xFF

#define MPU_PROBE_ITER 20000

/* Wait for a data byte (bit7 clear) and read it.  Returns -1 on timeout. */
static int mpu_read_byte(void)
{
    int i;

    for (i = 0; i < MPU_PROBE_ITER; i++)
        if ((inb(MPU_STATUS_PORT) & MPU_STATUS_RX_PENDING) == 0)
            return inb(MPU_DATA_PORT);
    return -1;
}

int hal_audio_detect(void)
{
    /* Reset, expect ACK. */
    outb(MPU_STATUS_PORT, MPU_CMD_RESET);
    if (mpu_read_byte() != MPU_ACK)
        return 0;
    /* Enter UART mode, expect ACK. */
    outb(MPU_STATUS_PORT, MPU_CMD_UART);
    return mpu_read_byte() == MPU_ACK;
}

void hal_midi_out(uint8_t b)
{
    int i;

    for (i = 0; i < MPU_PROBE_ITER; i++) {
        if ((inb(MPU_STATUS_PORT) & MPU_STATUS_OUT_BUSY) == 0) {
            outb(MPU_DATA_PORT, b);
            return;
        }
    }
}

/* --- 86-board PCM --- */

#define PCM_CTRL_PORT    0xA468
#define PCM_DACTRL_PORT  0xA46A
#define PCM_DATA_PORT    0xA46C

/* Port bit fields (docs/refdocs/F02_86pcm_registers.md §4).  Note that
 * A468 bit5 does NOT program a "fifosize": it is the FIFO interrupt permit,
 * and while it is set A46A is decoded as the FIFO *interrupt interval*
 * register instead of D/A control.  hal_pcm_play() raises it only to write
 * the interval, then drops it before programming the D/A mode. */
#define PCM_CTRL_OUT_EN     0x80  /* bit7: FIFO output enable */
#define PCM_CTRL_A46A_IRQ   0x20  /* bit5: FIFO IRQ permit (A46A = irq interval) */
#define PCM_CTRL_BUF_RESET  0x08  /* bit3: buffer reset (0->1 edge) */

#define PCM_DACTRL_8BIT_MONO_R 0x50  /* bit6=0: 8bit, bits5-4=01: right only */

/* 0xFF + 1 * 128 = 32768 = exactly the 32KB FIFO capacity. */
#define PCM_IRQ_INTERVAL_MAX 0xFF

/* A466 electronic volume / path constants are shared with hal_fm.c and live
 * in hal_audio_regs.h (PCM_VOL_PATH_PCM / FM_VOL_PATH_VOL1 / PCM_VOL_ATTEN_MAX). */

/* Sample rate per A468 bit2-0 (F02 §4.3).  Used to convert "how much real
 * time has passed since the last tick" into "how many bytes the FIFO needs";
 * pushing a fixed 2KB burst instead filled the 32KB FIFO in one interrupt and
 * spent milliseconds of handler time on port writes (devdoc 167). */
static const uint32_t g_pcm_rate_hz[8] = {
    44100, 33075, 22050, 16537, 11025, 8269, 5512, 4134
};

/* Upper bound for a single pump, in bytes.  1024 is ~23ms at 44.1kHz: enough
 * to refill after a late tick, small enough that the handler stays short. */
#define PCM_TICK_MAX_BYTES 2048
/* stage 4: cap covers double-period ~1422 bytes (devdoc 169) */

struct pcm_state {
    const uint8_t *data;   /* caller-owned sample buffer (borrowed) */
    uint32_t len;
    uint32_t pos;
    int      rate;         /* 0-7 rate code */
    int      loop;         /* 1: rewind pos at EOF (caller-decided) */
    int      active;
};

static struct pcm_state g_pcm;
static int g_pcm_vol;    /* A466 attenuation 0-15, 0 = loudest */
static uint32_t g_pcm_debt_bytes;  /* stage 4: un-fed byte remainder carried across ticks (devdoc 169) */

int hal_pcm_active(void)
{
    return g_pcm.active;
}

void hal_pcm_set_volume(int step)
{
    if (step < 0)
        step = 0;
    if (step > PCM_VOL_ATTEN_MAX)
        step = PCM_VOL_ATTEN_MAX;
    g_pcm_vol = step;
    outb(PCM_STATUS_PORT, (uint8_t)(PCM_VOL_PATH_PCM | step));
}

void hal_pcm_play(const uint8_t *data, uint32_t len, int rate, int loop)
{
    uint8_t rate_code;

    if (!data || len == 0)
        return;
    if (rate < 0)
        rate = 0;
    if (rate > 7)
        rate = 7;
    rate_code = (uint8_t)rate;

    outb(PCM_ID_PORT, PCM_OPNA_SELECT);  /* select OPNA, not forced silent */

    /* Raise A468 bit5 so A46A decodes as the FIFO interrupt interval; pulse
     * the reset bit; set the interval to the full 32KB FIFO. */
    outb(PCM_CTRL_PORT, PCM_CTRL_OUT_EN | PCM_CTRL_A46A_IRQ | PCM_CTRL_BUF_RESET | rate_code);
    outb(PCM_CTRL_PORT, PCM_CTRL_OUT_EN | PCM_CTRL_A46A_IRQ | rate_code);
    outb(PCM_DACTRL_PORT, PCM_IRQ_INTERVAL_MAX);

    /* Drop bit5 so A46A decodes as D/A control again, then program 8bit mono. */
    outb(PCM_CTRL_PORT, PCM_CTRL_OUT_EN | rate_code);
    outb(PCM_DACTRL_PORT, PCM_DACTRL_8BIT_MONO_R);

    outb(PCM_STATUS_PORT, (uint8_t)(PCM_VOL_PATH_PCM | g_pcm_vol));

    g_pcm.data = data;
    g_pcm.len = len;
    g_pcm.pos = 0;
    g_pcm.rate = rate;
    g_pcm.loop = loop ? 1 : 0;
    g_pcm.active = 1;
}



void hal_pcm_stop(void)
{
    if (!g_pcm.active)
        return;
    outb(PCM_CTRL_PORT, PCM_CTRL_BUF_RESET);
    g_pcm.data = NULL;
    g_pcm.active = 0;
}

/* Stage 3: unit-based PCM pump (devdoc 168).  delta_units is in 1/16 ms units
 * (258 units ≈ 16.154 ms at NB=200 / φM=7.9872 MHz); converts to ms for the
 * byte-rate calculation.  Unit-based replacement for the retired ms-based tick. */
void hal_pcm_advance_units(uint32_t units)
{
    uint32_t push;
    uint32_t i;
    uint32_t elapsed_ms;

    if (!g_pcm.active)
        return;

    /* Convert 1/16 ms units back to whole ms for the rate formula. */
    elapsed_ms = (uint32_t)(units / 16UL);
    if (elapsed_ms == 0)
        elapsed_ms = 1;

    push = (g_pcm_rate_hz[g_pcm.rate & 7] * elapsed_ms) / 1000UL;
    if (push == 0)
        push = 1;
    if (push > PCM_TICK_MAX_BYTES)
        push = PCM_TICK_MAX_BYTES;

    /* Stage 4: add carried debt from previous tick to the intended push. */
    push += g_pcm_debt_bytes;
    g_pcm_debt_bytes = 0;  /* debt applied; remainder will be recalculated */
    if (push > g_pcm.len - g_pcm.pos)
        push = g_pcm.len - g_pcm.pos;

    for (i = 0; i < push; i++) {
        if (inb(PCM_STATUS_PORT) & PCM_STATUS_FIFO_FULL)
            break;
        outb(PCM_DATA_PORT, g_pcm.data[g_pcm.pos]);
        g_pcm.pos++;
    }

    if (g_pcm.pos >= g_pcm.len) {
        if (g_pcm.loop) {
            g_pcm.pos = 0;
            return;
        }
        outb(PCM_CTRL_PORT, PCM_CTRL_BUF_RESET);
        g_pcm.data = NULL;
        g_pcm.active = 0;
    }
}
