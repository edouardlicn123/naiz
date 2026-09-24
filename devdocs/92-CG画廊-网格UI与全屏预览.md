# 92-CG画廊-网格UI全屏预览与占位框

> CG 画廊功能阶段 5/6（原分两阶段，用户决策合并为单一阶段）。
> 本阶段目标：实现完整的 CG 画廊网格浏览 UI + 全屏预览 + 锁定占位框 + `CG_COUNT` 管线补全。
> 是画廊功能的最后一个实现阶段；后续阶段 7 仅文档收口（B92/B18/B90 更新 + bump）。

## §一 阶段定位与目标

阶段 1–4 已完成：

| 阶段 | 状态 | 要点 |
|------|------|------|
| 1 type=CG 管线 | ✅ 已验证 | `export_asset_table.py` 生成 `cg_map[]`，含 cg01/c02（id 19/20） |
| 2 解锁 API | ✅ 已验证 | `sys_save_unlock_cg`/`sys_save_is_cg_unlocked`（save.h/save_sys.c） |
| 3 cmd_cg 展示 | ✅ 已验证 | `nb_cg.c`，演示载体（nbook001.nb 插 `cg(cg01)`）已就绪 |
| 4 入口骨架 | ✅ 已验证 | 主菜单 gallery → `cgview.nb` → `cmd_cgvmenu` 骨架 → ESC 回 mainmenu |

阶段 5（本 devdoc）目标：

1. **`CG_COUNT` 管线补全**：`export_asset_table.py` 生成 `#define CG_COUNT N` 常量。
2. **网格浏览 UI**：`cmd_cgvmenu` 填充完整的网格渲染 + 键盘/鼠标导航 + 翻页。
3. **锁定占位框**：解锁格显示 CG 编号标签；锁定格显示深色占位框 + `[LOCKED]` 文本。
4. **全屏预览**：选中已解锁 CG → 全屏展示（`layer_bg_change` + `image_load`），任意键回网格。
5. **回程保序**：`menu_save/restore_item_palette` 保证画廊进出调色板不泄露。

## §二 网格布局设计（全部坐标经 pixel 级对齐）

**屏幕**：640×400（LAYER_SCREEN_W / LAYER_SCREEN_H）

**布局区域**（自上而下）：

| 区域 | y 范围 | 高度 | 说明 |
|------|--------|------|------|
| 标题 | 0–28 | 28 | `draw_title_large("CG GALLERY", 20, 12, 3, PAL_WHITE)` |
| 网格 | 32–342 | 310 | 4 列 × 3 行，每格 144×100 |
| Back | 356–386 | 30 | `draw_rounded_emboss` 返回按钮（save_load 同款） |
| 翻页 | 366–386 | 20 | `<` / `>` 箭头 + 页码文字，与 Back 按钮同行不重叠 |

**网格详细坐标**（4×3 = 12 格/页）：

```
列  x 坐标：20, 168, 316, 464  （间距 4px）
行  y 坐标：32, 136, 240  （间距 4px）
每格尺寸：144 × 100（宽 × 高）
```

边界验证：
- 最右格右边缘 = 464 + 144 = 608 < 640 ✅（余 32px）
- 最下行底边 = 240 + 100 = 340 < 342 ✅（与 Back 间距 16px）
- Back 按钮上沿 356，下沿 386，与翻页箭头底边 386 齐平

**每格内构**（锁定 vs 解锁）：

```
解锁格（sys_save_is_cg_unlocked 为真）：
┌──────────────────────────┐
│  fill_rect 整格 PAL_BLUE │  ← 背景填充
│  "CG 01"                 │  ← 编号文字（bold, PAL_WHITE）
│  draw_rect 白边框         │  ← 边框
└──────────────────────────┘

锁定格（sys_save_is_cg_unlocked 为假）：
┌──────────────────────────┐
│  fill_rect 整格 0（黑色） │  ← 全黑背景
│  "[LOCKED]"              │  ← 居中文本（dim, PAL_WHITE）
│  draw_rect 暗边框         │  ← 暗灰边框
└──────────────────────────┘
```

## §三 关键决策表

