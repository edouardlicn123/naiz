# 152 — BGM 残余「电流声/颤音」判别取证：真实循环时基 + LFO + 抢音

> **状态**：`已完结`（`0.3.040`）——Phase 1 已执行并回填 §六；结论：残余可测分量（~13.5 Hz AM）来自 **NP2kai 输出通路**（随 `Latencys` 移动），非引擎音乐输出；**经用户裁决收束引擎侧 A/C 轴排查**。
> **版本**：`0.3.039`（立项版本）
> **创建于**：2026-10-19
> **类型**：诊断 + 取证计划（承 `149`/`150` 的三轴归因 → 收敛到残余伪影）
> **前序**：`151`（bell 载波八度修复 = B 轴）、`150`（录制对比工具链与归因协议）、`149`（执行计划 Phase A/C）、`148`（三轴）、`146`、`143`/`142`、`135`（LFO）、`123`（FM 通路）
> **来源/坐标**（立项时 `0.3.039`）：`core/engine/main.c`、`core/engine/nb.c`、`core/lib/fmseq.c`、`core/lib/fmopn.c`、`core/plat/hal_audio.c`、`core/lib/vclock.c`、`assets/demo-a2/fm/flute.fmp`、`tools/naiz_audio/spectrum_report.py`、`tools/diag/np2kai_audio.py`

---

## 一、背景与现状

`151` 修复了 `bell.fmp` 的载波八度错误（B 轴），实机反馈 **003/004（icy_garden）电流声「减少」**。用户裁决：

| 曲目 | 用户反馈 | 本轮处置 |
|---|---|---|
| 003/004（icy_garden/bell） | 电流声**减弱，仍有** | **记录为「待后续优化」，本轮不改** |
| 001/002（melody_town/flute） | **仍**是电流声/颤音 | 本轮取证目标 |

**关键约束（已证）**：`001/002` 频谱与 GM 几乎一致（引擎 `>5kHz` 0.0008 / 质心 726 Hz vs GM 0.0006 / 902 Hz，`151 §二`）⇒ 残余**不是亮度/谐波/宽带噪声**，而是**时域伪影**（幅度调制、音高调制或点击）或**系统性时基**。

**已有测量的缺口（本文件动机）**：`150 §六` 的时基测量跑在 `BGM_BENCH` —— 它是**纯紧循环**（`core/engine/main.c` 的 `#if BGM_BENCH` 分支仅 `for(;;) engine_frame_pump();`，不渲染、不预取、不跑脚本）。因此测得的派发抖动 **6.5–8.2 ms 是最乐观值**；用户听到 flutter 的「静置对白页」跑的是**真实主循环**（`main.c` 输入等待内循环：`engine_frame_pump` + `nb_prefetch_lookahead` + kbd/mouse 轮询），含预取 I/O 尖峰 ⇒ **A 轴可能在真实循环里才暴露，而 bench 恰好测不到**。

---

## 二、候选根因

| 假设 | 机制 | 定位坐标 | 判别法 |
|---|---|---|---|
| **H1 · C 轴 LFO** | `flute.fmp` `pms=2`（~6.6 Hz 音高颤音）；`hal_audio.c` 全局 `$22=0x08|FM_LFO_RATE` 使能 ⇒ PMS 生效 | `assets/demo-a2/fm/flute.fmp`、`core/plat/hal_audio.c` | 录「LFO 全局关」A/B |
| **H2 A 轴 时基** | 真实主循环 pass 率低于紧 bench ⇒ 音符派发量化更粗、抖动更大（系统性，四曲皆中） | `core/lib/vclock.c`、`core/lib/fmseq.c` 派发、`core/engine/frame.c` | 真实循环下测 `[VC]`/`[BGMT]` |
| **H3 抢音/点击** | 断奏快 + 分配器耗尽时 `fm_send_keyoff` **force-steal 硬切**旧音（`core/lib/fmseq.c` 注释 "force-steal: cut the old note"），或 keyon 相位/包络不连续 | `core/lib/fmseq.c` 分配器 | 加命中 trace + 录音包络 |
| **H4 残余 voicing** | 003/004 仍偏亮（`151` 后 `>5kHz` 0.0123 vs GM 0.0041） | `assets/demo-a2/fm/bell.fmp` | 频谱（已测，低优先） |

---

