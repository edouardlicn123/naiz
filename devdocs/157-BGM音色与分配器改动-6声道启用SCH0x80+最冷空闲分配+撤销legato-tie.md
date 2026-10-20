# 157 — BGM 音色与分配器改动：启用 6 声道（$29=0x80） + 「最冷空闲」分配 + 撤销 legato tie + 场景切换 age 复位

> **状态**：`已完结`（`0.3.047`）——离线 fmgen A/B：melody_town `rms 1689 → 2300`（+0.22 dB 与 notie 同），`max|diff| 901 → 901`（零 click）；icy_garden 多声部用上 voice 3-5，`rms 3487 → 4318`；场景切换起点 click 由 `clicks=4753 → 0`。pytest **819 passed, 1 skipped** + fullaudit 全绿。
> **版本**：`0.3.047`
> **创建于**：2026-10-19
> **类型**：修复（引擎侧 FM 通路）
> **前序**：`155`（legato tie）→ 本文推翻其保留的过度切换，采用「冷声分配 + 放弃同声部重击」取舍；`135`（$22/LFO）、`123`（fmseq）、`138`（音高八度）、`152-154`（NP2kai 输出通路）
> **依赖证据**：`devdocs/138` 低八度根因、`tools/tests/test_fm_voice_enable.py`（$29 + bgm_start stop 守卫）、`tools/tests/test_fm_seq.py`（分配器 + stop 复位守卫）、离线 `seqdump2+chplay`（fmgen 核，双场景同芯片实例）复核

## 一、症状与发现

0.3.042（`devdoc 155`）的 legato tie 成功消除「水泡」click，但也大幅压低 `melody_town`（单声部旋律）的响度（`rms 1689.4 →` 100ms 后快速衰减）。与此同时，排查中发现：

1. **YM2608 六声道未启用**：手册 `$29` D7(SCH)=0 → 只出 3 声道。引擎 `hal_fm_init()` 从未写 `$29`，NP2kai fmgen 也默认不强制 SCH=1；导致 voice 3-5 永远静音。`icy_garden` 有 34/287 个音被分到该组 → **多声部丢音**。
2. **OPNA keyoff→keyon 会复位算子相位**：fmgen `Operator::KeyOn()` 在 `off||release` 态 `pg_count_=0`，直接重击**刚释放**的同一声部会产生 click（`155` 所述）。但要完全回归响度，就不能同声部重击。
3. **场景切换后起点 click（用户报告）**：同一首 `melody_town`，场景 1 起播干净、场景 2 起播有「水泡」click。离线双场景 oracle（`seqdump2`，同一 fmgen 芯片实例：场景 1 播放 → `fmseq_stop` → 场景 2 从事件 0 重启）复现并定位：`fmseq_stop()` 重置了 `cursor`/`last_tick`/`last_age`，**却未重置各声部 `fm[i].age`**。场景 1 结束时 age 残留为大值，场景 2 起播的多个音被「最冷空闲」扫描反复选到**同一个残留声部**（keyon 全挤在 t=stop 同一毫秒），连续 `keyoff→keyon` 重击 release 尾音 → click。修复（`stop` 补 `fm[i].age = 0`，对齐 `fmseq_init`）后 keyon 恢复 0,1,2,3,4,5 轮转，`clicks 4753 → 0`。

离线 oracle（`seqdump` dump 真实引擎写流 → `chplay` 灌入 fmgen OPNA 核，32-bit stereo）给出：

| 配置 | melody_town rms | melody_town max\|Δ\| | 说明 |
|---|---|---|---|
| tie（current 0.3.042） | 1689.4 | 901 | 无 click，但 EG 尚在衰减时被 retune |
| 禁 tie（撤回） | 2359.0 | 3890 | 恢复响度，但同声部 0ms 重击 → click |
| `$29=0x80` + 最冷空闲分配 + 撤 tie（本案） | 2300.1 | 901 | **响度与 notie 差 −0.22 dB，0 click** |

icy_garden：voice 3-5 原本全部 0（keyon 0）。加 `$29=0x80` 后，4/5/6 三个 select D/E/F 均有 121–129 次 keyon，`rms 3486.5 → 4317.8`。

## 二、修复

### 2.1 `core/plat/hal_audio.c::hal_fm_init()`
写入 `$29 = 0x80`。bits 0-5 保留 0（不启用 OPNA 计时器 IRQ，现有代码轮询心跳）。
```c
/* Enable all six FM voices (reg $29 bit7 = SCH). */
hal_fm_write_reg(0, 0x29, 0x80);
```

### 2.2 `core/lib/fmseq.h`
- 移除 `FMSEQ_LEGATO_MS 40`。
- `FmseqVoice` 移除 `uint8_t tied;`。
- 注释更新：steal 顺序改为「coldest free voice, then pedal-pending, then oldest」；新增 `devdoc 156` 的 click-free 原理（不重击刚释放的声部）。

