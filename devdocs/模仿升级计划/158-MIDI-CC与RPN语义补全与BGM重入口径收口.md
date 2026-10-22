# 158 — MIDI CC/RPN 语义补全与 BGM 重入口径收口

> **状态**：`计划中`
> **版本**：`0.3.047`（撰写时）
> **创建**：2026-10-20
> **类型**：实施计划（非实现轮，零代码）
> **前序**：`123`（MIDI→FM 通路 S0–S5，CC 语义「只认 CC64」的 v1 决策）、`146`/`147`（事件模型/分片）、`144`/`145`（外部项目调研，本计划净增量来源之一）、`155`/`157`（近况：legato tie 撤销、声部分配）
> **范围声明**：仅本文件 §三 的 A/B/C/D 四项。RHYTHM（`159`）、颤音 CC1（`160`）、工具（`161`）、候选池（`162`）均不在本轮。
> **坐标说明**：`file:line` 为本计划撰写时实测坐标，随实施位移；实施后须重校并更新 `test_devdoc_refs` 白名单。

---

## 一、背景与动机（实测数据，非推断）

对 `assets/demo-a2/bgm/*.mid` 逐事件解析（本计划撰写时执行）：

| 曲目 | CC7（音量） | CC10（pan） | CC1（颤音） | RPN | ch10 音符 |
|---|---|---|---|---|---|
| `Melody Town Theme.mid` | ch1=**100**（×2，含回绕前重复） | ch1=64 | 无 | (0,0) 数据=12（弯音范围 ±12 半音声明） | 0 |
| `Icy Garden.mid` | ch1/2/3=127 | ch1/2/3=64 | 无 | 无 | 0 |

由此得出三件事：

1. **现存缺陷（小）**：`melody_town` 的 CC7=100 在 **MPU 后端生效**（`audio.c:605-620` 逐字节原样转发），但在 **FM 后端被丢弃**（`fmseq.c:436-443` dispatch `0xB0` 只认 CC64）⇒ 同一首曲两个后端混音差约 **−1.7 dB**（100/127）。这是「同一首曲在有/无 MPU 的机器上响度不同」的后端一致性缺口。
2. **隐性口径缺口**：`melody_town` 经 RPN(0,0) 声明弯音范围 **±12 半音**，而 `fmopn_bend_ratio()`（`fmopn.c:79-97`）按 **±2 半音**固定系数实现（`4096 + (bend-8192)*502/8192`，2^(2/12)−1=0.1225 的定点化）。现曲 4 处 bend 事件值全为 8192（居中）故**暂无影响**；一旦未来素材使用 bend，音程精度错误。
3. **价值重估**：CC10=64（居中）、CC1=0 处、ch10=0 音符 ⇒ 本文件只处理「后端一致性 + 声明口径」，不承诺任何现曲可闻改善。

## 二、现状坐标（现状与差距）

- FM 后端 CC 处理：`fmseq.c:436-443` — `case 0xB0` 仅 `ev->b1 == 64`（踏板），其余 CC（7/10/64 以外全部，含 RPN 101/100/6）静默丢弃。
- MPU 后端：`audio.c:605-620` — `hal_midi_out(st); hal_midi_out(e->b1); if (status != 0xC0/0xD0) hal_midi_out(e->b2);` 原样转发 ⇒ CC7/CC10/RPN 全部生效。
- 全局音量：`audio.c:221-234` `bgm_apply_volume()` — 起播时对 16 通道各发一次 CC7=`g_bgm_vol`（`g_bgm_vol` 来自 `USER.CFG` `bgm_vol`），**MPU 侧**。FM 侧对应 `hal_fm_set_volume(15-atten)`（c53 S5）。两机制并存不冲突，但 FM 侧无**每通道** CC7。
- Patch TL 路径：`fm_write_patch()`（`fmseq.c:162+`）按 velocity 与 patch 算子表算 4 个 TL 写出；`$B4` 由 `fmseq.c:186-189` 组合 patch 的 pan/AMS/PMS 字段回写（c64 S7）。
- Bend 路径：`fm_apply_bend()`（`fmseq.c:368+`）→ `fmopn_bend_ratio(bend, &block, &fnum)`（`fmopn.c:79-97`）。
- 事件过滤职责边界：`midi_parse` 不过滤任何 CC（c51 去通道过滤）；过滤在 dispatch。⇒ 新 CC 语义全部落在 `fmseq`，`midi.c` 零改动。
- 「读档恢复 BGM」核实（**非缺口**）：naiz `save` 载入 → `nb_saveload` → `scene_switch()` → `audio_stop_all()` → `nb_load()` **从头重放脚本**，`nbook001.nb:3` / `nbook002.nb:4` 的 `bgm(){}` 在重放首屏即重新触发 ⇒ ADV98 需要 resume 模式是因为它不重放脚本（`ADV98/src/main/ADVMachine.cpp:4941`：load 时游戏暂停、BGM 不停、恢复时无 BGM-restore 路径），naiz 结构上已覆盖同名能力。**本条从工作项剔除，仅保留一项实机验证**（§五）。

