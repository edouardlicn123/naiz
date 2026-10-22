# 160 — MIDI 颤音接入：CC1/RPN01 软件 LFO 进 fmseq

> **状态**：`计划中`
> **版本**：`0.3.047`（撰写时）
> **创建**：2026-10-20
> **类型**：实施计划（非实现轮，零代码）
> **前序**：`123`（S0–S5）、`135`（LFO/`$22`+`$B4` PMS 接入，芯片侧硬件 LFO）、`153`/`154`（flute `pms=1` 设计轻颤音与 Latencys 关闭，**硬件 LFO 与本文件的 MIDI 软件颤音是两层，须分清**）、`158`（RPN 状态机 —— 本文件复用其 RPN 选择态）
> **范围声明**：CC1 深度 + RPN(1,0) 定标的**三角波**软件 LFO，作用于 FM 旋律声部音高。不含波形全集/LFO2/slot delay（PMD 有，超范围）；不含触后颤音（→ `162`）。SSG 打击乐不参与。

---

## 一、背景与价值重估

- 现曲实测（`158` §一）：`Melody Town Theme`/`Icy Garden` **CC1 = 0 处** ⇒ 本项零现曲影响，属**未来素材能力**（AI 生成/外部 MIDI 常用 CC1 + RPN(1,0)）。
- 与既有硬件 LFO 的分工：`135` 已接 `$22` + `$B4` PMS（芯片侧，pms 按 patch 家族固定）；本项是**合成器软件层**按 MIDI 语义逐通道调制。两者叠加是标准合成器行为（MIDI 颤音 + patch vibrato 并存），但**必须合成后单次写 fnum**，避免两套写路径互相覆盖。
- PMD 有完整的软件 LFO（三角/锯齿/方波/随机 + delay + LFO2，`fmdriver_pmd.c:499-600`），本文件只取其**三角波 + delay + 频率**骨架。

## 二、现状坐标

- dispatch `0xB0`：`fmseq.c:436-443`（仅 CC64）；`0xE0` bend：`fmseq.c:448-450` → `fm_apply_bend`（`fmseq.c:368+`）→ `fmopn_bend_ratio`（`fmopn.c:79-97`，±2 硬编码 —— `158` C 节将改为可变 range，本文件在其之上叠加）。
- 节奏源：`fmseq_pump()`（`fmseq.c:501-523`）已有 `dt`（ms）并传给 `ssg_decay`（`fmseq.c:341+`）⇒ 软件 LFO 同一 dt 推进，不新增时间基。
- `$22`/PMS 现状：`hal_fm_init()` 写 `$22=0x08|FM_LFO_RATE`（c64），`$B4` 由 `fmseq.c:186-189` 组合 pan/AMS/PMS 回写。

## 三、方案

### A. 状态与语义

`Fmseq` 增每 MIDI 通道（16）：

| 字段 | 来源 | 缺省 |
|---|---|---|
| `lfo_depth`（0–127，CC1） | dispatch `case 1` | 0（关） |
| `lfo_rate`（0–127，RPN(1,0) data entry 高字节） | RPN 状态机（复用 `158` C） | 64（≈ GM 默认 5 Hz 档） |
| `lfo_delay_ms`（RPN(1,0) 低字节 → 0..~2s 映射） | 同上 | 0 |
| `lfo_phase` / `lfo_wait_ms`（通道级运行态） | pump 推进 | 0 / delay 值 |

- RPN(1,0) 的 data entry 取**高字节=rate、低字节=depth**（GM 常见约定）；未发 RPN(1,0) 时 rate/depth 维持缺省，仅 CC1 生效（CC1 单独可用）。
- 叠加顺序：`ratio_total = bend_ratio(ch) × vibrato_ratio(ch)`，对**该通道每个 sounding FM 声部**在每次 pump 中**合并后一次**回写 fnum/block（无 keyon）。`158` C 节把 `fmopn_bend_ratio` 打开后，本项新增 `fmopn_vibrato_ratio(depth, phase)`（纯函数，宿主可测）：`cents ≈ (depth/127) × max_cents × tri(phase)`，`max_cents` 取 100（≈±0.83 半音，默认封顶；常量可调）。
- 三角波：`tri(phase)` 相位 0..1 → −1..1 折线；相位推进 `phase += dt / period_ms`，`period_ms = f(rate)`（5 Hz 起步表：`period = 1000 × (64 / max(1,rate))` 的单调映射，实施时按 GM 5 Hz@64 锚点校一次）。
- delay：note-on 时该通道所有新发声部记录 `lfo_wait = lfo_delay_ms`；wait>0 的声部不调制（bend 仍生效）。

