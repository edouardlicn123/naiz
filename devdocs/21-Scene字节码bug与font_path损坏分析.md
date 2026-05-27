# Scene 字节码 bug 与 ROOTINFO.font_path 损坏分析

## 症状

执行 `make_hdi.sh -g demo-A1 -y` 制作 HDI 后在 NP2kai 启动，直接进入 DOS 命令行，引擎没有自动运行。

提取 `ENGINE.LOG` 结果为 **0 字节** → 引擎启动并创建了日志文件，但在 256 字节内部缓冲区刷新前崩溃。

## 调查过程

### 1. ENGINE.LOG 为空的原因

`engine/log.c` 使用 256 字节环形缓冲区 `log_buf[LOG_BUF_SIZE]`：
- `log_open()` → 创建文件
- `log_write("OPEN ")` → 写入缓冲区（~5 字节）
- `log_write_datetime()` → 写入缓冲区（~20 字节）
- `log_write("\r\n")` → 写入缓冲区（2 字节，约 27 字节总计）
- 然后调用 `init_display()` → **此处崩溃**
- 缓冲区 < 256 字节，未触发 `flush()` → 数据丢失 → 日志文件为 0 字节

### 2. ROOTINFO.DAT font_path 损坏

`projects/demo-A1/out/ROOTINFO.DAT` 偏移 0x16 的 12 字节内容：
```
b'H\x8b\x0c$\xe9L\xf7\xff\x00\x00\x00\x00'
```

这是 x86 机器码碎片，不是有效 8.3 DOS 文件名。由 `mhvnlink` 工具生成时写入了错误数据。

该字段在 `read_root_info()` 之后才被加载（`fontfile.c:init_font_file` 第 62 行读取），且早于 `init_display()` 的 `fontfile.c:init_font_file()` 实际上读取的是 `root_info` 全局变量**零初始化**后的空字符串（`init_font_file` 在 `read_root_info` 之前调用），因此 `file_open("")` 失败后优雅返回，**不是初始崩溃的原因**。

### 3. BGIMAGE.DAT 分解

`BGIMAGE.DAT` (264 字节) → LZ4 解压 → 40122 字节。

结构解析：
- BSAVE 头 (7 字节)：`0xF9 0x00 0x00 0x00 0x00 0x9C 0x9C`
  - 偏移 3-4: `0x0000` — 段地址
  - 偏移 5-6: `0x9C9C` — 图像数据长度（40092 字节）
- BSAVE 体（40092 字节）：在 PC-98 16-color 模式下对应分辨率约 200×N（每像素 4bit，1 word/像素）。若 200 像素宽 → 每行 100 words = 200 字节 → 40092 / 200 ≈ 200.46 → 非整数。实际为 200×200 + 92 字节额外数据（可能是 palette 或其他 meta）。

### 4. SCENE.DAT 字节码 bug

Python 最小 LZ4 解压器验证 SCENE.DAT (238 字节) 解压后为 **262 字节**，远小于 `cur_scene_data[4096]` 上限（`load_new_scene` 第 109 行 `mem_alloc(comp_size + 4)`）。

字节码追踪：

```
位置: 0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16
数据: 30 00 00 12 00 00 11 00 00 10 10 10 10 10 10 10 12 ...
```

| PC | Op | 参数 | 动作 | PC 变化 |
|----|----|------|------|---------|
| 0  | 0x30 | bgNum=0 | load_bg_image(0) | PC=3 |
| 3  | 0x12 | charNum=0 | 设角色 0 | PC=6 |
| 6  | 0x11 | textNum=0 | 设下一文本为 0 → **落入 0x10** | PC=8 |
| 8  | 0x10 | (fallthrough) | 显示 text_array[0] → break | PC=8 |
| 8  | 0x00 | sNum=*(0x1000) | load_new_scene(0x1000) → **越界崩溃** | — |

**根本原因**：`case 0x10`（`scenevm.c:589`）在 `VMFLAG_TEXTINBOX` 已置位时执行 `cur_scene_data_pc--` 回退 1 字节，然后 `goto delText`。回退后的 PC 指向 `0x11` 指令的第二个参数字节（`0x00`），与后续字节 `0x10` 组合读出 `sNum = 0x1000`，触发 `load_new_scene(4096)` → 越界 seek → 读入垃圾数据 → `mem_alloc(garbage_size)` 可能失败 → 崩溃。

`cur_scene_data_pc--` 是 MHVN98 原版中的约定：当 `0x10` 在文本模式下被命中时，它意味着"清除当前文本并等待"，回退 PC 以便重新执行该指令。但 `case 0x11` 的 fallthrough 让 PC 停在了参数区之后而非指令流起点，回退后落入了参数区。

