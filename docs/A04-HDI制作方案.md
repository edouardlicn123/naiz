# HDI 制作方案

## 1. 概述

从基座镜像 `tools/base_msdos5_scsi_48m.hdi`（MS-DOS 5.0, 48MB, FAT16）中保留完整的 IPL/VBR/boot chain，
只替换 FAT 文件系统的内容，注入游戏文件后生成可直接在 NP2kai 启动的 HDI。

```
tools/base_msdos5_scsi_48m.hdi
    │
    ▼ shutil.copy2 复制基座镜像
    │
    ▼ inject_common.inject_into_hdi() 增量 FAT 编辑
    │       ├── 替换 AUTOEXEC.BAT/CONFIG.SYS（原地或重分配簇）
    │       ├── 创建/更新游戏子目录
    │       └── 写入游戏文件（新建目录项）
    │
    ▼ 写回 FAT 表 + 根目录区 + img.save()
disks/<name>.hdi
```

## 2. 目录结构

| 目录 | 用途 |
|------|------|
| `tools/ref_config/` | CONFIG.SYS（FILES=30 / SHELL=\COMMAND.COM /P） |
| `games/<name>/` | 游戏部署文件（engine.exe + 素材） |
| `disks/<name>.hdi` | 输出镜像 |

### ref_config/

```
CONFIG.SYS:
  FILES=30
  SHELL=\COMMAND.COM /P

AUTOEXEC.BAT:
  （由 generate_autoexec() 运行时生成，使用 \ 根相对路径）
```

## 3. 注入流程

### 3.1 inject_into_hdi() — 增量 FAT 注入

`tools/naiz_img/inject_common.py:inject_into_hdi()` 在复制后的 HDI 上执行精准 FAT 编辑，不修改 IPL/VBR：

```
0. 移除 DBLSPACE.BIN（根目录标记 0xE5），防 IO.SYS 弹出"how many files"询问
1. 打开复制后的 HDI，解析 FAT16
2. 替换 AUTOEXEC.BAT（优先原地覆盖，空间不足时重分配簇链）
3. 替换 CONFIG.SYS（同上）
4. 查找或创建游戏子目录（如 DEMO-A1/）—— 新分配目录簇立即清零，防止残留数据被误解析为垃圾目录项
5. 遍历 games/<name>/ 下每个文件：
   a. 已存在 → 原地覆盖或重分配
   b. 新文件 → 分配簇链 + 创建目录项
6. 写回所有 FAT 副本
7. img.save() → 写出 HDI 文件
```

**优点 vs 全量重建：**
- IO.SYS/MSDOS.SYS 的簇链地址不变，VBR 无需任何调整
- 只修改变化的扇区，写入速度快
- 基座镜像原有碎片分布完全保留

### 3.2 基座镜像 `tools/base_msdos5_scsi_48m.hdi`

原始 MS-DOS 5.0 启动盘，关键参数：

| 参数 | 值 |
|------|-----|
| 格式 | HDI (Anex86) |
| 头部 | 4096 字节 |
| 几何 | 722 cyls × 8 heads × 17 spt |
| 总扇区 | 98192 |
| 容量 | 48MB |
| 分区起始 | LBA 136 |
| 文件系统 | FAT16 |
| 扇区大小 | 1024 bytes |
| 每簇 | 2 扇区 (2048 bytes) |

## 4. 关键约束

### 4.1 CONFIG.SYS 路径格式

CONFIG.SYS 中的路径**必须使用 `\` 根相对格式（无盘符）**。

原因：MS-DOS 引导顺序——
1. VBR 加载 IO.SYS
2. IO.SYS 加载 MSDOS.SYS
3. MSDOS.SYS 处理 CONFIG.SYS → **此时盘符尚未分配**
4. DEVICE= 全部处理完毕后，MS-DOS 才分配 A:/B:/C:

正确：`SHELL=\COMMAND.COM /P`
错误：`SHELL=C:\COMMAND.COM /P`

AUTOEXEC.BAT 虽在盘符分配后执行（技术上可用 `C:\`），但为保持统一，`generate_autoexec()` 也使用 `\` 根相对路径。

### 4.2 IO.SYS 必须排根目录第一

IO.SYS 必须是根目录第一个目录项，MSDOS.SYS 第二个，否则 MS-DOS 无法启动。
增量注入不移动根目录项，基座镜像的 IO.SYS/MSDOS.SYS 位置天然保持正确。

### 4.3 8.3 文件名

FAT 文件系统要求 8.3 格式（文件名最多 8 字符 + 扩展名最多 3 字符）。
`_to_dos_name()` + `_unique_83()` 自动转换并处理重名冲突。

## 5. CLI 参考

```bash
python -m tools.naiz_img.inject --game demo-A1
python -m tools.naiz_img.inject --game mygame -o disks/mygame.hdi
python -m tools.naiz_img.inject --game demo-A1 --preview       # 预览
python -m tools.naiz_img.inject --game demo-A1 --list-files    # 列出基座文件
python -m tools.naiz_img.inject --game demo-A1 --extract DEMO-A1/ENGINE.LOG  # 提取日志
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `-g, --game` | 必填 | 游戏名，对应 `games/<name>/` |
| `-b, --base` | `tools/base_msdos5_scsi_48m.hdi` | 基座 HDI |
| `-o, --output` | `disks/<game>.hdi` | 输出路径 |
| `--preview` | false | 只预览文件清单 |
| `--list-files` | false | 列出基座镜像全部文件 |
| `--no-config` | false | 不覆写 CONFIG.SYS |
| `--no-autoexec` | false | 不覆写 AUTOEXEC.BAT |
| `-y, --yes` | false | 非交互模式 |
| `--extract PATH` | — | 从 HDI 提取文件到 logs/ |