| # | 决策点 | 选择 | 依据 |
|---|--------|------|------|
| E1 | CG_COUNT 获取方式 | `export_asset_table.py` 生成时追加 `#define CG_COUNT N` | 用户指定；与 anim_map / char_map 的演进方向一致；编译期常量无运行时除法 |
| E2 | 网格尺寸 | 4×3 = 12 格/页 | 640×400 屏幕利用率最优（约 88%）；galgame 画廊常用 4×3 布局；最大支持 99 CG（CG_TOTAL=99）→ 9 页 |
| E3 | 翻页控制 | `hal_kbd_is_down(KC_LEFT/RIGHT)` + 鼠标 `<`/`>` 区域 | 镜像 save_load_menu 的翻页模式（nb_saveload.c:214-224/301-313） |
| E4 | 锁定占位框 | 全黑底 + 暗灰 `draw_rect` 边框 + 居中 `[LOCKED]` 文本 | 无真缩略图资源；一期用纯文字/颜色区分，二期扩展为真缩略图 |
| E5 | 焦点导航 | UP/DOWN/LEFT/RIGHT 维护 `sel`（0–11 页内偏移）；DOWN 超底行→焦点跳 Back；Back 按 UP 回底行 | 完全对齐 save_load_menu 的 `slot_idx`+`focus_on_back` 模式（nb_saveload.c:188-250） |
| E6 | 全屏预览触发 | `sel` 聚焦 + ENTER/SPACE → `image_load(cg_map[sel].id)` → `layer_bg_change(img)` → `mag_release(img)` | `layer_bg_change` 内含完整渲染七步（blit + palette + snapshot），对齐 devdoc 90 D2 结论；`image_load` 引用计数+1，`mag_release` 释放后快照仍在 VRAM |
| E7 | 预览退出回程 | 按任意键/点击 → 黑屏 → `layer_bg_change(yellow_grid)` → 重绘全网格 + `menu_restore_item_palette()` | 避免 CG 调色板残留污染菜单；`yellow_grid` 与 `cgview.nb` 的 `bg(yellow_grid)` 一致 |
| E8 | 调色板生命周期 | 网格绘制前 `menu_save_item_palette()`；预览入口 `layer_bg_change` 覆写 CG 调色板；预览退出 `menu_restore_item_palette()` 后 `layer_bg_change(yellow_grid)` 恢复 bg 调色板 | 对齐 settings_menu.c 的 vram 快照模式（但此处无 vram 快照，靠重绘保证一致性） |
| E9 | 页面重绘策略 | 翻页 = 全量重绘（`fill_rect(0,0,640,400,0)` + 重画标题/网格/Back/翻页） | 12 格 × fill_rect + draw_text <1ms，全量重绘零闪烁（vblank_wait 保证）；无 vram_read 快照，简化实现 |
| E10 | 焦点变更增量绘制 | 仅重绘旧/新格边框 + 文字 | 镜像 save_load_menu 的增量模式（nb_saveload.c:341-342 条件触发 `save_load_draw(..., 0)`），避免全量重绘闪烁 |

## §四 逐文件改动

### A. `tools/naiz_build/export_asset_table.py` — 追加 `#define CG_COUNT`

在 cg_map[] 块之后（第 139 行 `lines.append('')` 之后）、`lines.extend(header_footer('NB_ASSET_TABLE_H'))`（第 142 行）之前插入：

```python
        # -- CG_COUNT constant --
        lines.append('/* Number of registered CG assets */')
        lines.append('#define CG_COUNT %d' % len(cg_rows))
        lines.append('')
```

当 `cg_rows` 为空（无 CG）时输出 `#define CG_COUNT 0`，画廊显示空网格 + 提示。

**验证**：`export_asset_table` 现有 5 元组返回值和 `__main__` 解包无需改动（CG_COUNT 宏由 `len(cg_rows)` 在写文件时已知，不进入返回值）。

### B. `core/engine/nb_mainmenu.c` — `cmd_cgvmenu` 全面重写

**状态（local，非 static）**：`sel`(页内焦点 0–11)、`page`(页号)、`focus_on_back`、`running`、`view`(0=grid,1=fullscreen)。
预览退出后需恢复到进入前焦点/页面 → 用命令级变量，预览子状态 `view==1` 时保持 `sel/page/focus_on_back` 不变，退出预览切回 grid 时沿用（`gallery_exit_preview` 以当前值重绘）。

