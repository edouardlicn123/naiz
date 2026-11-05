# PC-98 系统内存映射

> 来源：http://radioc.web.fc2.com/column/pc98bas/pc98memmap_en.htm
> 详细 BIOS 数据区：https://www.webtech.co.jp/company/doc/undocumented_mem/memsys.txt
> DOS 工作区：https://www.webtech.co.jp/company/doc/undocumented_mem/memdos.txt

## 系统内存布局

| 地址范围 | 大小 | 类型 | 描述 |
|----------|------|------|------|
| 000000–0003FF | 1KB | Main RAM | IVT（中断向量表） |
| 000400–0005FF | 512B | Main RAM | BDA（BIOS 数据区） |
| 000600–07FFFF | 510KB | Main RAM | 常规内存 |
| 080000–09FFFF | 128KB | Main RAM | 常规内存或外部总线 |
| 0A0000–0A3FFF | 16KB | Sub RAM | **文本 VRAM**（字符码 + 属性） |
| 0A4000–0A4FFF | 4KB | Sub RAM | **CG 窗口**（字符生成器窗口，读 font ROM） |
| 0A5000–0A7FFF | 12KB | — | 保留 |
| 0A8000–0BFFFF | 96KB | Sub RAM | **图形 VRAM**（Plane 0, 1, 2，每平面 32KB） |
| 0C0000–0C3FFF | 16KB | ROM | 用户 ROM 区 |
| 0C4000–0DFFFF | 112KB | ROM | 系统 ROM 区 |
| 0E0000–0E7FFF | 32KB | Sub RAM | **图形 VRAM**（Plane 3） |
| 0E8000–0FFFFF | 96KB | ROM | 系统 ROM（BIOS） |
| 100000–EFFFFF | 14MB | Main RAM | 保护模式内存 |
| F00000–F9FFFF | 640KB | — | 保留 |
| FA0000–FFFFFF | 384KB | — | 镜像 0A0000–0FFFFF |
| 1000000–∞ | 可变 | Main RAM | 保护模式内存（因机型而异） |
| FFF00000–FFFFFFFF | 1MB | — | 镜像 F00000–FFFFFF（部分机型） |

## 文本 VRAM 详细布局

文本 VRAM 位于 **A0000h–A3FFFh**（16KB），分为两个区域：

| 区域 | 地址 | 描述 |
|------|------|------|
| 字符码 | A0000h–A1FFFh | 每个字符 2 字节：第 1 字节 JIS 第 1 字节，第 2 字节 JIS 第 2 字节 |
| 属性 | A2000h–A3FFFh | 每个字符 2 字节属性 |
| CG 窗口 | A4000h–A4FFFh | 4KB，用于读取 CG 字体 ROM |

80 列 × 25 行 = 2000 字符/页，每字符占 2 字节 → 每页 4000 字节

## 图形 VRAM（G-VRAM）详细布局

标准 16 色模式（4 平面 × 32KB = 128KB）：

| 平面 | 地址范围 | 大小 | 描述 |
|------|----------|------|------|
| Plane 0 (B) | A8000h–AFFFFh | 32KB | 蓝色位 |
| Plane 1 (R) | B0000h–B7FFFh | 32KB | 红色位 |
| Plane 2 (G) | B8000h–BFFFFh | 32KB | 绿色位 |
| Plane 3 (I) | E0000h–E7FFFh | 32KB | 亮度位 |

每平面 32KB = 640×400 / 8（每像素 1 bit）= 32,000 字节（略有富余）

8 色模式只使用 Plane 0–2。

**可选第 2 页**：通过 I/O A4h/A6h 切换显示/绘制页面。第 2 页的 VRAM 需要额外 128KB（位于正常地址之上）。

## 扩展卡默认内存地址

| 地址范围 | 大小 | 扩展卡 |
|----------|------|--------|
| C4000–C5FFF | 8KB | BRANCH4680 (PC-98XL2-04) |
| C8000–C9FFF | 8KB | BRANCH4680 (PC-9867) |
| CA000–CBFFF | 8KB | 通信适配器 (PC-9866, PC-9801-59) |
| CC000–CDFFF | 8KB | 声音 (PC-9801-26) |
| D0000–D3FFF | 16KB | RS-232C (PC-9861), BRANCH4670 (PC-9864) |
| D2000–D3FFF | 8KB | BRANCH4680, R8100 |
| D4000–D5FFF | 8KB | GP-IB (PC-9801-29) |
| D6000–D6FFF | 4KB | 640KB FD I/F (PC-9801-08,-09) |
| D7000–D7FFF | 4KB | 1MB FD I/F, SASI HD I/F |
| D8000–DBFFF | 16KB | IDE HD I/F, RAM drive |
| DC000–DCFFF | 4KB | SCSI I/F (PC-9801-55,-92) |
| DC000–DDFFF | 8KB | SCSI I/F (PC-9801-50) |