## 二·五、判别原理（为何先测真实循环）

`BGM_BENCH` 与真实循环的**唯一差异是每 pass 工作量**：真实循环额外跑 `nb_prefetch_lookahead()`（可能触发脚本扫描与图片解码 I/O）与输入轮询。若这是伪影源，则**只在真实循环暴露**。故 Phase 1 必须复刻真实循环的「静置首张对白页」状态。

---

## 三、Phase 1 — 真实循环时基取证（本文件主交付）

### 3.1 为何需要 `BGM_IDLE` 模式

无输入 ⇒ 无法从 bootmenu 进游戏（`logo.nb→op.nb` 是标题菜单，等输入）；且 xdotool 在无 WM 下进不了 guest。故新增编译期 `BGM_IDLE`（默认 0）：跳过 bootmenu → `scene_switch(<BGM_IDLE_SCENE>, SCENE_SWITCH_INIT)` 直进剧情节（其脚本 `bgm(){…}` 起播）→ **落入正常主循环**，跑到首张对白页后停在**输入等待内循环**（`core/engine/main.c` `input_drain_boundary()` 后的 `for(;;)`）——即用户所述场景。

### 3.2 采集

```
EXTRA_DEFS="-DBGM_IDLE=1 -DBGM_IDLE_SCENE=nbook001 -DBGM_TICK_TRACE=1"
./makegame.sh build demo-a2 && ./makegame.sh make demo-a2
# 无头：SDL_AUDIODRIVER=disk -> raw 录音；--serial -> [VC]/[BGMT]
```

### 3.3 判据（决策门）

| 观测 | 结论 | 去向 |
|---|---|---|
| 真实循环 `[BGMT]` 抖动 **≫ 8 ms**（vs 紧 bench） | **H2 成立**（时基） | Phase 3-A |
| 抖动仍 ≈ bench（~ms 级） | H2 排除 | 转 Phase 2（H1/H3） |
| 录音包络呈**周期 AM**（~6.6 Hz） | **H1**（LFO 颤音） | Phase 3-B |
| 包络呈**无规尖峰**（click） | **H3**（抢音/点击） | Phase 3-C |

---

## 四、Phase 2 — 判别式 A/B（据 Phase 1 分支）

- **H1**：临时 `hal_fm_init()` 写 `$22=0`（LFO 全局关）与 `FM_LFO_RATE` 变体各录一次 001/002；杂音消失/变化即坐实。
- **H3**：`fmseq.c` 分配器加 `force-steal` 计数 trace，统计命中率与时刻；对照录音包络尖峰。

---

## 五、Phase 3 — 修复候选（据判别定夺）

| 分支 | 候选修法 | 代价/风险 |
|---|---|---|
| A（时基） | 细于 DOS 10ms tick 的插值派发；vclock 路径调参；方案 C（Timer-B 中断，`134`） | C 在本环境不可验证；A 需重测 |
| B（LFO） | 调 `flute.fmp` `pms` 深度 / 降 `FM_LFO_RATE` | 低，离线可验 |
| C（抢音） | 分配器策略（避免硬切 / 保留释放尾）/ 脚本层避免重叠 | 中，需回归 |

---

## 六、实测（已回填）

### 6.1 采集条件

`BGM_IDLE=1`（`main.c`）+ `EXTRA_DEFS`，`nbook001`（`melody_town`，flute；`bgm(){melody_town}`）与 `nbook003`（`icy_garden`，bell；无 LFO）对照。无头：`SDL_AUDIODRIVER=disk` → `S16/2ch/44100`（NP2kai `SampleHz=44100`，已由 `~/.config/wxnp21kai/wxnp21kai.toml` 证实；早前按 48000 读数的频率**偏高一档**，本文一律按 44100 复算）。产物 `/tmp/opencode/idle_nbook001.{raw,log}`（46–50 s）、紧 bench `bench.raw`/`bench_icy.raw`。

### 6.2 真实循环时基（H2）

