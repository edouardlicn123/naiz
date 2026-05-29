# Naiz — AI 编程规则 (Rules for AI Agents)

## 目录结构 (Directory Layout)

```
Naiz/
├── core/                    # Engine source (C, gcc-ia16)
├── tools/                   # Python toolchain
│   ├── naiz_img/            #   HDI/FAT toolchain (inject.py, inject_common.py, hdi.py, fat.py, ...)
│   ├── diag/                #   诊断工具 (gen_com, hdi_patch_autoexec, hdi_find_file, hdi_integrity, np2kai_screenshot, np2kai_serial)
│   ├── inject_common.py          #   增量注入核心
│   └── ref_config/          #   CONFIG.SYS
│   └── base_msdos5_scsi_48m.hdi           #   Base HDI image (read-only, MS-DOS 5.0 48MB)
├── ref_projects/            # Read-only git submodules (references)
├── projects/                # Engineering projects (source code, build files)
├── games/                   # Deployable game files (injected into HDI, built from projects/)
├── disks/                   # Generated HDI disk images
├── docs/                    # Specifications (A-prefix: engine, toolchain, HDI, dev guides)
├── devdocs/                 # Development notes (numbered 01-30)
│   ├── MHVN98/              #   MHVNVisualNovelEngine 逆向笔记
│   ├── 01-*.md
│   ├── 02-*.md
│   └── ...
├── make_hdi.sh              # （已删除，由 makegame.sh 替代）
├── makegame.sh              # Game build/test workflow (make/test/build)
├── setup_env.sh             # 开发环境安装菜单
└── start.sh                 # Launcher menu
```

## HDI 镜像制作 (HDI Image Creation)

使用 `makegame.sh make <name>` 制作启动盘，详细方案见 `docs/A04-HDI制作方案.md`。

**核心流程**：`makegame.sh make` → `tools/naiz_img/inject.py` (Python 工具链)

