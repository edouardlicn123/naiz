# B12 — VRAM 渲染策略：背景/精灵/对话框/文字分层与 blit 发布

> **状态**：活跃维护
> **创建**：2026-06-10
> **最后更新**：2026-09-11（R19-R23 图层化：对话框/菜单改为 RAM 复合缓冲合成 + blit 发布，见 B93）
> **依赖**：`B02-显示管线规范.md`（VRAM 布局、图元函数）、`B11-MAG图片加载与显示规范.md`（背景/立绘 loading）、`B93-图层渲染与菜单图层规范.md`（当前图层范式）、`B15-图层渲染与换装机制.md`（换装决策表、对话框复合缓冲）

本文定义 Naiz 引擎的 VRAM 渲染策略——背景加载、立绘叠加、对话框覆盖、文字局部刷新的完整顺序与约束。

---

## 1. 硬件前提：PC-98 只有一个图形层

在 `640×400 256c PEGC` 模式下（`INT 18h AH=30h AL=0x08`），PC-98 硬件提供：

| 资源 | 数量 | 结构 |
|------|------|------|
| 图形层 | **1 层** | PEGC bank-switched packed-pixel 256c，窗口 0xA8000–0xAFFFF |
| 文字层 | 1 层 | 独立 VRAM（0xA0000/0xA2000），**DOS/4GW 保护模式下不可用于可见输出** |

图形层无硬件 overlay（叠加）——所有像素共享同一组 packed-pixel VRAM。视觉上的"背景 + 立绘 + 对话框"分层效果**完全由软件写入顺序实现**。

> **R19/R23 更新**：对话框与菜单是反复重绘的覆盖层，已改为 **RAM 复合缓冲离屏合成 + 整框/整屏 blit 发布**（`dialog_layer` / `menu_layer`，见 `B93` §3-§4）。绘制先在 RAM 完成（无中间态可见帧），再一次性写 VRAM；z 序仍唯一由 VRAM 写入顺序决定——背景 → 精灵 → 对话框 → 文字 → 菜单。

> **注意**：GDC 支持两个显示页（page 0 / page 1），通过 `outb(0xA4, page)` 切换。这是 page flipping（双缓冲），不是硬件叠加——任何时候屏幕上只有一个页面可见。

---

## 2. 分层渲染顺序

引擎的完整渲染流程按时间先后执行。核心不变：**对话框不在 `bgload` 时绘制，延迟到首次 `text` 时**，确保精灵在对话框之下。R19 起对话框/菜单先合成为 RAM 复合缓冲再整块发布（虚线为 RAM 阶段）。

### 2.1 第一层：背景层（全屏 + 快照）

```
bg(){key} 命令触发时执行一次（layer_bg_change 统一入口）
─────────────────────────────────────────
  image_load(id)                    ← 从 IMAGE.DAT 解压 MAG
  image_set_palette(img)            ← 更新调色板（跳过 ≥248 保护位）
  vram_blit(img, 0, 0)             ← 全屏 640×400
  ── 快照（源图直拷，零 VRAM 回读）──
    layer_capture_bg_from_image(img→bg_snapshot)       (static)
    layer_capture_bg_dialog_from_image(img→under_dialog)
  layer_redraw_sprites()           ← 全身重绘；尾部 sync_dialog_base
  dlg_update_palette() / btn_update_palette()
  mag_free(img)                     ← 释放解压后的临时内存
```

**效果**：VRAM 被背景完全覆盖。`bg_snapshot`（全屏）+ `under_dialog`（对话框区纯背景）均来自源图像素缓冲——**内存直拷，绝无 VRAM 回读**（R19）。对话框若已打开，`layer_redraw_sprites` 尾部重建 `dialog_occluder` 并 `layer_dialog_recompose` 重绘框+当前页文字——**跨图存活**（见 §2.3）。

### 2.2 第二层：立绘 / 精灵层（指定位置）

```
char <name> <l|c|r> [expr] 命令触发时执行
─────────────────────────────────────────
  MagImage *img = image_load(sprite_id) ← 从 IMAGE.DAT 解压
  /* 不调用 image_set_palette —————— 共享背景调色板 */
  vram_blit_sprite(img, x, y, 15, 0)   ← 逐像素 blit，跳过索引 15（透明色）
  mag_free(img)
```

**效果**：在背景之上绘制角色。R20 起精灵**全幅 200×400 绘制，对话框开启时也不再裁剪**（取消旧 Option X 的 y<280 裁剪），对话框合成在其上；face 仅上半身 clip 沿用（§4.3）。精灵变更尾部 `layer_sprite_sync_dialog_base()` 重建活动底，保证伪透明孔洞透出立绘。

