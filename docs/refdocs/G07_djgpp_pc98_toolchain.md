# DJGPP 在 PC-98 / NP2kai 上的技术分析

> **来源**: [target-earth.net/wiki/doku.php?id=blog:pc98_devtools](https://www.target-earth.net/wiki/doku.php?id=blog:pc98_devtools)
> **作者**: John (Target-Earth)
> **日期**: 2020-08-22（最后一版），Naiz 项目二析 2026-06-09

---

## 一、文档概要

这篇文章是现今少数关于**英语 PC-98 开发工具**的完整参考文档。作者系统地记录了：

1. 可在 PC-98 上使用的编译器（Borland Turbo C, Microsoft Quick C, DJGPP）
2. DJGPP v2.03 针对 PC-98 的补丁机制——如何打 patch、编译 libc、解决 make 3.71 的 bug
3. 在**实机 PC-9821 + DOS 6.22 + VCPI** 和 **NP2kai 仿真器** 上验证 DJGPP 程序的截图
4. 样本 Makefile、示例 C 代码、优化选项

## 二、对 Naiz 项目至关重要的发现

### 2.1 DJGPP 在 NP2kai 上运行无误

文章提供了 **NP2kai 运行 DJGPP 程序的截图**，证明：

```
PC-98 平台检测程序（单二进制）
  ├── 在 Dosbox (AT MS-DOS) 运行 → 输出 "Hello, PC world"
  └── 在 NP2kai (PC-98 MS-DOS) 运行 → 输出 "Hello, PC98 world"
```

作者通过 libc 补丁中的 `__crt0_mtype` 机制在运行时检测平台类型（PCAT vs PC98），并分支到底层 BIOS/硬件调用。

### 2.2 保护模式切换路径：VCPI 而非裸 CR0

这是**推翻 Naiz AI 规则中 "DJGPP 禁止" 禁令的核心发现**：

```
DJGPP 程序的保护模式切换链路：

  DJGPP 二进制 (MZ .exe)
     → go32-v2.exe (DJGPP own DOS extender)
        → DPMI32.EXE (MS-DOS 5.0 DPMI 服务)
           → VEM486.EXE (VCPI 服务，NP2kai 支持)
              → 保护模式 (32-bit ring 1)
```

关键点：
- DJGPP 的 go32 不执行裸 `mov cr0` PE 位切换——它通过 VCPI 接口请求保护模式
- VCPI 由 VEM486.EXE 提供——**我们已在 CONFIG.SYS 中加载**
- NP2kai 的 IA-32 核心完全支持 VCPI/DPMI 标准的保护模式切换
- AGENTS.md 中 "CR0 PE 位切换，NP2kai 不支持" 适用于 PMODE/W 等裸切换方案，**不适用于 DJGPP 的 go32 + DPMI32 路径**

### 2.3 版本与补丁细节

| 组件 | 版本 | 说明 |
|------|------|------|
| DJGPP | **v2.03** | 最后一个有 PC-98 patch 的版本，不能直接用 v2.05+ |
| GCC | **2.95.2** | 编译器（在 DJGPP v2.03 中内含） |
| libc | v2.03 + PC-98 patch | 关键：patch 替换了全部 BIOS/console 调用为 PC-98 版本 |
| go32-v2 | 定制版 | DJGPP 的 32-bit DOS extender，依赖 DPMI |
| DPMI32.EXE | MS-DOS 5.00 附带 | PC-98 版 MS-DOS 5.00 中的 DPMI 服务 |
| make | **4.3 (修复版)** | 原 3.71 版在 PC-98 FAT32 上有文件发现 bug |
| VCPI | VEM486.EXE | 实机和 NP2kai 都支持 |

### 2.4 实机测试时发现的问题

作者在实机 PC-9821 上遇到 DJGPP make 3.71 无法找到 Makefile 的 bug——这是 PC-98 FAT32 文件系统的兼容性问题。修复方案是替换为 make 4.3。

## 三、运行时链路分析

### 3.1 作者验证的链路

```
CONFIG.SYS:
  DEVICE=EMM386.EXE (或 VEM486.EXE)    ← VCPI 服务

AUTOEXEC.BAT / 命令行:
  DPMI32.EXE 或 DPMI.EXE              ← DPMI 服务
  程序.exe                            ← DJGPP 二进制 + go32 stub
```

### 3.2 Naiz 现有的运行时链

```
CONFIG.SYS:
  DEVICE=A:\VEM486.EXE /U             ← VCPI 服务 ✅

AUTOEXEC.BAT:
  SET DOS16M=1
  ENGINE.EXE                          ← DOS/4GW LE executable
```

对比：
- DJGPP 方案的 DPMI host 是 DPMI32.EXE（外部），而我们用的是 DOS/4GW（嵌入 ENGINE.EXE 的 MZ stub 内）
- 两种方案都依赖 VEM486.EXE 提供 VCPI **✅ 已存在**
- 链条底部是同一套 NP2kai 保护模式支持

### 3.3 为何 DOS/4GW 方案优于 go32+DPMI32 方案

| 方面 | DOS/4GW (现用) | go32 + DPMI32 (DJGPP 文章方案) |
|------|---------------|-------------------------------|
| 部署文件数 | **1 个** (ENGINE.EXE 自包含) | **3 个** (app.exe + go32-v2.exe + dpmi32.exe) |
| BIOS/FAT 兼容性 | 已知良好 ✅ | 作者遭遇 make bug |
| 已验证的 NP2kai 运行 | ✅ love es×××× + Naiz engine | ✅ 文章截图 |
| 启动速度 | 嵌入 stub，单文件 | 外部扩展器加载，需额外 I/O |
| PC-98 平台检测 | DOS/4GW 不关心平台 | DJGPP crt0 自动检测 PC-98 |

## 四、DJGPP 在 Naiz 中的应用可能性

### 4.1 编译方式选择

| 方式 | 工具链 | 优点 | 缺点 |
|------|--------|------|------|
| **原生 GCC** | 在 NP2kai 内运行 DJGPP suite 本身 | 经作者验证 | 编译速度极慢（文章提到 "半小时"）；开发体验差 |
| **Linux 交叉编译** | `i586-pc-msdosdjgpp-gcc` 包 | 现代开发体验，CI 友好，速度快 | 需验证 NP2kai 兼容性；DPMI host 兼容性未知 |

两种方式产生相同格式的二进制——区别在编译速度。

### 4.2 若使用 DJGPP 交叉编译器

```
交叉编译链：
  i586-pc-msdosdjgpp-gcc -O2 -march=i486 source.c -o app.exe

运行时文件：
  app.exe (MZ .exe)
  └── 需 go32-v2.exe + DPMI32.EXE 在同一个 FAT 分区
```

### 4.3 引擎迁移成本（Open Watcom → DJGPP）

| 组件 | Open Watcom (当前) | DJGPP | 迁移成本 |
|------|-------------------|-------|---------|
| 编译器 | `wcl386 -bt=dos -l=dos4g` | `i586-pc-msdosdjgpp-gcc` | Makefile 重写 2h |
| 启动代码 | Open Watcom crt0.asm | DJGPP crt0.c + PC-98 patch | 需改写 ~50 行 |
| inline asm | `#pragma aux` / `__emit` | `__asm__()` (AT&T 语法) | 改写每个 asm 块 |
| DPMI host | DOS4GW (嵌入) | CWSDPMI / DOS4GW | 选 DOS4GW 可兼容 |
| 链接脚本 | Open Watcom `.lnk` | GNU ld `.ld` 脚本 | 需从零编写 |
| VRAM 访问 | `(volatile uint8_t *)0xA8000L` | 相同（flat 模式） | 零成本 |
| HAL 边界 | `core/plat/hal.h` (outb/inb) | 相同（GCC inline asm） | 中等 |

### 4.4 何时值得迁移

- ✅ Open Watcom wcl386 遇到编译器 bug（C89 标准兼容问题）
- ✅ 需要 C11/C17 特性（`_Generic`、`_Bool`、`_Alignas` 等）
- ✅ 需要链接第三方 C 库（zlib、SDL 等——GCC 有广泛支持）
- ✅ 需要更先进的优化（LTO、profile-guided optimization）
- ❌ "因为它是 GCC" → 不够充分

## 五、对 DGJPP 技术路线的评估

### 5.1 已确认

- DJGPP v2.03 程序的保护模式切换走 VCPI 路径——**不需要 NP2kai 支持裸 CR0 写**
- go32-v2.exe + DPMI32.EXE 方案在 NP2kai 上已验证 ✅
- 需要的 VCPI 服务 VEM486.EXE 已内置 ✅

### 5.2 未验证

- Linux 交叉编译器 `i586-pc-msdosdjgpp-gcc` 生成的程序在 NP2kai 上是否运行
- DJGPP 程序结合 DOS/4GW（替换 go32+DPMI32）的兼容性
- 在 NP2kai 上多帧渲染、键盘输入、串口等外围功能是否完好

### 5.3 Naiz 当前策略

| 项目 | 选择 |
|------|------|
| **主编译器** | Open Watcom `wcl386`（已验证 NP2kai 运行正常） |
| **DPMI 运行时** | DOS4GW.EXE（嵌入 ENGINE.EXE） |
| **DJGPP 状态** | **备选技术路线（未在主流程验证）** |

DJGPP 方案保持观察但不启用在主工程，等待以下条件之一：
- Open Watcom 出现功能瓶颈
- 有人完成 DJGPP 交叉编译器 + NP2kai 端到端验证
- 需要 GCC 特有优化或第三方库链接

### 5.4 后续验证计划

若决定启用 DJGPP：

```bash
# 1. 安装 DGJPP 交叉编译器
start.sh djgpp

# 2. 最小程序验证
i586-pc-msdosdjgpp-gcc -o test.exe test.c
# 注入 HDI → NP2kai 运行 → 检查串口输出

# 3. 全引擎迁移（需 2-4 天工作量）
#   - 重写 Makefile
#   - 改写 inline asm 为 AT&T 语法
#   - 改写链接脚本
#   - 选择性：保留 DOS4GW 或切换到 go32+DPMI32
```

## 六、对 NP2kai 源码的启示

文章确认了 NP2kai 支持 VCPI/DPMI 保护模式链路。这意味着 NP2kai 的内存管理器 (VEM486.EXE) + IA-32 核心有能力处理以下类别的 DOS extender：

- ✅ DOS/4GW（已验证——love es×××× 和 Naiz engine）
- ✅ go32-v2 + DPMI32（文章截图，DJGPP v2.03）
- ❓ CWSDPMI（文章未测试，但机制相同）
- ❓ PMODE/W（裸 CR0 写——NP2kai 可能不支持，文章未涉及）

这也部分解释了为什么我们在 NP2kai 中对 display pipeline 的修复能在引擎中正常工作——NP2kai 的底层 IA-32 核心是完整的，问题只在 GDC 命令模拟层。

## 七、来源

- 原始文章: https://www.target-earth.net/wiki/doku.php?id=blog:pc98_devtools
- DJGPP v2.03 PC-98 patch: https://www.mfp.gr.jp/users/takas/prog/djgpp.html
- DJGPP CVS PC-98 branch: https://github.com/PC-98/djlsr
- PC-98 MS-DOS 5.0 DPMI info: https://virtuallyfun.com/wordpress/2016/06/21/ms-dos-5-0-dpmi/
