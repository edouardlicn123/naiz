# HDI 增量制作方案

## 1. 背景

目前的 HDI 制作流程（`tools/naiz_img/inject.py`）采用**全量 FAT 重建**方式：

1. `build_temp_dir()` 将 `tools/ref_disk/`（DOS 系统文件） + `tools/ref_config/`（CONFIG.SYS） + `games/<name>/`（游戏文件）合并到一个临时目录
2. `NAIZFatFS.write_back_from_directory()` 将 FAT、根目录、数据区**全部清零**，然后从临时目录重建所有文件
3. 输出到 `disks/<name>.hdi`

### 1.1 问题

- **基座 HDI（`tools/base_msdos5_scsi_48m.hdi`）已经包含完整的 MS-DOS 5.0 系统**（IO.SYS、MSDOS.SYS、COMMAND.COM、DOS/\* 工具），`ref_disk/` 中的文件与基座内容完全冗余
- 全量重建会导致 IO.SYS/MSDOS.SYS 的簇链位置发生变化，增加 VBR 几何参数不匹配和引导失败的风险
- 相当于每次制作游戏镜像都重新写了一遍 48MB 的磁盘

### 1.2 基座 HDI 现状

```
/IO.SYS         65536B
/MSDOS.SYS      39620B
/COMMAND.COM    48402B
/DBLSPACE.BIN   65270B
/CONFIG.SYS      333B  (FILES=30 / SHELL=\COMMAND.COM)
/AUTOEXEC.BAT     94B  (含 A:\ 软盘路径，这是安装盘遗物)
/DOS/*          全套 DOS 5.0 工具（FORMAT、XCOPY、MSCDEX 等约 90 个文件）
/NECAI.SYS      660480B
/DOS/ 约占用 3MB
```

## 2. 设计原则

1. **增量优先**：基座 HDI 作为只读模板，每个游戏镜像从基座复制出来，只修改必要的部分（AUTOEXEC.BAT、CONFIG.SYS、游戏目录）
2. **不触引导链**：IPL/VBR/IO.SYS/MSDOS.SYS 的扇区位置和簇链必须与基座完全一致，不做任何移动
3. **扇区透明**：所有操作通过 FAT 文件系统语义进行，不手动编辑扇区数据
4. **集中逻辑**：增量注入的核心逻辑放在一个共享模块中，`inject.py` 和 `inject_file.py` 都是对该模块的薄包装

## 3. 设计决策

### 3.1 C:\ 还是 A:\ ？

**结论：使用 `C:\`。**

理由：
- NP2kai 将 SCSI 硬盘映射为 MS-DOS 的 **C:** 盘
- IPL/VBR 从 SCSI 硬盘加载 IO.SYS 时，DOS 核心自动分配盘符 C:
- 基座 HDI 中 IO.SYS/MSDOS.SYS 的路径引用都不带盘符（`\IO.SYS`、`\DOS\XCOPY.EXE`），证明 DOS 认为自己是 C:
- 基座自带的 AUTOEXEC.BAT 使用 `A:\` 是 MS-DOS 5.0 安装盘（软盘）的遗物，与我们的 SCSI HDI 启动无关
- `inject.py` 和 `inject_file.py` 长期以来的 autoexec 生成逻辑也是 `C:\`

**防御措施：** 在 autoexec 生成函数中加断言：
```python
assert b'A:\\' not in autoexec, "BUG: autoexec must use C:\\, not A:\\"
```

### 3.2 ref_disk/ 的角色

从注入流程中移除，整个目录已删除。基座 HDI 已包含完整的 DOS 5.0 系统文件，不需要再复制备用。

### 3.3 CONFIG.SYS 来源

始终从 `tools/ref_config/CONFIG.SYS` 读取内容并覆盖写入目标 HDI。当前内容：
```
FILES=30
SHELL=\COMMAND.COM /P
```

### 3.4 AUTOEXEC.BAT 生成

由 `inject_common.py` 的 `generate_autoexec()` 函数集中生成：

```python
def generate_autoexec(game_name):
    name = game_name.upper()
    content = (
        b'@ECHO OFF\r\n'
        b'PATH C:\\DOS;C:\\' + name.encode() + b'\r\n'
        b'SET TEMP=C:\\DOS\r\n'
        b'SET DOSDIR=C:\\DOS\r\n'
        b'ECHO BOOT_OK > C:\\BOOTMARK.TXT\r\n'
        b'CD C:\\' + name.encode() + b'\r\n'
        b'ENGINE.EXE\r\n'
    )
    assert b'A:\\' not in content
    return content
