# 72 — sceneconf 场景配置命令（标题 + 类型）

> **状态**: 设计定稿，待实施
> **日期**: 2026-08-13
> **范围**: NB 命令层（`core/engine/nb_commands.c` / `nb.c` / `nb_internal.h`）+ demo 脚本迁移 + 文档
> **方法**: 静态分析，结论核实到 `file:line`
> **结论**: 以新命令 `sceneconf(title, type)` 取代 `title` 指令；类型 `normal`/`cg`/`menu` 仅运行态存储（不随存档）；`menu` 类型取代 `nb_is_menu_scene()` 的文件名硬编码（F5/F6 存档热键控制）

---

## 1. 现状与动机（已核实）

### 1.1 `title` 指令现状

| 位置 | 内容 |
|---|---|
| `nb_commands.c:250-255` | `cmd_title` → `nb_set_chapter_title(tr(argv[0]))` |
| `nb.c:42` | `NbState.chapter_title[64]` 字段 |
| `nb.c:48-52` | `nb_set_chapter_title` 存标题 |
| `nb.c:171` | `nb_load` 重置 `chapter_title[0]='\0'` |
| `save.c:20-22` | `nb_get_state` 取标题随存档写入 SaveData（**持久化**） |
| 存档界面 | `nb_save_dialog.c:251` / `nb_saveload.c:97` 显示 chapter_title |

**问题**：`title` 只能表达"标题"一个维度，无法表达场景类别。而场景类别目前靠文件名硬编码。

### 1.2 `nb_is_menu_scene()` 文件名硬编码（nb.c:178-186）

```c
int nb_is_menu_scene(void)
{
    return strcmp(nb.filename, "mainmenu.nb") == 0 ||
           strcmp(nb.filename, "loadscene.nb") == 0 ||
           strcmp(nb.filename, "scenes.nb") == 0 ||
           strcmp(nb.filename, "setting.nb") == 0 ||
           strcmp(nb.filename, "logo.nb") == 0 ||
           strcmp(nb.filename, "op.nb") == 0;
}
```

- 唯一消费方：`main.c:133/139` 控制 F5（存档）/ F6（读档）热键是否可用
- 缺陷：新场景若属菜单类（如 future CG 鉴赏场景）必须改文件名或在列表追加，脚本侧无法声明

### 1.3 解析器能力（nb_parser.c，已核实）

- `cmd(arg1, arg2)` 括号形式：**按逗号自动拆分为多参数**
- `cmd(){text}` 文本形式：`{...}` 内**整体作为一个参数**（不按逗号拆分，nb_parser.c:61-70）

因此 `sceneconf(){A normal day, normal}` 会得到**单个**参数 `"A normal day, normal"`，需在处理器内再拆分；而 `sceneconf(A normal day, normal)` 自动拆 2 参。

**决策**：demo 用文本形式 `sceneconf(){标题, 类型}`（保持与现 `title(){...}` 风格一致），`cmd_sceneconf` 内实现「标题,类型」二次拆分。

---

## 2. 设计定稿

### 2.1 命令语义

