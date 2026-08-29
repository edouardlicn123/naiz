# 85 — 统一的层管理API：封装状态判断与操作序列

> 日期：2026-08-26
> 前置：devdoc 84（层序显式化，提供 LAYER_Z_* 常量和 layer_is_active 查询）
> 版本起点：0.2.063

---

## 一、问题陈述

### 1.1 调用者需要手动判断层状态

当前层系统暴露了状态查询函数（`layer_dialog_drawn()`、`layer_has_sprite()`），但没有封装状态相关的操作逻辑。调用者必须在每个使用点手动判断状态，然后选择不同的操作路径。

**典型案例1：cmd_bg()（nb_commands.c）**

```c
void cmd_bg(int argc, const char **argv, const char *cmd_name) {
    ...
    vram_blit(img, 0, 0);
    if (!layer_dialog_drawn())        // 调用者查询状态
        layer_capture_bg_dialog();    // 调用者决定条件操作
    layer_redraw_sprites();           // 调用者执行固定操作
    mag_release(img);
    dlg_update_palette();             // 调用者执行调色板同步
    btn_update_palette();
    layer_capture_bg();               // 调用者执行快照（隐式清除对话框状态）
}
```

问题：调用者必须知道7步仪式的正确顺序，且必须理解`layer_capture_bg()`会隐式清除对话框状态。

**典型案例2：dialog_show()（nb_dialog.c）**

```c
static void dialog_show(void) {
    if (!layer_dialog_drawn()) {      // 调用者查询状态
        layer_dialog_open();          // 路径A：首次打开
    } else {
        layer_dialog_snap();          // 路径B：重新拍快照
    }
    layer_dialog_restore();           // 固定操作
}
```

问题：调用者必须判断"是首次打开还是重新拍快照"，然后选择正确的函数。

**典型案例3：cmd_char()（nb_commands.c）**

```c
void cmd_char(int argc, const char **argv, const char *cmd_name) {
    ...
    type = layer_has_sprite(char_id) ? "face" : "body";  // 查询状态
    if (strcmp(type, "body") == 0) {
        if (layer_has_sprite(char_id))                     // 再次查询状态
            layer_sprite_replace(char_id, asset_id, x, 0, 0);
        else
            layer_sprite_show(char_id, asset_id, x, 0, 0);
    } else {
        layer_sprite_face(char_id, asset_id, x, 0, 0);
    }
}
```

问题：调用者需要在3个sprite函数中选择，且`layer_sprite_show()`内部可能递归调用`layer_sprite_replace()`。

### 1.2 状态查询分散在8+个调用位置

| 调用位置 | 查询函数 | 用途 |
|---------|---------|------|
| nb_anim.c:216 | `layer_dialog_drawn()` | 动画帧裁剪判断 |
| nb_anim.c:164 | `layer_dialog_drawn()` | 动画帧后重建对话区 |
| nb_commands.c:172 | `layer_dialog_drawn()` | 换背景时条件capture |
| nb_commands.c:226 | `layer_has_sprite()` | 立绘操作路径选择 |
| nb_commands.c:229 | `layer_has_sprite()` | 再次查询（重复） |
| nb_dialog.c:55 | `layer_dialog_drawn()` | 对话框打开路径选择 |
| nb_question.c:99 | `layer_dialog_drawn()` | 问题对话框打开路径选择 |
| layer_sprite.c:94 | `layer_dialog_drawn()` | 立绘show/replace选择 |
| layer_sprite.c:146 | `layer_dialog_drawn()` | 立绘face/replace选择 |
| layer_sprite.c:226 | `layer_dialog_drawn()` | 立绘replace/show选择 |

每个调用点都是一个潜在的出错位置。

### 1.3 重复的操作模式

以下模式在代码中反复出现：

**模式A：对话框显示三连**
```c
if (!layer_dialog_drawn()) layer_dialog_open(); else layer_dialog_snap();
layer_dialog_restore();
```
出现位置：nb_dialog.c:55-60, nb_question.c:99-102

**模式B：光标擦除+绘制+标记脏**
```c
hal_mouse_invalidate_cursor();
/* ... 绘制操作 ... */
layer_dialog_mark_dirty();
```
出现位置：layer_sprite.c:92+120, layer_sprite.c:139+154, layer_sprite.c:224+255, layer_sprite.c:285+306

**模式C：背景恢复+重绘立绘**
```c
layer_bg_restore_rect(...);
layer_redraw_sprites();
```
出现位置：layer_dialog.c:178-179, layer_sprite.c:304

---

## 二、方案：统一入口函数封装状态逻辑

### 2.1 核心思路

为每个重复模式创建统一的入口函数，封装状态判断逻辑。调用者只需调用一个函数，不需要了解内部状态机。