### 5. setbg (case 0x30) null palette 风险

`scenevm.c:1011` `set_scene_palette_bg(bg_palette_keep)` 传入的 `bg_palette_keep` 可能为 `NULL`（`cur_scene_palette_bg` 未初始化时）。`gpimage.c:256` 的 `memset()` 对 NULL 指针解引用会导致崩溃。但该 crash 发生在字节码 bug 之后，不是当前阻塞点。

## 修复执行

三项修复已于 2026-05-26 全部代码落地并部署：

| Step | 文件 | 行 | 修改 | 状态 |
|------|------|-----|------|------|
| 1 | `core/engine/main.c` | 34 | `init_display()` 前插入 `log_flush()` | ✅ 已提交 |
| 2 | `core/engine/scenevm.c` | 592 | 删除 `case 0x10` 中 `cur_scene_data_pc--` | ✅ 已提交 |
| 3 | `tools/naiz_img/inject.py` | 67-71 | 注入后自动修补 ROOTINFO.DAT 偏移 0x16 | ✅ 已提交 |

engine.exe 重建为 31240 字节，HDI 已重建至 `disks/demo-A1.hdi`（127 文件注入）。

## 验证方法

```bash
# 部署 + 构建 HDI
cp core/engine.exe games/demo-A1/
source tools/env_setup/venv/bin/activate
python3 -m tools.naiz_img.inject --game demo-A1 --yes

# 提取日志（引擎运行后在 NP2kai 中执行）
python3 -m tools.naiz_img.inject --extract ENGINE.LOG --game demo-A1

# LZ4 解压验证
python3 -c "
import lz4.block
with open('games/demo-A1/SCENE.DAT','rb') as f:
    f.seek(4); comp = f.read()
dec = lz4.block.decompress(comp, uncompressed_size=65536)
print(f'Decompressed: {len(dec)} bytes')
print('Hex:', dec[:64].hex())
"
```

## 剩余风险

| 风险 | 说明 |
|------|------|
| scenevm.case 0x30 NULL | 已修复（2026-05-26）：`load_bg_image` 失败时提前 `break`，不解引用 NULL 指针 |
| dos_mem_alloc 返回值 | 已修复（2026-05-26）：OOM 时返回 `(void*)0` 而非 DOS 错误码 |
| BSAVE palette 解析 | BGIMAGE.DAT 的 BSAVE 体包含 palette 数据，当前 `load_bg_image` 未正确解析 |
| font_path 虚拟值 | `FONT.DAT` 不存在但 `init_font_file` 失败后优雅返回，不阻止启动。后续需要真实字库文件 |

## 后续 HAL 架构整顿（2026-05-26）

根据 `devdocs/22-HAL架构整顿与规范对齐修复计划.md`，完成了以下 HAL 层对齐工作：

- **P1a**：`fontfile.c`、`gpimage.c` 等文件 I/O 迁移 `file_*` → `hal_file_*`，删除 `filehandling.c/.h`
- **P1b**：`memalloc.c` 迁移 `dos_mem_alloc/free` → `hal_mem_alloc/free`
- **P2a**：实现 `hal_mem_alloc/free`（DOS INT 21h AH=48h/49h）
- **P2b**：实现 `hal_vsync_count`（ISR 计数器）+ `vsync_counter` 在 `isr.asm`
- **P3a**：`main.c` 添加 `hal_check_compatibility()` 调用
- **P3b**：日志埋点双向对齐 A/B/C/F

全部修改已在 `core/` 编译通过。

**未完成项**：
- **P2c** `hal_video_fill_rect` — 仍忽略 x/y/w/h，填满全屏（`hal_pc98.c:86-98`）
- **P1b 遗留 bug** — `hal_mem_alloc` 缺 `"%bx"` clobber；`hal_mem_free` 缺 `"%es"`、`"%ax"` clobber（`hal_pc98.c:264-285`）

## 相关文件

| 文件 | 行号 | 用途 |
|------|------|------|
| `core/engine/main.c` | 34 | log_flush() 调试点 |
| `core/engine/scenevm.c` | 589 | case 0x10 PC-- bug（已修复） |
| `tools/naiz_img/inject.py` | 67-71 | ROOTINFO.DAT font_path 修补 |
| `core/engine/log.c` | 17-21 | 256 字节缓冲区 + flush 逻辑 |
| `core/engine/fontfile.c` | 62-63 | init_font_file 失败处理 |
| `core/engine/scenevm.c` | 109-113 | load_new_scene LZ4 解压 |
| `core/engine/scenevm.c` | 1008-1014 | case 0x30 setbg（空指针风险） |
| `core/engine/gpimage.c` | 256 | memset NULL palette 崩溃点 |