**要点**：
- 基于已知可启动的 `tools/base_msdos5_scsi_48m.hdi`（MS-DOS 5.0 48MB，只读），保留完整 IPL/VBR/boot chain
- **增量注入**：复制基座 → `inject_common.inject_into_hdi()` 在 FAT 层精准写入文件，不重建整个文件系统
- 注入三部分内容：`tools/ref_config/CONFIG.SYS`（系统配置）+ `generate_autoexec()` 生成的 AUTOEXEC.BAT + `games/<name>/` 游戏文件；注入时自动移除 DBLSPACE.BIN
- 输出到 `disks/<name>.hdi`
- `tools/naiz_img/` 镜像工具链参考 98Bridge (MIT) 设计思路独立实现，涵盖 5 种容器格式（HDI/FDI/D88/Raw/NHD）和 FAT12/FAT16 文件系统
- IO.SYS/MSDOS.SYS 保持基座镜像原有簇链不变，无需重排
- CONFIG.SYS 必须使用根相对路径 `\`（MS-DOS 引导阶段盘符尚未分配）；AUTOEXEC.BAT 虽在盘符分配后执行，但 `generate_autoexec()` 同样使用 `\` 保持统一
- DBLSPACE.BIN 在注入时自动从根目录移除（Step 0），否则 IO.SYS 加载它后会扫描新簇数据并弹出交互式询问
- 新分配的目录簇必须立即清零，否则簇内残留的 EXE 数据（`MZ%` 魔数）会被 FAT 解析层误判为垃圾目录项，导致 `CD` 失败

## 基座镜像 (Base HDI)

以只读形式存放于 `tools/base_msdos5_scsi_48m.hdi`，具体属性：

| 属性 | 值 |
|------|-----|
| 系统 | MS-DOS 5.0（OEM: `NEC  5.0`） |
| 接口 | SCSI（IPL 分区表 sys_id = `0x91`） |
| 原始大小 | 约 48 MB（50,274,304 数据字节 + 4096 头部） |
| HDI 头部 | 4096 字节 |
| 几何 | 722 cyls × 8 heads × 17 spt × 512 bytes/sector |
| 分区起始 | LBA 136 |
| 文件系统 | FAT16，扇区 1024B，每簇 2 扇区 |

## 工具链 (Toolchain)

| 用途 | 工具 |
|------|------|
| 引擎编译 | gcc-ia16 (IA32, 16-bit real-mode) + ia16-elf-as, Make |
| 素材处理 | Python 3.x |
| 测试运行 | NP2kai（wxnp21kai，wxWidgets GTK3 前端 + IA32 核心，系统安装于 /usr/local/bin/wxnp21kai，源码在 /tmp/NP2kai/） |

**注意**：使用 IA32 核心模拟器 (`wxnp21kai`)，i286 核心已废弃。SDL 前端 (`sdlnp21kai_sdl2`) 已弃用。所有测试通过 `makegame.sh test <name>` 或 `make test` 运行。

## 诊断工具 (Diagnostic Tools)

详情见 `docs/DiagnosticTools.md`。所有工具在 `tools/diag/` 下，通过 `python -m tools.diag.<tool>` 调用。

### 工具优先级

| 优先级 | 工具 | 适用场景 |
|--------|------|----------|
| **P0** | `np2kai_screenshot` | 最直接的验证手段。截图看模拟器画面，确认 DOS 启动链、文本 VRAM、engine 输出 |
| **P1** | `np2kai_serial` | 绕过 HDI 写回问题，通过 INT 14h + PTY 实时捕获串口输出 |
| **P2** | `gen_com` | 生成特定 COM 测试文件，配合 screenshot/serial 使用 |
| **P3** | `hdi_patch_autoexec` | 直接修改 AUTOEXEC.BAT（不经过 inject.py 重建 HDI） |
| **P4** | `hdi_find_file` | 离线检查 HDI 中文件的存在性、内容、FAT 链 |
| **P4** | `hdi_integrity` | SHA256 检查点，确认 NP2kai 是否实际写回 HDI |

### 已知限制

- NP2kai 的 SCSI HDI **写不回**（`hdi_integrity` 已确认），依赖文件输出的验证走不通
- 串口首次测试无输出，疑似 DOS 未完成启动
- 截图工具已在桌面环境验证可用

---

## 一、基础行为原则 (Foundation Rules)

### 1. ref_projects/ 绝不写入 (Never write to ref_projects/)

- **要求**：`ref_projects/` 是只读参考目录，所有文件来自 git submodule，绝对不能修改或写入。
- **行动**：需要参考时直接在原位置阅读。每个子目录的 `README.md` 已注明项目名称、GitHub URL 和许可证。
- **禁忌**：严禁在此目录下创建、编辑或删除任何文件。

### 2. 代码按目录归属 (Code goes where it belongs)

- **要求**：不同性质的代码必须严格归位。
  - 引擎 C 源码 → `core/`
  - Python 工具 → `tools/`
  - 游戏项目部署文件 → `games/<name>/`
  - 工程项目源码 → `projects/<name>/`
  - 规范文档 → `docs/`
  - 开发文档 → `devdocs/`
- **禁忌**：禁止跨目录混放。

### 3. 先读后写，胸有成竹再动手 (Read first, then write)

- **要求**：修改任何文件前，必须先完整阅读该文件及其上下文（相邻文件、调用方接口）。
- **目标**：防止写出功能重复或风格冲突的代码。

### 4. 只改必改之处 (Surgical modifications only)

- **要求**：只修改必须修改的行，保持与现有代码风格绝对一致。
- **禁忌**：不要顺手重构无关代码，不要修改无关注释或格式。

---

## 二、参考引用规则 (Reference Usage Rules)

### 5. 严禁直接链接 ref_projects/ (No direct linkage to ref_projects/)

- **要求**：`core/` 和 `tools/` 中的代码绝不能通过 `#include`、`import`、符号链接等方式引用 `ref_projects/` 中的文件。
- **行动**：编译器/解释器的搜索路径不得包含任何 `ref_projects/` 子目录。
- **禁忌**：禁止出现 `#include "../ref_projects/..."` 这类路径。

### 6. 借鉴思路，独立重写 (Learn from it, write it yourself)

- **要求**：优先阅读参考项目的源码理解其设计，然后在 `core/` 或 `tools/` 中**独立书写**自己的实现。
- **行动**：不复制原文件，仅参考逻辑和算法。
- **理念**：即使许可证允许复制，重写也能加深理解并避免许可证污染。

