/*
 * hal_pc98.c — HAL 的 PC-98 平台实现（核心部分）
 *
 * 实现 hal.h 定义的基础平台抽象接口，将 HAL 调用委派到具体模块：
 *   - hal_init()          → serial_init()        串口初始化
 *   - hal_log()           → serial_puts()        串口字符串输出
 *   - hal_set_palette()   → gdc_set_palette()    GDC 调色板设置
 *   - hal_read_palette()  → gdc_read_palette()   GDC 调色板读取
 *   - hal_vblank_wait()   → GDC 状态端口轮询     垂直同步等待
 *   - hal_vram_*()        → PEGC bank 窗口        VRAM 访问
 *   - hal_bgm/sound/voice → 音频 stub（hal_log 输出）
 *
 * 键盘/鼠标/视频转发分别拆至 hal_kbd.c / hal_mouse.c / hal_video.c。
 *
 * 移植到新平台时，只需替换 plat/ 中各 hal_*.c 的委派目标即可。
 *
 * 参考：docs/ — HAL 架构设计
 */
#include "hal.h"
#include "pc98.h"
#include "serial.h"
#include "gdc.h"
#include <i86.h>

/*
 * Platform initialization.
 *
 * PC-98 implementation: initializes uPD8251 serial port (COM1, 9600 8N1)
 * as the debug log output channel.
 */
void hal_init(void) { serial_init(); }

/*
 * Debug log output.
 *
 * PC-98 implementation: outputs string via serial port.
 * In DPMI protected mode, DOS printf/text layer is invisible;
 * serial is the most reliable debug output path.
 *
 * @param s  NUL-terminated string
 */
void hal_log(const char *s) { serial_puts(s); }

/*
 * Set RGB values for a palette index.
 *
 * Delegates to gdc_set_palette() via GDC PEGC ports 0xA8-0xAE.
 *
 * @param idx  Palette index (0-255)
 * @param r    Red component (0-255)
 * @param g    Green component (0-255)
 * @param b    Blue component (0-255)
 */
void hal_set_palette(int idx, uint8_t r, uint8_t g, uint8_t b) {
    gdc_set_palette(idx, r, g, b);
}

/*
 * Read RGB values for a palette index.
 *
 * Delegates to gdc_read_palette() via GDC PEGC ports 0xA8-0xAE.
 *
 * @param idx  Palette index (0-255)
 * @param r    Output pointer for red component
 * @param g    Output pointer for green component
 * @param b    Output pointer for blue component
 */
void hal_read_palette(int idx, uint8_t *r, uint8_t *g, uint8_t *b) {
    gdc_read_palette(idx, (unsigned char *)r, (unsigned char *)g, (unsigned char *)b);
}

/*
 * Wait for vertical retrace (VBLANK).
 *
 * Polls GDC graphics status port 0xA0 bit 5 (VSYNC flag, refdocs C01).
 * Returns at the beginning of VBLANK, ~16ms safe window for tear-free VRAM ops.
 */
void hal_vblank_wait(void)
{
    int timeout = 100000;
    while (!(inb(GDC_GFX_PARAM) & GDC_VSYNC) && --timeout > 0);
}

/*
 * Wall-clock milliseconds via PIT channel 0 hardware counter.
 *
 * Time source for time-based animation stepping, decoupled from the
 * emulated frame cadence.  The 8254 PIT counter ticks at ~1.193182 MHz
 * and wraps from 0 to 1193181 (~838 µs per full count).  We latch the
 * counter before reading (PIT command 0x00 on port 0x44) and accumulate
 * elapsed ticks into a running millisecond total.  Handles midnight
 * rollover by returning a monotonic-ish value within one day.
 */
static unsigned long pit_ms_total = 0;
static unsigned int  pit_prev = 0;
static unsigned char pit_inited = 0;

#define PIT_FREQ     1193182UL
#define PIT_CH0_PORT 0x40
#define PIT_CMD_PORT 0x44
#define PIT_CMD_LATCH 0x00  /* latch channel 0 counter */

unsigned long hal_wallclock_ms(void)
{
    unsigned int pit_now;
    unsigned int elapsed;

    /* Latch counter before reading */
    outb(PIT_CMD_PORT, PIT_CMD_LATCH);
    pit_now = (unsigned int)inb(PIT_CH0_PORT);
    pit_now |= ((unsigned int)inb(PIT_CH0_PORT)) << 8;

    if (!pit_inited) {
        pit_prev = pit_now;
        pit_inited = 1;
        return pit_ms_total;
    }

    /* PIT counts down; elapsed = (prev - now) mod 2^16 */
    elapsed = (unsigned int)(pit_prev - pit_now);
    pit_prev = pit_now;

    /* Convert PIT ticks to milliseconds: ticks * 1000 / 1193182 */
    pit_ms_total += (unsigned long)elapsed * 1000UL / PIT_FREQ;
    return pit_ms_total;
}

/*
 * Keyboard/mouse/video HAL forwarding is split into hal_kbd.c, hal_mouse.c
 * and hal_video.c respectively.

 *
 * VRAM banked access — abstract PEGC bank port and window address
 * so engine rendering code does not reference hardware addresses.
 */
void hal_vram_bank_select(int bank)
{
    *PEGC_BANK_PORT = (uint16_t)bank;
}

volatile uint8_t *hal_vram_get_window(void)
{
    return (volatile uint8_t *)0xA8000L;
}

/*
 * Audio stubs — see devdocs/0.1版开发文档总结.html#doc-41 for backend implementation plan.
 */
void hal_bgm_play(const char *key) {
    (void)key;
    hal_log("bgm: ");
    hal_log(key);
    hal_log("\r\n");
}

void hal_bgm_stop(void) {
    hal_log("bgm: stop\r\n");
}

void hal_sound_play(const char *key) {
    (void)key;
    hal_log("sound: ");
    hal_log(key);
    hal_log("\r\n");
}

void hal_voice_play(const char *key) {
    (void)key;
    hal_log("voice: ");
    hal_log(key);
    hal_log("\r\n");
}

void hal_sound_stop(void) {
    hal_log("sound: stop\r\n");
}

void hal_voice_stop(void) {
    hal_log("voice: stop\r\n");
}
