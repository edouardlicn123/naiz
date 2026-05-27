# HDI 制作方案

## 1. 概述

从基座镜像 `tools/msdos5.hdi`（MS-DOS 5.0, 48MB, FAT16）中保留完整的 IPL/VBR/boot chain，
只替换 FAT 文件系统的内容，注入游戏文件后生成可直接在 NP2kai 启动的 HDI。

```
ref_disk/（系统文件） + ref_config/（CONFIG.SYS/AUTOEXEC.BAT） + games/<name>/（游戏文件）
    │
    ▼ build_temp_dir() 合并到临时目录
    │
    ▼ NAIZFatFS.write_back_from_directory() 全量重建 FAT
    │
    ▼ img.save()
disks/<name>.hdi
```

## 2. 目录结构

| 目录 | 用途 |
|------|------|
| `tools/ref_disk/` | MS-DOS 5.0 系统文件（IO.SYS, MSDOS.SYS, COMMAND.COM, DOS/ 工具集） |
| `tools/ref_config/` | 适配后的 CONFIG.SYS + AUTOEXEC.BAT |
| `games/<name>/` | 游戏部署文件（engine.exe + 素材） |
| `disks/<name>.hdi` | 输出镜像 |

### ref_disk/ 内容

```
IO.SYS          MS-DOS 内核（系统第一个文件）
MSDOS.SYS       MS-DOS 内核
COMMAND.COM     命令解释器
CONFIG.SYS      系统配置（被 ref_config/ 覆盖）
AUTOEXEC.BAT    自动执行（被 ref_config/ 覆盖）
DOS/            MS-DOS 工具（HIMEM.SYS, EMM386.EXE 等）
DBLSPACE.BIN    磁盘压缩
NECAI.SYS       日本 NEC AI 软件
README.DOC      说明文件
```

### ref_config/

```
CONFIG.SYS:
  FILES=30
  SHELL=\COMMAND.COM /P

AUTOEXEC.BAT:
  @ECHO OFF
  PATH A:\DOS;A:\
  SET TEMP=A:\DOS
  SET DOSDIR=A:\DOS
  MOUSE
  A:\DEMO-A1\ENGINE.EXE
```

## 3. 注入流程

### 3.1 build_temp_dir() — 合并源目录

`tools/naiz_img/inject.py:build_temp_dir()` 按以下顺序合并文件到临时目录：

```
1. tools/ref_disk/        → 复制全部系统文件
2. tools/ref_config/      → 覆盖 CONFIG.SYS / AUTOEXEC.BAT
3. games/<name>/          → 覆盖/添加游戏文件
```

支持 `--no-dos`（跳过 DOS 工具集）、`--no-config`（跳过 CONFIG.SYS 覆盖）、`--no-autoexec`（跳过 AUTOEXEC.BAT 覆盖）。

### 3.2 write_back_from_directory() — FAT 重建

`NAIZFatFS.write_back_from_directory()` 全量重建文件系统，不修改 IPL/VBR：

```
1. 初始化 FAT 表：簇 0/1 设介质描述符/EOC，其余填 0
2. 清零 FAT 区（所有副本）、根目录区、数据区
3. 递归遍历源目录：
   a. 根目录特殊处理：IO.SYS 排第一，MSDOS.SYS 排第二
   b. 每个文件/目录分配连续簇，构建 FAT 链
   c. 数据写入 data 区
   d. 生成 8.3 格式 32 字节目录项
4. 写回根目录区
5. _build_fat_bytes() 序列化 FAT 表（12/16 位编码）
6. 写回所有 FAT 副本
7. img.save() → 写出 HDI 文件
```

### 3.3 基座镜像 `tools/msdos5.hdi`

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

