# 123 — MIDI 转 FM 通路实现计划（SMF 解析器复用 + 6 声部分配 + 自研 32 字节音色格式）

> **状态**：**实现在完成中**（S0–S5 代码已落地，S7 实机/NP2kai 验证待做；详见下方实现记录）
> **日期**：2026-10-05
> **关联版本**：`0.3.022`（S0–S5 落地轮）
> **前置**：`devdocs/122-BGM本地静音根因与音频通路取舍.md`（其 §5.2 与 `:213` 由本文接替，见 §一）、`docs/refdocs/F03_opna_fm_and_bgm_routes.md`（通路选型与寄存器调研，本文为其落地计划）
> **参考**：`docs/refdocs/F01_sound_boards.md`、`docs/refdocs/F02_86pcm_registers.md`、`docs/B92-NB脚本命令参考.md`
> **行号坐标系**：本文写于 `0.3.021` 现行坐标。**实现落地后 §二 的全部行号必须重校**（§十「规格与实现的收敛责任」）
>
> ## 📌 实现记录（0.3.022 追加；正文按 AGENTS.md §十 所述「计划中」允许修订，本轮以追加为主）
>
> | 阶段 | 落地 | 位置 | 主机测试 |
> |------|------|------|------|
> | **S0** | 端口分工（0.3.022 文档轮完成） | `F03` §3.8 | — |
> | **S1** | M1 `fmopn` 完成 | `core/lib/fmopn.{h,c}` | `tools/tests/test_fmopn.py`（12 项）✅ |
> | **S3** | M5 音色编译器 + `FMP` 打包 + `fmp_map` | `tools/naiz_audio/fm_patch.py`、`pack_audio.py`、`tools/naiz_build/export_asset_table.py` | `tools/tests/test_fm_patch.py` + 更多 ✅ |
> | **S2** | M3 `hal_fm_*` 端口层 | `core/plat/hal_audio.c`（`hal_fm_detect/init/shutdown/write_reg/set_volume`，`0188h–018Fh` 唯一写处） | ❌ 需硬件/S7 |
> | **S4** | M2 `fmseq` 分配器 | `core/lib/fmseq.{h,c}`（+`fmseq_finished` loop 辅助） | `tools/tests/test_fm_seq.py`（14 项）✅ |
> | **S5** | M4 引擎接线 | `core/engine/audio.c`（后端自动检测、FM 泵、loop、音量、patch 装载兜底） | ❌ 需硬件/S7 |
| **S6** | 默认音色内容 + GM→族映射 | `assets/demo-a2/fm/*.fmp`（15 族）、`tools/naiz_audio/gm_families.py`、`export_asset_table.py` 生成 `fmp_gm_map[128]`、`audio.c` 接线 | `test_fm_patch.py` + `test_gm_map.py` ✅ |
>
> **本轮关键订正**（见 §2.4）：A466 各音量通路（VOL1/VOL2/VOL6）**各持独立 4-bit 衰减寄存器**（MAME 解码 `m_vol[line_select]`），写入只改所选路径，**「两个路径互相覆盖」的担心不成立**——FM 写 `000b|atten`、PCM 写 `101b|atten（0xA0|step）` 互不影响，无需统一入口。
> **§ 十 检查**：S1/S3/S4 测试计数与实现记录一致；`audio.c` 行号已随 M4 位移，`tools/tests/test_devdoc_refs.py` 的 `LINE_REF_WHITELIST` 已更新为现行行、含 devdoc 119 过期行号的 `SUPERSEDED_AUDIO_LINE_REFS` 分类。
> **遗留（仅 S7）**：VOL1/VOL2 step 曲线实测；§1.5 五条判据实机验证；音色试听（S6 已交付 15 族默认值，见 `devdocs/124`，逐族微调归 S7）。S6（内容 + gm_map）已完成，历史终态「`gm_map=NULL` 全映射 family 0」不再成立。

---

## 一、前序结论订正与目标

### 1.1 承接 devdoc 122 §5.2 的 ERRATA

`devdocs/122-*.md` §5.2「由此得到的方向」推荐了一条**已被本项目判死的路**。按 §十 的四步订正路径，原文正文一字不改、仅在头部追加 ERRATA 块，完整记录由本文承载。

