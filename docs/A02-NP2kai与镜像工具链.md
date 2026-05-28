# NP2kai 与镜像工具链

## 1. 概述

NP2kai 是 Neko Project II 的改进版（kai = 改良），PC-9800 系列模拟器。本项目的开发环境围绕 NP2kai 构建，配合自研的 `tools/naiz_img/` 镜像工具链（基于 98Bridge 设计思路），实现从游戏文件到可启动 HDI 再到模拟器验证的完整闭环。

### 核心架构

```
游戏项目 (games/<name>/) + 配置 (tools/ref_config/)
    │
    ▼
tools/naiz_img/inject.py  ── 基于 base_msdos5_scsi_48m.hdi 注入 ──▶  disks/<name>.hdi
    │
    ▼
makegame.sh test ──▶  NP2kai (wxnp21kai)  ──▶  MS-DOS 5.0 boot → AUTOEXEC.BAT → ENGINE.EXE
```

### NP2kai 两大核心

| 核心 | 二进制 | 模拟目标 | 用途 |
|------|--------|----------|------|
| **[DEPRECATED] i286** | `sdlnp2kai_sdl2` | PC-9801 (286) | 已弃用（BIOS 不匹配） |
| **IA32** | `wxnp21kai` | PC-9821 (486+) | **当前开发目标**，与 PC-9821 BIOS 兼容 |

### 开发环境路径速查

| 项目 | 路径 |
|------|------|
| NP2kai 源码 | `/tmp/NP2kai/` |
| NP2kai 构建 | `/tmp/NP2kai/build/` |
| 模拟器安装 | `/usr/local/bin/wxnp21kai` |
| 模拟器配置 | `~/.config/wxnp21kai/wxnp21kai.toml` |
| BIOS ROM | `~/.config/wxnp21kai/bios.rom` |
| Font ROM | `~/.config/wxnp21kai/font.rom` |
| 基座镜像 | `tools/base_msdos5_scsi_48m.hdi` |
| 输出镜像 | `disks/<game>.hdi` |
| 测试日志 | `logs/test_<game>_<timestamp>.log` |

---

## 2. 构建指南

### 依赖

```bash
sudo apt install libsdl2-dev libsdl2-ttf-dev libgl1-mesa-dev \
                 g++ cmake make libssl-dev
```

### 源码获取

```bash
git clone https://github.com/AZO234/NP2kai.git /tmp/NP2kai
```

### 自动构建

提供 `install_env.py` 命令（通过 `start.sh` → 环境设置 → [DEPRECATED] 构建 i286 核心）：

| 命令 | 功能 |
|------|------|
| `build-i286` | [DEPRECATED] 编译 i286 核心（带 SASI 补丁） |
| `np2kai` | 编译 IA32 核心（标准流程） |
| `np2kai-libretro` | 编译 libretro 核心 |
| `check` | 检查已安装的模拟器二进制 |
| `backup-emu` | 安装 libretro + RetroArch 备选 |

### [DEPRECATED] i286 核心构建（手动）

```bash
cmake /tmp/NP2kai -B /tmp/NP2kai/build \
    -DBUILD_I286=ON -DBUILD_SDL=ON \
    -DUSE_SDL=2 -DBUILD_WX=OFF
cmake --build /tmp/NP2kai/build --target sdlnp2kai_sdl2 -j$(nproc)
```

### [DEPRECATED] i286 核心补丁（自动应用）

`cmd_build_i286()` 在编译前自动应用以下补丁：

1. **compiler.h** — 添加 `#define SUPPORT_SASI`（启用 SASI 硬盘控制器）
2. **sxsi.c: `sxsi_issasi()`** — 重写 NC 槽位检测逻辑（参见 §11）
3. **sxsi.c: `gethddtype()`** — 移除 `INVSASI` 标记（非 SASI 标准几何的 HDI 不会被拒绝）
4. **CMakeLists.txt** — 添加 `SUPPORT_DEBUGSS` 编译标志
5. **fontmng.c** — 添加 `#include <SDL2/SDL_ttf.h>`（SDL_ttf 支持）
6. **CMakeLists.txt** — 链接 `libcrypto`

