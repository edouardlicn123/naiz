# HDI 注入规范

## 1. 概述

从基座镜像 `tools_commercial/base_msdos5_scsi_48m_clean.hdi`（MS-DOS 5.0, 48MB, FAT16, SCSI）出发，通过增量 FAT 编辑注入游戏文件，生成可直接在 NP2kai (`wxnp21kai`) 中启动的 HDI 镜像。

### 核心架构

```
 游戏文件 (games/<name>/) + CONFIG.SYS (tools/ref_config/)
     │
     ▼  shutil.copy2 复制基座镜像
     │
     ▼  inject_into_hdi()  增量 FAT 编辑（不动 IPL/VBR）
     │       ├── 移除 DBLSPACE.BIN
     │       ├── 替换 AUTOEXEC.BAT
     │       ├── 替换 CONFIG.SYS（DEVICE=VEM486）
     │       └── 写入游戏文件到根目录
     │
     ▼
 disks/<name>.hdi
     │
     ▼  makegame.sh test ──▶ NP2kai (wxnp21kai) ──▶ MS-DOS 5.0
     │                                               │
     │                                               ▼ IO.SYS → MSDOS.SYS
     │                                               │
     │                                               ▼ CONFIG.SYS (VEM486)
     │                                               │
     │                                               ▼ AUTOEXEC.BAT
     │                                               │    │
     │                                               │    ▼ ENGINE.EXE
     │                                               │
     │                                               ▼ 引擎执行 → 场景循环 → idle
     └────────────────────────────────────────────────┘
```

## 2. 基座镜像

| 属性 | 值 |
|------|-----|
| 系统 | MS-DOS 5.0（OEM: `NEC  5.0`） |
| 接口 | SCSI（IPL 分区表 sys_id = `0x91`） |
| 格式 | HDI (Anex86) |
| 头部 | 4096 字节 |
| 几何 | 722 cyls × 8 heads × 17 spt × 512 bytes/sector |
| 总扇区 | 98192 |
| 原始大小 | 约 48 MB（50,274,304 数据字节 + 4096 头部） |
| 分区起始 | LBA 136 |
| 文件系统 | FAT16，扇区 1024B，每簇 2 扇区（2048B） |

以只读形式存放于 `tools_commercial/base_msdos5_scsi_48m_clean.hdi`，保留完整 IPL/VBR/boot chain。每次制作时复制到输出路径，再在其上执行增量编辑。

## 3. 目录结构

| 路径 | 用途 |
|------|------|
| `tools_commercial/base_msdos5_scsi_48m_clean.hdi` | 基座镜像（只读） |
| `tools/ref_config/CONFIG.SYS` | CONFIG.SYS 模板 |
| `games/<name>/` | 游戏部署文件（`ENGINE.EXE` + 素材） |
| `disks/<name>.hdi` | 输出镜像 |
| `core/engine.exe` | 编译后的引擎二进制 |
| `tools/naiz_conv/psf2font.py` | ASCII 字库生成器 (Uni1-VGA16.psf → FONT.DAT) |

### `games/<name>/` 必须包含 ENGINE.EXE 和数据文件

`ENGINE.EXE` 是游戏启动的唯一入口（见 §4.4 约定）。`makegame.sh make` 会自动从 `core/engine.exe` 部署，无需手动复制。

此外，`games/<name>/` 还必须包含引擎运行时需要加载的数据文件（见 §4.4 数据文件清单）。这些文件由 `makegame.sh build` 部署（见 §6.2）。

诊断工具（如 `RWCHECK.COM`）可额外放入目录，不影响启动流程。

## 4. 注入流程

### 4.1 步骤概览

`tools/naiz_img/inject_common.py:inject_into_hdi()` 执行以下步骤：

```
 0. 移除 DBLSPACE.BIN（根目录标记 0xE5）
 1. 替换 AUTOEXEC.BAT（SET DOS16M=1 + ENGINE.EXE）
 2. 替换 CONFIG.SYS（DEVICE=VEM486, SHELL=）
 3. 遍历 games/<name>/ 下每个文件，注入到根目录
    - 文件已存在 → 覆盖（新簇立即清零）
    - 文件不存在 → 新建目录项（新簇立即清零）
 4. 写回所有 FAT 副本
 5. img.save() → 写出 HDI
```

**`_inject_file_content()` 签**：`fat_eoc` 参数指定 FAT12_EOC（0xFF8）或 FAT16_EOC（0xFFF8），兼容 FAT12/FAT16 双格式。
修复前硬编码 FAT16_EOC，在 FAT12 基座镜像上导致簇链尾标记错误，进而引发文件截断或溢出。