### 2.2 新增统一入口函数

#### A. `layer_bg_change(MagImage *img)` — 换背景

封装 `cmd_bg()` 的7步仪式：

```c
/* 统一的换背景操作
 * 1. 写入背景到VRAM
 * 2. 如果对话框未打开，捕获对话区背景
 * 3. 重绘所有立绘
 * 4. 同步调色板
 * 5. 拍快照（隐式清除对话框状态）
 * 前置条件：img 已解码，调色板已设置
 * 后置条件：bg_snapshot 更新，对话框状态清除
 */
void layer_bg_change(MagImage *img);
```

**实现逻辑**：

```c
void layer_bg_change(MagImage *img) {
    if (!img) return;

    vram_blit(img, 0, 0);

    if (!layer_dialog_drawn())
        layer_capture_bg_dialog();

    layer_redraw_sprites();
    dlg_update_palette();
    btn_update_palette();
    layer_capture_bg();
}
```

#### B. `layer_sprite_update(int id, int asset, int x, int y, int mirror)` — 更新立绘

封装 `cmd_char()` 的状态判断逻辑：

```c
/* 统一的立绘更新操作
 * 内部根据当前状态自动选择：
 *   - 首次显示 → layer_sprite_show()
 *   - 已存在 → layer_sprite_replace()（body）或 layer_sprite_face()（face）
 *   - 对话框打开时自动裁剪到 y<LAYER_DIALOG_Y
 * 前置条件：asset 已在 IMAGE.DAT 中
 * 后置条件：立绘显示在指定位置
 */
void layer_sprite_update(int sprite_id, int asset_id, int x, int y, int mirror);
```

**实现逻辑**：

```c
void layer_sprite_update(int sprite_id, int asset_id, int x, int y, int mirror) {
    int exists = layer_has_sprite(sprite_id);

    /* 第一次显示：使用 show */
    if (!exists) {
        layer_sprite_show(sprite_id, asset_id, x, y, mirror);
        return;
    }

    /* 已存在：使用 replace（会自动处理对话框状态） */
    layer_sprite_replace(sprite_id, asset_id, x, y, mirror);
}
```

#### C. `layer_dialog_show()` — 显示对话框

封装 `dialog_show()` 的三连模式：

```c
/* 统一的对话框显示操作
 * 内部根据当前状态自动选择：
 *   - 首次打开 → layer_dialog_open()
 *   - 已打开 → layer_dialog_snap()
 * 前置条件：无
 * 后置条件：对话框显示在屏幕上
 */
void layer_dialog_show(void);
```

**实现逻辑**：

```c
void layer_dialog_show(void) {
    if (!layer_dialog_drawn())
        layer_dialog_open();
    else
        layer_dialog_snap();
    layer_dialog_restore();
}
```

#### D. `layer_dialog_hide_clean()` — 隐藏对话框并恢复背景

封装 `layer_dialog_hide()` 的完整恢复逻辑：

```c
/* 统一的对话框隐藏操作
 * 1. 从 bg_dialog_snapshot 恢复对话区背景
 * 2. 重绘立绘（如果被对话框覆盖）
 * 3. 清除对话框状态
 * 前置条件：对话框当前打开
 * 后置条件：对话区恢复为原始背景
 */
void layer_dialog_hide_clean(void);
```

**实现逻辑**：

```c
void layer_dialog_hide_clean(void) {
    if (!layer_dialog_drawn())
        return;

    layer_dialog_hide();
    layer_redraw_sprites();  /* 立绘可能被对话框覆盖，需要重绘 */
}
```

#### E. `layer_sprite_hide(int id)` — 隐藏单个立绘

封装 `layer_sprite_hide_all()` 的单个立绘隐藏逻辑：

```c
/* 统一的单个立绘隐藏操作
 * 1. 从 bg_snapshot 恢复立绘下方背景
 * 2. 如果是最后一个立绘，重建对话区背景
 * 3. 标记对话框脏（需要重新拍快照）
 * 前置条件：立绘 id 存在
 * 后置条件：立绘消失，背景恢复
 */
void layer_sprite_hide(int id);
```

**实现逻辑**：

```c
void layer_sprite_hide(int id) {
    SpriteEntry *se;
    int i, has_any;

    if (!layer_has_sprite(id))
        return;

    se = &g_sprites[id];
    /* 恢复立绘下方背景 */
    layer_bg_restore_rect(se->x, se->y, se->w, se->h, 0);
    se->active = 0;

    /* 检查是否还有其他立绘 */
    has_any = layer_has_any_sprite();
    if (!has_any) {
        /* 最后一个立绘：重建对话区背景 */
        layer_bg_restore_rect(0, 0, 640, LAYER_DIALOG_Y, 0);
        layer_capture_bg_dialog_from_bg();
    }

    layer_dialog_mark_dirty();
    layer_set_active(LAYER_Z_SPRITE, has_any);
}
```

