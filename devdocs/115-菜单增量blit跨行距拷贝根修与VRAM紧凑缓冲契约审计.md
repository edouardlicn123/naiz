# 115-菜单增量 blit 跨行距拷贝根修与 VRAM 紧凑缓冲契约审计

> 状态：**已落地**（0.2.142）
>
> 所属：VRAM 块拷贝契约（render_vram.c / render_internal.h）+ 菜单层增量发布（menu_layer.c / nb_menu.c）+ 软件光标 splice（cursor.c / layer_dialog.c）
> 上游：devdoc 114 反馈轮（special 菜单返回主菜单后 continue/start 两键花屏）；devdoc 108–112（软件光标层 / splice 预拼）

## 1. 背景与症状

NP2kai 目检：从 special 菜单返回主菜单后，**左列上两个按键 continue（400,208）与 start（400,252）花屏**——外观为杂点 / 横线乱码，程序仍在运行。

冷启动首轮主菜单未复现：用户首轮只用鼠标点击（`menu_show` 的鼠标路径不触发增量标签重绘），返回后按了一次方向键才暴露。**该 bug 与 special 无因果，只要在主菜单（或设置菜单）按任意方向键即花**；「恰好两键」= 一次 ↓（sel 0→2，键盘分支重绘 label 0 与 label 2）。

## 2. 根因一：`menu_layer_blit_rect` 把 composite 切片当紧凑缓冲（唯一实测 bug）

`vram_read()` / `vram_write()`（render_vram.c）的文档化契约 = **缓冲区行距必须等于参数 `w`**（紧凑 `w×h` 矩形缓冲；`skip_x/skip_y` 仅在 clip 时非零）。违反者会把底下的行错位进来。

`menu_layer_blit_rect`（menu_layer.c:139）不透明分支传的是 **640 行距 composite 的切片**，而函数内以 `orig_w = w`（按钮宽 100）作行距：

```c
vram_write(menu_layer_buf + by * menu_layer_w + bx, x, y, w, h);
/* vram_write 内行源 = buf + py*orig_w = buf + py*100，真实行距却是 640 */
```

→ 发布矩形第 0 行正确、第 1..h-1 行全部错位（读到 composite 前部行的字节）→ 键面横向乱码。

**触发面**：唯一调用方 `menu_label_draw`（nb_menu.c:220），`menu_show` 类菜单（主菜单 / 设置）键盘焦点移动时逐键增量发布。special / LOAD / CG 画廊均只走全量 `menu_layer_blit()`，不受影响。

### 修复（menu_layer.c）

`vram_write` 契约对 `h==1` 无行距要求（源只取行首）→ 逐行发布：

```c
else {
    int i;
    /* vram_write 契约 = 紧凑缓冲（行距 == 参数 w）；640 行距的 composite
     * 切片不能一次整块发布，逐行（h==1）写回，每行源都在行首。 */
    for (i = 0; i < h; i++)
        vram_write(menu_layer_buf + (by + i) * menu_layer_w + bx,
                   x, y + i, w, 1);
}
```

透明分支（menu_layer.c:135）已走显式 stride 的 `render_blit_transparent`，正确，不动。

## 3. 根因二：`cursor_composite_splice` 跨行距 memcpy（同族潜患）

devdoc 110/111 的光标 splice（cursor.c:311-352）：把光标盒合成进**一次性书写副本**时，保存盒下背景用了一块连续 memcpy：

```c
memcpy(cursor_saved.buf, buf + oy * stride + ox,
       CURSOR_SAVED_W * CURSOR_SAVED_H);   /* 24×24 = 576 连续字节 */
```

源行距 `stride`（对话框合成 = 480），盒宽 24；576 > 480 必然跨过 `ox` 补足后撞进下一行尾/再下一行头——保存的「盒下背景」是**斜纹**而非 24×24 矩形。

**触发**：光标盒完整落在对话框矩形内（鼠标移入叙述框，`cursor_composite_splice` 返回 1）的每次 splice 都写坏 `cursor_saved.buf`；随后光标移出时 `cursor_erase`（cursor.c:159）用损坏背景擦除旧盒 → 框内留斜纹残影；叙述文本已静止（不再逐帧重发合成）时残影持续到下次文本推进。

> 常态非 splice 路径（cursor.c:144/159）是 24×24 紧凑缓冲经 `vram_read/write`（stride==w==24）读写，正确，不在此 bug 内。

### 修复（cursor.c）

保持盒语义，逐行拷贝：

```c
{
    int r;
    for (r = 0; r < CURSOR_SAVED_H; r++)
        memcpy(cursor_saved.buf + r * CURSOR_SAVED_W,
               buf + (oy + r) * stride + ox, CURSOR_SAVED_W);
}
```

## 4. 同族全量审计（「还有没有类似的潜在问题」）

以「跨行距拷贝 / 紧凑缓冲契约」为扫描面，全代码库 `vram_read` / `vram_write` 九处调用方 + 其余行拷贝逐条核对：

| 调用点 | 缓冲 | 行距 vs w | 结论 |
|------|------|----------|------|
| cursor.c:41/144/159 光标快照与擦除 | 24×24 `CursorBg.buf` | 24 == 24 | ✓ |
| cursor.c:369 光标刷新快照 | 24×24 | 24 == 24 | ✓ |
| layer_dialog.c:259/265/384 对话框合成/还原 | 480×115 紧凑 | 480 == 480 | ✓ |
| layer_dialog.c:333+ splice 保存背景 | 480 stride × 24×24 盒 | **576 连续 ≠ 480** | ✗（已修，§3） |
| layer_bg.c 快照（bg_snapshot / under_dialog） | 640 / 480 紧凑 | 行距各自 == 宽 | ✓ |
| layer_sprite.c:234 校验单行读 | h==1 | 无行距要求 | ✓ |
| menu_layer.c:71 open 底座快照 | w×h 全屏 640 | w == 640 | ✓ |
| menu_layer.c:115 全量 blit | 640×400 composite | w == 640 | ✓ |
| menu_layer.c:139 blit_rect（不透明） | **640 切片 × 矩形 w** | **w≠640** | ✗（已修，§2） |
| menu_layer.c:139 blit_rect（透明） | 显式 stride 参数 | ✓ | ✓ |
| menu_layer.c:191 close(1) 底座还原 | 640×400 全宽 | w == 640 | ✓ |
| layer_debug.c:123/165 全幅读取 | 640×400 | w == 640 | ✓ |
| layer_bg_restore_rect | 逐像素 `vram_pset` | 无行距依赖 | ✓ |
| menu_layer_erase_to_base | `(by+py)*640+bx` | 行距显式正确 | ✓ |

结论：仅 §2 / §3 两处需要动，其余全部符合紧凑缓冲契约。

## 5. 验证与记账

- `make -C core`：0 errors / 0 warnings。
- venv pytest（tools/tests，463 用例基线 + 增量）。
- `./start.sh fullaudit`：6 步全 `[✓]`。
- `./makegame.sh build demo-a2 && ./makegame.sh make demo-a2`：HDI 重建。
- NP2kai 目检三点：
  1. 主菜单按一次 ↓（sel 0→2）→ continue/start 不再花屏；
  2. special → 主菜单回路往返正常；
  3. 鼠标移入叙述框再移出 → 框内无斜纹残影。
- `bump_version` → 0.2.142（demo-a2/animatest 同步）；CHANGELOG 新锚点 `c25`；AGENTS.md 头部「当前版本」同步。