### 2.3 `core/lib/fmseq.c`
- `fm_release()`：不清 `tied`（已删字段）。保留 keyoff + `active=0` + `sustain_pending=0`。
- **删** `fm_tie_follows()` 全部实现（纯前瞻，曾用于 0-ms 边界 tie）。
- `fm_note_on()`：**移除 tie 分支**。首选策略改为：**最冷的空闲声部**（`!active && age < best.age`）——冷声 = 已释放最长，EG 已走进较深阶段或即将结束，`pg_count_` 在算子上不再是「刚才被清零」的同一脉冲起步，实测能避开 click。
  - 若无空闲：首选 `sustain_pending`，否则 `age` 最小（oldest）。
  - 强制 steal 时先 `fm_send_keyoff()` 释放旧音。
- `fm_note_off()`：签名改回 `fm_note_off(Fmseq*, const FmseqSink*, int midi_ch, int note)`；sustain pending 时不再走 tie，直接按 sustain 处理。
- `dispatch()`：`case 0x80`/note-off by vel=0 均改为不传 `now_ms, cursor`。
- `fmseq_init()`/`fmseq_stop()`：清理 `tied` 相关赋值；**`fmseq_stop()` 补 `seq->fm[i].age = 0`**（与 `fmseq_init` 对齐）——修复场景切换/循环回绕/中途切歌后「最冷空闲」读到残留 age、把多个音堆在同一 release 尾音重击的 click（本节症状 3）。

### 2.4 `core/engine/audio.c::audio_bgm_start()`
在同一模块加一道防线：装新事件流前先 `fmseq_stop()`，切掉上一首仍发声的 FM 声部（中途 `bgm(){key}` 覆盖旧 BGM 时旧声部不会残留、age 不复用脏值）。`scene_switch` 路径本已由 `audio_stop_all` 覆盖，此改动让该起点独立成立。

## 三、验证

- **离线 oracle**：`eng_new`（SCH6 + 最冷空闲 + 撤 tie）melody_town `rms=2300.1, max|diff|=901`；icy_garden `rms +24%`，keyon 覆盖 0/1/2/4/5/6。
- **离线双场景 oracle（症状 3）**：`seqdump2`（同一 fmgen 芯片实例，场景 1 播 4s → `fmseq_stop` → 场景 2 从 0 重启）。修复前场景 2 起点 0–600 ms `clicks=4753`（场景 1 同期 `clicks=0`）；修复后场景 2 起 `clicks=0`；keyon select 恢复轮转（`F0 00, F1 01, F2 02, F4 04, F5 05, F6 06`）。click 判据 = 逐样本 `|Δ|` 超过局部中位数 ×8 且 >300 的孤立峰。
- **ctypes 单元测试**：`tools/tests/test_fm_seq.py` 22→**24 passed**（新增 `test_stop_resets_voice_ages_for_the_next_stream`，先红后绿：临时移除 `age=0` 即失败）；`tools/tests/test_fm_voice_enable.py` **2 passed**（$29 bit7=1 + `audio_bgm_start` 必在 `bgm_release()` 前 `fmseq_stop()`）。
- **ctypes 分配器回归**：`test_repeat_note_does_not_rekey_its_own_voice`、`test_repeat_note_rotates_through_voices`、`test_coldest_free_does_not_preempt_a_live_voice`。
- `tools/tests/test_fm_lfo.py`、`test_fmopn.py`、`test_fm_timbre.py` 全过。
- `pytest tools/tests/`：**819 passed, 1 skipped**（全仓）。
- `make -C core` 0 诊断，`./start.sh fullaudit` 7/7。

## 四、文档/版本

- 新建 `devdocs/157-*.md`（本文件）。
- `devdocs/155.md` 原文保持不动（已完结）。不追加 ERRATA，因 155 的离线证据在「只用 tie」场景下是正确的；当前取舍是「tie or level + click」的工程折衷，须单独留档 157。
- `CHANGELOG.md` 新增 c77 `0.3.047`。
- `AGENTS.md` 版本 → `0.3.047`；概述补充 `$29` 证据与场景切换 age 复位。
- `docs/B90-参考-函数索引.md` 若有 `fmseq_tie_follows` 等引用按现状修订。
- `bump_version.py` 已运行：所有 `projects/*/config.toml` `version = "0.3.047"`。
- `core/engine/nb_config.h` 重生成。
- `tools/tests/test_devdoc_refs.py`：`audio.c` 三条 whitelist（`g_snd_on`/`g_vc_on`/`audio_bgm_stop`）+7 移位更新，旧坐标记入 `SUPERSEDED_SHIFTED_LINE_REFS`。

## 五、取舍说明

「最冷空闲」分配是业界常见的 click 缓解：不重击刚释放的声部，靠选取已走 release 尾的声部做新 keyon 来隐蔽相位突变。配合 `$29=0x80` 恢复六声道后，旋律线（`melody_town`）基本回归原响度且几乎无可闻 click；复调（`icy_garden`）不再丢声道。

实机听感仍需用户拍板：若仍有极微 click 可考虑将冷声判据再放宽（如「free 且 age < 某阈值」）或恢复 155 的 40ms 窗口 tie，但代价是低音部分再度压低。当前折衷在离线 oracle 上已达成设计目标。
