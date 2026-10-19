# 155 — BGM 长笛「水泡爆开」杂音根修：note-off→note-on 复用声部触发 OPNA 相位重置（legato tie）

> **状态**：`已完结`（`0.3.042`）——离线 fmgen A/B 已由用户确认为正确修法；实机录音交界瞬态由 17 → 9（`max|diff|` 7691 → 3780）；**最终听感确认待用户**（见 §六 遗留）。
> **版本**：`0.3.042`
> **创建于**：2026-10-19
> **类型**：根因修复（引擎侧）
> **前序**：`153`/`154`（颤音 = NP2kai 输出通路伪影，已收束）、`151`（bell 载波八度）、`123`/`135`（`fmseq`/`fmopn` 通路）
> **结论反驳**：本条推翻「`001/002` BGM 残余杂音全部属 NP2kai 输出通路（`152`/`154`）」的过宽表述——`152`/`154` 处理的是**周期 AM 颤音**；本条处理的是**音符交界处的宽频 click**，二者不同源、可叠加。`152`/`154` 的正文一字未改，仅此说明边界。

---

## 一、症状

`demo-a2` 场景 `001`/`002`（`melody_town` 长笛 BGM）在 NP2kai 实机播放时，可闻**周期性、位置固定的「水泡爆开」杂音（click/pop）**，每次旋律音符交接处一下。与 `152`/`154` 的「持续颤音」（周期增益调制）**听感不同**：后者是持续的金属感抖动，本条是每个音界一次的爆裂声。

关键判据：**位置固定、可重复**——同一首曲每次都在相同的音符交界处出现，与随机/时基抖动无关。

## 二、判定（排除法）

| 已排除 | 证据 |
|---|---|
| flute patch 起音太硬 | 改 `flute.fmp` 为 softbreath（`ar` 放慢、去八度）后**水泡依旧** ⇒ 非包络形状 |
| LFO / `pms` 颤音（`153` 假设） | 临时 `pms=0` 重建后**水泡依旧**（`154` 已证 `pms` 只产生 ~6 Hz 音高颤音，非本杂音） |
| NP2kai 输出通路伪影（`152` 通用结论） | 水泡**随音符边界出现**（`Latencys` 扫频只移动 13.5 Hz AM，不改变水泡位置） |
| ymfm（`tools/vendor/ymfm`） | **ymfm 结构上复现不出该杂音**：`ymfm_fm.ipp` 的 `start_attack()` 会把同一采样内的 keyoff+keyon 合并 ⇒ single/rekey/tie 三份渲染 md5 全同（`a8c44692befe5f07f8f784e6a37eff5f`）⇒ **不能作 oracle** |

**唯一能复现的 oracle = NP2kai 的 `fmgen`**（即用户实机听的那一份）。据此自建忠实 fmgen 渲染器（见 §四）做 A/B。

---

## 三、根因

链路（`core/lib/fmseq.c`）：

1. `fm_note_off()` → `fm_release()` 发 **keyoff**（`$28 = 0`）并立即 `active = 0`（`fm_release` 不清寄存器，慢释放 `rr=8` 的尾音仍在芯片上响）；
2. 下个 note-on 复用同一 FM 声部：分配器把 `active == 0` 的声部当**空闲**，于是直接 `$28 = 0xF0` **keyon**，没有额外 keyoff；
3. fmgen/真机 `Operator::KeyOn()` 在 `eg_phase_ == off || release` 时执行 **`pg_count_ = 0`** ⇒ **相位归零** ⇒ 波形从零点开始出现阶跃 ⇒ **click（水泡）**。

**关键事实**：`assets/demo-a2/bgm/Melody Town Theme.mid`（format 1 / 3 tracks / div 96）的 ch0 长笛线，**每个 note-off 与下一个 note-on 落在同一 tick**（间隔 0 tick = 0 ms）——这正是最坏情形，逐音触发相位重置。若无本修复，谈「改起音包络」必然无效（§二已实测）。

---

## 四、修复（引擎侧 legato tie，`0.3.042`）

**策略：前瞻式 tie**（不用 wall-clock 窗口，避免依赖 `audio_tick()` 60 Hz 心跳的调用节奏）。

