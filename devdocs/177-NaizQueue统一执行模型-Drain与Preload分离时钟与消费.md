# 177 — Naiz Queue：统一执行模型（Drain + Preload 分离时钟与消费）

> **状态**：**已实施（Phase 0-5 + Phase 6）**——2026-10-27；落地记录见文末 §九
> **创建于**：2026-10-27
> **承接**：`devdocs/176`（ISR 路径 FM 静音根因，修复后进入 v176 ISR drain 架构）、`devdocs/175`（ISR 路径回退与根因待解）、`devdocs/173`（虚拟时钟停顿保护与追赶爆发根因收束）、`devdocs/131`（立绘加载拖慢分析）
> **影响**：`core/engine/frame.c`、`core/engine/audio.c`、`core/engine/transition.c`、`core/engine/image.c`、`core/engine/image_cache.c`、`core/engine/layer_sprite.c`、`core/plat/hal_irq.c`、`core/lib/vclock.c`
> **命名**：本设计的统一执行模型称为 **Naiz Queue**——取"资源排队预加载 + 消费均匀 drain"之意，与当前每帧同步泵入的"一次性处理"模式对照

---

## 一、问题定义

### 1.1 用户感知到的症状

在 PC-98 平台（DOS/4GW 单线程无抢占）上，游戏运行过程中存在三类可感知的"暂停"和"卡顿"：

1. **立绘/场景切换时的首次加载卡顿** —— VM script 执行 `show sprite` 或 `layer_scene_load` 时，主线程被 `image_load()` 的同步磁盘读 + `mag_decode` 阻塞 30-50ms，错过 1-2 个 vblank
2. **过渡期间 BGM/动画/打字机节奏不均** —— `transition_run()` 用 `for` 循环阻塞主线程直到过渡结束（典型 16 帧 ≈ 800ms），期间其他事务被硬塞进循环内逐个处理
3. **BGM 速度轻微不稳定** —— ISR 路径下 stall 后主线程回来时，一次 drain 数十 ms 的 BGM 事件，FM 事件批量爆发派发到 OPNA，后续几个 frame pump 又无事可做

### 1.2 根因分类（按"CPU 排队"的具体形态）

PC-98 没有多线程抢占——所谓"CPU 排队"是单线程中**同步阻塞点**和**执行节奏不均**导致的，具体分三类：

| 排队类型 | 具体机制 | 关联代码 | 影响 |
|---|---|---|---|
| **A. 同步阻塞占住主线程** | `image_load()` → `farchive_read_alloc` + `mag_decode` 30ms+，或 `layer_scene_load()` 同时加载背景+多张立绘 | `image.c:147 image_load()`、`layer.c scene_end()` | 错过 vblank → 所有事务停 1-2 帧 |
| **B. for 循环内自占主线程** | `transition.c:38 for(step=0; step<frames; step++)` 硬等每帧过渡 | `transition.c:25 transition_run()` | 800ms 内主线程被独占，其他事务只能被塞进循环硬 tick |
| **C. burst drain 后空窗** | 主线程恢复时一次 drain N tick 的 BGM 事件，OPNA 写集中爆发，后续 frame pump 无事可做 | `audio.c:audio_tick_isr_pending()`（当前只 drain 不 split） | BGM 节奏不均，可闻抖动 |

### 1.3 受影响的事务（全部需要纳入统一模型）

| # | 事务 | 当前驱动方式 | 时间源 | 是否阻塞主线程 | Stall 敏感点 |
|---|---|---|---|---|---|
| ① | VRAM 刷新 | `vblank_wait()` 帧 pace | GDC vblank | ✅ 等 vblank（~50ms） | 本身就是 pace，不敏感 |
| ② | 文字输出（打字机） | `nb_dialog_reveal_tick()` 每帧 | `hal_wallclock_ms()` | ❌ 轻量 | display-paced，不敏感 |
| ③ | 动画（anim_tick） | `anim_tick()` 每帧 + decode pump 内 poll | `hal_wallclock_smooth_ms()` | ❌ 轻量 | stall 期间不推进 → stall 后暴冲 |
| ④ | 立绘加载 | `image_load()` 同步磁盘读+解码 | 无 | ✅ 30-50ms 阻塞 | 直接卡主线程 |
| ⑤ | 场景加载 | `layer_scene_load()` 同步 | 无 | ✅ 更重（背景+立绘+调色板） | 同上 |
| ⑥ | BGM（ISR 路径） | ISR 记 units → 主线程 drain | ISR 自记 | ❌ ISR 不阻塞；drain 轻量 | C 类排队（burst drain） |
| ⑦ | BGM（协作泵） | `audio_tick()` 每帧 | `hal_wallclock_smooth_ms()` | ❌ 轻量 | A 类排队（stall 时钟冻结） |
| ⑧ | 音效/语音（PCM） | `hal_pcm_advance_units()` 每帧 | 同 BGM | ❌ 轻量 | A 类排队（stall → PCM 队列撑空） |
| ⑨ | 过渡效果 | `transition_run()` for 循环内 | 混合 | ✅ 阻塞直到过渡完 | B 类排队（for 循环独占） |

---

## 二、Naiz Queue 统一执行模型

### 2.1 设计原则

**时钟与执行层解耦**——所有事务共享一条虚拟时钟（vclock），但执行时机由各自的"生产-消费模型"决定。stall 只影响消费节奏，不影响时间线本身的推进。

四条硬约束：

1. **时钟单写者** —— 只有 Timer-B ISR handler 能推进 vclock（`vc->virtual += 258`），引擎代码不得直接 advance
2. **时间戳驱动** —— 每个事件（BGM 音符、动画帧、打字机字符）都带 timestamp，消费者按 timestamp 顺序派发，不靠"间隔推进"
3. **队列深度 ≥ 1 帧** —— 每个生产者-消费者队列深度至少能容纳 1 帧数据量，避免短暂 stall 就撑空
4. **慢消费者不阻塞其他消费者** —— 立绘加载慢不能卡 BGM drain，各队列独立 drain

### 2.2 三层架构

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 0: 时钟（ISR 独立推进，永不 stall）                           │
│                                                                     │
│  Timer-B ISR → vclock += 258 匀速，每 ~16ms                         │
│  唯一职责：告诉世界"现在该是什么时刻了"                              │
│  当前实现：devdoc 176 修复后的 ISR handler，只做全局计数             │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 1: 生产-消费队列（每个事务独立）                               │
│                                                                     │
│  生产者（不阻塞、只记账/入队）:                                       │
│    BGM:      ISR handler 记 g_irq_units_total                       │
│    动画:     VM script 设 anim_set（timestamped）                   │
│    立绘:     image_prefetch_async() 标"需要"，image_decode_step() 拆 │
│              tile 级解码，每 step ~1ms，不阻塞 frame pump           │
│    场景背景: 同上，transition 期间 preload_step() 悄悄解完           │
│    BGM 数据: audio_preload_bgm() 按场景 preload MIDI/OPNA 数据     │
│    音效/语音: hal_pcm_play 入队（timestamped）                      │
│    打字机:   VM script 发 reveal 事件（timestamped）                │
│    过渡效果: transition_start() 初始化，不阻塞                       │
│                                                                     │
│  消费者（主线程 drain，均匀节奏）:                                   │
│    BGM:      split drain，每次 ≤258 units，按参数化 timestamp 派发  │
│    动画:     anim_tick() 每帧读 vclock 推进                          │
│    立绘:     image_load() 只消费已 prefetch cache hit 的；cache miss │
│              时画占位，下次 frame pump 再 retry                     │
│    打字机:   reveal_tick() 每帧读 vclock 显示                       │
│    音效:     hal_pcm_advance() 每帧推进                             │
│    过渡:     transition_tick() 每帧 render 1 step，不阻塞            │
│    preload:  preload_step() 每帧解 1-2 个 tile，消费 preload 队列   │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 2: 帧 pace（唯一 vblank_wait）                                │
│                                                                     │
│  engine_frame_pump() 每 ~50ms 一次                                  │
│  执行顺序（固定，每帧不变）:                                         │
│    ① vblank_wait()               ← 唯一帧 pace 点                  │
│    ② hal_bgm_irq_probe_step()    ← 候选扫描（devdoc 174）           │
│    ③ audio_tick_isr_pending()     ← BGM split drain（Phase 0）      │
│    ④ anim_tick()                  ← 动画推进                        │
│    ⑤ nb_dialog_reveal_tick()      ← 打字机                          │
│    ⑥ preload_step()               ← 每帧解 1-2 tile（Phase 3）     │
│    ⑦ transition_tick()            ← 过渡 render（Phase 1）           │
│    ⑧ hal_mouse_update() / draw    ← 输入                           │
│                                                                     │
│  无任何 while/for 循环内部阻塞；所有重操作拆成 ≤1ms step            │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.3 与当前实现的对比