### 2.3 第三层：对话框层（RAM 复合缓冲，首次 dialog_show 触发）

```
首次 dialog_show() 触发时执行一次
─────────────────────────────────────────
  layer_dialog_show():                    ← 确保缓冲持有框
    alloc dialog_layer + dialog_occluder（OOM→直绘 VRAM 降级）
    set_active(DIALOG,TEXT)；sync_dialog_base()   ← 建活动底
    dialog_paint_box(dialog_layer)        ← 框（PAT75 孔洞保留已种底）

  layer_dialog_render_page(name,text,off):  ← 一页合入 RAM 缓冲
    dialog_seed_base()  →  dialog_paint_box()（擦上一页文字）
    text_set_target(缓冲) + draw_text(角色名/正文) + text_set_target_vram()

  dialog_layer_store_render(name,text,off)  ← 记录投影（换图重绘用）
  dialog_layer_blit()                     ← 整框原子发布：vram_write 55KB
```

**效果**：对话框合成覆盖精灵。精灵延伸入 `[80,280,480,115]` 区域的像素在 RAM 合成时覆盖（dither 孔洞透出活动底，伪透明）。背景快照不受影响。

### 2.4 第四层：文字层（翻页）

```
后续 dialog_show() 翻页时执行
─────────────────────────────────────────
  layer_dialog_render_page(name,text,next_off)  ← 重画框 + 新文字进缓冲
  dialog_layer_store_render(...)
  dialog_layer_blit()                     ← 整框再发布
  → 无 VRAM 中间态：旧文字与边框底色在 RAM 内一次清除+重画
```

---

## 3. 图层的可逆性（基于快照/复合缓冲的恢复）

### 3.1 关键约束

```
VRAM 是"画布"而非"图层"。一旦被对话框/精灵覆盖，原像素永久丢失。
bg_snapshot 提供"时间机器"——可从内存快照恢复任意矩形区域。
对话框/菜单层已是 RAM 复合缓冲（程序化生成），其清除/重绘不消耗 VRAM 读。
```

| 场景 | 恢复方法 |
|------|----------|
| 加载新背景 | `layer_bg_change` → 全屏 blit + 源图直拷双快照 |
| 切换对白行 | `layer_dialog_render_page(新页)` → `dialog_layer_blit()`（RAM 重合成 + 整框发布） |
| 换表情 | `layer_bg_restore_rect(x, y, 200, DIALOG_Y-y, clip=1)` 恢复背景 |
| 换装/换位置 | `layer_bg_restore_rect(union_bbox, clip=1)` + 全幅 blit + `sync_dialog_base` |
| 隐藏精灵 | `layer_bg_restore_rect(old_rect, clip=1)` + `sync_dialog_base` |

> R20 起精灵恢复一律 `clip_dialog=1`（跳过对话框矩形）——对话框合成在立绘之上，恢复路径不得盖框（Revoked Option X）。

### 3.2 场景转换的处理

当场景脚本触发新 `bg`：

```
顺序（固定，layer_bg_change 收口）：
1. vram_blit(new_mag, 0, 0)                ← 全屏新背景（覆盖一切）
2. 双快照（源图直拷 → bg_snapshot / under_dialog）
3. layer_redraw_sprites()                  ← 精灵全身重绘（尾部 sync_dialog_base）
4. dlg/btn 调色板刷新
5. 若对话框已开 → layer_dialog_recompose（投影重绘框+文字）+ blit
6. char <name> <l|c|r> [expr]              ← 后续立绘全身
```

---

## 4. 局部刷新策略

### 4.1 原则

**只重绘变化的区域，不动不变的区域。** 全屏/立绘恢复通过 `bg_snapshot` 快照实现；对话框与菜单层在 RAM 复合缓冲中增量合成，只对变化矩形做 VRAM 发布。

### 4.2 各操作刷新范围