**6 个 static 辅助函数**：

```c
static void gallery_cell_xy(int i, int *px, int *py)
   /* 格内偏移 i(0..11) -> 屏幕坐标，供 grid/cells_range/mouse hit-test 共用 */
static void gallery_draw_cell(int abs_idx, int x, int y, int is_sel)
   /* 绘制单个网格单元。abs_idx 为 CG_COUNT 范围内绝对索引；解锁→蓝底+编号，锁定→黑底+[LOCKED]。 */
static void gallery_draw_grid(int page, int sel, int focus_on_back)
   /* 全量重绘：黑屏 + 标题 + 12 格（越界跳过）+ Back 按钮 + 翻页箭头/页码。 */
static void gallery_draw_cells_range(int page, int from_sel, int to_sel, int focus_on_back)
   /* 增量重绘：以 from_sel/to_sel 直接驱动，仅重绘旧(去高亮)与新(高亮)两个格子位置；Back 焦点另处理。 */
static int  gallery_preview(int abs_idx)
   /* 全屏预览单张 CG：锁定/加载失败返回 0；成功 layer_bg_change + mag_release + force_draw + 返回 1。 */
static void gallery_exit_preview(int page, int sel, int focus_on_back)
   /* 退出预览：image_load(yellow_grid) 恢复背景（失败黑屏兜底）→ gallery_draw_grid → force_draw。 */
```

**`gallery_draw_cell` 实现**（每格 144×100）：

```c
static void gallery_draw_cell(int abs_idx, int x, int y, int is_sel)
{
    char label[16];
    int unlocked = sys_save_is_cg_unlocked(abs_idx + 1);   /* 1-based cg_id 契约 */

    if (unlocked) {
        fill_rect(x, y, 144, 100, PAL_BLUE);
        snprintf(label, sizeof(label), "CG %02d", abs_idx + 1);
        draw_text(label, 0, x + 12, y + 10, x + 132, y + 26, 1, PAL_WHITE);
        draw_rect(x, y, 144, 100, 1, is_sel ? PAL_WHITE : 7);
    } else {
        fill_rect(x, y, 144, 100, 0);
        draw_text("[LOCKED]", 0, x + 30, y + 42, x + 114, y + 58, 0, is_sel ? 15 : 7);
        draw_rect(x, y, 144, 100, 1, is_sel ? 15 : 12);
    }
}
```

格子坐标换算辅助（供 grid/focus/cell/mouse hit-test 共用）：

```c
/* 格内偏移 -> 屏幕坐标 */
static void gallery_cell_xy(int i, int *px, int *py)
{
    *px = 20 + (i % 4) * 148;
    *py = 32 + (i / 4) * 104;
}
```

**`gallery_draw_grid`（全量重绘）**：

```c
static void gallery_draw_grid(int page, int sel, int focus_on_back)
{
    int total_pages = (CG_COUNT + 11) / 12;
    int page_start = page * 12;
    int i;
    char buf[32];

    vblank_wait();
    fill_rect(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
    draw_title_large("CG GALLERY", 20, 12, 3, PAL_WHITE);

    for (i = 0; i < 12; i++) {
        int abs_idx = page_start + i;
        if (abs_idx >= CG_COUNT) break;
        int x, y;
        gallery_cell_xy(i, &x, &y);
        gallery_draw_cell(abs_idx, x, y, (i == sel) && !focus_on_back);
    }

    draw_rounded_emboss(66, 356, 80, 30, 4, BTN_FILL_IDX, BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX);
    draw_text("Back", 0, 76, 363, 136, 379, 1, focus_on_back ? MENU_PAL_YELLOW : PAL_WHITE);

    if (page > 0)        draw_text("<", 0, 56, 370, 72, 386, 0, PAL_WHITE);
    if (page < total_pages - 1) draw_text(">", 0, 576, 370, 592, 386, 0, PAL_WHITE);
    snprintf(buf, sizeof(buf), "%d/%d", page + 1, total_pages);
    draw_text(buf, 0, 308, 370, 332, 386, 0, PAL_WHITE);
}
```