| 项 | 内容 |
|---|---|
| **症状** | §5.2 推荐「用 tracker 作曲并**导出 WAV**（立刻可听可交付，不依赖引擎实现 FM）」，并以「切断循环依赖」为理由论证该方向可行 |
| **判定过程** | ①WAV 必须经 `wav_convert.py` 转 `.pcm` 才能进管线（`docs/B92` §3）；②`.pcm` 占用 86 板**唯一一条** PCM FIFO（`F02` §1、AGENTS §十四）；③该 FIFO 与 `voice`/`sound` 共用、后到覆盖（devdoc 122 根因二）；④⇒ BGM 走 PCM 会与语音互顶 |
| **根因** | §5.2 的「切断循环依赖」论证建立在「WAV 能当 BGM 交付」这个前提上，而该前提与项目既有约束**直接冲突**。`naiz-guildbook/pages/mc06-音频通路机制.html` §3 方案 D 早已把这条路标注 `❌ 行不通`，两处文档结论互斥而无人发现 |
| **修复** | 出口改为**导出 MIDI**，喂给将来的 FM 通路。方向本就正确——`mc07` §3 工作流图末尾一直写的是 `└─▶ 引擎（YM2608 后端）`；错的是 122 §5.2 单独把 WAV 抬成主出口 |
| **验证** | 本文 §三 的数据流不经 PCM；§七 S7 的成功判据含「BGM 进行中 `voice` 正常发声且不被顶掉」，该判据在 WAV 方案下**不可能成立**，在 MIDI→FM 方案下成立 |

同段另两处事实错误（已在 ERRATA 块记录）：

- **SSG 通道数错**：§5.2 称「2608 = 2612 的 6FM + **6SSG** + ADPCM」。两个芯片都不是 6——**YM2608(OPNA) 是 3 通道 SSG**（`F03` §2），**YM2612 是 9 通道**（3 颗 YM2149）。且该式**漏了 RHYTHM**（2608 独有，6 通道）。
- **`:213` 待研究项已收敛**：原文列的「FM 乐谱格式选型（MML/PMD `.MML` 采样 vs 直接驱动 YM2608 端口序列 vs MIDI+音源映射）」由本文 §1.2 决策闭合。注意原文把 **MML 称作「采样」**——MML 是纯文本记谱法，不是采样数据，术语亦误。

### 1.2 已定决策

| 项 | 决定 | 理由 |
|---|---|---|
| **输入格式** | **MIDI**（SMF），复用 `core/lib/midi.c` | 解析器已把 **velocity / program change / CC / pitch bend** 全部保留（`core/lib/midi.c:238` 保留 `0x80–0xEF` 全部通道语音消息），力度→TL 与弯音→F-number 偏移都是现成数据，**不必改解析器**；且项目现有 AI 工具链（Mureka / Suno Studio / basic-pitch）输出全是 MIDI |
| **后端选择** | **自动检测**：`hal_audio_detect()` 返回有 MPU-401 → 走现有 MIDI 通路；无 → 走 FM | 见 §八.1 的交付风险 |
| **v1 范围** | **FM 6 通道 + SSG 3 通道**；**RHYTHM 推迟** | SSG 3 通道本身即方波 + 噪声源，足够合成底鼓/踩镲/军鼓（`mc06` §5 已有此建议）；**推迟 RHYTHM 使实机与 NP2kai 行为一致**（见 §1.3） |
| **音色内容** | **另开 devdoc**；本文只定**格式与机制** | 见 §五、§六 |
| **RHYTHM 素材** | v1 不涉及 | `2608_*.WAV` 是 **NP2kai 模拟器侧**的 YM2608 内置 ROM 镜像，实机不需要（详见 §1.3） |

### 1.3 为什么推迟 RHYTHM（一条实测无关的理由）

YM2608 的 RHYTHM 6 通道鼓声读**芯片内置 ROM**，实机零素材依赖。但 `2608_BD.WAV` / `2608_SD.WAV` / `2608_RIM.WAV` / `2608_TOP.WAV` / `2608_TOM.WAV` / `2608_HH.WAV` 是 **NP2kai 模拟器侧**用来补这段 ROM 的文件（`F03` §3.6、§7 第 9 条；`HH` 在库中标注 Optional）。

⇒ 做 RHYTHM 就引入**唯一一处「实机有 / 模拟器要外挂」的行为差异**，而这类不一致正是 AGENTS §八 五禁所列「每一条都曾让错误的结论看起来完全正常」的形态。v1 不做 RHYTHM，则 FM 输出在实机与 NP2kai 上**逐字节一致**。

> **⚠ 顺带订正 `mc06` 的归因错误**：`mc06` §2 表与 §5 原写「在 PC-98 上通常要另外备 `2608_*.WAV`，缺了就完全没声音」。这是**归因错误**——它是模拟器缺 ROM 镜像，不是硬件缺素材；且「完全没声音」过强，缺的只是鼓通道、FM 通道照样响。该错误已在本轮修正（会让创作者误以为上真机还得准备素材，从而误判工作量）。

### 1.4 目标与不做的事

