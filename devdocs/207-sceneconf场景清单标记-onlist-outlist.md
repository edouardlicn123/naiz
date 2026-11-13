# 207 — sceneconf 第三字段：场景清单标记（onlist / outlist）

- **状态**：**已实施（完结，2026-11-13）**
- **基线版本**：0.4.027 → 实施后 0.4.028
- **日期**：2026-11-13
- **目标项目**：`projects/demo-a2`
- **关联规则**：§十（规格与实现的收敛责任）、§十四.9（段内字段逗号须转义）、§十四（系统界面 i18n）、§十七（Bug 防复发清单）

> ## ⚠ ERRATA（0.4.029 追加）
>
> **被推翻的结论**：本文 §2/§3 声称运行期用 `nb_is_scene_listed()` 访问器消费 `NbState.scene_listed`，且该访问器是「本版唯一消费接口」。
>
> **错在哪**：scene 菜单最终采用**构建期扫描**方案（`tools/naiz_build/scene_menu.py` 直接读 `sceneconf` 第三字段并生成 `core/engine/nb_scene_menu.h`），运行期没有任何调用方。若保留 `nb_is_scene_listed()` 即成为死导出，`symbol_audit -s A,B --gate`（R30）会判失败。
>
> **正确结论**：`NbState.scene_listed` 字段、`nb_load()` 中的重置、`nb_is_scene_listed()` 均已于 0.4.029 删除；`nb_set_scene_conf()` 仍接收并校验第三字段（拼错 `onlst` 依旧 `hal_log` WARN），但不再存储。
>
> **接替文档**：`devdocs/208-scene菜单（场景鉴赏）.md`。本文正文按归档规则一字未改。
>
> **行号再校准（0.4.029）**：删除 `scene_listed` 字段/重置/访问器后 `nb.c` 再次上移——`prefs_load` 调用 **178**、`nb_set_lang` 调用 **183**、`nb_set_lang` 定义 **360**；`test_devdoc_refs.py` 白名单已同步。§三「行号校准」表中的 180/185/370 为 0.4.028 当时值，已被本次取代。**0.4.030 再校准（devdoc 209）**：`nb_load` 增加解锁块、`scene_switch` 增加播放标志，且 `nb_get_filename()` 因失去调用方被删除——当前 `prefs_load` 调用 **172**、`nb_set_lang` 调用 **177**、`nb_set_lang` 定义 **381**。

---

## 1. 需求

`sceneconf` 现有语法：

```
sceneconf(){title[, type]}
```

扩展为：

```
sceneconf(){title[, type[, onlist|outlist]]}
```

- 第三个字段标记该场景**是否计划进入 scene 菜单展示**（`specialmenu` 的 `scenes` 入口 / `mainmenu` 的 `scenes` 分支在未来落地时消费）。
- **默认值 `outlist`**（不展示）；未写第三字段与显式 `outlist` 等价。
- `nbook005.nb` 标记为 `onlist`。

## 2. 设计决策

| 项 | 决策 | 理由 |
|---|---|---|
| 存储 | `NbState.scene_listed`（`int`，0=outlist / 1=onlist） | 二值语义，无需字符串存储；`scene_type` 保持字符串因有 3 种取值 |
| 解析 | 第二逗号后的剩余字段；空字段 = outlist | 与 `type` 尾字段处理一致 |
| 非法值 | `hal_log` WARN + 回落 outlist | §九.6 消灭静默失败；拼错 `onlst` 必须可见 |
| 生命周期 | `nb_load()` 重置为 0 | 与 `chapter_title` / `scene_type` 同处重置，防止跨场景残留 |
| 消费 | 本版仅提供 `nb_is_scene_listed()` 访问器 | scene 菜单尚未实现（`nb_mainmenu.c` 现为 `hal_log("scene select: not implemented")`）；无消费方时不做凭空 UI |

## 3. 改动清单

| # | 文件 | 改动 |
|---|---|---|
| 1 | `core/engine/nb.c` | `NbState` 加 `int scene_listed;`；`nb_set_scene_conf()` 加第三参 `const char *list`；`nb_load()` 重置；新增 `nb_is_scene_listed()` |
| 2 | `core/engine/nb_internal.h` | `nb_set_scene_conf` 签名更新 |
| 3 | `core/engine/nb.h` | 声明 `int nb_is_scene_listed(void);` |
| 4 | `core/engine/nb_commands.c` | `cmd_sceneconf` 解析第三字段（`nb_next_field` 取 type，再取剩余为 list） |
| 5 | `projects/demo-a2/scene/nbook005.nb` | `sceneconf(){Come with cat, normal, onlist}` |
| 6 | `tools/naiz_build/nb_validator.py` | `SIGNATURES` 描述更新；校验第三字段 ∈ {空, onlist, outlist}，非法即 error |
| 7 | `tools/naiz_conv/i18n_gen.py` | 注释说明第三字段不影响标题取键（标题仍在第一个逗号前） |
| 8 | `docs/B92-NB脚本命令参考.md` | 命令表 `sceneconf` 行更新 |
| 9 | `guildbook_cn/pages/sc11-sceneconf.html` | 语法 / 参数表 / 示例补第三字段；`doc-version` 更新 |
| 10 | `guildbook_en/pages/sc11-sceneconf.html` | 英文同步；`translated-from` 更新 |
| 11 | `tools/tests/test_sceneconf_list.py`（新增） | 见 §4 |