**构建验证**：

```bash
python3 tools/env_setup/install_env.py check
# 输出示例：
#   ia32: /usr/local/bin/wxnp21kai
```

---

## 3. 配置系统 (np2kai.cfg)

### 加载机制

wx 前端 (`wxnp21kai`) 使用 TOML 格式配置文件，默认路径 `~/.config/wxnp21kai/wxnp21kai.toml`。`cmd_test_hdi()` 自动在测试前生成该配置。

### TOML 配置键名

wx 前端的 TOML 键名（按 `~/.config/wxnp21kai/wxnp21kai.toml` 格式）：

```toml
# 自动由 cmd_test_hdi() 生成
title = "Naiz — <game>"
SCSIHDD0 = "/path/to/disks/<game>.hdi"
keyboard = 106
```

### 已知问题

- wx 前端配置文件路径为 `~/.config/wxnp21kai/wxnp21kai.toml`，`cmd_test_hdi()` 自动生成
- BIOS ROM 路径自动发现自配置目录，无需在配置文件中指定

---

## 4. BIOS / 固件

### 文件

| 文件 | 大小 | 说明 |
|------|------|------|
| `bios.rom` | 98304 B | PC-9821 系列 BIOS |
| `font.rom` | 288768 B | 字体 ROM（日文半角/全角字符） |

存储位置：`~/.config/wxnp21kai/`

### 核心匹配规则

```
PC-9821 BIOS (v3.0+)  →  IA32 核心 (wxnp21kai)
```

**跨核心不匹配的症状**：BIOS POST 检查 IMA（Integrated Memory Architecture）失败 → 显示「IMA未启用」→ 键盘输入无效 → 引导卡死。

根因是 PC-9801 BIOS 不认识 PC-9821 的 IMA 硬件，且键盘中断处理程序在两种架构下不兼容。

### 来源

BIOS ROM 来自合法备份或 free86-project 项目。Font ROM 同样。ROM 文件不与源代码一起分发，需在首次开发环境设置时手动配置。

---

## 5. IPL 启动链 (PC-98 HDD Boot)

PC-98 的硬盘启动流程与 IBM-PC 不同，核心差异在 IPL（Initial Program Loader）范式。

### 完整链条

```
NP2kai 内置 IPL ROM
    │ BIOS POST 结束后，从 HDD 读取 LBA 0
    ▼
[LBA 0] IPL1 (Initial Program Loader 1)
    │ 魔数 "IPL1" @ offset 4:8
    │ 加载 IPL2 到内存并跳转
    ▼
[LBA 1-13] IPL2 (13 个扇区)
    │ 读取扇区 1 的分区表，找到激活分区
    │ 加载该分区的 VBR 到内存 0x0060:0000
    ▼
[LBA 136] VBR (Volume Boot Record)
    │ BPB 参数描述文件系统布局
    │ 加载 IO.SYS 到内存
    ▼
IO.SYS → MSDOS.SYS → CONFIG.SYS → AUTOEXEC.BAT
```

### IPL1 数据结构 (LBA 0)

| 偏移 | 大小 | 内容 |
|------|------|------|
| 0x00 | 4 | 跳转指令 / 保留 |
| 0x04 | 4 | 魔数 `49 50 4C 31` ("IPL1") |
| 0x08 | 4 | IPL2 起始 LBA（通常 = 1） |
| 0x0C | 4 | IPL2 扇区数（通常 = 13） |
| 0x10 | 4 | 加载地址（段:偏移） |
| ... | ... | 加载代码 |

**注意**：IPL1 魔数在 **offset 4:8**（不是 offset 3:7），这是早期实现中发现的关键 bug。

### 分区表 (LBA 1, 扇区 1)

PC-98 分区表位于扇区 1，格式与 IBM-PC MBR 不同：

| 偏移 | 大小 | 字段 |
|------|------|------|
| 0x00 | 1 | boot 标志 |
| 0x01 | 1 | sys_id（类型 ID） |
| 0x02 | 2 | 保留 (pad) |
| 0x04 | 1 | head（0-based） |
| 0x05 | 1 | sector（0-based） |
| 0x06 | 2 | cylinder（LE） |

