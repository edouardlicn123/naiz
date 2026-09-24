# 111-光标移动残影根治：splice 只进一次性书写副本

> 状态：**已落地**（0.2.138）
>
> 所属：软件光标层（cursor.c / cursor.h / layer_dialog.c）
> 上游：devdoc 110（对话框合成缓冲预拼光标）；本 doc 为其 **splice 自我污染（持久缓冲烘烙）** 的根治补充。

## 1. 问题与复现

0.2.137 落地后用户反馈：

> 「暂时不闪烁了，但鼠标移动有残影。」

即 c20 的零缺窗方案生效后，缺窗（闪烁/消失）消失，但出现**新症状**：鼠标在对话框上移动，旧位置的箭头像素持续残留（幽灵箭头/拖影）。

## 2. 根因（splice 把活箭头烘进了跨 pass 持久缓冲）

c20 的 `cursor_composite_splice` 把箭头**就地混进** `dialog_layer`（跨 pass 持久合成缓冲，内含 480×115 对话框正文快照）。问题出在**持久化** + dither 对话框样式两件事叠加：

1. **持久缓冲**：`dialog_layer` 并非每 pass 重建——它保存「上一次合成对话框」的完整内容，后续 blit 直接把它写回 VRAM。而 splice 只负责「下次正文变化前临时拼一次箭头」，箭头被当作正文的一部分烙进缓冲。
2. **dither 孔位保留旧内容**：demo-a2 使用 `dlgstyle=5`（dither 样式）。`dialog_paint_box` 画底时 dither 孔位**跳过写入**（保留缓冲既有像素）。于是既有像素（上一 pass 烘进去的箭头）在部分重绘后**原样残留**。
3. **不清底路径**：`layer_dialog_clear()` / `layer_dialog_show()` 等走 `layer_dialog_recompose` 的路径**不做** `dialog_seed_base()` 全幅重绘；blit 不经 paint_box 时旧箭头像素就一直留在持久缓冲里并被写回 VRAM。

于是一个移动后的旧箭头像素既被 blit 写回 VRAM（残影本体），又被**下次 splice 的 `memcpy` 采为 `cursor_saved.buf`**（残影基准）——splice 把「含箭头的缓冲」当作防残影背景存下来，等于把自我的污染永久化（C18 快路径副作用核对缺失：splice 的 memcpy 必须只取「无箭头」内容，本实现违反）。

devdoc 110 只规定「透明/部分缓冲禁止 splice」，把「活箭头烘进持久背景 → 108 残影」堵在部分缓冲这一类；但**不透明 + dither 洞**的持久缓冲同样自污染，属于漏网。

## 3. 方案（箭头只进一次性书写副本）

持久合成缓冲 `dialog_layer` **永不写箭头**；箭头只进每 blit 的一次性主存副本 `dialog_blit_tmp`：

```
typedef struct {
    ...
} LayerSnapshot;                       // layer_snapshot_alloc_dialog 管理的 RAM buffer

static unsigned char *dialog_blit_tmp = NULL;   // 一次性书写副本（主存，非持久）

dialog_layer_blit():
    dialog_seed_base()/touch_opaque(...);       // 原语义不变（跨边触摸 erase）
    if (dialog_blit_tmp == NULL)                // OOM 降级：退回不预拼直写
        vram_write(dialog_layer, LAYER_DIALOG_X, LAYER_DIALOG_Y, ...);
    else {
        memcpy(dialog_blit_tmp, dialog_layer, LAYER_DIALOG_W * LAYER_DIALOG_H);
        cursor_composite_splice(dialog_blit_tmp, LAYER_DIALOG_W,
                                LAYER_DIALOG_X, LAYER_DIALOG_Y, ...);  // 箭头只进 tmp
        vram_write(dialog_blit_tmp, LAYER_DIALOG_X, LAYER_DIALOG_Y, ...);
    }

layer_dialog_show() 首次分配块:
    ...
    dialog_blit_tmp = layer_snapshot_alloc_dialog("dialog_blit_tmp");  // 与既有块同生命周期

layer_dialog_reset():
    ...
    dialog_blit_tmp = free 并置 NULL;
```

要点：

- **顺序**保持 `touch_opaque → splice → vram_write` 三段式（0.2.137 契约），splice 命中条件、混合模型、`valid` 置位不变。
- **无 vblank、无额外 VRAM 流量**；额外成本仅一次 `W*H`(=480×115=55200 B) RAM `memcpy` 每 blit。
- 持久 `dialog_layer` 不再被 splice 写脏 → 移动残影无源；splice 的 `cursor_saved.buf` 采样自 tmp（无箭头的 fresh 副本）→ 防残影基准干净。
- dither/部分重绘/不清底路径全部免疫，因为坑里**再也不会有箭头可残留**。

## 4. 守卫测试

`tools/tests/test_cursor_layer.py`（+1 例 = 443）：

- 新增 `test_dialog_blit_tmp_buffers_arrow_away_from_persistent_composite`：`dialog_layer_blit` 体内**不出现** `cursor_composite_splice(dialog_layer`（不许再对持久缓冲 splice）；`memcpy(dialog_blit_tmp, ...)` 位于 splice 之前；`dialog_blit_tmp` 的分配出现在 `layer_dialog_show`、释放出现在 `layer_dialog_reset`。
- 更新 `test_dialog_layer_blit_splices_before_vram_write`：splice 目标改为 `dialog_blit_tmp`，且仍位于 touch 与 `vram_write` 之间。

## 5. 验证

- `make -C core`：0 err / 0 warn（engine.exe + engine_a.exe 双变体均含改动）。
- pytest：**443 passed**（442 → 443）。
- `./start.sh fullaudit`：7/7 全绿（`logs/fullaudit_20260922_113636.log`）。
- **AUTOEXIT 无头回归**：`makegame.sh test demo-a2 --auto --serial` 串口至 `End` + `VE:0..5` 收尾（设置菜单用键盘 Enter 启动，绝对鼠标口在该环境不可用；详见 devdoc 108 §方法）；回归后 `build/make` 复原正常引擎入 HDI，`games/demo-a2/engine.exe` md5 == `core/engine.exe`。
- 真机鼠标目检（移动无残影、揭示零缺窗）留人工复核。