### 4.4 入口与数据文件约定

#### ENGINE.EXE

**`ENGINE.EXE` 是游戏启动唯一入口，约定不可变更。** 理由：

1. `AUTOEXEC.BAT` 写死 `ENGINE.EXE`——不依赖目录扫描或自动检测
2. 自动检测哪个文件是「主要可执行文件」过于脆弱（游戏目录名、文件列表均不可靠）
3. `makegame.sh make` 负责确保 `games/<name>/ENGINE.EXE` 存在——如果缺失，自动从 `core/engine.exe` 部署

#### 数据文件清单

引擎启动时需要加载以下数据文件（均位于 `games/<name>/` 根目录，非子目录）：

| 文件 | 来源 | 引擎用途 |
|------|------|---------|
| `.nb` | `projects/<name>/nb/` | NB 纯文本剧本（角色台词、场景流程） |
| `ENGINE.EXE` | `core/engine.exe` — Open Watcom 编译 | 游戏启动入口（MZ stub + DOS/4GW + LE body） |
| `FONT.DAT` | `tools/naiz_conv/psf2font.py` 生成（Uni1-VGA16.psf 源） | 8×16 ASCII 字形数据 |
| `IMAGE.DAT` | `projects/<name>/` — `pack_images.py` 打包 | MAG 图片归档（背景 + 精灵） |
| `DOS4GW.EXE` | `tools_commercial/dos_system/` — 固定 v4.45 | DOS/4GW 保护模式扩展器 |
| `VEM486.EXE` | `tools_commercial/dos_system/` | 内存管理器（CONFIG.SYS DEVICE= 加载） |

`FONT.DAT` 提供 8×16 ASCII 字形（源为 Uni1-VGA16.psf）。CJK 字形由 `CJK.DAT` 提供（B14 规范）。引擎内置 94 个 ASCII 字形作为最小回退。

数据文件由 `makegame.sh build <name>` 统一部署（见 §6.2）。

#### 添加新游戏

1. 创建 `projects/<name>/` 和 `games/<name>/` 目录
2. 编写场景/图片/文本源文件
3. `makegame.sh build <name>` — 编译源文件并部署数据文件
4. `makegame.sh make <name>` — 制作可启动 HDI
5. `makegame.sh test <name>` — 测试

### 4.5 文件系统约束

**8.3 文件名**：FAT16 要求文件名最多 8 字符 + 扩展名最多 3 字符。`_to_dos_name()` 自动截断补齐。

**IO.SYS 必须排根目录第一**：IO.SYS 必须是根目录第一个目录项，MSDOS.SYS 第二个。增量注入不移动根目录项，基座位置天然保持正确。

**DBLSPACE.BIN 自动移除**：启动时 IO.SYS 加载 DBLSPACE.BIN，该驱动扫描所有新分配的簇数据，将游戏文件误判为 DriveSpace 压缩卷，弹出 "how many files" 询问。Step 0 将根目录项标记为 0xE5 解决。

**新目录簇必须清零**：新分配的目录簇中若残留 `MZ%` 魔数等 EXE 数据，FAT 目录解析层会误判为垃圾目录项，导致 `CD` 命令失败。`inject_into_hdi()` 在 Step 3 分配新链后立即调用 `_zero_cluster()` 写入全零。

## 5. NP2kai 测试

### 5.1 模拟器选择

| 核心 | 二进制 | 状态 |
|------|--------|------|
| IA32 | `/usr/local/bin/wxnp21kai` | **当前开发目标** |
| i286 | `/usr/local/bin/sdlnp21kai_sdl2` | 已废弃 |

IA32 核心对应 PC-9821 (486+) 架构。BIOS ROM 必须匹配（PC-9821 BIOS → IA32 核心），否则显示 "IMA未启用" 并死锁。

### 5.2 SCSIHDD0 配置优先级

**NP2kai 的 `SCSIHDD0` 配置项是 SCSI 硬盘的唯一启动源。** 命令行参数会被忽略。

配置文件 `~/.config/wxnp21kai/wxnp21kai.toml` 格式：

```toml
[NP21kai]
SCSIHDD0 = "/absolute/path/to/disks/<name>.hdi"
```

`cmd_test_hdi()` 在每次 `makegame.sh test` 时自动更新此配置。如果配置指向错误的 HDI，所有测试结果均为**误报**（模拟器实际启动的是另一个镜像）。

