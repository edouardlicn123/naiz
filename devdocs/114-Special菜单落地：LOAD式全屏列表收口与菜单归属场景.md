# 114-Special 菜单落地：LOAD 式全屏列表收口与菜单归属场景

> 状态：**已落地**（0.2.140）
>
> 所属：NB 菜单系统（nb_mainmenu.c / nb_cggallery.c / nb_special.c / nb_internal.h / nb_commands.c）
> 上游：nb_saveload.c 的 LOAD 场景（两阶段渲染菜单范式，AGENTS.md §十四「菜单 UI 渲染」正反例来源）

## 1. 目标与背景

主菜单为 NB 脚本驱动（`projects/demo-a2/scene/mainmenu.nb`）：

```nb
mainmenu(400,200,2,0,continue,load,start,scenes,music,gallery,special,settings,exit)
```

`cmd_mainmenu`（nb_mainmenu.c:28）逐关键字路由。其中 `scenes` / `music` / `special` 一直是 **TODO 日志桩**；`gallery` 直切 `cgview.nb`。本次目标：

1. 新增 **special 菜单**：主菜单去掉 scenes/music/gallery 三键，仅留 `special` 入口；special 菜单提供 gallery / scenes / music 三个子项。
2. special 菜单的**布局、行为、显示方式必须参考 LOAD 场景**（`loadscen.nb` → `loadscene()` → `save_load_menu`，nb_saveload.c）——全屏固定版式 + 凹刻列表行 + 左下 Back + 底部翻页条 + `focus_on_back` 模型 + 两阶段增量渲染。
3. **保留分页**：列表采用 LOAD 同款每页 4 行的分页语义，为日后条目增多留空间。

用户确认的约束：

- special 需有 Back 按钮（返回主菜单）。
- scenes 复用现有 `loadscen.nb`（读档槽位），返回沿用 temp 快照机制。
- 主菜单按钮顺序 = `continue,load,start,special,settings,exit`（**exit 必须末位**，AGENTS 长期约定）。
- 本次范围仅 demo-a2（animatest 主菜单本就只有 start,exit，无 gallery/scenes/music）。

## 2. LOAD 场景范式解剖（照抄蓝本）

`save_load_menu` / `save_load_draw`（nb_saveload.c）是唯一被 AGENTS §十四 5 项反例亲点名的满意范式。逐项解剖：

### 2.1 固定版式（几何常量）

| 元素 | 几何 | 说明 |
|------|------|------|
| 大标题 | `draw_title_large(text, (640 - text_title_width)/2, 28, 4, PAL_WHITE)` | 顶部居中黑体大标题 |
| 行凹刻 | `draw_rounded_emboss(80, row_y[i], 480, 44, SAVE_SLOT_R, BTN_FILL_IDX, BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX)` | 每行 480×44 圆角凹刻，`slot_y[] = {90,146,202,258}` |
| 行焦点指示 | `fill_rect(86, y+2, 12, 40, BTN_FILL_IDX)` 再在焦点行画 `>` | 指示条始终填充；焦点行画 `>` + 黄字 |
| 行文字 | `draw_text(label, 0, 100, y+14, 570, y+36, 0/1, PAL_WHITE/MENU_PAL_YELLOW)` | 非焦点白字 / 焦点黄字 |
| 翻页条 | `menu_pagenav_draw(318, 330, PAL_WHITE, page, total_pages)` | 两箭头 + `%d/%d`；首/末页箭头自动隐藏 |
| Back | `menu_back_draw(352, focus, emboss, PAL_WHITE)` | 先 emboss=1 画背景，结尾 emboss=0 画文字；`menu_back_hit(352, mx, my)` |

### 2.2 生命周期与输入

```
menu_save_item_palette();          // 1. 换硬件调色板
hal_kbd_drain_advance();           //    防粘连
hal_mouse_erase_cursor();          // 2. 擦旧光标
menu_layer_open(0,0,640,400,0);    // 3. 全屏菜单层（备份底色快照）
full_draw();                       // 4. 全量首绘
hal_mouse_set_pos(320,200);
hal_mouse_draw_cursor_force();     // 5. 光标现形
for(;;) { kbd/mouse update; 增量重绘; }
menu_finish();                     // 6. menu_layer_close(1) + flush + 还原调色板
```

