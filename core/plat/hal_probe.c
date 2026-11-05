/*
 * hal_probe.c — HAL PC-98 interrupt-capability probes
 *
 * Split out of hal_pc98.c (devdoc 200 §12.2): this code only takes part in
 * NAIZ_IRQ_PROBE diagnostic builds and is independent of the runtime
 * platform implementation.
 *
 * See: docs/ — HAL architecture design
 */
#include "hal.h"
#include <i86.h>

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
 * the IRQ2 route (devdoc 163 §5 C2) is viable on this platform; zero hits
 * means fall back to the OPNA Timer-B route (F04). */
void hal_irq_probe_run(void)
{
    unsigned long t0;
    unsigned long hits = 0, samples = 0;
    unsigned long imr;

    outb(0x64, 0x00);        /* arm/wake vsync IRQ (C01 §VSYNC interrupt) */
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

#if NAIZ_IRQ_PROBE
/*
 * devdoc 164 phase 0: DPMI interrupt-capability probe (read-only).
 *
 * Before an ISR can be written the toolchain must be able to hook a hardware
 * IRQ from 32-bit protected mode.  Open Watcom ships no dpmi.h (G08 §2 flags
 * the Watcom equivalent of the DJGPP `_go32_dpmi_*` API as unmapped), so this
 * probe queries the DPMI host directly via INT 31h:
 *
 *   AX=0400  -> DPMI version (AH=major/AL=minor), flags in BX
 *               (BX bit0 = 32-bit host, bit2 = virtual memory)
 *               CL = CPU type, DH/DL = master/slave PIC base vectors
 *   AX=0204  -> get the protected-mode vector for a real-mode vector number
 *   AX=0600  -> lock a linear region (answers if the service exists)
 *
 * Nothing is written: no vector is set, no PIC mask is touched.  The verdict
 * decides between Phase 1 (ISR) and the fallback vclock catch-up (devdoc 163
 * §4 B3).  IRQ3 (OPNA Timer-B, F04 §6) maps to real-mode INT 0Bh (vector base
 * 0x08 + 3, G01:87); INT 0Ah is probed too as the vsync cross-check.
 *
 * devdoc 164 §4.2: the 32-bit-host flag lives in BX bit0, NOT in CL -- CL is
 * the CPU type (02=286/03=386/04=486).  The earlier probe read ECX bit0, which
 * is just CL bit0 (even CPU type => 0) and carried no signal.  The byte verb we
 * report now is (BX & 0x05): bit0 = 32-bit host, bit2 = virtual memory.
 */
void hal_dpmi_probe_run(void)
{
    union REGS r;
    unsigned long v0b, v0a;
    int ver_h, ver_l, flags, cpu, pic_hi, pic_lo;
    int cf_b, cf_a;
    unsigned long lock_off = 0;
    int lock_ok;

    /* AX=0400: DPMI version.  AH=major, AL=minor; BX=flags, CL=CPU type,
     * DH/DL=master/slave PIC base vectors. */
    r.x.eax = 0x0400;
    int386(0x31, &r, &r);
    ver_h = (int)((r.x.eax >> 8) & 0xFF);
    ver_l = (int)(r.x.eax & 0xFF);
    flags = (int)(r.x.ebx & 0x0005);   /* BX bit0 = 32-bit host, bit2 = VM */
    cpu   = (int)(r.x.ecx & 0xFF);     /* CL = processor type */
    pic_hi = (int)((r.x.edx >> 8) & 0xFF);   /* DH = master PIC base vector */
    pic_lo = (int)(r.x.edx & 0xFF);          /* DL = slave PIC base vector */

    /* AX=0204: read PM vector.  Input: BL=vector number, returns CX:EDX=sel:off.
     * Carry clear = success; off != 0 proves a PM vector space exists. */
    r.x.eax = 0x0204;
    r.h.bl = 0x0B;
    r.x.edx = 0;
    r.x.ecx = 0;
    cf_b = (int386(0x31, &r, &r) & INTR_CF) ? 1 : 0;
    v0b = ((unsigned long)r.x.ecx << 16) | (r.x.edx & 0xFFFF);

    r.x.eax = 0x0204;
    r.h.bl = 0x0A;
    r.x.edx = 0;
    r.x.ecx = 0;
    cf_a = (int386(0x31, &r, &r) & INTR_CF) ? 1 : 0;
    v0a = ((unsigned long)r.x.ecx << 16) | (r.x.edx & 0xFFFF);

    /* AX=0600: lock a linear region.  Asking about a 1-page region at the
     * current code just tests whether the API answers; the lock request is
     * not expected to succeed for an arbitrary address and we only report
     * whether the call was serviced (no carry = service present). */
    r.x.eax = 0x0600;
    r.x.ecx = 0x00000000UL;   /* linear address (probe only) */
    r.x.ebx = 0x1000;         /* 4 KiB */
    r.x.esi = 0x00000000UL;   /* high 32 bits = 0 */
    r.x.edi = 0x00000000UL;
    lock_ok = (int386(0x31, &r, &r) == 0);
    lock_off = r.x.ebx;

    hal_logf("[DPMP] ver=%d.%d flags=%d cpu=%d pic=%02x/%02x cfB=%d cfA=%d vec0B=%lx vec0A=%lx lock_ok=%d lock_off=%lx\r\n",
             ver_h, ver_l, flags, cpu, pic_hi, pic_lo, cf_b, cf_a, v0b, v0a, lock_ok, lock_off);
}
#endif /* NAIZ_IRQ_PROBE */
