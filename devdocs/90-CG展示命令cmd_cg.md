# 90 - CG 展示命令：cmd_cg 全屏展示 + 即时解锁

> 状态：**活动文档**（CG feature 阶段 3 的权威设计 + 实施计划载体；实施落地后按实际代码复核修订本档）。
> 前序关系：devdoc 88（CG 数据管线，产出 `cg_map[]`）→ 89（CG 解锁 API，产出 `sys_save_unlock_cg`）→ **本档**（消费 API + `cg_map` 的展示命令）→ 91/92（画廊）。
> 引擎命令名：`cg`，注册于 cmd_table，处理函数 `cmd_cg`。

---

## 一、决策记录

### 1.1 命令设计

| # | 决策 | 理由 |
|---|------|------|
| D1 | **语法**：`cg <asset_key>`（括号参数，单参） | 对标 `bg <asset>`；key 在 `cg_map[]`（type='CG'）解析。零位置参数、无 effect 位（阶段 3 不做转场） |
| D2 | **渲染路径**：`cg` **复用 `layer_bg_change(img)`，与 `bg` 同路径** | ★ 关键修正，推翻早期讨论的"不复用"设想（见 §1.2 详细论证） |
| D3 | **解锁时点**：在绘制前调用 `sys_save_unlock_cg` | 先持久化后展示 → 展示途中崩溃也不会丢解锁；对接 devdoc 89 契约 |
| D4 | **cg_id 映射**：`cg_id = cg_map[] 数组下标 + 1`（1-based） | devdoc 89 契约落地；阶段 5 画廊必须同规则遍历（见 §四 R-1） |
| D5 | `cg` 触发 `anim_stop()`（隐式停止动画） | 与 `cmd_bg` 一致：新全屏内容终结既有动画 |
| D6 | 调色板三固定（白/透明白/光标黑）复制自 `cmd_bg` | CG 与 bg 共享同渲染语义；索引 7/15/254 状态必须一致 |
| D7 | 失败路径全部 `NB_DEBUG` 日志，不中断剧本 | 命令失败不 panic（同 `cmd_bg` 抛错风格）；未知 key / 加载失败 / cg_id 越界均显式记录 |

### 1.2 D2 详细论证（推翻早期讨论设想）

> 注：此处"不复用 `layer_bg_change`"的设想来自 feature 早期 **会话讨论**（未落笔 devdoc 88 正文——devdoc 88 §一 D2 只记录了"渲染语义等价非 sprite 全屏背景"，未涉及复用策略）。本档将其显式载入并推翻，作为设计演化结论。

devdoc 88 §一曾写"`cg` 不复用 `layer_bg_change` 的背景快照语义，CG 是一次性展示，不应成为持久背景"。深入细化对照渲染状态机后**确认此设想有隐性 bug，予以推翻**：

`layer_bg_change` 职责（layer_bg.c:175）：`vram_blit` 全屏 → 条件重建 `bg_dialog_snapshot` → 重绘精灵 → dialog/button 调色板 → **捕捉 `bg_snapshot`（全屏）**。它保证两套快照与当前画面一致。

若 `cg` 只做 `vram_blit` 而不更新快照（原设想），后续任何依赖快照的操作都会基于**过期背景**：
- 台词触发 `layer_dialog_open()` → 对话框快照捕捉的是 CG 画面，但本底恢复路径 / 精灵 clean-reset 都用旧 `bg_dialog_snapshot` → 立绘底一半露出旧背景。
- `char(hideall)` / sprite 隐藏恢复 → 恢复旧背景，CG 被穿帮。

因此 **CG 必须走完整 `layer_bg_change`**，让 CG 成为"当前背景"。galgame 中 CG 场景本就由剧本在后续 `bg(...)` 切换走，与"CG=临时背景"语义不冲突。此修正同时让 `bg(cgxxx)` 与 `cg(cgxxx)` 渲染结果逐像素一致（仅解锁/日志/表不同）。

---

## 二、命令规范

### 2.1 语法

```
cg <asset>       # 全屏展示 CG（type='CG' 资产），首次调用即永久解锁
```

单参数，key 与 `asset_map` 的 bg key 命名空间**独立**（devdoc 88 R-C）：`cg` 只查 `cg_map`，不经过 `nb_asset_id()`，同名不同类的 key 无歧义。

### 2.2 语义

| 项 | 行为 |
|----|------|
| 展示 | `image_load(id)` → `layer_bg_change(img)` 全屏 + 调色板 + 快照重建（同 bg） |
| 解锁 | `sys_save_unlock_cg(cg_id)` 于绘制前执行，即时写盘 `SYSTEM.SAV` |
| 动画 | `anim_stop()` 隐式停止已播动画 |
| 后续对白 | CG 即当前背景；`fei(){...}` 等正常触发对话框，快照机制无陈旧感 |
| 切换走 | 下一 `bg(...)` / `cg(...)` / 场景切换覆盖 |

