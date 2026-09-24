# 113-diff 增量写时代的对话框 overlay 残留：选项菜单强制整幅重发收口

> 状态：**已落地**
>
> 所属：软件光标层与对话框（layer_dialog.c / scene_layers.h / nb_question.c）
> 上游：devdoc 112（对话框增量写入）；本 doc 处理增量写暴露的 **对话框 rect 内临时 overlay 无主残留**。

## 1. 问题与复现

devdoc 112 的增量 diff 写落地后，yes/no 选项菜单出现新残留：

> 「yes 和 no 的选单选择 yes 后，no 的位置有文字残留。」

复现路径（demo-a2 的 `@q` 选项）：`question` 命令 → `layer_dialog_clear()` 发布干净框（`dialog_blit_prev` = 干净框）→ `draw_text` 问题 → `ui_interact()` 在内容区**直绘**选项按钮（emboss outline + label，VRAM overlay）→ 交互返回，**没有任何清除动作**。

## 2. 根因（overlay 依赖未来 diff 恰好覆盖 = 无主残留）

选项 UI 是对话框 rect 内的**临时 VRAM overlay**，对话框恢复此前靠「全幅写时代每次 blit 整框重绘覆盖一切」隐式完成。devdoc 112 改为 **diff 增量写**后：

- reveal 推进由 `dialog_layer_blit()` 的 diff 承担，以 `dialog_blit_prev`（干净框）为基准**只写真正变化的行**；
- yes 按钮行与正文首行重合 → 被 reveal 写覆盖；**no 按钮行在正文未到达区或与 composite 同字节 → 判「未变」跳过不写 → 永久残留**。

即：**任何「对话框 rect 内临时直绘、关闭后靠 blit 擦除」的 overlay，在增量写语义下都会因无主动清除而残留。** yes 与 no 命运不同的原因仅是行重叠差异。

## 3. 方案（强制整幅重发入口 + 交互返回收口）

在 devdoc 112 的基准失效位（`dialog_blit_baseline_valid`）之上新增**主动整幅发布入口**，让 overlay 关闭者显式复原对话框：

| 文件 | 改动 |
|------|------|
| `layer_dialog.c` / `scene_layers.h` | 新增 `void layer_dialog_blit_force(void)`：置 `dialog_blit_baseline_valid = 0` 后调 `dialog_layer_blit()` → 一帧整幅重发 composite，无条件覆盖框内一切 overlay。复用既有失效语义，不新增机制 |
| `nb_question.c` | `ui_interact()` 返回后（`sel` 无论选中/超时）调用：`menu_restore_item_palette();` → `layer_dialog_show();`（重画 box，复合缓冲内的 ui 像素清掉）→ `layer_dialog_blit_force();`（整幅重发，覆盖 no 等未命中行）→ `nb_set_last_choice()` / `apply_option()`。此后 reveal 继续走正常 diff（基准已重发） |

**说明**：
- 全幅写仅发生在选项关闭那一瞬（低频、非 reveal 热循环），代价可控；reveal 逐字路径不受影响。
- save 确认框是自绘路径，关闭时经 `render_page + blit`（正文 diff 天然覆盖确认区），暂无症状；若日后残留，同法并入 `blit_force`。
- 这是「对话框 rect 内临时 overlay」应遵循的契约：**打开直绘、关闭必须主动整幅复原**（凭靠未来 diff = 残留隐患）。

## 4. 验证

- 实机：选项菜单选 yes/no/超时后，按钮行无残留、对话框恢复原正文；回归 devdoc 112 全部症状（打字闪、移动闪、涂抹、整框完整）。
- `make -C core` 0 err / 0 warn；pytest 全绿；`./start.sh fullaudit` 7/7。
- AUTOEXIT 无头回归后复原干净 HDI（engine.exe md5 `3e501f92…`）。
- `bump_version` → 0.2.139。