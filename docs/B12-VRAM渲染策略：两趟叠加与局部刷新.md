# B12 — VRAM 渲染策略：背景/精灵/对话框/文字四趟叠加与局部裁剪

> **状态**：活跃维护
> **创建**：2026-06-10
> **最后更新**：2026-06-12（四趟渲染顺序、200×400 立绘、bg_snapshot 裁剪策略、B15 换装机制引用）
> **依赖**：`B02-显示管线规范.md`（VRAM 布局、图元函数）、`B11-MAG图片加载与显示规范.md`（背景/立绘 loading）、`C01-引擎基本概念.md`（对白概念）、`C02-对话框样式方案.md`（对话框方案）、`C03-立绘与角色.md`（200×400 立绘约束）、`B15-图层渲染与换装机制.md`（换装决策表）

本文定义 Naiz 引擎的 VRAM 渲染策略——背景加载、立绘叠加、对话框覆盖、文字局部刷新的完整顺序与约束。

---

## 1. 硬件前提：PC-98 只有一个图形层

在 `640×400 256c PEGC` 模式下（`INT 18h AH=30h AL=0x08`），PC-98 硬件提供：

| 资源 | 数量 | 结构 |
|------|------|------|
| 图形层 | **1 层** | PEGC bank-switched packed-pixel 256c，窗口 0xA8000–0xAFFFF |
| 文字层 | 1 层 | 独立 VRAM（0xA0000/0xA2000），**DOS/4GW 保护模式下不可用于可见输出** |

图形层无硬件 overlay（叠加）——所有像素共享同一组 packed-pixel VRAM。视觉上的"背景 + 立绘 + 对话框"分层效果**完全由软件写入顺序实现**。

> **注意**：GDC 支持两个显示页（page 0 / page 1），通过 `outb(0xA4, page)` 切换。这是 page flipping（双缓冲），不是硬件叠加——任何时候屏幕上只有一个页面可见。

---

## 2. 四趟渲染顺序

引擎的完整渲染流程分为四个阶段，按时间先后执行。核心变化：**对话框不在 `bgload` 时绘制，延迟到首次 `text` 时**，确保精灵在对话框之下。

### 2.1 第一趟：背景层（全屏 + 快照）

```
bg(id) 命令触发时执行一次
─────────────────────────────────────────
  image_load(id)                    ← 从 IMAGE.DAT 解压 MAG
  image_set_palette(img)            ← 更新调色板（跳过索引 7、15、≥248）
  vram_blit(img, 0, 0)             ← PEGC bank 窗口写入全屏 640×400
  mag_free(img)                     ← 释放解压后的临时内存
  layer_capture_bg()               ← 保存全屏 256KB 快照到 bg_snapshot
  dialog_drawn = 0                 ← 对话框尚未绘制
```

**效果**：VRAM 被背景完全覆盖。同时 `bg_snapshot` 保存纯背景用于后续精灵恢复。

### 2.2 第二趟：立绘 / 精灵层（指定位置）

```
char <name> <l|c|r> [expr] 命令触发时执行
─────────────────────────────────────────
  MagImage *img = image_load(sprite_id) ← 从 IMAGE.DAT 解压
  /* 不调用 image_set_palette —————— 共享背景调色板 */
  vram_blit_sprite(img, x, y, 15, 0)   ← 逐像素 blit，跳过索引 15（透明色）
  mag_free(img)
```

**效果**：在背景之上绘制角色。精灵全幅 200×400 绘制，此时对话框尚未出现，精灵可以自由延伸到屏幕底部。

### 2.3 第三趟：对话框层（首次 dialog_show 触发）

```
首次 dialog_show() 触发时执行一次
─────────────────────────────────────────
  layer_dialog_open():
    scene_draw_dialog():                 ← 整体对话框
      fill_rect(80, 280, 480, 115, 248)    ← 底色（palette 248，黑或蓝）
      draw_rect(80, 280, 480, 115, 2, 7)   ← 白边 2px（palette 7）
  dialog_drawn = 1
  draw_text("对白内容…", 104, 308, 7)      ← 写新文字
```