- `core/lib/fmseq.h`：
  - `#define FMSEQ_LEGATO_MS 40`（tie 窗口；0 ms 边界被完全覆盖，且远低于任何有意休止）；
  - `FmseqVoice` 新增 `uint8_t tied;`（该声部的 note-off 被挂起、等待 retune）。
- `core/lib/fmseq.c`：
  - `fm_tie_follows()`（`:151`，新纯函数）：从 `cursor + 1` 起扫事件表，`tick_ms > now_ms + FMSEQ_LEGATO_MS` 即停；先遇到**同 MIDI 频道**的 note-on → 返回 1（tie），遇到同频道 note-off/vel-0 → 返回 0。
  - `fm_note_off()`（`:309`）：签名增 `uint32_t now_ms, int cursor`；无 pedal 且 `fm_tie_follows()` 为真时置 `tied = 1` 并**跳过 keyoff**（尾音继续响）。
  - `fm_note_on()`（`:225`）：开头新增 tie 分支——优先选 `tied && midi_ch` 中 `age` 最大者，**重写除 `$28` 外的全部寄存器后直接 return**（`fm_write_patch`），**不 keyon** ⇒ 相位不重置、音高平滑滑到新音（legato）。
  - `fm_release()`（`:139`）与正常分配路径（`:249`/`:305`）均清 `tied`；`fmseq_init()`（`:519`）/`fmseq_stop()`（`:581`）清全部 `tied`。
  - `dispatch()`（`:464`）签名增 `int cursor`；`fmseq_pump()`（`:557`）传 `seq->cursor`。

**行为不变的情形**：间隔 > `FMSEQ_LEGATO_MS` 的真实休止仍走 keyoff + keyon；pedal（`CC64`）路径优先于 tie；旧曲若本无近触边界，行为零变化。

---

## 五、验证

- **离线 fmgen A/B（用户已确认）**：自建 `/tmp/opencode/fmgenbench/fmgenbench`（复刻 fmbench 寄存器逻辑 + NP2kai `FM::OPNA`；`Init(7987200, 44100, false, 0)` + `SetReg(0x22, 0x0A)`；32-bit stereo；bank1 = `reg+0x100`）。对 `melody_town` 片段：**rekey（旧行为）5 处瞬态、tie（`--legato-ms 40`）0 处** ⇒ 用户确认「norekey 是对的」。
- **单元测试**：`tools/tests/test_fm_seq.py` 18 → **21 passed**，新增
  - `test_legato_tie_retunes_without_rekey`（无 keyoff、单一 keyon、两次 retune）；
  - `test_legato_tie_spans_pump_passes`（**跨 pump pass** 挂起——真实引擎节奏：note-off 与 tie note-on 落在不同 `fmseq_pump` 调用）；
  - `test_legato_gap_beyond_window_rekeys`（> 窗口 → keyoff + 新 keyon）。
- **构建**：`make -C core` 0 诊断（`core/*.err` 全空）。
- **全量**：pytest **810 passed / 1 skipped**；`./start.sh fullaudit` **7/7**。
- **实机录音**：`tools/diag/np2kai_audio.py --game demo-a2 --after BGM`。同一 flute patch（softbreath），旧引擎 vs 新引擎：交界瞬态 **17 → 9**、`max|diff|` **7691 → 3780** —— 与「~8 处边界 click 消失、9 处音符起音保留」的签名一致。WAV：`/tmp/opencode/ab/BEFORE_0.3.041.wav`、`/tmp/opencode/ab/AFTER_0.3.042.wav`。

---

## 六、防复发与遗留

**防复发**：`test_fm_seq.py` 三条 tie 守卫删即红；`fm_tie_follows` 为纯函数（无 `outb`），可在主机穷举。

**遗留**：
1. **最终听感确认待用户**（判据：`001/002` 长笛逐音边界的水泡消失；`003/004` 若无同型近触边界则本不受影响）。
2. `FMSEQ_LEGATO_MS = 40` 为常量；若未来出现 40–80 ms 的**有意**近触分隔线被误 tie，可下调。
3. 本修复只覆盖 FM 通路；MIDI（MPU-401）通路的近触边界由外部音源决定，引擎不干预。
