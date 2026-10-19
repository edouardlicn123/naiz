# 151 — bell.fmp 载波八度错误修复（alg4 载波 mul=8 → 基频）：BGM「电流声/颤音」的 B 轴根因

> **状态**：`已完结`
> **版本**：`0.3.039`（修复版本）
> **创建于**：2026-10-19
> **类型**：Bug 修复（症状 → 判定 → 根因 → 修复 → 验证 → 防复发 → 遗留）
> **前序**：`149`（执行计划：Phase B = bell voicing）、`150`（录制对比工具链与三轴归因协议，本文件回填其 §六）、`148`（三轴 A/B/C）、`143`/`142`（buzz 诊断）、`138`（oracle 职责教训）、`136`（度量定义）、`135`（LFO + 15 族）、`124`（S6 默认音色）、`66`（`op=N` = 算法算子 N 的语义修正）
> **来源/坐标**（修复后 `0.3.039`）：`assets/demo-a2/fm/bell.fmp`、`assets/demo-a2/fm/targets.toml`、`core/engine/audio.c`（`BGM_TICK_TRACE`）、`core/engine/main.c`（`BGM_BENCH`）、`core/engine/bootmenu.c`（`AUTOEXIT`）、`core/Makefile`（`EXTRA_DEFS`）、`tools/naiz_audio/{fm_render,spectrum_report,gm_render,midi_ref}.py`、`tools/diag/{np2kai_audio,bgm_compare}.py`、`tools/vendor/ymfm/src/ymfm_fm.ipp:1019`（算法载波表）

---

## 一、症状

`0.3.038`（P0 三修）之后，用户 NP2kai 实机复报：BGM「音乐有所改善，但仍有类似电流声的颤音」，**四曲都有**（含 `001/002` flute）。场景 → BGM 映射（`projects/demo-a2/scene/nbook00N.nb`）：

| 场景 | BGM key | GM program | 族 |
|---|---|---|---|
| `001` / `002` | `melody_town` | ch0 = 73 | flute（族 8） |
| `003` / `004` | `icy_garden` | ch0 = 10、ch1 = 15、ch2 = 46 | bell（族 1）＋ strings（族 5） |

## 二、判定（录制对比，`150` 协议）

按 `150` 的工具链录引擎稳态运行音频（`BGM_BENCH` 无头循环 + SDL `disk` 驱动 → `np2kai_audio` 手法），与原版 MIDI 时间线（`midi_ref`）及 GM soundfont（`gm_render`）对比：

| 录音 | `>5kHz` 占比 | 质心 |
|---|---|---|
| **引擎 icy_garden** | **0.3977（39.8%）** | **4160 Hz** |
| GM `icy_garden` | 0.0041（0.4%） | 861 Hz |
| ENGINE melody_town | 0.0008 | 726 Hz |
| GM melody_town | 0.0006 | 902 Hz |

**判定**：`icy_garden`（`003/004`，bell 族）能量比 GM 参考**高约 100 倍的 5kHz 以上成分**，频谱质心 4160 vs 861 Hz ⇒ **B 轴（voicing）确证**。`melody_town`（`001/002`，flute）频谱与 GM 几乎一致（0.0008 vs 0.0006）⇒ 其听感问题**不是亮度**（见 §六 遗留）。

**时基（A 轴）同时被排除为主因**：引擎派发时刻（`BGM_TICK_TRACE`，`$28` 键位掩码）对 MIDI note-on 的残差抖动 **std 6.5–8.2 ms / p95 14.8–20.1 ms / drift −0.33 ~ −0.56 ms/s**（`bench` 高 pass 率下）。⇒ 电流声来自**音色**而非派发抖动。

---

## 二·五、根因

`bell.fmp` 使用 `alg=4`。YM2608 的 4 算子算法连接表（**权威出处** `tools/vendor/ymfm/src/ymfm_fm.ipp:1019` 的 `s_algorithm_ops`）给出：

| alg | 输出（载波算子） |
|---|---|
| 0–3 | 仅 O4 |
| **4** | **O2 + O4** |
| 5–6 | O2 + O3 + O4 |
| 7 | O1 + O2 + O3 + O4 |

`alg=4` = 两组 2-op：`(op1→op2) + (op3→op4)`，故 **载波 = `op2` 与 `op4`**，`op1`/`op3` 是调制器（与 `c66` 修正后的「`op=N` = 算法算子 N」语义一致；flute 的可用性即为其佐证——flute 载波在 `op2`、mul=1，音高正确）。

原 `bell.fmp`（修复前）：

```
alg=4 fb=0 pan=0xc0
op=1 ... mul=2  tl=14      # 调制器
op=3 ... mul=5  tl=16      # 调制器
op=2 ... mul=8  tl=14      # 载波 —— mul=8、tl=14（最响）
op=4 ... mul=1  tl=22      # 载波
```

**`op2`（最响的载波）`mul=8` ⇒ 该堆栈把音符的基频按 8× 发出**（VCO 频率 = fnum × mul），即音高基调上移 3 个八度，能量全部堆到高频 ⇒ 听成金属性电流声/颤音。原始注释「High inharmonic partials (mul 2/5/8)」说明设计意图是把 `mul 2/5/8` 放在**调制器**上制造非谐分音，但这两个高比值实际落在了**载波**（`op2`）上——`c66` 的语义修正（旧「寄存器槽 N」→ 新「算法算子 N」）改变了算子编号的解码，使这一处成品音色未随之复核。

