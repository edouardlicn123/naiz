# 208 — Scene 菜单（场景鉴赏）

- **状态**：完结（0.4.029 实施；实机冒烟待人工）
- **基线版本**：0.4.028 → 实施后 0.4.029
- **日期**：2026-11-13
- **目标项目**：`projects/demo-a2`
- **关联规则**：§十（规格与实现的收敛责任）、§十一（8.3 命名）、§十四（输入循环 / 系统界面 i18n）、§十七（Bug 防复发）
- **前置文档**：`devdocs/207-sceneconf场景清单标记-onlist-outlist.md`（其运行期访问器由本文构建期方案替代）

---

## 1. 需求

> 架构参考画廊菜单。
> 1. 仅显示 sceneconf 为 normal 的场景，且必须为 onlist。
> 2. 如该场景带 cg，则使用第一张 cg 作为缩略图；如该场景不带 cg 但有动画，则从该动画中抽取第一帧作为缩略图；如果两者都没有，则使用该场景名称的第一个字母的大写字母作为图标。

## 2. 设计决策

| 项 | 决策 | 理由 |
|---|---|---|
| 数据来源 | 构建期扫描 `projects/<game>/scene/*.nb`，生成 `core/engine/nb_scene_menu.h` | 运行期无目录遍历能力；`scene_switch()` 只需 8.3 文件名，表在编译期固化 |
| 运行期访问器 | 删除 207 的 `nb_is_scene_listed()` / `NbState.scene_listed` | 无消费方即死导出，`symbol_audit -s A,B --gate`（R30）会判失败 |
| 缩略图 | 构建期生成固定 160×100 MAG | 引擎无缩放原语；`menu_layer_blit_sprite` 只裁剪到层边界，无源子矩形 blit |
| 缩略图优先级 | 首个 `cg(){key}` → 首个 `playanima(...){key}` → 字母图标（`thumb_id=0`） | 需求 2；仅看该场景脚本自身 |
| 网格 | 3 列 × 2 行 = 6/页；格 180×130；缩略图 (x+10,y+4) 160×100；标题基线 y+108 | 640×400：548 宽居中（x=46）；底 304 < 翻页箭头 318 |
| 选中态 | 选中：黄色 2px 边框 + 黄标题；未选中：白色 1px 边框 | 场景菜单是「进入播放」语义，焦点必须可见 |
| 播放 | `menu_finish()` 后 `scene_switch(entry.scene, SCENE_SWITCH_SCRIPT)` | 章节播放属脚本语义（同 `scene()` 命令），不携带菜单状态 |
| 返回 | `scene_switch(nb_get_menu_return()` 或 `"mainmenu.nb"`, `SCENE_SWITCH_MENU`) | 与 `nb_cggallery.c: gallery_return_home()` 同款 |

## 3. 构建期生成（`tools/naiz_build/scene_menu.py`）

```python
THUMB_W, THUMB_H = 160, 100
THUMB_SUFFIX = '_t'
THUMB_TYPE = 'THUMB'
HEADER_PATH = ROOT / 'core/engine/nb_scene_menu.h'

def build_scene_menu(proj_dir: Path, scene_dir: Path, asset_dirs=()) -> int
```

流程：

1. `scene_dir.glob('*.nb')` 按文件名升序；每文件取**第一条** `sceneconf(){...}`，字段拆分一律用 `naiz_lib.nb_line.next_field()`（§十四.9 转义逗号）。
2. 过滤 `type ∈ {'', 'normal'}` 且 `list == 'onlist'`（缺省即 outlist）。标题 = 字段 0。
3. 缩略图：
   - 首个 `cg(){<key>}`：ASSETS.DB `type='CG' AND name=<key>` → 文件名基名 `<cg>`；查 `type='THUMB' AND filename='images/<cg>_t.MAG'` 取 `id`（与 `cg_thumb.py` 的 `THUMB_SUFFIX` 同规则）。缺失 WARN 后降级。
   - 否则首个 `playanima(...){<key>}`：ASSETS.DB `type='ANI' AND name=<key>` → `filename`（相对 `proj_dir`，如 `ani/X.ANI`）→ `parse_ani()` → `blobs[0]` → `decode_mag_full()` → PIL `Image`（`pixels` 为 w*h 索引 + `palette`）→ `resize_to_screen(..., 160, 100, cover=True)` → `convert_image(..., no_resize=True, reserved=PROTECTED_IDX_ALL)` 写 `proj_dir/images/<ani>_t.MAG` → upsert ASSETS.DB `(filename, 'THUMB', name)`。8.3 与短名互异校验同 `cg_thumb._check_name`。
   - 均无 → `thumb_id = 0`。