**目标**：`bgm(){key}` 在**无 MPU-401** 的机器上出声，且与 `voice`/`sound` 同时可闻。

**不做**（明确排除，避免日后重开讨论）：

- 不引入 PMD 作为运行时依赖（实模式互操作撞 AGENTS §四 禁止表，且独占 OPNA）
- 不做 WAV → FM 音色（欠定逆问题，无解；`mc06` §4）
- 不改 NB 脚本语法（`bgm(){key}` / `bgm(stop)` 保持不变）
- 不做 S98 / VGM 播放器（`mc06` §3 方案 B/C 降为备选；VGM 仅保留为将来的精确回放/对照手段）
- 不做 RHYTHM 鼓组（§1.3）
- 不做 ADPCM 采样播放（与 PCM 通路无关，另议）

### 1.5 成功判据（5 条，全部可测）

| # | 判据 | 验证手段 |
|---|---|---|
| 1 | 无 MPU-401 环境下 `bgm(){key}` 出声 | NP2kai 串口出现 FM 后端标记 + 寄存器写 trace；音频可闻 |
| 2 | BGM 进行中 `voice` 正常发声且**不被顶掉** | 两者同时段发声（**该判据在 WAV/PCM 方案下不可能成立**，是 §1.1 的判定器） |
| 3 | `bgm_vol` 对 FM 生效（无需新增用户设置） | 改 `USER.CFG` 的 `bgm_vol` 后 FM 音量实测变化（§2.4 的 VOL1/VOL2） |
| 4 | `audio_tick()` 每帧新增开销有上界且**留证** | 串口打每帧耗时；不达标即回退设计而非硬扛 |
| 5 | OPNA 寄存器写入序列**可逐条核对** | trace 打印 `(port, addr, val)` 三元组，与 `F03` §3 寄存器表对表 |

---

## 二、现状坐标

### 2.1 MIDI 通路（**复用，不改**）

| 位置 | 内容 |
|---|---|
| `core/lib/midi.c:254` | `midi_parse()` —— SMF 解析入口，输出时间有序的 `MidEvent[]` |
| `core/lib/midi.c:238` | `ndata = ((st>>4)==0xC \|\| (st>>4)==0xD) ? 1 : 2;` —— **保留全部通道语音消息 `0x80–0xEF`**，即 note on/off（含 velocity）、poly pressure、**CC**、**program change**、channel pressure、**pitch bend** |
| `core/lib/midi.h:36-40` | `MidEvent { tick_ms; b0; b1; b2; }` —— 原始字节，**未做任何解释** |
| `core/lib/midi.c:364` | `midi_free()` |
| `core/engine/audio.c:97` | `audio_bgm_start()` —— 取资产 → `midi_parse()` → 存 `g_bgm` |
| `core/engine/audio.c:343` | `audio_tick()` —— 60Hz 事件泵 |
| `core/engine/audio.c:370-374` | **透传点**：`hal_midi_out(st); hal_midi_out(b1); [b2];` —— 三个字节原样丢 UART |
| `core/engine/nb_audio.c:17` | `cmd_bgm()` —— 命令面，`bgm(){key}` / `bgm(stop)` |
| `core/plat/hal.h:168` | `hal_midi_out()` —— HAL 边界（`core/plat/` 之外不得触碰硬件，AGENTS §五） |

**结论：MIDI→FM 只需在 `audio.c:370-374` 这个透传点插入一层翻译，前半段（解析、时钟、循环、释放）完全不动。**

### 2.2 时钟（**必须复用，不可另起**）

| 位置 | 内容 |
|---|---|
| `core/plat/hal.h:142` | `hal_wallclock_smooth_ms()` |
| `core/engine/audio.c:141` | `g_bgm.wall0 = hal_wallclock_smooth_ms();` |
| `core/engine/audio.c:362` | 事件泵用 **smooth** 时钟，不用裸 `hal_wallclock_ms()` |

**平滑时钟是 devdoc 107 / 0.2.134 的修复**：NP2kai 下裸墙钟会卡顿 3–6 s 再跳 +1000..+6000 ms，导致 `cur` 在空洞里停滞、追帧时把事件积压一次性喷发（音爆）。**FM 后端必须接同一个 `hal_wallclock_smooth_ms()`**，另起时钟等于重新引入该 bug。

### 2.3 PCM 通路（**不动，但有两个交互点**）

| 位置 | 内容 |
|---|---|
| `core/plat/hal_audio.c:76-80` | PCM 端口：`A460`/`A466`/`A468`/`A46A`/`A46C` |
| `core/plat/hal_audio.c:143` | `outb(PCM_ID_PORT, 0x01);` —— **OPNA mask：bit0 = 选 OPNA，bit1 = 0 = 不强制静音** |
| `core/plat/hal_audio.c:155` | `outb(PCM_STATUS_PORT, PCM_VOL_PATH_PCM \| g_pcm_vol);` —— `0xA0\|step` |