**效果**：对话框在精灵**之上**。精灵延伸入 `[80,280,480,115]` 区域的像素被对话框覆盖。背景快照不受影响。

### 2.4 第四趟：文字层（翻页）

```
后续 dialog_show() 翻页时执行
─────────────────────────────────────────
  layer_dialog_restore()                 ← 从快照恢复对话框
  draw_text("对白内容…", 104, 308, 7)     ← 写新文字
  → 边框、对话框底色不重绘
```

---

## 3. 图层的可逆性（基于快照的局部恢复）

### 3.1 关键约束

```
VRAM 是"画布"而非"图层"。一旦被对话框/精灵覆盖，原像素永久丢失。
但 bg_snapshot 提供了"时间机器"——可以从内存快照恢复任意矩形区域。
```

| 场景 | 恢复方法 |
|------|----------|
| 加载新背景 | `bg` → 全屏 `vram_blit` → `layer_capture_bg()` 新快照 |
| 切换对白行 | `layer_dialog_snap()` + `layer_dialog_restore()` → 新文字 |
| 换表情 | `bg_restore_rect(x, y, 200, DIALOG_Y-y, clip=1)` 恢复背景 |
| 换装/换位置 | `bg_restore_rect(union_bbox, clip=0)` + `layer_dialog_refresh()` |
| 隐藏精灵 | `bg_restore_rect(old_rect, clip=0)` + 若覆对话框则 `dialog_refresh()` |

### 3.2 场景转换的处理

当场景脚本触发新 `bg`：

```
顺序（固定）：
1. vram_blit(new_mag, 0, 0)                ← 全屏新背景（覆盖一切）
2. layer_capture_bg()                       ← 新快照（覆盖旧快照）
3. dialog_drawn = 0                         ← 对话框未绘
4. char <name> <l|c|r> [expr]               ← 精灵全幅（对话框尚未出现）
5. dialog_show() → layer_dialog_open()      ← 首次 dialog_show 画对话框
```

---

## 4. 局部刷新策略

### 4.1 原则

**只重绘变化的区域，不动不变的区域。** 通过 `bg_snapshot` 快照实现非全屏的精灵恢复。

### 4.2 各操作刷新范围

| 触发事件 | 刷新区域 | 像素操作数 | 耗时估算 |
|----------|----------|-----------|---------|
| 场景切换（新 `bg`） | 全屏 640×400 | 256,000 vram_blit | ~15ms |
| 对话框初始化 | 480×115 fill + 边 | ~55,000 fill | ~3ms |
| 对白翻行（`dialog_show`） | dialog_snapshot restore + text | ~55,000 + text | ~3.5ms |
| **换表情（`face`）** | 200×280 恢复 + blit | ~22,000 restore + ~12,000 blit | **~1.5ms** |
| **换装/换位置（`replace`）** | ~400×400 恢复 + 200×400 blit + 对话框 | ~40,000 restore + ~40,000 blit + 55,000 dialog | **~5.5ms** |
| **隐藏精灵（`hide`）** | ~400×400 恢复 | ~40,000 restore | **~1.2ms** |

### 4.3 换表情的裁剪优化

`face` 操作利用裁剪避免重绘对话框区域：

```
恢复区域 = [x, y, 200, DIALOG_Y - y]    ← 只恢复到对话框顶边
绘制区域 = [x, y, 200, DIALOG_Y - y]    ← 只绘制到对话框顶边
对话框区域内像素完全不变                ✅
```

`replace` 操作不裁剪（全幅恢复+全幅绘制），最后 `layer_dialog_refresh()` 重绘对话框。

更详细的决策表和性能分析见 `B15-图层渲染与换装机制.md` §5（决策表）和 §8（性能分析）。

---

## 5. 精灵更换策略

### 5.1 三状态决策

所有精灵操作通过 `scene_layers` 模块统一调度：