4. 生成头文件（幂等，内容相同不重写）：

```c
#define SCENE_MENU_COUNT <n>
typedef struct { const char *scene; const char *title; unsigned short thumb_id; } SceneMenuEntry;
static const SceneMenuEntry scene_menu_entries[SCENE_MENU_COUNT > 0 ? SCENE_MENU_COUNT : 1] = {
    { "nbook005.nb", "Come with cat", 29 },
};
```

5. `build_game.py` 在 `build_cg_thumbs(...)` 之后、`export_asset_table.py` 之前调用（新 THUMB 行先入库，再导出头并打包进 IMAGE.DAT）。

## 4. 引擎（`core/engine/nb_scene_menu.c`）

- 常量：`SCM_COLS 3`、`SCM_ROWS 2`、`SCM_CELLS 6`、`SCM_ORIGIN_X 46`、`SCM_ORIGIN_Y 40`、`SCM_CELL_W 180`、`SCM_CELL_H 130`、`SCM_STEP_X 184`、`SCM_STEP_Y 134`、`SCM_THUMB_W 160`、`SCM_THUMB_H 100`、`SCM_GRID_BOTTOM 304`、`SCM_ARROWS_Y 318`、`SCM_COUNT_Y 330`、`SCM_BACK_Y 352`。
- 结构完全照 `nb_cggallery.c`：`menu_save_item_palette` / 255 槽 save-restore / `menu_layer_open` / `menu_layer_begin_draw|erase_to_base|commit|blit` / `input_drain_boundary` / `engine_frame_pump` / `hal_mouse_*` / `menu_finish`。
- `scm_draw_cell`：有缩略图 → `image_load(id)` + `menu_layer_blit_sprite(img,x+10,y+4,PAL_NO_TRANSPARENCY)`；无 → 255 槽蓝底 + `draw_title_large(大写首字符, scale 4)`（`text_title_width` 居中）。标题 `tr(entry.title)` 居中于格内。
- 键盘：方向键移动焦点、Enter/Space/XFER 选中、Esc 返回；鼠标：格命中选中并进入、`menu_back_hit` 返回、`menu_page_hit` 翻页。
- 空态：`SCENE_MENU_COUNT == 0` 画 `tr("No scenes available.")`，任一键/点击返回（照画廊空态）。
- 注册：`nb_commands.h` 声明 + `nb_commands.c` cmd_table `{"scenesmenu", cmd_scenesmenu, CMD_BLOCKING | CMD_NEEDS_INPUT | CMD_TOUCHES_DISPLAY}`。
- `core/Makefile` 用 `wildcard engine/*.c`，无需改动。

## 5. 改动清单

| # | 文件 | 改动 |
|---|---|---|
| 1 | `tools/naiz_build/scene_menu.py`（新增） | 扫描 / 缩略图 / 头文件生成 |
| 2 | `tools/naiz_build/build_game.py` | 管线接入（cg_thumb 之后、export 之前） |
| 3 | `core/engine/nb_scene_menu.c`（新增） | `cmd_scenesmenu` 网格菜单 |
| 4 | `core/engine/nb_commands.h` / `.c` | 声明 + cmd_table 注册 |
| 5 | `projects/demo-a2/scene/scenes.nb`（新增） | `sceneconf(){Scenes, menu}` + `bg(normal){yellow_grid}` + `scenesmenu()` |
| 6 | `core/engine/nb_special.c` | `scenes` 分支由误接的 LOAD 改为跳 `scenes.nb` |
| 7 | `core/engine/nb_mainmenu.c` | `scenes` 桩改为跳 `scenes.nb` |
| 8 | `core/engine/nb.c` / `nb.h` | 删除 `scene_listed` 字段 / 重置 / `nb_is_scene_listed()` |
| 9 | `devdocs/207-...md` | 头部 ERRATA 块（正文不改） |
| 10 | `tools/naiz_conv/i18n_gen.py` | `SYSTEM_UI_KEYS` 加 `SCENE GALLERY`、`No scenes available.` |
| 11 | `projects/demo-a2/i18n/sys_<lang>.txt` + `game_<lang>.txt` | 9 语言译文（UI 两条 + 场景标题 `Scenes`） |
| 12 | `tools/tests/test_scene_menu.py`（新增） | 守卫（见 §6） |

