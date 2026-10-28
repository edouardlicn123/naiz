# 182 — hideall 批量重组：一次 sync 替代逐个 sync

> **状态**：**已实施**——2026-10-28
> **创建于**：2026-10-28
> **承接**：`devdocs/180`（Naiz Queue 中段预载）、`devdocs/181`（对话框净底缓存——本篇修其验证后用户仍感知的 `char(hideall)` 明显暂停）
> **影响**：`core/engine/layer_sprite.c`（`layer_sprite_hide_all` 批量重构 + 删除单 sprite helper）、`tools/tests/test_sprite_hideall_batch.py`（新增 1 契约）

---

## 一、问题定义

用户实测：**001 脚本的 `char(hideall)` 执行时有明显暂停**（对话框开着时最显著）。

### 1.1 根因：每个立绘各付一次全管线

[layer_sprite.c](file:///home/edo/naiz/core/engine/layer_sprite.c) 旧实现：

```c
for (i = 0; i < LAYER_MAX_SPRITES; i++)
    if (sprite_table[i].active)
        layer_sprite_hide(sprite_table[i].id);   /* 每个 hide 一次 sync */
```

而 `layer_sprite_sync_dialog_base()` 一次的成本是：

| 步骤 | 成本 |
|---|---|
| `dialog_occluder_reset_base()` | 55KB memcpy + **置脏净底缓存**（181） |
| 逐活跃立绘 `image_load` + occluder 叠画 | 缓存命中 + 逐像素 |
| `layer_dialog_recompose()` | 净底缓存**重建**（55,200 逐像素循环，因刚被置脏）+ 页文本 + 55KB 一次性 memcpy + **55KB VRAM 写** |

N 个立绘的 hideall = **N 套上述管线在一帧内**（N=2-3 时 ~150-300ms）——即"明显暂停"。逐个 hide 的中间态从未被呈现过（frame pump 每帧才呈现一次），逐次 sync 是纯浪费。

## 二、修复

`layer_sprite_hide_all()` 批量化：先把每个活跃立绘的背景矩形还原并置 `active = 0`（N 次小 VRAM 写，语义必需），随后**只调一次** `layer_sprite_sync_dialog_base()`（occluder 重置 + 零个残留立绘叠画 + 一次重组）。最终像素与逐个 hide 完全一致，管线从 N 次收敛到 1 次。

- 无立绘时（`hidden == 0`）整条 sync 跳过（与旧行为一致）
- 静态 helper `layer_sprite_hide(id)` 唯一调用者就是 hideall，已删除；**未来任何 hide-by-id 入口必须同样批量**（测试守卫钉死）
- `layer.c:33` 场景重置路径的 hideall 同样受益

## 三、验证

- `python3 -m pytest tools/tests/`：859 通过（851 基线 + 180 篇 4 条 + 181 篇 2 条 + 本篇 1 条），14 失败均为既有类别
  - `test_hideall_syncs_the_dialog_base_once`：hide_all 内 `sync_dialog_base` 必须恰好 1 次、空场必须跳过、单 sprite helper 必须保持删除
- `bash core/build.sh` 零诊断；`makegame.sh make demo-a2` 重打 HDI；NP2kai 无头冒烟干净退出（`NB OK` / `End` / `VE:0`）
- 实机观感待用户确认：001 的 hideall 应从"明显暂停"降到一帧内的 1 套管线（~30-50ms，1-3 掉帧）

## 四、遗留

- hideall 帧的残余成本 = N 次背景矩形还原 + 1 次 occluder 重建 + 1 次重组 blit（R20 语义必需），无进一步压缩空间
- 若脚本在 hideall 后紧跟 `bg(){x}` 切场景，两帧的重组/还原仍各自发生（语义正确，不动）
