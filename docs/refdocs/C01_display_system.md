# PC-98 显示系统

> 关键来源：
> - UNDOCUMENTED Vol.2 io_disp.txt：https://www.webtech.co.jp/company/doc/undocumented_mem/io_disp.txt
> - UNDOCUMENTED Vol.2 io_egc.txt：https://www.webtech.co.jp/company/doc/undocumented_mem/io_egc.txt
> - radioc 图形系统：http://radioc.web.fc2.com/column/pc98bas/pc98disphw_en.htm
> - radioc I/O 细节：http://radioc.web.fc2.com/column/pc98bas/pc98vxioports_en.htm

## 显示系统架构

PC-98 显示由以下芯片/模块协同工作：

```
CPU
 ├──> 文本 GDC (Master, μPD7220) ──> CRT 同步信号
 ├──> 图形 GDC (Slave,  μPD7220) ──> 图形层
 ├──> CRTC (μPD52611) ──> 文本行/滚动控制
 ├──> 字符发生器 (CG) ──> 字体 ROM → 文本像素
 ├──> GRCG/EGC ──> 图形加速
 ├──> 调色板 DAC ──> 数字颜色 → 模拟 RGB
 └──> 模式 F/F ──> 显示模式控制
```

## 文本 GDC (I/O 60h–62h)

Master GDC 生成 CRT 同步信号，控制文本显示。

### 命令集 (写 62h)

| 命令 | 编码 | 功能 |
|------|------|------|
| RESET1 | 00h | 复位 1 |
| RESET2 | 01h | 复位 2 |
| STOP2 | 05h | 停止 2 |
| RESET3 | 09h | 复位 3 |
| STOP1 | 0Ch | 停止 1 |
| START | 0Dh | 启动 |
| SYNC | 0Eh/0Fh | 同步 |
| WRITE/DMAW | 20h–3Fh | 写入 / DMA 写入 |
| ZOOM | 46h | 缩放 |
| PITCH | 47h | 间距 |
| CSRW | 49h | 光标位置写 |
| CSRFORM | 4Bh | 光标格式 |
| VECTW | 4Ch | 向量宽 |
| TEXTE | 68h | Text End |
| START | 6Bh | 启动 |
| VECTE | 6Ch | Vector End |
| SCROLL/TEXTW | 70h–7Fh | 滚动/文本写入 |
| SLAVE | 6Eh | 从模式 |
| MASTER | 6Fh | 主模式 |
| READ/DMAR | A0h–BFh | 读取 / DMA 读取 |
| LPEN | C0h | 光笔 |
| CSRR | E0h | 光标位置读 |
| MASK | 4Ah | 掩码 |

图形 GDC (A0h–A2h) 命令集与文本 GDC 相同。

### 状态寄存器 (读 60h/A0h)

| Bit | 标志 | 说明 |
|-----|------|------|
| 7 | LPEN | 光笔检测 |
| 6 | HBLANK | 水平消隐 |
| 5 | VSYNC | 垂直同步 |
| 4 | DMA | DMA 执行中 |
| 3 | DRAWING | 绘图中 |
| 2 | FIFO EMPTY | FIFO 空 |
| 1 | FIFO FULL | FIFO 满 |
| 0 | DATA READY | 数据就绪 |

## 模式 F/F 寄存器 (68h/6Ah)

### I/O 68h — 模式 F/F 1 (Mode Flip-Flop 1)

写 68h 设置以下模式（bit3–1 = 地址选择, bit0 = 数据）：

| 编码 | 功能 | 值含义 |
|------|------|--------|
| 00h/01h | ATR SEL | 属性位4 功能选择：0=垂直行, 1=简易图形 |
| 02h/03h | GRAPHIC Mode | 图形颜色模式：0=彩色, 1=单色 |
| 04h/05h | Column WIDTH | 文本列宽：0=80列, 1=40列 |
| 06h/07h | FONT SEL | 字体选择：0=6x8 点阵, 1=7x13 点阵 |
| 08h/09h | GRP Mode | 图形纵向分辨率：0=显示线数, 1=不显示线数 |
| 0Ah/0Bh | KAC Mode | 汉字访问模式：0=代码访问, 1=点阵访问 |
| 0Ch/0Dh | NVMW PERMIT | VRAM 写入保护：0=禁止, 1=允许（A000:3FE2–3FFEh） |
| 0Eh/0Fh | DISP ENABLE | 显示开/关：**1=显示开, 0=所有屏幕不显示** |

**DISP ENABLE (0Fh/0Eh) 是最关键的设置**：
- 0Fh = OUT 68h, 0Fh → 打开文本和图形的显示
- 0Eh = OUT 68h, 0Eh → 全部关闭