### 2.3 改动后的调用者代码

#### cmd_bg() 改动前后对比

**改动前（nb_commands.c:141-179）**：

```c
void cmd_bg(int argc, const char **argv, const char *cmd_name) {
    ...
    vram_blit(img, 0, 0);
    if (!layer_dialog_drawn())
        layer_capture_bg_dialog();
    layer_redraw_sprites();
    mag_release(img);
    dlg_update_palette();
    btn_update_palette();
    layer_capture_bg();
    ...
}
```

**改动后**：

```c
void cmd_bg(int argc, const char **argv, const char *cmd_name) {
    ...
    layer_bg_change(img);    /* 一行替代7行 */
    mag_release(img);
    ...
}
```

#### dialog_show() 改动前后对比

**改动前（nb_dialog.c:55-60）**：

```c
static void dialog_show(void) {
    if (!layer_dialog_drawn()) {
        layer_dialog_open();
    } else {
        layer_dialog_snap();
    }
    layer_dialog_restore();
}
```

**改动后**：

```c
static void dialog_show(void) {
    layer_dialog_show();    /* 一行替代5行 */
}
```

#### cmd_char() 改动前后对比

**改动前（nb_commands.c:226-239）**：

```c
void cmd_char(int argc, const char **argv, const char *cmd_name) {
    ...
    type = layer_has_sprite(char_id) ? "face" : "body";
    if (strcmp(type, "body") == 0) {
        if (layer_has_sprite(char_id))
            layer_sprite_replace(char_id, asset_id, x, 0, 0);
        else
            layer_sprite_show(char_id, asset_id, x, 0, 0);
    } else {
        layer_sprite_face(char_id, asset_id, x, 0, 0);
    }
}
```

**改动后**：

```c
void cmd_char(int argc, const char **argv, const char *cmd_name) {
    ...
    layer_sprite_update(char_id, asset_id, x, 0, 0);    /* 一行替代8行 */
}
```

---

## 三、改动清单

### A. `scene_layers.h` — 新增统一入口函数声明

```c
/* 统一入口函数（封装状态判断逻辑） */
void layer_bg_change(MagImage *img);
void layer_sprite_update(int sprite_id, int asset_id, int x, int y, int mirror);
void layer_dialog_show(void);
void layer_dialog_hide_clean(void);
void layer_sprite_hide(int id);
```

### B. `layer_bg.c` — 实现 layer_bg_change()

```c
void layer_bg_change(MagImage *img) {
    if (!img) return;
    vram_blit(img, 0, 0);
    if (!layer_dialog_drawn())
        layer_capture_bg_dialog();
    layer_redraw_sprites();
    dlg_update_palette();
    btn_update_palette();
    layer_capture_bg();
}
```

### C. `layer_sprite.c` — 实现 layer_sprite_update() 和 layer_sprite_hide()

```c
void layer_sprite_update(int sprite_id, int asset_id, int x, int y, int mirror) {
    if (!layer_has_sprite(sprite_id)) {
        layer_sprite_show(sprite_id, asset_id, x, y, mirror);
    } else {
        layer_sprite_replace(sprite_id, asset_id, x, y, mirror);
    }
}

void layer_sprite_hide(int id) {
    SpriteEntry *se;
    int has_any;

    if (!layer_has_sprite(id))
        return;

    se = &g_sprites[id];
    layer_bg_restore_rect(se->x, se->y, se->w, se->h, 0);
    se->active = 0;

    has_any = layer_has_any_sprite();
    if (!has_any) {
        layer_bg_restore_rect(0, 0, 640, LAYER_DIALOG_Y, 0);
        layer_capture_bg_dialog_from_bg();
    }

    layer_dialog_mark_dirty();
    layer_set_active(LAYER_Z_SPRITE, has_any);
}
```

### D. `layer_dialog.c` — 实现 layer_dialog_show() 和 layer_dialog_hide_clean()

```c
void layer_dialog_show(void) {
    if (!layer_dialog_drawn())
        layer_dialog_open();
    else
        layer_dialog_snap();
    layer_dialog_restore();
}

void layer_dialog_hide_clean(void) {
    if (!layer_dialog_drawn())
        return;
    layer_dialog_hide();
    layer_redraw_sprites();
}
```

### E. `nb_commands.c` — 重构 cmd_bg()

```c
void cmd_bg(int argc, const char **argv, const char *cmd_name) {
    ...
    /* 改动前：7行手动操作 */
    /* 改动后：1行统一入口 */
    layer_bg_change(img);
    mag_release(img);
    ...
}
```