- 键盘：Up/Down 移焦点（Down 越末行 → 进 Back），Left/Right 翻页，Enter/Space/XFER 确认，Esc=Back。
- 鼠标：行点击即确认；Back / 箭头可点。
- 焦点变更走**文本级增量重绘**（凹刻/pagena/标题只管一次），commit + 全幅 blit。
- 翻页 = 全量重绘（行凹刻随之变化）+ `hal_mouse_draw_cursor_force()`（C17 规则）。

### 2.3 两阶段渲染与 §十四 合规

- 入口全量绘制一次（draw_rounded_emboss / draw_title_large 只画一次），循环内只增量改文字颜色/指示符。
- `menu_layer_begin_draw()` … `menu_layer_commit()` + `menu_layer_blit()` 提交。
- 反例列表（AGENTS §十四 4）全部避开：不调 `fill_rect(0,0,640,400,0)`、不在循环内重画 emboss/title。

## 3. 方案：nb_special.c（LOAD 式全屏列表）

新建 `core/engine/nb_special.c`，命令名 **`specialmenu`**（`specialmenu(gallery,scenes,music)`），行标签与主菜单一样经 `tr()` 渲染（sys_*.txt 已含 `gallery=画廊/scenes=章节/music=音乐/special=特别篇/Back=返回` 译文，无需新译）。

### 3.1 数据模型

- 行数 = argc；总页数 `total_pages = menu_pagecount(argc, SPECIAL_ROWS)`（`SPECIAL_ROWS=4`）。
- 当前页可见行 `rows_on_page = min(argc - page*SPECIAL_ROWS, 4)`。
- 焦点：`(page, sel, focus_on_back)`；行绝对下标 = `page*SPECIAL_ROWS + sel`。

### 3.2 绘制函数 `special_draw(argc, argv, page, sel, focus_on_back, total_pages, full)`

- `full=1`（入口/翻页）：标题 `tr("SPECIAL")` + 逐行凹刻 + 翻页条 + Back 背景。
- 每帧：逐可见行 fill_rect 指示条；焦点行 `>` + 黄字，非焦点白字；Back 文字。
- 全部在 `menu_layer_begin_draw()`…`commit()`+`blit()` 间。

### 3.3 输入与路由

键盘 / 鼠标完全对齐 2.2。选中行后退出循环，`menu_finish()` 后再按绝对下标路由：

| 关键字 | 动作 |
|--------|------|
| `gallery` | `nb_set_menu_return("special.nb")`；`scene_switch("cgview.nb", SCENE_SWITCH_MENU)` |
| `scenes` | `save_request(SAVE_OP_CAPTURE_TEMP, -1)`；`save_request(SAVE_OP_OPEN_LOAD, -1)`（Esc 走 RESTORE_TEMP 回 special 画面） |
| `music` | `hal_log` TODO 桩（停留本菜单） |
| Back / Esc | `scene_switch("mainmenu.nb", SCENE_SWITCH_MENU)` |
| 未知项 | `NB_DEBUG` 告警停留（消灭静默失败） |

### 3.4 菜单归属场景 `g_menu_return`

cgview 退出目前硬编码 `scene_switch("mainmenu.nb")`（nb_cggallery.c:258/357）。SPecial → gallery → Back 应回 **special** 而非主菜单。引入单一归属状态：

- `nb_mainmenu.c` 新增 `static char g_menu_return[64]` + 访问器 `nb_set_menu_return(const char*)` / `nb_get_menu_return()`（声明入 nb_internal.h，`str_copy` 收口，C32 合规）。
- `nb_cggallery.c` 两处退出改 `gallery_return_home()`：`nb_get_menu_return()` 非空用之，空回退 `mainmenu.nb`。
- 写点：specialmenu 的 gallery 分支写 `"special.nb"`；mainmenu 的 special 分支写 `""`（清除陈旧值，mainmenu 起源的 gallery 回主菜单）。**读点总是紧邻写点**，无陈旧污染面。

