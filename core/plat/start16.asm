; Naiz engine DPMI startup — goes to 32-bit PM and calls _main
; Reference: love ex×××× DPMI startup sequence
; Uses VEM486.EXE as DPMI host (loaded via CONFIG.SYS)

    .386
    .model small
    .dosseg
    .stack 4096

    EXTERN main_:BYTE

    .code

start16:
    ; Release excess DOS memory
    mov  ax, @data
    mov  ds, ax
    mov  bx, ss
    sub  bx, ax
    shl  bx, 4
    add  bx, sp
    mov  ss, ax
    mov  sp, bx

    mov  ax, ss
    mov  cx, es
    sub  ax, cx
    mov  bx, sp
    shr  bx, 4
    inc  bx
    add  bx, ax
    mov  ah, 4Ah
    int  21h

    ; Detect DPMI host
    mov  ax, 1687h
    int  2Fh
    and  ax, ax
    jnz  nohost
    push es
    push di
    and  si, si
    jz   nomemneeded
    mov  bx, si
    mov  ah, 48h
    int  21h
    jc   nomem
    mov  es, ax

nomemneeded:
    mov  bp, sp
    mov  ax, 0001
    call far ptr [bp]
    jc   initfailed

    ; Create 32-bit code segment and jump to C main
    mov  cx, 1
    mov  ax, 0
    int  31h
    mov  bx, ax
    mov  cx, @code
    mov  dx, cx
    shl  dx, 4
    shr  cx, 12
    mov  ax, 7
    int  31h
    mov  dx, -1
    mov  cx, 0
    mov  ax, 8
    int  31h
    mov  cx, cs
    lar  cx, cx
    shr  cx, 8
    or   ch, 40h
    mov  ax, 9
    int  31h
    push ebx
    push offset main_
    retd

nohost:
    mov  dx, offset msg_no_dpmi
    jmp  error_exit
nomem:
    mov  dx, offset msg_no_mem
    jmp  error_exit
initfailed:
    mov  dx, offset msg_init_fail
error_exit:
    push cs
    pop  ds
    mov  ah, 9
    int  21h
    mov  ax, 4C00h
    int  21h

msg_no_dpmi    db "no DPMI host",13,10,'$'
msg_no_mem     db "not enough DOS memory",13,10,'$'
msg_init_fail  db "DPMI init failed",13,10,'$'

    end start16