## 中断向量表

标准 IVT 位于 0000:0000–0000:03FFh。

| INT # | 功能 |
|-------|------|
| 00h | 除以零 |
| 05h | COPY 键 |
| 06h | STOP 键 |
| 07h | 间隔定时器 |
| 08h | 系统定时器 |
| 09h | 键盘 |
| 0Ah | CRTV（V-Sync） |
| 0Bh–0Fh | 扩展总线 INT0–INT2 |
| 10h | 打印机 / FPU |
| 11h–16h | 扩展总线 INT3–INT6 |
| 18h | KB / CRT BIOS |
| 19h | RS-232C BIOS |
| 1Ah | 打印机 BIOS |
| 1Bh | 磁盘 BIOS |
| 1Ch | 日历 BIOS |
| 1Dh | 保留 |
| 1Eh | 内建 BASIC |
| 1Fh | 保留（H98/NOTE 系统） |
| 20h–3Fh | 系统保留 |
| 40h–7Fh | 用户可用 |

## IRQ 分配

| IRQ | 主 8259A | IRQ | 从 8259A |
|-----|----------|-----|----------|
| 0 | 系统定时器 | 8 | 打印机（V30）/ FPU（286） |
| 1 | 键盘 | 9 | 扩展总线 INT3 |
| 2 | CRTV (V-Sync) | 10 | 扩展总线 INT41 |
| 3 | 扩展总线 INT0 | 11 | 扩展总线 INT42 |
| 4 | RS-232C | 12 | 扩展总线 INT5 |
| 5 | 扩展总线 INT1 | 13 | 扩展总线 INT6 |
| 6 | 扩展总线 INT2 | 14 | FPU（V30）/ 未使用（286） |
| 7 | 从 8259A | 15 | 系统定时器 |

### 扩展卡 IRQ 占用表

| 扩展卡 | INT0 | INT1 | INT2 | INT3 | INT41 | INT42 | INT5 | INT6 |
|--------|------|------|------|------|-------|-------|------|------|
| 传真 (PC-9801-37) | o | x | x | — | — | — | x | — |
| RS-232C 2ch (PC-9861) | o | x | x | x | — | — | — | — |
| 通信适配器 (PC-9862) | o | — | — | — | x | x | x | x |
| 网络 (PC-9864) | o | — | — | — | x | x | x | x |
| 触摸板 (PC-9873) | o | x | — | — | — | — | x | x |
| R8100 (PC-9801-88) | x | o | x | x | x | x | x | x |
| 声音 (PC-9801-26) | x | — | — | — | x | x | o | x |
| GP-IB (PC-9801-29) | x | — | — | — | x | x | o | x |
| SASI (PC-9801-27) | — | — | — | x | — | — | — | — |
| SCSI (PC-9801-50,-55) | — | — | — | x | — | — | — | — |
| 640KB FD (PC-9801-09) | — | — | — | — | x | — | — | — |
| 1MB FD (PC-9801-15) | — | — | — | — | — | x | — | — |
| 鼠标 (PC-9871) | x | x | x | x | x | x | x | o |
| 86 音源 (PC-9801-86) | x | — | — | — | x | x | o | — |

o = 默认占用(通常)，x = 可选，— = 未使用

## BIOS 数据区（BDA）关键地址

| 地址 | 大小 | 描述 |
|------|------|------|
| 0000:0400h | BYTE | BIOS_FLAG2：RAM 盘、CPU 类型、Resume 等标志位 |
| 0000:0401h | BYTE | EXPMMSZ：可用保护内存总量（单位 128KB） |
| 0000:0402h | BYTE | SYS_SEL：引导选择器，Shift/Ctrl/Grph 键状态 |
| 0000:0495h | BYTE | GRCG 状态记录 |
| 0000:0496–99h | 4 BYTEs | GRCG Tile 寄存器备份 |
| 0000:0501h | BYTE | CPU 速度 + 内存大小位 |
| 0000:0502–053Ah | — | 键盘缓冲区（详细见键盘文档） |
| 0000:054Ch | BYTE | 图形系统类型标志 |
| 0000:054Dh | BYTE | 扩展图形标志（EGC, hires, 256 色等） |

完整 256 字节 BDA 参见 UNDOCUMENTED Vol.2 `memsys.txt`。