### I/O 6Ah — 模式 F/F 2 (Mode Flip-Flop 2)

| 编码 | 功能 | 值含义 |
|------|------|--------|
| 00h/01h | 8/16 色 | 0=8色, 1=16色 |
| 04h/05h | EGC Mode | 0=GRCG 兼容, 1=EGC 扩展 |
| 06h/07h | EGC F/F 切换 | 0=禁止, 1=允许 |
| 40h/41h | 文本+图形显示模式 | 0=CRT 模式, 1=等离子/LCD 模式 |
| 82h/83h | GDC 时钟 1 | 0=2.5MHz, 1=5.0MHz |
| 84h/85h | GDC 时钟 2 | 0=2.5MHz, 1=5.0MHz |

## VRAM 布局

### 文本 VRAM (A0000h–A3FFFh)

- 字符码：A000h:0000h–1FFFh（每字符 2 字节 JIS 码）
- 属性：   A000h:2000h–3FFFh（每字符 2 字节属性）

### CG 窗口 (A4000h–A4FFFh)

- 4KB 窗口，用于读取字体 ROM 中的字符点阵模式
- 通过 KAC Mode（68h, 0Ah/0Bh）切换为 Dot Access 模式可读取

### 图形 VRAM（标准 16 色，4 平面）

| 平面 | 段地址 | 偏移范围 | 大小 |
|------|--------|----------|------|
| Plane 0 (Blue) | A800h | 0000h–7FFFh | 32KB |
| Plane 1 (Red) | B000h | 0000h–7FFFh | 32KB |
| Plane 2 (Green) | B800h | 0000h–7FFFh | 32KB |
| Plane 3 (Intensity) | E000h | 0000h–7FFFh | 32KB |

每像素 1 bit → 4 bits 构成 16 色索引：
- 颜色值 = (Plane3 << 3) | (Plane2 << 2) | (Plane1 << 1) | Plane0
- 即：bit3=I, bit2=G, bit1=R, bit0=B

### 8 色模式只使用 Plane 0–2（A800h, B000h, B800h）

### 显示页面选择 (I/O A4h)

写 A4h:
- 00h = 显示 Plane 0
- 01h = 显示 Plane 1（双缓冲页面切换）

### 绘制页面选择 (I/O A6h)

写 A6h:
- 00h = 绘制 Plane 0
- 01h = 绘制 Plane 1

## GRCG (Graphic Charger)

GRCG 是 4 平面同时操作的图形加速器，3 种模式：

### 模式寄存器 (I/O 7Ch — Normal, I/O A4h — Hires)

| Bit | 名称 | 功能 |
|-----|------|------|
| 7 | CGmode | 1=GRCG 启用, 0=禁用 |
| 6 | RMWmode | 1=RMW 模式, 0=TCR 模式(TDW 写) |
| 5–4 | RP1/RP2 | Hires 平面选择（仅 A4h 版本） |
| 3–0 | P3EN#–P0EN# | 平面启用：1=禁用, 0=启用 |

### Tile 寄存器 (I/O 7Eh — Normal, I/O A6h — Hires)

写 7Ch/A4h 后，写入 7Eh/A6h 四次，分别对应 Tile 0–3（每平面一次）。

### GRCG 三种模式

1. **TDW** (Tile Data Write)：CPU 写入任何值 → Tile 寄存器内容写入启用的平面
2. **TCR** (Tile Compare Read)：比较 VRAM 数据与 Tile 寄存器，全匹配=1
3. **RMW** (Read Modify Write)：按 Tile 寄存器掩码，1 写 Tile, 0 保留 VRAM

### GRCG 切换条件

```
EGC 模式 (6Ah bit4=1) 时 GRCG 不可用
EGC 兼容模式 (6Ah bit4=0) 时继续使用 GRCG
```

## EGC (Enhanced Graphic Charger)

EGC 是 GRCG 的超集，增加 ROP、位移位、块拷贝。

### EGC 启用条件

1. I/O 6Ah bit4–5 = 05h (EGC 扩展模式)
2. I/O 7Ch bit7 = 1 (CGmode)

### EGC 寄存器 (WORD 访问, 4A0h–4AEh)

