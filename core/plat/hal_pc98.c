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
 *
 * 音频 HAL 实现拆分至 plat/hal_audio.c（MPU-401 MIDI + 86 板 PCM，devdoc 101）。
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
#include "vclock.h"
#include <i86.h>
#include <stdarg.h>
#include <stdio.h>

/*
 * Wall-clock milliseconds via DOS system time (INT 21h AH=2Ch).
 *
 * Clock-source history:
 *   - PIT (0.2.128/0.2.129): read-back under NP2kai is
 *     `nevent_getremain(NEVENT_ITIMER) / pccore.multiple` — driven by the
 *     emulated CPU clock (clk_mult scales it), non-monotonic samples, so
 *     the PIT cannot serve as a clock under the emulator (probe dVB/dLOOP
 *     in 0.2.130, ports 0x71/0x77 per refdocs B02).
 *   - vblank frame counter (0.2.130): NP2kai pass rate is ~20.5Hz
 *     (devdoc 82), so wallclock_frames++ once per hal_vblank_wait()
 *     advanced only ~342ms of clock per real second — a 3x slowdown.
 *   - DOS INT 21h AH=2Ch (this): 10ms granularity, maintained by DOS in
 *     the emulator and real hardware alike.  devdoc 82 §5.3 measured it
 *     exactly (guest 5000ms) under DOS/4GW DPMI; int386() reflection is
 *     the same channel already used for CRT BIOS INT 18h (video.c).
 *
 * Callers treat a decrease (midnight / counter wrap) as recalibration.
 */
static unsigned long wallclock_ms_total = 0;
static unsigned long wallclock_now_prev = 0;
static int          wallclock_inited = 0;

#define WALLCLOCK_DOS_TIME_INT  0x21
#define WALLCLOCK_DOS_AH_GET_TIME 0x2C

/* Virtual wall clock (devdoc 107 / 0.2.134, devdoc 129 follow-up).
 *
 * hal_wallclock_ms() is MACRO-accurate but its single-call delta is coarse:
 * the DOS 2Ch reading is second-quantised and delivered in clusters (frozen
 * 3-6s, then +1000..+6000ms), which froze the naive consumers and burst them
 * on catch-up.  The original answer (0.2.134) clamped the per-pass delta to
 * a fixed floor/ceiling; devdoc 129's frame pump then exposed that
 * clamp's flaw: with the advance happening once per pass, the
 * clamp alternates a 40ms floor step and a 100ms ceiling step, and that
 * uneven step size is the BGM flutter.
 *
 * The smoothing therefore lives in lib/vclock, which slews its step size
 * toward the rate the DOS clock actually measures instead of clamping it.
 * HAL's remaining job is ownership: vclock_advance() is the sole writer (the
 * frame pump) and hal_wallclock_smooth_ms() only reads.
 */
static VClock g_vclock;

/*
 * Platform initialization.
 *
 * PC-98 implementation: initializes uPD8251 serial port (COM1, 9600 8N1)
 * as the debug log output channel.
 */
void hal_init(void) { serial_init(); vclock_init(&g_vclock); }

unsigned long hal_wallclock_ms(void)
{
    union REGS regs;
    unsigned long now;   /* ms since midnight (folded) */

    /* DOS system time via int386() (DPMI-reflected INT 21h AH=2Ch):
     * returns CH=hour, CL=minute, DH=second, DL=hundredths of a second.
     * Fold into a monotonic-ish ms-since-midnight for clean deltas. */
    regs.h.ah = WALLCLOCK_DOS_AH_GET_TIME;
    int386(WALLCLOCK_DOS_TIME_INT, &regs, &regs);

    now = ((unsigned long)regs.h.ch * 3600UL
         + (unsigned long)regs.h.cl * 60UL
         + (unsigned long)regs.h.dh) * 1000UL
        + (unsigned long)regs.h.dl * 10UL;

    if (!wallclock_inited) {
        wallclock_now_prev = now;
        wallclock_inited = 1;
        return wallclock_ms_total;
    }

    if (now >= wallclock_now_prev) {
        wallclock_ms_total += now - wallclock_now_prev;
    } else {
        /* Midnight wrap (now < prev): recalibrate, keep accumulated total. */
    }
    wallclock_now_prev = now;

    return wallclock_ms_total;
}

unsigned long hal_wallclock_smooth_ms(void)
{
    return vclock_ms(&g_vclock);
}

void hal_wallclock_smooth_advance(void)
{
    vclock_advance(&g_vclock, hal_wallclock_ms());
}

/*
 * Wait for vertical retrace (VBLANK).
 *
 * Polls GDC graphics status port 0xA0 bit 5 (VSYNC flag, refdocs C01).
 * Returns at the beginning of VBLANK, ~16ms safe window for tear-free VRAM ops.
 * Purely a pacing/tear-prevention sync point — it no longer feeds the
 * wall clock (NP2kai pass rate ~20.5Hz would make frame counting useless).
 */
void hal_vblank_wait(void)
{
    int timeout = 100000;
    while (!(inb(GDC_GFX_PARAM) & GDC_VSYNC) && --timeout > 0);
}

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
 * Formatted debug log output.
 *
 * printf-style convenience wrapper: formats into a stack buffer then calls
 * hal_log().  Replaces the ad-hoc snprintf+hal_log two-liner scattered across
 * the engine, giving one uniform buffer size and truncation policy.
 */
void hal_logf(const char *fmt, ...)
{
    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    hal_log(buf);
}

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
