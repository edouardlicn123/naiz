# 124 — MIDI 转 FM 通路 S6：默认音色内容与 GM 映射数据（15 族 patch + gm_map）

> **状态**：**已实现**（devdoc 123 的 S6 内容轮；音质试听归 S7）
> **日期**：2026-10-08
> **关联版本**：`0.3.023`（S6 内容落地轮）
> **前置**：`devdocs/123-MIDI转FM通路实现计划.md`（本文为其中 **S6** 的落地文档，§五 32B 格式 / §六 映射策略 / §七 判据）、`docs/refdocs/F03_opna_fm_and_bgm_routes.md`（OPNA 寄存器参考，§5.2/5.3）
> **行号坐标系**：本文写于 `0.3.023` 现行坐标。

---

## 一、S6 目标与边界（承接 devdoc 123 §七）

devdoc 123 §7「待确认项」遗留清单第 S6 项 = **音色内容**（默认族集 + GM program→族映射数据，另开 devdoc）。本轮兑现：

1. **默认族集**：15 个自研 32B patch（`assets/demo-a2/fm/*.fmp` 文本），按 GM 程序聚类，覆盖 128 个 GM program，零空档（消灭静默失败）；
2. **gm_map 数据**：128 项 GM→族索引表，作为**数据**（非引擎代码）随项目构建产物生成，与族 patch 行序锁步；
3. **接线**：`audio.c` 把 `fmseq_init(..., NULL, ...)` 改为传入 `fmp_gm_map`——引擎不再「全 program 回落 family 0」。

**边界（不做）**：
- **音质试听与微调归 S7**。本轮交付「结构合理、范围合法、C 校验通过、许可干净」的**默认值起点**，不是最终混音成品；
- **项目级 gm_map 覆盖**（devdoc 123 §6.2「项目可覆盖」）不做——当前严格约束「FMP 行序必须是 `gm_families.FAMILIES` 序」，序不一致构建即 `RuntimeError`（宁错勿错映射）。覆盖机制留待真正需要时另开。

## 二、交付物总览

| 类别 | 位置 | 说明 |
|------|------|------|
| 15 个族 patch（文本） | `assets/demo-a2/fm/<族>.fmp` | 单一事实源，作者编辑文本，二进制是构建产物 |
| 聚类表（数据源） | `tools/naiz_audio/gm_families.py` | `FAMILIES`：族名 → GM program 列表，含 `build_gm_map()` 校验 |
| gm_map 生成 | `tools/naiz_build/export_asset_table.py` | 生成 `fmp_gm_map[128]` 进 `nb_asset_table.h`（无 FMP 资产时全 0） |
| 引擎接线 | `core/engine/audio.c:466` | `fmseq_init(..., fmp_gm_map, fm_unmapped, NULL)` |
| 守卫测试 | `tools/tests/test_gm_map.py` | 数据契约 + 覆盖性 + 8.3 唯一性 + 引擎上限 |

## 三、族集设计（15 族，序 = family index）

`gm_families.FAMILIES` 顺序即注册顺序即 `fmp_map` 顺序即 `g_fm_patches` 索引。每族一个 `.fmp`：

| idx | 族名 | GM programs | 设计取向 |
|----|------|-------------|---------|
| 0 | `piano` | 0–7 | 双载波对（alg 6）+ 失谐「锤击」调制器，打击感、快速衰减 |
| 1 | `bell` | 8–15 | 高次非谐泛音（mul 2/5/8），极快起音、长泛音（钟/钢片琴/马林巴） |
| 2 | `organ` | 16–23 | 四并联（alg 7）+ 反馈，d1r=d2r=0、sl=15 全程保持音（拉杆风琴） |
| 3 | `guitar` | 24–31 | op4 反馈杂音（alg 0 fb 4），快拨、中速衰减（尼龙/钢弦/电吉他） |
| 4 | `bass` | 32–39 | 双 mul=1 基频载波 + 轻 2 次泛音，重反馈，结实短衰减 |
| 5 | `strings` | 40–46, 48–54 | 暖色并联堆（alg 7），慢起音、近恒定持续（弦乐/竖琴/合唱；47 鼓除外） |
| 6 | `brass` | 56–63 | 明亮并联 + 重反馈（alg 7 fb 5），铜管快起、持续、短收尾 |
| 7 | `reeds` | 64–71 | 奇次谐波（mul 5/9）木管体（单簧管/双簧管/萨克斯），中反馈持续 |
| 8 | `flute` | 72–79 | 单调制器近正弦（alg 2，侧音高 TL 弱调制），柔和起音（笛/排箫/哨） |
| 9 | `synlead` | 80–87 | 明亮并联锯齿感（alg 7 fb 3），快起、持续、短尾 |
| 10 | `synpad` | 88–95 | 失谐双对（alg 6），慢起音涌动、持续、长尾 |
| 11 | `synfx` | 96–103 | 宽非谐（alg 7 fb 7）+ 颤音着色，慢扫频下降（SFX 合成器） |
| 12 | `ethnic` | 104–111 | 失谐弦偏音拨弦（alg 4，西塔琴/班卓/古筝/卡林巴） |
| 13 | `perc` | 47, 55, 112–119 | 打击：最大速率起音、立即落到短持续（定音鼓/管弦hit/旋律鼓） |
| 14 | `sfx` | 120–127 | 金属撕裂/撞击：最紧起音、硬非谐（alg 7 fb 7）瞬时衰减 |