| 端口 | 寄存器 | 功能 |
|------|--------|------|
| 4A0h | R1 | 平面启用 (P0EN#–P7EN#) |
| 4A2h | R2 | FGC/BGC 选择 + 模式平面 |
| 4A4h | R3 | **ROP 代码** + 移位/模式控制 |
| 4A6h | R4 | Foreground 颜色 |
| 4A8h | R5 | Mask 寄存器 |
| 4AAh | R6 | Background 颜色 |
| 4ACh | R7 | 位移位方向/源地址 |
| 4AEh | R8 | 位计数器 |

### ROP 代码 (4A4h bit7–0)

EGC 支持 256 种 ROP；常用示例：

| ROP | 源 A | 目标 B | 模式 P | 结果 | 说明 |
|-----|------|--------|--------|------|------|
| F0h | 依赖 | — | — | VRAM 移入 | Shifter → Dst |
| CCh | — | 依赖 | — | 无操作 | 直通 |
| AAh | — | — | 依赖 | Pattern | 模式填充 |
| FFh | — | — | — | 全 1 | 涂白 |
| 00h | — | — | — | 全 0 | 涂黑 |

**源选择** (4A4h bit12–11)：
- 00 = CPU 数据
- 01 = 移位结果（FGC/BGC 模式）
- 10 = Pattern 寄存器

**位移位**：
- 4ACh: bit12 = DIR（位移方向）, bit7–4 = 目标位地址, bit3–0 = 源位地址
- 4AEh: 位计数（通常 000Fh = 16 bits）

## 调色板

### 8 色模式 (I/O A8h–AEh)

16 色寄存器（部分为 8 色模式用），每 2 字节一组：
```
bit7–4: 0 B G R (颜色 n+1)
bit3–0: 0 B G R (颜色 n)
```

### 边框颜色 (I/O 6Ch)

写 6Ch：
```
bit6–4: 颜色编码 (R,G,B)
bit7:   H98 系列的 Intensity 位
```

## CRTC (μPD52611) — 文本行/滚动控制

I/O 端口 70h–7Ah：

| 端口 | 名称 | 说明 |
|------|------|------|
| 70h | PL | 字符位置行数（初始扫描行） |
| 72h | BL | Body 面行数（= 可见行数 − 1） |
| 74h | CL | 字符行数 |
| 76h | SSL | 平滑滚动计数 |
| 78h | SUR | 滚动区域上边界（×2） |
| 7Ah | SDR | 滚动区域行数（= 行数 − 1） |

## 字符发生器 (I/O A1h/A3h/A5h/A9h)

### 字符代码设置

| 端口 | 写功能 |
|------|--------|
| A1h | 第 2 字节代码：00h=ANK, 01h–DFh=汉字第 2 字节 |
| A3h | 第 1 字节代码：00h=ANK, 01h–08h/0Ch–DFh=汉字第 1 字节 |

### 行计数器 + 数据 (A5h/A9h)

| 端口 | 功能 |
|------|------|
| A5h | bit5=L/R, bit4–0=行内扫描行(最高16行) |
| A9h | 读=点阵数据读出，写=用户定义字体写入 |

### CG 窗口访问

**Code Access 模式**（显示用）：按 JIS 码索引字体 ROM，字体像素直接送显。
**Dot Access 模式**（读取用）：通过 A400h:0000h–4FFFh 直接读取字体点阵。

## 显示初始化序列

典型的显示初始化顺序（love es×××× 参考）：

```c
// 1. 文本 GDC 复位 + 启动
outp(0x62, 0x00);  // RESET1
outp(0x62, 0x01);  // RESET2
outp(0x62, 0x09);  // RESET3
outp(0x62, 0x6B);  // START

// 2. 图形 GDC 复位 + 启动
outp(0xA2, 0x00);  // RESET1
outp(0xA2, 0x01);  // RESET2
outp(0xA2, 0x09);  // RESET3
outp(0xA2, 0x6B);  // START

// 3. 模式设置
outp(0x68, 0x06);  // 6x8 字体
outp(0x68, 0x02);  // 彩色
outp(0x68, 0x04);  // 80 列
outp(0x68, 0x00);  // 正常属性模式
outp(0x68, 0x0F);  // 显示开! (关键)

// 4. 颜色模式
outp(0x6A, 0x00);  // 8 色

// 5. 清除文本 VRAM
memset(0xA0000, 0x20, 4000);  // 空格填充字符码
memset(0xA2000, 0, 4000);     // 属性清 0

// 6. 清除图形 VRAM (可选)
memset(0xA8000, 0, 0x8000);
memset(0xB0000, 0, 0x8000);
memset(0xB8000, 0, 0x8000);
memset(0xE0000, 0, 0x8000);

// 7. GRCG 禁用默认
outp(0x7C, 0x00);  // CGmode=0, RMW=0
```

## VSYNC 中断

- IRQ 2（INT 0Ah）在 V-Sync 开始时触发
- I/O 64h 写任意值可手动触发一次 VSYNC 中断
- 部分 INT 18h 函数会关闭 VSYNC，需通过写 64h 重新唤醒

## 图形硬件演进史

### GDC (μPD7220) — 1982

1981 年 NEC 推出 μPD7220，是最早的 GPU 之一。最初用于 N5200 model 05（640×475 分辨率）。PC-9801 包含两颗 μPD7220A（2.5MHz），分别控制文本和图形。支持 640×200（8 色, 2 页）和 640×400（8 色, 1 页）。DEC Rainbow、Tulip System-1 和 Number Nine 显卡也使用 μPD7220。

1983 年 PC-9801F 增加 JIS Level-1 汉字 ROM 和 4KB 额外文本 RAM。

### GRCG (Graphic Charger) — 1985

1985 年 NEC 推出 GRCG 图形加速芯片，支持多平面同时访问，加速矩形填充。PC-9801VM 首次支持 4096 色中选 16 色（需额外 VRAM 板 PC-9801-24）。PC-9801UV2（1986）后标准 256KB VRAM。

### EGC (Enhanced Graphic Charger) — 1986

与 PC-9801VX 一同推出，向下兼容 GRCG，支持 GDC 并行处理、光栅操作（ROP）、位移位和块传输。部分早期机型（UV, UR, CV, PC-98DO）不支持。2 GDC + EGC + 640×400 16 色 2 页 成为 PC-98 图形标准，持续至末代 PC-9821Ra43（2000）。

**原版 EGC 芯片 (D65101S017) 存在 bug**：某种寄存器操作在特定情况下不正确。中后期 9801 机型（VX, RA, EX）受影响。后期机型和 Epson 克隆不受影响。

### 高分辨率模式 — 1987

PC-98XA/XL/XL2/PC-H98 系列支持 1120×750 分辨率、768KB 常规内存和不同图形系统。BIOS 和 I/O 部分兼容正常 PC-98。昂贵且多用于 CAD。

### PC-98GS — 1991

唯一包含"扩展画面图形"的机型。1MB VRAM，支持 640×240 24bit 色或 640×480 65536 色。其音频子系统精简版成为 PC-9801-86 声音板。

### PEGC (256 色模式) — 1993

与 98MATE（PC-9821Ap, As, Ae）一同推出。支持两种模式：
- 640×400 × 256 色（24bit 调色板中选）× 2 页
- 640×480 × 256 色 × 1 页

类似但**不兼容** PC-98GS 的扩展画面图形。官方名称未知，通常称"256 色模式"或"PEGC"（源自 Windows 显示驱动 PEGCV8.DRV）。

**两种 VRAM 访问模式**：
- **平面模式 (Planar Mode)**: 仅 PC-9821Ap, As, Ae, Af, Ap2, As2, An, Ce, Ce2, Cs2, Np, Ne 支持。这些机型是 98 爱好者最受欢迎的。
- **Packed-Pixel 模式**: 所有 PEGC 机型支持。

**256 色 VRAM 访问**：通过 Bank 切换
```
逻辑地址 = Y * 640 + X
BANK     = 逻辑地址 >> 15
BANK内地址 = 逻辑地址 & 32767
```

**256 色 BIOS (INT 18h)**：
| 功能 | AH | 参数 |
|------|----|------|
| 设置模式 | 30h | AL=时钟, BH=分辨率 |
| 获取模式 | 31h | — |
| 切换标准/扩展 | 4Dh | CH=00(标准)/01(扩展) |

## 已知兼容性问题

### 早期 98 游戏在后期机型上过快

依赖 CPU 周期的游戏在后期机型上运行过快。即使 CPU 时钟相同，每周期指令数和 I/O 等待周期也不同（如 8086 8MHz vs V30 8MHz）。

### GDC 5MHz 不兼容

PC-9801DA 及后期机型可以 5MHz 运行 GDC，但部分 DOS 游戏（如 Puyo Puyo、东方 1-3）会出问题。需在系统设置中将 GDC 时钟设为 2.5MHz。

### 30 行文本模式

PC-9821 支持 31kHz 水平频率（标准 24kHz），可设置 30 行文本模式（≈VGA 640×480）。需要多同步显示器。

### 640×200 / 40 列 / 单色模式

1995 年中之后的 PC-9821 机型不再支持 640×200 图形、40 列文本和单色模式。

## CRT 显示器信息

标准 PC-98 使用 DA-15 接口（模拟 RGB，与 VGA 信号格式兼容），可通过 AD-D15NE 适配器转 DE-15（VGA）。但水平频率为 24kHz，多数现代显示器不支持。

PC-9821 及后期机型可切换至 31kHz：
- GRPH+1: 24kHz
- GRPH+2: 31kHz（启动时按住）

256 色模式下水平频率固定为 24kHz。