| 维度 | 当前实现 | Naiz Queue 后 |
|---|---|---|
| 时钟推进 | ISR handler（ISR 路径）/ smooth_advance（协作泵） | **统一 ISR handler 单写**，协作泵模式改为 drain ISR 也推进的时钟 |
| BGM drain | 一次 drain 所有差分（burst） | **split drain** 每次 ≤258 units，参数化 timestamp 均匀派发 |
| transition | for 循环阻塞 800ms | **frame pump 驱动** transition_tick()，每帧 render 1 step |
| 立绘加载 | image_load() 同步阻塞 30ms | **image_decode_step()** tile 级拆分 + **preload_step()** 提前解完 |
| image_cache | 8 slots，场景切换全清 | **≥32 slots**，不清，LRU 自然淘汰；每个 slot 带 ready 位 |
| BGM 数据加载 | 启动时全量载入 | **按场景 preload**，transition 期间悄悄载入下一场景的 BGM |
| stall 后果 | BGM burst drain，动画暴冲 | **时钟匀速推进**，消费节奏均匀，stall 只导致"累积的 drain 量"但不影响派发时刻 |

---

## 三、Drain 机制详解

### 3.1 BGM split drain + 参数化（Phase 0 核心）

**当前问题**：`audio_tick_isr_pending()` 一次取 N units 差分 → 一次 `audio_tick_isr(N)` → FM 读全局 `hal_wallclock_smooth_ms()` 得到同一个时刻 → 所有 FM 事件一次性派发。

**Naiz Queue 做法**：

```c
// audio_tick_isr 签名变更
void audio_tick_isr(unsigned long delta_units, unsigned long now_ms_abs);
//                                              ^^^^^^^^^^^^^^^^^^^^
//                                              调用者传入"应该是什么时刻"，
//                                              函数内部不再读全局

// audio_tick_isr_pending 改造成 split drain
void audio_tick_isr_pending(void)
{
    unsigned long units = hal_bgm_irq_take_pending_units();
    if (units == 0) return;
    
    unsigned long now = hal_wallclock_smooth_ms();
    // stall_start_ms = 当前时刻减去"这段差分覆盖的时长"
    //   即 stall 开始的时刻（或上次 drain 的时刻）
    unsigned long stall_start_ms = now - units / 16;  // 16 = VCLOCK_UNITS_PER_MS
    
    while (units >= BGM_TIMER_B_UNITS) {  // 258 units ≈ 16.1ms
        units -= BGM_TIMER_B_UNITS;
        stall_start_ms += BGM_TIMER_B_UNITS / 16;  // 每次步长 ≈ 16ms
        audio_tick_isr(BGM_TIMER_B_UNITS, stall_start_ms);
        // PCM 推进：用 delta_units（局部，单次调用量）
        // FM 推进：用 now_ms_abs（参数，递增的时刻）
    }
    if (units > 0) audio_tick_isr(units, now);
}
```

**效果**：stall 后 3096 units（12 tick）被拆成 12 次 `audio_tick_isr(258, stall_start_ms + i*16)`，FM 事件按均匀递增的 timestamp 派发，OPNA 写节奏和 ISR tick 对齐。

**零冲突**：split drain 不动 vclock——vclock 由 ISR handler 独立推进，anim_tick() 读到的是同一个 vclock，FM 和动画的时间线完美对齐。

### 3.2 PCM drain

`hal_pcm_advance_units(delta_units)` 当前已经是"用局部 delta 推进"，不需要参数化 timestamp——PCM FIFO 的消费节奏天然由 delta_units 控制。Phase 0 的 split drain 已经保证 PCM 每次只推进 ≤258 units（~16ms 的 PCM 数据），FIFO 填充均匀。

### 3.3 其他事务的 drain 模式

| 事务 | drain 方式 | 是否需要 split |
|---|---|---|
| 动画 anim_tick | 每帧读 vclock → 按 delta_ms 推进帧号 | ❌ 不需要——天然 display-paced |
| 打字机 reveal_tick | 每帧读 vclock → 按 delta_ms 推进字符 | ❌ 不需要 |
| 音效 hal_pcm_play | 入队 timestamp → 每帧 advance | ❌ 不需要——PCM FIFO 天然节奏 |
| 过渡 transition_tick | 每帧 render step++ → 单步 render | ❌ 不需要——单步就是 1 帧 |
| preload_step | 每帧 decode 1-2 tile → ≤1ms | ❌ 不需要——本身就是单步小粒度 |

---

## 四、Preload 机制详解

### 4.1 三类 preload 时机

| 类型 | 触发时机 | 价值 | 内存占用 |
|---|---|---|---|
| **A. 启动时 preload** | bootmenu → 进入第一个场景的收尾期 | 极大——消除"进入游戏首次卡顿" | 场景 1 全量 ≈ 1-2MB |
| **B. 过渡期间 preload** | scene A → B 的 transition_tick 每帧 | 极大——transition 本身就是等待期，变等待为加载 | 场景 B 全量 ≈ 1-2MB |
| **C. 运行时按需 preload** | VM script dispatch lookahead | 中等——现有机制被 cache_clear 抵消，修复后有效 | lookahead N = 24 × 单图 ≈ 2MB |

### 4.2 image_decode_step() — tile 级拆分

```c
// 新增：把 mag_decode 拆成 tile 级 step
// 每个 tile 约 4KB，解码 + blit 到 VRAM 或 cache ≈ 0.8-1.2ms

typedef struct {
    int img_id;           // 目标 image id
    int state;            // 0=未开始 1=farchive 已读 raw 2=正在解第 N tile 3=完成
    long offset, msize;   // farchive 定位信息
    uint8_t *raw;         // 原始数据（state 1+）
    MagImage *img;        // 解码结果（state 3）
    int tile_idx;         // 当前解到第几个 tile
    int total_tiles;      // 总共多少 tile
} ImageDecodeJob;

// 每 frame pump 调一次，一次只解 1-2 个 tile
int image_decode_step(void)
{
    ImageDecodeJob *job = preload_queue_pop_ready();
    if (!job) return 0;
    
    int decoded = mag_decode_tile(job->raw, job->total_tiles, 
                                  job->tile_idx, job->img);
    job->tile_idx++;
    
    if (job->tile_idx >= job->total_tiles) {
        image_cache_insert(job->img_id, job->img);
        image_cache_mark_ready(job->img_id);
        return 2;  // 完成
    }
    return 1;  // 继续
}
```

**关键约束**：`mag_decode_tile()` 必须是**纯函数**（不碰全局状态、不调 hal_log），因为它可能被 ISR 触发的 frame pump 调到——虽然 Phase 3 还在主线程跑，但和 devdoc 176 的 ISR 安全原则一致。

### 4.3 image_cache 改造

| 项目 | 当前 | Naiz Queue 后 |
|---|---|---|
| slots 数 | 8 | **32**（场景 1 背景 + 主立绘 6 + 次立绘 6 + lookahead 16） |
| slot 结构 | `{id, img, hits}` | `{id, img, hits, ready}` |
| scene_clear | `image_cache_clear()` **全清** | **删除此调用**。场景切换时只做 `image_cache_bump_priority(scene_ids[])`，旧场景 slot 自然被 LRU 淘汰 |
| cache hit 检查 | `image_cache_lookup(id)` | 同，但 `image_load()` cache miss 时：如果 preload_queue 里有 job 且已 ready，用 `image_cache_get_ready(id)`；否则画占位，设 `needs_retry` 标志 |
| pin 机制 | `image_cache_pin(id)` 防 LRU | 保留，但扩到 preload job——`preload_queue_hold(id)` |

### 4.4 BGM/音效 preload

当前 BGM 数据在 `audio_init()` 启动时一次性载入。Naiz Queue 改成**按场景关联 preload**：

```c
// layer_scene_load("sc02") 触发时
void layer_scene_load_preload(const char *scene_name)
{
    // 1. 查 config.toml 里 scene_name 关联的 bgm 名称
    const char *bgm = scene_get_bgm(scene_name);
    if (bgm) {
        audio_preload_bgm(bgm);  // 只读文件 + 解析 MIDI/FM 格式，不 start
    }
    
    // 2. preload 该场景需要的所有立绘/背景
    scene_collect_image_ids(scene_name, ids[], count);
    for (int i = 0; i < count; i++) {
        preload_queue_push(ids[i], PRELOAD_PRIORITY_HIGH);
    }
}

// transition 结束时
void transition_finish()
{
    layer_scene_apply_preload();  // 把 preload 的资源正式挂到 layer
    audio_start_preloaded_bgm();  // 零延迟启动 BGM
}
```

音效/语音同理：transition 期间 preload 该场景的高频 SE（button click、chime 等），首次播放时直接 cache hit。

### 4.5 堆水位守卫

preload 不是无限的——每帧 preload_step() 前检查堆剩余：

```c
int preload_step(void)
{
    // 守卫：堆剩余 < 2MB 时停止 preload，降级为按需加载
    unsigned long heap_left = (unsigned long)farcoreleft();
    if (heap_left < 2 * 1024 * 1024) {
        preload_queue_evict_low_priority();  // 主动释放最低优先级的 pending job
        return 0;
    }
    return image_decode_step();
}
```

优先级策略：**背景图 > 主立绘 > BGM > 次立绘 > 音效**。内存不够时依次放弃低优先级，降级为按需同步加载（仍然有 tile 级 step 拆分保护 frame pump）。

---

## 五、冲突处理与安全性

### 5.1 已知不会冲突的组合

| 组合 | 为什么不冲突 |
|---|---|
| split drain vs vclock | split drain 不动 vclock——ISR handler 独立推进，anim_tick 读同一个 vclock，时间线完美对齐 |
| transition_tick vs 其他事务 | transition_tick 是 frame pump 最后一个 step，render 完就 return，不阻塞后续事务 |
| image_decode_step vs vblank | decode_step 每帧 ≤1ms，远小于 vblank 50ms 间隔，不会错过 vblank |
| preload vs BGM drain | 两个独立队列，独立 drain；preload 不碰音频寄存器，BGM drain 不碰图像内存 |
| ISR handler vs 主线程 drain | devdoc 176 的安全原则：ISR handler 只写全局计数器，不调引擎代码；drain 在主线程执行（SS==DS） |

