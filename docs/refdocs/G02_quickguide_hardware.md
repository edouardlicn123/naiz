# NEC PC-9800 Quick Guide Hardware 集成

> **来源**: 多个 Wayback Machine 归档 + 公开文档
> **原文编码**: 日文 Shift-JIS

---

本文件整合了 PC-9800 Quick Guide Hardware 系列文档的关键内容，涵盖从 PC-9801 到 PC-9821 系列的硬件差异、I/O 映射、系统内存布局。

## 硬件世代概览

| 机种 | CPU | 图形系统 | 备注 |
|------|-----|---------|------|
| PC-9801 | 8086/286 | GDC+GRCG | 初代, 8色/16色 |
| PC-9801VX | 286/386 | GRCG | 16色标准 |
| PC-9821 | 386+/486 | EGC | 256色选项 |
| PC-9821Ce/Cx | 486/Pentium | PEGC | 内藏 256色 |

## I/O 端口兼容性

### 共通端口

| 端口 | 功能 | 备注 |
|------|------|------|
| 00h-1Fh | DMA 控制器 | i8237A 相当 |
| 20h-3Fh | 中断控制器 | i8259A 相当 |
| 40h-5Fh | 计时器 | i8253 相当 |
| 60h-6Fh | TEXT GDC + 模式 | 全机种共通 |
| 70h-7Fh | 键盘 + GRCG | 全机种共通 |
| A0h-AFh | GRAPHIC GDC | 全机种共通 |
| 80h-8Fh | NMI 控制 + DMA 页面 | 全机种共通 |

### 机种固有

| 机种 | 端口 | 功能 |
|------|------|------|
| VX 以降 | 6Ah.4 | GRCG/EGC 切换 |
| 9821 | 04A0h-04AFh | EGC 寄存器 |
| 9821 | 9A0h-9AFh | 扩展显示控制 |
| Ce/Cx | 0B0h-0BFh | PCI 配置 |

## GDC/CRTC 差异

- PC-9801: μPD7220 (GDC) + μPD7228 (CRTC), 2.5MHz/5MHz
- PC-9821: μPD7220A (GDC 兼容), 5MHz 固定
- 高分辨率: 9821 的 31KHz 模式需要不同 CRTC 设定

## 附录: 有用的汇编技巧

### 端口 I/O 延迟

```asm
; I/O 延迟 (PC-9821 需要)
out 0xA0, al
jmp $+2  ; I/O 延迟
```

### 平面回転

```asm
; 4平面同时写入 1 点 (通过 GRCG RMW 模式)
mov dx, 0x7c
mov al, 0x82  ; GRCG enable + RMW mode
out dx, al
; 然后写入任意 VRAM 地址即可
```