**交互点 1（危险）**：`:143` 那个 `0x01` 的 **bit1 是「强制 OPNA 静音」**（`F02` §3.2）。若日后有人改 PCM 初始化时动了这个写值（例如为省电写 `0x00`），会**静默把整条 FM 通路静音**，且 PCM 一切正常 ⇒ 典型「错误结论看起来完全正常」。

**交互点 2**：`A460` 是 OPNA **选择**寄存器（bit0 选 OPNA/OPN），与 FM 端口窗口 `0188h–018Fh` 是两回事，但**同属一颗芯片的生命周期**——FM 后端初始化应当也确认一次当前选的是 OPNA。

### 2.4 音量（**利好：无需新增用户设置**）

`docs/refdocs/F02_86pcm_registers.md:100-101` 记载 `A466h` 电子音量有 **FM 路径**：

| 路径码 | 含义 |
|---|---|
| `000b` | VOL1 —— FM 音源**直接**输出电平 |
| `001b` | VOL2 —— FM 音源**间接**输出电平 |
| `101b`(`0xA0`) | VOL6 —— PCM 路径（现 `pcm_vol` 已实现，`hal_audio.c` 写 `101b`） |

⇒ **`bgm_vol` 对 FM 生效不需要新的 pref、不需要新的设置界面项**：`bgm_vol` → `A466h` VOL1/VOL2，`pcm_vol` → `101b`，同端口不同路径码。

> **⚠ 待实测确认**：VOL1/VOL2 的**具体 step 编码与衰减曲线**未实测（F03 §7 未覆盖此项）。S5 阶段必须实测，不能照抄 PCM 的「0=最响..15=最轻」倒序假设。
>
> **⚠ 已消解（0.3.023）：两条路径不存在互相覆盖。** A466 的 bit7–5 **选择**通路，各通路**各自独立的 4-bit 衰减寄存器**（MAME 解码 `line_select = data >> 5; m_vol[line_select] = data & 0x0f`）。FM 写 `000b|atten`、PCM 写 `101b|atten` 只改各自路径，**无需统一收口**。`hal_fm_set_volume()` 现已写 `000b|atten`，`hal_pcm_set_volume()` 保持写 `0xA0|step`。

### 2.5 资产管线（音色库要接进来）

| 位置 | 内容 |
|---|---|
| `tools/naiz_audio/pack_audio.py:63` | `WHERE type IN ('BGM','SND','VC')` —— **需扩为含 `FMP`** |
| `tools/naiz_audio/pack_audio.py:98` | `if asset_type != 'BGM': _validate_pcm(...)` —— PCM 校验只对非 BGM 生效；`FMP` 须同样跳过 |
| `ASSETS.DB` | `assets.img_map` 表；`filename` 列对 BGM/SND/VC 相对 `assets/<项目>/`（`naiz_lib.project_assets_dir()` 为单一事实源） |
| AGENTS §二 | 源素材唯一位置 = `assets/<项目>/`，与 `png/`、`anim/` 同根；**不进部署树** |
| AGENTS §十一 | `AUDIO.DAT` 的 TOC 条目名受 **DOS 8.3** 约束，`name` 截断后必须互异（`pack_audio` 硬拒碰撞） |

---

## 三、架构与数据流

```
                    ┌─────────────── 现有（不动）───────────────┐
  bgm(){key} ──▶ cmd_bgm() ──▶ audio_bgm_start() ──▶ midi_parse() ──▶ MidEvent[]
                    │                                                  │
                    │                                        tick_ms 有序，原始字节
                    ▼                                                  ▼
              ┌─────────── 新增 ───────────┐            ┌──────────────────────┐
              │ M2 fmseq：MIDI → 6 声部    │◀───────────┤ audio_tick() 事件泵  │
              │  · patch 映射（§六）       │  每帧消化   │ （平滑时钟 §2.2）    │
              │  · 通道分配 / 抢声          │  到期事件   │  替换 :370-374 透传  │
              │  · 力度 → TL               │            └──────────┬───────────┘
              │  · bend → F-number 偏移     │                       │
              │  · sustain / note-off       │                       ▼
              └───────────┬─────────────────┘            ┌──────────────────────┐
                          │  32B patch                    │ M1 fmopn：纯寄存器模型 │
                          ▼                              │  · bank 解码 (A1A0)   │
              ┌───────────────────────┐                   │  · 算子 → 寄存器地址   │
              │ 音色库（§五 32B 格式）  │                   │  · 音符 → F/BLOCK     │
              │ assets/<项目>/fm/*.fmp │                   └──────────┬───────────┘
              └───────────────────────┘                              │ hal_fm_write_reg()
                                                                    ▼
                                                          ┌────────────────────┐
                                                          │ M3 hal_fm_*        │
                                                          │ core/plat/         │
                                                          │ 唯一写 0188h–018Fh │
                                                          └─────────┬──────────┘
                                                                    ▼
                                            YM2608(OPNA) ──▶ BGM
                                            YM3433B      ──▶ voice / sound（§2.3 完全并行）
```