### F. `nb_commands.c` — 重构 cmd_char()

```c
void cmd_char(int argc, const char **argv, const char *cmd_name) {
    ...
    /* 改动前：8行状态判断 */
    /* 改动后：1行统一入口 */
    layer_sprite_update(char_id, asset_id, x, 0, 0);
    ...
}
```

### G. `nb_dialog.c` — 重构 dialog_show()

```c
static void dialog_show(void) {
    /* 改动前：5行状态判断 */
    /* 改动后：1行统一入口 */
    layer_dialog_show();
}
```

### H. `nb_question.c` — 重构 cmd_question()

```c
void cmd_question(int argc, const char **argv, const char *cmd_name) {
    ...
    /* 改动前：4行状态判断 */
    /* 改动后：1行统一入口 */
    layer_dialog_show();
    ...
}
```

---

## 四、代码量变化

| 项目 | 行数 |
|------|------|
| **新增统一入口函数** | +80行（5个函数实现） |
| **新增函数声明** | +10行（scene_layers.h） |
| **重构 cmd_bg()** | -6行（7行→1行） |
| **重构 cmd_char()** | -7行（8行→1行） |
| **重构 dialog_show()** | -4行（5行→1行） |
| **重构 cmd_question()** | -3行（4行→1行） |
| **净变化** | +70行 |

虽然净增70行，但调用者代码从"理解状态机"变为"调用一个函数"，开发难度大幅降低。

---

## 五、行为矩阵

| 操作 | 触发条件 | 内部执行 | 调用者感知 |
|------|---------|---------|-----------|
| `layer_bg_change(img)` | 换背景 | vram_blit + 条件capture + redraw_sprites + palette + capture_bg | 一行调用 |
| `layer_sprite_update(id,asset,x,y,mirror)` | 显示/更新立绘 | show 或 replace（自动判断） | 一行调用 |
| `layer_dialog_show()` | 显示对话框 | open 或 snap + restore（自动判断） | 一行调用 |
| `layer_dialog_hide_clean()` | 隐藏对话框 | hide + redraw_sprites | 一行调用 |
| `layer_sprite_hide(id)` | 隐藏立绘 | restore_bg + rebuild_dialog + mark_dirty | 一行调用 |

---

## 六、验证计划

### 6.1 编译验证

```bash
make -C core 2>&1 | grep -iE 'error|warning'
```

### 6.2 功能验证

1. **换背景**：`cmd_bg()` 调用 `layer_bg_change()` 后，验证：
   - 背景正确显示
   - 立绘正确重绘
   - 对话框状态正确（如果有）

2. **立绘更新**：`cmd_char()` 调用 `layer_sprite_update()` 后，验证：
   - 首次显示：立绘出现
   - 再次调用：立绘替换
   - 对话框打开时：立绘裁剪到y<280

3. **对话框显示**：`dialog_show()` 调用 `layer_dialog_show()` 后，验证：
   - 首次打开：对话框出现
   - 再次调用：对话框快照更新

4. **对话框隐藏**：调用 `layer_dialog_hide_clean()` 后，验证：
   - 对话框消失
   - 背景恢复
   - 立绘重绘

### 6.3 回归验证

```bash
make -C core && tools/env_setup/venv/bin/python -m pytest tools/tests/
```

### 6.4 运行时验证（NP2kai）

1. 完整游戏流程测试：
   - 换背景 → 显示立绘 → 打开对话框 → 输入文字 → 隐藏对话框
   - 动画播放 + 对话框并发
   - 存档/读档

2. 边界情况测试：
   - 快速连续换背景
   - 立绘快速显示/隐藏
   - 对话框快速打开/关闭

---

## 七、版本变更

- 版本号：0.2.063 → 0.2.064
- 新增文件：无
- 修改文件：
  - `core/engine/scene_layers.h`（+10行：统一入口函数声明）
  - `core/engine/layer_bg.c`（+15行：layer_bg_change 实现）
  - `core/engine/layer_sprite.c`（+30行：layer_sprite_update + layer_sprite_hide 实现）
  - `core/engine/layer_dialog.c`（+15行：layer_dialog_show + layer_dialog_hide_clean 实现）
  - `core/engine/nb_commands.c`（-13行：重构 cmd_bg + cmd_char）
  - `core/engine/nb_dialog.c`（-4行：重构 dialog_show）
  - `core/engine/nb_question.c`（-3行：重构 cmd_question）
- 无头文件依赖变更

---

## 八、后续文档

本方案为以下文档提供基础：
- **devdoc 86**：可视化调试工具（基于统一API导出层状态）
- **防复发规则更新**：建议添加 C26 "调用者不得直接查询层状态后选择操作路径，应使用统一入口函数"