**`gallery_draw_cells_range`（增量重绘，焦点移动时才调用）**：

```c
static void gallery_draw_cells_range(int page, int from_sel, int to_sel, int focus_on_back)
{
    int x, y, abs_idx;

    if (!focus_on_back) {
        /* Old cell loses focus */
        gallery_cell_xy(from_sel, &x, &y);
        abs_idx = page * GAL_CELLS + from_sel;
        if (abs_idx < CG_COUNT) gallery_draw_cell(abs_idx, x, y, 0);
        /* New cell gains focus */
        gallery_cell_xy(to_sel, &x, &y);
        abs_idx = page * GAL_CELLS + to_sel;
        if (abs_idx < CG_COUNT) gallery_draw_cell(abs_idx, x, y, 1);
    } else {
        /* Focus moved onto Back: de-emphasise old cell, highlight Back. */
        gallery_cell_xy(from_sel, &x, &y);
        abs_idx = page * GAL_CELLS + from_sel;
        if (abs_idx < CG_COUNT) gallery_draw_cell(abs_idx, x, y, 0);
        draw_text("Back", 0, 76, 363, 136, 379, 1, MENU_PAL_YELLOW);
    }
}
```

（实现即以上伪码——以 `from_sel`/`to_sel` 直接驱动，无任何占位数组；与最终代码逐行一致。）

**`cmd_cgvmenu` 主体**：

