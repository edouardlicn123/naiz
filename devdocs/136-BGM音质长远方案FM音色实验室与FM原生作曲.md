# 136 — BGM 音质长远方案：FM 音色实验室（ymfm oracle + 模拟器对齐）/ 音色库 / FM 原生作曲

> **状态**：`实施中`（P1a 工具就位；**op= 标签语义根因已修复**，见 §十三）
> **版本**：`0.3.035`
> **日期**：2026-10-14
> **关联**：devdoc 122（BGM 本地静音根因与音频通路取舍）、123（MIDI→FM 通路实现计划 S0–S7）、124（S6 默认音色内容与 GM 映射数据）、125c/125d（flute 族历代调节史）、134（方案 C-OPNA 定时器中断驱动音泵立项，**独立线**）、135（S7 OPNA LFO 接入 + 15 族重做）
> **参考**：`docs/refdocs/F03_opna_fm_and_bgm_routes.md`（OPNA 寄存器）、`F04_opna_timer_a_b_specs.md`、`F05_pmd_driver_architecture.md`、`F06_pmd_mml_manual_en.md`
> **前置结论**：135 §2 已定性「像电子琴」= **patch 设计问题**（持续八度 + 硬起音），非映射/构建错误；123 §6.3 已定性 **GM→FM 是原理性损失**，工程上消不掉。
> **行号坐标系**：本文写于 `0.3.034` 现行坐标。实现落地后 §三 引用的 `core/` 行号须按 §十「规格与实现的收敛责任」重校，并由 `tools/tests/test_devdoc_refs.py` 守护。

> ## ⚠ ERRATA（`0.3.036` 追加，devdoc 138）
>
> **§十五「oracle 低八度根因」的判定方向是错的**，正文以下按存档规则原样保留。
>
> - **错在哪**：§十五 判定「① 引擎公式正确（A4=block4/fnum520=440）、③ ymfm 低八度」，并在 `fmbench.cpp` 写 `$A4/$A0` 时 **FNUM ×2** 作「修复」。
> - **正确结论**：**错的是引擎**。YM2608 手册、NP2kai `fmgen`（逐行核算 + 宿主渲染实测：block4/fnum520→220Hz、block5/fnum520→440Hz）、ymfm `(fnum<<1<<block)>>2` **三方一致**为 `f=(fnum<<(block-1))×7987200/(144×2^20)`。引擎 `fmopn.c` 的 `FMOPN_FNUM_SCALE_N=18432` 漏了 `2^(block-1)` 折半，把每个音符编低一个 block ⇒ **芯片对引擎发出的寄存器只给到半频 = 用户实听的「音调偏低」**。`×2` 只是把 oracle 拉高到「作曲者心里的音高」，反而**掩盖**了引擎 bug，使 oracle 与实听脱钩。
> - **修复与后果**：`FMOPN_FNUM_SCALE_N 18432→36864`（A4 改发 block5/fnum520）、撤销 fmbench 的 `×2`；详见 **`devdocs/138-FM音高整体低八度根因修复.md`**。§十五 中「八度不变量」（谐波比值 / inharm / centroid / 颤音率）**结论仍有效**，仅「绝对音高=f0」相关的表述作废。

---

## 一、背景：为什么逐 patch 打补丁治不了本

三轮实机反馈（c64 → c65）暴露的不是某一个数值错，而是**方法错**：

| # | 结构性成因 | 出处 | 后果 |
|---|---|---|---|
| 1 | **原理性错配**：把任意 GM MIDI 塞进 6 复音 4-op FM + 15 族映射 | 123 §6.3 | 同 patch 换算法/包络可完全不像原乐器；族归并必然产生可听偏差 |
| 2 | **盲调**：无可客观指标，唯一反馈是「用耳朵在模拟器上听」 | 135 §2.2 | 每轮只改一个数值，无法累积、无法回归、易反复 |
| 3 | **目标环境非参考级**：NP2kai 的 FM 合成 `tinny/distorted` | 123 §10.4（issue #112） | 在劣化输出上定「像不像」，是在追错目标 |
| 4 | **能力缺口已补但用法缺失**：引擎原无 LFO，S7 已补（`$22`/`$B4`） | 135 §2.3/§4.1 | 有工具但无「谱目标」引导，仍靠手感 |