共 16 个分区表项，每项 32 字节。

LBA 计算公式：`cyl × heads × spt + head × spt + sector`

**典型值**（base_msdos5_scsi_48m.hdi）：
- 分区起始：cyl=1, head=0, sector=0 → LBA = 1×8×17 + 0×17 + 0 = 136
- 类型 ID：`0x91`
- 分区大小：47520 扇区（从 LBA 136 开始）

### VBR (Volume Boot Record)

PC-98 VBR 与 IBM-PC 的关键区别：

| 检查项 | IBM-PC | PC-98 |
|--------|--------|-------|
| 有效签名 | 0x55AA @ 0x1FE | **不需要** 0x55AA |
| 有效跳转 | `EB xx` @ 0x00 | `EB xx` @ 0x00 |
| BPB 验证 | bytes_per_sector | bytes_per_sector ∈ {512, 1024, 2048} |

**base_msdos5_scsi_48m.hdi 的 BPB**：

| 字段 | 值 |
|------|-----|
| BytesPerSector | 1024 |
| SectorsPerCluster | 2 |
| ReservedSectors | 1 |
| NumFATs | 2 |
| RootEntries | 3072 |
| TotalSectors16 | 47520 |
| MediaDescriptor | 0xF8 |
| FatSize16 | 47 |
| SPT | 17 |
| Heads | 8 |
| Hidden | 136 |
| TotalSectors32 | 47520 |

#### FAT 布局计算

```
VBR 大小        = 1 扇区 (reserved)
FAT 偏移        = part_offset + 1024       (= 69632 + 1024)
每 FAT 大小     = fat_sectors × bps        = 47 × 1024 = 48128 B
FAT 副本数     = 2
根目录偏移     = FAT 偏移 + 2 × 48128      = 70656 + 96256 = 166912
根目录大小     = ceil(3072 × 32 / 1024)    = 96 扇区
数据区偏移     = 166912 + 96 × 1024        = 166912 + 98304 = 265216
簇大小         = 1024 × 2                  = 2048 B
总簇数         = (total_sectors - 1 - 2×47 - 96) / 2 = (47520 - 191) / 2 = 23664
```

---

## 6. 镜像容器格式

`tools/naiz_img/` 实现了 5 种 PC-98 常见磁盘镜像格式，全部继承自 `DiskImage` 基类。

### DiskImage 基类 (`base.py`)

```python
class DiskImage:
    def __init__(self, path):     # 读入文件到 bytearray
    def _parse(self):             # 子类实现：解析文件头，设定几何参数
    @property sector_size         # 扇区大小
    @property total_sectors       # 总扇区数
    def read_sector(lba) -> bytes # 读单个扇区
    def read_sectors(lba, count)  # 读连续扇区
    def write_sector(lba, data)   # 写单个扇区
    def save(path=None)           # 保存（None 时原子覆盖源文件）
```

### HDI (Anex86) — `hdi.py`

HDI 头部 4096 字节，其后为连续扇区数据。

| 偏移 | 大小 | 字段 |
|------|------|------|
| 0x00 | 4 | reserved |
| 0x04 | 4 | hdd_type（容量 MB 提示） |
| 0x08 | 4 | hdr_size（通常 4096） |
| 0x0C | 4 | data_size |
| 0x10 | 4 | bytes_per_sector |
| 0x14 | 4 | spt |
| 0x18 | 4 | heads |
| 0x1C | 4 | cylinders |

扇区 LBA → 文件偏移：`hdr_size + LBA × bytes_per_sector`

### FDI (Anex86 软盘) — `fdi.py`

头部结构与 HDI 完全相同，几何参数不同（软盘）。实际继承 `HDIImage`。

### D88/D68/D77 — `d88.py`

D88 头部 0x2B0 字节，内含 164 × 4 字节磁道偏移表。每个磁道内扇区有 16 字节头（C/H/R/N），数据紧随其后。软盘格式，本项目主开发用 HDI，D88 为备用。