### 2.3 与 bg 的差异

| 维度 | bg | cg |
|------|----|----|
| 解析表 | `asset_map`（IMG） | `cg_map`（CG） |
| 解锁副作用 | 无 | `sys_save_unlock_cg(cg_id)` |
| 渲染路径 | `layer_bg_change` | **相同** `layer_bg_change` |
| effect/transition 位 | 接收 2-3 参（忽略 effect） | 阶段 3 仅单参；多余参数由编译器签名/validator 拦截 |

---

## 三、细化实现（逐文件）

### 3.1 新文件 `core/engine/nb_cg.c`

```c
/*
 * nb_cg.c -- CG fullscreen display command (cmd_cg).
 *
 * Shows an event CG (type='CG' asset) using the same rendering path as
 * bg, then permanently unlocks it in SYSTEM.SAV (devdoc 89/90).
 * Syntax: cg <asset_key>
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "render.h"
#include "image.h"
#include "scene_layers.h"
#include "hal.h"
#include "save.h"
#include "debug.h"
#include "nb_asset_table.h"
#include "nb_anim.h"
#include "nb_commands.h"
#include "nb_internal.h"

void cmd_cg(int argc, const char **argv, const char *cmd_name)
{
    const struct { const char *key; int id; } *p;
    int cg_id = -1;
    int id = -1;
    MagImage *img;

    (void)cmd_name;
    if (argc < 1) {
        NB_DEBUG("cg: no args\r\n");
        return;
    }

    /* Resolve key in cg_map.  cg_id is the 1-based array index (devdoc 89
     * contract); the gallery (devdoc 92) must traverse with the same rule. */
    for (p = cg_map; p->key != NULL; p++) {
        if (strcmp(p->key, argv[0]) == 0) {
            id = p->id;
            cg_id = (int)(p - cg_map) + 1;
            break;
        }
    }
    if (id < 0) {
        NB_DEBUG("cg: unknown asset '%s'\r\n", argv[0]);
        return;
    }
    if (cg_id < 1 || cg_id > CG_TOTAL) {
        NB_DEBUG("cg: logical id %d out of range (CG_TOTAL=%d)\r\n",
                 cg_id, CG_TOTAL);
        return;
    }

    anim_stop();          /* implicit stop: new CG ends any animation */

    img = image_load((unsigned short)id);
    if (!img) {
        NB_DEBUG("cg: image_load(%d) failed\r\n", id);
        return;
    }

    /* Unlock BEFORE drawing: persist even if a later panic cuts us off. */
    sys_save_unlock_cg(cg_id);

    hal_mouse_invalidate_cursor();
    hal_set_palette(PAL_WHITE, 0xFF, 0xFF, 0xFF);
    hal_set_palette(PAL_TRANSPARENT, 0xFF, 0xFF, 0xFF);
    hal_set_palette(PAL_CURSOR_BLACK, 0x00, 0x00, 0x00);
    layer_bg_change(img);
    mag_release(img);

    NB_DEBUG("cg: id=%d cg_id=%d key=%s\r\n", id, cg_id, argv[0]);
}
```

> 注释按 AGENTS.md §九-9 全英文。

### 3.2 `core/engine/nb_commands.h` — 声明

在 `cmd_cgvmenu` 声明前/后追加（归入"Handlers split"注释组）：
```c
/* CG display command (nb_cg.c, registered in cmd_table). */
void cmd_cg(int argc, const char **argv, const char *cmd_name);
```

### 3.3 `core/engine/nb_commands.c` — 注册

`cmd_table[]` 中 `{"bg", cmd_bg}` 之后插入：
```c
{"cg",           cmd_cg},
```

### 3.4 编译接入

`core/Makefile` 用 `ENG_SRCS = $(wildcard engine/*.c)` 自动收集 → **无需改 Makefile**。`nb_asset_table.h` 自动含 `cg_map[]`（阶段 1 已就位），`build/nb_cg.o` 依赖引擎层头文件（ENG_HEADERS 聚合，无需单列）。

### 3.5 `tools/naiz_build/nb_validator.py` — 校验下放

1. `SIGNATURES` 增：
   ```python
   'cg':       (1, 1, 'cg(key)'),
   ```
2. `validate_scene` 的 `elif cmd == 'bg'` 分支后新增：
   ```python
   elif cmd == 'cg' and len(args) >= 1:
       if args[0] not in cg_keys:
           errors.append(
               f"  {nb_path.name}:{lineno}: cg key {args[0]!r} "
               "not in img_map (type=CG)")
   ```
3. 删除阶段 1 的占位 `_ = cg_keys`（cg_keys 现被真实消费）。

---

## 四、Bug 检查（§十七 规则逐条过）

### C 类（nb_cg.c / 头 / 命令表）