```
sceneconf(){<title>, <type>}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `title` | 是 | 章节标题，沿用 chapter_title 存储（随存档持久化，存档界面显示） |
| `type` | 否（默认 normal） | `normal` / `cg` / `menu` |

- `type` 省略或非法 → 回退 `normal` + hal_log 警告
- `title` 经 `tr()` 翻译（与现 cmd_title 一致）

### 2.2 类型存储与消费

| 项 | 方案 |
|---|---|
| 存储 | `NbState.scene_type[16]`（内存字段，**不**入 SaveData，SAVE_VERSION 不变） |
| 默认 | `"normal"` |
| 重置 | `nb_load`（nb.c:171）重置 `scene_type="normal"`（与 chapter_title 重置同处） |
| menu 消费 | `nb_is_menu_scene()` 改为 `strcmp(nb.scene_type, "menu") == 0`，**删除**文件名硬编码列表 |

### 2.3 类型字段不持久化的理由

- 场景类型是**运行期上下文**，随 `nb_load` 重新声明（每个场景首行 sceneconf），无跨场景持久意义
- 存档读回走 `nb_load(filename)` → 新场景首行 sceneconf 会重新设置类型，无需存档携带
- 避免 SAVE_VERSION 3→4 升级与 `slot_info` 偏移计算（save.c:181-190）的回归风险

---

## 3. 引擎改动清单

### 3.1 `core/engine/nb.c`

1. `NbState` 增加 `char scene_type[16];`
2. 新增 `nb_set_scene_conf(const char *title, const char *type)`：
   - 内部 `nb_set_chapter_title(tr(title))`（标题翻译在调用方或此处，二选一，见 3.3）
   - type 为空或非法（非 normal/cg/menu）→ 回退 `"normal"` + `hal_log` 警告
   - 合法 → `strncpy` 进 `scene_type`
3. `nb_load()` :171 处：`nb.chapter_title[0]='\0'` 后加 `nb.scene_type[0]='\0'`（或置 `"normal"`，用 strncpy）
4. `nb_is_menu_scene()`：改查 `scene_type`；删除文件名列表

### 3.2 `core/engine/nb_internal.h`

- 新增 `void nb_set_scene_conf(const char *title, const char *type);`

### 3.3 `core/engine/nb_commands.c`

1. `cmd_title` → 重写为 `cmd_sceneconf`：
   - argc==0 → return（无参数）
   - 拆分第一个参数（文本形式 `{标题, 类型}` 为整体单参）：
     - 以逗号分割 `argv[0]` → 前段=标题，后段=类型
     - `tr()` 翻译标题
   - 调 `nb_set_scene_conf(标题, 类型)`
2. `cmd_table[]` :309：`{"title", cmd_title}` → `{"sceneconf", cmd_sceneconf}`
3. `cmd_title` 移除（C13：无引用死函数）

> 注：若 `argv[0]` 中含逗号但只有标题无类型（`sceneconf(){A normal day}`），需判定「只有一个逗号且后段为空」→ 类型缺省 normal。实现细节：`strchr(argv[0], ',')` 拆分，无逗号 → 全为标题、类型 NULL。

### 3.4 时序安全论证（菜单类型生效时机）

- `nb_load()` 重置 scene_type → 加载脚本
- 主循环 `nb_process()` 逐行执行，首行 `sceneconf(..., menu)` 即设置 `scene_type="menu"`
- F5/F6 检查在 `main.c:126-144` 的**输入等待循环**内，此时脚本已执行完（sceneconf 已生效）→ **安全**
- 唯一窗口：脚本加载到首条 sceneconf 之间若发生输入检查——但输入检查只在 VMFLAG_PROCESS 清除后的输入等待阶段，此时 nb_process 已完整跑完本轮（含 sceneconf）→ **无窗口**

---

## 4. 迁移清单

### 4.1 demo 脚本（projects/demo-a2/scene/）

| 文件 | 现状 | 迁移后 |
|---|---|---|
| nbook001~020.nb（有 title 的 4 个：001/002/003/004） | `title(){...}` | `sceneconf(){..., normal}` |
| mainmenu.nb | 首行 `bg(mainmenu,normal)` | 首行加 `sceneconf(){..., menu}`（置于 bg 前） |
| loadscene.nb | 首行 `bg(yellow_grid)` | 首行加 `sceneconf(){..., menu}` |
| logo.nb / op.nb | 纯 bg+跳转 | 首行加 `sceneconf(){..., menu}`（用户确认需要） |
| nopbook.nb | 空文件 | 无需 |

### 4.2 文档

| 文档 | 改动 |
|---|---|
| `docs/B92-NB脚本命令参考.md` | `title` 行 → `sceneconf <title>[,type]` 说明 |
| `naiz-guildbook/pages/sc04-scene.html` | §4「title 章节标题」→「sceneconf 场景配置」，加类型表 |
| `docs/B90-参考-函数索引.md` | `cmd_title`→`cmd_sceneconf`、新增 `nb_set_scene_conf`、`nb_is_menu_scene` 语义注记 |

---

## 5. 风险与验证

### 5.1 风险

| 风险 | 等级 | 缓解 |
|---|---|---|
| `cmd_sceneconf` 参数拆分逻辑 bug（文本形式整体单参） | 中 | 拆分复用 `nb_next_field`（nb_commands.c:120，已在 scene 条件链使用） |
| 菜单场景 F5/F6 热键回归 | 中 | 迁移后逐一验证 mainmenu/loadscene/logo/op 场景按 F5/F6 无效 |
| 漏迁移某个脚本（仍用 title） | 低 | `grep -rn '^title' projects/` 确认零残留 |
| B90 索引漏更新 | 低 | 对照 §3 改动清单 |

### 5.2 验证步骤

1. `make -C core` → 0 error / 0 warning
2. `python -m tools.diag.symbol_audit -s A,B` → 清空（cmd_title 移除后无死导出）
3. `tools/env_setup/venv/bin/python -m pytest tools/tests/ -q` → 62 passed
4. `makegame.sh build demo-a2` → 构建通过
5. 运行时（NP2kai --serial）：主场景按 F5 弹出存档；mainmenu/loadscene/logo 按 F5/F6 无效；存档界面显示 chapter_title 正常
6. `grep -rn '^title' projects/demo-a2/scene/` → 零残留

---

## 6. 参考

- `core/engine/nb_commands.c` — cmd_table（:308-327）、cmd_title（:250-255）、nb_next_field（:120）
- `core/engine/nb.c` — NbState（:35-45）、nb_load（:129-175）、nb_is_menu_scene（:178-186）
- `core/engine/nb_internal.h` — nb_set_chapter_title 声明（:38）
- `core/engine/nb_parser.c` — 括号/文本参数解析（:18-73）
- `core/engine/main.c` — F5/F6 输入循环（:126-144）
- `core/engine/save.c` — 存档持久化（chapter_title 路径）
