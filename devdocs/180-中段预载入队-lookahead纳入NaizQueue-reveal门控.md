# 180 — 中段预载入队：lookahead 纳入 Naiz Queue + reveal 门控

> **状态**：**已实施**——2026-10-28
> **创建于**：2026-10-28
> **承接**：`devdocs/177`（Naiz Queue 统一执行模型——本篇补齐其遗留的中段同步解码面）、`devdocs/131`（立绘加载拖慢分析）
> **影响**：`core/engine/nb.c`（仅 `nb_prefetch_lookahead`）、`core/engine/frame.c`（仅 preload 消费门控）、`core/engine/preload_queue.h`（新增优先级档）、`tools/tests/test_naiz_queue.py`（+2 契约）

---

## 一、问题定义

177 落地后用户仍报告两类卡顿：

1. **文字载入卡顿** —— 翻页瞬间（新文本页刚显示）画面冻结一下
2. **大量立绘变更卡顿** —— 连续 `char` 换装/换表情时每帧都顿

### 1.1 根因：中段路径从未纳入 Naiz Queue

177 的预载只覆盖**场景切换窗口**（`nb_load()` → `nb_preload_scene()` → 过渡期 `preload_step()` 消费）。中段路径（§9.2 D1/D3 明确保留同步整图解码）残留两个阻塞点：

| 阻塞点 | 机制 | 落点 |
|---|---|---|
| **lookahead 批量解码** | `nb_prefetch_lookahead()` 在一帧内对 24 行窗口内所有未缓存 bg/cg/char 逐一调用 `image_prefetch()`（整图解码 30-50ms/张）。K 张 = K×30-50ms 一帧冻结 | 窗口只在 pc 前进时滑动——**恰是翻页后新文本页上屏的那一帧**（`nb_process` 对话分支 + main.c 主循环都调用它）。玩家感知：文字出现瞬间卡顿 |
| **变更帧同步 `image_load`** | `char` 命令 → `display_apply_sprite` → `layer_sprite_update` → `image_load`（缓存未命中 = 30-50ms 解码）+ blit + 对话框重组。未命中原因：窗口 24 行之外、32 slot 驱逐 | 每次立绘变更帧 |

已排除的嫌疑（文字路径无磁盘 IO）：字库常驻 `glyph_cache`（boot 一次），脚本常驻 `nb.buf`（场景切换一次读入），翻译常驻——"文字载入"卡顿的全部增量来自同帧的 lookahead 批量解码。

### 1.2 与 177 架构的关系

177 §2.2 的设计目标就是"资源排队预加载 + 消费均匀 drain"，但落地时（§9.1）只接了场景预载一个生产者。本篇把**中段 lookahead 作为第三个生产者**接入既有队列，零新机制。

## 二、修复

### 2.1 lookahead 入队（nb.c）

`nb_prefetch_lookahead()` 把 `image_prefetch((unsigned short)id)` 改为：

```c
preload_push(id, PRELOAD_PRIO_LOOKAHEAD);
```

- 新增最低优先级档 `PRELOAD_PRIO_LOOKAHEAD = 2`（场景自己的 BG/CHAR 优先消费；队列满时被挤掉的只有 lookahead job——滑窗自管理）
- 解码由既有 `engine_frame_pump()` 的 `preload_step()` 每帧均匀消费 1 个——批量同帧解码不复存在
- 顺带删除 nb.c 中已无引用的 `image_prefetch` 本地前向声明（image.h 仍声明，`preload_queue.c` 照常用）
- 命中已被同步解码的 id：`image_load()` 的 `preload_cancel(id)` 契约不变（image.c:170）

### 2.2 reveal 门控（frame.c）

打字机 reveal tick 每帧重绘整个对话框合成（box + 已显文本 + 55KB VRAM 写），帧预算本已紧张。若解码照常每帧消费一个，30-50ms 会把打字机帧挤成 2-3 掉帧——**比批量卡顿更频繁的抖动**。故消费端加门控：

```c
if (!nb_dialog_reveal_active()) {
    if (preload_step() && transition_active())
        preload_step();
}
```

- reveal 活动期：队列保持，解码让位
- reveal 结束后（玩家阅读静止画面）：每帧消费 1 个，单帧光标跳一下，阅读中不可感知
- 过渡期 reveal 不可能活动 → 177 的双消费（2/帧）原样保留
- AUTOEXIT 无头构建 reveal 恒关 → 冒烟行为不变
- 快速连点降级：队列未及排空时 `cmd_char` 回落同步 `image_load`（与改动前行为一致，不更差）

## 三、验证