**结论**：长远解 = **可测量的离线 oracle（含对模拟器对齐）→ 受目标约束的音色库 → FM 原生作曲**。三者缺一：无 oracle 则继续盲调；无对齐则 oracle 与实机脱节；无原生作曲则永远受 GM→FM 错配上限约束。

---

## 二、决策基线（已定，不再重议）

| 项 | 决定 | 依据 |
|---|---|---|
| 方案范围 | **P1 + P2 + P3 全做** | 用户拍板 |
| MIDI 导入路径定位 | **长期降级为回落路径**（配合 P3）；文档写明音质损失 | 用户拍板；123 §8.1 已预登记该代价 |
| oracle 基座 | **ymfm**（BSD-3、原生 YM2608/OPNA、C++14），**叠加 NP2kai 对齐层** | 用户拍板「基于 ympm，再针对模拟器进行对齐或有针对的微调」 |
| P1a 形态 | **方案 A**：独立 C++ CLI `fmbench` + Python `subprocess` 包装 | 用户选定 A |
| 运行时影响 | P1/P2 **零运行时影响**；仅 P3 引擎侧改动须把关「开销 ≤ 现状」 | 见 §六 |

**oracle 选型理由（ymfm vs NP2kai 的 fmgen）**：

| 维度 | ymfm（选中） | fmgen（NP2kai 内嵌） |
|---|---|---|
| 许可 | **BSD-3（已核实），最干净** | 内嵌于 NP2kai，许可不明确，抽离有风险 |
| 芯片覆盖 | **原生 YM2608(OPNA)**——正是 PC-98 芯片 | 覆盖，但与模拟器耦合 |
| 行为基准 | 参考级（与真实 YM2608 对齐） | 近似，且已知 `tinny/distorted` |
| CI 可用 | **可**（主机 g++ 编译） | 需连模拟器，重 |

次选记录（**不采用**）：Nuked-OPN2（许可非 BSD 系，须核对；且仅覆盖 YM2612/OPN2，非 2608）；YM2608-LLE（晶体管级、CPU 极重、作者标注不适合实时、WIP）。**保留 NP2kai 抓取作次级对照**，因交付/试听实际落在 NP2kai。

---

## 三、P1 — FM 音色实验室（先做，最高杠杆）

### P1a　ymfm 离线 oracle（方案 A）

**目标**：主机侧按**我们的寄存器写法**把「patch + 音符序列」渲染成 PCM，供离线测量与回归。

**目录与成果物**：

| 路径 | 内容 |
|---|---|
| `tools/vendor/ymfm/` | vendor 的 ymfm 源码 + `LICENSE`（BSD-3）+ `PROVENANCE.md`（来源 URL + 许可 + 用途），遵 AGENTS §十「复制代码必须附来源+许可」 |
| `tools/naiz_audio/fmbench/` | 极简 C++ CLI；链接 ymfm 的 **YM2608** 核心；含 `Makefile`（g++ 12.3 已确认可用） |
| `tools/naiz_audio/fm_render.py` | Python 包装：调用 `fmbench`、读回 PCM、按 job 哈希缓存 |

**实际接口（实现偏离原草案）**：`fmbench` 不用 `job.json`，改为纯 CLI 参数 + 可选事件文件（见 §十三）：

```
fmbench <patch.bin> <out.wav> [--clock N] [--fidelity min|med|max]
        [--note N] [--vel N] [--dur MS] [--bend N] [--tail MS]
        [--events FILE] [--no-lfo] [--raw-note]
```

事件文件每行 `note vel start_ms dur_ms bend`。**关键**：`fmbench` 读的是 **编译后的 32 字节二进制**，不是 `.fmp` 文本；`fm_render.py` 必须先经 `fm_patch.compile_source()`。

- `--raw-note`：跳过 velocity→TL 衰减（纯音色），默认复刻 `fmseq` 的 velocity 缩放、bend 应用、KEYON/KEYOFF 时序、`$B4` 组合回写——以保证与实机 **apples-to-apples**。

**门控**：`fmbench` 对内置正弦 patch 渲染出预期波形；与 `fmseq` 写序一致（逐寄存器对照单测）。**实现中已借此定位 `flute.fmp` 实为静音**（见 §十三）。

### P1b　测量与验收目标

**目标**：把「像不像」变成数字。

**成果物**：