| 触发事件 | 刷新区域 | 像素操作数 | 耗时估算 |
|----------|----------|-----------|---------|
| 场景切换（新 `bg`） | 全屏 640×400 | 256,000 vram_blit + 快照 RAM 拷 | ~15ms |
| 对话框初始化 | RAM 合成 55KB×2 + 55KB blit | ~55,000 blit | ~3ms |
| 对白翻行（`dialog_show`） | RAM 重合成 + 55KB blit | ~55,000 blit | ~3.5ms |
| **换表情（`face`）** | 200×280 恢复 + blit | ~22,000 restore + ~12,000 blit | **~1.5ms** |
| **换装/换位置（`replace`）** | ~400×400 恢复 + 200×400 blit + occluder 重建 | ~40,000 restore + ~40,000 blit + RAM 55KB | **~5.5ms** |
| **隐藏精灵（`hide`）** | ~400×400 恢复 + occluder 重建 | ~40,000 restore | **~1.2ms** |
| **菜单全量（R23）** | 全屏 opaque 合成 + 全屏 blit | 256KB RAM + 256KB blit | **~2-4ms** |
| **菜单增量（R23）** | `menu_layer_blit_rect` 局部矩形 | 局部 vram_write | **≪1ms** |

> 对话框翻行的"恢复"成本已从 VRAM 读-写转移到 RAM 重合成（单次整框 blit）——中间态不可见，bank 端口写降到逐行。

### 4.3 换表情的裁剪优化

`face` 操作利用裁剪避免重绘对话框区域：

```
恢复区域 = [x, y, 200, DIALOG_Y - y]    ← 只恢复到对话框顶边
绘制区域 = [x, y, 200, DIALOG_Y - y]    ← 只绘制到对话框顶边
对话框区域内像素完全不变                ✅
```

`replace` 操作不裁剪（全幅恢复+全幅绘制），`layer_sprite_replace` 尾部重建活动底让对话框合成盖回（R20）。

更详细的决策表和性能分析见 `B15-图层渲染与换装机制.md` §5（决策表）和 §8（性能分析）。

---

## 5. 精灵更换策略

### 5.1 三状态决策

所有精灵操作通过 `scene_layers` 模块统一调度：

| 操作 | API | 恢复背景 | 绘制精灵 | 重绘对话框 |
|------|-----|---------|---------|-----------|
| 初始化（`dialog_drawn==0`） | `layer_sprite_show()` | 不恢复 | 全幅 | 不适用 |
| 换表情（同角色不同表情） | `layer_sprite_face()` | 裁剪至 `[0, DIALOG_Y)` | 裁剪至 `[0, DIALOG_Y)` | **不重绘**（clip=1） |
| 换装/换位置 | `layer_sprite_replace()` | 全幅 union bbox（clip=1） | 全幅 | sync_dialog_base + recompose（缓冲层重画） |
| 隐藏 | `layer_sprite_hide()` | 全幅旧位（clip=1） | 不绘制 | sync_dialog_base（若覆盖框区） |

> R20 起 `layer_sprite_replace/hide` 的对话框重绘由"活动底重建 + 缓冲内重画 + 整框 blit"完成（不再是 `layer_dialog_refresh` 直写 VRAM）。

### 5.2 与 bg_snapshot 的关系

```
bg_snapshot (256KB, 640×400，源图直取)
     │
     ├── layer_bg_restore_rect(x, y, w, h, clip_dialog=1)
     │     用于 face：仅恢复 y<DIALOG_Y 的区域，不碰对话框
     │
     └── layer_bg_restore_rect(x, y, w, h, clip_dialog=1)
           用于 replace/hide：全幅恢复但跳过对话框矩形，由 occluder 重建补回

under_dialog (55KB, 480×115)  ← 对话框区纯背景（源图直取），hide 时 vram_write 还原
dialog_occluder (55KB, 480×115) ← 纯背景+立绘框内像素，复合缓冲种底、伪透明孔
```

### 5.3 调试输出

- 图层状态/图像导出：`layer_debug.c`（`dump bg|sprite|dialog|anim|all|status`，写宿主文件 `layer_debug:*` 日志，`layer_dialog_snapshot()` 供 dump 读取对话框复合缓冲）
- OOM 诊断：dialog/menu 复合缓冲与 `bg_snapshot` 分配失败均打 `hal_log("OOM: ...")`（C14 强制）

> 旧版本每图层操作的 `BGSNAP/DLGOPEN/DLGREFR/FACE/REPLACE/HIDE` 阶段标记已随 R19 图层化移除。

---

## 6. 与其他文档的集成

