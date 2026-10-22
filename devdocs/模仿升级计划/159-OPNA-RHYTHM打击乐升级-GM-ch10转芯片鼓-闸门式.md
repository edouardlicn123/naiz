# 159 — OPNA RHYTHM 打击乐升级：GM ch10 转芯片鼓（闸门式）

> **状态**：`计划中`
> **版本**：`0.3.047`（撰写时）
> **创建**：2026-10-20
> **类型**：实施计划（闸门式 —— §〇 环境闸门通过前**禁止进入 §三 引擎实现**）
> **前序**：`123` §1.3/§1.4（v1「RHYTHM 推迟」决策，本文件重开其论证）、`124`/`135`（15 族音色）、`144`/`145`（`opnadrum.c`/`pmd` 调研，寄存器蓝本）、`155`/`157`（近况）
> **范围声明**：仅 GM ch10 → OPNA RHYTHM 6 槽。ADPCM、PPZ8、fadeout、FM3ex 均不在本轮（→ `162`）。

---

## 〇、前置闸门（先做，不通过则本文档收敛为「已暂缓」结论）

**已实测的环境缺口**（2026-10-20）：`~/.config/wxnp21kai/wxnp21kai.toml:26` `USEFMGEN = true`；`~/.config/wxnp21kai/` 现有 `bios.rom`/`font.rom`/配置文件，**无 `2608_*.WAV`**。NP2kai fmgen 的 `OPNA::LoadRhythmSample()`（`NP2kai/sound/fmgen/fmgen_opna.cpp:1415-1445`）按序拼名 `2608_` + `{BD,SD,TOP,HH,TOM,RIM}` + `.WAV`（**大写**），第一个缺失即 `break`（`i==5` 时回落 `2608_RYM.WAV`）⇒ 当前模拟器侧 rhythm **全哑**，与 devdoc 123 §1.4 的推迟理由完全吻合。

**闸门步骤**：

1. 取 6 个（或 1 个 `2608_RYM.WAV` 合集）采样文件，放入 `~/.config/wxnp21kai/`（**大写文件名**；采样为测试环境文件，**不进 HDI、不进引擎资产**，来源建议 `98fmplayer/README.md:33` 链接的 mame wav 包）。
2. 用一段最小探针（SSG 路径已有鼓声的同一探针曲）在 NP2kai + `USEFMGEN=true` 下录音，确认 6 槽鼓可闻 + 频谱瞬态与 SSG 旧路径比对有差异（证明走的是 rhythm 通路）。
3. **通过判据**：鼓可闻、串口无新增 WARN。**不通过** → §三 撤为「暂缓」节，闸门记录保留，引擎零改动。

## 一、背景：重开 123 §1.3 的论证

- **原决策**（`123` §1.3/§1.4）：RHYTHM 推迟，因它是「实机有 / 模拟器要外挂 wav」的唯一行为差异点；v1 用 SSG 3 通道合成鼓保证两平台逐字节一致。
- **重开依据**：
  1. 差异的**本质**是模拟器侧文件可补（真机内置 ROM 零依赖，`F03 §3.6`），闸门化后可控；
  2. 实机为产品目标平台，鼓音质上限（芯片 ROM 采样）远高于 SSG 方波+噪声近似；
  3. SSG 路径**保留为未映射键兜底 + 编译期可关**（§三 C），差异被限制在「映射表内键位」；
  4. 现曲 ch10=0 音符（`158` §一 实测）⇒ 收益属**未来素材**，无回归压力。
- **残余风险声明**：wav 缺失且用户不补时，映射内鼓在模拟器无声（实机仍有声）。缓解 = 闸门把「模拟器能出声」变成前置事实 + `FMSEQ_RHYTHM` 编译开关默认开、文档写明关法。

## 二、GM 键位 → 6 槽映射表

| GM 键 | 名 | 槽位名 | 寄存器（触发/电平） |
|---|---|---|---|
| 35, 36 | Acoustic/Bass Drum | BD | `$10` bit0 / `$18` |
| 38, 40 | Acoustic/Electric Snare | SD | `$10` bit1 / `$19` |
| 42, 44, 46 | Closed/Pedal/Open Hi-Hat | HH | `$10` bit3 / `$1B` |
| 41, 43, 45, 47, 48, 50 | Low/Mid/High Tom 系 | TOM | `$10` bit4 / `$1C` |
| 49, 51, 57, 59 | Crash/Ride 系 | TopCym | `$10` bit2 / `$1A` |
| 37, 39 | Side Stick/Hand Clap | RIM | `$10` bit5 / `$1D` |
| **其余键** | — | **SSG 兜底** | 走现 `percussion_class()`（`fmseq.c:86-112`） |

依据：OPNA rhythm 槽序 `BD/SD/TopCym/HH/TOM/RIM`（`opnadrum.c:118-155` 寄存器表，BSD-2）；GM 键归类为 GM 标准打击乐布局（常见于 PMD/各 tracker 的 ch10 惯例）。