### RAW — `raw.py`

无头部，整个文件为连续扇区数据。自动检测扇区大小：已知几何表（1.2MB=1024B, 720KB/1.44MB=512B），其余按文件大小对齐。

### NHD (T98-Next) — `nhd.py`

512 字节 ASCII 文本头，以 `T98HDDIMAGE.R0\0` 开头，`key=value` 换行分隔几何参数。数据体从偏移 512 开始。

### 统一入口 (`__init__.py`)

```python
open_image(path)       # 按扩展名自动分派到对应类
create_blank_image()   # 创建空白 HDI 镜像
```

扩展名映射：`.hdi`→HDI, `.fdi`→FDI, `.d88/.d68/.d77`→D88, `.nhd`→NHD, `.raw/.bin/.img`→RAW

---

## 7. 文件系统 (FAT12/FAT16)

`tools/naiz_img/fat.py` 实现了 `NAIZFatFS` 类，参考 98Bridge `fat_fs.py` 的设计思路独立实现。

### 数据结构

```python
@dataclass
class FileEntry:
    name: str            # 8.3 格式文件名（填空格部分已 strip）
    ext: str
    attr: int            # 文件属性
    cluster: int         # 起始簇号
    size: int            # 文件大小
    children: dict       # 子目录项（目录专用）
    is_directory: bool   # 是否目录
```

### BPB 解析 (构造函数)

1. 自动分区检测（或指定 `part_offset`）
2. 读 VBR → 验证 `EB` 跳转 + 合理 BPB（bps ∈ {512, 1024, 2048}）
3. 计算文件系统布局：FAT 偏移、根目录偏移、数据区偏移
4. 根据 `total_clusters < 4085` 自动选择 FAT12 / FAT16
5. 加载 FAT 表 → 构建目录树

### 目录项解析

目录项遍历的关键过滤逻辑：

| 属性值 | 含义 | 处理 |
|--------|------|------|
| `== 0x0F` | ATTR_LFN（长文件名） | **跳过**（精确匹配，非位掩码） |
| `== 0x08` 或 `== 0x28` | ATTR_VOLUME_ID | **跳过** |
| `& 0x10` | 子目录 | 递归解析 |
| `& 0x20` | 归档文件 | 正常读取 |

**关键修正**：ATTR_LFN 必须用 `== 0x0F` 而非 `& 0x0F`，因为 IO.SYS 属性 `0x27`（System+Archive+Hidden）的特定位与 `0x0F` 不匹配，但 `& 0x0F` 会错误匹配导致 IO.SYS 被跳过。

### 簇链遍历

```python
# FAT12：12-bit 打包格式
offset = cluster + (cluster // 2)
word = struct.unpack('<H', fat_data[offset:offset+2])[0]
value = (word >> 4) if (cluster & 1) else (word & 0x0FFF)

# FAT16：直读
value = struct.unpack('<H', fat_data[cluster * 2:cluster * 2 + 2])[0]
```

EOC 值：FAT12 = `0x0FF8`，FAT16 = `0xFFF8`

### inject_into_hdi() — 增量 FAT 注入

这是当前工具链的核心入口（替代旧 `write_back_from_directory()` 全量重建），见 `tools/naiz_img/inject_common.py`。

**流程**：

```
1. 打开复制后的 HDI，解析 FAT16
2. 替换 AUTOEXEC.BAT（优先原地覆盖，空间不足时重分配簇链）
3. 替换 CONFIG.SYS（同上）
4. 查找或创建游戏子目录（如 DEMO-A1/）
5. 遍历 games/<name>/ 下每个文件：
   a. 已存在 → 原地覆盖或重分配
   b. 新文件 → 分配簇链 + 创建目录项
6. 写回所有 FAT 副本
7. img.save() → 写出 HDI 文件
```

**优点 vs 全量重建**：
- IO.SYS/MSDOS.SYS 的簇链地址不变，VBR 无需任何调整
- 只修改变化的扇区，写入速度快
- 基座镜像原有碎片分布完全保留

---

## 8. 分区检测 (`partition.py`)