AUTOEXEC.BAT 在盘符分配后执行，可以使用 `C:\`。

### 4.2 IO.SYS 必须排根目录第一

IO.SYS 必须是根目录第一个目录项，MSDOS.SYS 第二个，否则 MS-DOS 无法启动。
`write_back_from_directory()` 自动将 `SYSTEM_FILES = {'IO.SYS', 'MSDOS.SYS'}` 排在最前。

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
| `-b, --base` | `tools/msdos5.hdi` | 基座 HDI |
| `-o, --output` | `disks/<game>.hdi` | 输出路径 |
| `--preview` | false | 只预览文件清单 |
| `--list-files` | false | 列出基座镜像全部文件 |
| `--no-dos` | false | 跳过 DOS 工具文件 |
| `--no-config` | false | 不覆写 CONFIG.SYS |
| `--no-autoexec` | false | 不覆写 AUTOEXEC.BAT |
| `-y, --yes` | false | 非交互模式 |
| `--extract PATH` | — | 从 HDI 提取文件到 logs/ |

## 5.1 make_hdi.sh — 交互式制作工具

`make_hdi.sh` 是 `inject.py` 的交互式外壳，自动选择游戏并确认后调用注入：

```bash
./make_hdi.sh                  # 交互菜单
./make_hdi.sh -g demo-A1       # 指定游戏
./make_hdi.sh -g demo-A1 -y    # 静默模式（跳过确认）
./make_hdi.sh --list-files     # 列出基座镜像文件
./make_hdi.sh --preview        # 预览文件清单
```

内部流程：检测 `games/` 下所有子目录 → 选择游戏 → 调用 `inject.py --game <name>`。

## 5.2 添加新游戏项目

新增一个游戏（例如 `mygame`）的步骤：

1. 创建 `games/mygame/` 目录，放入编译好的 `engine.exe` 及素材文件
2. （可选）创建 `projects/mygame/` 存放源码和 Makefile
3. 运行 `./make_hdi.sh -g mygame -y` 生成 `disks/mygame.hdi`
4. 运行 `./test_hdi.sh mygame` 在 NP2kai 中测试

`inject.py` 会自动将 `games/mygame/` 的全部文件注入 HDI 的根目录。
如需子目录（如 `MYGAME/ENGINE.EXE`），在 `games/mygame/` 下建立对应目录结构即可。

## 6. 集成方式

### Makefile

```makefile
test: $(OUTPUT)
	cp $(OUTPUT) ../games/demo-A1/
	python3 -m tools.naiz_img.inject --game demo-A1 --yes
	../test_hdi.sh demo-A1
```

### make_hdi.sh

交互式外壳，调用 `inject.py`：

```bash
./make_hdi.sh              # 交互菜单
./make_hdi.sh -g demo-A1   # 指定游戏
./make_hdi.sh -g demo-A1 -y  # 静默模式
```

### 测试流程

```bash
# 完整循环
cd projects/demo-A1 && make clean && make
python3 -m tools.naiz_img.inject --game demo-A1 --yes
echo | SDL_VIDEO_WINDOW_POS=9999,9999 SDL_AUDIODRIVER=dummy \
  timeout 35 python3 -c "
import sys; sys.path.insert(0, 'tools')
from env_setup.install_env import cmd_test_hdi
cmd_test_hdi(hdi_path='disks/demo-A1.hdi', emulator='ia32')
"
```

## 7. 常见问题

### 7.1 MS-DOS 无法启动
- 检查 IO.SYS 是否为根目录第一个文件（`write_back_from_directory` 自动排序）
- 检查 CONFIG.SYS 路径是否使用 `\` 而非 `C:\`
- 检查基座镜像 `tools/msdos5.hdi` 是否存在且未损坏

### 7.2 文件找不到
- 文件名必须是 8.3 格式（`inject.py` 自动转换）
- 路径分隔符使用 `\`（MS-DOS 风格）
- 文件名大小写在 FAT16 中不敏感但建议大写

### 7.3 引擎崩溃（UD 异常）
- 检查 engine.exe 的 MZ 头：`CS=0, IP=0` 是否正确指向 `_start`（见 A03）
- 确认链接脚本 `msdos.ld` 包含 `*crt0.o(.text)` 和 `*(.text.*)`
- 确认 `crt0.s` 包含 `.code16`

## 8. 来源声明

`tools/naiz_img/` 全部模块参考 98Bridge (MIT) 的设计思路独立实现。
来源: `https://github.com/NullMagic2/98Bridge`