```c
void cmd_cgvmenu(int argc, const char **argv, const char *cmd_name)
{
    int running = 1, total_pages, page = 0, sel = 0, focus_on_back = 0, view = 0;
    (void)argc; (void)argv; (void)cmd_name;

    if (CG_COUNT == 0) {
        NB_DEBUG("cgvmenu: CG_COUNT=0, empty gallery\r\n");
        hal_kbd_drain_advance();
        draw_text("No CGs available.", 0, 200, 190, 440, 210, 1, PAL_WHITE);
        hal_mouse_draw_cursor_force();
        /* 等任一键/点击退出 */
        for (;;) {
            hal_kbd_update(); hal_mouse_update();
            if (hal_kbd_is_down(KC_ESC) || hal_kbd_is_down(KC_SPACE) ||
                hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_XFER) ||
                hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) break;
            hal_mouse_draw_cursor();
        }
        hal_mouse_flush();
        nb_load("mainmenu.nb");
        return;
    }

    total_pages = (CG_COUNT + 11) / 12;

    hal_kbd_drain_advance();
    hal_mouse_erase_cursor();
    menu_save_item_palette();
    gallery_draw_grid(page, sel, focus_on_back);
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    hal_mouse_draw_cursor_force();

    while (running) {
        int prev_sel = sel, prev_fb = focus_on_back;
        int abs_sel = page * 12 + sel;

        hal_kbd_update();

        if (view == 0) {   /* grid */
            if (focus_on_back) {
                if (hal_kbd_is_down(KC_UP)) {
                    focus_on_back = 0;
                    sel = 11;                       /* 回到底行右端 */
                    if (page * 12 + sel >= CG_COUNT) sel = CG_COUNT - page * 12 - 1;
                } else if (hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_SPACE) ||
                           hal_kbd_is_down(KC_XFER)) {
                    running = 0;
                    continue;
                }
            } else {
                if (hal_kbd_is_down(KC_UP) && sel / 4 > 0) { sel -= 4; }
                else if (hal_kbd_is_down(KC_DOWN)) {
                    if (sel / 4 >= 2) { focus_on_back = 1; }
                    else { sel += 4; if (page * 12 + sel >= CG_COUNT && sel / 4 == 2)
                                      sel = CG_COUNT - page * 12 - 1; }
                }
                else if (hal_kbd_is_down(KC_LEFT) && sel % 4 > 0) { sel--; }
                else if (hal_kbd_is_down(KC_RIGHT) && sel % 4 < 3) { sel++; }
                else if (hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_SPACE) ||
                         hal_kbd_is_down(KC_XFER)) {
                    if (abs_sel < CG_COUNT) {
                        view = gallery_preview(abs_sel) ? 1 : 0;
                        continue;
                    }
                }
                else if (hal_kbd_is_down(KC_LEFT) && page > 0) {   /* 需歧义消解，见下 */
                    page--; sel = 0;
                    gallery_draw_grid(page, sel, focus_on_back);
                    hal_mouse_draw_cursor_force();
                    continue;
                }
                else if (hal_kbd_is_down(KC_RIGHT) && page < total_pages - 1) {
                    page++; sel = 0;
                    gallery_draw_grid(page, sel, focus_on_back);
                    hal_mouse_draw_cursor_force();
                    continue;
                }
            }
            /* ESC 在 grid 态：回主菜单 */
            if (hal_kbd_is_down(KC_ESC)) { running = 0; continue; }

            hal_mouse_update();
            /* 鼠标：Back / 翻页 / 格子 hit-test */
            {
                int mx = hal_mouse_get_x(), my = hal_mouse_get_y();
                if (hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
                    /* Back 按钮 */
                    if (mx >= 66 && mx < 146 && my >= 356 && my < 386) { running = 0; continue; }
                    /* 翻页 '<' */
                    else if (mx >= 56 && mx < 72 && my >= 370 && my < 386 && page > 0) {
                        page--; sel = 0; gallery_draw_grid(page, sel, focus_on_back);
                        hal_mouse_draw_cursor_force(); continue;
                    }
                    /* 翻页 '>' */
                    else if (mx >= 576 && mx < 592 && my >= 370 && my < 386 && page < total_pages - 1) {
                        page++; sel = 0; gallery_draw_grid(page, sel, focus_on_back);
                        hal_mouse_draw_cursor_force(); continue;
                    }
                    /* 格子 */
                    {
                        int i;
                        for (i = 0; i < 12; i++) {
                            int gx, gy;
                            gallery_cell_xy(i, &gx, &gy);
                            if (page * 12 + i >= CG_COUNT) break;
                            if (mx >= gx && mx < gx + 144 && my >= gy && my < gy + 100) {
                                sel = i; focus_on_back = 0;
                                if (gallery_preview(page * 12 + i)) { view = 1; continue; }
                            }
                        }
                    }
                }
            }
        } else {           /* view == 1 : fullscreen preview */
            hal_mouse_update();
            if (hal_kbd_is_down(KC_ESC) || hal_kbd_is_down(KC_SPACE) ||
                hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_XFER) ||
                hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
                /* 退出预览：恢复背景 + 重绘网格（gallery_exit_preview 内完成） */
                gallery_exit_preview(page, sel, focus_on_back);
                view = 0;
                continue;
            }
        }

        /* 增量重绘（仅 grid 态、焦点变化时） */
        if (view == 0 && (sel != prev_sel || focus_on_back != prev_fb))
            gallery_draw_cells_range(page, prev_sel, sel, focus_on_back);

        hal_mouse_draw_cursor();
    }

    menu_restore_item_palette();
    hal_mouse_flush();
    nb_load("mainmenu.nb");
}
```

**歧义消解（重要）**：LEFT/RIGHT 同时是"页内移动"（`sel % 4 > 0` / `< 3`）与"翻页"（`page` 增减）。当焦点在页首列且 `page>0` 时按 LEFT 才翻页；在页末列且 `page<total_pages-1` 时按 RIGHT 才翻页。实现用 if-else 链保证：**先试页内移动，命中则不再触发翻页**（else-if）。范围外按键静默忽略。此与 save_load_menu 的 `LEFT`(page--) 无条件翻页略异——因画廊"页内 LEFT/RIGHT"也需要移动焦点，故需条件化。已在上方伪码体现（`sel % 4 > 0 → sel--` else-if `page > 0 → 翻页`）。

**`nb_asset_id` 返回值**：查 bg 资产 key→id。需确认 `nb_asset_id` 在 nb_mainmenu.c 可用（nb_commands.c 定义，nb_commands.h 声明）。若用 `image_load(-1)` 会越界——必须先用返回值判断。见 §五 边界表。

