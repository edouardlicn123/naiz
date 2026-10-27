# 177 — Naiz Queue：统一执行模型（Drain + Preload 分离时钟与消费）

> **状态**：**设计阶段**（尚未落地，Phase 0-6 待执行）
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

## 六、实施计划（Phase 0-6）

每个 Phase 独立可验证——完成后跑 `make -C core && pytest`，通过才进下一个。

### Phase 0：BGM split drain + 参数化（~20 行改动）

| 文件 | 改动 |
|---|---|
| `audio.c` | `audio_tick_isr` 加 `now_ms_abs` 参数；内部用参数代替读 `hal_wallclock_smooth_ms()`；`audio_tick_isr_pending` 实现 split drain 循环 |
| `audio.h` | 声明签名同步 |
| `test_frame_pump.py` | 新增断言：ISR drain 路径 FM 调用必须传参数化 timestamp |

**前置**：无。Phase 0 是完全自包含的改造。
**验证**：`pytest` 全过；实机听 BGM stall 后节奏是否均匀。

### Phase 1：transition 从 for 循环改 frame pump 驱动（~50 行改动）

| 文件 | 改动 |
|---|---|
| `transition.c` | 拆 `transition_run()` 为 `transition_start()`（只初始化 g_transition 状态，立即返回）+ `transition_tick()`（每帧 render 1 step，内部调 audio_tick_isr_pending 正常 drain） |
| `transition.h` | 新增 transition_start / transition_tick 声明 |
| `layer.c` | `scene_end()` 从调 `transition_run()` 改调 `transition_start()` |
| `frame.c` | `engine_frame_pump()` 末尾加 `transition_tick()` |
| `test_frame_pump.py` | 新增断言：transition_run 内不得出现 for 循环硬阻塞 |

**前置**：无。Phase 1 和 Phase 0 互不依赖，可并行。
**验证**：`pytest` 全过；实机场景切换期间 BGM/动画/打字机继续跑。

### Phase 2：image_cache 扩容 + 去掉 scene_clear（~15 行改动）

| 文件 | 改动 |
|---|---|
| `image_cache.c` | `IMAGE_CACHE_SLOTS` 8→32；slot 结构加 `ready`；删除 `image_cache_clear()` |
| `image_cache.h` | 删除 image_cache_clear 声明；新增 `image_cache_mark_ready` / `image_cache_bump_priority` |
| `image.c` | 删除 `image_cache_clear()` 调用 |
| `layer.c` | 删除 scene_end 里可能的 image_cache_clear 调用 |

**前置**：无。Phase 2 和 Phase 0/1 互不依赖。
**验证**：`pytest` 全过；实机连续切换 3 个场景，立绘不再每次重新解码（看串口 `image_load cache hit` 日志）。

### Phase 3：image_decode_step + preload_step 队列（~80 行改动）

| 文件 | 改动 |
|---|---|
| `image.c` | 拆 `mag_decode` 为 `mag_decode_tile()`；新增 `image_decode_step()`；`image_load()` cache miss 时画占位 + retry 标志 |
| `image.h` | 新增 image_decode_step 声明 |
| `preload_queue.c`（新） | preload 队列管理（push/pop/heap 守卫/优先级） |
| `preload_queue.h`（新） | 声明 |
| `frame.c` | `engine_frame_pump()` 末尾加 `preload_step()` |

**前置**：Phase 2（image_cache 扩容 + ready 位）。
**验证**：`pytest` 全过；实机立绘加载每帧 ≤1ms（串口计时）；stall 不再错过 vblank。

### Phase 4：过渡期间 preload 下一个场景资源（~60 行改动）

| 文件 | 改动 |
|---|---|
| `scene.c`（或新增） | `layer_scene_load_preload()` 解析场景配置、收集 image ids、推 preload 队列 |
| `transition.c` | `transition_start()` 里调 `layer_scene_load_preload()`；`transition_tick()` 里持续 drain preload_step |
| `frame.c` | transition_tick 已在 Phase 1 接入，preload_step 已在 Phase 3 接入 |

**前置**：Phase 1 + Phase 3。
**验证**：场景切换进来后所有立绘全是 cache hit（串口日志）；零感知卡顿。

### Phase 5：BGM/音效按场景 preload + 堆水位守卫（~40 行改动）

| 文件 | 改动 |
|---|---|
| `audio.c` | 新增 `audio_preload_bgm()`（只读不 start）；`audio_start_preloaded_bgm()` |
| `audio.h` | 新增声明 |
| `preload_queue.c` | 堆水位守卫逻辑 |
| `scene.c` | layer_scene_load_preload 扩展到 BGM 数据 |

**前置**：Phase 4。
**验证**：场景切换后 BGM 零延迟启动；音效首次播放零延迟。

### Phase 6：启动时 preload 场景 1（~20 行改动）

| 文件 | 改动 |
|---|---|
| `bootmenu.c` | Start Game 按钮 → 调 `layer_scene_load_preload("sc01")`；bootmenu 收尾期 preload_step drain |
| `main.c` | bootmenu 结束后调 `preload_step()` 直到场景 1 资源全 ready |

**前置**：Phase 5。
**验证**：进入游戏第一个场景，零加载等待。

---

## 七、最终效果量化

### 7.1 每类排队的改善