**不改**：`i18n_gen` 的标题取键逻辑（`text.split(',')[0]` 仍取到标题，第三字段在其后）；`nb_is_menu_scene()`；存档格式（标记不落盘）。

## 4. 防呆守卫（`tools/tests/test_sceneconf_list.py`）

1. `test_engine_parses_third_field` — `nb_commands.c` 的 `cmd_sceneconf` 含第二次 `nb_next_field` 且把剩余字段传给 `nb_set_scene_conf`。
2. `test_engine_defaults_to_outlist` — `nb_set_scene_conf` 对空/`outlist` 置 0、`onlist` 置 1；未知值有 `hal_log` WARN 并回落 0。
3. `test_nb_load_resets_scene_listed` — `nb_load` 中重置语句存在（跨场景不残留）。
4. `test_all_project_sceneconf_fields_legal` — 全项目 `sceneconf` 第三字段 ∈ {空, onlist, outlist}。
5. `test_nbook005_marked_onlist` — 005 场景为 `onlist`，其余默认 `outlist`。
6. `test_validator_rejects_bad_list_flag` — `nb_validator` 对 `sceneconf(){T, normal, onlst}` 报错、对合法值放行。

## 5. 验收标准

1. `make -C core` 0 err（`core/*.err` 全空）；`pytest` 全绿（基线 912 + 新增守卫）。
2. `./makegame.sh build demo-a2 && ./makegame.sh make demo-a2` 成功。
3. `nb_validator` 对全项目零 error。
4. 完成后 `bump_version` + CHANGELOG 条目（锚点续号 c105）+ AGENTS 头部状态行。

## 6. 实施记录（0.4.028）

| 项 | 结果 |
|---|---|
| `make -C core` | 0 err（`core/*.err` 全空） |
| `pytest` | **918 passed, 2 skipped**（基线 912 + 新增 6 项） |
| `nb_validator` | demo-a2 全场景零 error（含 005 的 `onlist`） |
| `build + make demo-a2` | 成功，HDI 与 `engine.exe` 同步 |
| 版本 | 0.4.027 → **0.4.028**；CHANGELOG 锚点 `c105` |
| 行号校准 | `nb.c` 因新增字段与函数整体下移：`prefs_load` 调用 167→**180**、`nb_set_lang` 调用 172→**185**、`nb_set_lang` 定义 349→**370**；`test_devdoc_refs.py` 白名单与 `KNOWN_GOOD`（`nb.c` 316→**332**）已同步 |

**§十 收敛责任自查**：

- 新增文件（`test_sceneconf_list.py`、本 devdoc）存在性已核。
- 「改动既有文件」逐处核对：`nb.c`（struct/`nb_set_scene_conf`/`nb_load`/访问器 4 处）、`nb_internal.h`、`nb.h`、`nb_commands.c`（`cmd_sceneconf` 函数体整段替换）、`nbook005.nb`（首行）、`nb_validator.py`（SIGNATURES + 校验分支）、`i18n_gen.py`（取键改 `nb_next_field`）、B92/B90、guildbook cn/en 两页——均落在声称位置。
- `i18n_gen` 的改动是**行为级**（裸 `split` → `next_field`），仅在标题含 `\,` 时取键结果不同，与引擎逐字节一致，属 §十四.9 的收口而非新特性。

## 7. 实机冒烟（待执行）

1. 启动 `nbook005.nb`，串口无 `WARN: sceneconf` 行（005 为合法 `onlist`）。
2. 全部场景加载后串口无 `unknown list flag` / `unknown type`（全项目字段合法）。
3. 因本版无消费方（scene 菜单为桩），画面与既有行为一致——仅验证无回归。

## 8. 风险与二期

- 第三字段为**编译期/加载期元数据**，不落存档；读档后 `nb.scene_listed` 由目标场景重新解析，语义正确。
- 二期实现 scene 菜单时才真正消费 `nb_is_scene_listed()`；届时需决定展示顺序（按 `id` 还是按场景文件名）与标题来源（`chapter_title`）。
- `nb_validator` 的第三字段校验依赖 `naiz_lib.nb_line.next_field()` 而非裸 `split(',')`，遵守 §十四.9 的转义语义。
