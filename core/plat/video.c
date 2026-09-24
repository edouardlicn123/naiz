/*
 * video.c — CRT BIOS 显示通道（INT 18h）与 PEGC 初始化
 *
 * PC-98 在保护模式下调用 CRT BIOS 必须通过 DPMI 的 int386() 转发，
 * DOS/4GW 会捕获 INT 18h 并将其路由到实模式 BIOS 处理程序。
 *
 * 显示模式设置流程：
 *   1. PEGC MMIO — 启用硬件图形加速器（端口 0xE0100/0xE0102）
 *   2. CRT BIOS INT 18h AH=30h — 设 PEGC 640×400 256 色
 *   3. CRT BIOS INT 18h AH=40h — 启用图形显示层
 *   4. NP2kai 专用：端口 0x6A 触发放大器模拟扩展模式
 *   5. 逐 bank 清 VRAM 消除启动残留
 *
 * 参考：devdocs/0.1版开发文档总结.html#doc-19 — NP2kai 平台差异与调色板自检系统
 *       devdocs/0.1版开发文档总结.html#doc-09 — VRAM 调查报告
 */
#include <stdint.h>
#include <i86.h>
#include "video.h"
#include "pc98.h"
#include "hal.h"

/* NP2kai analog extension port for 256-color mode enable. */
#define VIDEO_ANALOG_PORT      0x6A
#define VIDEO_ANALOG_256_ON    0x21
#define VIDEO_ANALOG_256_OFF   0x20

/* Text VRAM layout (80x25 text mode, char+attr pairs). */
#define TEXT_VRAM_BASE         0xA0000UL
#define TEXT_VRAM_SIZE         4000
#define TEXT_VRAM_ATTR_OFS     0x2000
#define TEXT_ATTR_WHITE_ON_BLK 0x07

/*
 * Output an unsigned int as 8 hex digits via serial (debug).
 *
 * Formats as 8 hex digits without "0x" prefix or leading spaces.
 * Example: 0xAB -> "000000AB". Used for palette readback diagnostics.
 *
 * @param v  Unsigned integer to output
 */
static void video_puthex(unsigned int v)
{
    static const char hex[] = "0123456789ABCDEF";
    char buf[9];
    int i;
    /* Convert from LSB to MSB, filling buf[7..0]. */
    for (i = 7; i >= 0; i--) {
        buf[i] = hex[v & 0xF];
        v >>= 4;
    }
    buf[8] = '\0';
    hal_log(buf);
}

/*
 * Video subsystem initialization.
 *
 * Complete 640x400 256-color PEGC mode setup sequence:
 *
 *   Step 1 — PEGC MMIO: Set MMIO registers to known state.
 *      0xE0100 (mode port) = 0x00 (standard mode)
 *      0xE0102 (VRAM enable) = 0x01 (enable VRAM window)
 *
 *   Step 2 — CRT BIOS mode set: INT 18h AH=30h
 *      AL=0x08 (24kHz standard clock)
 *      BH=0x01 (640x400 lines)
 *      Sets PEGC 256-color mode on NP2kai.
 *
 *   Step 3 — Graphics display enable: INT 18h AH=40h
 *      AL=0x01 (display ON)
 *      NP2kai's AH=30h does not set GDCSCRN_ENABLE (bit 7);
 *      bit 7 of gdcs.grphdisp must be set to trigger pccore render loop.
 *
 *   Step 4 — NP2kai analog extension: port 0x6A
 *      NP2kai's INT 18h AH=30h does not set GDCANALOG_256;
 *      write 0x21 to port 0x6A to trigger gdc_analogext(TRUE).
 *
 *   Step 5 — VRAM clear: zero-fill 8 banks of 32KB each.
 */
void video_init(void)
{
    union REGS regs;
    int i, bank;

    /* === Step 1: PEGC MMIO register init === */
    *PEGC_MODE_PORT   = 0x00;   /* Standard PEGC mode (non-dual/non-interlace) */
    *PEGC_VRAM_ENABLE = 0x01;  /* Enable VRAM window access (A8000h) */

    /* === Step 2: BIOS mode set — 640x400 256c PEGC === */
    regs.h.ah = 0x30;          /* CRT BIOS: 256-color mode set */
    regs.h.al = 0x08;          /* 24kHz standard dot clock */
    regs.h.bh = 0x01;          /* 640x400 line resolution */
    int386(0x18, &regs, &regs);/* Call INT 18h CRT BIOS (DPMI forwarded) */
    if (regs.w.ax & 0xFF00)
        hal_log("WARN: INT 18h AH=30h returned non-zero\r\n");

    /* === Step 3: Enable graphics display layer === */
    regs.h.ah = 0x40;          /* CRT BIOS: graphics display ON/OFF */
    regs.h.al = 0x01;          /* ON */
    regs.h.bh = 0x00;
    int386(0x18, &regs, &regs);
    if (regs.w.ax & 0xFF00)
        hal_log("WARN: INT 18h AH=40h returned non-zero\r\n");

    /* === Step 4: NP2kai analog extension === */
    /*
     * NP2kai's INT 18h AH=30h does not set GDCANALOG_256,
     * causing incorrect 256-color video output.  Writing 0x21
     * to port 0x6A forces gdc_analogext(TRUE).
     * REVIEWED: platform-specific (plat/), by design. */
    outb(VIDEO_ANALOG_PORT, VIDEO_ANALOG_256_ON);

    /* === Step 5: Clear VRAM bank by bank === */
    /*
     * In PEGC mode, VRAM is accessed via bank window (0xA8000-0xAFFFF),
     * bank select register at 0xE0004.  8 banks total (256KB VRAM),
     * 32KB each.  Zero-fill to eliminate random boot-up pixel noise.
     */
    for (bank = 0; bank < 8; bank++) {
        *PEGC_BANK_PORT = (uint16_t)bank;   /* 选择 bank */
        for (i = 0; i < 32768; i++)
            ((volatile uint8_t *)0xA8000L)[i] = 0;  /* bank 内逐字节清零 */
    }
}