### 双方案检测

```python
def detect_partitions(img) -> list[PartitionEntry]:
    parts = detect_mbr(img)     # 优先尝试 MBR
    if parts: return parts
    return detect_pc98(img)     # 失败则回退到 PC-98 IPL
```

### MBR 检测

标准 IBM-PC MBR：
- 校验 `0x1FE` 处 55AA 签名
- 解析 4 个分区表项（`0x1BE` 开始，每项 16 字节）
- LBA 从 CHS 转换或直接读 `offset 8` 的 LBA 字段

### PC-98 IPL 检测

PC-98 专用：
- 校验 sector 0 的 `IPL1` 魔数（`offset 4:8`）
- 解析 sector 1 的 16 个分区表项（每项 32 字节）
- PC-98 分区表项格式：`boot@0, sys_id@1, pad@2-3, head@4, sector@5(0-based), cyl@6-7(LE)`
- LBA = `cyl × heads × spt + head × spt + sector`

### base_msdos5_scsi_48m.hdi 实际检测值

| 检测项 | 值 |
|--------|-----|
| sector 0 IP1 魔数 | `49 50 4C 31` @ offset 4 |
| 分区扇区 | LBA 1 (sector 1) |
| 分区起始 | LBA 136 (cylinder 1, head 0, sector 0) |
| 分区类型 | 0x91 |
| 分区大小 | 47520 扇区 |

---

## 9. 工具链集成 (`inject.py`)

### 命令行接口

```bash
python -m tools.naiz_img.inject --game demo-A1
python -m tools.naiz_img.inject --game mygame -o disks/mygame.hdi
python -m tools.naiz_img.inject --game demo-A1 --preview   # 预览
python -m tools.naiz_img.inject --game demo-A1 --list-files # 列出基座镜像文件
```

### 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-g, --game` | 必填 | 游戏名，对应 `games/<name>/` |
| `-b, --base` | `tools/base_msdos5_scsi_48m.hdi` | 基座 HDI |
| `-o, --output` | `disks/<game>.hdi` | 输出路径 |
| `--preview` | false | 只预览文件清单 |
| `--list-files` | false | 列出基座镜像全部文件 |
| `--no-config` | false | 不覆写 CONFIG.SYS |
| `--no-autoexec` | false | 不覆写 AUTOEXEC.BAT |
| `-y, --yes` | false | 非交互模式 |

### 工作流程

```python
shutil.copy2(base_hdi, output)                # 复制基座（完整保留 IPL/VBR）
inject_into_hdi(output, game, game_dir,       # 增量 FAT 编辑
                no_config=..., no_autoexec=...)
```

### `ref_config/` 文件内容

```
CONFIG.SYS (tools/ref_config/CONFIG.SYS):
FILES=30
SHELL=\COMMAND.COM /P

AUTOEXEC.BAT:
  （由 generate_autoexec() 运行时生成，使用 \ 根相对路径）
```

**CONFIG.SYS 路径格式**：必须使用根相对路径 `\`（盘符 `C:\` 在此阶段未分配），详见 §11.4。

### makegame.sh 集成

`makegame.sh` 统一管理制作、测试、构建流程：

```bash
./makegame.sh make demo-A1     # 制作 HDI
./makegame.sh test demo-A1     # 模拟器启动测试
./makegame.sh build demo-A1    # 编译 + 制作
./makegame.sh                  # 交互模式
```

---

## 10. 测试与启动流程

### 测试启动链

```
makegame.sh test <game>
    │ 激活 Python venv
    │ 调用 install_env.py test-hdi --hdi <hdi_path>
    ▼
cmd_test_hdi(hdi_path)
    │ 生成 logs/test_<game>_<timestamp>.log
    │ 生成 ~/.config/wxnp21kai/wxnp21kai.toml（SCSIHDD0 指向所选 HDI）
    │ 复制 BIOS/Font ROM 到配置目录
    │ 等待 Enter 确认
    ▼
NP2kai (wxnp21kai) 启动
    │ 加载 BIOS → IPL → IO.SYS → CONFIG.SYS → AUTOEXEC.BAT
    ▼
