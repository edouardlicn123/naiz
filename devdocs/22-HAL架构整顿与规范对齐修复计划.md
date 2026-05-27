# HAL 架构整顿与规范对齐修复计划

## 状态

| 阶段 | 状态 | 日期 |
|------|------|------|
| P1 — HAL 路径收束 | ✅ 已完成 | 2026-05-26 |
| P2 — HAL 存根实现 | ✅ 已完成（P2d 低优先级保留） | 2026-05-26 |
| P3 — main.c 规范对齐 | ✅ 已完成 | 2026-05-26 |
| P4 — 文档同步 | ✅ 已完成 | 2026-05-26 |

## 背景

检查发现 `docs/` 规范与 `devdocs/05` 实际实现之间存在 10 项差距。本计划分 4 个阶段逐步修复。

## 阶段划分

| 阶段 | 内容 | 依赖 |
|------|------|------|
| **P1** — HAL 路径收束 | `file_*` / `mem_*` 改为走 `hal_*`，消除两套 API | 无 |
| **P2** — HAL 存根实现 | `hal_mem_alloc/free`、`hal_vsync_count`、`hal_video_fill_rect`、`hal_input_poll` 补全 | P1 |
| **P3** — main.c 规范对齐 | 加 `hal_check_compatibility`、对齐 A01 日志埋点、A03 主循环 | 无 |
| **P4** — 文档同步 | 更新 devdocs/05、devdocs/21、A01 | P1-P3 完成后 |

---

## P1 — HAL 路径收束

### 目标

消除 `filehandling.c` / `memalloc.c` 两条绕过 HAL 的通道，使引擎只通过 `hal.h` 与平台交互。

### P1a: 文件 I/O 合并

**现状**：
- `hal.h` 声明 `hal_file_open/read/write/close/seek`（在 `hal_pc98.c` 实现）
- `filehandling.h` 声明 `file_open/close/read/write/seek`（在 `filehandling.c` 实现，调 `dos_*`）
- 引擎代码全部用 `file_*` 函数

**改动**：

```
删除 filehandling.c 和 filehandling.h（或降级为 hal_file_* 的 thin wrapper）
将 hal_file_* 的函数签名调整为与 engine 使用方式匹配：
  hal_file_open(path, mode)      → int fd (-1 on error)
  hal_file_read(fd, buf, count)  → int bytes_read (-1 on error)
  hal_file_write(fd, buf, count) → int bytes_written (-1 on error)
  hal_file_close(fd)             → int 0/-1
  hal_file_seek(fd, method, len, newpos) → int 0/-1
```

当前 `haddock` 引擎使用方式（`scenevm.c:98`）：
```c
file_handle fh;
int res = file_open(path, DOSFILE_OPEN_READ, &fh);
// res = 0 success, fh = handle
file_seek(fh, DOSFILE_SEEK_ABSOLUTE, pos, &curpos);
file_read(fh, 4, buf, &br);
file_close(fh);
```

`hal_file_*` 当前签名：
```c
int  hal_file_open(const char *path, unsigned char mode);     // fd or -1
int  hal_file_read(int fd, void *buf, int count);            // bytes or -1
int  hal_file_write(int fd, const void *buf, int count);     // bytes or -1
int  hal_file_close(int fd);                                 // 0 or -1
int  hal_file_seek(int fd, unsigned char method, unsigned long len, unsigned long *newpos);  // 0 or -1
```

调用侧需要改为：
```c
int fh = hal_file_open(path, 0);
if (fh < 0) { error; }
hal_file_seek(fh, 0, pos, &curpos);
hal_file_read(fh, buf, 4, &br);
hal_file_close(fh);
```

**涉及文件**（引擎中所有使用 `file_*` 的地方）：