### 5.3 诊断工具链

| 工具 | 路径 | 用途 |
|------|------|------|
| `np2kai_serial` | `tools/diag/np2kai_serial.py` | 串口输出捕获（INT 14h + PTY） |
| `naiz_screendig` | `tools/naiz_screendig/` | 截图验证画面（**P0**） |
| `read_fat16` | `tools/diag/read_fat16.py` | FAT 分区浏览（离线检查文件/FAT 链） |
| `hdi_patch_autoexec` | `tools/diag/hdi_patch_autoexec.py` | 直接修改 AUTOEXEC（不经过 inject） |
| `gen_com` | `tools/diag/gen_com.py` | 生成测试 COM 文件 |
| `symbol_audit` | `tools/diag/symbol_audit.py` | core/ 封装/拆分审计（static 候选 / 死导出 / 耦合视图 / 符号清单） |

**截图验证流程：**

```bash
# 1. 确保配置指向被测 HDI
# 2. 启动模拟器
makegame.sh test demo-a2 &
sleep 6
# 3. 截图
python3 -m tools.naiz_screendig
# 4. 亮度分析（正常启动 ~214，黑屏 ~29-38）
convert /tmp/p.png -resize 1x1! -format '%[fx:int(mean*255)]' info:
```

**NP2kai SCSI HDI 写不回已知限制**：NP2kai 的 SCSI 仿真不实际写回 HDI 文件（调试期间已确认），依赖文件输出的验证走不通。必须用截图或串口验证。

### 5.4 验证方法

- **P0 — 截图**：最直接的手段。看模拟器画面确认 DOS 启动链、文本 VRAM、engine 输出
- **P1 — 串口**：绕过 HDI 写回问题，通过 INT 14h + PTY 实时捕获串口输出
- **P2 — HDI 离线检查**：`read_fat16` 检查 FAT 分区内文件是否存在、内容是否正确、FAT 链完整性

## 6. 工作流

### 6.1 makegame.sh 使用

```bash
makegame.sh make <name>     # 制作 HDI（自动部署 ENGINE.EXE）
makegame.sh test <name>     # 在 wxnp21kai 中启动测试
makegame.sh build <name>    # 编译项目数据（projects/<name>/）
makegame.sh                 # 交互模式
```

**`make` 子命令内部流程：**
1. 检查 `games/<name>/ENGINE.EXE` 是否存在
2. 若不存在，从 `core/engine.exe` 自动复制
3. 若 `core/engine.exe` 也不存在，报错提示 `make -C core`
4. 调用 `inject.py --game <name> --yes`

### 6.2 从源码到启动盘完整流程

```bash
# 1. 编译引擎
make -C core clean all

# 2. 编译游戏数据并部署到 games/<name>/
makegame.sh build demo-a2

# 3. 制作 HDI（自动部署 ENGINE.EXE + 注入数据文件）
makegame.sh make demo-a2

# 4. 测试
makegame.sh test demo-a2

# 或一键：make -C core test
#（该命令执行：编译引擎 → 复制到 games/ → 制作 HDI → 启动模拟器）
```

**`build` 子命令内部流程：**

```
0. PNG→MAG 素材转换（由 assets/<name>/images.map 驱动）
   └── mag_convert.py 自动检测 PNG 比 MAG 新时重新转换

1. make -C core（编译引擎）
   └── wcl386 → engine.exe → 部署到 games/<name>/ENGINE.EXE

2. NB 剧本部署
   └── 复制 projects/<name>/scenes/*.nb → games/<name>/

3. IMAGE.DAT 打包
   └── pack_images.py → projects/<name>/ASSETS.DB (img_map) → IMAGE.DAT

4. 部署字库
   └── tools/naiz_font/FONT.DAT → games/<name>/FONT.DAT
   └── tools/naiz_font/CJK.DAT → games/<name>/CJK.DAT

5. 部署运行时
   └── tools_commercial/dos_system/{DOS4GW.EXE,VEM486.EXE} → games/<name>/
```

`build` 子命令不涉及 HDI 操作，仅刷新 `games/<name>/` 中的部署文件。修改源文件后，只需重新运行 `makegame.sh build <name>` + `makegame.sh make <name>`。

## 7. 常见问题

### 7.1 NP2kai SCSI 启动黑屏

**症状**：模拟器启动后屏幕全黑，无 DOS 启动画面，亮度约 29-38。