**三条架构约束**：

1. **HAL 边界**：`outb()` 只出现在 `core/plat/`（AGENTS §五）。`fmopn`/`fmseq` 是 `core/lib/` 的纯逻辑，**零 `outb()`**。
2. **与 PCM 无争用**：BGM 与语音走不同芯片、不同端口（F02 §1），二者可同时发声。这正是选 FM 的根本理由（`mc06` §1）。
3. **与 MPU-401 二选一**：同一时刻只启用一个后端（§八.1）。

---

## 四、模块分解

> **⚠ 本章列出的全部文件路径在 0.3.023 前均为**待建**——本文写于**零实现**之时，它们当时不存在。**S0–S5 落地后本章即规格**：`core/lib/fmopn.{h,c}`、`core/lib/fmseq.{h,c}`、`tools/naiz_audio/fm_patch.py`、`tools/tests/{test_fmopn,test_fm_seq,test_fm_patch}.py` 均已创建；`core/plat/hal_audio.c` 增补 `hal_fm_*`、`core/engine/audio.c` 接线 FM 后端。M6（`assets/<项目>/fm/*.fmp`）与 §1.2 的 GM→族映射**内容**属 S6，未落地。**本章后续未逐条校准的 `file:line` 以代码为准**（AGENTS §十）。

| 模块 | 文件 | 职责 | 依赖 | 主机单测 |
|---|---|---|---|---|
| **M1** | `core/lib/fmopn.h` `core/lib/fmopn.c`（待建） | 纯寄存器模型：bank 解码（A1A0）、算子 → 寄存器地址映射、音符 → F-number + BLOCK、32B patch 结构与校验、KEYON 位操作。**零 `outb()`** | 无 | ✅ |
| **M2** | `core/lib/fmseq.h` `core/lib/fmseq.c`（待建） | MIDI → 6 声部：patch 映射（§六）、通道分配、抢声策略、力度 → TL、bend → F-number 偏移、sustain pedal、note-off → release | M1 | ✅ |
| **M3** | `core/plat/hal_audio.c`（增补 `hal_fm_*`） | `hal_fm_detect()` / `hal_fm_write_reg(bank,addr,val)` / `hal_fm_init()` / `hal_fm_shutdown()`。**唯一写 `0188h–018Fh` 的地方** | **S0 端口消解** | ❌ 需硬件 |
| **M4** | `core/engine/audio.c`（改现有文件） | 事件泵分派、`audio_fm_start/stop` 生命周期、音量路径、串口 trace | M2/M3 | ❌ |
| **M5** | `tools/naiz_audio/fm_patch.py`（待建） | 构建期编译器：音色文本 → 32B 二进制；校验项；写 `ASSETS.DB` 的 `FMP` 行 | 无 | ✅ |
| **M6** | `assets/<项目>/fm/*.fmp`（待建目录） | 音色源（**文本**，人可读可 diff） | — | — |

**M1/M2 是纯逻辑、无硬件依赖、可在主机上穷举单测** —— 这是本计划最重要的风险削减点：**绝大部分验证不需要模拟器**。`tools/tests/` 下新增 `test_fmopn.py` / `test_fmseq.py`。

---

## 五、音色格式（32 字节）

规格详见 `docs/refdocs/F03_opna_fm_and_bgm_routes.md` §5.2/§5.3，本节只定**工程约束**。

| 项 | 决定 |
|---|---|
| 记录大小 | **32 字节**（覆盖 MUCOM88 / PMD `.FF` 的全部能力，另加 pan） |
| 源格式 | **文本**，存 `assets/<项目>/fm/*.fmp`（与 `bgm/`/`se/`/`voice/` 同根，AGENTS §二） |
| 编译 | M5 在**构建期**编成 32B 二进制，随 `AUDIO.DAT` 注入；引擎只 `memcpy` 32 字节，**不做文本解析** |
| 资产类型 | `ASSETS.DB` 新增 **`FMP`**；`pack_audio.py:63` 的 `IN` 列表与 `:98` 的校验条件同步 |
| DOS 8.3 | `name` 列受 8.3 约束，截断后互异（AGENTS §十一；`pack_audio` 已硬拒碰撞） |
| 许可 | **自研格式，无外部 patch 数据依赖** —— F03 §5.4 已确认未找到任何 CC0/公有领域 OPN patch 库，且工具许可≠数据许可 |