| 操作 | API | 恢复背景 | 绘制精灵 | 重绘对话框 |
|------|-----|---------|---------|-----------|
| 初始化（`dialog_drawn==0`） | `layer_sprite_show()` | 不恢复 | 全幅 | 不适用 |
| 换表情（同角色不同表情） | `layer_sprite_face()` | 裁剪至 `[0, DIALOG_Y)` | 裁剪至 `[0, DIALOG_Y)` | **不重绘** |
| 换装/换位置 | `layer_sprite_replace()` | 全幅 union bbox | 全幅 | 重绘 |
| 隐藏 | `layer_sprite_hide()` | 全幅旧位 | 不绘制 | 若需则重绘 |

### 5.2 与 bg_snapshot 的关系

```
bg_snapshot (256KB, 640×400)
     │
     ├── restore_rect(x, y, w, h, clip_dialog=1)
     │     用于 face：仅恢复 y<DIALOG_Y 的区域，不碰对话框
     │
     └── restore_rect(x, y, w, h, clip_dialog=0)
           用于 replace/hide：全幅恢复，之后由 dialog_refresh 修补
```

### 5.3 调试输出

引擎通过串口输出每次图层操作的阶段标记：

| 标记 | 含义 |
|------|------|
| `BGSNAP` | `layer_capture_bg()` 完成 |
| `DLGOPEN` | `layer_dialog_open()` 完成 |
| `DLGREFR` | `layer_dialog_refresh()` 完成 |
| `FACE` | `layer_sprite_face()` 完成 |
| `REPLACE` | `layer_sprite_replace()` 完成 |
| `HIDE` | `layer_sprite_hide()` 完成 |

---

## 6. 与其他文档的集成

| 文档 | 集成点 |
|------|--------|
| `B02-显示管线规范.md` §2 | Init 序列 |
| `B02-显示管线规范.md` §9 | 对话框布局、渲染顺序 |
| `B11-MAG图片加载与显示规范.md` §5.2 | 调色板保护 |
| `B11-MAG图片加载与显示规范.md` §6 | `vram_blit()` / `vram_blit_sprite()` 算法 |
| `B11-MAG图片加载与显示规范.md` §11 | Sprite/立绘加载流程 |
| `C01-引擎基本概念.md` §3 | 制作者视角的 UI 概念 |
| `C02-对话框样式方案.md` | 6 种预设样式 |
| `C03-立绘与角色.md` | 200×400 立绘标准、跨表情制图约束 |
| `B15-图层渲染与换装机制.md` | `scene_layers` 模块 API、决策表、操作码 |

---

## 7. 对话框变体（引擎实现）

### 7.1 设计目的

基本渲染策略（背景 → 覆盖）支持不同对话框视觉效果，核心差异在于覆盖区域是**实心填充**还是**图案点阵**。

10 种预设样式（见 `C02-对话框样式方案.md` §1）：

| 索引 | 枚举名 | 类型 | 覆盖色 | 密度 |
|------|--------|------|--------|------|
| 0 | `SOLID_BLACK` | 不透明 | palette 248（黑） | 100% |
| 1 | `DITHER75_BLACK` | 透明 | palette 248（黑） | 75% |
| 2 | `SOLID_BLUE` | 不透明 | palette 248（蓝） | 100% |
| 3 | `DITHER75_BLUE` | 透明 | palette 248（蓝） | 75% |
| 4 | `SOLID_RED` | 不透明 | palette 248（暗红） | 100% |
| 5 | `DITHER75_RED` | 透明 | palette 248（暗红） | 75% |
| 6 | `SOLID_GREEN` | 不透明 | palette 248（深绿） | 100% |
| 7 | `DITHER75_GREEN` | 透明 | palette 248（深绿） | 75% |
| 8 | `SOLID_PURPLE` | 不透明 | palette 248（紫） | 100% |
| 9 | `DITHER75_PURPLE` | 透明 | palette 248（紫） | 75% |

**编码**：`(color_idx<<1) | dither_bit` (color_idx 0-4, dither 0/1)，连续无间隙。

**全局配置**：引擎通过 `g_dialog_style` 全局变量（`unsigned char`）选择当前样式。场景脚本可通过 `dlgstyle` 命令在运行时切换。

