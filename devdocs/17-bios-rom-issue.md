# BIOS ROM 兼容性问题

## 问题描述

NP2kai 启动后，MS-DOS 6.20 显示「IMA未启用」并等待按键，但键盘输入完全无效，导致引导过程卡死。

## 根因分析

| 组件 | 版本/类型 | 说明 |
|------|----------|------|
| `bios.rom` | PC-9801 系列 (N88-BASIC(86) v2.0) | 98304 bytes, 0xE8000 加载 |
| NP2kai (IA32) | `sdlnp21kai_sdl2` (NP21kai) | **当前开发目标**，IA32 核心，模拟 PC-9821 (486+) |
| NP2kai (旧) | `sdlnp2kai_sdl2` (NP2kai) | [DEPRECATED] i286 核心，模拟 PC-9801 (286) |

### BIOS ROM 来源

当前使用的 `bios.rom`（98304 bytes，位于 `core/sdlnp21kai/bios.rom` 或 `core/sdlnp2kai/bios.rom`）经检查包含字符串「NEC N-88 BASIC(86) version 2.0」，说明它来自 **PC-9801 系列**（8086/286 时代）。

NP2kai 的 IA32 核心（NP21kai）模拟的是 PC-9821 系列（486+ 时代），其硬件架构与 PC-9801 存在显著差异：

- **键盘控制器**：PC-9821 使用不同的键盘接口，BIOS 中的键盘中断处理程序不兼容
- **IMA (Integrated Memory Architecture)**：PC-9821 特有，PC-9801 BIOS 无法检测
- **A20 门控**：286 与 486 的 A20 处理方式不同
- **中断控制器**：存在硬件差异

### 连锁反应

1. BIOS POST 检查 IMA → 失败（PC-9801 BIOS 不认识 PC-9821 的 IMA）
2. 显示「IMA未启用」→ 调用 INT 09h 等待按键
3. 键盘中断处理程序不兼容 → 按键事件不被识别 → 无限等待

## 解决方案

### 方案 A（已实施）：使用 IA32 核心

NP2kai 使用 IA32 核心（PC-9821 模拟），当前为主要开发目标。

配置路径：
- IA32 版：`$XDG_CONFIG_HOME/sdlnp21kai/np21kai.cfg`
- [DEPRECATED] i286 版：`$XDG_CONFIG_HOME/sdlnp2kai/np2kai.cfg`

### 方案 B：寻找 PC-9821 BIOS ROM

获取适配 PC-9821 的 BIOS ROM（版本 3.0 以上），替换当前文件。NP2kai 的 IA32 核心需要对应 9821 的 BIOS。

潜在来源：
- 从 PC-9821 实机 dump
- ReC98 项目中可能包含 BIOS 信息
- 其他 PC-98 模拟器（如 Neko Project 21/W）的 BIOS 文件

### 方案 C：跳过 IMA 检查（不推荐）

在 IO.SYS 层面绕过 IMA 检查需要二进制修改 DOS 系统文件，复杂且不可靠。

## 当前状态

已切换到 **IA32 核心**：`sdlnp21kai_sdl2` 为主要开发目标。[DEPRECATED] `sdlnp2kai_sdl2` (i286 核心) 不再使用。

## 下次继续开发

HDI 镜像（`disks/*.hdi`）不在 git 跟踪范围内，不会同步到远程仓库。**下次继续开发时，必须先重新生成 HDI：**

```bash
./make_hdi.sh       # 选择项目 demo-A1，生成 disks/demo-A1.hdi
./test_hdi.sh       # 启动 NP2kai 进行测试
```

`make_hdi.sh` 会根据 `games/<name>/` 下的部署文件和 `tools/ref_config/` 的系统配置，重新构建 FAT16 磁盘镜像。确保 `projects/demo-A1/` 已最新编译（`make -C projects/demo-A1`）。

## 相关文件

- `test_hdi.sh` — 启动脚本，使用 `sdlnp2kai_sdl2`
- `core/sdlnp2kai/bios.rom` — BIOS ROM 文件（从旧目录复制）
- `core/sdlnp2kai/font.rom` — 字体 ROM 文件
- `core/sdlnp2kai/np2kai.cfg` — 模拟器配置文件