### 5.1 编译器校验项（不通过即 `RuntimeError`，禁止静默）

- 记录长度 = 32 的整数倍
- 算法号 ∈ `[0,7]`；每个算子的 `TL/AR/D1R/D2R/RR/SL/FB` 在 ymfm 范围内（**SR 是 0–31 而非 FMP 文档所写的 0–15**，F03 §3.3）
- **算子顺序按置换后的 `1/3/2/4`**（F03 §5.3）—— 写错则**静默音高全错**，必须在编译器与单测里各钉一遍
- DT 编码用**原始 0–7**（不转线性 −3..+3），避免跨格式歧义
- 名字字段长度上限按本格式定义（不兼容 MUCOM88 的 6B 与 PMD 的 7B，须显式选一个并写进格式文档）

---

## 六、GM → patch 映射策略

### 6.1 为什么不做 128 个 patch 的全表

- F03 §5.4：**未找到任何 CC0 / 公有领域 OPN patch 库**，现存全是受版权保护的商用或免费Ware 转储，且**转换工具许可不传递给数据**。
- 128 个 4-op patch 是**纯内容成本**（不是代码成本），且无人能核验许可。
- ⇒ 全表方案在许可与工作量上都不可行。

### 6.2 采用：族归并默认表 + 项目可覆盖

| 项 | 决定 |
|---|---|
| 默认表 | **~12–16 个自研 patch**，按乐器族（弦 / 铜管 / 木管 / 键盘 / 打击 / 合成 …）覆盖 |
| 映射 | 128 个 GM program → 族 → patch。映射表是**数据**（128 字节级），与代码分离 |
| 项目覆盖 | 项目可自带映射资产，覆盖默认表 |
| 未映射 program | **必须 `hal_log` 报警**（AGENTS §九.6 消灭静默失败），并回落到一个明确的默认族；**禁止静默映射到 patch 0** |

### 6.3 这是原理性损失，不可通过工程消除

`mc06` §5 已写明「GM 音色 ≠ FM 音色」：同一个 patch 换不同算法和包络可以完全不像原乐器。**族归并必然产生可听的音色偏差**，这是 6 复音 + 128 patch 的固有代价，不是 bug。

⇒ 创作者侧的应对是 `mc07` §3 已有的建议：**AI 出的 GM MIDI 必须在 tracker 里重做一遍**（换 FM 音色、改织体、删掉用不上的声部）以适配 6 通道。引擎侧不做「让 GM MIDI 听起来像 GM」的虚假承诺。

---

## 七、分阶段与硬门控

| 阶段 | 内容 | 完成判据（逐条写死） | 门控 |
|---|---|---|---|
| **S0** | 消解 `0188h`–`018Fh` **逐端口分工**（纯调研，不写代码） | 每个端口的「地址 / 数据」角色有一手出处（F03 §7 第 1 条） | **阻塞 S2，不阻塞 S1** |
| **S1** | M1 `fmopn` + `test_fmopn.py`（均待建） | F-number/BLOCK 表穷举正确；算子→地址映射全对；patch 32B 往返一致；`SR` 范围断言 0–31 | 无 |
| **S2** | M3 `hal_fm_*` 端口层 | 串口能逐条 trace `(port,addr,val)`；寄存器回读一致 | **需 S0** |
| **S3** | §五 音色格式 + M5 编译器 + `FMP` 打包 | 校验项全绿；8.3 name 互异；`ASSETS.DB` 行可解析到实际文件 | 无 |
| **S4** | M2 `fmseq` + `test_fm_seq.py`（均待建） | 16→6 分配、抢声、力度→TL、bend、sustain、note-off→release 全覆盖；并发压力用例不崩 | 需 S1 |
| **S5** | M4 引擎接线 + 音量 | `bgm_vol`→VOL1/VOL2 **实测**生效（§2.4 待确认项）；开关/音量场景回归 | 需 S2/S3/S4 |
| **S6** | 音色**内容**（~12–16 patch 设计） | **另开 devdoc** | 需 S3 |
| **S7** | 实机 / NP2kai 验证 | §1.5 五条判据全绿 | 需 S5/S6 |

**排序的关键事实：S0 只卡 S2，S1 可立即开工** —— 寄存器语义（bank 表、算子地址、音符换算）**不依赖端口映射**。这让调研等待期不阻塞主线。

---

## 八、待决项

### 8.1 后端选择：自动检测（1b）的交付风险