### 5.2 需要守卫的边界

| 边界 | 守卫方式 |
|---|---|
| image_cache 并发访问 | 当前只有主线程访问 image_cache（ISR handler 不碰图像），无竞态 |
| preload_queue 与 image_load 的竞态 | image_load() cache miss 时，检查 preload_queue 对应 job 的 ready 位；已 ready → 用 cache；未 ready → 画占位，设 retry 标志 |
| 过渡期间 VM script dispatch | transition_tick 期间 VM dispatch 暂停（设计如此，transition 就是不可交互的），所以 transition 期间不会同时有新的 image_load 请求 |
| DOS/4GW DPMI 中断调度 | Timer-B ISR 由 DPMI 投递，极少数情况下可能延迟几个 tick。但 vclock 是累计计数器，最终追上；DPMI 延迟是微秒级，不是毫秒级 stall |

---

## 五-A、前置调研结果（2026-10-27 补）

> **范围**：Phase 0-3 的前置调研全部跑完；Phase 4-5 未覆盖
> **方法**：纯代码 grep + Read 切片 + 静态分析（无实机探针）
> **参考项目**：ADV98 已定位在 `/home/edo/pc98`，源码与性能笔记已逐条核对，结论见 §K

### A. VRAM page 1 API → ❌ 无独立 page flip，但 PEGC bank 窗口可用

| 项目 | 现状 |
|---|---|
| HAL API | `hal_vram_bank_select(0-7)` + `hal_vram_get_window()`（`hal.h:504-507`, `hal_pc98.c:384-392`） |
| 架构 | PC-98 PEGC 256-color：640×400 = 256KB VRAM，8×32KB bank，窗口固定在 `0xA8000` |
| 引擎使用者 | `render.c`, `render_vram.c`, `render_text.c`, `render_blit.c`, `cursor.c` 全部在用 |
| 无 | 无 "page 0/page 1" 双页翻页 API，bank select 切换需要 CPU 主动写端口 |

**对设计的修正**：ADV98 "page 1 预合成"方案在 Naiz 上不能叫 page flip（见下方复核）。Phase 3 预合成不存整张 256KB 全 8 bank（代价高），改为 **transition 前把所有 image_load 提前做完、decoded MagImage 存在 image_cache 里，transition 期间只做 render copy + bank select 切换 —— 零文件 I/O**。

**参考项目复核（2026-10-27，`/home/edo/pc98` = ADV98）**：ADV98 确实在用 page 0/1 双页预合成，但那是 **16 色 planar 模式**的机制（A4h 显示页 / A6h CPU 访问页，每页 4 平面 × 32,000B = 128,000B，两页共 256KB）。Naiz 走的是 **PEGC 256 色 packed-pixel 模式**（`video.c:59` 的 Mode set 序列），整屏一帧即占满 256KB，HAL 暴露的 8×32KB bank（`hal_pc98.c:384`）恰好等于一帧用量，**没有余量做后台页**。因此：

- ADV98 的双页方案**不能移植**，"无独立 page flip"的结论**成立，不改**；
- 但 ADV98 的**执行结构**完全可移植：演出前把数据全部备好 → 演出期间文件 I/O = 0 次 → 只做定长分阶段搬运。这正是 Phase 1/3 要的形状，且已在 PC-98 实机（V13 / Ra43 / T98-NEXT）验证；
- 只有在将来引入 16 色兼容模式时，才谈得上 bank 4-7 当后台页；当前 256 色路线下不成立。

### B. 共用图像工作缓冲 → ❌ 无全局/模块级，全 per-instance malloc；但 mag_decode_into 已存在可复用

| 项目 | 现状 |
|---|---|
| per-instance | `nb_anim.c` 每个动画实例 malloc `decode_buf`（`nb_anim.h:39`） |
| decoder | `mag_decode` 内部 `malloc(output)` + `malloc(action)`（`mag.c:278-280`） |
| 可复用的 pool | `mag_decode_into()` **已存在**（`mag.c:536-542`），接受 caller 预分配的 buffer |
| image_cache slot | 只有 `id`, `img`, `hits` 三个字段（`image_cache.c:30-34`），无 ready 位，无预分配 buffer |

**对设计的修正**：Phase 2 image_cache 扩容 8→32 后，每个 slot 可提前分配好 output/action buffer，用 `mag_decode_into` 直接 decode 到 slot —— 省掉每次 malloc/free。

### C. image_load 阻塞路径静态分析 → mag_decode 解压循环内已有 cooperative pump，但 farchive_read_alloc + malloc 段是 gap

image_load 完整路径（`image.c:147-190`）：

```
image_load(id)
  ├─ image_cache_lookup → cache hit? 返回（快）
  ├─ farchive_lookup_id → 查表（快，内存）
  ├─ farchive_read_alloc           ← ① 阻塞点：malloc + fseek + fread（磁盘 I/O，无 hook）
  ├─ mag_decode(raw, size, &img)
  │   ├─ 签名/头/调色板解析         ← ② 阻塞点：纯 CPU，无 hook（~1-2ms）
  │   ├─ malloc(output) + malloc(action) ← ③ 阻塞点：两次 malloc
  │   ├─ 解压主循环 (line 305)      ← ④ ✅ 有 g_mag_progress_hook → frame_decode_pump（每 4KB stride）
  │   ├─ 4bpp→8bpp 转换 (line 397)  ← ⑤ ✅ 也有 hook（每 4KB）
  │   ├─ cropping (line 417)        ← ⑥ 阻塞点：mag_crop_rows 纯 CPU，无 hook
  │   └─ malloc(MagImage) + palette  ← ⑦ 阻塞点：最终 malloc
  ├─ free(raw)
  ├─ image_set_palette
  ├─ image_cache_insert
  └─ return mag_retain(img)
```

cooperative pump 只覆盖 mag_decode 内部的解压循环 + 4bpp→8bpp 转换（占 mag_decode 总耗时约 70%），但 farchive_read_alloc（磁盘 I/O）+ header 解析 + 两次 malloc + cropping + 最终 malloc 段（约占总耗时 30-50%）**完全没有泵**。

**对设计的修正**：Phase 3 逐行 `mag_decode_row` 拆分优先级**大幅降低**。核心洞察——**preload 的价值不是拆 decode 循环（循环内已有 pump），而是把整个 image_load（含磁盘读 + 所有无 pump 段）提前到 transition 间隙完成**。修正后的决策树：

```
Phase 3 核心路径（优先）：
  transition_start 之前
    → scene_collect_image_ids(next_scene) 拿到所有待加载图 id
    → preload_push_batch(ids) 全部入队
  transition_tick 每帧
    → preload_step × N：从队列取 job → farchive_read_alloc + mag_decode_into 到 cache slot → 设 ready=1
    → transition 结束（~800ms）preload 完 10-13 张图绰绰有余
  scene 进入后
    → image_load 全 cache hit → 零阻塞

Phase 3 逐行 mag_decode_row 拆分（降级为 fallback）：
  仅当 farchive_read_alloc 耗时实测 > 100ms（极少见的大文件/慢盘）时启用
  或用于启动时 preload（bootmenu 收尾期无 transition 可利用）
```

**参考项目补充（ADV98 第23話 AB 对比表）**：ADV98 做过六项对照，结论是 `G98 fread 回数 = 効いた`（减少**调用次数**有效），而 `SPR fread 回数 = ほぼ効かない`、`背景復元 = 犯人ではない`、`SPR 再描画 = 1 回だけ`、`graph98_pset 高速化 = 体感変化なし`、`8ドット単位描画 = 体感変化なし`。说明 DOS 下 **stdio 函数调用次数本身就是独立成本项**，不等价于字节数。

对 Phase 3 的含义：`farchive_read_alloc` 每图一次 `fseek+read`，调用次数已是最小，所以 §3.0 第 2、3 项实机探针应拆成三问分别测量：

| 探针 | 测什么 | 若结果偏高的对策 |
|---|---|---|
| ① 单图 read 调用耗时 | `farchive_read_alloc` 单独计时 | 区分"调用次数成本"与"实际读盘时间"；前者无解（已最小），后者说明盘慢 → 走 3.1d fallback |
| ② 单图 mag_decode 耗时 | 含无 pump 的 header/malloc/cropping 段 | 若 > 100ms 才启用逐行拆分；否则 preload 一次性解码即可 |
| ③ 同场景二次 image_load 是否再读盘 | cache 命中率 | **若"是"，则 Phase 2 扩容（8→32）的收益高于 Phase 3 预加载**，应先做 Phase 2 再评估 Phase 3 |

③ 是本次复核新增的判据：ADV98 **完全没有 image_cache**、每次从文件重读，在 i486SX/8MHz 上立绘显示速度仍与既有商业 ADV「ほぼ同程度」——这说明它的卡顿不来自绘制或解码，而来自 I/O 次数。Naiz 已有 8 slot cache，若实测显示 8 slot 不足以装下一个场景（10-13 张图）导致反复重解码，那"preload 到 32 slot"本身就能解决大部分体感问题，不需要提前引入逐行拆分。

