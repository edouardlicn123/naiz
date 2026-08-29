# Naiz Engine (core/)

PC-98 视觉小说引擎核心（DOS/4GW 32-bit 保护模式）。

## 目录说明

- `engine/` — 平台无关核心逻辑（NB 剧本解释器、渲染、图层、存档、菜单）
- `lib/` — 平台无关可复用库（字形、LZ4、MAG 解码、i18n、文件读取）
- `plat/` — 平台抽象层 (HAL)，PC-98 硬件驱动（键盘、鼠标、视频、串口、GDC）
- `build/` — 构建输出（.o 对象文件）
- `Makefile` — 构建文件（`make` 编译 engine.exe / engine_a.exe / diag.exe）

## 构建

```bash
make -C core          # 编译 engine.exe + engine_a.exe（0 errors / 0 warnings）
make -C core diag     # 编译 diag.exe（串口诊断）
make -C core clean    # 清理 build/ 与可执行文件
```

需要 Open Watcom `wcl386`（见 `build.sh` / `detect_watcom.sh`，由 start.sh 安装）。

## 架构约束

- `engine/` 只能通过 `core/plat/hal.h` 访问硬件；`outb()`/`inb()`/INT 18h 只能在 `plat/` 中调用。
- `lib/` 完全密封，仅依赖 C 标准库。
- 详细规范见 `docs/B91-构建环境与参考速查.md`。

## 文件版权注释规则

所有 `core/` 下的源文件，如果其代码**复制或改编自 ref_projects/ 中的参考项目**，必须在文件开头添加注释块：

```c
/*
 * 来源项目：<项目名称>
 * GitHub:   <GitHub URL>
 * 许可证：   <许可证类型>
 */
```

如果是独立新写的文件则无需添加。详见 `AGENTS.md`。
