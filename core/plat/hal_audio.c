/*
 * hal_audio.c — PC-98 audio HAL: MPU-401 (MIDI) + 86-board PCM (devdoc 101).
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
 *   - A460 bit0: board enable
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

#define PCM_ID_PORT      0xA460
#define PCM_STATUS_PORT  0xA466
#define PCM_CTRL_PORT    0xA468
#define PCM_DACTRL_PORT  0xA46A
#define PCM_DATA_PORT    0xA46C

#define PCM_CTRL_OUT_EN     0x80  /* bit7: PCM output enable */
#define PCM_CTRL_A46A_FIFO  0x20  /* bit5: A46A programs fifosize */
#define PCM_CTRL_BUF_RESET  0x08  /* bit3: buffer reset (0->1 edge) */

#define PCM_DACTRL_8BIT_MONO_R 0x50  /* 8-bit, right channel only */

#define PCM_CTRL_FIFOSIZE_MAX  0xFF  /* ~32KB threshold */

#define PCM_TICK_MAX_BYTES 2048

struct pcm_state {
    const uint8_t *data;   /* caller-owned sample buffer (borrowed) */
    uint32_t len;
    uint32_t pos;
    int      rate;         /* 0-7 rate code */
    int      active;
};

static struct pcm_state g_pcm;

int hal_pcm_active(void)
{
    return g_pcm.active;
}

void hal_pcm_play(const uint8_t *data, uint32_t len, int rate)
{
    uint8_t rate_code;

    if (!data || len == 0)
        return;
    if (rate < 0)
        rate = 0;
    if (rate > 7)
        rate = 7;
    rate_code = (uint8_t)rate;

    outb(PCM_ID_PORT, 0x01);  /* board enable */

    /* Select A46A=fifosize mode; raise + drop buffer reset, set rate. */
    outb(PCM_CTRL_PORT, PCM_CTRL_OUT_EN | PCM_CTRL_A46A_FIFO | PCM_CTRL_BUF_RESET | rate_code);
    outb(PCM_CTRL_PORT, PCM_CTRL_OUT_EN | PCM_CTRL_A46A_FIFO | rate_code);
    outb(PCM_DACTRL_PORT, PCM_CTRL_FIFOSIZE_MAX);  /* large FIFO threshold */

    /* Select A46A=dactrl mode; program 8bit mono. */
    outb(PCM_CTRL_PORT, PCM_CTRL_OUT_EN | rate_code);
    outb(PCM_DACTRL_PORT, PCM_DACTRL_8BIT_MONO_R);

    outb(PCM_STATUS_PORT, 0xA0);  /* full volume */

    g_pcm.data = data;
    g_pcm.len = len;
    g_pcm.pos = 0;
    g_pcm.rate = rate;
    g_pcm.active = 1;
}

void hal_pcm_tick(void)
{
    uint32_t push;
    uint32_t i;

    if (!g_pcm.active)
        return;

    push = g_pcm.len - g_pcm.pos;
    if (push > PCM_TICK_MAX_BYTES)
        push = PCM_TICK_MAX_BYTES;

    for (i = 0; i < push; i++) {
        /* Wait until FIFO not full, then write one byte. */
        if (inb(PCM_STATUS_PORT) & 0x80)
            break;
        outb(PCM_DATA_PORT, g_pcm.data[g_pcm.pos]);
        g_pcm.pos++;
    }

    if (g_pcm.pos >= g_pcm.len) {
        /* EOF: stop output, drop the buffer reference. */
        outb(PCM_CTRL_PORT, PCM_CTRL_BUF_RESET);
        g_pcm.data = NULL;
        g_pcm.active = 0;
    }
}

void hal_pcm_stop(void)
{
    if (!g_pcm.active)
        return;
    outb(PCM_CTRL_PORT, PCM_CTRL_BUF_RESET);
    g_pcm.data = NULL;
    g_pcm.active = 0;
}