**统一行为**（全样式共享）：
- 边框：2px 白色实线 (`draw_rect`, color=7)，**不使用图案填充**
- 提示文字：白色 "Space/Enter"，**不使用图案**
- 文字区域：无实心底衬，白字直接写在图案背景上
- 翻行时：旧文字区域先以与对话框相同的图案覆盖（恢复半透明），再写新字

### 7.2 `fill_rect_pattern()` — 图案掩码填充

**文件**：`core/engine/render.c` + `render.h`

```c
void fill_rect_pattern(int x, int y, int w, int h,
                       const uint8_t pattern[8], uint8_t color);
```

**算法**（PEGC bank 窗口 + 图案跳过）：

```c
void fill_rect_pattern(int x, int y, int w, int h,
                       const uint8_t pattern[8], uint8_t color)
{
    int px, py, addr;
    uint8_t byte;
    for (py = 0; py < h; py++) {
        byte = pattern[(y + py) & 7];      /* 8×8 周期 */
        for (px = 0; px < w; px++) {
            if (!(byte & (0x80 >> (px & 7))))
                continue;                    /* 图案 bit=0 → 跳过 */
            addr = (y + py) * 640 + (x + px);
            *PEGC_BANK = (uint16_t)(addr >> 15);
            VRAM_WIN[addr & (BANK_SZ - 1)] = color;
        }
    }
}
```

**设计要点**：
- PEGC packed-pixel 写入，每字节 = 1 像素
- 图案 bit=0 时**完全跳过 VRAM 访问**——性能关键（节省 50%–75%）
- `pattern` 参数是 `const uint8_t[8]` — 8 字节编码 8×8 像素掩码，MSB 为左

### 7.3 图案位图定义

```c
#define PAT_BITS 8

/* 40% 密度：Bayer 4×4 有序抖动点阵（阈值 < 6，24/64 bit） */
static const uint8_t pattern_40[8] = {
    0xAA,   /* 1010 1010 — ▓░▓░ */
    0x44,   /* 0100 0100 — ░▓░░ */
    0xAA,   /* 1010 1010 — ▓░▓░ */
    0x11,   /* 0001 0001 — ░░░▓ */
    0xAA,   /* 1010 1010 */
    0x44,   /* 0100 0100 */
    0xAA,   /* 1010 1010 */
    0x11,   /* 0001 0001 */
};



/* 75% 密度：对角错位空隙（48/64 bit，每行 2 透明缺口） */
static const uint8_t pattern_75[8] = {
    0xEE,   /* 1110 1110 — ▓▓▓░▓▓▓░ */
    0x77,   /* 0111 0111 — ░▓▓▓░▓▓▓ */
    0xBB,   /* 1011 1011 — ▓░▓▓▓░▓▓ */
    0xDD,   /* 1101 1101 — ▓▓░▓▓▓░▓ */
    0xEE,   /* 1110 1110 */
    0x77,   /* 0111 0111 */
    0xBB,   /* 1011 1011 */
    0xDD,   /* 1101 1101 */
};
```

**图案规范**：
- 8 字节 = 8 行，每字节 8 列（bit=1 = 该像素写覆盖色）
- `pattern_40`：24 bit / 64 bit ≈ 40%（Bayer 4×4 有序抖动，`0xAA/0x44/0xAA/0x11` 循环）
- `pattern_75`：48 bit / 64 bit = 75%（对角错位空隙，`0xEE/0x77/0xBB/0xDD` 循环）
- 实心（100%）不使用图案表，直接调现有的 `fill_rect()`

### 7.4 `scene_draw_dialog()` — 对话框绘制

所有样式使用 palette **248** 作为底色（由 `C02-对话框样式方案.md` 定义的 2 位编码：`style & 1` 控制是否使用抖动，`style >> 1` 表示颜色索引）。`draw_rect` 统一画白边：