### D. audio_tick_isr 时间源 + 调用点 + 常量 → 精确定位

**函数体内读 smooth_ms 的位置**（Phase 0 必须改）：

| 位置 | 代码 | 用途 |
|---|---|---|
| `audio.c:672` | `unsigned long now = hal_wallclock_smooth_ms();` | FM 路径 `cur = now - g_bgm.wall0` + MIDI fallback 路径（line 708 复用同一个 `now`） |

**调用点**：

| 位置 | 调用 | 说明 |
|---|---|---|
| `audio.c:748` | `audio_tick_isr(units)` | `audio_tick_isr_pending()` — Phase 0 改 split drain while 循环 |
| `audio.c:783` | `audio_tick_isr(hal_wallclock_last_advance_units())` | `audio_tick()` 协作泵外壳 — 需同步加 now 参数 |

**常量定义**：

| 常量 | 值 | 位置 |
|---|---|---|
| `BGM_TIMER_B_UNITS` | **258** | `hal_irq.c:70` |
| `VCLOCK_UNITS_PER_MS` | **16** | `vclock.h:47` |

**对 Phase 0 精确改动清单**（已锁定，动手时无需再调研）：
1. `audio.h:18` 原型：`audio_tick_isr(unsigned long delta_units)` → `audio_tick_isr(unsigned long delta_units, unsigned long now_ms_abs)`
2. `audio.c:670` 实现签名同步
3. `audio.c:672` 删 `unsigned long now = hal_wallclock_smooth_ms();` → 改用参数 `now_ms_abs`
4. `audio.c:742-748` `audio_tick_isr_pending` 加 while 循环 split drain
5. `audio.c:783` 同步改 `audio_tick()` 外壳的调用参数

### E. Phase 1 额外确认项

| 项目 | 现状 | 对 Phase 1 的影响 |
|---|---|---|
| `transition_run` 唯一调用点 | `layer.c:38` 一处（grep 确认） | Phase 1 改动局限 transition.c + layer.c + frame.c |
| `g_transition` 全局状态 | **不存在**（grep 无匹配） | Phase 1 需新建 `TransitionState` 结构 + 全局实例 |
| transition family step-wise render | 全部**无状态依赖** | Phase 1 安全拆 step-by-step |
| transition_pfade_solid step=0 | step=0 时 capture palette 到 file-scope static `pfade_basis` | Phase 1 `transition_start` 调一次 step=0 的 palette capture（或把 basis 存到 g_transition） |
| transition_pblinds_wipe | 每步独立计算 front_prev/front_cur/delta，只画新增 strip | 无依赖 |
| transition_checker_wipe | 每步独立计算所有 cell activation step | 无依赖 |

### F. Phase 2 额外确认项

| 项目 | 现状 | 对 Phase 2 的影响 |
|---|---|---|
| ImageCacheSlot 结构 | `id` + `img` + `hits` 三字段（`image_cache.c:30-34`） | Phase 2 需加 `int ready` 位 + 可选预分配 buffer |
| `image_cache_pin` 调用点 | 仅 `image.c:226` 一处（在 image_prefetch 结尾） | Phase 2 ready 位与 pin 互不影响——pin 管 LRU 淘汰优先级，ready 管 preload 完成状态 |
| `IMAGE_CACHE_PREFETCH_HITS` | 当前值 4（`image_cache.c:28`） | prefetch 后 pin 把 hits 抬到 4，防止被新 decode 淘汰 |

### G. Phase 3 额外确认项

| 项目 | 现状 | 对 Phase 3.1c 的影响 |
|---|---|---|
| **VM script dispatch 暂停时机** | `scene_switch()` → `nb_load(filename)` → **`scene_end()`（启动 transition）** → 读 .nb → `vm_request_scene_change()`。transition 在 .nb 解析之前，期间没有 VM 在跑 | Phase 3.1c 的 preload_push_batch + transition_start 位置正好——在 `scene_end()` 里 transition_start 之前触发 preload，此时 .nb 还没读 |
| **image id 来源** | .nb 脚本里 `bg(...)`, `char(...)`, `cg(...)` 等命令引用 asset key 字符串；`nb_asset_id(key)` 映射成 TOC index | `scene_collect_image_ids_from_nb(filename)` 实现：`fopen` .nb → 正则提取 asset key → `nb_asset_id` 转 id |
| **config.toml 不含场景级 asset 配置** | config.toml 只有全局配置（transition 类型/帧数、对话框配色等），没有 "scene N 需要哪些图" 的场景级配置 | 只能从 .nb 脚本解析，不能从 config.toml 拿 |

### H. Phase 4 额外确认项

| 项目 | 现状 | 对 Phase 4 的影响 |
|---|---|---|
| **audio_init 只做硬件检测，BGM 按需加载** | `audio_init()`：archive open + MPU/FM detect + patch load + `fmseq_init()`。**BGM 数据在 `audio_bgm_start()` 里按需加载**——`farchive_read_alloc` + MIDI/FM 解析成 MidEvent 数组 + `fmseq_events()` 喂 | `audio_preload_bgm` 复用 `audio_bgm_start` 里的解析逻辑，存 MidEvent 数组但不喂 fmseq、不 start |
| **MIDI/FM 解析函数** | `fmseq` 库 API：`fmseq_size()` / `fmseq_init()` / `fmseq_events()` / `fmseq_pump()` / `fmseq_stop()`。**无独立 MIDI 解析**——MIDI → MidEvent 在 `audio_bgm_start` 内部（`audio_load_midi` / `audio_load_fm`，audio.c） | preload 时需要把 audio_bgm_start 里的解析逻辑拆成独立函数 |
| **PCM preload 情况** | `audio_snd_play()` / `audio_vc_play()` → `pcm_play()` → **每次 farchive_read_alloc + hal_pcm_play**。**无 preload**，首次播放有文件 I/O 阻塞 | Phase 4 需要新增 PCM preload 机制（存档 + 复用已解压 buffer） |
| **farcoreleft 不可用；`_memavl()` 也没用** | `farcoreleft()` 只返回 1MB 以下常规内存剩余；Open Watcom `_memavl()` 只反映 near heap（heap 可 grow，没用）；**正确方案是 DPMI Int 31H Function 0500H（DOS/4GW 官方推荐）**。DPMI 0.9（DOS/4GW 用的版本，不支持 1.0 的 050BH）返回 48-byte buffer，offset 00H 是 Largest available free block in bytes（唯一保证有效的字段）。Naiz 保护模式程序可以直接 `int386(0x31, &in, &out)` 调用 | Phase 4 堆水位守卫用**两层方案**（AdvisorTool 推荐）：① Tier 1（主方案，零开销）：**try-malloc-fail-skip**——preload job malloc 失败就跳过，返回 cache miss 时 image_load 降级同步解码；② Tier 2（可选优化，~10 行 inline asm）：引擎启动时调一次 DPMI 0500H 记初始 free block，preload_heap_ok() 对比估算，避免注定失败的 malloc 尝试（减少堆碎片） |

### I. Phase 5 额外确认项

| 项目 | 现状 | 对 Phase 5 的影响 |
|---|---|---|
| **bootmenu → 场景 1 调用链** | bootmenu → main loop → **mainmenu.nb**（主菜单） → 用户点击 Start → `scene_switch("nbook001.nb", SCENE_SWITCH_MENU)`（`nb_mainmenu.c:89`）。**bootmenu 不直接进入 nbook001.nb**，中间有 mainmenu 层 | bootmenu 收尾期（bootmenu_run 返回后 → main loop 第一帧）→ **进入 main loop 后每帧 drain preload_step** 等用户点击 Start 时 nbook001 可能已 preload 完 |
| **bootmenu 收尾期空闲时间** | bootmenu_run 返回 → main loop → mainmenu.nb 加载 → 等待用户操作 → 用户点击 Start → nbook001.nb。这段时间主循环正常跑 frame pump，可以在 frame pump 里偷偷 drain preload | Phase 5 的 preload 触发点不是 bootmenu 内，而是 **engine_frame_pump 里检测"首次进主循环"后自动 preload 场景 1** |
| **场景 1 名称** | demo-a2 硬编码 `"nbook001.nb"`（`nb_mainmenu.c:83/89`）。不是从 config.toml 读的。不同工程的场景 1 名不同 | Phase 5 需要 **从 mainmenu.nb 的 start 命令自动提取目标文件名**（和 Phase 3.1c 用同一套 .nb 解析工具），或者在 config.toml 新增 `bootmenu.first_scene` 配置 |

### K. ADV98 参考项目实证（`/home/edo/pc98`）→ ✅ 已定位并核对源码

> **项目**：ADV98.EXE（upstream `yarufu/pc98`），面向 PC-9801/9821 的 **16 色** ADV 引擎，ia16-elf-gcc **small model**，`-Os -march=v30`
> **凭据**：`README.md` 自述、`docs/030.performance_notes.md`（分章实测记录）、`src/graph98.c`（共享工作缓冲）
> **注意**：ADV98 与 Naiz 是**不同色深**的两套显示模型，结论须逐条判定适用性，不可整体搬用

#### K.1 可引用的实测数据

