# Tasks — Scene 菜单（场景鉴赏）

> 依赖：`spec.md` §2–§7。按序执行，每完成一项即勾选。

1. [x] **devdoc 208**：写 `devdocs/208-scene菜单（场景鉴赏）.md`（需求 / 设计 / 改动清单 / 守卫 / 验收），内容取自 `spec.md`，头部状态「实施中」。
2. [x] **构建期生成器**：新增 `tools/naiz_build/scene_menu.py`
   - `build_scene_menu(proj_dir, scene_dir, asset_dirs)`：扫描 `sceneconf`（`nb_line.next_field`）、过滤 normal+onlist、CG→THUMB / ANI 首帧→THUMB / 字母图标。
   - 生成 `core/engine/nb_scene_menu.h`（幂等）；8.3 + 短名互异校验。
3. [x] **接入构建**：`tools/naiz_build/build_game.py` 在 `build_cg_thumbs` 之后、`export_asset_table` 之前调用。
4. [x] **引擎**：新增 `core/engine/nb_scene_menu.c`（`cmd_scenesmenu`，3×2 网格、选中态、翻页、Back、空态、`scene_switch(..., SCENE_SWITCH_SCRIPT)`）。
5. [x] **注册**：`nb_commands.h` 声明 + `nb_commands.c` cmd_table 条目（`nb_validator` 白名单同步）。
6. [x] **接线**：`nb_special.c` scenes 分支改为跳 `scenes.nb`；`nb_mainmenu.c` scenes 桩改为同款；新增 `projects/demo-a2/scene/scenes.nb`。
7. [x] **删除死访问器**：`nb.c` 的 `scene_listed` / `nb_load` 重置 / `nb_is_scene_listed()`，`nb.h` 声明。
8. [x] **207 ERRATA**：仅追加订正块，正文不动（含行号再校准）。
9. [x] **i18n**：`i18n_gen.py` `SYSTEM_UI_KEYS` 加 `SCENE GALLERY`、`No scenes available.`；9 语言 `sys_*.txt` 补译文。
10. [x] **守卫测试**：新增 `tools/tests/test_scene_menu.py`（9 项，见 spec §6）。
11. [x] **验证链**：`make -C core`（`core/*.err` 空）→ `pytest` 926 passed → `./start.sh fullaudit --no-make` 全绿 → `./makegame.sh build demo-a2 && ./makegame.sh make demo-a2`。
12. [x] **收尾**：`bump_version`（0.4.029）→ 重新 build+make → `CHANGELOG.md` c106 + 索引首行 → `AGENTS.md` 头部 → `docs/B90`/`docs/B92` → guildbook `sc11-sceneconf` cn/en 版本标签。禁止 commit。
