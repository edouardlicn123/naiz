# PC-98 引导与磁盘系统

> 来源：
> - 引导记录：http://radioc.web.fc2.com/column/pc98bas/pc98diskep_en.htm
> - HDI 注入规范：`docs/B06-HDI注入规范.md`
> - UNDOCUMENTED Vol.2 io_sasi.txt / io_scsi.txt / io_ide.txt / io_fdd.txt
> - UNDOCUMENTED Vol.2 io_syste.txt（系统端口 + DIP 开关）

## 引导过程

### 上电顺序

1. CPU 复位 → 从 **FFFF0h** 开始执行（系统 ROM BIOS）
2. BIOS POST → 初始化硬件
3. BIOS 读 **硬盘 IPL**（LBA 0，第一个扇区）
4. IPL → 读引导扇区（FAT/VBR）→ 加载 IO.SYS
5. IO.SYS → 处理 CONFIG.SYS → 加载 MSDOS.SYS → 读 AUTOEXEC.BAT
6. 引擎启动

### 引导设备选择

系统 DIP 开关或引导菜单选择引导设备：
- FDD（640KB / 1MB）
- HDD（SASI / SCSI / IDE）

### 启动快捷键

PC-9821 及后期机型支持以下启动按键（开机或复位时按住）：

| 按键 | 功能 | 备注 |
|------|------|------|
| STOP | 跳过系统内存测试 | 未公开 |
| TAB | 显示硬盘引导菜单 | 需扩展格式硬盘 |
| COPY | 从 RAM 盘引导 | 仅笔记本电脑 |
| HELP | 进入系统设置菜单 | PC-9801DA 及以后 |
| HELP+RETURN | 进入系统设置菜单 | 部分 CPU 升级套件 |
| SHIFT+STOP+CTRL | 将系统内存转储到 FD | VX 及以后，未公开 |
| GRPH+1 | 设置水平频率 24kHz | 9821 除 S1,S2 外 |
| GRPH+2 | 设置水平频率 31kHz | 9821 除 S1,S2 外 |
| HELP+ESC+1 | 显示 BIOS 版本 | 9821An 及以后，未公开 |
| HELP+ESC+8 | 显示 BIOS 更新菜单 | 9821 及以后，未公开 |
| HELP+ESC+9 | 初始化 PnP BIOS | PnP 支持机型 |
| CTRL+CAPS+KANA+GRPH | 显示 CPU 速度和屏幕模式 | RA 及以后，未公开 |
| CTRL+SHIFT | 复位内存开关数据 | 仅笔记本电脑，未公开 |
| GRPH+SHIFT | 复位内存开关数据 | PC-9801DA 及以后，未公开 |

### IPL 记录格式

| 参数 | 640KB FD | 1MB FD | HDD (CT=11) | HDD (CT=00) |
|------|----------|--------|-------------|-------------|
| 引导单元号 | 0–3 | 0–3 | 0, 1 | 0, 1 |
| 记录格式 | FM | FM/MFM | MFM | MFM |
| 扇区大小 | 128–1024B | 128–1024B | 256B | 256B |
| 加载地址 | 1FE0h:0000h | 1FE0h:0000h | 1FE0h:0000h | 1FE0h:0000h |
| 入口偏移 | 0000h | 0000h | 0000h | 0000h |
| IPL 签名 | — | — | "IPL1" @ +4 | — |

### 硬盘 IPL 的控制器类型

- **CT=11**：PC-98XA/XL/XL2 内置接口
- **CT=00**：PC-9801-27 SASI 接口
- 通过 DIP 开关设置，可从 I/O 82h 读取

## 系统 DIP 开关 (I/O 31h)

读 I/O 31h（8255A Port A）获取系统 DIP 开关状态（反相）：

| Bit | 开关 | 功能 |
|-----|------|------|
| 0 | SW1 | 保留 |
| 1 | SW2 | 保留 |
| 2 | SW3 | 保留 |
| 3 | SW4 | 保留 |
| 4 | SW5 | 保留 |
| 5 | SW6 | 保留 |
| 6 | SW7 | 保留 |
| 7 | SW8 | CPU 类型（0=80286, 1=V30） |

