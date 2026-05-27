# Fix Demo Blue Screen — 6 Issues

## Fix 1: CRT0 — set DS/ES to DGROUP
**File:** `core/crt0.s`

Replace:
```asm
mov %dx, %ds
mov %dx, %es
```
With:
```asm
mov $__seg_dgroup, %ax
mov %ax, %ds
mov %ax, %es
```

Why: DX holds the PSP segment at entry, not the program's data segment. Using `__seg_dgroup` (ia16-elf linker symbol) correctly initializes DS/ES for global variable access.

---

## Fix 2: AUTOEXEC.BAT — drive letter
**File:** `tools/ref_config/AUTOEXEC.BAT`

Replace `A:\demo-A1\ENGINE.EXE` with `C:\demo-A1\ENGINE.EXE`

Why: HDI boots as C:, not A:.

---

## Fix 3: gdc_interrupt_reset() inline asm
**File:** `core/plat/pc98/pc98_gdc.h:131-134`

Replace:
```c
__asm volatile ("outb %al, $0x64");
```
With:
```c
__asm volatile ("outb %%al, $0x64" : : "a" (0));
```

Why: The original asm has no input constraint for AL, so undefined garbage is written to port 0x64.

---

## Fix 4: VSync ISR installation
**File:** `core/plat/pc98/hal_pc98.c`

### 4a. Implement `hal_interrupt_set()`
Replace stub with actual IVT write via `hal_set_isr()` from `x86interrupt.h`.
Also implement `hal_interrupt_get()`.

### 4b. Implement `hal_vsync_enable()`
Unmask VSync IRQ in PIC, install ISR vector.

### 4c. Update `hal_video_init()`
Install `vsync_isr` at vector `0x0A`, unmask VSync in PIC, call `gdc_interrupt_reset()`, set `vsynced = 1`.

---

## Fix 5: Complete GDC display initialization
**File:** `core/plat/pc98/hal_pc98.c`

Update `hal_video_init()` to the full initialization sequence:

```c
void hal_video_init(void)
{
    hal_cli();

    // Set up display timing
    gdc_set_display_mode(640, 400, 440);

    // Start text GDC, stop graphics GDC
    gdc_stop_graphics();
    gdc_start_text();
    gdc_set_graphics_line_scale(1);

    // Configure display
    gdc_set_mode1(GDC_MODE1_LINEDOUBLE_ON);
    gdc_set_mode1(GDC_MODE1_COLOUR);
    gdc_set_mode2(GDC_MODE2_16COLOURS);
    gdc_set_display_page(0);
    gdc_set_draw_page(0);
    gdc_set_display_region(0, 400);
    gdc_scroll_simple_graphics(0);

    // VSync interrupt setup
    hal_interrupt_set(INTERRUPT_VECTOR_VSYNC, vsync_isr);
    pic_enable_irqs(INTERRUPT_MASK_VSYNC);
    gdc_interrupt_reset();
    vsynced = 1;

    hal_sti();
}
```

---

## Fix 6: Keyboard — use BIOS key status array
**File:** `core/plat/pc98/hal_pc98.c`

Replace `hal_input_state()`:

```c
int hal_input_state(int scancode)
{
    unsigned char __far *key_status = (unsigned char __far *)0x052A;
    int byte = scancode >> 3;
    int bit = scancode & 7;
    return (key_status[byte] >> bit) & 1;
}
```

Why: Direct port I/O (ports 0x41/0x43) conflicts with the BIOS keyboard ISR (INT 09h), which reads from the same FIFO. The BIOS maintains a key status bit array at `0x052A` — reading from there is reliable and doesn't conflict.

**File:** `projects/demo-A1/main.c`

Add `#include "pc98_keyboard.h"` and change:
```c
if (hal_input_state(0x01)) break;
```
To:
```c
if (hal_input_state(KC_ESC)) break;
```

`KC_ESC = 0x00` maps to bit 0 of byte 0 in the key status array — this is the correct ESC bit position.

---

## New includes needed in hal_pc98.c

After changes, `hal_pc98.c` needs these additional includes:
```c
#include "pc98_interrupt.h"
#include "x86interrupt.h"
#include "pc98_keyboard.h"
```
`pc98_gdc.h` is already included.

---

## Verification

After applying all fixes:
```bash
cd projects/demo-A1 && make clean && make
../..//test_hdi.sh demo-A1
```