- `tools/naiz_audio/spectrum_report.py`：把 `/tmp/opencode/flute_spectrum.py` 正式化（该脚本已用合成信号自测通过）。
- `assets/demo-a2/fm/targets.toml`：每族验收带（初值来自研究，落地时由 P1c 标定修正）。

**指标定义（须与实现逐字一致）**：

| 指标 | 定义 |
|---|---|
| 谐波比 | 稳态窗（去起音/释放）FFT，f0 已知（音符），输出 `2f/1f`、`3f/1f`… 的 dB |
| 起音时间 | RMS 包络从峰值 10% 到 90% 的时间（ms） |
| 颤音率/深 | 瞬时频率估计（STFT 峰 / 过零）→ 调制率（Hz）+ 峰值偏差（cent，`1200*log2`） |
| 谱心 | 频谱加权平均频率（Hz），衡量「亮度」 |
| 非谐波能量比 | 非 f0 整数倍频段能量占比（区分气声/纯音） |
| 峰值/RMS | 归一声压用（对齐时消除音量差） |

**targets.toml schema（草案）**：

```toml
[flute]
harmonics  = { "2f" = [-25, -15], "3f" = [-35, -25] }
attack_ms  = [30, 80]
vibrato_hz = [5.5, 7.5]
vibrato_cent = [10, 60]
centroid_hz  = [500, 2500]
```

**测试**：

| 测试 | 判定 | 是否需 oracle |
|---|---|---|
| `tools/tests/test_fm_patch_shape.py` | **编译后字节**结构不变量：如 flute 禁「持续八度载波」（不允许多算子 `mul>=2` 且 `sl` 低不衰减）；AR/SL/TL 范围带 | 否（纯主机、快） |
| `tools/tests/test_fm_timbre.py` | 经 oracle 渲染探测音 → 指标落 `targets.toml` 带内；oracle 缺失则 `skip`（目标是在本环境构建） | 是 |

### P1c　ymfm ↔ NP2kai 对齐与针对性微调　★（本轮核心新增）

**目标**：让 oracle 的指标能**预测用户实际在 NP2kai 听到的东西**，而非描述一个没人听得到的理想芯片。

**步骤**：

| # | 动作 | 细节 |
|---|---|---|
| 1 | 采集真机 | 新增**确定性语料** `test_timbres.mid`：每族一个固定音（C4=note 60，vel 96，1s，等间隔），经引擎在 NP2kai 播放；用宿主 monitor 抓 WAV（`parec --device=<monitor> --format=s16le --rate=48000 --channels=2`）。走真实引擎 path ⇒ 测的是交付物 |
| 2 | 同源对照 | 同一语料喂 `fmbench mode="engine-faithful"` → ymfm 渲染 |
| 3 | 归一 | **等响归一**（NP2kai 自带音量/混音，须先消除）；再逐族比对每谐波 dB 差、噪声底、起音、颤音 |
| 4 | 分流 | **差异小** → 以 ymfm 为准；**系统性差异**（如高频倾斜/噪声底）→ 在**分析端**加「对齐修正」（per-frequency 加权；**不改引擎、不改 ymfm 源码**），使 oracle 指标预测 NP2kai；**差异大且属 NP2kai 缺陷** → 记录，targets 用「ymfm 值 + 容差」表达，NP2kai 仅作「有无/对不对」判据 |
| 5 | 针对性微调 | 用对齐后的 oracle 定位「像电子琴」的物理特征并调 patch：持续八度→`mul=2`+`sl` 不衰减；硬起音→`ar` 过大；谐波比过高→调制器 `tl` 过低。迭代至指标进带 |

**成果物**：对齐报告（入本 devdoc 或接替文档）+（如需）修正系数文件 `assets/demo-a2/fm/alignment.toml` + 标定后的 `targets.toml`。

**注**：NP2kai 每台机器/版本可能有音量差，故对齐指标一律用**归一后**的比值，不用绝对值。

### P1d　回归守卫

- `test_fm_patch_shape.py`（静态字节不变量）、`test_fm_timbre.py`（oracle 谱回归）。
- （可选）`test_fm_oracle_alignment.py`：若仓库存在 NP2kai 采样，校验「对齐系数」未漂移。

**P1 完成判据**：oracle 可构建并完成一次标定；flute 与全部 15 族均有可测量目标且回归绿。