| 文件 | 行数范围 | 改动量 |
|------|----------|--------|
| `core/engine/scenevm.c` | 98, 104, 105, 106, 108, 110, 111, 135, 141, 146 | ~12 处 |
| `core/engine/graphics.c` | 57, 58, 61, 62, 64, 66, 68, 71, 72, 74, 82, 84 | ~12 处 |
| `core/engine/textengine.c` | (grep file_open/read/close/seek) | ~10 处 |
| `core/engine/rootinfo.c` | (调 hal_file_* 已经正确) | 0 — 已对齐！ |
| `core/data/fontfile.c` | 62, 64, 158, 162, 164, 169, 170, 171 | ~8 处 |
| `core/data/gpimage.c` | 14, 83, 86, 90 | ~4 处 |
| `core/engine/log.c` | 13, 20 | ~2 处 |
| `core/plat/pc98/filehandling.c` | 全部 | 删除此文件 |

**总计改写**：约 48 处调用点 + 删除 filehandling.c/h。

### P1b: 内存分配合并

**现状**：
- `memalloc.c` 调 `dos_mem_alloc/free`（`doscalls.h`）
- `hal_mem_alloc/free` 是空存根
- 引擎用 `mem_alloc/free`（来自 `memalloc.h`）

**改动**：

```
1. 实现 hal_mem_alloc/free（把 doscalls.h 的代码移过来或用 thin wrapper）
2. 让 mem_alloc/free 调 hal_mem_alloc/free 而非 dos_*
3. 删除 memalloc.c（或降级为 hal 的 wrapper）
```

**涉及文件**：
| 文件 | 改动 |
|------|------|
| `core/plat/pc98/hal_pc98.c:301-308` | 实现 `hal_mem_alloc/free`（从 `doscalls.h` 迁入 DOS 调用） |
| `core/plat/pc98/memalloc.c` | 改为调 `hal_mem_alloc/free` |
| `core/plat/pc98/doscalls.h` | 可保留 `dos_mem_alloc/free` 供 HAL 使用，或直接移入 HAL 实现 |

**注意**：`doscalls.h` 中的 `dos_mem_alloc` 是 `static inline` 内联函数，直接在汇编层操作。迁入 `hal_pc98.c` 时需要保持相同的 `__asm` 内联实现。

---

## P2 — HAL 存根实现

### P2a: `hal_mem_alloc/free`（P1b 的一部分）

见 P1b。

### P2b: `hal_vsync_count`（`hal_pc98.c:336-338`）

**现状**：返回 0。

**改动**：在 VSync 中断处理程序（`isr.asm`）中增加计数器，`hal_vsync_count` 读取并清零。

```asm
; isr.asm 增加
vsync_counter: .word 0

; vsync_isr 中 inc vsync_counter
```

```c
// hal_pc98.c
extern volatile unsigned short vsync_counter;
int hal_vsync_count(void)
{
    int c = vsync_counter;
    vsync_counter = 0;
    return c;
}
```

### P2c: `hal_video_fill_rect` 矩形参数（`hal_pc98.c:85-97`）

**现状**：忽略 x/y/w/h，填满全屏。

**改动**：实现真正的矩形填充（4 位平面，逐行 `rep stosw`）。

```c
void hal_video_fill_rect(int x, int y, int w, int h, int color)
{
    unsigned short v[4];
    v[0] = (color & 1) ? 0xFFFF : 0x0000;
    v[1] = (color & 2) ? 0xFFFF : 0x0000;
    v[2] = (color & 4) ? 0xFFFF : 0x0000;
    v[3] = (color & 8) ? 0xFFFF : 0x0000;
    // 每 plane 从 (y*80 + x/8) 到 ((y+h)*80 + (x+w)/8)
    // 填充 w/8 words × h 行
    for (int row = y; row < y + h; row++)
    {
        unsigned long addr = 0xA8000000L + row * 80 + x / 8;
        fill_plane(addr, v[0], w / 8);
        // ... plane 1-3 at +0x08000000 each
    }
}
```

### P2d: `hal_input_poll`（`hal_pc98.c:124-127`）

**现状**：返回 0。

**改动**：如果需要事件模型，实现键状态变化检测。当前用途有限（主循环自己轮询 `KEY_STATUS`），可暂返回 `hal_input_state` 的 OR 聚合或保留为 0 但加注释说明。