| 项目 | 数值 | 出处 |
|---|---|---|
| 共享图像工作缓冲 | `graph98_image_work[8192]` 替代 6 个重复 static 缓冲（2×2,560B + 80B + 3×8,192B），前提是"这些处理不会同时执行" | `graph98.c:113` 起多处 `static assert` 校验不越界 |
| 合并收益 | `.bss` 42,824B → 21,240B（-21,584B）；DGROUP 静态负载 62,168B → 40,584B；最低栈预留后余量 2,568B → 24,152B | 030 §「画像作業用バッファの共通化」 |
| 背景矩形 520×299 | 一方向 78,936B（中央 76,544B + 左右边界 2,392B）；桥接 157,872B；38 段；**演出期文件 I/O = 0 次** | 030 §2026-08-02 |
| 全画面 640×400 | 4 平面 × 32,000B = 128,000B；桥接 256,000B；VSYNC 等 2 次；**演出期 I/O = 0 次** | 030 §「通常背景の裏画面完成合成方式」 |
| 立绘部分更新（8 ライン） | 290 ライン、37 小単位、RAM 37,120B、最大缓冲 8,192B、VSYNC 1 次 | 030 §「通常立ち絵部分更新」 |
| 立绘显示速度 | i486SX/8MHz 实机与既有商业 ADV 对比「ほぼ同程度」→ 判定绘制速度不是瓶颈 | 030 §第23話「追加確認（結論）」 |

#### K.2 对 177 的适用性判定

| ADV98 结论 | 适用 Naiz？ | 理由 |
|---|---|---|
| page 0/1 双页预合成 | ❌ **不适用** | ADV98 是 16 色 planar：A4h 显示页 / A6h CPU 访问页，2 × 128,000B。Naiz 是 PEGC 256 色 packed-pixel，整屏占满 256KB，HAL 只暴露 8×32KB bank，无后台页余量。详见 §A 复核段 |
| 演出前备齐数据 → 演出期 0 文件 I/O → 定长分阶段搬运 | ✅ **完全适用** | 与 Phase 1 `transition_tick` + Phase 3 `preload_step` 同构，且在 T98-NEXT / V13 / Ra43 三环境验证过 |
| 单一共享图像工作缓冲 | ✅ 适用（形态不同） | Naiz 是 DOS/4GW 保护模式，堆不受 DGROUP 64KB 约束；但"同一时刻只有一个解码 job"的假设可用于省 malloc，对应 Phase 3.1a slot 预分配 buffer |
| 减少 fread **调用次数** 优于减少字节数 | ✅ 适用（需实机确认） | 见 §C 补充的三问探针表 |
| 立绘绘制速度不是瓶颈 | ⚠️ 需独立验证 | ADV98 无 image_cache、每次重读文件仍达商用水平；Naiz 已有 8 slot cache，其卡顿更可能来自 **cache miss 重复解码** 而非绘制本身 |

#### K.3 一条反例警告：DGROUP 压力

ADV98 记录过：仅新增 2,560B static 缓冲后，DGROUP 余量被压到 2,568B，症状是**背景/立绘绘制异常变慢、BGM 变调、文字乱码**，但**无崩溃、无越界、无栈破坏**——根因是 libc 的第二份 stdio 缓冲（约 1,024B/文件）拿不到空间而退化到小缓冲。

映射到 Naiz：Naiz 是保护模式 + 正常 malloc，不受 DGROUP 约束，但同类风险的现代形态是**堆碎片**。因此：

- Phase 4 的 Tier 1 `try-malloc-fail-skip` 守卫**不可省略**；
- 不能用"链接通过 / 启动成功 / 单次跑通"当作内存安全证据——ADV98 的症状恰恰是"没有报错但一切都变慢"。

---

## 六、实施计划（Phase 0-6，细化版）

> **前置修正**（devdoc 177 原文勘误）：`image_cache_clear()` **只在 `image_close()` 引擎关闭时调用一次**，不是每次场景切换都清。立绘加载卡顿的根因改为：① image_cache 只有 8 slots，一个场景 10-13 张图 → 频繁 LRU 淘汰 → 再次 image_load 重新解码 ② image_load 同步阻塞 ③ transition 期间未利用空闲 preload

每个 Phase 独立可验证——完成后跑 `make -C core && pytest`，通过才进下一个。

---

### Phase 0：BGM split drain + 参数化 timestamp

**目标**：消除 ISR 路径下 stall 后 FM 事件一次性 burst drain 的节奏不均。

#### 0.0 前置调研清单（**全部已确认** §五-A.D）

| # | 确认项 | 状态 |
|---|---|---|
| 1 | `audio_tick_isr()` 内读 smooth_ms 位置：**仅 audio.c:672 一处**（`unsigned long now = hal_wallclock_smooth_ms()`） | ✅ 已确认 |
| 2 | 调用点：`audio_tick_isr_pending()` 内 audio.c:748 + `audio_tick()` 外壳内 audio.c:783 | ✅ 已确认 |
| 3 | `BGM_TIMER_B_UNITS` = 258，定义在 `hal_irq.c:70` | ✅ 已确认 |
| 4 | `VCLOCK_UNITS_PER_MS` = 16，定义在 `vclock.h:47` | ✅ 已确认 |
| 5 | split drain 循环内 FM 累积派发事件量与一次性 drain 相同 | ✅ 逻辑推导成立 |

#### 0.1 详细改动清单

| 文件 | 改动 | 具体操作 |
|---|---|---|
| `audio.h` | 改 `audio_tick_isr` 签名 | `void audio_tick_isr(unsigned long delta_units)` → `void audio_tick_isr(unsigned long delta_units, unsigned long now_ms_abs)` |
| `audio.c` | `audio_tick_isr` 内部改时间源 | 把函数体内的 `unsigned long now = hal_wallclock_smooth_ms();` 改成用参数 `now_ms_abs`；所有读 `now` 的地方不变 |
| `audio.c` | `audio_tick_isr_pending` 实现 split drain | 当前是 `audio_tick_isr(units)` 一次性 drain；改成 while 循环：每次 drain ≤258 units，每次传递增的 `stall_start_ms + i * (BGM_TIMER_B_UNITS / VCLOCK_UNITS_PER_MS)` |
| `audio.c` | frame pump 内的 audio_tick 适配 | `audio_tick()` 内部如果有调 `audio_tick_isr` 的协作泵分支，保持传 `hal_wallclock_smooth_ms()`（参数化对协作泵也是好事） |
| `frame.c:37` | ISR drain 调用点不变 | `audio_tick_isr_pending()` 已经内部 split，调用点不改 |
| `transition.c:63` | 同上 | transition ISR 分支里的 `audio_tick_isr_pending()` 调用点不改 |

#### 0.2 构建与测试步骤

```bash
cd /home/edo/naiz/core && make clean && make 2>&1 | tail -20
# 预期：零 .err 诊断

cd /home/edo/naiz && python3 -m pytest tools/tests/test_frame_pump.py -v 2>&1 | tail -30
# 预期：现有 ISR 相关测试全过；split drain 守卫测试（新增）过
```

#### 0.3 实机验证步骤

1. `./makegame.sh test demo-a2 --serial`（不要 --auto，手动进场景）
2. bootmenu BGM Mode 选 ISR
3. 进场景后让 BGM 跑起来，触发一次立绘加载（制造 stall）
4. 串口发 `irq status` 确认 ISR active
5. 听 stall 前后 BGM 节奏是否均匀
6. 串口观察 `[ISR] ticks=xxx v=xxx w=xxx` 日志

#### 0.4 回滚方案

如果 split drain 引入 bug（FM 事件丢失或重复派发），只需把 `audio_tick_isr_pending` 里的 while 循环改回一次性 drain `audio_tick_isr(units, now)`，其他文件不变。

#### 0.5 风险点

| 风险 | 缓解 |
|---|---|
| split drain 循环内多次调用 audio_tick_isr 增加 CPU 时间 | 理论上每次 audio_tick_isr(258) 内 FM 推进只覆盖 16ms 范围，fmseq_pump 内部事件派发量和原来一次 drain 3096 总量相同，只是调用次数增加（~12 次 vs 1 次），额外开销 <0.5ms/帧 |

---

### Phase 1：transition 从 for 循环改 frame pump 驱动

**目标**：消除 transition 期间主线程被独占 800ms，让所有事务（BGM、动画、打字机、preload）在 transition 期间继续 drain。

#### 1.0 前置调研清单（**全部已确认** §五-A.E）

| # | 确认项 | 状态 |
|---|---|---|
| 1 | `transition_run()` 唯一调用点：`layer.c:38` 一处 | ✅ 已确认 |
| 2 | `g_transition` 全局变量**不存在**——Phase 1 需新建 `TransitionState` 结构 | ✅ 已确认 |
| 3 | transition family 函数全部**无状态依赖**，step-wise render 安全；pfade step=0 做 palette capture（`pfade_basis` 是 file-scope static） | ✅ 已确认 |
| 4 | transition 期间 VM script dispatch 是否暂停——**已确认：自然暂停**。调用链：`scene_switch()` → `nb_load(filename)` → 读 .nb + `scene_end()` → `transition_run()` → `vm_request_scene_change()`。transition 在 `vm_request_scene_change()` 之前，期间没有 VM 在跑 | ✅ 已确认（无需显式守卫） |
| 5 | transition 结束时 `palette_set_all(transition_black)`（`transition.c:80`）——需移到 transition_tick 的最后一帧执行 | ✅ 已确认 |

#### 1.1 详细改动清单

