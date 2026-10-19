# 157 — BGM 音色与分配器改动：启用 6 声道（$29=0x80） + 「最冷空闲」分配 + 撤销 legato tie

> **状态**：`已完结`（`0.3.044`）——离线 fmgen A/B：melody_town `rms 1689 → 2300`（+0.22 dB 与 notie 同），`max|diff| 901 → 901`（零 click）；icy_garden 多声部用上 voice 3-5，`rms 3487 → 4318`。pytest + fullaudit 全绿。
> **版本**：`0.3.044`
> **创建于**：2026-10-19
> **类型**：修复（引擎侧 FM 通路）
> **前序**：`155`（legato tie）→ 本文推翻其保留的过度切换，采用「冷声分配 + 放弃同声部重击」取舍；`135`（$22/LFO）、`123`（fmseq）、`138`（音高八度）、`152-154`（NP2kai 输出通路）
> **依赖证据**：`devdocs/138` 低八度根因、`tools/tests/test_fm_voice_enable.py` 新增、`tools/tests/test_fm_seq.py` 三条新守卫、离线 `seqdump+chplay`（fmgen 核）复核

## 一、症状与发现

0.3.042（`devdoc 155`）的 legato tie 成功消除「水泡」click，但也大幅压低 `melody_town`（单声部旋律）的响度（`rms 1689.4 →` 100ms 后快速衰减）。与此同时，排查中发现：

1. **YM2608 六声道未启用**：手册 `$29` D7(SCH)=0 → 只出 3 声道。引擎 `hal_fm_init()` 从未写 `$29`，NP2kai fmgen 也默认不强制 SCH=1；导致 voice 3-5 永远静音。`icy_garden` 有 34/287 个音被分到该组 → **多声部丢音**。
2. **OPNA keyoff→keyon 会复位算子相位**：fmgen `Operator::KeyOn()` 在 `off||release` 态 `pg_count_=0`，直接重击**刚释放**的同一声部会产生 click（`155` 所述）。但要完全回归响度，就不能同声部重击。

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
- `fmseq_init()`/`fmseq_stop()`：清理 `tied` 相关赋值，`stop` 将 `fm[i].age = 0`（便于下次首发从 voice 0 起算也符合冷声语义）。

## 三、验证

- **离线 oracle**：`eng_new`（SCH6 + 最冷空闲 + 撤 tie）melody_town `rms=2300.1, max|diff|=901`；icy_garden `rms +24%`，keyon 覆盖 0/1/2/4/5/6。
- **ctypes 单元测试**：`tools/tests/test_fm_seq.py` 21→24 passed（保留 18 条旧项；替换 3 条 tie 测试为 `test_repeat_note_does_not_rekey_its_own_voice`、`test_repeat_note_rotates_through_voices`、`test_coldest_free_does_not_preempt_a_live_voice`）；新增 `tools/tests/test_fm_voice_enable.py`（$29 bit7=1）。
- `tools/tests/test_fm_lfo.py`、`test_fmopn.py`、`test_fm_timbre.py` 全过。
- `pytest tools/tests/`：**817 passed, 1 skipped**（全仓）。
- `make -C core` 0 诊断，`./start.sh fullaudit` 7/7。

## 四、文档/版本

- 新建 `devdocs/157-*.md`（本文件）。
- `devdocs/155.md` 原文保持不动（已完结）。不追加 ERRATA，因 155 的离线证据在「只用 tie」场景下是正确的；当前取舍是「tie or level + click」的工程折衷，须单独留档 157。
- `CHANGELOG.md` 新增 c77 `0.3.044`。
- `AGENTS.md` 版本 → `0.3.044`；概述补充 `$29` 证据。
- `docs/B90-参考-函数索引.md` 若有 `fmseq_tie_follows` 等引用按现状修订。
- `bump_version.py` 已运行：所有 `projects/*/config.toml` `version = "0.3.044"`。
- `core/engine/nb_config.h` 重生成。

## 五、取舍说明

「最冷空闲」分配是业界常见的 click 缓解：不重击刚释放的声部，靠选取已走 release 尾的声部做新 keyon 来隐蔽相位突变。配合 `$29=0x80` 恢复六声道后，旋律线（`melody_town`）基本回归原响度且几乎无可闻 click；复调（`icy_garden`）不再丢声道。

实机听感仍需用户拍板：若仍有极微 click 可考虑将冷声判据再放宽（如「free 且 age < 某阈值」）或恢复 155 的 40ms 窗口 tie，但代价是低音部分再度压低。当前折衷在离线 oracle 上已达成设计目标。
