# 135 — MIDI→FM 通路 S7：OPNA LFO 接入 + 15 族音色重做（试听基线）

> 状态：`实现完成待实机试听验证`
> 版本：`0.3.033`
> 相关：devdoc 123（MIDI→FM 通路总体计划，S0–S6）、124（S6 默认音色内容与 GM 映射数据）、125c/125d（flute 族历代调节史）、docs/refdocs/F03（OPNA 寄存器参考，本轮据 NP2kai fmgen 订正 `$22`/`$B4` 位域）、F04/F05（Timer/PMD 架构）
> 前序：124 明确定义 15 族为「结构合理起点，非成品」，把音质试听/微调**推迟到 S7**。本轮即执行 S7，并顺带交付一项 124 未预见的能力缺口（引擎无 LFO）。

## 1. 症状（用户实机反馈）

进场景 1 播 `Melody Town Theme.mid` 时，**原曲是笛子（flute），游戏里听成电子琴（electric organ）**。

## 2. 根因判定（结论：不是映射错误）

### 2.1 映射链端到端正确

| 环节 | 事实 | 位置 |
|---|---|---|
| SMF 解析 | Track 2 ch0 的 program change = **73（Flute）**，位于 tick 0 | `Melody Town Theme.mid`（format 1，division 96） |
| GM→族 | `fmp_gm_map[73] = 8` → 族 8 | `core/engine/nb_asset_table.h`（`gm_families.build_gm_map()` 生成） |
| 族→patch | 族 8 装载顺序 == `flute.fmp` | `fmp_map` 顺序与 `FAMILIES` 顺序一致（`test_gm_map.py` 守护） |
| program 存储 | `dispatch()` 的 0xCx 分支存 `seq->program[ch]` | `core/lib/fmseq.c:440`（解析 `core/lib/midi.c:238`） |
| 选族 | `fm_note_on` 经 `fm_family()` 取 patch | `core/lib/fmseq.c:147` |

**结论**：程序号、族映射、patch 装载全部正确落在 flute 族。

### 2.2 真正原因：`flute.fmp` 本身设计为近正弦 + 强同频调制

旧 `flute.fmp`（devdoc 124 §三第 8 行原文即写「单调制器近正弦」）用 `alg=2` + `op3` 调制器 `tl=8`（接近满强度）在**基频同频**上调制载波，产生丰富的基频边带 = 簧片/管风琴的「嗡嗡」谐波，正是「电子琴」听感来源。叠加**无任何颤音**（无 LFO），稳态又平又人工。

### 2.3 能力缺口：引擎从来没有 LFO

`fmopn`/`fmseq`/`hal_fm` 全链路**不写 `$22`（LFO 使能+速率）**，`$B4` 只写 pan。因此即使想要颤音也做不到。这是 124 未预见的结构性缺口。

## 3. 关键硬件事实（据 NP2kai fmgen 逐位核实）

`config.toml`/模拟器实际用 fmgen 合成，故以其源码为准（非二手文档）：

- **`$22`**：`bit3 = LFO 使能`，`bits2-0 = 速率 LFRQ`。`fmgen_opna.cpp` 的 `SetReg`：`lfodcount = reg22 & 8 ? lfotable[reg22 & 7] : 0`。
- **`$B4`**：`bits7-6 = pan L/R`（`(data>>6)&3`），`bits5-4 = AMS`（`(ms>>4)&3`），`bits2-0 = PMS`（`ms&7`），`bit3 = 保留`。F03 §3.3 原掩码记法自相矛盾，本轮已订正。
- **联动（关键）**：`FMMix()` 中 `if (!(reg22 & 0x08)) act &= 0x555;`——**全局 LFO 关闭时强制走无 LFO 合成路径，PMS 颤音同样失效**（不只是 AMS）。故 `$22` 是 PM/AM 的共同前置。
- **逐算子 AM 使能**：`$60` bit7（patch 的 `am` 字段）。AMS>0 但无任一算子 `am=1` 时 AM 不产生效果；PMS 不受此限制。
- **旧 patch 兼容性**：现有 15 族 `pan=0xc0`、AMS=PMS=0 ⇒ `(ms & 0x37)==0` ⇒ 走无 LFO 路径，加全局 LFO 后**听感零变化**。

## 4. 实现

### 4.1 patch 格式：byte25 复用为完整 `$B4`

原 byte25 = `PANL<<6|PANR<<4`（低 4 位保留=0）。现定义：

```
byte25 = pan(bits7-6) | AMS(bits5-4) | 0(bit3) | PMS(bits2-0)
```

