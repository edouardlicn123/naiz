#/*
# * 来源项目：MHVNVisualNovelEngine
# * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
# * 许可证：   MIT License
# */
#
# VSync interrupt handler

.intel_syntax noprefix
.code16
.text

	.p2align 2
	.globl	vsync_isr
vsync_isr:
	push ax
	xor  al, al
	out  0x64, al
	movb ss:vsynced, 1
	push ds
	mov  ax, ss
	mov  ds, ax
	inc  word ptr vsync_counter
	pop  ds
	mov  al, 0x20
	out  0x00, al
	pop  ax
	iret

.bss
	.globl	vsynced
	vsynced: .skip 1,0
	.globl	vsync_counter
	vsync_counter: .skip 2,0