---

## 四、P2 — 音色库：借/推，而非手调

| 项 | 内容 |
|---|---|
| 来源策略 | 默认 **FM 理论推导**（用 P1 oracle 验证）；若移植开源则**逐文件**注明来源 + 许可（123 §6.1：**无任何 CC0 OPN patch 库**） |
| 成果物 | `assets/demo-a2/fm/PROVENANCE.md`（来源 + 许可 + 用途） |
| 范围 | 依 `targets.toml` 重整 15 族（`piano/bell/organ/guitar/bass/strings/brass/reeds/flute/synlead/synpad/synfx/ethnic/perc/sfx`，见 `tools/naiz_audio/gm_families.py`）；可选扩 GM 覆盖（受许可与工作量约束） |
| 验收 | 每族过 `test_fm_timbre` |

---

## 五、P3 — FM 原生作曲（真正的长期解）

**原理**：不再把任意 GM MIDI 当基准，改为**为 6 FM + 3 SSG 的硬件上限作曲**。这是 122 §5.2 / 123 §6.3 已给的方向，本轮把它从「下一步研究」变成「立项执行」。

| # | 子项 | 内容 |
|---|---|---|
| 3.1 | 格式选型 | 基于 refdocs **F05**（PMD 架构）/ **F06**（MML 手册）在「MML/PMD 风格」vs「tracker 导出」间选定；产出选型记录 |
| 3.2 | 编译器 | `tools/naiz_audio/mml/`：**MML → 引擎数据**（patch 引用 + 序列） |
| 3.3 | 引擎侧评估 | 现为运行时解析 SMF（`core/lib/fmseq.c`）；决定「新增原生序列格式」还是「编译成内存 SMF 交给 `fmseq`」。**约束：运行时开销 ≤ 现状** |
| 3.4 | 资产重做 | 用 MML 重做 BGM（`Melody Town` / `Icy Garden` …），适配 6 FM + 3 SSG 织体 |
| 3.5 | MIDI 降级 | MIDI 导入改为回落路径，文档写明音质损失（123 §8.1） |

**完成判据**：至少一首 BGM 走通 MML 全链路且达音色目标。

---

## 六、横切约束

### 6.1 验证矩阵（对齐 AGENTS §八 五禁）

| 层 | 手段 | 纪律 |
|---|---|---|
| 主机谱回归 | `test_fm_patch_shape.py` / `test_fm_timbre.py` | 静态不变量优先；oracle 回归次之 |
| oracle 标定 | `fmbench` ↔ NP2kai 抓取 | 先等响归一；NP2kai 只判「有无/对不对」 |
| 编译 | `make -C core` + `find core -maxdepth 1 -name '*.err' -size +0` | **诊断在 `.err` 不在 stdout**（0.3.014 教训） |
| 工具链 | `tools/env_setup/venv/bin/python -m pytest tools/tests/` | pytest 全绿**不构成文档正确的证据**（§十） |
| 全审计 | `./start.sh fullaudit` | symbol_audit A/B 空 |

### 6.2 运行时影响边界（回答「是否影响游戏性能」）

- **P1 / P2 零运行时影响**：`fmbench`、`fm_render.py`、`spectrum_report.py`、`tools/vendor/ymfm/` 全在 `tools/`（开发期），**不进 `engine.exe`、不进 HDI、不在 PC-98/NP2kai 运行**。游戏内 FM 播放仍是 `core/lib/fmopn.c` + `core/lib/fmseq.c` + `core/plat/hal_audio.c`。
- **P1/P2 产物是 patch 字节（`.fmp`）**：合成在 OPNA 硬件做，引擎只写寄存器，**改 patch 不增加 CPU 负载**。
- **唯一触及运行时的是 P3 引擎侧**（若新增原生序列格式）：设计目标写明 **开销 ≤ 现状**（现为运行时解析 SMF）。

### 6.3 与既有独立线的边界

- **时序方案 C（devdoc 134）独立线**：治时序（解耦主循环），**不治音色**，与本方案正交，不混做。
- **本方案不动 `$22`/`$B4`/LFO 通路**：那些已在 135 交付；P1 仅**测量与调参**。

---

## 七、风险与已知不可解（对齐 123 §十）