## 三、方案

### A. CC7 每通道音量（FM 后端）

**模型**：PMD `pmd_fm_vol_out`（`98fmplayer/pmd/fmdriver_pmd.c:1522-1636`，BSD-2，附来源注释）——音量 = 通道状态 `vol` 对**载波 TL 附加衰减**，`tl' = min(127, tl_base + (127 - vol))`，**不重键、不重写全套 patch**，仅回写载波 TL 寄存器。

**naiz 落点**：

1. `Fmseq` 增每 MIDI 通道状态 `uint8_t vol[16]`（初值 127，`fmseq_init`/`fmseq_stop` 复位——注意 `fmseq_stop` 的复位循环须与 `age` 复位同轮补齐，c75 教训）。
2. dispatch `0xB0` 增 `case 7`：存 `vol[ch]`，对**该通道当前 sounding 的 FM 声部**立即按公式重写载波 TL（不 keyon）。SSG 打击乐路径不参与（无 GM 通道音量语义）。
3. note-on 时 `fm_write_patch` 的载波 TL 计算并入 `vol[ch]` 衰减项（velocity 与 vol 叠加顺序：先 velocity 后 vol，两者都是加性 TL，`min(127)` 封顶）。
4. 载波识别：复用既有算法→寄存器槽映射（`fmopn_op_slot`，c66 语义不变）。

**优先级低于 D 的前置问题**：无。可独立合入。

### B. CC10 每通道 pan（`$B4` L/R）

- 状态 `uint8_t pan[16]`，初值取「等效居中」（`$B4` bit7=L、bit6=R，居中=0xC0 两者皆开；patch 自带 pan 字段照旧作**该通道从未收到 CC10 前**的缺省）。
- dispatch `0xB0` 增 `case 10`：3 级映射 `L=(v<96), R=(v>32)` ⇒ v≤32 仅左 / 33–95 双开 / ≥96 仅右。收到后即覆盖该通道后续所有 `$B4` 回写中的 pan 位（AMS/PMS 位不动，仍取 patch 字段）。
- **不重键**：对 sounding 声部立即回写 `$B4`（只改 pan 位）。

### C. RPN(0,0) 弯音范围解析（替代 ±2 硬编码）

1. dispatch `0xB0` 增 RPN 状态机：`CC101/100` 选 RPN（101=MSB、100=LSB），`CC6` 数据入口，`CC101=127 且 100=127` 视为 deselect。仅当 RPN=(0,0) 时采 `CC6` 高字节 → `bend_range[ch]`（半音，夹逼 1..48；缺省 2，即现行为）。
2. `fm_apply_bend` 的固定系数改为按 `bend_range[ch]` 计算：`factor = 2^(((bend−8192)/8192) × range/12)`。落点：`fmopn.c` 新增纯函数 `fmopn_bend_range_ratio(int bend, int range_semis, int *block, int *fnum)`（沿用 `fmopn_bend_ratio` 的定点/查表骨架；`double fmopn_ratio_freq` 已在库中，允许 double）。旧 `fmopn_bend_ratio` 保留为 `range=2` 的封装或直接改签名（单测锚点同步）。
3. RPN 全套（101/100/6）事件现曲已在流中（±12 声明）⇒ 解析器落地即**自动对齐声明**，无素材改动。

### D. 同键重入守卫（`audio_bgm_start`）

- 现状：`audio_bgm_start()`（`audio.c:238+`）不看当前键，同键重发 = 停旧起新（`wall0`/`idx` 复位 + `fmseq_stop`）。
- 改动：起播前比较「请求键」与「当前在播键」（`g_bgm` 需新增 `char key[...]` 或复用 TOC 名缓冲）；**同键 → `hal_log("AUD BGM skip (same key)\r\n")` + 直接 return**（不打断当前相位）。异键/未在播 → 现行为不变。
- **边界（刻意保留）**：`scene()` → `audio_stop_all()` 使场景切换后 `g_bgm_on=0` ⇒ **跨场景同键重播不受此守卫影响**（这是 AGENTS 十四.6 既定规则，不动）。守卫只拦「同场景内、BGM 仍在播时」的重复 `bgm(){key}`。
- 语义出处：ADV98 `onresume`（`BGMPlayerBase.cpp:659`）同键续播、异键切歌；naiz 用「重放脚本 + 同键 no-op」达成同型行为。

