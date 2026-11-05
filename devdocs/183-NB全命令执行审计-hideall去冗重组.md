# 183 — NB 全命令执行路径审计 + hideall 去冗重组

> **状态**：**已实施**——2026-10-28
> **创建于**：2026-10-28
> **承接**：`devdocs/177`（Naiz Queue）、`devdocs/180`（中段预载入队）、`devdocs/181`（净底缓存）、`devdocs/182`（hideall 批量）、`devdocs/173`（显示命令逐帧 yield）
> **影响**：`core/engine/layer_sprite.c` + `scene_layers.h`（`layer_sprite_hide_all_ex`）、`core/engine/nb_commands.c`（hideall 走 ex(0)）、`tools/tests/test_sprite_hideall_batch.py`（+1 契约）

---

## 一、审计范围与方法

对 [cmd_table](file:///home/edo/naiz/core/engine/nb_commands.c#L471-L498) 全部 24 条 NB 命令的执行体逐条核对，成本模型沿用本系列：

- **同步 I/O**（磁盘读/解码 30-50ms）——白名单守卫已在位
- **一帧内批量重活**（逐个 sync / 重复全管线）
- **被同帧后续写覆盖的冗余工作**
- **可见帧大块 VRAM 写**（R20 语义下限除外）

结构性前提：`devdoc 173` 让每条 CMD_TOUCHES_DISPLAY 命令独占一帧（dispatch 后 yield），所以"多条显示命令挤一帧"已不可能；阻断类命令自持输入循环。

## 二、逐命令判定

| 命令 | 执行体 | 判定 |
|---|---|---|
| `bg` | `display_apply_bg` → bg 解码（177 队列/lookahead 预载）+ 全屏写 + 立绘还原/重blit + **一次** occluder 重置 + 一次重组 | ✓ 语义必需，各一次 |
| `cg` | 同 bg 路径 + `sys_save_unlock_cg`（SYSTEM.SAV 小文件写，~5-20ms） | ✓ 可接受；解锁先于绘制（断电安全设计） |
| `cg(hidedialog)` | `layer_dialog_hide`（整框还原 + 重blit 残留立绘） | ✓ 立绘仍活跃，重blit 必需 |
| `char`（show/face/replace） | 一次还原 + 一次 blit + 一次 sync（182 后语义不变） | ✓ |
| `char(hideall)` | 见 §三 | **已修**（ex(0)） |
| `scene` | 场景切换：过渡幕遮盖 + Naiz Queue 预载 + 脚本常驻读 | ✓（177） |
| `sceneconf` / `var` / `delay` | 纯内存 | ✓ |
| `bgm` | 首条预载（177 D6）；中段切换回退读档 1-2 帧 | 已知遗留（180 §四 #2），用户可感知再立项 |
| `sound` / `voice` | `pcm_play` 同步小样本读 | 已知遗留（177 §9.3），1 帧内 |
| `fei/ira/neon`（dialogue） | `nb_dialog_pending` 分支：翻页帧 = 181 净底 memcpy + 文本 + blit | ✓（181 后已最轻） |
| `playanima` | ANI 容器经 `image_raw_blob`（一次同步读，raw-blob 槽缓存）+ 逐帧解码自常驻内存（设计使然）+ `anim_stop_internal` | ✓ |
| `waitanima` | 停车 | ✓ |
| `stopanima` | 帧释放 + 层去激活 | ✓ |
| `mainmenu` / `startsetting` / `question` / `settingmenu` / `specialmenu` / `cgvmenu` / `loadscene` | 自持输入循环的 UI 屏 | ✓ 交互触发；缩略图批量解码为已判定可接受项（180 §四 #3/#4） |
| `musicmenu` | 空实现（flags=0 一致） | ✓ |
| `host` | `display_apply_dialog` 一次性屏显 | ✓（181 缓存覆盖） |

## 三、本次修复：char(hideall) 的被覆盖重组

`cmd_char(hideall)` 的序列是：

```c
layer_sprite_hide_all();   /* 含一次 occluder 重置 + 重组 + 2×55KB blit */
layer_dialog_hide();       /* 整框从净底还原（55KB VRAM 写）—— 立刻覆盖重组结果 */
nb_dialog_reset();
```

重组结果在**同一帧内被整框还原覆盖**，整条 sync 管线是纯浪费（~20-40ms）。修复：

- 新增 [layer_sprite_hide_all_ex(recompose)](file:///home/edo/naiz/core/engine/layer_sprite.c#L301-L316)：`recompose=0` 跳过最后一次 sync；`layer_sprite_hide_all()` 保持 ex(1)（场景重置路径不变）
- `cmd_char(hideall)` 改走 `ex(0)` 再 `layer_dialog_hide()`——此时立绘已全部去激活，hide 内部的 redraw/sync 自然空转
- **hideall 帧最终成本**：N 次立绘矩形还原 + 1 次整框还原，无 occluder、无重组、无中间 blit——不可再压缩

## 四、验证

- `python3 -m pytest tools/tests/`：860 通过（851 基线 + 180/181/182/183 篇新增契约），14 失败均为既有类别
- `bash core/build.sh` 零诊断；HDI 重打；NP2kai 无头冒烟干净退出
- 实机确认点：001 的 `char(hideall)` 应在对话框开着时也不再可感知暂停

## 五、结论

全 24 条命令的执行路径均已核对：**除已登记遗留（中段 bgm 切换、SE/语音读）外，无新的同帧批量/冗余面**。本类问题的拦截网现为三层：`test_sync_decode_allowlist`（新阻塞点）、`test_cmd_meta`（显示/非显示边界）、`test_sprite_hideall_batch` / `test_dialog_box_cache` / `test_naiz_queue`（已修行为回归）。
