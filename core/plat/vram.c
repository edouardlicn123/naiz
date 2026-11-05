/*
 * vram.c — GDC VRAM 的 DPMI 线性地址映射 (NOT COMPILED by default)
 *
 * 本模块使用 DPMI INT 31h AX=0800h 将 GDC 物理 VRAM 映射到 LDT 线性空间。
 * 当前引擎使用 PEGC bank-switching (render.c) 方案访问 VRAM，此文件仅
 * 保留作为 DPMI 映射方案的参考实现。如需启用，在编译时定义 VRAM_DPMI_MAP。
 *
 * 参考：devdocs/0.1版开发文档总结.html#doc-09 — VRAM 调查报告
 */
#ifdef VRAM_DPMI_MAP

static unsigned char *vram_base;

void *vram_init(void)
{
    unsigned long linear;

    __asm {
        mov  eax, 0x0800
        mov  ebx, 0x000A8000
        mov  ecx, 0x00000000
        mov  esi, 5
        mov  edi, 0
        int  0x31
        jc   fail
        movzx eax, bx
        shl   eax, 16
        movzx edx, cx
        or    eax, edx
        mov   linear, eax
        jmp   done
    fail:
        mov   linear, 0
    done:
    }

    if (!linear) { vram_base = 0; return 0; }
    vram_base = (unsigned char *)linear;
    return vram_base;
}

unsigned char *vram_plane(int n)
{
    if (!vram_base) return 0;
    return vram_base + (unsigned long)n * 0x8000;
}

#endif /* VRAM_DPMI_MAP */