| 文档 | 集成点 |
|------|--------|
| `B02-显示管线规范.md` §2 | Init 序列 |
| `B02-显示管线规范.md` §9 | 对话框布局、渲染顺序 |
| `B11-MAG图片加载与显示规范.md` §5.2 | 调色板保护 |
| `B11-MAG图片加载与显示规范.md` §6 | `vram_blit()` / `vram_blit_sprite()` 算法 |
| `B11-MAG图片加载与显示规范.md` §11 | Sprite/立绘加载流程 |
| `B92-NB脚本命令参考.md` §2.2 | `g_dialog_style` 对话框样式表 |
| `B93-图层渲染与菜单图层规范.md` | 对话框/菜单复合缓冲、`render_set_target` 目标分流、`menu_layer` |
| `B15-图层渲染与换装机制.md` | 图层 API、决策表、操作码 |

---

## 7. 对话框变体（引擎实现）

### 7.1 设计目的

基本渲染策略（背景 → 覆盖）支持不同对话框视觉效果，核心差异在于覆盖区域是**实心填充**还是**图案点阵**。

10 种预设样式（见 `B92-NB脚本命令参考.md` §2.2 `g_dialog_style` 表）：

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

### 7.4 `dialog_paint_box()` — 对话框框体绘制

所有样式使用 palette **248** 作为底色（`style & 1` 控制是否使用抖动，`style >> 1` 表示颜色索引；样式编号见 `B92-NB脚本命令参考.md` §2.2）。`draw_rect` 统一画白边：

```c
/* layer_dialog.c static；目标为 dialog_layer RAM 复合缓冲（stride=LAYER_DIALOG_W），
   先种底（保住 PAT75 洞孔下背景/立绘）再画框+白边；buf==NULL 直绘 VRAM（OOM 降级） */
static void dialog_paint_box(uint8_t *buf, int stride)
{
    if (!buf) {
        fill_dialog_bg(LAYER_DIALOG_X, LAYER_DIALOG_Y, LAYER_DIALOG_W, LAYER_DIALOG_H);
        draw_rect(LAYER_DIALOG_X, LAYER_DIALOG_Y, LAYER_DIALOG_W, LAYER_DIALOG_H,
                  LAYER_DIALOG_BORDER, PAL_WHITE);
        return;
    }
    /* 逐行：PAT75 孔洞透出已种底像素，其余写底色与边框 */
    for (y = 0; y < LAYER_DIALOG_H; y++)
        write_box_row(buf, stride, y);
}
```

**注意**：实际实现采用 `if (g_dialog_style & 1)` 的简洁形式，支持所有 10 种样式（5 色 × 2 密度）；框体绘制到复合缓冲（非 VRAM，`render_set_target` 分流）。R19 起由 `layer_dialog_show()`/`layer_dialog_render_page()` 内部调用，每页重画（清上一页文字）。

### 7.5 `dialog_show()` — RAM 复合 + blit 发布

旧文字区清除改在 RAM 复合缓冲内完成（`dialog_paint_box` 重画框体，不留文字残留同时保持半透明视觉效果）：

```c
int dialog_show(const char *charname, const char *text)
{
    int mw = LAYER_DIALOG_W - LAYER_DIALOG_INDENT - LAYER_DIALOG_RIGHT_INDENT;

    if (dialog_state.text_offset < 0) {
        dialog_state.charname = charname;
        /* strncpy → 截断中文 UTF-8 尾字节修复 → text_offset = 0 */
    }

    layer_dialog_show();                       /* 首次：建立 dialog_layer/dialog_occluder */

    int next = layer_dialog_render_page(dialog_state.charname,
                                        dialog_state.text,
                                        dialog_state.text_offset);   /* RAM 合成整页 */
    dialog_layer_store_render(dialog_state.charname,
                              dialog_state.text,
                              dialog_state.text_offset);             /* 记录投影（换图重绘用） */
    dialog_layer_blit();                       /* 整框发布 */

    if (next >= 0)                             /* 分页：未显示完 */
        dialog_state.text_offset = next;
    else
        dialog_state.text_offset = -1;
    return next;
}
```

**关键**：文字进入 `dialog_layer` RAM 缓冲（`text_set_target` 分流），整框 `dialog_layer_blit` 一次性发布；`draw_text` 的 `max_y = DIALOG_Y + DIALOG_TEXT_Y + 60` 限制每页 3 行，超出的文字由 `layer_dialog_render_page` 返回字节偏移供分页续印。角色名头部以粗体（`bold=1`）绘制于对话框顶部，不参与翻页。`dlg_update_palette()` 在 `dlgstyle` 切换时动态改色（重绘框体回缓冲）。

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

### 9.2 重叠处理（分层顺序）