- `python3 -m pytest tools/tests/`：856 通过（851 基线 + 本篇 4 条新增契约），14 项失败均为既有类别（12 × devdoc 118-139 重命名残留、market ANSI、版本分叉）
  - `test_lookahead_queues_instead_of_synchronous_decode`：lookahead 必须入队、不得残留同步解码、LOOKAHEAD 档必须是最大值、废弃前向声明必须删除
  - `test_pump_holds_the_queue_while_the_typewriter_reveals`：消费必须被 reveal 门控、过渡双消费必须存活于门内
- `bash core/build.sh`：engine.exe / engine_a.exe 零 `.err`
- `bash makegame.sh make demo-a2` 重打 HDI
- `bash makegame.sh test demo-a2 --serial --auto`：`[PRELOAD] scene='logo.nb' jobs=2` / `op.nb jobs=1` / `mainmenu.nb jobs=1` 入队正常，主菜单 AUTOEXIT 干净退出（`End` + `VE:0..5`）
- 实机听感/观感验证待用户确认（翻页帧不再吃批量解码；连续换装时解码散布到阅读间隙）

## 四、同类问题审计（2026-10-28 补充）

对"同步磁盘读/解码落在可见帧"这一卡顿类做全仓清点（`image_load` / `mag_decode*` / `farchive_read_alloc` / `file_read_all` 全部调用点）：

| # | 调用点 | 时机 | 判定 |
|---|---|---|---|
| 1 | `audio.c` `pcm_play`（SE/语音资产读） | 音效/语音起始帧 | **已知遗留**（177 §9.3 判定收益<风险暂不做）：单次读小样本，卡 1 帧 |
| 2 | `audio.c` BGM 回退读档 | 中段 `bgm()` 切换（非场景首条） | **已知遗留**（177 D6 单条预载缓存只覆盖场景第一条 BGM）：曲目切换帧卡 1-2 帧 |
| 3 | `nb_cggallery.c` 缩略图网格 | 画廊打开/翻页 | 可接受：UI 屏，用户触发，缩略图小 |
| 4 | `nb_saveload.c` 存档缩略图 | 存/读档界面打开 | 可接受：UI 屏，用户触发 |
| 5 | `nb_anim.c` 逐帧解码 | 动画播放 | 设计使然：blob 常驻，逐帧 `mag_decode_into`，无磁盘读；解码量随动画帧尺寸，暂可接受 |
| 6 | `mag_decode` 本身 30-50ms | 每次解码 | **结构性残留**：即使散布到每帧，单次解码仍掉 1-3 帧。终极杠杆是 177 §9.3 已判 fallback 的逐行 `mag_decode_row` 拆分 |
| 7 | cache 32 slots / queue 64 cap | 超 32 张不同立绘的场景 | 行为安全：被驱逐的图在用时同步回落（与改动前一致），只是慢 |

结论：玩法路径上的"批量同帧解码"已由 177+180 消灭；剩余为（a）UI/音效的小额同步读（b）单次解码时长的结构性下限。均无隐蔽回归面。

## 五、预防机制（2026-10-28 落地）

既有守卫都是"钉住已修行为"（`test_naiz_queue` 钉队列接线、`test_frame_pump` 钉 lookahead 调用点），**缺"拦截新阻塞点"的守卫**——本次 180 修的 lookahead 同步解码正是这样漏进来的：177 落地时它已存在，无人报警。

新增 `tools/tests/test_sync_decode_allowlist.py`（2 条契约）：

- **引擎侧白名单**：`core/engine/*.c` 中 `image_load(` / `mag_decode(` / `mag_decode_into(` / `farchive_read_alloc(` / `file_read_all(` 的每一处出现都必须命中 `EXPECTED` 白名单（文件 × 符号 × 数量）；**未列入文件默认 DENY**。新增调用点会让测试失败，失败信息指路：走 `preload_push()` 入队，或带着理由上白名单
- **库侧禁入**：`core/lib/*.c` 仅原始实现与启动期加载器（cjk/font/tr）可引用这些符号，其余 lib 文件出现即失败
- 注释行不计（`*`/`/*`/`//` 开头），文档改动不会误报；已验证负例（模拟新增调用点会被计数捕获）

效果：今后任何 PR 若在玩法路径引入新的同步读/解码，CI 即红——把"这类卡顿"从"事后用户感知"前移到"提交时拦截"。

## 六、遗留与后续可评估

- **逐行 `mag_decode_row` 拆分**（177 §9.3 已判 fallback）：若用户仍感知"阅读静止期每帧掉 1 帧"，这是下一杠杆——每 step ~1ms 彻底消灭解码 hitch
- `layer_sprite_sync_dialog_base` 的重组成本（全 body replace 后 occluder 重建 + 对话框重blit）是 R20 伪透传设计的固有成本，不动
- 24 行窗口在超长无对话段（>24 行连续换装）下仍会晚预热 1-2 帧，靠同步回落兜底
- 音效/语音与中段 BGM 切换的同步读（§四 #1/#2）：单帧小额，若用户可感知再立项
