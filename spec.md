# Spec — Scene 菜单（场景鉴赏）

* **状态**：待批准

* **基线**：0.4.028（pytest 918 passed / 2 skipped）

* **目标项目**：`projects/demo-a2`

* **关联规则**：§十（规格收敛）、§十一（8.3）、§十四（输入循环 / i18n）、§十七（C/Python 防复发）

* **前置文档**：`devdocs/207-sceneconf场景清单标记-onlist-outlist.md`

## 1. 需求（用户原文）

> 架构参考画廊菜单。
>
> 1. 仅显示 sceneconf 为 normal 的场景，且必须为 onlist。
> 2. 如该场景带 cg，则使用第一张 cg 作为缩略图；如该场景不带 cg 但有动画，则从该动画中抽取第一帧作为缩略图；如果两者都没有，则使用该场景名称的第一个字母的大写字母作为图标。

## 2. 总体设计

| 项        | 决策                                                                                                                                                             | 理由                                                                                        |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| 数据来源     | **构建期扫描** `projects/<game>/scene/*.nb`，生成 `core/engine/nb_scene_menu.h`                                                                                        | 运行期无场景目录遍历能力；`scene_switch()` 只需文件名，表在编译期固化                                               |
| 运行期访问器   | **删除** `nb_is_scene_listed()` 与 `NbState.scene_listed`                                                                                                         | 无消费方即死导出，会触发 fullaudit `symbol_audit -s A,B --gate`（R30）。devdoc 207 按 §十 加 ERRATA 块（正文不改） |
| 缩略图      | 构建期生成，语义同 `cg_thumb.py`：统一 160×100 MAG                                                                                                                         | 引擎无缩放原语；`menu_layer_blit_sprite` 无源子矩形裁剪（只裁到层边界）                                          |
| 缩略图选择优先级 | 首个 `cg(){key}` → 首个 `playanima(){key}` → 字母图标（`thumb_id=0`）                                                                                                    | 与需求 2 一致；只看该场景脚本自身                                                                        |
| 网格       | 3 列 × 2 行 = 6/页；格 180×130；缩略图 160×100（x+10,y+4）；标题 16px 在 y+108                                                                                                | 640×400：548 宽居中（x=46），底部 304 < 翻页箭头 318                                                   |
| 复用件      | `menu_layer_*`、`menu_save_item_palette`、`menu_pagenav_draw`、`menu_back_draw`、`menu_finish`、`engine_frame_pump`、`input_drain_boundary`、`image_load/mag_release` | 与 `nb_cggallery.c` 同构，保持系统菜单一致                                                            |
| 选中态      | 选中格：黄色 2px 边框 + 黄色标题；非选中：白色 1px 边框                                                                                                                             | 画廊格子无选中反馈，但场景菜单是「进入播放」语义，必须可见焦点                                                           |
| 播放       | `scene_switch(entry.scene, SCENE_SWITCH_SCRIPT)`，先 `menu_finish()`                                                                                             | 章节播放属脚本语义（与 `scene()` 命令一致），不应带菜单状态                                                       |
| 返回       | `menu_finish()` 后 `scene_switch(nb_get_menu_return() 或 "mainmenu.nb", SCENE_SWITCH_MENU)`                                                                      | 与 `gallery_return_home()` 同款                                                              |

## 3. 构建期生成（`tools/naiz_build/scene_menu.py`，新增）

公开函数：

```python
THUMB_W, THUMB_H = 160, 100
THUMB_SUFFIX = '_t'
THUMB_TYPE = 'THUMB'
HEADER_PATH = Path('core/engine/nb_scene_menu.h')
STATE_FILE = '.scene_menu_state.json'

def build_scene_menu(proj_dir: Path, scene_dir: Path, asset_dirs=()) -> int
```

流程：

1. 遍历 `scene_dir/*.nb`（按文件名升序），逐文件找**第一条** `sceneconf(){...}`；段内字段拆分**必须**用 `naiz_lib.nb_line.next_field()`（§十四.9，转义逗号）。
2. 过滤：`type ∈ {'', 'normal'}` 且 `list == 'onlist'`（`onlist`/`outlist` 缺省 = outlist）。标题 = 字段 0。
3. 缩略图解析：

   * 首个 `cg(){<key>}`：ASSETS.DB `type='CG' AND name=<key>` → `filename` 基名；查 `type='THUMB' AND filename='images/<cgname>_t.MAG'` → `id`。缺失则 WARN 并继续下一优先级。

   * 否则首个 `playanima(...){<key>}`：ASSETS.DB `type='ANI' AND name=<key>` → `filename`（相对 `proj_dir`，如 `ani/X.ANI`）→ 读字节 → `parse_ani()` 取 `blobs[0]` → `decode_mag_full()`（返回 `pixels,w,h,palette,bpp,is_sprite`；None 则 WARN 跳过）→ 用 palette 构造 PIL `Image`（`pixels` 为 w\*h 索引）→ `resize_to_screen(..., THUMB_W, THUMB_H, cover=True)` → `convert_image(..., no_resize=True, reserved=PROTECTED_IDX_ALL)` 写 `proj_dir/images/<ani_name>_t.MAG` → upsert ASSETS.DB `(filename='images/<ani_name>_t.MAG', type='THUMB', name='<ani_name>_t')`；8.3 与短名互异校验同 `cg_thumb._check_name`。

   * 都没有：`thumb_id = 0`。