### B. 与硬件 LFO 的写路径合流

- 音高写路径现状：bend（`fm_apply_bend` 重写 fnum）+ note-on（`fm_write_patch`）。本项把「音高调制」统一为 **pump 末尾的 per-voice 调制步**：凡通道 vibrato 或 bend 非静止，合并写一次。
- `$B4` PMS 不受本项影响（它是芯片侧 LFO 对相位的调制）；两者听感叠加可接受（标准行为）。

### C. 节奏与预算

- LFO 推进挂在 `fmseq_pump` 的 `ssg_decay` 同处（`dt` 已有），**无新增调用点** ⇒ `test_frame_pump.py PUMP_CALLERS` 不动。
- 每 pump 的 fnum 回写上限：sounding 声部 ≤6（`FMSEQ_MELODY_FM_CH`）+ SS​G 不参与 ⇒ 远低于 `FMSEQ_PUMP_MAX_PER_CALL=32` 预算，无分片需求。

## 四、改动清单与验证

| 文件 | 改动 | 守卫 |
|---|---|---|
| `core/lib/fmseq.h` | 上表字段 + 初始化/复位 | ctypes 镜像同步 |
| `core/lib/fmseq.c` | dispatch `case 1` + RPN(1,0) 接入（依赖 `158` C 的状态机先落地或同轮）；pump 末尾调制步；note-on 记 delay | 新用例：CC1=100 探针曲 → fnum 摆动周期/幅度断言；delay>0 时起始 N ms 无摆动；depth=0 与未实现前逐字节一致 |
| `core/lib/fmopn.c/.h` | `fmopn_vibrato_ratio`（纯函数） | `test_fmopn` 三角波锚点（0/25/50/75% 相位） |

**回归判据（硬）**：现曲（CC1=0、无 RPN(1,0)）在 FM 后端的寄存器序列**逐字节不变**——调制步在 `depth==0 && bend 静止` 时零写入。

**流程**：pytest → `make -C core` 0 诊断 → fullaudit → `bump_version` → CHANGELOG；`docs/B90` 登记新函数。

## 五、验证（实机）

合成探针曲（单音 A4 + CC1 0→127 渐入 + RPN(1,0) rate=80）在 NP2kai 录音：颤音率 ≈ 5–8 Hz、深度随 CC1 增长；与无 CC1 版探针 A/B 听感差明确。现曲试听无变化。

## 六、不做什么

- 不做 PMD 波形全集/LFO2/slot delay；不做触后/CC11 表情对音高的调制（`162`）。
- 不改 `$22`/PMS 既有路径（`135` 的 patch 家族分配维持）。
- 不在 `midi.c` 加过滤（事件照旧全量进 fmseq）。

## 七、风险与回退

- 风险中低：调制步与 bend 合并写是唯一动到共用音高路径的点——用「depth=0 ⇒ 零写入」回归判据钉死。
- rate 表非线性/查表实现自由度大，锚点（64→5 Hz）必须有单测。

## 八、遗留

- 触后颤音、CC11 对音量的逐通道表情（与 `158` A 的 CC7 关系：CC7=静态混音、CC11=动态表情，均归 `162` 再议）。
- 波形扩展（锯齿/方波）触发条件：未来素材实测需要时再开。

## 九、来源清单

| 来源 | 许可证 | 用途 |
|---|---|---|
| `98fmplayer/pmd/fmdriver_pmd.c:499-536`（`pmd_lfo_tick`） | BSD-2 | 三角波 + delay + 相位推进骨架（借思路） |
| `98fmplayer/pmd/fmdriver_pmd.c:540-600`（`pmd_lfo_tick_waveform`） | BSD-2 | 波形扩展的未来参照（本轮不取） |
| `devdocs/135` | 仓内 | 硬件 LFO（`$22`/PMS）现状与边界 |