| # | 规则 | 落点 | 检查结论 |
|---|------|------|---------|
| C1 | malloc 检查 | 无 malloc（image_load 内部已有） | ✓ |
| C2/C3 | fopen/fread | 无 | ✓ |
| C5 | snprintf vs sprintf | 无格式化输出到栈缓冲区 | ✓ |
| C6 | 数组/指针边界 | `p - cg_map` 受 `p->key != NULL` 停止；cg_id 范围 `[1, CG_TOTAL]` 显式复查；`cg_map` 空表时 `__dummy__` 占位保终止不越界 | ✓ |
| C8 | 有符号溢出 | 无取负/加法（cg_id ≥ 1 受检；`(p-cg_map)` 是 ptrdiff，int 内） | ✓ |
| C10 | switch default | 无 switch | ✓ |
| C12 | void 用返回值 | 无 | ✓ |
| C13 | static 未用 | `cmd_cg` 非 static，被 cmd_table 引用 → 非死导出 | ✓ |
| C14 | 失败日志 | 4 条失败路径均有 `NB_DEBUG`（无参/未知 key/cg_id 越界/加载失败） | ✓ |
| C18 | 快路径副作用 | **无快路径**——`cg` 完整走 `layer_bg_change`（§1.2 论证），无省步 | ✓ |
| C21 | 禁 strcpy | 无 | ✓ |
| C22 | INT_MIN 取负 | 无 | ✓ |
| C23 | 双重 free | `mag_release(img)` 单次于绘制后 | ✓ |
| C24 | memcpy 尺寸 | 无 memcpy | ✓ |
| C25 | use-after-free | `mag_release` 在 `layer_bg_change` 完成后（后者已 blit/快照，不再引用 img） | ✓ |

### 特定于本阶段的风险

- **R-1：cg_id 映射两处一致性**。devdoc 89 契约 + 本档 D4：`cg_id = cg_map[] 下标 + 1`。阶段 5 画廊**必须**用同一规则遍历 `cg_map[]` 得到解锁位号，否则画廊勾选错位。登记到 devdoc 92 的前置条件。
- **R-2：`layer_bg_change` 内部 `if (!layer_dialog_drawn()) layer_capture_bg_dialog()`**——若对白进行中调 `cg`，对话框区快照不重捕，覆盖的仍是旧背景。这与 `cmd_bg` 行为完全一致（同路径同行为），非本命令引入的新问题；CG 场景惯例上先清场再展示。登记为已知边界，不改。
- **R-3：`__dummy__` 占位**。空 `cg_map` 时表为 `{{"__dummy__",0},{NULL,0}}`。脚本若引用 `__dummy__` 会解锁 cg_id=1 并 `image_load(0)`——属资产占位符伪引用，validator 会以"key not in cg_map(CG)"拦下（`__dummy__` 不在 cg_keys 集合），仅引擎直接跑脚本的裸用才触达，风险可忽略。
- **R-4：解锁数据面**。`sys_save_unlock_cg` 越界静默 return（devdoc 89 D2）——`cmd_cg` 已在调用前自检 cg_id 范围，双保险，不会静默丢解锁。

### Python 类（validator）

| # | 规则 | 检查结论 |
|---|------|---------|
| P1/P2/P3/P4/P5/P8/P9/P14 | 不触碰异常/open/assert/struct/import/默认参/动态执行 | ✓ |
| P11 | `cg_keys` 只读集合，无跨函数回写 | ✓ |

---

## 五、验证方案（阶段 3 完成标准）

1. **编译**：
   ```bash
   make -C core
   ```
   确认 0 err / 0 warn；`cmd_cg` 注册无重复、无死导出告警。
2. **validator 单测**：
   ```bash
   tools/env_setup/venv/bin/python -m py_compile tools/naiz_build/nb_validator.py
   tools/env_setup/venv/bin/python -m pytest tools/tests/ -q
   ```
3. **demo 演示资产**（临时构造，验收后按用户决定保留或回滚）：
   - 复制 `projects/demo-a2/images/pink_grid.MAG → cg01.MAG`、`yellow_grid.MAG → cg02.MAG`
   - `ASSETS.DB` 插两行 `type='CG'`（name=cg01/cg02）
   - 某 `.nb` 脚本插入 `cg(cg01)` / 对白示例
   - 重建：`export_asset_table` + `pack_images` + `make`
   - 运行验证：CG 全屏显示；`SYSTEM.SAV` 对应位被置（`sys_save_is_cg_unlocked`）
4. **完整回归**：`./start.sh fullaudit`。
5. **手动验收**：用户运行查看 CG 场景显示 + 解锁生效。

---

## 六、范围外（后续阶段）

- `cg` 过渡效果参数（未排；D1 仅静态展示）
- gallery 入口（**devdoc 91**）→ 网格 + 回看（**devdoc 92**）
- 缩略图（二期独立阶段）