- 真实循环 `[VC]` 稳态 **`step=574` 单位 = 35.9 ms/pass ≈ 27.9 Hz**（起始瞬态 823→1448）；`BGM_BENCH` 紧循环 **`step=55` = 3.4 ms/pass ≈ 291 Hz**。故 idle 比 bench 慢约 **10×**，但 idle 仍远高于「用户静置对白页」应有的卡顿。
- `[BGMT]` vs MIDI 拟合：`engine_t = 0.9977·midi_t + 1210.7` ⇒ **tempo ratio 0.998（正确）**；残差 **std 21.4 ms / p95 35.0 ms**（bench 为 6.5–8.2 ms ⇒ ~3×）。**H2 部分成立**（真实循环派发抖动确实比 bench 大），但**幅度不足以解释「电流声」**（见 6.3）。

### 6.3 录音包络谱（H1/H3）— 主发现

- **GM 参考**（`TimGM6mb` 渲染 `melody_town`）：包络峰只有 **1.2–2.4 Hz**（音符率），无高频调制。
- **引擎录音**：包络谱主导 **~13.4–13.8 Hz**（rel 6–18×），外加 1.8/29.5 Hz。**GM 无此分量**。
- **判别四连（逐一排除引擎）**：

| 变量 | 变更 | 13.5 Hz 是否存在 | 结论 |
|---|---|---|---|
| 音色 | flute（`pms=2`，有 LFO） vs bell（`pms=ams=0`，无 LFO） | **两者都有** | 排除 H1（LFO） |
| 循环速率 | 291 Hz（紧 bench） vs 28 Hz（真实 idle） | **两者都有，频率相同** | 排除「每 frame 寄存器重写」类周期 |
| FM 核 | `USEFMGEN=true`（fmgen） vs `false` | **两者都有** | 排除 FM 核 |
| 输出延迟 | `Latencys`=30 / 93 / 250 | **频率随之移动：8.3 / 13.5 / 5.7 Hz** | **锁定 NP2kai 音频输出通路** |

- **全频带**：`<300`/`300–3k`/`>3k` 三段包络**都在 13.4 Hz 有峰**（`an3.py`）⇒ 这是**对整段输出的增益（AM）调制**，**非 click/断续**（click 只会出现在宽带差分）。
- **无 HDD 静音采集**（`sil.raw`）：除开机 beep 外近零；beep 仅 ~0.1 s 太短无法分辨 13.5 Hz（`an4.py`），故未单独复证「非引擎纯音」，但上表已由「引擎设置全改而 13.5 Hz 不随动、仅 `Latencys` 令其移动」充分定向。

### 6.4 结论

1. **轴 B（`bell.fmp`）是真实且已修**（`151`，频谱质心/高频比实测下降）——本轮复算不推翻。
2. **残余「电流声/颤音」的无头可测分量（~13.5 Hz AM）来自 NP2kai 输出通路**（实现/采样缓冲相关，随 `Latencys` 移动），**不是引擎的音乐输出**。引擎侧（轴 A 时基 / 轴 C LFO）改动**不能**消除该分量。
3. 真实循环 `[BGMT]` 派发抖动 std 21 ms（H2）**存在**，但属**次级**，且未在包络谱留下对应特征（29.5 Hz 峰强度远低于 13.5 Hz）；其可闻性待定，交由用户裁决是否仍修。
4. **方法论警示**：无头 `SDL_AUDIODRIVER=disk` 采集**自带此 13.5 Hz 伪影**，凡以此法判定「引擎音频伪影」必须先过 `Latencys` 扫频以剔除。

### 6.5 用户裁决（已定）

用户裁决 **收束引擎侧音频排查**：接受残余可测分量以 NP2kai 输出伪影为主的结论，**不再执行 A/C 轴**；恢复发布引擎。

---

## 七、遗留

- **003/004（bell）**：`151` 后仍有可闻电流声，**记为「待后续优化」**（`151 §六` 同步），非本轮目标。
- **模拟器侧缓解（未采纳）**：`Latencys` 可移动该 AM 频率（250 → 5.7 Hz 更低更不易闻），但属模拟器设置、非引擎可控，未纳入本轮。
- **A 轴次级项**：真实循环 `[BGMT]` 派发残差 std 21.4 ms（bench 6.5–8.2 ms）确实偏大，但未在包络谱留下主导特征；**未修**（可闻性未证），若日后有价值再立新案（判据须绕开 13.5 Hz 伪影）。
- **方法论**：`BGM_IDLE` 诊断模式保留于 `core/engine/main.c`（编译期默认关，用途同 `BGM_BENCH`），供日后复现真实循环采集；无头音频采集须先过 `Latencys` 扫频剔除 13.5 Hz 伪影。
