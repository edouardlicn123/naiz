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

/* devdoc 133: serial tempo probe toggle (0 = off).  Defaults on so a single
 * build is verifiable; the [VC] line is emitted every 64 advances. */
#ifndef VCLOCK_TRACE_ENABLED
#define VCLOCK_TRACE_ENABLED 1
#endif

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
#if VCLOCK_TRACE_ENABLED
    /* devdoc 133 tempo probe.  step is in 1/16 ms (step/16 = ms/pass), tgt the
     * rate the DOS clock measures, cal=1 once the first window is adopted.
     * Compare step/16 against the display frame time to see whether the clock
     * runs fast or slow.  Compile out with -DVCLOCK_TRACE_ENABLED=0. */
    {
        static unsigned trace_ctr = 0;
        if (++trace_ctr >= 64) {
            trace_ctr = 0;
            hal_logf("[VC] v=%lu w=%lu step=%lu tgt=%lu cal=%d\n",
                     vclock_ms(&g_vclock), hal_wallclock_ms(),
                     g_vclock.step, g_vclock.target,
                     g_vclock.calibrated);
        }
    }
#endif
}

/*
 * Vertical-retrace sync and frame-boundary detection (devdoc 131 A/B).
 *
 * GDC graphics status port 0xA0 bit 5 is the VSYNC flag (refdocs C01).
 *
 * `g_vs_level` tracks the last sampled level so a caller that cannot afford
 * to block (the MAG decode inner loop, devdoc 131 §6 方案 B) can still detect
 * that the display advanced one frame — the virtual clock must step at the
 * DISPLAY's rate, not at the decode loop's stride count, or the BGM races.
 * Frame counting is deliberately used ONLY as a boundary detector, never as a
 * time source: B19 §2.3 retired it as a CLOCK because NP2kai runs it at
 * ~20.5Hz (a 3x-slow time base).  A boundary is just a boundary.
 */
static int g_vs_level = -1;   /* last sampled VSYNC level, -1 = uninitialised */

void hal_vblank_wait(void)
{
    int timeout = 100000;
    while (!(inb(GDC_GFX_PARAM) & GDC_VSYNC) && --timeout > 0);
    /* Returning at the start of a VBLANK:  the flag is asserted here. */
    g_vs_level = 1;
}

/*
 * Non-blocking VSYNC sampling for long CPU-bound paths (devdoc 131 方案 B).
 *
 * Returns 1 exactly once per rising edge (VBLANK start); 0 otherwise.  Cheap
 * enough to call on every MAG decode stride.  The baseline is set by the first
 * call, and hal_vblank_wait() keeps it fresh after a blocking sync, so a
 * blocking pump and a polling decode loop never double-count the same frame.
 */
int hal_vblank_poll(void)
{
    int now = (inb(GDC_GFX_PARAM) & GDC_VSYNC) ? 1 : 0;
    int prev = g_vs_level;
    g_vs_level = now;
    if (prev < 0)
        return 0;            /* establish baseline */
    return (prev == 0 && now == 1);
}

#if NAIZ_IRQ_PROBE
/*
 * devdoc 163 Phase 3 C1: GDC vsync IRQ delivery probe (NP2kai verdict for
 * the interrupt-driven audio pump, devdocs/134).
 *
 * Facts this rests on (refdocs): IRQ2 = INT 0Ah (C01:310; vector base 0x08
 * cross-checked by keyboard.c INT 09h and G01:87), any write to port 0x64
 * arms/wakes the GDC vsync interrupt (C01:311-312, G09 §2), master PIC is
 * 00h cmd / 02h data (G01:78).  The probe samples the master PIC IRR (OCW3
 * 0x0A then data-port read) for ~2 wall seconds in a tight loop.
 *
 * Safety design: the PIC mask (IMR) and the INT 0Ah vector are NEVER touched.
 * A level-triggered PIC shows a pending request in IRR regardless of the IMR
 * mask, so sampling alone proves the GDC asserts the line — zero side effects
 * on DOS, no DPMI vector API needed.  A hit rate near the display rate means
 * the IRQ2 route (devdoc 163 §五 C2) is viable on this platform; zero hits
 * means fall back to the OPNA Timer-B route (F04). */
void hal_irq_probe_run(void)
{
    unsigned long t0;
    unsigned long hits = 0, samples = 0;
    unsigned long imr;

    outb(0x64, 0x00);        /* arm/wake vsync IRQ (C01 §VSYNC 中断) */
    imr = inb(0x02);         /* master IMR (default data-port read select) */
    t0 = hal_wallclock_ms();
    for (;;) {
        if (hal_wallclock_ms() - t0 >= 2000UL)
            break;
        outb(0x00, 0x0A);    /* OCW3: next data-port read returns IRR */
        if (inb(0x02) & 0x04)
            hits++;          /* bit2 = IRQ2 pending */
        samples++;
    }
    hal_logf("[IRQP] vsync irq2 hits=%lu samples=%lu imr=%02lx (2s)\r\n",
             hits, samples, imr);
}
#endif /* NAIZ_IRQ_PROBE */

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