ENGINE.EXE 运行 → 画面输出
```

### SDL 环境设置

（wx 前端不依赖 SDL 环境变量，SDL 前端已弃用。）

### 日志

日志写入 `logs/test_<game>_<timestamp>.log`，内容包含：
- HDI 路径、时间戳
- NP2kai 二进制路径、配置路径
- NP2kai 标准输出/标准错误

---

## 11. 已知问题与解决方案

### 11.1 BIOS/核心不匹配 → "IMA未启用" 键盘死锁

**症状**：NP2kai 启动后显示「IMA未启用」并等待按键，键盘无效。

**根因**：使用 IA32 核心 (`wxnp21kai`) 加载 PC-9801 BIOS ROM（N88-BASIC(86) v2.0）。PC-9821 硬件架构差异导致 IMA 检测失败 + 键盘中断不兼容。

**解决**：使用 IA32 核心 (`wxnp21kai`) + 匹配的 PC-9821 BIOS。i286 核心 (`sdlnp2kai_sdl2`) 不再作为开发目标。

**涉及文件**：`17-bios-rom-issue.md`

---

### 11.2 SASI 硬盘控制器未启用

**症状**：HDI 镜像通过 `HDD1FILE` 加载后，MS-DOS 下 RSDRV.SYS 无法检测到硬盘，C: 盘不出现。

**根因**：[DEPRECATED] i286 SDL/Unix 构建未定义 `SUPPORT_SASI` 宏。SASI 控制器代码 (`cbus/sasiio.c`) 被 `#if defined(SUPPORT_SASI)` 守卫，编译时不包含。

**解决**：在 `sdl/unix/compiler.h` 添加：

```c
#define SUPPORT_SASI
```

**附带修复**：`sdl/np2.c` 中 `IMAGETYPE_SASI_IDE`/`IMAGETYPE_SASI_IDE_CD` 分支引用了 `np2cfg.idetype[j]`，该字段仅在 `SUPPORT_IDEIO` 下存在。需用 `#if defined(SUPPORT_IDEIO)` 守卫。

**状态**：`cmd_build_i286()` 已包含自动补丁。

**涉及文件**：`sdl/unix/compiler.h`, `sdl/np2.c`, `cbus/sasiio.c`

---

### 11.3 sxsi_issasi() 检测逻辑缺陷

**症状**：即使 `SUPPORT_SASI` 已定义，`pccore.hddif` 中 `PCHDD_SASI` 标志位仍不置位，SASI 控制器不初始化。

**根因**：`fdd/sxsi.c` 的 `sxsi_issasi()` 原逻辑对所有 4 个 SASI 槽位统一要求 `(drv < 0x02) && (devtype == SXSIDEV_HDD) && (flag & SXSIFLAG_READY)`。当 HDD1 连接、HDD2 未配（devtype=NC）时，第二个槽位进入 `else` 分支直接返回 `FALSE`。

**解决**：重写函数，区分三种槽位类型：
- `drv<0x02`：允许 HDD(READY,!INVSASI) 或 NC；其他返回 FALSE
- `drv≥0x02`：必须为 NC（纯 SASI 模式预期行为）；非 NC 返回 FALSE
- 至少有一个 READY HDD 即可返回 TRUE

```c
BOOL sxsi_issasi(void) {
    REG8 drv;
    SXSIDEV sxsi;
    BOOL ret = FALSE;
    for (drv = 0x00; drv < 0x04; drv++) {
        sxsi = sxsi_getptr(drv);
        if (sxsi == NULL) continue;
        if (drv < 0x02) {
            if (sxsi->devtype == SXSIDEV_HDD) {
                if (sxsi->flag & SXSIFLAG_READY) {
                    if (sxsi->mediatype & SXSIMEDIA_INVSASI)
                        return(FALSE);
                    ret = TRUE;
                }
            }
            else if (sxsi->devtype != SXSIDEV_NC)
                return(FALSE);
        }
        else {
            if (sxsi->devtype != SXSIDEV_NC)
                return(FALSE);
        }
    }
    return(ret);
}
```