```c
void scene_draw_dialog(void)
{
    if (g_dialog_style & 1)
        fill_rect_pattern(DIALOG_X, DIALOG_Y, DIALOG_W, DIALOG_H, PAT75, 248);
    else
        fill_rect(DIALOG_X, DIALOG_Y, DIALOG_W, DIALOG_H, 248);
    draw_rect(DIALOG_X, DIALOG_Y, DIALOG_W, DIALOG_H, DIALOG_BORDER, 7);
}
```

**注意**：实际实现采用 `if (g_dialog_style & 1)` 的简洁形式，支持所有 10 种样式（5 色 × 2 密度）。`draw_rect` 在 if/else 之后统一执行。对话框由 `layer_dialog_open()`、`layer_dialog_refresh()` 或 `layer_dialog_rebuild()` 调用。

### 7.5 `dialog_show()` — 文字区清除与绘制

旧文字区清除使用与对话框背景**相同的图案和 palette 248**——不留文字的残留像素，同时保持区域的半透明视觉效果：

```c
void dialog_show(const char *charname, const char *text)
{
    int mw = DIALOG_W - DIALOG_INDENT - DIALOG_RIGHT_INDENT;

    if (dialog_state.text_offset < 0) {
        dialog_state.charname = charname;
        strncpy(dialog_text_buf, text, sizeof(dialog_text_buf) - 1);
        dialog_text_buf[sizeof(dialog_text_buf) - 1] = '\0';
        dialog_state.text = dialog_text_buf;
        dialog_state.text_offset = 0;
    }

    if (!layer_dialog_drawn()) {
        layer_dialog_open();
    } else {
        layer_dialog_snap();
    }
    layer_dialog_restore();

    if (dialog_state.charname)
        draw_text(dialog_state.charname, 0,
                  DIALOG_X + DIALOG_INDENT, DIALOG_Y + DIALOG_HEADER_Y,
                  mw, DIALOG_BOTTOM, 1, PAL_WHITE);

    int next = draw_text(dialog_state.text, dialog_state.text_offset,
                         DIALOG_X + DIALOG_INDENT, DIALOG_Y + DIALOG_TEXT_Y,
                         mw, DIALOG_Y + DIALOG_TEXT_Y + 60, 0, PAL_WHITE);
    if (next >= 0) {
        dialog_state.text_offset = next;
        /* 暂停等待翻页 */
    } else {
        dialog_state.text_offset = -1;
        dialog_state.text = NULL;
    }
}
```

**关键**：所有样式统一使用 palette 248。`draw_text` 第 6 个参数 `max_y = DIALOG_Y + DIALOG_TEXT_Y + 60` 限制每页 3 行，超出的文字返回字节偏移，`dialog_show()` 据此通知 VM 暂停等待翻页。角色名头部以粗体（`bold=1`）绘制于对话框顶部，不参与翻页。`dlg_update_palette()` 在 `dlgstyle` 切换时动态改色。

### 7.6 性能

| 样式 | 对话框区域 | 每像素 VRAM 写 | 相对成本 |
|------|-----------|---------------|---------|
| 实心 (100%) | 480×115 = 55,200 | 1 (PEGC byte) | 100% |
| 40% 图案 | 55,200 × 40% = 22,080 | 1 (PEGC byte) | 40% |
| 75% 图案 | 55,200 × 75% = 41,400 | 1 (PEGC byte) | 75% |

图案填充的实际 VRAM 写入次数**低于**实心 `fill_rect()`。跳过像素不产生 VRAM 访问。

---

## 8. 潜在扩展

以下场景当前未实现，但架构已为其预留空间：

| 场景 | 方案 |
|------|------|
| 文字效果（颜色/颜色变化） | 增加 `op_text_color` 操作码，调 `draw_text(text, x, y, new_color)` 不重绘边框 |
| 场景切换动画（渐变/滑动） | 利用 GDC page flipping（显示页切换），在另一页构建好后再翻页 |
| 对话框淡入/淡出 | 在 `bg_snapshot` 上逐帧混合调色板或 fill_rect_pattern 密度 |

---

## 9. 立绘 / 精灵渲染细节

### 9.1 渲染位置

精灵由场景脚本指定左上角坐标 `(x, y)`。标准立绘尺寸 200×400，y=0 对齐屏幕顶，底部接触屏幕底。

