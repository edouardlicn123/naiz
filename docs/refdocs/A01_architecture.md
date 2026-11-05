# PC-98 硬件架构总览

> 来源：http://radioc.web.fc2.com/column/pc98bas/pc98disphw_en.htm
> 补充：https://pc98.ne.jp/devdocs/
> PDF 参考：PC-9800 Technical Data Book (Hardware)

## GDC (μPD7220) — 第一代

- 1981 年 NEC 推出 μPD7220，最早商用的 GPU 之一
- PC-9801 初代搭载 **2 片** μPD7220A（2.5MHz）：
  - **Master**：文本屏 GDC，生成 CRT 同步信号，控制文本显示
  - **Slave**：图形屏 GDC，接收 Master 的同步信号驱动图形层
- 支持 4 种屏幕模式：640×200 单色 / 8 色、640×400 单色 / 8 色
- 文本 VRAM 8KB（A0000h–A1FFFh），属性 E2000h？实际为 A2000h+ 区域
- 图形 VRAM 96KB（A8000h–BFFFFh），4 平面中的前 3 个

## GRCG (Graphic Charger) — 第二代

- 1985 年随 PC-9801VM 等引入
- **图形加速器**，支持同时访问多个图形平面
- 8/16 色（从 4096 色中选择），256KB VRAM（+ 可选 192KB）
- 三种模式：
  - **TDW** (Tile Data Write)：CPU 写入 → 根据 Tile 寄存器写入 VRAM
  - **TCR** (Tile Compare Read)：将 VRAM 读出的数据与 Tile 寄存器按位比较
  - **RMW** (Read Modify Write)：根据 Tile 寄存器选择性写入 VRAM
- I/O 端口：7Ch/7Eh（Normal）、A4h/A6h（Hires）

## EGC (Enhanced Graphic Charger) — 第三代

- 1986 年随 PC-9801VX 引入
- 向后兼容 GRCG
- 支持 **并行处理**（与 GDC 同时访问 VRAM）
- **Raster Operation**（ROP）：对 CPU↔VRAM 数据进行逻辑运算
- **Bit Shifter**：数据按位移位
- **Block Transfer**：快速块拷贝
- **Tile Register** 扩展为 4 个独立平面控制
- I/O 端口：4A0h–4AEh（8 个 16-bit 寄存器）
- 注意：原始 EGC 芯片（D65101S017）存在 bug，特定寄存器操作异常
- EGC 仅在通过 I/O 6Ah bit 4–5 切换到 EGC 模式时才启用

## High-resolution Mode

- 1120×750 分辨率，768KB 常规内存
- PC-98XA/XL/XL2/H98 系列支持
- 图形系统与标准 PC-98 部分兼容，但不完全相同
- 成本高，主要用于 CAD，游戏不支持

## PC-98GS 扩展图形

- 唯一特殊图形系统 "Extended Screen Graphics"
- 1MB VRAM，最大 640×240 24bit 或 640×480 65536 色
- 视频捕获 + 录音功能
- 需要特殊显示器 PC-98GS-C1
- 其简化版声音电路成为 PC-9801-86（最常见的声音卡）

## 256 色模式 (PEGC)

- 1993 年随 98MATE（PC-9821Ap/As/Ae）引入
- 640×400 256 色 2 页，或 640×480 256 色 1 页
- **Planar 模式**（平面模式）和 **Packed-pixel 模式**（像素打包模式）
- Planar 模式仅少数早期 9821 支持（Ap/As/Ae/Af/Ap2/As2/An/Ce/Ce2/Cs2/Np/Ne）
- 常用名 "PEGC" 源于 Windows 显示驱动中的标识
- DOS 游戏支持有限（Blandia, Doom, Rance IV, War Craft 等）

## 兼容性问题汇总

- **旧游戏在后期机型运行过快**：CPU 周期差异（8086 8MHz vs V30 8MHz）
- **GDC 5MHz 问题**：部分 DOS 游戏（Puyo Puyo, Touhou 1–3）需软件 DIP 开关切回 2.5MHz
- **30 行文本模式**：需要 31kHz 显示器，部分 9821 支持
- **640×200 / 40 列文本 / 单色在后期机种移除**：1995 年中以后机型不支持
- **标准 256 色驱动不兼容**：零售 Windows 3.x 的 256 色驱动要求 Planar 模式，仅少数机型支持

## 显示器连接

- DA-15 接口，模拟视频信号与 VGA 相同
- 水平频率 24kHz（标准）或 31kHz（部分 9821），需多频显示器
- 启动时按住 GRPH+2 切 31kHz，GRPH+1 切回 24kHz
- 256 色模式下固定 24kHz
