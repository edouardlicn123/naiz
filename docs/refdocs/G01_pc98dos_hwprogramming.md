# PC98 DOS プログラミング ハードウェアバリバリ編

> **来源**: [MPC (Muroran Programming Club)](https://web.archive.org/web/20000709114152/http://www2.muroran-it.ac.jp/circle/mpc/pc98dos/title.html)
> **作者**: 山西, 野田, 飯田, 宇都宮
> **版本**: Ver 1.06 (1998/12/20)
> **编码**: 日文 Shift-JIS（正文为 ASCII 转写，代码片段完整可用）

---

## 目录总览

| Part | 主题 | 内容 |
|------|------|------|
| 1 | DOS Function Call | 从C调用软中断、主要DOS功能调用介绍 |
| - | 中断 | 硬件中断的处理方法 |
| 2 | 输入设备 | KEYBOARD, MOUSE |
| 3 | 内存管理 | EMS, XMS, 系统内存区域 |
| 4 | **图形 (GDC/GRCG/EGC/256)** | TEXT VRAM, KCG, GDC, 16色图形, GRCG & EGC, 256MODE |
| 5 | 声音 | CDDA (MSCDEX), PCM (86音源) |

---

## PART 1: DOS Function Call

### (1) 从C语言调用软件中断

使用 `intdos()` / `intdosx()` / `int86()` / `int86x()` 调用 DOS/BIOS 中断。

```c
#include <dos.h>

union REGS inregs, outregs;
struct SREGS segregs;

inregs.h.ah = 0x09;          /* 功能号 */
inregs.x.dx = (unsigned int)&SampleText[0];
segread(&segregs);
intdosx(&inregs, &outregs, &segregs);
```

### (2) 主要 DOS Function Call 介绍

**文件访问:**

| 功能 | Function No. | 参数 | 返回 |
|------|-------------|------|------|
| File Open | 3Dh | AL=Access, DS:DX=Filename | AX=Handle |
| File Create | 3Ch / 5Bh | CX=Attr, DS:DX=Filename | AX=Handle |
| File Close | 3Eh | BX=Handle | CF=0 OK |
| File Read | 3Fh | CX=Bytes, DS:DX=Buffer, BX=Handle | AX=Read Bytes |
| File Write | 40h | CX=Bytes, DS:DX=Buffer, BX=Handle | AX=Written |
| Move Pointer | 42h | AL=Origin, CX:DX=Size, BX=Handle | DX:AX=New Pos |
| File Delete | 41h | DS:DX=Filename | CF=0 OK |
| Directory Create | 39h | DS:DX=Path | CF=0 OK |
| Directory Delete | 3Ah | DS:DX=Path | CF=0 OK |
| Directory Change | 3Bh | DS:DX=Path | CF=0 OK |

**内存管理:**

| 功能 | Function No. | 参数 | 返回 |
|------|-------------|------|------|
| Allocate Memory | 48h | BX=Size (Paragraph) | AX=Segment |
| Free Memory | 49h | ES=Segment | CF=0 OK |
| Resize Memory | 4Ah | ES=Segment, BX=New Size | CF=0 OK |

**进程控制:**

| 功能 | Function No. | 参数 | 返回 |
|------|-------------|------|------|
| Child Execute | 4Bh | ES:BX=Param, DS:DX=Filename, AL=0/3 | CF=0 OK |
| Get Return Code | 4Dh | — | AX=Return Code |
| Keep (TSR) | 31h | AL=Code, DX=Size | — |

### (3) 硬件中断的处理方法

使用 INT 18h (PC-98 BIOS) 和 INT 21h (DOS)。8259A PIC 控制:

- Master PIC: 端口 00h (ICW1/OCW2/OCW3), 02h (ICW2-4/OCW1)
- Slave PIC: 端口 08h (ICW1/OCW2/OCW3), 0Ah (ICW2-4/OCW1)
- IMR (中断屏蔽): 端口 02h (Master), 0Ah (Slave)

关键结构:
- IMR: 中断屏蔽寄存器 (1=禁用)
- IRR: 中断请求寄存器
- ISR: 中断服务寄存器

定时器中断是 IRQ 0 (INT 08h)。中断处理步骤:
1. 禁用外部中断
2. 保存中断向量表
3. 设置新处理函数
4. 配置 PIT 定时器
5. 清除 IMR 对应位
6. 启用中断

---

## PART 2: 输入设备

### (1) KEYBOARD

PC-98 键盘使用 PD8251 串行接口。扫描码格式:

| D7 | D6-D0 |
|----|-------|
| Make(0)/Break(1) | 键盘位置码 |

**键盘 BIOS (INT 18h):**

| 功能 | AH | 参数 | 返回 |
|------|----|------|------|
| 读键(等待) | 00h | — | AX=扫描码+数据 |
| 读键(不等待) | 01h | — | AX=数据, BH=状态 |
| 获取Shift键 | 02h | — | AL=Shift状态位图 |
| 键盘接口初始化 | 03h | — | — |
| 读键盘矩阵 | 04h | AL=组号 | AH=位图 |
| 读键(移动指针) | 05h | — | AX=数据, BH=状态 |

**键盘矩阵地址:** `0000:052A` ~ `0000:0539` (16字节, 系统内存区域)

Shift 状态:

| D7 | D6 | D5 | D4 | D3 | D2 | D1 | D0 |
|----|----|----|----|----|----|----|----|
| — | — | — | CTRL | GRPH | KANA | CAPS | SHIFT |

**键盘数据缓冲:** `0000:0502` (32字节环形缓冲)
- 头指针: `0000:0524`
- 尾指针: `0000:0526`
- 缓冲字符数: `0000:0528`

### (2) MOUSE

使用 INT 33h (Microsoft Mouse Driver):

| 功能 | AX | 参数 | 返回 |
|------|----|------|------|
| 初始化 | 00h | — | AX=状态, BX=按钮数 |
| 光标显示 | 01h | — | — |
| 光标隐藏 | 02h | — | — |
| 获取状态 | 03h | — | BX=按钮, CX=X, DX=Y |
| 设置位置 | 04h | CX=X, DX=Y | — |
| 按下信息 | 05h | BX=按钮 | AX=状态, CX=X, DX=Y |
| 抬起信息 | 06h | BX=按钮 | AX=状态, CX=X, DX=Y |
| X范围设置 | 07h | CX=Min, DX=Max | — |
| Y范围设置 | 08h | CX=Min, DX=Max | — |
| 光标形状 | 09h | BX,CX=热点, ES:DX=数据 | — |
| 移动量获取 | 0Bh | — | CX=X移动, DX=Y移动 |
| 用户子程序 | 0Ch | CX=条件, ES:DX=地址 | — |
| 米奇比设定 | 0Fh | CX=X, DX=Y | — |

**鼠标 I/O (直接硬件访问):**

| 端口 | 功能 |
|------|------|
| 7FD9h | 鼠标状态读取 (按钮+X/Y移动量) |
| 7FDBh | 模式端口B (DIP开关) |
| 7FDDh | 模式端口C (HC/SX/SH/IN控制) |

计数器读取步骤:
1. HC=1 锁定计数器
2. 设置 SXY/SHL 选择轴和半字节
3. 从 7FD9h Bit3-0 读取 4位
4. HC=0 清除计数器

---

## PART 3: 内存管理

### (1) EMS (Expanded Memory Specification)

使用 INT 67h (EMM):

| 功能 | AH | 参数 | 返回 |
|------|----|------|------|
| 获取页帧段 | 41h | — | BX=段地址 |
| 获取页数 | 42h | — | BX=未分配, DX=总页 |
| 分配页 | 43h | BX=页数 | DX=句柄 |
| 映射页 | 44h | AL=逻辑页, BX=物理页, DX=句柄 | — |
| 释放句柄 | 45h | DX=句柄 | — |
| 获取版本 | 46h | — | AL=版本 |

EMS 驱动检测: 检查 INT 67h 向量 +0Ah 处字符串 "EMMXXXX0"。

### (2) XMS (eXtended Memory Specification)

使用 INT 2Fh:

| 功能 | AX | 返回 |
|------|----|------|
| 驱动存在检测 | 4300h | AL=80h 存在 |
| 获取调用地址 | 4310h | ES:BX=调用地址 |

XMS 函数 (通过 FAR CALL 调用):

| AH | 功能 |
|----|------|
| 00h | 获取版本 |
| 01h | 请求 HMA |
| 02h | 释放 HMA |
| 08h | 查询 EMB 大小 |
| 09h | 分配 EMB |
| 0Ah | 释放 EMB |
| 0Bh | EMB 移动 |
| 10h | 分配 UMB |

---

## PART 4: 图形 (GDC/GRCG/EGC/256)

### (1) TEXT VRAM

PC-98 文本 VRAM 由字符码区和属性区组成:

**字符码区:** A0000h ~ A1FFFh (80列×25行 = 2000字符, 每字符2字节)

**属性区:** A2000h ~ A3FFFh (属性字节)

半角字符 (2字节):

| N+1 | N |
|-----|---|
| ANK Code | 00h |

全角字符 (4字节):

| N | N+1 | N+2 | N+3 |
|---|---|---|---|
| JIS高位-20h | JIS低位 | JIS高位+60h | JIS低位 |

属性字节格式:

| D7 | D6 | D5 | D4 | D3 | D2 | D1 | D0 |
|----|----|----|----|----|----|----|----|
| G | R | B | VL | UL | RV | BL | ST |

- ST: 显示(0)/不显示(1)
- BL: 闪烁
- RV: 反转
- UL: 下划线
- VL: 垂直行
- G/R/B: 字符颜色 (蓝/红/绿)

### (2) KCG (汉字模式访问)

通过 I/O 端口读取字体模式:

| 端口 | 功能 |
|------|------|
| A1h | 汉字码第2字节指定 |
| A3h | 汉字码第1字节指定 (-20h) |
| A5h | 字体读取位置指定 (L/R + 行计数器) |
| A9h | 字体数据读/写 |

字体读取需要进入 KCG 访问模式，可通过：
1. 代码访问模式（GDC 设置）
2. KCG 访问模式（VSYNC 自动切换）

CG Window (VM 以上机型): A400:0000 ~ A400:001Fh (32字节)

### (3) GDC (图形显示控制器)

**I/O 端口:**

| 端口 | 读 | 写 |
|------|----|----|
| 60h | TEXT GDC 状态 | TEXT GDC 命令 |
| 62h | TEXT GDC FIFO | TEXT GDC 数据 |
| A0h | GRAPHIC GDC 状态 | GRAPHIC GDC 命令 |
| A2h | GRAPHIC GDC FIFO | GRAPHIC GDC 数据 |
| 64h | — | CRT 中断复位 |
| 68h | — | 模式触发器 1 设置 |
| 6Ah | — | 模式触发器 2 设置 |
| 6Ch | — | 同步信号设置 |
| A4h | — | 图形显示页面指定 |
| A6h | — | 图形绘图页面指定 |
| A8h | — | 调色板号指定 |
| AAh | — | 绿色亮度设置 |
| ACh | — | 红色亮度设置 |
| AEh | — | 蓝色亮度设置 |
| 9A0h | — | 读取端口设置 |
| 9A8h | — | 显示时钟设置 |

**模式触发器 1 (68h):**

| 值 | 含义 |
|----|------|
| 00h/01h | ATR4(文本)/ATR4(图形) |
| 02h/03h | 图显示/文显示 |
| 04h/05h | TEXT 80列/40列 |
| 06h/07h | ANK 6x8/7x13 |
| 08h/09h | 400线/200线 |
| 0Ah/0Bh | 图形/KCG 显示 |
| 0Ch/0Dh | 行重复禁止/允许 |
| 0Eh/0Fh | 显示停止/显示 |

**模式触发器 2 (6Ah):**

| 值 | 含义 |
|----|------|
| 00h/01h | 8色/16色模式 |
| 04h/05h | GRCG/EGC 模式 |
| 06h/07h | 扩展模式切换不可/可 |
| 20h/21h | 标准/扩展图形模式 |
| 40h/41h | CRT/模拟 RGB 模式 |
| 68h/69h | 显示页独立/连续 (256色) |
| 83h/85h/84h | GDC 5MHz/2.5MHz |

**16色图形模式初始化示例:**
```c
outp(0x68, 0x02); /* 彩色图形模式 */
outp(0x68, 0x08); /* 高分辨率 */
outp(0x6a, 0x41); /* 模拟 RGB 显示 */
outp(0x6a, 0x01); /* 16 COLOR MODE */
outp(0xa2, 0x4b); /* 行长度设置命令 */
outp(0xa0, 0x00); /* 水平总点 */
outp(0xa4, 0x00); /* 显示页面指定 */
outp(0xa6, 0x00); /* 绘图页面指定 */
```

**GDC 状态读取 (60h/A0h):**

| Bit | 含义 |
|-----|------|
| 0 | 数据读就绪 |
| 1 | FIFO 满 |
| 2 | FIFO 有数据 |
| 3 | FIFO 有空位 |
| 5 | VSync 进行中 |
| 6 | HSync 进行中 |

**GDC 命令:**

| 命令 | 代码 | 说明 |
|------|------|------|
| 显示开始 | 0Dh | — |
| 显示停止 | 0Ch | — |
| 开始地址+显示大小 | 70h+x | 设置显示区域地址和行长度 |
| 行长度/光标设置 | 4Bh | CS/光标/行长度 |
| VRAM 间隔设置 | 47h | TEXT GDC 5MHz 可设置 |
| GDC 复位 | 00h | 复位 GDC |

显示模式设置命令:

| Bit | 含义 |
|-----|------|
| DE | 0=不显示/1=显示 |
| CHR,G | 00=文本重写, 01=文本, 10=图形, 11=禁止 |
| F | 0=刷新型, 1=非刷新型 |
| I,S | 00=无中断, 10=中断, 11=中断+VSync |
| D | 0=静态(文本), 1=动态(图形) |

### (4) GVRAM (16色图形)

**平面结构:** PC-98 图形 VRAM 由 4 个位平面组成:

| Plane | 地址 |
|-------|------|
| Plane0 | A8000h |
| Plane1 | B0000h |
| Plane2 | B8000h |
| Plane3 | E0000h |

每个点 1 位, 每个平面 1 位组合成 4 位调色板号 (16色)。

**坐标计算:**
```
OffsetAddress = x / 8 + y * 80
BitAddress = x % 8
```

**调色板设置:**
- 端口 A8h: 选择调色板号 (0-15)
- 端口 AAh: 绿色亮度 (0-15)
- 端口 ACh: 红色亮度 (0-15)
- 端口 AEh: 蓝色亮度 (0-15)

RGB 各 4 位, 总计 4096 色中选 16 色。

**显示/绘图页面选择 (端口 A4h/A6h):**
- bit0=0: 表
- bit0=1: 里

### (5) GRCG & EGC

#### GRCG (Graphic CharGer)

端口:

| 地址 | 功能 |
|------|------|
| 7Ch | GRCG 模式/掩码设置 |
| 7Eh | GRCG 图样寄存器 |

GRCG 模式寄存器:

| D7 | D6 | D5-D4 | D3-D0 |
|----|----|-------|-------|
| CG | RMW | 0 | P3-P0 |

- CG: GRCG 启用(1)/禁用(0)
- RMW: 0=TC(透明)/TCR(读比较), 1=RMW(写叠加)
- P0-P3: Plane 0-3 写入有效(0=有效)

图样寄存器需要 4 次写入 (Plane 0-3) 完成设置。

#### EGC (Enhanced Graphic Charger)

端口:

| 地址 | 功能 |
|------|------|
| 04A0h | 访问平面指定 |
| 04A2h | 模式/图样寄存器 |
| 04A4h | 模式/光栅操作 |
| 04A6h | 前景色指定 |
| 04A8h | 掩码寄存器 |
| 04AAh | 背景色指定 |
| 04ACh | 位地址/块移动 |
| 04AEh | 写入区域位长 |

**EGC 启用步骤:**
1. 禁用中断
2. 扩展模式切换可: `0x6A <- 0x07`
3. EGC 模式: `0x6A <- 0x05`
4. EGC 启用: `0x7C <- 0x80`
5. 访问平面全设: `0x4A0 <- 0xfff0`
6. 图样数据选择图样寄存器: `0x4A2 <- 0x0000`
7. 前景色清零: `0x4A6 <- 0x00`
8. 掩码全设: `0x4A8 <- 0xffff`
9. 写入位长 15: `0x4AE <- 0xf`
10. 扩展模式切换不可: `0x6A <- 0x06`
11. 启用中断

光栅操作:

| 操作 | 代码 |
|------|------|
| MOV | 0CF0h |
| OR | 0CFCh |
| AND | 0CC0h |
| 反相 MOV | 28F0h |
| 反相 OR | 29BEh |

### (6) 256 色模式 (PC-9821)

**格式:** Packed Pixel (1字节=1点)

**分辨率:** 640x400 (24/31KHz) 或 640x480 (31KHz only)

**VRAM 访问:** 通过 Bank 切换

```
逻辑地址 = Y * 640 + X
BANK     = 逻辑地址 >> 15
BANK内地址 = 逻辑地址 & 32767
```

内存映射 I/O (E000:0xxx):

| 地址 | 功能 |
|------|------|
| E000:0004 | VRAM Window0 Bank 位置 |
| E000:0006 | VRAM Window1 Bank 位置 |
| E000:0100 | VRAM 写入方式 (0=Packed, 1=Plane) |

**256 色 BIOS (INT 18h):**

| 功能 | AH | 参数 |
|------|----|------|
| 设置模式 | 30h | AL=时钟, BH=分辨率 |
| 获取模式 | 31h | — |
| 切换模式 | 4Dh | CH=00(标准)/01(扩展) |

---

## PART 5: 声音

### (1) CDDA (使用 MSCDEX)

通过 INT 2Fh (AX=1510h) 发送 IOCTL 请求包。

主要命令:
- 0x84: Play Audio
- 0x85: Stop Audio
- 0x88: Resume Audio

### (2) PCM (86音源)

86 音源板 PCM 使用 YM2608 (OPNA)。

关键 I/O 端口:

| 端口 | 功能 |
|------|------|
| A460h | ID 识别 (D7-4=设备ID) |
| A466h | FIFO 状态/电子音量 |
| A468h | FIFO 控制 + PCM 速率 |
| A46Ah | 量化位/立体声 |
| A46Ch | FIFO 数据 |
| A66Eh | 输出静音 |

PCM 速率:
- 000: 44.10kHz
- 001: 33.08kHz
- 010: 22.05kHz
- 011: 16.54kHz
- 100: 11.03kHz
- 101: 8.27kHz
- 110: 5.52kHz
- 111: 4.13kHz

支持 8/16 位, 单声道/立体声。FIFO 大小: 32KB。