### 3.5 命令注册

- `nb_commands.h` 声明 `void cmd_specialmenu(int argc, const char **argv, const char *cmd_name);`
- `nb_commands.c` cmd_table 注册 `{"specialmenu", cmd_specialmenu, CMD_BLOCKING | CMD_NEEDS_INPUT | CMD_TOUCHES_DISPLAY}`（test_cmd_meta.py 三字段 guard）。
- `core/Makefile` 用 `$(wildcard engine/*.c)`，新文件自动入编。

### 3.6 场景脚本（demo-a2）

`mainmenu.nb` 第 4 行改为：

```nb
mainmenu(400,200,2,0,continue,load,start,special,settings,exit)
```

新建 `special.nb`：

```nb
sceneconf(){Special, menu}
bg(normal){yellow_grid}
specialmenu(gallery,scenes,music)
```

- `yellow_grid`(id13) 已在 nb_asset_table.h；`assets/common/bg/yellow_grid.png` 640×400 RGB，`bg(normal)` 直接解析。
- `sceneconf` 标题 "Special" 走既有 collection（dialogue_texts，game_<lang>.txt）。

## 4. i18n 联动（tools/naiz_conv/i18n_gen.py）

1. **menu_options 收集扩展**（现仅 `cmd == 'mainmenu'` 收 args[4:]）：`cmd in ('mainmenu', 'specialmenu')`，specialmenu 全量 args；保证按钮译词重生成督导不复用丢失。
2. `SYSTEM_UI_KEYS` 追加 `"SPECIAL"`（标题词，§十四 规则 3 强制登记，否则重生成标 `# ORPHANED` 译文失效）。

## 5. 改动清单

| 文件 | 改动 |
|------|------|
| `core/engine/nb_special.c` | **新建**：`cmd_specialmenu` + `special_draw` + 路由 |
| `core/engine/nb_commands.c/.h` | 注册 / 声明 `cmd_specialmenu` |
| `core/engine/nb_internal.h` | 声明 `nb_set/get_menu_return()` |
| `core/engine/nb_mainmenu.c` | `g_menu_return` + 访问器；`special` 分支→`scene_switch("special.nb", SCENE_SWITCH_MENU)`＋清归属 |
| `core/engine/nb_cggallery.c` | 两处退出改 `gallery_return_home()` |
| `projects/demo-a2/scene/mainmenu.nb` | 按钮序列改 `...,start,special,settings,exit` |
| `projects/demo-a2/scene/special.nb` | **新建**（黄色网格 bg + specialmenu） |
| `tools/naiz_conv/i18n_gen.py` | specialmenu 收集 + `SPECIAL` 标题键 |
| `tools/tests/test_i18n_menu_options.py` | **新建**：specialmenu 按钮词入 menu_options guard |
| `docs/B92-NB脚本命令参考.md` | 新增 `specialmenu` 命令条目 |
| `docs/B90-参考-函数索引.md` | 登记 `cmd_specialmenu` / `nb_set/get_menu_return` |
| `config.toml` ×2 | bump → 0.2.140 |

## 6. 验证

1. `make -C core` → 0 errors / 0 warnings；py_compile 全过。
2. `pytest tools/tests/` → 新增用例 + 全量回归（460 → 461+）。
3. `./start.sh fullaudit` → 全部 `[✓]`（含 C16/C17/C32/C34/C35 增量审计，special 焦点覆盖用 C17 快照语义核对）。
4. `./makegame.sh build demo-a2` → 数据构建含 special.nb 场景 / yellow_grid 资产 / i18n 重生成。
5. NP2kai 目检：主菜单 6 键（无 gallery/scenes/music）；special 里黄色网格 + LOAD 式列表（画廊/章节/音乐）+ Back；gallery 返回回 special；scenes 回 special；Esc/Back 回主菜单；每场景切换黑屏（引擎层保证）。