| # | 风险 | 性质 | 缓解 |
|---|---|---|---|
| 1 | ymfm 适配/主机构建工作量 | 工程 | 工具链已确认（g++ 12.3 / cmake / make）；一个 Makefile 即可 |
| 2 | ymfm ↔ NP2kai 行为差异 | 环境 | P1c 对齐层管理；NP2kai 不判音质 |
| 3 | P3 体量最大（格式 + 编译器 + 资产重做） | 工程 | 单独门控；先出一首全链路样板 |
| 4 | 无 CC0 OPN patch 库 | **原理性** | P2 默认自研推导 + P1 验证；移植须逐文件注明许可 |
| 5 | 6 复音对多声部编曲的硬限制 | **原理性** | P3 作曲即适配；123 §8.2 第 5 项资产过载告警 |
| 6 | NP2kai FM 非参考级 | 环境 | 真机为终态听感基准；NP2kai 只判「有无/对不对」 |
| 7 | 许可核对 | 法务 | ymfm=BSD-3 **已核**；任何新增 vendor 须先核许可再入库 |

---

## 八、阶段门控与完成判据

| 阶段 | 内容 | 完成判据 | 版本动作 |
|---|---|---|---|
| **P0** | 本文（总纲） | 文档就位 | 仅文档，不 bump |
| **P1a** | ymfm + `fmbench` + `fm_render.py` | 正弦 patch 自检通过；`engine-faithful` 写序单测通过 | bump |
| **P1b** | `spectrum_report.py` + `targets.toml` + 两个测试 | 两项测试就位（shape 必过，timbre 依赖 oracle） | bump |
| **P1c** | 标定 + 对齐 + 调 flute/15 族 | 对齐报告完成；flute 及 15 族指标进带 | bump |
| **P1d** | 回归收口 | 回归全绿 | bump |
| **P2** | 音色库 | `PROVENANCE.md` + 15 族达标 | bump |
| **P3** | MML 全链路 | 至少一首 BGM 达标 | bump |

---

## 九、交付物清单

```
tools/vendor/ymfm/                      # vendor + LICENSE + PROVENANCE.md
tools/naiz_audio/fmbench/               # C++ CLI + Makefile
tools/naiz_audio/fm_render.py           # Python 包装
tools/naiz_audio/spectrum_report.py     # 测量（正式化 /tmp/opencode/flute_spectrum.py）
tools/tests/test_fm_patch_shape.py      # 静态不变量
tools/tests/test_fm_timbre.py           # oracle 谱回归
assets/demo-a2/fm/targets.toml          # 每族验收带
assets/demo-a2/fm/PROVENANCE.md         # 音色来源/许可
assets/demo-a2/fm/alignment.toml        # （如需）对齐系数
tools/naiz_audio/mml/                   # （P3）MML→引擎数据 编译器
devdocs/137-*.md                        # （接替）落地记录
```

---

## 十、规格与实现的收敛责任（预登记）

- 本文件标为**规划中**，实现期间可修订；**实现完成后**须逐条核对 §三 引用的 `core/` 行号，并交 `tools/tests/test_devdoc_refs.py` 守护（行号会随实现位移）。
- 若实现过程中推翻本文任一结论，按 AGENTS §十 四步订正路径：原文正文不改 + 头部追加 `ERRATA` 块 + 新建接替文档 + CHANGELOG 加标记 + AGENTS 规则就地订正。

---

## 十一、未决项（动手前须拍板）

| # | 项 | 何时需定 |
|---|---|---|
| 1 | `engine-faithful` 模式是否严格复刻 velocity→TL 与 bend（工作量 vs 保真度） | P1a 前 |
| 2 | 对齐修正做在「分析端加权」还是「oracle 输出后处理」 | P1c 前 |
| 3 | P3 记谱格式最终选型（MML/PMD 风格 vs tracker 导出） | P3.1 前 |
| 4 | P3 引擎侧「新增原生序列格式」vs「编译成内存 SMF」 | P3.3 前 |
| 5 | 是否顺带做 GM 覆盖扩张（P2 边界） | P2 前 |

---

## 十二、本轮（P0 文档轮）实际改动清单

**纯文档，零代码。** 未新增/修改任何 `.c`/`.h`/`.py`/`.nb`；未跑 `bump_version`（仍 `0.3.034`）。

| 文件 | 改动 |
|---|---|
| `devdocs/136-BGM音质长远方案FM音色实验室与FM原生作曲.md` | **新建**（本文） |