```
次序          写入内容                  覆盖关系
───────────────────────────────────────────────
(1) bg         背景全屏 640×400          地基
(2) char       立绘 200×400（全高）      在背景之上
(3) dialog     对话框 480×115           在立绘之上——RAM 合成后整框发布
(4) text       文字行                    合入 dialog 复合缓冲
(5) menu       menu_layer 全屏 opaque    在对话框之上（独立复合缓冲）
```

结果：对话框白字和边框始终在最前。精灵延伸入对话框区域的像素被对话框合成覆盖（R20 立绘全高绘制，不复建"底部一致"前提）。

### 9.3 精灵恢复（基于 bg_snapshot / occluder）

PC-98 的单层 VRAM 中，修改后的精灵像素可通过 `bg_snapshot` 恢复；覆盖对话框区的改动由 occluder 重建补回（R20）：

| 操作 | 恢复方法 |
|------|----------|
| 移动精灵 | `layer_sprite_replace(nx,ny)` → `layer_bg_restore_rect` union + blit 新位 + sync_dialog_base |
| 隐藏精灵 | `layer_sprite_hide` → `layer_bg_restore_rect` 旧位（clip=1）+ sync_dialog_base |
| 切换精灵（表情） | `layer_sprite_face` → 裁剪至 `y<280` 恢复 + blit，**不碰对话框** |
| 切换精灵（换装） | `layer_sprite_replace` → 全幅恢复 + blit + recompose（缓冲内重画） |

### 9.4 精灵尺寸标准

- **标准尺寸**：200×400（接触屏幕底部）
- 精灵必须 ≤ 640×400（越界部分被 `vram_blit_sprite` 裁剪）
- R20 起精灵**全高绘制**（撤销旧 Option X 的 y<280 裁剪）；跨表情底部一致性仅保留为美术侧约定，不再作为引擎剪裁前提

### 9.5 性能

标准立绘 200×400 blit 性能：

| 操作 | 像素 | 透明比例 | 有效写入 |
|------|------|----------|----------|
| 全幅 blit | 80,000 | ~50% | ~40,000 |
| 裁剪 blit（换表情） | 56,000 (200×280) | ~50% | ~28,000 |

### 9.6 调色板共享

精灵不设自己的调色板（共享背景调色板），约束见 `B11-MAG图片加载与显示规范.md` §5。

---

## 10. 菜单渲染策略

### 10.1 菜单即覆盖层（R23：menu_layer RAM 复合缓冲）

菜单在渲染层面是"位于对话框之上的独立覆盖层"——R23 起为**全屏菜单复合缓冲**（`menu_layer_open`），opaque 模式内嵌整个屏幕快照极简底，选中切换在缓冲内增量合成后 `blit_rect` 发布：

```
次序          写入内容                      覆盖关系
────────────────────────────────────────────────
(1) bg         背景全屏 640×400              地基
(2) char       立绘 200×400                 在背景之上
(3) dialog     对话框 480×115（复合缓冲）    在立绘之上
(4) menu_layer 全屏复合（opaque 含底）       在对话框之上，整屏 blit 发布
```

背景样式与对话框一致：`fill_rect(248) + fill_rect_pattern(PAT40, 248) + draw_rect(thick=2, 7)`（绘制进菜单缓冲）。

### 10.2 菜单渲染架构（复合缓冲 + 增量发布）

`menu_open` 全量绘制一次进缓冲区 → `menu_blit` 整屏发布。随后每次键盘输入方向键（`KBD_UP`/`KBD_DOWN`）触发 `begin_draw → 增量改色 → commit → blit_rect`：

1. **选中移动到新 item**（`menu_highlight` / `menu_unhighlight` 成对，缓冲内改色）
2. **文字区无条件重绘**（`menu_draw_item` 每帧调用，即使选中无变化）

> 会话期间的中间态只存在于 RAM 缓冲，VRAM 上永远只有已发布结果——闪烁窗口被整体消除（§10.3 的根源分析仍适用，但"全部重绘开销聚集"一项已不再可见）。

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
| 4.0 | 2026-09-11 | **R19-R23 图层化重述**：对话框改为 RAM 复合缓冲合成 + 整框 blit 发布（`dialog_layer`/`dialog_occluder`、`layer_dialog_render_page`）；背景收口 `layer_bg_change`（源图直拷双快照、跨图存活）；R20 撤销立绘裁剪（全高绘制+伪透明活动底）；`render_set_target`/`text_set_target` 目标分流；菜单章节改 `menu_layer` 复合缓冲（R23）；§4.2 刷新表换复合缓冲版本；§5.3 调试输出按 `layer_debug.c` 实况重写；删除失效 C0x 文档引用 |