---

## P3 — main.c 规范对齐

### P3a: 加 `hal_check_compatibility` 调用

`main.c` 开头（`log_open` 之后、`init_display` 之前）：

```c
if (!hal_check_compatibility())
{
    log_write("INCOMPATIBLE\r\n");
    log_close();
    return 0xFF;
}
log_write("COMPAT OK\r\n");
```

### P3b: 日志埋点对齐 A01

将 `main.c` 的日志埋点从当前自由格式改为 A01 标准：

| A01 规范 | main.c 实现 |
|----------|-------------|
| `A` | 保留 `OPEN <datetime>` |
| `B OK/FAIL` | 新增：`COMPAT OK` / `COMPAT FAIL` |
| `C VIDEO_INIT` | 新增：`VIDEO_INIT` |
| `D FILL_LOOP` | 新增：`GFX INIT`（替代当前 GRAPHICS） |
| — | 保留 `ROOTINFO` / `TEXT` / `SCENE` 等 |
| `F DONE` + 秒数 | 改为 `DONE <seconds>`（需实现计时） |

### P3c: 主循环对齐 A03 伪码

A03 第 284-316 行伪码结构与当前 `main.c` 基本一致，微小差异：
- `hal_vsync_wait` → `wait_vsync()`（实际调 `hal_video_vsync_wait`）— 名称不一致
- `DoDrawRequests()` 在 main.c 中通过 `redraw_everything()` 触发，但不在主循环中——而是由 scene opcode 触发。这是设计差异（被动 vs 主动渲染），当前方式可用，暂不改。

---

## P4 — 文档同步

### P4a: devdocs/05

- Step 1-9 实现标记不变
- 新增「已知架构缺陷」小节，链接到 devdocs/22
- `M2` 验证项保持未完成

### P4b: devdocs/21

- 删除「剩余风险」中已修复项（dos_mem_alloc、setbg null palette）
- 添加 P1-P3 完成后更新的跨引用

### P4c: docs/A01

- 将埋点表从旧版 `projects/demo-A1/main.c` 更新为 `core/engine/main.c` 实际埋点

---

## 依赖关系

```
P1a ──→ P3 (引擎代码路径变了)
P1b ──→ P2a (HAL 实现后才能 mem_alloc)
P2a ──→ 无 (独立)
P2b ──→ 无 (独立)
P2c ──→ 无 (独立)
P2d ──→ 无 (独立)
P3a ──→ 无 (独立)
P3b ──→ 无 (独立)
P4a/b/c ──→ 全部 P1-P3 (需确认最终状态)
```

**建议执行顺序**：P1a → P1b/P2a → P2b/P2c/P2d → P3a/P3b → P4。

## 涉及文件总表

| 文件 | P1 | P2 | P3 | P4 |
|------|----|----|----|----|
| `core/plat/pc98/hal_pc98.c` | 增 hal_* 实现 | 改 fill_rect/vsync_count | — | — |
| `core/plat/pc98/filehandling.c` | 删 | — | — | — |
| `core/plat/pc98/filehandling.h` | 删 | — | — | — |
| `core/plat/pc98/memalloc.c` | 改调 hal_* | — | — | — |
| `core/plat/pc98/doscalls.h` | 保留供 HAL 用 | — | — | — |
| `core/engine/scenevm.c` | 改 file_* → hal_file_* | — | — | — |
| `core/engine/graphics.c` | 同 | — | — | — |
| `core/engine/textengine.c` | 同 | — | — | — |
| `core/data/fontfile.c` | 同 | — | — | — |
| `core/data/gpimage.c` | 同 | — | — | — |
| `core/engine/log.c` | 同 | — | — | — |
| `core/engine/main.c` | — | — | 加 compat check + 日志对齐 | — |
| `devdocs/05-Phase2-核心引擎系统.md` | — | — | — | 更新 |
| `devdocs/21-Scene字节码bug与font_path损坏分析.md` | — | — | — | 更新 |
| `docs/A01-Engine日志机制.md` | — | — | — | 更新 |