/*
 * Verify palette readback values match expectations.
 *
 * Checks indices 1 (blue) and 7 (white) for write-read consistency.
 * If palette ports are not working (I/O mapping errors, emulator quirks),
 * readback values will differ. This is part of the engine startup self-test.
 *
 * Normal output: "Pal chk OK\n", warning: "WARN: ..." with actual values.
 */
void video_check_palette(void)
{
    unsigned char r, g, b;
    int warn = 0;

    /* Check index 1: should be pure blue (0x00, 0x00, 0xFF). */
    hal_read_palette(1, &r, &g, &b);
    if (r != 0x00 || g != 0x00 || b != 0xFF) {
        hal_log("WARN: pal[1] readback != Blue(00,00,FF): ");
        video_puthex(r); hal_log(","); video_puthex(g);
        hal_log(","); video_puthex(b); hal_log("\n");
        warn = 1;
    }

    /* Check index 7: should be pure white (0xFF, 0xFF, 0xFF). */
    hal_read_palette(7, &r, &g, &b);
    if (r != 0xFF || g != 0xFF || b != 0xFF) {
        hal_log("WARN: pal[7] readback != White(FF,FF,FF): ");
        video_puthex(r); hal_log(","); video_puthex(g);
        hal_log(","); video_puthex(b); hal_log("\n");
        warn = 1;
    }

    if (!warn)
        hal_log("Pal chk OK\n");
}

/*
 * Video subsystem exit.
 *
 * Reverses video_init steps to restore text mode:
 *   1. Disable analog extension (0x6A <- 0x20, opposite of 0x21)
 *   2. CRT BIOS INT 18h AH=30h AL=0x00 BH=0x00 -> standard CRT text mode
 *   3. Disable PEGC MMIO (must be after BIOS calls)
 *   4. Clear text VRAM (space char + attr 0x07)
 *   5. Re-enable display for clean DOS prompt
 *
 * Each step outputs VE:0~5 log markers for fault localization.
 */
void video_exit(void)
{
    static int video_exit_called = 0;
    union REGS regs;
    int i;

    if (video_exit_called) {
        hal_log("WARN: video_exit already called\n");
        return;
    }
    video_exit_called = 1;

    hal_log("VE:0\n");

    /* === Step 1: Disable analog extension === */
    outb(VIDEO_ANALOG_PORT, VIDEO_ANALOG_256_OFF);
    hal_log("VE:1\n");

    /* === Step 2: Switch to standard CRT text mode === */
    regs.h.ah = 0x30;          /* CRT BIOS: mode set */
    regs.h.al = 0x00;          /* Text mode */
    regs.h.bh = 0x00;          /* 80x25 standard text */
    int386(0x18, &regs, &regs);
    if (regs.w.ax & 0xFF00)
        hal_log("WARN: VE INT 18h AH=30h failed\r\n");
    hal_log("VE:2\n");

    /* === Step 3: Disable PEGC (must be after all BIOS calls) === */
    *PEGC_MODE_PORT   = 0x00;  /* PEGC mode off */
    *PEGC_VRAM_ENABLE = 0x00; /* Disable VRAM window access */
    hal_log("VE:3\n");

    /* === Step 4: Clear text VRAM for clean DOS prompt === */
    {
        volatile uint8_t *txt = (volatile uint8_t *)TEXT_VRAM_BASE;
        for (i = 0; i < TEXT_VRAM_SIZE; i++) txt[i] = 0x20;          /* char = space */
        for (i = 0; i < TEXT_VRAM_SIZE; i++) txt[TEXT_VRAM_ATTR_OFS + i] = TEXT_ATTR_WHITE_ON_BLK;
    }
    hal_log("VE:4\n");

    /* === Step 5: Re-enable display === */
    regs.h.ah = 0x40;          /* CRT BIOS: display ON/OFF */
    regs.h.al = 0x01;          /* ON */
    regs.h.bh = 0x00;
    int386(0x18, &regs, &regs);
    hal_log("VE:5\n");
}