| 文件 | 改动 | 具体操作 |
|---|---|---|
| `transition.c` | 拆 transition_run → start + tick | ① transition_start() 初始化 g_transition 状态（type, frames, step=0, x,y,w,h,color），立即返回；② transition_tick() 每帧：根据 type 调对应 family 函数 render 本 step；step++；step >= frames 时 palette_set_all(transition_black) + 设 active=0 |
| `transition.c` | 删除 for 循环内的 audio_tick 硬塞 | transition_tick 不再管 audio——frame pump 里正常 drain |
| `transition.c` | 新增 g_transition 状态结构 | typedef struct { int active, step, total; unsigned char type, color; int x,y,w,h; } TransitionState; 全局实例 |
| `transition.h` | 新增声明 | `void transition_start(...); void transition_tick(void); int transition_active(void);` |
| `layer.c:38` | scene_end 改调用 | `transition_run(...)` → `transition_start(...)` |
| `frame.c:57 附近` | frame pump 末尾加 transition_tick | 在 `nb_dialog_reveal_tick()` 之后加 `transition_tick();` |
| `frame.c` | decode pump 里也加 transition_tick（可选） | 如果 transition 期间有 decode 在跑，frame_decode_pump 也应该调 transition_tick |

#### 1.2 构建与测试步骤

```bash
cd /home/edo/naiz/core && make clean && make 2>&1 | tail -20
cd /home/edo/naiz && python3 -m pytest tools/tests/test_frame_pump.py -v 2>&1 | tail -30
```

#### 1.3 实机验证步骤

1. 进场景后执行一次场景切换（触发 transition）
2. transition 期间观察：BGM 是否继续均匀播放？打字机是否继续显示？动画是否继续推进？
3. 串口观察 transition 期间 frame pump 是否正常运行

#### 1.4 回滚方案

把 transition_start/tick 删掉，恢复 transition_run 的 for 循环。改动局限在 transition.c + layer.c + frame.c 三个文件。

#### 1.5 风险点

| 风险 | 缓解 |
|---|---|
| transition 期间用户输入（鼠标/键盘）导致状态错乱 | transition_tick 期间 hal_mouse_update 仍然在 frame pump 里调，但 VM dispatch 在 transition 期间已经暂停——确认这一点；如果没有暂停，加 transition_active() 守卫 |
| transition_pfade / blinds / checker 的 step-wise render 是否有状态依赖（比如是否依赖"当前 step 之前已 render 过"） | 读每个 family 函数实现——pfade 是 palette 插值（无依赖），blinds/checker 是 partial wipe（无依赖）。每帧 render 一个 step 是安全的 |

---

### Phase 2：image_cache 扩容 8→32 + slot 加 ready 位

**目标**：一个场景 10-13 张图不再因 cache 容量不够被频繁淘汰，为 Phase 3 的 preload 铺路。

#### 2.0 前置调研清单（**全部已确认** §五-A.F）

| # | 确认项 | 状态 |
|---|---|---|
| 1 | ImageCacheSlot 结构：`int id` + `MagImage *img` + `int hits`，三字段（`image_cache.c:30-34`），**无 ready 位，无预分配 buffer** | ✅ 已确认 |
| 2 | `image_cache_pin` 调用点：仅 `image.c:226` 一处（在 image_prefetch 结尾）；无 unpin 调用 | ✅ 已确认 |
| 3 | prefetch pins（devdoc 133）和新 ready 位**互不影响**——pin 管 LRU 淘汰优先级（抬 hits 到 4），ready 管 preload 完成状态 | ✅ 已确认 |

#### 2.1 详细改动清单

| 文件 | 改动 | 具体操作 |
|---|---|---|
| `image_cache.c:22` | IMAGE_CACHE_SLOTS 8→32 | 宏定义改值 |
| `image_cache.c:30-34` | slot 结构加 `int ready` | ImageCacheSlot 结构体加 ready 字段 |
| `image_cache.c:39-45` | cache_init 初始化 ready=0 | image_cache_init 循环里加 slot.ready = 0 |
| `image_cache.c:147` 附近 | 新增 image_cache_mark_ready | slot.ready = 1；预加载完成时调 |
| `image_cache.c` | 新增 image_cache_is_ready 查询 | slot.ready 读取 |
| `image_internal.h` | 声明新函数 | image_cache_mark_ready / image_cache_is_ready |

#### 2.2 构建与测试步骤

```bash
cd /home/edo/naiz/core && make clean && make 2>&1 | tail -20
cd /home/edo/naiz && python3 -m pytest tools/tests/ -v -k "image" 2>&1 | tail -20
# 预期：所有 image 相关测试全过
```

#### 2.3 实机验证步骤

1. 连续切换 3 个场景，每个场景 ≥10 张立绘
2. 串口观察 image_load 的 cache hit 日志——前几次是 miss（首次加载），之后应该全 hit
3. 不应该再有 LRU 淘汰（因为 32 slots 足够容纳所有场景图）
4. **记录同一场景内第二次访问同一张图的 hit 率**（§C 探针 ③）：这是决定 Phase 3 预加载是否必要的关键判据。若扩到 32 slot 后 hit 率已接近 100%，Phase 3 可只做"transition 期间 preload"而无需任何解码拆分

#### 2.4 回滚方案

slot 数改回 8，删掉 ready 位。改动只在 image_cache.c + image_internal.h。

#### 2.5 风险点

| 风险 | 缓解 |
|---|---|
| 32 slots 增加堆内存（每个 MagImage 30-80KB，32 × 60KB = 1.92MB） | DOS/4GW 堆通常 16-32MB，2MB 可接受；加上 Phase 5 的堆水位守卫后更安全 |
| image_cache 操作效率（slot 数增加 → lookup 线性扫描变慢） | 32 slots 线性扫描 32 次 = 微秒级，不敏感 |

---

### Phase 3：异步 preload 队列 + transition 期间 preload_step

**目标**：transition 期间（~800ms）利用空闲 preload 下一个场景的所有立绘/背景，场景切换进来后 image_load 全 cache hit。

> **§五-A.C 设计修正（关键）**：mag_decode 解压循环内已有 cooperative pump（`g_mag_progress_hook` → `frame_decode_pump`），但 image_load 的前半段——`farchive_read_alloc`（磁盘 I/O）+ header 解析 + 两次 malloc + cropping + 最终 malloc——完全没有泵。**preload 的核心价值不是拆 decode 循环（循环内已有 pump），而是把整个 image_load 同步阻塞路径提前到 transition 间隙完成**。因此 Phase 3 的优先路径是 **mag_decode_into 一次性解码到 cache slot**（利用 Phase 2 的预分配 buffer），`mag_decode_row` 逐行拆分降级为 fallback（仅用于极端慢盘或启动时 preload）。

#### 3.0 前置调研清单（**6 项中 4 项已确认** §五-A.B/C）

| # | 确认项 | 状态 |
|---|---|---|
| 1 | mag_decode 可拆逐行吗？**解压循环有行级依赖（引用上 1-3 行），理论上可拆逐行；不可拆 tile**。但 §五-A.C 指出 mag_decode_row 优先级已降级 | ✅ 已确认（但决策修正：降级为 fallback） |
| 2 | 一张立绘 mag_decode 实际耗时——**本轮未做实机探针**；但 image_load 完整阻塞路径的各段已分析（§五-A.C 树状图） | ⚠️ 需实机 hal_logf 探针确认 |
| 3 | farchive_read_alloc 读磁盘实际耗时——**本轮未做实机探针**；但静态分析显示它是纯同步阻塞（`malloc` + `fseek` + `fread`，无 hook） | ⚠️ 需实机确认（极关键，§五-A.C 决策树的前提） |
| 4 | 如何从场景名解析出关联的 image id 列表——**已确认方案**。.nb 脚本里 `bg(normal){homeday}` / `char(l,normal,body){fei}` 等命令引用 asset key；`nb_asset_id(key)` 把 key 字符串映射成 TOC index。实现：`fopen(next_scene.nb)` → 正则匹配 `bg(|char(|cg(` 等命令里的 asset key → `nb_asset_id(key)` 转 id → 收集。**注意**：transition 启动时 .nb 文件还没解析（调用链是 `nb_load` → `scene_end` → transition → 解析 .nb → `vm_request_scene_change`），所以需要在 `scene_end` 里自己读一次 .nb 提取 key | ✅ 已确认实现方案 |
| 5 | image_load cache miss 当前行为——**已读 image.c:147-190 完整实现**：cache miss → `farchive_read_alloc` + `mag_decode` → `image_cache_insert` → `return mag_retain(img)` | ✅ 已确认 |
| 6 | 是否已有 preload 队列雏形——**`image_prefetch()` 已存在**（`image.c:197-226`）：cache miss → `farchive_read_alloc` + `mag_decode` → `image_cache_insert` + `image_cache_pin`。可以复用作为 preload_step 的底层，但需要改成逐 job 调用（当前是一次性同步 decode） | ✅ 已确认（可复用为基础） |

#### 3.1 详细改动清单（**路径修正：mag_decode_into 优先，mag_decode_row 降级**）

**这是最大的一个 Phase（~60-100 行改动），建议拆成 3.1a / 3.1b / 3.1c 三个小步分别验证。**

##### 3.1a：preload_queue 基础 + Phase 2 slot 预分配 buffer（与 Phase 2 联动）