| 排队类型 | 当前 | Naiz Queue 后 | 改善幅度 |
|---|---|---|---|
| **A. 同步阻塞 image_load 卡主线程** | 30-50ms 阻塞 → 错过 1-2 vblank | cache hit：0ms；preload 完成：0ms；decode_step：每帧 ≤1ms | **消除 95%+** |
| **A. 场景加载卡主线程** | 50-80ms | preload 期间悄悄解完 → 0ms | **消除 100%** |
| **B. transition for 循环阻塞** | 800ms 内主线程被独占 | transition_tick 每帧 render 1 step → frame pump 照走 | **消除 100%** |
| **C. burst drain 后空窗** | FM 事件一次性派发 → 后续空窗 | split drain 均匀派发 → 和 ISR tick 对齐 | **消除 100%** |

### 7.2 各事务的最终表现

| 事务 | 当前 | Naiz Queue 后 |
|---|---|---|
| VRAM 刷新 | 每 50ms vblank_wait | 不变（就是 pace） |
| 打字机 | 每帧推进，display-paced | 不变（本来就不阻塞） |
| 动画 | stall 后暴冲 | vclock 匀速 → anim_tick 每帧均匀推进 |
| 立绘切换 | 首次 30ms 卡顿 → 后续 cache hit | 全部 preload → 0ms |
| 场景切换 | 50-80ms 卡顿 | transition 期间 preload → 0ms |
| BGM 节奏 | stall 后 burst drain → 抖动 | split drain + 参数化 timestamp → 均匀 |
| 音效/语音 | 首次播放微延迟 | preload → 零延迟 |
| 过渡期间 | 只有硬塞进去的事务能跑 | 所有事务正常 drain |

### 7.3 仍不可消除的下限

| 下限 | 原因 | 是否可感知 |
|---|---|---|
| 50ms 帧 pace | GDC vblank 硬件决定 | ❌ 就是游戏帧率 |
| DPMI 微秒级抖动 | DOS/4GW 投递 ISR 的极少数延迟 | ❌ 微秒级，非毫秒级 |
| 磁盘硬等待（极端） | farchive_read 遇到坏块 | ⚠️ 极端场景，preload_step 守卫降级 |

---

## 八、规约与测试

### 8.1 新增测试

每个 Phase 完成后新增对应的守卫测试，防止未来改动回退：

| Phase | 测试文件 | 守卫内容 |
|---|---|---|
| 0 | `test_frame_pump.py` 扩展 | ISR drain 路径 FM 调用必须传参数化 timestamp（grep `audio_tick_isr(` 参数数量） |
| 1 | `test_frame_pump.py` 扩展 | transition.c 内不得有 `for.*step.*frames` 硬阻塞循环 |
| 2 | `test_image_cache.py`（新） | cache slots ≥ 32；image.c 不得调用 image_cache_clear |
| 3 | `test_frame_pump.py` 扩展 | frame.c engine_frame_pump 末尾必须调 preload_step；mag_decode 必须有 tile 版本 |
| 4 | `test_preload_queue.py`（新） | preload_queue 基本功能 + 优先级 + heap 守卫 |
| 5 | `test_frame_pump.py` 扩展 | audio_preload_bgm 存在且被 scene_preload 调用 |
| 6 | `test_frame_pump.py` 扩展 | bootmenu Start Game 后立即调 scene_preload |

### 8.2 devdoc 编号规划

| 编号 | 内容 | 状态 |
|---|---|---|
| 177（本文件） | Naiz Queue 完整设计 | 设计中 |
| 178 | Phase 0：BGM split drain 实施记录 | 待写 |
| 179 | Phase 1-3：transition + image_cache + decode_step 实施记录 | 待写 |
| 180 | Phase 4-6：preload 全链实施记录 | 待写 |

### 8.3 CHANGELOG 规约

每个 Phase 落地后在 CHANGELOG.md 顶部追加条目，标注版本号 + Phase 编号 + 关键改动点。

---

## 九、风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| mag_decode_tile 拆分引入解码错误（tile 边界、调色板计算） | 中 | 画面错位或花屏 | Phase 3 加 tile 边界单测 + 实机逐 tile 对比完整 mag_decode 输出 |
| preload 期间图像资源被同时 access（VM script 突然 dispatch image_load） | 低 | 读到半成品 | image_cache 加 ready 位；image_load 检查 ready 后才返回 |
| DOS/4GW 堆不足导致 preload 失败 | 低 | 降级为按需加载（和当前一样） | 堆水位守卫主动降级，不崩不卡 |
| split drain 循环内调用 audio_tick_isr 增加 CPU 时间（从 1 次变 12 次） | 极低 | 每帧多花 ~0.5ms | split drain 每次 audio_tick_isr(258) 内部 FM 推进只覆盖 16ms 范围，fmseq_pump 事件派发量和原来一次 drain 3096 的总量相同，只是调用次数增加 |
| transition 改 frame pump 后用户在过渡期间输入导致状态错乱 | 低 | 提前操作了下一场景的资源 | transition_tick 期间 VM dispatch 暂停（原有设计就是不可交互），输入只更新但不 dispatch |

---

## 十、命名与定位

**Naiz Queue**（ナイツ・キュー）是本引擎的统一执行模型，定位为：

> 让 PC-98 单线程 DOS/4GW 环境下的所有时间敏感事务（BGM、动画、立绘、音效、语音、过渡、打字机）在运行过程中**尽可能不暂停、不冲突**。

核心理念用一句话：

> **时钟独立推进、生产只记账、消费均匀 drain、重操作拆小步、资源提前 preload。**

这不是 BGM 的单一修复，而是整个引擎的执行架构升级——从"同步泵入、一次性处理"改成"异步排队、均匀消费"。