SW3-8 (bit 7) 在 PC-9801VX 等机型上切换 CPU：OFF=80286, ON=V30。

### 系统设置菜单 (System Setup Menu)

PC-9801DA（1990）及后期机型具有系统设置菜单（类似 IBM PC 的 BIOS 设置）。启动时按住 **HELP** 键进入。

**主要设置项**：

| 菜单 | 设置项 | 选项 |
|------|--------|------|
| 运行环境 | 16MB 系统空间 | 不使用/使用（Windows 3.1 需设为"使用"） |
| | 声音 | 不使用/使用（安装外部声卡时设为不使用） |
| | 声音中断通道 | INT0, INT1, INT41, INT5 |
| | ROM BASIC | 不使用/使用 |
| DIP 1 | 等离子显示器 | 不使用/使用（仅 Digital RGB 输出） |
| | 软驱编号 | 内置 #3,#4 外置 #1,#2 / 内置 #1,#2 外置 #3,#4 |
| | RS-232C 模式 | BCI 同步/ST2 同步/接收同步/异步 |
| | 固定磁盘扇区长 | 512 字节/256 字节 |
| | 图形模式 | 扩展(16色)/基本(8色) |
| DIP 2 | 终端模式选择 | 终端模式/BASIC 模式 |
| | 文本行数 | 25 行/20 行 |
| | 内存开关 | 保持/初始化 |
| | 内置固定磁盘 | 不使用/使用 |
| | **GDC 时钟** | **5MHz/2.5MHz**（兼容性问题时设 2.5MHz） |
| DIP 3 | 软驱模式 | 640K/1M/自动(640K)/自动(1M) |
| | 软驱电机控制 | 是/否 |
| | DMA 时钟 | 高速(10MHz)/兼容(5MHz) |
| | 内置 RAM 空间 | 禁用/启用 |
| | CPU 模式 | High(原生速度)/Low(≈i486-16MHz) |

## 软件 DIP 开关

后期机型（PC-9821 等）使用软件 DIP 开关替换部分硬件 DIP：

- I/O 0810h–081Fh 系列端口
- 用于 GDC 时钟（2.5/5MHz）、启动设备等
- 通过 BIOS 设置菜单（启动时按特定键）配置

## HDI 镜像结构

### HDI 头 (4096 字节)

| 偏移 | 大小 | 内容 |
|------|------|------|
| 0 | 4 | 签名 "HDI\x1a" |
| 4 | 4 | 头部大小（通常 4096） |
| 8 | 4 | 总扇区数 |
| 12 | 2 | 磁头数 |
| 14 | 2 | 每道扇区数 |
| ... | ... | 几何信息 |
| 4096 | — | 数据起始 |

### 磁盘几何（基座 HDI）

- 722 柱 × 8 磁头 × 17 扇区/道 × 512 字节/扇区
- FAT16，每簇 2 扇区（1024 字节/簇）
- 分区起始：LBA 136
- 系统 ID：0x91（SCSI）

## CONFIG.SYS 与 VEM486

标准引导配置：

```ini
DEVICE=A:\VEM486.EXE /U
DOS=HIGH,UMB
```

VEM486.EXE 功能：
- XMS 服务器
- EMS 服务器
- VCPI 服务器（DOS/4GW 需要）
- `/U` 开关 = UMB 支持

## AUTOEXEC.BAT

典型内容：
```batch
@ECHO OFF
SET DOS16M=1
ENGINE.EXE
```

`SET DOS16M=1` 是 DOS/4GW 启用 PC-98 路径的开关键。

## 磁盘接口

### SASI (PC-9801-27)

- I/O 80h–87h
- 传统硬盘接口，PC-9801-27 扩展卡
- 数据传输速率较低

### SCSI

- I/O DC000h–DCFFFh (PC-9801-55,-92)
- PC-9801-50 使用 DC000h–DDFFFh
- 提供更高速度和更多设备支持

### IDE

- I/O D8000h–DBFFFh
- 后期机型支持
- 类似 AT 接口的 IDE/ATA

### FDD

| 类型 | I/O | 控制器 |
|------|-----|--------|
| 320KB 2D | 50h–5Fh | 8255A |
| 640KB | 90h–97h | μPD765 |
| 1MB | 90h–97h | μPD765 |
