.code16
.globl _start
_start:
    mov %ss, %ax
    mov %ax, %ds
    mov %ax, %es

    /* Zero BSS */
    movw $_bss_start, %di
    movw $_bss_end, %cx
    subw %di, %cx
    xorw %ax, %ax
    cld
    rep stosb

    /* Set stack pointer */
    movw $_stack_top, %sp

    call main
    movb $0x4C, %ah
    int $0x21
