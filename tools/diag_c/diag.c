/*
 * VRAM/GDC 诊断 — 串口输出 GDC 寄存器 + VRAM 采样
 *
 * Standalone PC-98 diagnostic tool (not used by the engine).
 * Reports VRAM state before/after GDC init, fills with test patterns,
 * and validates readback.
 */
#include <stdio.h>
#include <string.h>
#include <conio.h>
#include "font.h"

typedef unsigned char uint8_t;

#include "serial.h"
#include "gdc.h"
#include "video.h"

/* Send an unsigned char as two lowercase hex digits over serial. */
static void serial_puthex(unsigned char c)
{
    static const char hexdig[] = "0123456789abcdef";
    char buf[3];
    buf[0] = hexdig[(c >> 4) & 0x0F];
    buf[1] = hexdig[c & 0x0F];
    buf[2] = 0;
    serial_puts(buf);
}

/* Minimal HAL stubs for linking video.o into this standalone tool.
 * The full HAL (hal_pc98.c) drags in the whole keyboard/mouse chain;
 * diag only needs log + palette readback. */
void hal_log(const char *s) { serial_puts(s); }
void hal_read_palette(int idx, unsigned char *r, unsigned char *g, unsigned char *b)
{
    gdc_read_palette(idx, r, g, b);
}

/* Dump a named register value as hex (e.g. "  GDC status(0xA0)= 0x87"). */
static void dump_reg(const char *name, unsigned char val)
{
    serial_puts(name);
    serial_puthex(val);
    serial_puts("\r\n");
}

/* Dump a range of VRAM bytes with a label (hex values space-separated). */
static void dump_vram(volatile uint8_t *addr, const char *label, int count)
{
    int i;
    serial_puts(label);
    for (i = 0; i < count; i++) {
        if (i > 0) serial_puts(" ");
        serial_puthex(addr[i]);
    }
    serial_puts("\r\n");
}

/* Diagnostic main: test sequence with serial output for each step.
 * 1. VRAM sample before init
 * 2. GDC init
 * 3. Read GDC status registers
 * 4. Fill VRAM with known patterns (0xAA/0x55/0xCC/0x11)
 * 5. Read back and verify
 * 6. Attempt mode1 register read
 * Loops forever at end. */
int main(void)
{
    int i;
    uint8_t b_sample, r_sample, g_sample;

    serial_init();
    serial_puts("=== GDC/VRAM DIAG ===\r\n");

    /* 1. VRAM before any init */
    b_sample = *(volatile uint8_t *)0xA8000L;
    r_sample = *(volatile uint8_t *)0xB0000L;
    g_sample = *(volatile uint8_t *)0xB8000L;
    serial_puts("VRAM BEFORE INIT:\r\n");
    dump_reg("  B[0xA8000]= ", b_sample);
    dump_reg("  R[0xB0000]= ", r_sample);
    dump_reg("  G[0xB8000]= ", g_sample);

    /* 2. Video/GDC init */
    video_init();
    serial_puts("GDC init done\r\n");

    /* 3. Read GDC status after init */
    {
        uint8_t s0 = inp(0xA0);  /* GDC status */
        uint8_t s1 = inp(0xA2);  /* GDC mode1 return */
        dump_reg("  GDC status(0xA0)=", s0);
        dump_reg("  GDC mode1(0xA2)=", s1);
    }

    /* 4. Fill VRAM with known patterns */
    memset((void *)0xA8000L, 0xAA, 0x40);  /* B: 0xAA */
    memset((void *)0xB0000L, 0x55, 0x40);  /* R: 0x55 */
    memset((void *)0xB8000L, 0xCC, 0x40);  /* G: 0xCC */
    memset((void *)0xA0000L, 0x11, 0x40);  /* text: 0x11 */

    /* 5. Read back VRAM */
    serial_puts("VRAM AFTER FILL:\r\n");
    dump_vram((volatile uint8_t *)0xA8000L, "  B[0xA8000]: ", 8);
    dump_vram((volatile uint8_t *)0xB0000L, "  R[0xB0000]: ", 8);
    dump_vram((volatile uint8_t *)0xB8000L, "  G[0xB8000]: ", 8);
    dump_vram((volatile uint8_t *)0xA0000L, "  T[0xA0000]: ", 8);
    dump_vram((volatile uint8_t *)0xA4000L, "  T[0xA4000]: ", 8);

    /* 6. Verify all 3 planes */
    {
        int bok=1, rok=1, gok=1;
        for (i=0; i<0x40; i++) {
            if (((volatile uint8_t *)0xA8000L)[i] != 0xAA) bok=0;
            if (((volatile uint8_t *)0xB0000L)[i] != 0x55) rok=0;
            if (((volatile uint8_t *)0xB8000L)[i] != 0xCC) gok=0;
        }
        serial_puts("VERIFY:\r\n");
        serial_puts(bok?"  B OK\r\n":"  B FAIL\r\n");
        serial_puts(rok?"  R OK\r\n":"  R FAIL\r\n");
        serial_puts(gok?"  G OK\r\n":"  G FAIL\r\n");
    }

    /* 7. More GDC state - try reading various registers */
    {
        /* Write mode1 register command to be able to read it back */
        uint8_t m1;
        outp(0xA0, 0x0F);  /* dummy write param */
        outp(0xA2, 0x0D);  /* START command */
        m1 = inp(0xA2);
        dump_reg("  mode1(after cmd)=", m1);
        
        /* Try reading 0xA0 */
        dump_reg("  inp(0xA0)=", inp(0xA0));
    }

    serial_puts("=== DIAG DONE ===\r\n");

    for (;;) {}
    return 0;
}