**调色板顺序**：`menu_save_item_palette()` 在入口调用后，`gallery_draw_grid`/`draw_title_large` 用 PAL_WHITE(7)/PAL_BLUE(1) 均为 palette 固定色，不依赖恢复。`menu_restore_item_palette()` 在最终返回前调用，镜像 save_load_menu 的 begin/end 对称（nb_saveload.c:143/346）。

### C. `nb_asset_table.h`（自动生成，验证产物）

运行 `export_asset_table` 后，第 61–65 行 cg_map[] 后应出现：

```c
/* Number of registered CG assets */
#define CG_COUNT 2
```

## §五 边界与失败路径

| 路径 | 行为 |
|------|------|
| `CG_COUNT == 0`（无 CG 资产） | `cmd_cgvmenu` 直接绘制 `"No CGs available."` + 等按键 → 回 mainmenu，不进网格 |
| `image_load` 返回 NULL（全屏预览） | `NB_DEBUG` 日志 + 不进入预览（`view` 保持 0，留在网格），画面不崩、焦点不丢 |
| `image_load` 返回 NULL（退出预览时载入 yellow_grid） | `fill_rect` 黑屏兜底，再重绘网格；网格文字不依赖背景色 |
| `nb_asset_id("yellow_grid")` 返回 -1 | `image_load((unsigned short)-1)` 会越界（image.c:151 `id >= g_image_count` 拦截）→ 返回 NULL → 走黑屏兜底；日志提示。demo-a2 已含 yellow_grid，不触发 |
| 焦点在空格区（`CG_COUNT < 12` 页尾） | `gallery_draw_cell` 越界跳过；`gallery_draw_grid` break；DOWN 到越界格被 `sel = CG_COUNT-page*12-1` 夹紧；hit-test 对 `abs_idx >= CG_COUNT` 的格不进入 |
| 翻页边界 | `page>0`/`page<total_pages-1` 条件守卫，不可越 |
| 全屏预览锁定时（未解锁格按 ENTER） | `sys_save_is_cg_unlocked(abs_sel+1)` 为假 → 不触发 preview；等同忽略 |
| 预览后回网格焦点 | 保持进入前 `sel/page/focus_on_back`；`gallery_draw_grid` 以当前值重绘 |

## §六 §十七 Bug 防复发检查表

### C 规则

| 规则 | 本阶段检查 |
|------|------------|
| C1 malloc/calloc/realloc | 无动态分配 |
| C2 fopen | 无文件操作 |
| C3 fread/fwrite | 同上 |
| C4 strncpy | `snprintf` 替代；无 strncpy |
| C5 snprintf | 页码/编号用 `snprintf`，已手动确保 NUL（sizeof 足够） |
| C6 数组越界 | `cg_map[abs_sel]`：`abs_sel < CG_COUNT` 已守卫（ENTER/hit-test 均检查）；`gallery_draw_grid`/`gallery_draw_cell` 均先判 `abs_idx < CG_COUNT` |
| C7 offsetof | 无 |
| C8 有符号溢出 | `page*12+sel`：page max (99-1)/12=8，8*12+11=107 < INT_MAX；`CG_COUNT` 编译期已知 |
| C9 memcpy | 无 |
| C10 switch default | 无 switch（if-else 链，保持 nb_mainmenu.c 风格） |
| C11 assert | 无 |
| C12 void 返回值 | 无 |
| C13 static 死函数 | `gallery_cell_xy/draw_cell/draw_grid/draw_cells_range/preview/exit_preview` 六者均被 cmd_cgvmenu 调用 |
| C14 OOM/fail 日志 | `image_load` NULL 路径均有 `NB_DEBUG` |
| C15 fclose | 无 fopen |
| C16 offsetof | 无 |
| C17 光标残影 | 进入预览前 `hal_mouse_erase_cursor()`；退出预览 `erase`→`force_draw`；全量重绘用 `force_draw`（§十四：全量重绘后 `force_draw`）；增量用 `draw_cursor` |
| C18 快路径副作用 | 无 cache/shortcut |
| C21 strcpy/strcat | 无 |
| C22 INT_MIN 取负 | 无 `-v` |
| C23 双重 free | `mag_release` 每路仅一次；`img` 用后即弃 |
| C24 memcpy 尺寸 | 无 memcpy |
| C25 use-after-free | `layer_bg_change` 完成后才 `mag_release(img)`；其后 `img` 不再解引用 |