4. 生成 `core/engine/nb_scene_menu.h`（幂等，内容不变则不重写）：

```c
#ifndef NB_SCENE_MENU_H
#define NB_SCENE_MENU_H
#define SCENE_MENU_COUNT <n>
typedef struct { const char *scene; const char *title; unsigned short thumb_id; } SceneMenuEntry;
static const SceneMenuEntry scene_menu_entries[SCENE_MENU_COUNT > 0 ? SCENE_MENU_COUNT : 1] = {
    { "nbook005.nb", "Come with cat", 29 },
};
#endif
```

`scene` 用 `to_dos_name()` 后的 8.3 基名 + 原扩展名（本项目场景基名已 ≤8，仅做强校验）。

1. 接入 `build_game.py`：在 `build_cg_thumbs(...)` 之后、`export_asset_table.py` 之前调用（新增 THUMB 行需先进 ASSETS.DB，再由 export 导出 + pack 进 IMAGE.DAT）。

## 4. 引擎（`core/engine/nb_scene_menu.c`，新增）

* 常量（与 Python 同源，守卫测试对齐）：
  `SCM_COLS 3`、`SCM_ROWS 2`、`SCM_CELLS 6`、`SCM_ORIGIN_X 46`、`SCM_ORIGIN_Y 40`、`SCM_CELL_W 180`、`SCM_CELL_H 130`、`SCM_STEP_X 184`、`SCM_STEP_Y 134`、`SCM_THUMB_W 160`、`SCM_THUMB_H 100`、`SCM_GRID_BOTTOM 304`、`SCM_ARROWS_Y 318`、`SCM_COUNT_Y 330`、`SCM_BACK_Y 352`。

* 调色板：`MENU_PAL_WHITE` / `MENU_PAL_YELLOW`；图标底色用 255 槽（`gallery_palette_save/restore` 同法）。

* `scm_draw_cell(i)`：`thumb_id ? image_load + menu_layer_blit_sprite(trans, no transparency) : fill 255 + 大写首字符 draw_title_large(scale 4)`；标题 `tr(entry.title)` 居中于格内；边框按选中态。

* `scm_draw_grid(page, sel, focus_on_back)`：`menu_layer_begin_draw` → `erase_to_base` 三条带 → 标题 `tr("SCENE GALLERY")`（scale 3）→ 格子 → `menu_back_draw` + `menu_pagenav_draw` → commit + blit。

* 增量重绘 `scm_draw_cells_range(page, from, to, focus_on_back)`：只重画旧/新两格 + Back。

* 主循环：完全照 `nb_cggallery.c`（`engine_frame_pump` / `hal_kbd_update` / 方向键 / 鼠标命中 / `menu_back_hit` / `menu_page_hit`），无预览态：

  * Enter/Space/XFER/左键命中格 → 记录 `chosen`，`running = 0`。

  * Esc/Back → `running = 0`，`chosen = -1`。

  * 退出后：`menu_finish(); chosen >= 0 ? scene_switch(entries[chosen].scene, SCENE_SWITCH_SCRIPT) : scm_return_home();`

* 空态：`SCENE_MENU_COUNT == 0` 时画 `tr("No scenes available.")`，任一键/点击返回（照 `cmd_cgvmenu` 空态分支）。

* 注册：`nb_commands.h` 声明 `void cmd_scenesmenu(int, const char**, const char*);`；`nb_commands.c` cmd\_table 增加
  `{"scenesmenu", cmd_scenesmenu, CMD_BLOCKING | CMD_NEEDS_INPUT | CMD_TOUCHES_DISPLAY},`。

* `core/Makefile` 用 `wildcard engine/*.c`，无需改动。

## 5. 接线与脚本

| # | 文件                                     | 改动                                                                                                                      |
| - | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| 1 | `projects/demo-a2/scene/scenes.nb`（新增） | `sceneconf(){Scenes, menu}` + `bg(normal){yellow_grid}` + `scenesmenu()`（照 `music.nb`）                                  |
| 2 | `core/engine/nb_special.c:105-107`     | 删除错误接到的 `save_request(...)`，改为 `nb_set_menu_return("special.nb"); scene_switch("scenes.nb", SCENE_SWITCH_MENU);`        |
| 3 | `core/engine/nb_mainmenu.c:103-104`    | `hal_log("not implemented")` 改为 `nb_set_menu_return(""); scene_switch("scenes.nb", SCENE_SWITCH_MENU);`                 |
| 4 | `core/engine/nb.c` / `nb.h`            | 删除 `scene_listed` 字段、`nb_load` 重置、`nb_is_scene_listed()` 定义与声明；`nb_set_scene_conf` 的 `list` 参数保留（validator 仍校验语法，仅不再存储） |
| 5 | `devdocs/207-...md`                    | 头部状态行下追加 `> ## ⚠ ERRATA（0.4.029 追加）`：运行期访问器已被构建期扫描替代，指向 devdoc 208；正文一字不改                                               |
| 6 | `tools/naiz_conv/i18n_gen.py`          | `SYSTEM_UI_KEYS` 增加 `"SCENE GALLERY"`、`"No scenes available."`                                                          |
| 7 | `projects/demo-a2/i18n/sys_<lang>.txt` | 9 语言补两条译文（留空则运行时回退英文并视为未完成）                                                                                             |