---

## 十三、实施记录 P1a：`op=` 标签语义根因（本会话发现并修复）

**症状**：P1a 工具首次自检时，用 c65 的 `flute.fmp` 渲染 C4，测得 **完全无声**（peak=0）。这解释了用户「flute 像电子琴」之外的更深问题：**c65 的 flute 其实是静音**——用户此前听到的奇怪音色来自别处或旧构建。

**排查**（两独立模拟器交叉验证，非推断）：

1. **`.fmp` 是文本源**：32 字节二进制由 `tools/naiz_audio/fm_patch.py` 的 `compile_source()` 生成、`pack_audio` 打包进 `AUDIO.DAT`。`fmbench` 必须喂编译产物，直接读 `.fmp` 会得到垃圾字节（首验错误根源）。
2. **算法算子顺序 = 寄存器槽 [1,3,2,4]**：ymfm `operator_map`（chan0 = `{0,6,3,9}`）与 NP2kai fmgen（`slottable = {0,2,1,3}`）**一致**确认——alg4 的载波是寄存器 **0x38 / 0x3C**（槽 2/3），不是 0x34/0x3C。
3. **旧语义错位**：`.`fmp` 的 `op=N` 被当作**寄存器槽号 N**，而算法算子顺序是槽 [1,3,2,4]，于是 `op2`（本意 = alg4 的组 A 载波）实际落进组 B 的调制器槽。c65 flute 恰好把「组 B」静音（`op3/op4 tl=127`），结果**真正的载波被静音 ⇒ 完全无声**。c64 只是碰巧没踩中。**补丁注释里写的 `op1->op2 + op3->op4` 一直是错的心智模型。**

**修复（用户拍板方案：`op=N` = 算法算子 N）**：

- `tools/naiz_audio/fm_patch.py`：`OP_FILE` 由 `[0,2,1,3]` 改为**恒等 `[0,1,2,3]`**（源 `op=N` 存到 file idx N-1 ⇒ 文件按算法顺序排列）。
- `core/lib/fmopn.{c,h}`：`fmopn_op_slot = {0,2,1,3}` **不变**——它的语义明确为「算法算子索引 → 寄存器槽」（硬件事实）。零代码行为改动。
- 同步更新注释/docstring：`fm_patch.py`、`fmopn.{c,h}`、`fmbench.cpp`、`test_fm_patch.py`、`test_fm_seq.py`、`test_fmopn.py`。
- **`flute.fmp` 源文件一行未改**——格式修正后其原文即正确（`op1` = 弱调制器、`op2` = 强载波、`op3/op4` = 静音的组 B）。

**验证**：

| 项 | 结果 |
|---|---|
| flute 渲染 | peak `0 → 2648`（fmbench C4，两声道） |
| 全 15 族 audit（旧 vs 新格式逐族对比） | 无一变静音；flute 由 0→2648，perc/piano/bell/synpad 微变，余者近同 |
| `make -C core` + `core/*.err` | 0 诊断 |
| pytest | **779 passed / 1 skipped** |
| 防复发测试 | `test_fm_patch.py::test_op_label_semantics_pinned`（钉 `OP_FILE` 恒等 + C `fmopn_op_slot={0,2,1,3}`）、`test_file_is_algorithm_order`、`test_ctypes_round_trips_per_field`（经 C 访问器验证 `op N → regslot[N-1]`） |

**遗留（非本修复引入）**：`bass.fmp` 等串行（alg0–3）patch 在**新语义下**的载波算子系数仍需按 P1b/P2 重估（其注释里的「two carriers」表述对 alg0 本就不成立）；`flute.fmp` 参数仍待 P1c 试听标定。

---

## 十四、P1a 接口与工具的收敛说明

- `fmbench` 接口以 §三 实际接口为准（CLI + 事件文件）。
- `fm_render.py` 包装须先在 Python 侧 `compile_source()` 得 32 字节再喂 `fmbench`。
- 本轮已落地（P1a）：`tools/vendor/ymfm/`、`tools/naiz_audio/fmbench/`、`tools/naiz_audio/fm_render.py`（Python 包装：`compile_source()` → fmbench → 读回 PCM → job 哈希缓存）、`fm_patch.py`（语义修复）、`tools/tests/test_fm_patch_shape.py`（P1b 静态不变量：**禁载波全静音**，已反证能捕获修复前 flute）。
- **P1b 已收口，见 §十五**：`spectrum_report.py`、`assets/demo-a2/fm/targets.toml`、`test_fm_timbre.py` 均已落地。

---

## 十五、实施记录 P1b：测量实验室 + oracle 低八度根因

**成果物（P1b）**：

| 文件 | 内容 |
|---|---|
| `tools/naiz_audio/spectrum_report.py` | 指标库（`analyze`/`estimate_f0`/`measure_vibrato`/`measure_attack_ms`/`_steady_spectrum`/`render_and_analyze` + CLI）。颤音用 Hilbert 瞬时频率法（带通 f0±、最长响亮段、去线性趋势、分块平均到 ~200 Hz 后 FFT）。含**可信度门控**：调制率须落在 OPNA LFO 实际范围 [2.5, 30] Hz 且谱峰显著（否则返回 `None`）——否则噪声/瞬态会误报 60+ Hz。 |
| `assets/demo-a2/fm/targets.toml` | 15 族验收带（每族 `harmonics 2f/3f` + `attack_ms` + `centroid_hz` + 可选 `vibrato_hz/cent`），另有 `calibrated` 标志。**初值来自研究（设计意图）**，`calibrated=false` 表示尚未核实达标（P1c/P2 达标后逐族翻 true）；`true` 时测试强制进带。 |
| `tools/tests/test_fm_timbre.py` | 三层：①**合成信号分析器自测**（恒跑，证明指标测的是目标物）②targets schema（族集/序、带形）③oracle 回归（fmbench 不可构建则 `skip`）。 |

**★ oracle 低八度根因（本会话发现并修复）**：

- **症状**：fmbench（ymfm）渲染的绝对音高比引擎低**一个八度**（×0.5）。纯音参考 patch：C4→130.6（目标 261.6）、A4→220.2（目标 440）、C5→261.7（目标 523.3），比率恒为 0.5。
- **判定（非推断）**：① **引擎公式正确**——`f=(fnum<<block)*7987200/(144*2^20)`（`F03 §S1`），A4 = block4/fnum520 = 440 ✓；② **fmgen 正确**——NP2kai `opna.c:123` 以 `OPNA_CLOCK*2 = 7987200` 调 `OPNA_Init`，`SetFNum` 公式给出同一频率（= 用户实听）；③ ymfm `GeneralInfo.md:178` 载明 OPN `block_freq = [block]:[fnum]0`（**尾随 0 位**），`compute_phase_step` 遂为 `fnum<<1` 后 `>>2`（净 `>>1`），配 10.10 相位（满周期 2^20）与 FM 率 clock/144 ⇒ 恰好半数。
- **关键分辨**：ymfm 的**时间基（LFO/EG）在标称时钟下是对的**——flute 的 LFRQ=2 实测颤音 6.0 Hz ≈ 硬件 6.6 Hz。故**不能**靠「时钟 ×2」修（那会把颤音/包络也 ×2）。**只修音高**。
- **修复**：`fmbench.cpp::write_patch_and_keyon()` 写 `$A4/$A0` 时把 FNUM **×2**（引擎 fnum ≤1023 ⇒ 倍数 ≤2046，稳落 11 bit）。验证：C4/A4/C5 均 100.0%；flute 颤音仍 ~6.0 Hz、起音 22.5 ms 不变。新增 `test_fm_timbre.py::test_oracle_pitch_is_engine_octave` 钉死该八度关系。
- **缓存失效**：`fm_render.py` 的 job 键原先不含二进制身份 ⇒ 重编 fmbench 后会命中旧（半音高）缓存。已在键中加入 `BENCH_BIN` 的 `size:mtime_ns`（`_bench_id()`）。

**验证**：pytest **792 passed / 1 skipped**（原 779）；`test_fm_timbre.py` 10 项全过（oracle 在本环境可构建，未 skip）。

**遗留（P1c/P2）**：`targets.toml` 全族 `calibrated=false`——带值为设计意图，待 P1c oracle↔NP2kai 对齐 + P2 调音后逐族翻 true（flute 实测 3f=−51.1 dB 低于设计带 [−35,−25]，属 P2 待调）；`bass.fmp` 等串行 patch 载波系数仍待重估。