**决定**：`hal_audio_detect()` 有 MPU-401 → 现有 MIDI 通路；无 → FM。日志沿用现成标记 `AUD MPU OK` / `AUD WARN: no MPU-401`，`bgm` 再补一行后端名。

**收益**：本地 NP2kai 宿主通常无 MIDI 设备 ⇒ `hal_audio_detect()` 返回 0 ⇒ **本地必然走 FM 路径**。测 FM 时不会意外落到 MIDI 老路上，两条路各自独立可测。

**⚠ 风险（必须写明，否则日后一定被当故障报）**：同一条 `bgm(){key}` 脚本，**装了 MIDI 卡的玩家听到的是真 MIDI 音源音色，没卡的玩家听到的是我们的 FM 合成音色**。交付物随机器变。这是 1b 的固有代价，不是 bug。

**消除该风险的可能手段（未决）**：项目级显式覆盖（`config.toml` 加 `bgm_backend`），或为 FM 路径单独提供一批专用 `.mid`（不走 GM 音色）。二者都改变「同一份资产两处播放」的简洁性，留待实测后再定。

### 8.2 其它待决

| # | 项 | 现状 |
|---|---|---|
| 1 | `A466h` VOL1/VOL2 的 step 编码与衰减曲线 | **未实测**，S5 前不得照抄 PCM 的倒序假设 |
| 2 | 抢声策略的具体偏好（抢最旧 / 抢最弱 / 抢已 release 的） | 未定，S4 前需拍板；影响可听度 |
| 3 | SSG 3 通道的音色映射（是否也进 32B 格式，还是另立 SSG patch） | 未定，S3 前需拍板 |
| 4 | FM 是否需要独立的循环点（vs 沿用 MIDI 的整曲循环） | 未定 |
| 5 | 多声部编曲的 6 复音限制是否需要在**资产校验**阶段拦截 | 未定，可能需要一个 `nb_validator` 侧的过载告警 |

---

## 九、验证矩阵（对齐 AGENTS §八 五禁）

| 层 | 手段 | 纪律 |
|---|---|---|
| 主机单测 | `tools/tests/test_fmopn.py`、`test_fm_seq.py` | 穷举优于抽样；F-number 表全表断言 |
| 编译 | `make -C core` + `find core -maxdepth 1 -name '*.err' -size +0` | **诊断在 `.err` 不在 stdout**（0.3.014 教训：`\| grep Error` 会假通过） |
| 工具链 | `tools/env_setup/venv/bin/python -m pytest tools/tests/` | pytest 全绿**不构成文档正确的证据**（§十） |
| 全审计 | `./start.sh fullaudit` | — |
| NP2kai | `tools/diag/np2kai_ab.py` + 串口 trace | **`--forbid` 否定断言为确定性判据，点击计数仅作辅助**；**先 `build` 再 `make`**，否则跑的是旧引擎而日志一切正常 |

**五条禁令对本计划的直接适用**：

1. 禁把一次性 trace 观察当因果证据 —— 判 FM 出声要看**寄存器写序列 + 音频**，不看单次 `[AUDIO]` 行。
2. 禁只 `build` 不 `make` —— 改 `hal_fm_*` 后必须 `./makegame.sh build <game> && ./makegame.sh make <game>`；`makegame.sh test` 与 `np2kai_ab.py preflight()` 已有 `STALE_HDI` 门控。
3. 禁把竞态指标当判别器 —— 「音乐还在不在响」不是稳定判据；用**寄存器状态标记**（如 KEYON 位图）做否定断言。
4. 禁门控只覆盖单一通道 —— 成功判据 2（BGM + voice 同时响）必须**分别**门控 BGM 与 voice 两条通道。
5. 禁留下互相矛盾的文档 —— 本文的 §一 订正、F03 的 4 处修正、mc06 的 6 处修正、`mc06` 的 `2608_*.WAV` 归因订正，均为落实此条。

---

## 十、风险与已知不可解

| # | 风险 | 性质 | 缓解 |
|---|---|---|---|
| 1 | `0188h`–`018Fh` 逐端口分工未证 | **硬阻塞**（S2） | 猜错则整条 FM 通路**静默无声**。S0 必须查 NEC 未公開情報 / MAME `pc9801_86` 一手实现 |
| 2 | GM 音色 → FM 的听感损失 | **原理性不可解** | 族归并（§六）；创作者侧在 tracker 重做（`mc07` §3） |
| 3 | 6 复音对多声部编曲的硬限制 | **原理性不可解** | 资产阶段限制；§8.2 第 5 项的过载告警 |
| 4 | NP2kai FM 音质不作参考级 | 环境限制 | F03 §7 第 2 条（issue #112 实录 `tinny / distorted`，作者归因 fmgen 与音量混音且仍在调）⇒ **听感判据不能以模拟器为准**，只用于「有无/对不对」 |
| 5 | 1b 使交付物随机器变 | **已接受**（§8.1） | 文档写明；后续可加项目级覆盖 |
| 6 | `A460h` bit1 静默静音 FM | 易误改 | §2.3 交互点 1；建议加单测钉住 `0x01` 的写值语义 |
| 7 | smooth clock 被绕过 | 易误改 | §2.2；FM 侧只能调 `hal_wallclock_smooth_ms()` |