| 文件 | 改动 | 具体操作 |
|---|---|---|
| `preload_queue.c`（新） | preload 队列基础操作 | `preload_push(img_id, priority)` / `preload_pop()` / `preload_queue_size()` —— 管理待 preload 的 image id 列表，按优先级排序。**栈数组实现，不安易追加 static**（ADV98 启示：共用工作缓冲，DGROUP 压力） |
| `preload_queue.h`（新） | 声明 | — |
| `image_cache.c`（Phase 2 联动） | slot 新增预分配 buffer 字段 | ImageCacheSlot 加 `uint8_t *work_out` + `uint8_t *work_action` 预分配 buffer；`image_cache_init` 里提前 malloc；`image_cache_clear` 里 free |

##### 3.1b：preload_step 核心实现（mag_decode_into 一次性路径）

> **§五-A.C 决策**：preload_step 内每个 job 做 **完整的 farchive_read_alloc + mag_decode_into 一次性解码**，不是逐行拆。理由：
> 1. image_load 的主要阻塞在 farchive_read_alloc（磁盘 I/O）和 malloc 段，解压循环已有 cooperative pump
> 2. transition 期间 ~800ms 足够 preload 完 10-13 张图（即使每张 50ms）
> 3. mag_decode_into 已存在，Phase 2 预分配 buffer 后省掉 malloc/free

| 文件 | 改动 | 具体操作 |
|---|---|---|
| `preload_queue.c` | 新增 preload_step | 从队列取下一个 job → 查 image_cache 是否已有该 id → 没有则：① farchive_lookup_id 拿 offset/size ② farchive_read_alloc 读 raw ③ mag_decode_into(raw, size, slot->work_out, slot->work_action, &img) ④ 设 slot.ready=1 ⑤ free(raw) |
| `frame.c` | engine_frame_pump 末尾加 preload_step | 在 transition_tick 之后；每帧调 1-2 次（transition 期间可多调） |
| `transition.c` transition_tick | 持续 drain preload | 每帧 transition_tick 里调 preload_step × 3-5（transition 期间有充足时间） |
| `image.c:147` image_load | cache miss 行为改 | 当前是 `farchive_read_alloc + mag_decode` 一次性同步解；改成：① 查 preload_queue 对应 id 的 slot → ready=1 直接用 cache ② ready=0 但 preload queue 里有 → 返回上一张图（占位），设 retry 标志 ③ preload queue 里没有 → 降级为同步 mag_decode（和现在一样，但这种情况极少） |

##### 3.1c：scene_end 触发 preload 下一场景

| 文件 | 改动 | 具体操作 |
|---|---|---|
| `scene.c`（或 scene 相关） | 新增 scene_collect_image_ids | 给定场景名，返回该场景所有需要加载的 image id 列表（背景 + 立绘 + 过渡图） |
| `layer.c` scene_end | transition_start 之前触发 preload | ① `scene_collect_image_ids(next_scene, ids, count)` ② `preload_push_batch(ids, count, PRIORITY_HIGH)` ③ `transition_start(...)` |

##### 3.1d（fallback，可选）：mag_decode_row 逐行拆分

> **§五-A.C 决策**：**仅当实机探针确认 farchive_read_alloc + mag_decode 单张耗时 > 100ms 时才启用**。800ms transition 窗口可能 preload 不完 8 张图时才需要拆。
> **也可用于启动时 preload**（bootmenu 收尾期无 transition 可利用，只能靠 frame pump 间隙逐行解）。

| 文件 | 改动 | 具体操作 |
|---|---|---|
| `mag.c` | 新增 mag_decode_row 函数 | 签名：`int mag_decode_row(MagDecodeState *state, uint8_t **out_row_buf)`；从 state 恢复 BitReader/fb_pos/col_pos/act_idx/action buffer/row_bytes 等中间状态，解一行，更新 state。新增 `MagDecodeState` 结构体（包含所有 mag_decode 内部局部变量） |
| `mag.h` | 声明新函数 + MagDecodeState | MagDecodeState 是不透明结构体，mag.c 内部定义，外部只传指针 |
| `preload_queue.c` | preload_step 切换为逐行模式 | 检测 slot->work_out 是否已有 partial data → 有则继续 mag_decode_row，没有则初始化 MagDecodeState 开始解 |

#### 3.2 构建与测试步骤

```bash
# 3.1a 后（preload_queue + slot 预分配 buffer）
cd /home/edo/naiz/core && make clean && make 2>&1 | tail -20

# 3.1b 后（preload_step 核心）
make -C core && python3 -m pytest tools/tests/ -v 2>&1 | tail -20

# 3.1c 后（全量测试）
make -C core && python3 -m pytest tools/tests/ -v 2>&1 | tail -30
# 预期：856+ passed

# 3.1d 后（fallback，可选）
# 手动构造小 MAG 图，逐行 decode 结果和一次性 mag_decode 对比，逐像素一致
python3 -c "from core.lib.mag import mag_decode_row, MagDecodeState; print('OK')"
```

#### 3.3 实机验证步骤

1. 在 transition 期间加 hal_logf 探针：每帧 preload_step 解了多少张、剩余多少 job
2. 记录单张 image_load 耗时（farchive_read_alloc + mag_decode_into 总耗时）
3. 场景切换进来后立刻触发 show sprite——串口观察 image_load cache hit 日志比例
4. 理想结果：transition 期间 preload 完所有图 → 场景切换进来后 cache hit 率 100%

#### 3.4 回滚方案

3.1a / 3.1b / 3.1c / 3.1d 分别可回滚：
- 3.1a：删掉 preload_queue.c + slot 预分配 buffer
- 3.1b：image_load 恢复同步解码；frame.c / transition.c 删掉 preload_step 调用
- 3.1c：layer.c 删掉 preload_push_batch 调用；scene_collect_image_ids 删掉
- 3.1d（fallback）：删掉 mag_decode_row + MagDecodeState（不影响原有 mag_decode / mag_decode_into）

#### 3.5 风险点

| 风险 | 缓解 |
|---|---|
| preload 期间图像被 VM script 同时 access（image_load） | image_load 检查 ready 位：ready=0 时如果 preload_queue 有该 id → 画占位 + retry；绝不能读半成品 |
| 一次性 mag_decode_into 阻塞 preload_step 超过 1 帧（>16ms） | transition 期间每帧可多调几次 preload_step（每帧解多张）；如果单张真的 >100ms，启用 3.1d fallback 逐行拆分 |
| preload 失败（farchive_read_alloc OOM / mag_decode_into 失败） | image_load 降级为同步 mag_decode（当前行为），场景切换时短暂卡顿但不会崩溃 |
| **3.1d fallback** mag_decode_row 拆分引入解码错误（行边界、引用偏移计算错） | 必须做逐行 decode 和一次性 decode 结果对比单测，逐像素一致才算过 |

---

### Phase 4：BGM/音效按场景 preload + 堆水位守卫

**目标**：场景切换进来后 BGM 零延迟启动、音效首次播放零延迟；堆不足时主动降级。

#### 4.0 前置调研清单（**3 项已确认，1 项需实机确认** §五-A.H）

| # | 确认项 | 状态 |
|---|---|---|
| 1 | audio_init 何时载入 BGM 数据——**audio_init 只做硬件检测+patch load+fmseq_init**；BGM 数据在 `audio_bgm_start()` 里按需加载 | ✅ 已确认 |
| 2 | 是否已有 MIDI/FM 格式解析函数——**fmseq 库 API 已齐全**（`fmseq_events()` 喂 MidEvent），但 MIDI → MidEvent 解析逻辑在 `audio_bgm_start` 内部，需拆成独立函数 | ✅ 已确认（需拆函数） |
| 3 | PCM preload 情况——**完全没有 preload**，`audio_snd_play()` / `audio_vc_play()` 每次 `farchive_read_alloc` + `hal_pcm_play` | ✅ 已确认 |
| 4 | **堆水位守卫方案**——**已确认** §五-A.H：Tier 1 try-malloc-fail-skip（零开销，始终有效）+ Tier 2 DPMI Int 31H 0500H 启动 probe（可选，~10 行 inline asm） | ✅ 已确认 |

#### 4.1 详细改动清单

| 文件 | 改动 | 具体操作 |
|---|---|---|
| `audio.c` | 新增 audio_preload_bgm | 只读文件 + 解析 MIDI/FM 格式，存入预加载缓冲区；**不调 OPNA write、不 start** |
| `audio.h` | 新增声明 | — |
| `preload_queue.c` | 扩展 preload 类型 | 除了 IMAGE 类型，新增 BGM 类型 + PCM_SE 类型 |
| `preload_queue.c` | 新增堆水位守卫 | `preload_heap_ok()` —— **Tier 1（主）**：try-malloc-fail-skip（preload 内部每个 job 分配失败就跳过，`preload_evict_low_priority()` 主动释放 pending job）；**Tier 2（可选，~10 行 inline asm）**：引擎启动时调 DPMI Int 31H Function 0500H（`ax=0x0500, es:edi=&buf`），读 buf[0]（Largest available free block in bytes）存全局变量，`preload_heap_ok()` 对比估算，避免注定失败的 malloc 尝试（减少堆碎片） |
| `scene.c` | scene_collect_bgm + scene_collect_se | 给定场景名，返回关联的 BGM 名 + 高频 SE 列表 |
| `layer.c` | scene_end 扩展 preload | transition_start 前除了 image ids，还 preload 下一场景的 BGM + 高频 SE |

#### 4.2 回滚方案

