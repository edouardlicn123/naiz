# 179 — BGM 启动回绕根因修复：drain 时间戳钳制 wall0

> **状态**：**已实施**——2026-10-28
> **创建于**：2026-10-28
> **承接**：`devdocs/177`（Naiz Queue 统一执行模型，本回归由其 split drain 引入）、`devdocs/176`（ISR 路径 FM 静音根因）
> **影响**：`core/engine/audio.c`（仅 `audio_tick_isr`）、`tools/tests/test_naiz_queue.py`（新增回归守卫）

---

## 一、问题定义

177 落地后用户报告两类 BGM 症状（demo-a2）：

1. **场景 001/002（melody_town）：BGM 有时不发声** —— 进场景后前几秒没有 BGM，之后乐曲从半途开始
2. **场景 003/004（icy_garden）：第一个音被拖得很长很长** —— 开场所"听到的第一个音"是乐句中途的长音

两症状均间歇出现（"有时候"），且与**曲目**相关而非场景逻辑相关。

## 二、根因

### 2.1 split drain 的时间戳可以早于 wall0

177 的 `audio_tick_isr_pending()`（[audio.c](../core/engine/audio.c)）把积攒的 Timer-B 周期拆成 ≤ 一个硬件周期的 chunk 逐个回放，时间戳从过去走向现在：

```c
now = hal_wallclock_smooth_ms();
start = (now > units / 16UL) ? now - units / 16UL : 0UL;  /* 回放窗口起点在过去 */
while (units > AUDIO_ISR_PERIOD_UNITS) {
    audio_tick_isr(AUDIO_ISR_PERIOD_UNITS, start);        /* chunk 时间戳 < 当前时刻 */
    ...
}
```

而 `audio_bgm_start()` 是在 VM 脚本执行（一帧中段）时设置 `g_bgm.wall0 = hal_wallclock_smooth_ms()` 的。于是**BGM 启动后的第一次 drain**：上一帧积攒的 1~3 个周期（NP2kai ~20Hz 帧 × 61.9Hz tick）回放窗口起点 `start = now − units/16`，可能比几分钟前……不，比**几十毫秒前**设置的 `wall0` 还早 0~32ms——取决于帧内相位，故**间歇性**。

### 2.2 无符号减法回绕 → 开头事件簇瞬时爆发

`audio_tick_isr()` 内：

```c
cur = now - g_bgm.wall0;      /* now < wall0 时回绕成 ~4.29e9 */
fmseq_pump(g_fm_seq, &g_fm_sink, cur);
```

`cur ≈ 42.9 亿` 使 `fmseq_pump` 认为"全部待发事件都到期"，一次 pump 立即派发 `FMSEQ_PUMP_MAX_PER_CALL`(16) × chunk 数个事件。

### 2.3 与两症状的对应（实测 MIDI 数据佐证）

解析 `games/demo-a2/AUDIO.DAT`：

| 曲目 | t=0 事件簇 | 前 16 个事件覆盖 | 爆发后果 |
|---|---|---|---|
| melody_town | 13 个事件（含首音 on@0 / off@422.5ms） | 0 ~ 845ms | 引子两音被压成一声咔哒 → 前几秒静默 → **"有时候不发声"** |
| icy_garden | 10 个事件（含首音 on@0 / off@369.8ms） | 0 ~ 750ms | 引子被跳过，乐句从 750ms 中段进入，听到的"第一个音"是乐句中途长音 → **"第一个音被拖得很长"** |

大改前 `audio_tick_isr` 自行读取**当前**时钟（恒 ≥ wall0），不存在此回绕——这是 177 引入的回归。

## 三、修复

`audio_tick_isr()` 在 `if (!g_bgm.active) return;` 之后、计算 `cur` 之前，把回放时刻钳制到 BGM 自己的起点：

```c
if (now < g_bgm.wall0)
    now = g_bgm.wall0;
```

- **不破坏单写者原则**：只改 chunk 时间戳，不动 vclock 推进（`hal_irq.c` 仍是唯一时钟写者）
- **不影响 PCM 步长**：钳制发生在 `hal_pcm_advance_units` 之后
- **语义**：先于 wall0 的 chunk 全部携带 wall0 → `cur` 从 0 开始，t=0 事件簇（含首音）在第一个 chunk 正常发声，其后 note-off 按虚拟时钟准点到达；两个后端（FM/MIDI）同时覆盖
- **协作泵路径恒不触发**：其时间戳在 wall0 之后读取；rewind 时 `fmseq_loop_start` 保证 wall0 ≤ now，钳制在循环中也不会误触发

## 四、回归守卫

`tools/tests/test_naiz_queue.py::test_audio_tick_isr_clamps_replayed_timestamp_to_wall0`——断言钳制存在，防止后续重构再次移除。

## 五、验证

- `pytest tools/tests/test_naiz_queue.py`：9 passed（含新守卫）
- 全量套件：851 passed；15 项失败均为既有问题（devdoc 重命名残留 / 版本号分叉 / engine.exe 过期），与本次改动无关
- `core/build.sh` 重建 engine.exe + engine_a.exe；`makegame.sh make demo-a2` 重打 HDI；`makegame.sh test demo-a2 --serial --auto` 过机验证