## 三、引擎方案（闸门通过后才实施）

### A. 寄存器实现

- 触发：`$10` = `0x08 | slot_bit` 形态写入即 key-on（`opnadrum.c:139` 的停鼓是 `$10 ← 0xFF`；触发位编码见 `opnadrum.c:128-153` 循环：bit(i) 对应槽位映射）。电平：`$11` bit6 为 SlotLevel 模式开关；槽电平寄存器 `$18`–`$1D`（**值越大越响还是越轻以 `opnadrum.c:139` `0x18 + level − velocity` 方向为准**，实施时逐位核对 NP2kai fmgen `Rhythm` 混音器实现）。
- velocity→槽电平：沿用 PMD 方向 `level = base − velocity`（`fmdriver_pmd.c:2782+`，`pmd_cmdeb_opnarhythm`：`0x10 = level + 0x18 − velocity`，`level = fmvolume−127`）；naiz 用 `slot_level = clamp(127 − vel, 0..127)` 起步，实机听感后再调。
- 停止：`fmseq_stop()` 增 rhythm 全停（`$10 ← 0xFF` 一次写）；`fmseq` 结构体增 rhythm 在播位图（防重复触发刷 `$10`）。

### B. fmseq 接线

- `dispatch` 的 ch10 路径（现 `fmseq.c:426` 附近 `ssg_note_on` 分支）前插：`note_in = (ch == 9)`（GM ch10 = index 9）⇒ 查 §二 映射表命中 → rhythm 路径；未命中 → `percussion_class` SSG 兜底（现行为）。
- note-off（0x80/0x90 vel0）：rhythm 为「一次性触发 + ROM 采样自然衰减」，**无 note-off**（与 SSG 路径的 release 衰减不同）——映射内键的 note-off 静默忽略。
- `$29`（SCH，c75 已写 0x80）：rhythm 不受 bit7 影响（rhythm 非 ch4-6），无需追加写入；实施时以 NP2kai fmgen `SetReg(0x10)` 路径复核「无 enable 位」假设。

### C. 编译开关与兜底

- `fmseq.h` 增 `FMSEQ_RHYTHM`（默认 1）。`=0` 时 §二 映射表整体跳过、全部走 SSG（输出回到 c75 现状，逐字节可回归）。
- 未映射键永远走 SSG ⇒ 两路径共存，`test_fm_seq.py` 两套用例都跑。

## 四、验证

| 层 | 内容 |
|---|---|
| 离线 sink | 映射表每键的寄存器序列断言（`$10`/`$18-$1D` 值）；未映射键断言仍走 SSG（`$07` mixer）；`fmseq_stop` 断言 `$10=0xFF` |
| NP2kai（闸门后） | 探针曲录音：6 槽逐一可闻；频谱与 SSG 版 diff 证明通路切换 |
| 实机 | 真机内置 ROM 出鼓；串口无新增 WARN |
| 回归 | 现曲（ch10=0 音符）寄存器序列**零变化**；`FMSEQ_RHYTHM=0` 重建后与本文件实施前逐字节一致 |

**流程**：pytest → `make -C core` 0 诊断 → fullaudit → `bump_version` → CHANGELOG；`fmseq` 新导出（若有）登记 `docs/B90`。

## 五、不做什么

- 不做 ADPCM（`$100+` bank1）、PPZ8、多层 velocity 曲线、鼓组切换（0xCC program）。
- 不删 SSG 打击乐代码（兜底 + 开关回归依赖它）。
- 不把 wav 放进 `assets/` 或 HDI（宿主模拟器侧文件，与引擎资产线严格分离，见 AGENTS §二 音频三层命名）。

## 六、遗留

- GM 键表外的打击音色（如 56 cowbell、76/77）维持 SSG 现映射；如未来素材需要再扩表（扩表须重过闸门录音）。
- `$18-$1D` 电平方向与曲线听感未定（占位公式，实机后调）。

## 七、来源清单

| 来源 | 许可证 | 用途 |
|---|---|---|
| `98fmplayer/opna_drums/opnadrum.c:118-155` | BSD-2 | 寄存器表/触发编码蓝本（附注释，不整段复制） |
| `98fmplayer/pmd/fmdriver_pmd.c:2782+`（`pmd_cmdeb_opnarhythm`） | BSD-2 | velocity→电平方向 |
| `NP2kai/sound/fmgen/fmgen_opna.cpp:1415-1445`（`LoadRhythmSample`） | BSD（NP2kai） | wav 命名规则（大写、缺一断链、`2608_RYM.WAV` 回落）——闸门文件名依据 |
| `docs/refdocs/F03_opna_fm_and_bgm_routes.md:161-197` | 仓内 | `$10` RKON、RHYTHM/ADPCM 寄存器组 |
| `devdocs/123` §1.3/§1.4 | 仓内 | 被重开的原决策与理由 |