### 菜单 UI 规约（§十四）

- **入口全量绘制一次**：`gallery_draw_grid`（含 vblank_wait）+ `hal_mouse_set_pos` + `force_draw`。
- **循环内增量绘制**：仅焦点移动时 `gallery_draw_cells_range`（2 格）。
- **翻页/预览是"场景切换"**：全量重绘 + `force_draw`，符合 §十四 反例清单（翻页属全量重绘场景）。

## §七 验证方案

1. **`export_asset_table` 正确性**：运行后 grep `nb_asset_table.h` 检查 `#define CG_COUNT 2` 且 cg_map[] 保持 cg01/cg02。
2. **`make -C core`**：0 errors / 0 warnings。
3. **`pytest`**：322 全绿。
4. **`nb_validator`**：`projects/demo-a2` 0 errors。
5. **`./start.sh fullaudit`**：6 步全绿。
6. **手动验收（NP2kai + 串口）**（执行入口已转 **devdoc 94 §二**）：

> 本步骤需实机操作，超出编码/自动化验证范围；执行、核销与进展记录统一转至 `devdocs/94-CG画廊-未完成部分与实机验收.md`。

| 步骤 | 操作 | 预期 |
|------|------|------|
| a | 主菜单 → 先打一遍 nbook001（触发 `cg(cg01)` 解锁 cg_id=1）→ 回主菜单 → gallery | 网格 1 格亮蓝 `CG 01`，其余黑 + `[LOCKED]` |
| b | RIGHT | 焦点到 CG 02（灰 `[LOCKED]`，边框变亮） |
| c | LEFT | 回 CG 01（白边框） |
| d | DOWN ×3 → 跳 Back | 焦点到 Back，文字变黄 |
| e | UP | 回底行（CG 01） |
| f | ENTER（CG 01 已解锁） | 全屏 pink grid 图 |
| g | ESC / 任意键 | 回网格，焦点不变 |
| h | 对 CG 02 按 ENTER（未解锁） | 无响应（不预览） |
| i | 检查 SYSTEM.SAV cg_flags | cg_id=1 位置位（步骤 a 已解锁）；cg02 未解锁（未触发 `cg(cg02)`） |
| j | ESC（grid 态，两层回主菜单） | 回 mainmenu，主菜单正常无调色板残留 |
| k | 串口日志 | `[LOAD] nb_load 'cgview.nb'`、`[CGALLERY] preview cg_id=1` |
| l | 翻页（若 >12 条） | `<`/`>` 切换，页码 `1/N` |

7. **`python -m tools.naiz_build.bump_version`**：0.2.076 → 0.2.077。

## §八 devdoc 93（原缩略图阶段）取消说明

> 执行入口已转 **devdoc 94 §四**（二期真缩略图挂起项）。本段保留为历史方案说明。

原阶段 6（缩略图支持）已合并入本 devdoc §四.B 的 `gallery_draw_cell` 占位框实现。
二期如需真缩略图：在 `gallery_draw_cell` 的 `fill_rect + draw_text` 位置替换为缩略图 blit
（需新增缩略图资产 + `image_load` 路径），网格布局与导航逻辑无需改动。

## §九 NEXT（阶段 7 文档收口）

- 更新 `docs/B92-NB脚本命令参考.md`：补充 `cg(key)` 命令说明、`cgview.nb` 使用说明。
- 更新 `docs/B90-参考-函数索引.md`：补充 `cmd_cgvmenu` / `sys_save_unlock_cg` / `sys_save_is_cg_unlocked`（修正 B90 line 132–133 的"内部 static"过期描述——阶段 2 已实现为公开非 static）。
- 更新 `docs/B18-存档读档系统设计.md`：§2.4 表格行号区间 `290–333` 过期，且未列 `sys_save_unlock_cg`/`sys_save_is_cg_unlocked`（devdoc 89 §2.3 预告过；devdoc 93 §五 已补修）。
- 最终 bump 版本号。

> 注：devdoc 89 本身(§2.3 行 67–68)已正确披露 B90 的脱节点并预告阶段 7 修正，其 95–100 行为实现预览（无错误声称）。