**根因**：使用 CONFIG.SYS 的 `INSTALL=` 方式启动引擎。`INSTALL=` 在 DOS 显示子系统完全初始化前执行引擎，此时 CRT BIOS 模式设置尚未完成，导致黑屏。

**排查**：
1. 确认 `wxnp21kai.toml` 中 `SCSIHDD0` 指向被测 HDI（§5.2）
2. 确认 AUTOEXEC.BAT 使用 `\` 根相对路径（非 `C:\`）
3. 确认 `AUTOEXEC.BAT` 末行为 `ENGINE.EXE`

**解决**：
- 改用 AUTOEXEC.BAT 启动引擎（由 `inject_into_hdi()` 自动处理）
- 禁止在 CONFIG.SYS 中使用 INSTALL= 启动游戏

### 7.2 DBLSPACE.BIN 导致 "how many files" 询问

**症状**：MS-DOS 启动过程中弹出提示询问文件数量，需手动输入数字。

**根因**：IO.SYS 自动加载 DBLSPACE.BIN，该驱动扫描新分配的簇数据，将游戏文件误判为 DriveSpace 压缩卷。

**解决**：`inject_into_hdi()` 自动在 Step 0 移除 DBLSPACE.BIN（标记根目录项为 0xE5）。

### 7.3 CD 命令失败（无法进入游戏目录）

**症状**：`CD \GAMENAME` 失败，停留在根目录。

**根因**：新分配的目录簇未清零，残留 `MZ%` 魔数被目录解析层误判为合法目录项。

**解决**：`inject_into_hdi()` 自动在 Step 3 对新目录簇写入全零。

### 7.4 引擎崩溃（UD 异常）

**症状**：模拟器显示 "UD"（Undefined Instruction）或引擎无输出。

**排查**：
- 确认 `DOS4GW.EXE` 存在于 HDI 根目录（引擎 MZ stub 需要 DOS/4GW 加载）
- 检查 `ENGINE.EXE` 是否由 Open Watcom `wcl386 -bt=dos -l=dos4g` 编译
- 确认 `CONFIG.SYS` 包含 `DEVICE=\VEM486.EXE /U`

### 7.5 BIOS/核心不匹配 → "IMA未启用"

**症状**：NP2kai 启动后显示 "IMA未启用" 并等待按键，键盘无效。

**根因**：IA32 核心 + PC-9801 BIOS ROM 不匹配。

**解决**：使用 IA32 核心 (`wxnp21kai`) + PC-9821 BIOS。BIOS ROM 在首次环境设置时手动配置。
## 8. 添加新游戏项目

新增一个游戏（例如 `mygame`）的步骤：

1. 创建 `games/mygame/` 目录，放入编译好的 `engine.exe` 及素材文件
2. （可选）创建 `projects/mygame/` 存放源码和 Makefile
3. 运行 `./makegame.sh make mygame` 生成 `disks/mygame.hdi`
4. 运行 `./makegame.sh test mygame` 在 wxnp21kai 中测试

`inject.py` 自动将 `games/mygame/` 的全部文件注入 HDI 的 `MYGAME/` 子目录。
如需调整子目录名，修改 `games/mygame/` 下的目录结构即可。
## 9. 集成方式

### Makefile

```makefile
test:
	../makegame.sh make demo-a2
	../makegame.sh test demo-a2
```

### makegame.sh

一键流程：

```bash
./makegame.sh make demo-a2   # 制作镜像
./makegame.sh test demo-a2   # 启动测试
./makegame.sh build demo-a2  # 编译 + 制作
```

### 测试流程

```bash
# 完整循环
cd projects/demo-a2 && make clean && make
./makegame.sh make demo-a2
./makegame.sh test demo-a2
```

## 10. 诊断工具参考

| 命令 | 用途 |
|------|------|
| `python -m tools.naiz_screendig` | 截图分析 |
| `python -m tools.diag.np2kai_serial --hdi disks/<name>.hdi` | 串口输出 |
| `python -m tools.diag.read_fat16` | 浏览基座 HDI FAT 分区 |
| `python -m tools.diag.hdi_patch_autoexec <hdi> "ENGINE.EXE"` | 修改 AUTOEXEC |
| `python -m tools.diag.gen_com <output> <size> [fill]` | 生成 COM 文件 |

## 11. 来源声明

`tools/naiz_img/` 全部模块参考 98Bridge (MIT) 的设计思路独立实现。
来源项目：98Bridge
GitHub: https://github.com/NullMagic2/98Bridge
许可证：MIT License