> **一般规律**：`alg 0–3/5/6` 的「载波」应承载基频（`mul` 1 或刻意的低谐波）；只有 **`alg=7` 全员是载波**，此时每算子给不同 `mul` 才是合法的「加法/管风琴式」设计。故「载波 mul 高」是否为 bug 取决于算法，不能只看 `mul`。

---

## 三、修复

`assets/demo-a2/fm/bell.fmp`：**载波回到基频，非谐比值移到调制器**。

```
alg=4 fb=0 pan=0xc0
op=1 dt=0 mul=5  tl=28 ks=2 ar=27 am=0 d1r=7 d2r=3 sl=5 rr=9   # 调制器：5×
op=3 dt=2 mul=7  tl=36 ks=1 ar=27 am=0 d1r=7 d2r=3 sl=6 rr=8   # 调制器：7×
op=2 dt=0 mul=1  tl=4  ks=1 ar=27 am=0 d1r=3 d2r=3 sl=2 rr=9   # 载波：基频、响
op=4 dt=0 mul=1  tl=10 ks=1 ar=27 am=0 d1r=3 d2r=3 sl=2 rr=8   # 载波：基频
```

`assets/demo-a2/fm/targets.toml` 的 `[bell] centroid_hz` 由 `[1500,5000]` 改为 `[300,1800]`——原带描述的是**错误音的亮**，新带对齐 GM 参考（见下），并注明其来源。

---

## 四、验证

**4.1 离线 oracle（`fmbench`/ymfm，`tools/naiz_audio/fm_render.py`）逐音高质心**（表为目标 GM=glockenspiel/music-box 渲染值）：

| note | 引擎修复前 | 引擎修复后 | GM 参考 |
|---|---|---|---|
| 60 | 3049 Hz（>5k 3.96%） | **402 Hz**（>5k 0.03%） | 401 Hz |
| 72 | 6287 Hz（>5k 52%） | **773 Hz**（>5k 0.40%） | 778 Hz |
| 84 | 13331 Hz（>5k 84%） | **1488 Hz**（>5k 3.75%） | 1569 Hz |

**4.2 实机通路（NP2kai，`BGM_BENCH_NAME=icy_garden` 无头录）**：

| | >5kHz | centroid | RMS |
|---|---|---|---|
| 修复前 | 0.3977 | 4160 Hz | 0.057 |
| 修复后 | **0.0123** | **1085 Hz** | 0.192 |
| GM 参考 | 0.0041 | 861 Hz | — |

⇒ 5kHz 以上能量降 **~32 倍**至与 GM 同量级，基频恢复后整体响度上升（不再把能量浪费在近 Nyquist 处）。

**4.3 回归**：`make -C core` 0 诊断（`core/*.err` 空）；`tools/env_setup/venv/bin/python -m pytest tools/tests/` **807 passed / 1 skipped**；`./start.sh fullaudit` **7/7**。

**4.4 同族审计**（防同类漏网）：以 `ymfm` 载波表逐 patch 扫「载波 `mul≥3` 且非静音」——`alg=7` 命中者（brass/organ/strings/synlead/synfx/sfx）为**合法加法设计**（每算子一谐波）；`alg=4/6` 命中的 `ethnic`（`op2 mul=3 tl=40`，主载波 `op4 mul=1 tl=32`）与 `perc`（打击乐金属谐波）**基频均在**，为刻意音色，非 bug。**唯 `bell` 的「最响载波 mul=8」为缺陷**。

---

## 五、防复发

- **`tools/tests/test_devdoc_refs.py`**：`audio.c` 引脚（`g_snd_on`/`g_vc_on`/`g_bgm_on`/`audio_bgm_stop`）与 `bootmenu.c`（`prefs_set_lang`）、`main.c`（`prefs_save`/`LANG] boot`/`cjk_load_for_lang`）随本轮 `BGM_TICK_TRACE`/`BGM_BENCH`/`AUTOEXIT` 的行位移更新；旧坐标登记入 `SUPERSEDED_SHIFTED_LINE_REFS`（附位移原因），删守卫或改坏即红。
- **`tools/tests/test_frame_pump.py`**：`PUMP_CALLERS` 的 `main.c` 由 3 → 4（新增 `BGM_BENCH` 循环也必须泵帧，否则虚拟时钟不前进）。
- **`targets.toml [bell]`**：改带后仍 `calibrated=false`（P2 流程再翻 true）；带值不再与错误音色自洽。

---

## 六、遗留

1. **`001/002`（flute）的「颤音」未归因**：其频谱与 GM 无本质差异（§二），故非亮度；候选为 **C 轴（LFO `pms=1` 颤音，`$22=0x08|FM_LFO_RATE(2)`≈6.6 Hz）** 与 **A 轴（真机/重载 pass 率下的派发抖动）**。按 `149` 的 A1/C 步骤继续取证。
2. **A2（OPNA Timer-B 中断时基）**：本环境不可验证（NP2kai 中断投递），仍按 `134`/`149` 走只读探针。
3. **实机听感**：本文件所有结论基于**录音 + 频谱 + 派发 trace**；用户 NP2kai 实听「电流声是否消失」为最终判据（`build`+`make` 后核 `003/004`）。
4. **`targets.toml` 其余族**仍 `calibrated=false`（P1c 对齐 + P2 调音的既定归属）。