## 6. 防呆守卫（新增 `tools/tests/test_scene_menu.py`）

1. `test_scan_filters_normal_onlist` — 临时项目：`{T1, normal, onlist}` 收、`{T2, normal, outlist}` 不收、`{T3, menu, onlist}` 不收、`{T4, , onlist}` 收（空 type 视为 normal）。
2. `test_title_escape_uses_next_field` — `sceneconf(){Ira\, Jr., normal, onlist}` 标题为 `Ira, Jr.`，且源码调用 `nb_line.next_field`。
3. `test_cg_thumb_id_from_assets_db` — demo-a2 生成的表中 `nbook005.nb` 的 `thumb_id == 29`（`cg01_t`）。
4. `test_anim_first_frame_thumb` — 合成 `AnimContainerDef` + `build_ani()`（blob = 一张真实小 MAG 字节）→ 生成 160×100 THUMB、ASSETS.DB 有行、表内 `thumb_id != 0`。
5. `test_letter_icon_fallback` — 无 CG/ANIM 的场景 `thumb_id == 0`。
6. `test_grid_constants_in_sync` — 从 `.py` 与 `nb_scene_menu.c` 读常量（W/H/COLS/ROWS 等）断言相等；并断言 `SCM_GRID_BOTTOM < SCM_ARROWS_Y`。
7. `test_command_registered` — `nb_commands.c` cmd\_table 含 `scenesmenu` 且带 `CMD_BLOCKING`；`nb_commands.h` 有声明。
8. `test_no_runtime_accessor` — `nb.c`/`nb.h` 不再出现 `nb_is_scene_listed`（防死导出回归）。
9. `test_i18n_keys_present` — 两条新 UI 文案出现在 `SYSTEM_UI_KEYS` 且 9 个 `sys_*.txt` 均有非空译文，且 `text_width` 不超对话框/标题限宽。

## 7. 验收步骤

1. `make -C core` → `core/*.err` 全空。
2. `pytest -q` 全绿（基线 918 + 新增）。
3. `./makegame.sh build demo-a2 && ./makegame.sh make demo-a2` 成功；`core/engine/nb_scene_menu.h` 生成且含 1 条 `nbook005.nb`。
4. `python -m tools.audit.audit -q` / `./start.sh fullaudit --no-make`：symbol\_audit A/B 节 gate 通过。
5. 实机（人工）：special → Scenes 显示 1 格（cg01 缩略图 + 标题）→ Enter 进入 `nbook005.nb` 从头播放；Esc 返回 special。
6. `python -m tools.naiz_build.bump_version`（→ 0.4.029）后重新 build + make。
7. `CHANGELOG.md` 新锚点 `c106` + 版本索引首行；`AGENTS.md` 头部四行；`docs/B90`/`docs/B92`；guildbook `sc11-sceneconf` cn/en 版本标签同步当前时间。

## 8. 风险与回退

* `menu_layer_blit_sprite` 要求缩略图 ≤ 格尺寸；生成端固定 160×100，守卫测试兜底。

* 动画首帧若是 sprite（带透明标记）则按不透明 blit（`PAL_NO_TRANSPARENCY`），与画廊一致；合成测试覆盖。

* 若 ANI 解码失败：WARN + 回退字母图标，构建不中断（不静默）。

* 不改存档格式、不改显示管线、不改启动方式。

## 9. 交付物

* 新增：`tools/naiz_build/scene_menu.py`、`core/engine/nb_scene_menu.c`、`projects/demo-a2/scene/scenes.nb`、`tools/tests/test_scene_menu.py`、`devdocs/208-scene菜单（场景鉴赏）.md`

* 生成（gitignored/build 产物性质）：`core/engine/nb_scene_menu.h`、`projects/demo-a2/images/*_t.MAG`（ANI 分支）

* 修改：`build_game.py`、`nb_commands.{c,h}`、`nb_special.c`、`nb_mainmenu.c`、`nb.c`、`nb.h`、`i18n_gen.py`、`sys_*.txt`、`devdocs/207`（仅 ERRATA）、`CHANGELOG.md`、`AGENTS.md`、`docs/B90`、`docs/B92`、guildbook cn/en