### 9.2 重叠处理（四趟顺序）

```
趟次          写入内容                  覆盖关系
────────────────────────────────────────────────
第一趟(bg)     背景全屏 640×400          地基
第二趟(char)   立绘 200×400             在背景之上
第三趟(dialog) 对话框 480×115           在立绘之上（覆盖重叠区）
第四趟(text)   文字行                    在对话框之上
```

结果：对话框白字和边框始终在最前。精灵延伸入对话框区域的像素被对话框底色覆盖。

### 9.3 精灵恢复（基于 bg_snapshot）

PC-98 的单层 VRAM 中，修改后的精灵像素可通过 `bg_snapshot` 恢复：

| 操作 | 恢复方法 |
|------|----------|
| 移动精灵 | `sprite_replace(id, nx, ny)` → `bg_restore_rect` union + blit 新位 + `dialog_refresh` |
| 隐藏精灵 | `sprite_hide(id)` → `bg_restore_rect` 旧位 + 对话框修补 |
| 切换精灵（表情） | `sprite_face(id, x, y)` → 裁剪至 `y<280` 恢复 + blit，**不碰对话框** |
| 切换精灵（换装） | `sprite_replace(id, x, y)` → 全幅恢复 + blit + `dialog_refresh` |

### 9.4 精灵尺寸标准

- **标准尺寸**：200×400（接触屏幕底部）
- 精灵必须 ≤ 640×400（越界部分被 `vram_blit_sprite` 裁剪）
- 同角色跨表情：**底部 120px（y≥280）必须像素级一致** —— 见 `C03-立绘与角色.md` §3.5

### 9.5 性能

标准立绘 200×400 blit 性能：

| 操作 | 像素 | 透明比例 | 有效写入 |
|------|------|----------|----------|
| 全幅 blit | 80,000 | ~50% | ~40,000 |
| 裁剪 blit（换表情） | 56,000 (200×280) | ~50% | ~28,000 |

### 9.6 调色板共享

精灵不设自己的调色板（共享背景调色板），约束同前。

详见 `C03-立绘与角色.md` §6。

---

## 10. 菜单渲染策略

### 10.1 菜单即增量覆盖层

菜单在渲染层面等价于"位于屏幕中部的另一个对话框"：

```
趟次          写入内容                      覆盖关系
────────────────────────────────────────────────
第一趟(bg)     背景全屏 640×400              地基
第二趟(char)   立绘 200×400                 在背景之上
第三趟(dialog) 对话框 480×115               在立绘之上
第四趟(text)   文字行                       在对话框之上
第五趟(menu)   菜单背景 + 选项文字 + 选中色   在对话框之上（位置不同）
```

背景样式与对话框一致：`fill_rect(248) + fill_rect_pattern(PAT40, 248) + draw_rect(thick=2, 7)`。

### 10.2 菜单渲染架构（增量式）

菜单重新渲染时**不清全屏，只重写菜单区域内的 VRAM 像素**。每次键盘输入方向键（`KBD_UP`/`KBD_DOWN`）触发：

1. **选中移动到新 item**（`menu_highlight` / `menu_unhighlight` 成对）
2. **文字区无条件重绘**（`menu_draw_item` 每帧调用，即使选中无变化）

### 10.3 闪烁原因分析

PC-98 引擎的闪烁根源与常规 VBlank 同步无关，而是由**累积的时间窗口** + **中间状态可见**共同导致：

| 原因 | 详情 |
|------|------|
| `GDC_MODE1_DISPLAY_OFF/ON` 不可用 | NP2kai 不接受 DISPLAY OFF 指令（所有 VBlank 同步方案失效） |
| 无双缓冲 | PEGC 只有一层 VRAM，每次 `fill_rect` / `draw_glyph` 都即时写入显示 |
| 逐像素字形写入慢 | `draw_glyph()` ＝ PEGC bank 切换(2 outb) + 16 次像素写入，每个字约 30+ 个 VRAM 周期 |
| palette 切换全局可见 | 调色板是 DAC 级共享资源——任何时候修改都瞬时影响所有像素 |
| 全部重绘开销聚集 | 每帧 8–12 个字 × n 选项的全帧重写 → 足够长时间内（按 PEGC 约 100ns/byte 计 ≈ 0.1ms 级别），用户看到绘制过程 |