---

## 十一、踩坑预登记

| # | 坑 | 出处 / 机理 | 防线 |
|---|---|---|---|
| 1 | FM 侧另起时钟 ⇒ 追帧喷发音爆 | devdoc 107 / 0.2.134（`audio.c:362` 用 smooth 钟的原因） | §2.2；FM 只调 `hal_wallclock_smooth_ms()` |
| 2 | PCM 与 FM 音量写互相覆盖 | 二者共用 `A466h`，仅路径码不同（`F02:100-101` vs `hal_audio.c:155`） | 统一收口到一个音量写入口 |
| 3 | 改 PCM 代码时误动 `A460h` 写值 ⇒ 静默静音 FM | `hal_audio.c:143` 的 `0x01` bit1 = 强制静音 | §2.3；加单测 |
| 4 | `scene()` 只停 PCM 忘了停 FM | `scene_switch()` → `audio_stop_all()`；FM 也必须纳入，否则 BGM 跨场景泄漏 | S5 接线时核对 `audio_stop_all()` 覆盖 FM |
| 5 | patch 算子顺序写 1/2/3/4 | F03 §5.3：真实布局被置换为 **1/3/2/4**，写错则**静默音高全错** | §5.1 编译器 + 单测各钉一遍 |
| 6 | SR 范围写成 0–15 | F03 §3.3：FMP 官方文档此处有误，实为 **0–31** | 编译器范围断言以 ymfm 为准 |
| 7 | 未映射 GM program 静默落到 patch 0 | 违反 AGENTS §九.6 | §6.2 强制 `hal_log` |
| 8 | 音色库文件超 8.3 或截断后碰撞 | AGENTS §十一；`AUDIO.DAT` TOC 条目名 | `pack_audio` 已硬拒；新增 `FMP` 时同步该校验 |
| 9 | `2608_*.WAV` 被当成引擎素材依赖 | 它是 **NP2kai 侧** ROM 镜像，实机不需要（F03 §3.6） | v1 不做 RHYTHM（§1.3）；`mc06` 归因已订正 |

---

## 十二、本轮（文档轮）实际改动清单

**纯文档，零代码。** 未新增/修改任何 `.c`/`.h`/`.py`/`.nb`；`hal_fm_*` 未实现。**不 bump 版本**（仍 `0.3.021`）。

| 文件 | 改动 |
|---|---|
| `devdocs/123-MIDI转FM通路实现计划.md` | **新建**（本文） |
| `devdocs/122-BGM本地静音根因与音频通路取舍.md` | **仅头部**追加 `⚠ ERRATA` 块（§5.2 WAV 死路 / SSG 通道数 / `:213` 已收敛 / FamiTracker）；**正文一字未改** |
| `docs/refdocs/F03_opna_fm_and_bgm_routes.md` | 4 处：§1.2 已决化、§4 降为备选、§4.1 重构、**§4.6 重写**（消除自相矛盾） |
| `naiz-guildbook/pages/mc06-音频通路机制.html` | 6 处：§3 方案 A 已选定 / 方案 C 备选 / 推荐语 / §2 MML 行 / **§2 与 §5 的 `2608_*.WAV` 归因订正** |
| `naiz-guildbook/manual.html` | ui02 的 `settings.txt` → `config.toml` + `USER.CFG`（devdoc 120 已废止 `settings.txt`） |
| `CHANGELOG.md` | 第十三轮条目；并按 §十 步骤 3 给 `c51` 加订正标记链接本文（锚点与索引编号不动） |
| `AGENTS.md` | 头部摘要 + §十四 音频通路表加前向引用（**表内现有行未改** —— 那些是 current-state 陈述，仍然准确） |
| `docs/refdocs/README.md` | F03 描述的「MML 记谱法子集」改备选措辞 |

**未改**：`naiz-guildbook/pages/mc07-音频平台与工具.html` —— §3 工作流图末尾已是 `└─▶ 引擎（YM2608 后端）`，方向与本决策一致；两处 MML 提及均在工具表内（`mml2mdx`、MML 语法参考），属事实登记，未声称是本项目输入格式。
