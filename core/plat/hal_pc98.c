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

/*
 * Platform initialization.
 *
 * PC-98 implementation: initializes uPD8251 serial port (COM1, 9600 8N1)
 * as the debug log output channel.
 */
void hal_init(void) { serial_init(); }

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

/* Virtual wall clock (devdoc 107 / 0.2.134).
 *
 * hal_wallclock_ms() is a MACRO-accurate clock: the accumulated total is
 * monotonic and second-correct across NP2kai's clock holes, but a single-call
 * delta is chunked — the DOS 2Ch reading on NP2kai is whole-second quantized
 * (dl=0 every sample) and delivered in clusters (frozen 3-6 real seconds, then
 * +1000..+6000ms in one jump).  Any consumer that derives a micro-beat from
 * consecutive raw deltas stalls during a hole and bursts on catch-up.
 *
 * This virtual clock bounds the per-pass delta to
 * [SMOOTH_CLOCK_MIN_MS, SMOOTH_CLOCK_MAX_MS], so it advances at main-loop pass
 * cadence through the holes (NP2kai's only smooth tick is ~20-28Hz pass rate)
 * and discards the catch-up surplus.  Macro seconds stay correct up to one
 * clamp per hole; the microscopic beat is smooth and monotonic.
 *
 * Calibration note: MIN_MS=40 is coupled to the pass rate — it is the nominal
 * pass interval under NP2kai (~25Hz -> ~1s/s inside holes).  On real 60Hz
 * hardware the floor inflates the virtual clock when raw reads delta==0; retune
 * SMOOTH_CLOCK_MIN_MS in hal.h if native hardware is ever targeted (has no
 * effect under DOS/4GW+NP2kai where the DOS clock ticks at ~55ms and only the
 * ceiling guard path is ever active). */
static unsigned long smooth_clock_total = 0;
static unsigned long smooth_raw_prev = 0;
static int           smooth_inited = 0;

unsigned long hal_wallclock_smooth_ms(void)
{
    unsigned long raw = hal_wallclock_ms();
    unsigned long delta;

    if (!smooth_inited) {
        smooth_raw_prev = raw;
        smooth_inited = 1;
        return 0UL;    /* baseline pass, no advancement */
    }

    delta = raw - smooth_raw_prev;   /* raw total is monotonic */
    smooth_raw_prev = raw;

    if (delta == 0)            delta = SMOOTH_CLOCK_MIN_MS;
    else if (delta > SMOOTH_CLOCK_MAX_MS) delta = SMOOTH_CLOCK_MAX_MS;

    smooth_clock_total += delta;
    return smooth_clock_total;
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