### 10.4 消除闪烁的固定策略

```
已确认实现的三条规则（缺一不可）：
```

**① 专用 palette 索引**（250/251），永不与场景图像共享索引：
- `MENU_PAL_WHITE = 250`：菜单文字色（白色），初始化时写入一次，运行时永不改变
- `MENU_PAL_YELLOW = 251`：菜单选中色（黄色），初始化时写入一次，运行时永不改变
- 这样菜单选中切换**不通过修改 palette 色值**实现，而是通过修改 VRAM 中像素值

**② 选中先高亮再取消——"highlight-first" 顺序**：
```c
if (selected_changed) {
    int new_index = menu_selected;
    int old_index = menu_prev_selected;
    menu_highlight(new_index);      // 先新: MENU_PAL_YELLOW
    menu_unhighlight(old_index);    // 后旧: MENU_PAL_WHITE
}
```
反序（先取消后高亮）会在短暂窗口内看到"无任何选中项"的状态——用户视觉上感知为闪烁。

**③ 每帧无条件重绘所有 option 的文字区域**：
选中高亮写入黄色像素后，旧选中的白色恢复可能会将新选中的黄色覆盖。无条件重绘所有选项的文字区保证每帧的最终状态正确，且因为文字数量少（典型 ≤6 项，每项 ≤20 字），总 VRAM 写入量可控。

### 10.5 关键约束

| 约束 | 原因 |
|------|------|
| palette 250/251 永不修改 | 所有文本绘制依赖固定色值。8-bit 调色板修改会瞬时影响全屏——哪怕 BG 图像不使用该索引，NPC 调色板操作也会波及 |
| `image_set_palette()` 跳过 ≥248 | 背景加载时 palette 索引 ≥248 不会被覆写——引擎侧保护已在 B11 §12.3.3 定义并实现 |
| `pack_images.py` 全量 remap | 所有图像（sprites + BG）在构建时脱离 PROTECTED_IDX（≥248），运行期无冲突风险 |
| 菜单背景和对话框同质化 | 菜单背景直接用相同的 `fill_rect` + `fill_rect_pattern` + `draw_rect` 函数，使用 palette 248 和 7。不引入新的背景绘制逻辑 |
| 不绘制"箭头指示器" | 选中项通过整体色差（黄/白）区分，无需额外 `draw_text("->")` —— 箭头引入新的闪烁点（箭头清除滞后于文字重绘） |

**Agent 强制规则**：菜单/UI 选项高亮渲染必须使用专用 palette 索引，不得在用户交互过程中切换 palette 色值。选中顺序必须为先高亮后取消，以避免可见的"无选中"中间帧。菜单样式必须与对话框保持一致，使用 palette 248/7 而非自定义背景。

---

## 11. 修订历史

| 版本 | 日期 | 修改内容 |
|------|------|----------|
| 1.0 | 2026-06-10 | 初版 |
| 1.1 | 2026-06-10 | 对话框变体 |
| 1.2 | 2026-06-10 | 两趟→三趟：立绘层 |
| 2.0 | 2026-06-12 | PEGC 256c 全线更新 |
| 3.0 | 2026-06-12 | **三趟→四趟**：对话框延迟到首次 text 触发；新增 `bg_snapshot` 快照恢复机制；精灵操作决策表；`layer_dialog_open/refresh`；裁剪策略；删除 F1:help；200×400 立绘；480×115 对话框；引用 B15 换装机制文档 |
| 3.1 | 2026-06-13 | op_text 翻页实现：`max_y = DIALOG_Y + DIALOG_TEXT_Y + 60`（3 行限制），draw_text 返回字节偏移用于翻页续印；新增 header_table 角色名头部；50% 图案→75%；DIALOG_INDENT=24→12 |