audio_preload_bgm 删掉；preload_queue 的堆守卫和 BGM/SE 类型删掉；layer.c 恢复只 preload image ids。

#### 4.3 风险点

| 风险 | 缓解 |
|---|---|
| audio_preload_bgm 解析时内存分配失败 | 和 image preload 一样，堆水位守卫提前降级 |
| MIDI 解析状态（track position 等）是否需要在 preload 期间正确初始化 | 读 fmseq_open 实现——确认它可以"打开但不 start" |

---

### Phase 5：启动时 preload 场景 1

**目标**：进入游戏第一个场景，零加载等待。

#### 5.0 前置调研清单

| # | 确认项 | 方法 |
|---|---|---|
| 1 | bootmenu Start Game 按钮 → 进入场景 1 的调用链 | grep `bootmenu.*start\|main.*scene\|sc01\|scene01` |
| 2 | bootmenu 收尾期有多少空闲时间可以用来 preload | 实测 bootmenu → game 的切换耗时（hal_logf 探针） |
| 3 | 场景 1 的配置名是什么 | 读 projects/demo-a2/config.toml |

#### 5.1 详细改动清单

| 文件 | 改动 | 具体操作 |
|---|---|---|
| `bootmenu.c` | Start Game 触发 preload | Start Game 按钮回调里调 `scene_collect_all("sc01", ids, count, bgm, ses)` → `preload_push_batch(...)` |
| `bootmenu.c` 或 `main.c` | bootmenu 收尾期 drain preload | bootmenu 显示"加载中..."或淡出期间，多次调 preload_step 直到场景 1 所有资源 ready |

#### 5.2 回滚方案

删掉 bootmenu preload 相关调用。

#### 5.3 风险点

| 风险 | 缓解 |
|---|---|
| bootmenu 收尾期不够 preload 完 | 堆水位守卫 + 降级——如果 bootmenu 收尾期时间不够，进场景后继续 preload_step，但 image_load 会因 cache miss 触发同步 decode（降级为当前行为） |

---

### Phase 6：审计 + 统一守卫（可选）

**目标**：把所有 Naiz Queue 的设计原则固化成测试，防止未来改动回退。

#### 6.1 详细改动清单

| 文件 | 改动 |
|---|---|
| `test_frame_pump.py` 扩展 | 断言 audio_tick_isr 签名含 now_ms_abs 参数 |
| `test_frame_pump.py` 扩展 | 断言 transition.c 内无 for.*step.*frames 阻塞循环 |
| `test_image_cache.py`（新） | 断言 IMAGE_CACHE_SLOTS >= 32；image_cache_clear 只在 image_close 调用 |
| `test_preload_queue.py`（新） | preload_push/pop/heap 守卫基本功能 |
| `test_frame_pump.py` 扩展 | frame.c engine_frame_pump 末尾必须调 preload_step + transition_tick |
| 所有 devdoc | 标注 Phase 编号落地状态 + 版本号 |

---

## 七、Phase 间依赖关系

```
Phase 0 ──→ 无依赖
Phase 1 ──→ 无依赖
Phase 2 ──→ 无依赖
Phase 3 ──→ Phase 1（transition_tick 期间 drain preload）+ Phase 2（cache ready 位）
Phase 4 ──→ Phase 3（preload_queue 基础设施）
Phase 5 ──→ Phase 4（BGM preload 能力）
Phase 6 ──→ Phase 0-5 全部完成后
```

**Phase 0/1/2 可以在同一次 session 内并行动手**，大约 85 行改动、零架构风险。

---

## 八、构建、测试、实机验证统一流程

每个 Phase 完成后：

```bash
# 1. Clean build
cd /home/edo/naiz/core && make clean && make 2>&1 | tee build.log
# 确认 build.log 中零 .err 诊断

# 2. Full pytest（或子集）
cd /home/edo/naiz && python3 -m pytest tools/tests/ -v 2>&1 | tee test.log
# 确认所有新增测试通过，无回归失败

# 3. Rebuild HDI
cd /home/edo/naiz && python3 -m tools.naiz_img.inject --game demo-a2 --yes

# 4. 实机验证（手动）
./makegame.sh test demo-a2 --serial
```

---

## 九、落地记录（2026-10-27）

### 9.1 已落地

| Phase | 内容 | 落点 |
| :---- | :---- | :---- |
| 0 | BGM split drain + 参数化 timestamp | `hal.h`（`BGM_TIMER_B_UNITS 258UL`）、`hal_irq.c`、`audio.c`（`audio_tick_isr(delta_units, now_ms_abs)`、`audio_tick_isr_pending()` 按硬件周期循环重放、子 tick 时间戳步进 16 units） |
| 1 | transition 帧驱动 | `transition.c`（`transition_start/tick/active` + `TransitionState g_transition`，删 `transition_run()`）、`transition.h`、`layer.c`、`frame.c`、`nb.c`（`nb_process()` 闸门） |
| 2 | image_cache 扩容 + ready | `image_cache.c`（`IMAGE_CACHE_SLOTS 32`、slot `ready`、`mark_ready/is_ready`）、`image_internal.h` |
| 3 | preload 队列 + 场景预加载 | 新增 `preload_queue.c/h`（64 项、BG/CHAR 两级）、`nb.c`（`nb_preload_scene()`，`nb_load()` 在 `scene_end()` 前调用）、`image.c`（miss 前 `preload_cancel`）、`frame.c`（`preload_step()`，过渡期双消费） |
| 4 | BGM preload + Tier 1 堆守卫 | `audio.c`（`bgm_load_events()` / `audio_preload_bgm()` / 单条 `g_bgm_pre`，`audio_bgm_start()` 命中接管）、`audio.h`、`nb.c`（`bgm` 命令分支） |
| 5 | 首个场景覆盖 | 无需新代码：`nb_mainmenu.c` 的三处 `scene_switch("nbook001.nb")` 全部经 `nb_load()` → `nb_preload_scene()`，过渡期即预载窗口 |
| 6 | 测试与文档固化 | 新增 `tools/tests/test_naiz_queue.py`（8 条契约）；`test_devdoc_refs.py` 行号锚点同步；`docs/B90` 函数索引更新 |

### 9.2 决策对照（D1-D8，含实施期修正）

- **D1 preload 解码方式**：按 `image_prefetch()` 整图解码 + 插入 cache + pin 实施，未引入 `mag_decode_into` 的 slot 预分配缓冲（32 slot × ~0.5 MB 会吃掉 16 MB 堆）。
- **D2 `ready` 位**：已实施。`insert` 两处置 1，`lookup` 见 `ready==0` 直接当 miss（本设计中解码是整图完成，`ready` 作契约守卫）。
- **D3 `image_load()` miss**：保持同步解码；解码前 `preload_cancel(id)` 摘掉同 id 排队 job。
- **D4 触发点**：`nb_load()` 内、`scene_end()` 之前；复用 `nb.c` 既有的 `nb_get_line` / `nb_parse_line` / `nb_prefetch_key`，不新建模块、不重读 .nb。
- **D5 VM 闸门（实施修正）**：原设计写 `vm_pause_process(); break;`，实测路径上**只保留 `break`**。原因：`main.c` 非 AUTOEXIT 的 input-wait 内层循环只在输入事件时 break，清掉 `VMFLAG_PROCESS` 会让过渡结束后一直停在等待按键，直到玩家按键才继续执行脚本。与 `nb.c` display-yield 分支既有注释（"break, NOT vm_pause_process()"）一致；`transition_tick()` 完成帧仍 `vm_request_process()`。
- **D6 Phase 4 范围**：Tier 1 守卫已实施——`preload_step()` 先弹出再解码，失败返回 0，`frame.c` 的 `if (preload_step() && transition_active())` 保证失败后本帧不再消费第二个 job。BGM 走单条 cache（key[32] + `MidEvent*` + count + len_ms），未命中回落原阻塞读档路径。整脚本扫描时**只预载第一条 `bgm`**：单条 cache 会被该场景开场的那次 `audio_bgm_start()` 取走，继续扫描后一条只会把前一条挤掉。
- **D7 Phase 5**：未硬编码 `nbook001.nb`；场景预加载对每次 `scene_switch()` 生效，已覆盖 mainmenu → 场景 1。
- **D8 常量来源**：`BGM_TIMER_B_UNITS` 上移到 `hal.h` 的 `#if NAIZ_BGM_IRQ` 段，`hal_irq.c` 的本地定义删除，`audio.c` 经 `AUDIO_ISR_PERIOD_UNITS` 复用同一常量。

### 9.3 未做项（后续可评估）

- **PCM / SE 预加载**：共享单通道 + ISR 锁下的 buffer 生命周期，收益小于风险，暂不做。
- **DPMI 0500H Tier 2（动态堆阈值）**：177 中标为可选；启动探针风险大于收益。
- **逐行 `mag_decode_row` 拆分（3.1d）**：177 §D 已判定为 fallback；preload 的价值在时机而非拆循环，故不实施。

### 9.4 验证

- `make -C core` 零 `.err`；`make clean && make` 终检通过。
- `tools/tests/test_naiz_queue.py` 8/8 通过；`test_bgm_timer_units.py`、`test_frame_pump.py`、`test_isr_pump_boundary.py` 全通过。
- `test_devdoc_refs.py` 仅剩既有 12 条「devdoc 118-139 文件已不在仓库」的失败，与本次改动无关。