**状态**：`cmd_build_i286()` 已包含自动补丁。

**涉及文件**：`fdd/sxsi.c`

---

### 11.4 CONFIG.SYS 路径格式：引导阶段无盘符

**症状**：CONFIG.SYS 中使用 `C:\DOS\RSDRV.SYS` 等带盘符路径时，MS-DOS 报告文件未找到，所有驱动加载失败。

**根因**：MS-DOS 引导顺序：
1. VBR 加载 IO.SYS
2. IO.SYS 加载 MSDOS.SYS
3. MSDOS.SYS 处理 CONFIG.SYS → **此时盘符尚未分配**
4. 所有 DEVICE= 处理完毕后，MS-DOS 才分配盘符 (A:, B:, C:...)

因此 CONFIG.SYS 中必须使用根相对路径 `\`（无盘符前缀）。

**解决**：
- `DEVICE=C:\DOS\RSDRV.SYS` → `DEVICE=\DOS\RSDRV.SYS`
- `SHELL=C:\COMMAND.COM /P` → `SHELL=\COMMAND.COM /P`

AUTOEXEC.BAT 虽在盘符分配后执行（技术上可用 `C:\`），但为保持统一，`generate_autoexec()` 也使用 `\` 根相对路径。

**涉及文件**：`tools/ref_config/CONFIG.SYS`

---

### 11.5 键盘输入：BIOS 键状态数组 vs 直接端口 I/O

**症状**：引擎通过直接读取 I/O 端口 (0x41/0x43) 获取键盘状态，导致与 BIOS 键盘中断 (INT 09h) 冲突，键值读取不稳定。

**解决**：改用 BIOS 键状态数组 `0x052A` (KEY_STATUS_AREA) 判断按键。该数组由 INT 09h 中断处理程序维护，与 FIFO 读取无冲突。

**涉及文件**：`core/plat/pc98/hal_pc98.c` — `hal_input_state()`

---

### 11.6 NP2kai 系统僵死（Wayland 键盘独占）

**症状**：NP2kai 启动后，系统全部功能僵死（无法切换 TTY，无法操作任何窗口）。鼠标仍可移动。

**根因**：NP2kai 通过 SDL2 Wayland 后端运行时，SDL 窗口默认抓取键盘独占输入（`SDL_WINDOW_INPUT_FOCUS` + Wayland 键盘锁定）。键盘事件全部被 NP2kai 消耗。

**解决**：不使用 `SDL_VIDEODRIVER=wayland`，让 SDL 使用默认驱动（通常是 x11）。或设置 `timeout` 保护。

**涉及文件**：`tools/sdl_env.sh`

---

### 11.7 引擎缺少自动退出机制

**症状**：测试时 NP2kai 或引擎没有自动退出机制，需要手动关闭窗口。

**解决**：引擎实现 300 帧（约 5 秒）自动退出循环。

**涉及文件**：`core/engine/main.c`

---

### 11.8 HDI 文件不可写（O_DIRECT 问题）

**症状**：`strace` 显示 VBR 读取次数是正常的 8 倍，每次 INT 1Bh 只消耗 256 字节。

**根因**：`O_DIRECT` 打开模式导致缓冲区未对齐，VBR 读取效率极低。

**解决**：移除 `O_DIRECT` 标志。

**涉及文件**：原始 `tools/hdi_tool/`（已弃用，当前基于 `tools/naiz_img/` 无此问题）

---

### 11.9 IPL1 魔数偏移错误

**症状**：`detect_pc98()` 从 sector 0 offset 3:7 读取魔数，实际 IPL1 在 offset 4:8。

**解决**：修正为 `sec0[4:8] != b'IPL1'`。

**涉及文件**：`tools/naiz_img/partition.py`

---

### 11.10 ATTR_LFN 过滤方式错误

**症状**：根目录中 IO.SYS（attr=0x27）和 MSDOS.SYS（attr=0x27）被错误跳过。

**根因**：使用 `attr & 0x0F != 0` 而非 `attr == 0x0F`。0x27 & 0x0F = 0x07 ≠ 0，导致误过滤。

**解决**：使用 `attr == ATTR_LFN` 精确匹配。

**涉及文件**：`tools/naiz_img/fat.py`

---

### 11.11 DBLSPACE.BIN 导致启动时"how many files"提示

**症状**：MS-DOS 启动过程中弹出提示询问文件数量，需人工输入后继续。

**根因**：IO.SYS 自动加载 DBLSPACE.BIN 驱动，该驱动扫描所有新分配的簇，将游戏文件数据误判为 DriveSpace 压缩卷（CVF），触发交互式询问。

**解决**：`inject_into_hdi()` 在 Step 0 自动将 DBLSPACE.BIN 的根目录项标记为 0xE5（已删除）。FAT 簇链（81-112）未释放但不再被引用，对游戏盘无影响。

**涉及文件**：`tools/naiz_img/inject_common.py`

---

### 11.12 新分配目录簇残留数据导致 CD 失败

**症状**：AUTOEXEC.BAT 执行 `CD \DEMO-A1` 失败，停留在命令提示符。

**根因**：`inject_into_hdi()` Step 4 为新游戏目录分配一个簇后，未将簇数据清零。该簇之前分配给一个 EXE 文件，残留 `MZ%` 魔数和二进制数据。目录解析代码读取簇数据后，将残留 EXE 头部误识别为合法目录项（ATTR=0x07），导致 MS-DOS 认为目录损坏。

**解决**：分配目录簇后立即写入 `b'\x00' * fs.cluster_size` 清零。当前版本尚未实现此修复。

**涉及文件**：`tools/naiz_img/inject_common.py`

---

## 12. 快速参考

### 常用命令速查

| 操作 | 命令 |
|------|------|
| 编译引擎 | `make -C core clean all` |
| 注入游戏 | `./makegame.sh make <name>` |
| 完整测试 | `make -C core test` |
| 启动模拟器 | `./makegame.sh test <game>` |
| 检查环境 | `python3 tools/env_setup/install_env.py check` |
| 预览文件 | `./makegame.sh make <name> --preview` |
| 列出基座文件 | `./makegame.sh list-files` |

### 启动检查清单

HDD 相关问题按序排查：

- [ ] `bios.rom` 来源是否与核心匹配（PC-9821 BIOS → IA32 核心）
- [ ] NP2kai 二进制是否正确（`wxnp21kai` IA32 核心）
- [ ] `sdl/unix/compiler.h` 是否包含 `#define SUPPORT_SASI`
- [ ] `sxsi_issasi()` 逻辑是否允许 HDD2/3/4 槽位为 NC
- [ ] CONFIG.SYS 路径是否使用 `\` 根相对格式（非 `C:\`）
- [ ] `wxnp21kai.toml` 使用 `SCSIHDD0`（SCSI 方式）
- [ ] HDI 是否已用最新 `inject_into_hdi()` 重建
- [ ] IO.SYS 是否为根目录第一个文件
- [ ] `SHIFT+Enter` 是否已用以跳过 MS-DOS 启动菜单（如适用）

### 文件路径速查

| 类别 | 路径 |
|------|------|
| **源文件** | `core/engine/`, `core/plat/` |
| **工具链** | `tools/naiz_img/`（9 个 Python 模块） |
| **游戏项目** | `games/<name>/` |
| **输出镜像** | `disks/<name>.hdi` |
| **基座镜像** | `tools/base_msdos5_scsi_48m.hdi` |
| **配置文件** | `~/.config/wxnp21kai/wxnp21kai.toml` |
| **BIOS/Font** | `~/.config/wxnp21kai/bios.rom`, `~/.config/wxnp21kai/font.rom` |
| **测试日志** | `logs/test_<game>_<timestamp>.log` |
| **文档** | `docs/A02-NP2kai与镜像工具链.md`, `devdocs/18-98Bridge方案.md`, `devdocs/19-实现方案.md` |

### 来源声明

`tools/naiz_img/` 全部 9 个模块参考 98Bridge (MIT) 的设计思路独立实现。
来源: `https://github.com/NullMagic2/98Bridge`