## 6. 防呆守卫

1. 扫描过滤：normal+onlist 收录；outlist / menu / 空 type 判定正确。
2. 标题转义：`Ira\, Jr.` → `Ira, Jr.`，源码使用 `nb_line.next_field`。
3. demo-a2 表中 `nbook005.nb` 的 `thumb_id == 29`。
4. 合成 ANI（`AnimContainerDef` + `build_ani`）→ 160×100 THUMB + ASSETS.DB 行 + `thumb_id != 0`。
5. 无 CG/ANIM → `thumb_id == 0`（并入扫描过滤用例的字母回退断言）。
6. Python 与 C 网格常量逐项相等，且 `SCM_GRID_BOTTOM < SCM_ARROWS_Y`。
7. `scenesmenu` 已注册且带 `CMD_BLOCKING`，头文件有声明。
8. `nb.c`/`nb.h` 不再出现 `nb_is_scene_listed`。
9. 两条新 UI 文案在 `SYSTEM_UI_KEYS` 且 9 语言译文非空、宽度不超限。

## 7. 验收

1. `make -C core` → `core/*.err` 全空。
2. `pytest` 全绿。
3. `./makegame.sh build demo-a2 && ./makegame.sh make demo-a2` 成功，`nb_scene_menu.h` 含 `nbook005.nb`。
4. `fullaudit --no-make` 的 symbol_audit A/B gate 通过。
5. 实机：special → Scenes → 1 格（cg01 缩略图）→ Enter 播放 `nbook005.nb`；Esc 返回 special。

## 8. 实施记录（0.4.029）

| 项 | 结果 |
|---|---|
| `make -C core` | 通过，`core/*.err` 全空（含新增 `nb_scene_menu.o`） |
| `pytest` | **926 passed, 2 skipped**（基线 918 + 新增 8；`test_sceneconf_list` 2 项改写为构建期语义） |
| `fullaudit --no-make` | 全绿：规则审计 / pytest / nb_validator / py_compile / bash -n / symbol_audit A+B gate |
| `build + make demo-a2` | 成功；`nb_scene_menu.h` 生成 1 项（`nbook005.nb` / `Come with cat` / `thumb_id=29`）；CJK 9 语言字库重生成含新 UI 文案 |
| 实机冒烟 | 待人工执行（special → Scenes → 缩略图 → Enter 播放 → Esc 返回） |

### 8.1 实施中的偏差与修正

- `sceneconf` 载荷在 **`{}`**（`parse_nb_line().text`），不是 `()`（`.raw`）——首版误读 `raw` 导致 0 项，已改为 `text`。
- 表内 `scene` 字段保留**原始文件名**（如 `nbook005.nb`），仅用 `to_dos_name()` 验证不会被截断；首个版本输出大写 8.3 名，虽查找大小写不敏感但会偏离脚本写法。
- ANI 派生缩略图名取**脚本 key**（`<key>_t`）而非 ANI 文件名，避免大小写/改名漂移。
- `nb_validator` 需登记 `scenesmenu`（自带命令白名单，与引擎 cmd_table 分离）。
- `nb_music.c:144` 的 C22 假阳性（`- hw` 被识别为取负）以无符号宽度 + 显式 `(int)` 转型收敛，fullaudit 转绿。
- 新增 6 行调用使 `build_game.py` / `nb_mainmenu.c` / `nb.c` 行号位移：`test_devdoc_refs` 白名单（549/564/571、130/132、178/183/360）与 `devdocs/204` 锚点、`devdocs/207` ERRATA 已同步。**0.4.030（devdoc 209）再校准**：`nb.c` 删除 `nb_get_filename()` 并新增解锁块/播放标志后，当前 `prefs_load` 调用 **172**、`nb_set_lang` 调用 **177**、定义 **381**。