```

这个函数是**唯一**生成 autoexec 的地方，`inject_common.py` 和 `inject_file.py` 都调用它。

### 3.5 CLI 参数保留

| 参数 | 行为变化 |
|------|----------|
| `-g`, `--game` | 不变 |
| `-b`, `--base` | 不变 |
| `-o`, `--output` | 不变 |
| `-y`, `--yes` | 不变 |
| `--preview` | 不变 |
| `--list-files` | 不变 |
| `--extract` | 不变 |
| `--no-config` | 保留（跳过 CONFIG.SYS 覆盖） |
| `--no-autoexec` | 保留（跳过 AUTOEXEC.BAT 覆盖） |
| `--no-dos` | **移除**（已无意义） |

## 4. 新工作流

### 4.1 核心流程

```
                   ┌──────────────────────┐
                   │ tools/base_msdos5_    │
                   │ scsi_48m.hdi          │  (只读源)
                   └──────────┬───────────┘
                              │ shutil.copy2()
                              ▼
                   ┌──────────────────────┐
                   │ disks/<game>.hdi     │  (可写副本)
                   │                      │
                   │ Contains:            │
                   │  IO.SYS (orig)       │
                   │  MSDOS.SYS (orig)    │
                   │  COMMAND.COM (orig)  │
                   │  DOS/* (orig)        │
                   │  CONFIG.SYS (orig)   │  ← 将被覆盖
                   │  AUTOEXEC.BAT (orig) │  ← 将被覆盖
                   └──────────┬───────────┘
                              │ inject_into_hdi()
                              ▼
                   ┌──────────────────────┐
                   │ disks/<game>.hdi     │  (已完成)
                   │                      │
                   │ New/modified:        │
                   │  CONFIG.SYS ✓        │  (来自 ref_config)
                   │  AUTOEXEC.BAT ✓      │  (游戏定制内容)
                   │  <GAME>/             │  (新建目录)
                   │  <GAME>/ENGINE.EXE ✓ │
                   │  <GAME>/...          │
                   └──────────────────────┘
```

### 4.2 步骤详解

1. **复制基座**：`shutil.copy2(DEFAULT_BASE, output)` — 文件级复制，不涉及任何扇区操作
2. **打开镜像**：`HDIImage(output)` + `NAIZFatFS(img)` — 解析已有 VBR/FAT/目录树
3. **覆盖 AUTOEXEC.BAT**（除非 `--no-autoexec`）：
   - 在根目录查找 AUTOEXEC.BAT
   - 如果新内容 ≤ 现有簇容量：原位覆写，只更新目录中的文件大小
   - 如果新内容 > 现有簇容量：分配新簇链，释放旧簇链，更新 FAT + 目录
4. **覆盖 CONFIG.SYS**（除非 `--no-config`）：
   - 同样方式处理（内容短，通常原位覆写即可）
5. **创建/更新 `<GAME>/` 目录**：
   - 根目录中如果没有目标目录，新建目录条目 + 分配首簇
   - 如果有，保留现有目录簇
6. **注入游戏文件**：
   - 遍历 `games/<name>/` 下的每个文件
   - 如果文件已存在（同名）：计算新大小，原位覆写或重新分配
   - 如果文件不存在：在目录中新建条目，分配新簇链
   - 对 `ROOTINFO.DAT` 做 font_path 补丁（`0x16` 处写入 `FONT.DAT`）
7. **写入 FAT**：仅更新被修改的簇链（新增/释放的簇），未改动的簇保持原值
8. **保存**：`img.save()` — 将修改后的内存数据写回文件

### 4.3 增量写入细节

与全量重建不同，增量写入**只修改**：
- 根目录中 AUTOEXEC.BAT、CONFIG.SYS、`<GAME>` 目录的条目（最多 3 个 32B 目录项）
- 覆盖的文件内容（AUTOEXEC.BAT、CONFIG.SYS、游戏文件）
- 这些文件的簇链在 FAT 中的条目
- 刚释放的簇在 FAT 中的标记（置 0）

**不变的部分**：
- IPL/VBR 扇区（从未写入）
- IO.SYS/MSDOS.SYS 的簇内容和 FAT 条目
- DOS/\* 的簇内容和 FAT 条目
- 根目录中除上述 3 项外的所有条目
- FAT 中未被修改的条目
- 数据区中未被覆盖的扇区

## 5. 文件修改清单

### 5.1 新建文件

**`tools/naiz_img/inject_common.py`** — 增量注入核心模块

```python
def generate_autoexec(game_name) -> bytes:
    """唯一的 AUTOEXEC.BAT 生成函数"""
    ...

def inject_into_hdi(hdi_path, game_name, game_dir,
                    no_config=False, no_autoexec=False) -> tuple[int, int]:
    """
    对已有 HDI（基座副本）做增量注入：
      - 覆写 AUTOEXEC.BAT
      - 覆写 CONFIG.SYS
      - 创建/更新游戏目录
      - 注入游戏文件
    """
    ...
```

### 5.2 修改文件

**`tools/naiz_img/inject.py`** — 改为调用 `inject_common.inject_into_hdi()`

1. 移除 `build_temp_dir()` 函数（不再需要）
2. 移除 `list_game_file_tree()`（改为调用 inject_common 中的同类函数，或保留但独立）
3. `main()` 流程改为：
   ```
   shutil.copy2(base, output)
   inject_into_hdi(output, game, game_dir, no_config=, no_autoexec=)
   ```
4. `list_game_file_tree()` 可以保留（仅预览用，无副作用）
5. 移除 `--no-dos` 参数解析

**`tools/naiz_img/inject_file.py`** — 改为调用 `inject_common.inject_into_hdi()`

1. `inject()` 函数改为：
   ```
   shutil.copy2(base_path, output_path)
   inject_into_hdi(output_path, game_name, game_dir)
   ```
2. 移除所有内联 FAT 操作代码（现在由 inject_common 提供）
3. 移除 `_find_free_root_slot`、`_find_entry_offset`、`_write_fat`、`_read_root`、`_write_root`、`_read_cluster`、`_write_cluster`、`_to_dos_name` 等内部函数（现在由 inject_common 提供）
4. 考虑是否保留 inject_file.py（如果 inject.py 已覆盖所有用例，可以废弃）
5. 保留 `--base`、`--game`、`--game-dir`、`--output` CLI

**`tools/naiz_img/__init__.py`** — 导出 `inject_common.inject_into_hdi`、`generate_autoexec`（可选）

**`docs/A04-HDI制作方案.md`** — 更新注入流程描述

删除/修改：
- 3.1 节：移除 `build_temp_dir()` 描述
- 3.2 节：改为描述增量注入步骤（复制 → 注入）
- 3.3 节：移除 `write_back_from_directory()` 描述
- 5 节：更新 CLI 参考，移除 `--no-dos`
- 新增 3.4 节：C盘 vs A盘决策说明

### 5.3 不修改的文件

| 文件 | 原因 |
|------|------|
| `make_hdi.sh` | 接口不变，仍然调用 `inject.py --game` |
| `test_hdi.sh` | 不受影响 |
| `start.sh` | 不受影响 |
| `core/Makefile` | `make test` 调 `test_hdi.sh demo-A1`，不变 |
| `tools/naiz_img/hdi.py` | HDI 容器操作不变 |
| `tools/naiz_img/fat.py` | FAT 解析/读取函数不变 |
| `tools/naiz_img/base.py` | 基类不变 |
| `tools/naiz_img/partition.py` | 分区检测不变 |
| `tools/ref_disk/` | 已删除（内容冗余于基座 HDI） |
| `tools/ref_config/` | 保留，`inject_common.py` 从中读取 CONFIG.SYS |
| `tools/sdl_env.sh` | 无关 |

## 6. 回归预防

### 6.1 A:\ 断言

`generate_autoexec()` 函数末尾必须包含：
```python
assert b'A:\\' not in content, (
    f"BUG: autoexec for {game_name} must use C:\\, not A:\\"
)
```

### 6.2 单一 autoexec 来源

整个工具链中只有 `generate_autoexec()` 能生成 AUTOEXEC.BAT。`inject_common.py`、`inject_file.py` 都必须调用此函数，不得各自独立拼接字符串。

### 6.3 基座 HDI 只读性验证

`inject_into_hdi()` 的第一件事是检查输出路径是否与基座路径相同，防止意外覆写基座：
```python
if os.path.abspath(hdi_path) == os.path.abspath(DEFAULT_BASE):
    raise ValueError("Refusing to inject into the base HDI directly")
```

## 7. 验证步骤

实施后执行以下验证：

```bash
# 7.1 预览（只读，仅打印文件列表）
python3 -m tools.naiz_img.inject --game demo-A1 --preview

# 7.2 注入
python3 -m tools.naiz_img.inject --game demo-A1 -y

# 7.3 列出注入后的镜像内容
python3 -m tools.naiz_img.inject --game demo-A1 --list-files
# 预期：AUTOEXEC.BAT 内容正确（C:\ 路径），CONFIG.SYS 正确，
#       DEMO-A1/ 目录及所有游戏文件存在

# 7.4 启动测试
./test_hdi.sh demo-A1

# 7.5 验证基座未被修改
# 对比基座 HDI 的 checksum 与备份一致
sha256sum tools/base_msdos5_scsi_48m.hdi > /tmp/base_hdi_checksum.txt
# 实施后再次校验应一致

# 7.6 二次注入（验证增量）
# 修改一个游戏文件后再次注入，观察只有被改的簇被写入
python3 -m tools.naiz_img.inject --game demo-A1 -y

# 7.7 独立测试 inject_file.py 路径
python3 -m tools.naiz_img.inject_file \
    --base disks/demo-A1.hdi \
    --game demo-A1 \
    --output /tmp/demo-A1_v2.hdi
```

## 8. 回退方案

如果增量注入出现问题，保留 `inject.py` 的原始版本（git history）作为回退方案。代码修改前先提交当前的 `inject.py`：

```bash
git add tools/naiz_img/inject.py tools/naiz_img/inject_file.py
git commit -m "backup: full-rebuild inject.py before incremental refactor"
```

然后在此基础上修改，出现问题时可通过 `git checkout` 恢复。