## 四、改动清单与验证

| 文件 | 改动 | 守卫 |
|---|---|---|
| `core/lib/fmseq.h` | `Fmseq` 增 `vol[16]`/`pan[16]`/`bend_range[16]`（初始化/复位语义写进头文件注释） | `test_fm_seq.py` ctypes 结构体镜像同步 |
| `core/lib/fmseq.c` | dispatch `0xB0` 增 7/10/101/100/6；`fm_write_patch` 载波 TL 并入 vol；`fm_apply_bend` 接 range | 新用例：CC7→载波 TL 寄存器值、CC10→`$B4` pan 位、RPN(0,0)+CC6=12→bend 系数=±12 半音档、未发 CC10 时 pan 位不变 |
| `core/lib/fmopn.c/.h` | `fmopn_bend_range_ratio`（或改 `fmopn_bend_ratio` 签名） | `test_fmopn` anchor 更新 |
| `core/engine/audio.c` | `g_bgm` 增当前键；`audio_bgm_start` 同键守卫 | 实机串口 `AUD BGM skip (same key)`；`test_devdoc_refs` audio.c 行号白名单重校（现行 pin：247/408/417/315 与 SUPERSEDED 末档 401/410/308） |

**回归判据**：现曲（CC7 只在起播前、CC10=64 居中）在 FM 后端的寄存器序列**除 CC7 生效导致的载波 TL 差**外无变化；「起播前全局 CC7」与既有 `bgm_apply_volume`→`hal_fm_set_volume` 的语义不打架（通道 vol=100 与全局 atten 是两级，最终响度 = patch × vel × chvol × global，逐级夹逼 127）。

**流程**：实施轮走 pytest → `make -C core`（0 诊断，`core/*.err` 空）→ fullaudit → `bump_version`（0.3.047→下一号）→ CHANGELOG。改 `audio.c` 必重校 `test_devdoc_refs` 白名单；新增导出函数须登记 `docs/B90`。

## 五、验证（实机）

1. 有 MPU 的环境播 `melody_town`：响度应较修前低 ~1.7 dB（CC7=100 生效），与无 MPU 的 FM 后端一致。
2. 重放脚本中同场景重复 `bgm(){melody_town}`（若有）应见 `AUD BGM skip` 且音乐不重置。
3. 读档后 BGM 仍起播（§二 非缺口结论的确认项，一次即可）。

## 六、不做什么

- 不做 CC1/CC11/触后（→ `160`/`162`）；不做 CC7 曲中渐变以外的音量曲线；CC10 不做连续立体声像（3 级即止）。
- 不改 MPU 后端转发语义（它已经是对的）；不改 `midi.c` 事件过滤。
- 不动跨场景 `audio_stop_all` 行为。

## 七、风险与回退

- 风险低（纯库状态 + TL/`$B4` 回写路径已有）。回退 = 还原 dispatch case 与结构体字段。
- RPN 状态机的唯一雷区：CC6 在非 RPN(0,0) 期间是 other-CC（must-ignore）——状态机须先判 RPN 选择态再采样。

## 八、遗留 / 后续

- 通道压力（0xD0）与 poly pressure 忽略现状不变 → `162` 候选池。
- `vol[16]` 等新状态的复位矩阵（init/stop/loop）须在实施 PR 中逐项打勾，防止 c75 型残留。

## 九、来源清单

| 来源 | 许可证 | 用途 |
|---|---|---|
| `98fmplayer/pmd/fmdriver_pmd.c:1522-1636`（`pmd_fm_vol_out`） | BSD-2 | CC7 载波 TL 附加衰减模型蓝本（借思路，附注释） |
| `98fmplayer/src/main/ADV98/.../BGMPlayerBase.cpp:659`（`onresume`） | MIT | 同键 no-op 语义出处 |
| `98fmplayer/src/main/ADV98/.../ADVMachine.cpp:4941` | MIT | load 时 BGM 不停（佐证 naiz 非缺口结论） |
| `docs/refdocs/F03_opna_fm_and_bgm_routes.md` | 仓内 | `$B4` pan/AMS/PMS 位义 |