> 47（timpani）、55（orchestra hit）从 strings 段摘出归 perc；24–27 剔出 organ 段归 guitar；104 sitar 归 ethnic。**128 项全覆盖、无重复**由 `build_gm_map()` 强制。

### 3.1 逐族寄存器要点（设计依据）

通用原则（OPNA 寄存器语义见 `F03` §5.2/5.3）：`pan=0xc0`（左路 3/右路 0）为默认；四个方面定族调：
- **谐波骨架**（`mul`/`dt`）决定音色结构的「和声性 vs 打击性」——钢琴/钟/打击用高次倍频或非谐，弦/风琴/口琴用低次谐波；
- **反馈**（`fb`）把并联堆推向「铜管/法兹」的过载边缘（brass 5、sfx 7）；
- **包络形状**：`ar`（起音速率）区分拨弦类（26–31，瞬起）与持续类（14–20，慢起）;`d1r/d2r/sl` 决定「衰减到持续」的快慢与电平（风琴 d1r=d2r=0、sl=15 恒持）；`rr` 决定收尾（钟 8–9 长、打击 4 短）；
- **TL 摊配**：接近合成谐波的调制器处低 TL（响、有效调制），纯音的旁路调制器高 TL（弱调制），避免失真堆叠。

具体每族数值见相应 `.fmp` 文件（头注释即族调性一句话）。

## 四、gm_map 数据管道

```
gm_families.py (FAMILIES 聚类表)
        │
        ▼
export_asset_table.py
  ① SELECT id,name FROM img_map WHERE type='FMP' ORDER BY id   ← fmp_map 同一查询
  ② build_gm_map(order)：序校验 + 128 项全覆盖 + 无重复      ← 序错 RuntimeError
  ③ 生成 nb_asset_table.h: static const uint8_t fmp_gm_map[128]
        │
        ▼
audio.c fmseq_init(..., fmp_gm_map, fm_unmapped, NULL)
        │
        ▼
fmseq fm_family(): fam = gm_map[program % 128]; 越界 → fm_unmapped 报警 + family 0
```

关键约束：**fmp_gm_map 必须由与 fmp_map 同一次的 `fmp_rows` 查询生成**（而非工具聚类表独立枚举），否则族索引与引擎 patch 表错位——这正是 `build_gm_map()` 接收 `order` 参数的用意。无 FMP 资产的项目得到全 0 表（一切回落 family 0，等效旧行为），保持引擎单二进制兼容所有项目。

## 五、验证矩阵

| 项 | 判据 | 手段 | 结果 |
|----|------|------|------|
| V1 | 15 个源文本各自编译 32B 且过 C 校验器 | `test_fm_patch.py::test_project_patch_library_compiles` | ✅ |
| V2 | FAMILIES 序 == ASSETS.DB FMP 行序 == 引擎 patch 表序 | `test_gm_map.py::test_fmp_registered_exactly_the_family_set` | ✅ |
| V3 | 128 GM program 每项都在 [0, 15) 且零空档、零重复 | `test_gm_map.py::test_gm_map_covers_all_programs` + `build_gm_map()` | ✅ |
| V4 | 族数 ≤ `FM_FAMILY_MAX`(16) | `test_family_count_within_engine_limit` | ✅ |
| V5 | 族名 ≤8 字符且 `to_dos_name` 互异 | `test_family_names_are_dos83_unique` | ✅ |
| V6 | 数据名 ↔ 源文件名 ↔ 目录位置一致 | `test_db_filename_matches_fm_dir` | ✅ |
| V7 | gm_map 引擎侧 family 选择与越界回落 | `test_fm_seq.py::test_gm_family_selection`（既有） | ✅ |
| V8 | 端到端构建：15 FMP 进 AUDIO.DAT，fmp_map 无 `__dummy__` | `./makegame.sh build` + 全量 pytest + fullaudit | ✅ |

**试听判据（S7，不做）**：V9 各族在实机/NP2kai 下辨识度、V10 demo-a2 `test1.mid`（program 0 → piano）实际听感、V11 bgm_vol 对 FM 生效等，全归 devdoc 123 §七 S7。

## 六、遗留与后续

- **音质**：15 族默认值合理性已按 §3.1 原则设计，但「好听」必须试听——S7 在 NP2kai/实机逐族过一遍，记入 CHANGELOG 后微调本节 3.1/3.2 数值；
- **覆盖机制**：项目级 gm_map 覆盖（§二边界）需另开，约束「FMP 行序 == FAMILIES 序」届时放宽为按行名匹配；
- **animatest** 无 BGM 资产、无 FMP 行 → 本轮不动（gm_map 全 0，行为不变）。