- `tools/naiz_audio/fm_patch.py`：`_GLOBAL_KEYS` 增 `ams`(0–3)、`pms`(0–7)；`pan` 收紧为仅 bit7-6（`& 0x3F == 0` 否则报错）；`to_bytes` 组装 byte25。旧 patch（`pan=0xc0`，无 ams/pms）字节不变。
- `core/lib/fmopn.{c,h}`：`fmopn_patch_validate` 的 byte25 检查由「低 4 位必须 0」改为「**仅 bit3 必须 0**」；新增 `fmopn_patch_ams()`（bits5-4）/`fmopn_patch_pms()`（bits2-0）访问器；`fmopn_patch_pan()` 改为只返回 pan 字段（bits7-6）。`fmseq.c:189` 处由「直写整字节」改为**组合三字段回写 `$B4`**：`fmopn_patch_pan(p) | (fmopn_patch_ams(p) << 4) | fmopn_patch_pms(p)`——使三个访问器各有真实调用方（否则 `symbol_audit` A/B 节判死导出）。
- `core/plat/hal_audio.c`：`hal_fm_init()` 追加 `hal_fm_write_reg(0, 0x22, 0x08 | FM_LFO_RATE)`；`FM_LFO_RATE = 2`（≈6.6 Hz，全局单速）。

### 4.2 装载索引错位修复（`audio.c fm_load_patches()`）

**缺陷**：原实现 `n++` 仅在成功时前进，`continue` 跳过缺失/非法/`__dummy__` 条目 ⇒ 其后所有族索引**整体前移**，而 `fmp_gm_map[]` 固定以 0..N 索引 `g_fm_patches[]` ⇒ **任一 patch 失败即令其后所有 GM program 静默错配**（仅一行 WARN）。当前 15 族都能过校验故未触发，但属「静默失败」类。

**修复**：每个 `fmp_map` 条目**固定占用一个槽**——先以 `g_fm_default_patch` 预置，失败/缺失/`__dummy__` 时保留默认，`n++` 无条件前进；`g_fm_families` = 条目数。保证 gm_map 位置索引永不漂移。

### 4.3 flute.fmp 重做

`alg=4`（两组独立 2-op：`op1->op2 + op3->op4`）：
- 组 A（op1→op2）：弱调制器（`tl=40`）+ 强基频载波（`tl=8`）⇒ 稳态近正弦；
- 组 B（op3→op4）：八度（`mul=2`）载波，快起音 + 快衰减（`d1r=9`）⇒ 起音时一声「气声/泛音 chiff」，随后淡出留下纯基频；
- `pms=2`：自然轻颤音；`ams=0`。

### 4.4 15 族 LFO 分配（S7 试听基线）

| 族 | pms | ams | 说明 |
|---|---|---|---|
| piano | 0 | 0 | 打击类，无 LFO |
| bell | 0 | 0 | 无 LFO |
| organ | 0 | 1 | 全算子 `am=1` ⇒ 慢速旋转/颤音（无音高颤） |
| guitar | 0 | 0 | 拨弦，无 LFO |
| bass | 0 | 0 | 拨弦，无 LFO |
| strings | 3 | 0 | 弦乐群颤音 |
| brass | 1 | 0 | 持续音轻微颤音 |
| reeds | 3 | 0 | 簧片颤音 |
| flute | 2 | 0 | 见 4.3 |
| synlead | 1 | 0 | 主音轻颤 |
| synpad | 2 | 1 | 载波 `am=1` ⇒ 慢速合唱式音高+音量起伏 |
| synfx | 3 | 2 | 狂野颤音+抖动（已有 `am=1`） |
| ethnic | 3 | 0 | 西塔/拨弦弦鸣颤音 |
| perc | 0 | 0 | 鼓，无 LFO |
| sfx | 0 | 1 | 金属摩擦抖动（已有 `am=1`） |

未列入的 tonal 微调遵循 124 既有结构，仅新增 LFO 层；piano/bell/guitar/bass/perc 保持原设计。

## 5. 验证

- `make -C core` 0 诊断（`core/*.err` 空）。✅
- pytest：`test_fmopn.py`（byte25 bit3 守卫 + AMS/PMS 接受 + 访问器 + 三字段组合回写 `$B4`）、`test_fm_patch.py`（ams/pms 解析/编码 + pan 收紧 + 全库编译过 C 校验）、`test_fm_lfo.py`（新增，`$22` 写入门卫）、`test_fm_load_alignment.py`（新增，装载无 `continue` + 无条件 `n++` + gm_map 接线）。全套 **779 passed / 1 skipped**。✅
- `./start.sh fullaudit` **7/7**（symbol_audit A/B 空——为此把 `fmopn_patch_pan/ams/pms` 三字段访问器接入 `fmseq` 回写 `$B4`，消除「新增访问器无调用方」判死）。✅
- **实机试听未执行**（用户手工 build+make 后试听）：15 族音色为 S7 基线，需实机逐族试听迭代。

## 6. 遗留 / 下一步

- **15 族为试听基线，非终版**——每族在实机上是否可辨识、pms 深度是否合适，需用户 build+make+试听后反馈迭代（AI 无法试听）。
- **全局单速 LFRQ=2 的取舍**：不同乐器理想颤音速率不同（strings 慢、synfx 快），当前共用 6.6 Hz；如需分族速率须再扩格式字段（本轮不做）。
- **时序问题（颤动/拖/起播快）不属本轮**：仍待用户静置对白页 `[VC]` 串口数据，另行继续（承 devdocs 131–134）。