## 5.1 makegame.sh — 一键制作与测试

`makegame.sh` 统一管理制作（make）、测试（test）、构建（build）流程：

```bash
./makegame.sh make demo-A1     # 制作 disks/demo-A1.hdi
./makegame.sh test demo-A1     # 在 wxnp21kai 中启动测试
./makegame.sh build demo-A1    # 从 projects/demo-A1/ 编译 → 制作
./makegame.sh                  # 交互模式（选择操作 + 游戏）
```

内部流程：`make` → `inject.py --game <name>`；`test` → `cmd_test_hdi()` → wxnp21kai。

## 5.2 添加新游戏项目

新增一个游戏（例如 `mygame`）的步骤：

1. 创建 `games/mygame/` 目录，放入编译好的 `engine.exe` 及素材文件
2. （可选）创建 `projects/mygame/` 存放源码和 Makefile
3. 运行 `./makegame.sh make mygame` 生成 `disks/mygame.hdi`
4. 运行 `./makegame.sh test mygame` 在 wxnp21kai 中测试

`inject.py` 自动将 `games/mygame/` 的全部文件注入 HDI 的 `MYGAME/` 子目录。
如需调整子目录名，修改 `games/mygame/` 下的目录结构即可。

## 6. 集成方式

### Makefile

```makefile
test:
	../makegame.sh make demo-A1
	../makegame.sh test demo-A1
```

### makegame.sh

一键流程：

```bash
./makegame.sh make demo-A1   # 制作镜像
./makegame.sh test demo-A1   # 启动测试
./makegame.sh build demo-A1  # 编译 + 制作
```

### 测试流程

```bash
# 完整循环
cd projects/demo-A1 && make clean && make
./makegame.sh make demo-A1
./makegame.sh test demo-A1
```

## 7. 常见问题

### 7.1 MS-DOS 无法启动
- 检查 IO.SYS 是否为根目录第一个文件（增量注入不移动根目录项，基座位置天然正确）
- 检查 CONFIG.SYS 路径是否使用 `\` 而非 `C:\`
- 检查基座镜像 `tools/base_msdos5_scsi_48m.hdi` 是否存在且未损坏

### 7.2 文件找不到
- 文件名必须是 8.3 格式（`inject_common._to_dos_name()` 自动转换）
- 路径分隔符使用 `\`（MS-DOS 风格）
- 文件名大小写在 FAT16 中不敏感但建议大写

### 7.3 引擎崩溃（UD 异常）
- 检查 engine.exe 的 MZ 头：`CS=0, IP=0` 是否正确指向 `_start`（见 A03）
- 确认链接脚本 `msdos.ld` 包含 `*crt0.o(.text)` 和 `*(.text.*)`
- 确认 `crt0.s` 包含 `.code16`

### 7.4 启动时弹出"how many files"询问
- **症状**：MS-DOS 启动过程中（内存检测后）弹出提示询问文件数量，需要手动输入数字
- **根因**：IO.SYS 自动加载 DBLSPACE.BIN，该驱动扫描所有新分配的簇数据，误判为 DriveSpace 压缩卷（CVF）
- **解决**：`inject_into_hdi()` 自动在 Step 0 移除 DBLSPACE.BIN（标记根目录项为 0xE5）

### 7.5 无法进入游戏目录（CD 命令失败）
- **症状**：AUTOEXEC.BAT 执行时 `CD \DEMO-A1` 失败，停留在根目录命令提示符
- **根因**：新分配的目录簇未清零，簇内残留的旧 EXE 数据（`MZ%` 魔数）被目录解析层误判为合法的目录项，导致目录结构损坏
- **解决**：分配目录簇后立即写满 `\x00`。当前版本尚未实现此修复，需确保 Step 4 中新簇写入零

## 8. 来源声明

`tools/naiz_img/` 全部模块参考 98Bridge (MIT) 的设计思路独立实现。
来源: `https://github.com/NullMagic2/98Bridge`