### 7. 不得不复制时，必须附版权注释 (Copy with attribution)

- **要求**：仅在确实无法重写时（硬件手册级汇编、数据表、复杂逆算法）才复制，且必须在文件开头添加版权注释。

```c
/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 *
 * 从原始项目复制，仅做必要适配。
 */
```

```python
# 来源项目：98imgtools
# GitHub:   https://github.com/tsdko/98imgtools
# 许可证：   Unlicense（公有领域）
```

- **禁忌**：注释中缺少来源项目名称、GitHub 地址或许可证类型中的任意一项视为违规。

### 8. 注意 GPL 传染性 (Beware of GPL copyleft)

- **要求**：GPL v2 代码复制后，整个引擎必须使用 GPL v2 发布。涉及项目：pmdmini、xsystem35-sdl2、xsys35c、djlsr。
- **行动**：GPL 项目优先借鉴思路而非复制代码。必须复制时，确认是否接受全项目 GPL 开源。

**全部 12 个参考项目许可证速查：**

| 项目 | 许可证 | 引用风险 |
|------|--------|----------|
| MHVNVisualNovelEngine | MIT | 无限制 |
| master.lib | 源码公开 | 无明确限制 |
| ReC98 | 无明确许可证 | 谨慎使用 |
| pmdmini | GPL v2 | 传染至全项目 |
| xsystem35-sdl2 | GPL v2 | 传染至全项目 |
| xsys35c | GPL v2 | 传染至全项目 |
| djlsr | GPL v2 / LGPL 2.1 | libc 部分 LGPL 安全 |
| gdc_test | 无明确许可证 | 谨慎使用 |
| ps2busmouse98 | MIT | 无限制 |
| np21w | 修正 BSD | 无限制 |
| 98imgtools | Unlicense | 无限制 |
| 98fmplayer | BSD 2-Clause | 无限制 |

---

## 三、架构约束规则 (Architecture Constraints)

### 9. HAL 是引擎与硬件的唯一边界 (HAL is the only hardware boundary)

- **要求**：`core/engine/` 只能通过 `core/plat/hal.h` 定义的标准接口与平台交互。
- **行动**：EGC/GRCG/GDC/端口 I/O/中断等 PC-98 硬件操作全部封装在 `core/plat/pc98/` 中。
- **禁忌**：严禁在 `core/engine/` 中出现 `outportb()`、`int 0x18` 等硬件操作代码。

### 10. 数据管线前后端分离 (Separate data pipeline from runtime)

- **要求**：源素材 → Python 工具链预处理 → 编译后数据 → 引擎加载运行，各阶段严格分离。
- **行动**：引擎不得直接解析 PNG、TTF、`.mhn` 源码等原始格式。所有素材在开发机上提前编译。
- **目标**：游戏项目不依赖任何 `ref_projects/` 中的工具链即可完整构建。

### 11. 全局风格一致 (One style throughout)

- **要求**：标识符命名、文件组织、注释风格必须与项目现有代码保持一致。
- **行动**：C 代码统一 `snake_case`（函数/变量）+ `PascalCase`（类型）；每个 `.c` 配对应 `.h`。
- **禁忌**：禁止在同一模块中混用不同命名风格。

### 12. 错误必须可见 (No silent failures)

- **要求**：所有错误路径必须明确处理。函数返回错误码或满足断言失败条件时必须让对方明确感知。
- **禁忌**：严禁吞掉错误、不返回状态、或不打印提示就假装操作成功。

### 13. 每次 compact 后用中文沟通 (Chinese after compact)

- **要求**：每次我 compact（整理对话）后，AI 必须改用中文沟通，包括回复、提问、注释和 commit message。
- **原因**：compact 后对话历史被截断，AI 可能丢失语言偏好设定，必须在此文件中显式声明。

### 14. 安装失败自动查日志 (Check log on env install failure)

- **要求**：当 `tools/env_setup/install_env.py` 相关操作失败或用户报告失败时，**必须先读取 `logs/env_install.log` 最后 200 行**定位原因，再给出修复方案。
- **原因**：`install_env.py` 的错误输出通过 `run_step()` 写入日志但不会自动打印到终端。
- **日志位置**：`logs/env_install.log`，由 `install_env.py` 在 `log_write()` 中追加写入。
