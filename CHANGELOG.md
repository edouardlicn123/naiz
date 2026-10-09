# Naiz — 开发历史（Bug 修复 / 功能演进）

自 R1 起全部 Bug 修复与功能演进记录（条目顺序沿用 AGENTS.md 既有历史排列）；`AGENTS.md` 仅保留当前版本与规则。**新条目约定**：每轮修复/演进完成后，在下方 `---` 分隔线之后（第一条位置）追加变更摘要，并在 AGENTS.md 头部同步「当前版本」。**条目格式**：每条以 `### <版本号> — <标题>` 开头（版本号化标题行 + `<a id="cN">` 锚点，N 按条目序递增），正文整段或分小节；历史速查直接读下方「版本索引」。

<a id="c57"></a>
### 0.3.026 — 引擎按 8.3 短名解析音频键（str_toc8）：修 AUDIO.DAT 截断名失配 + 全素材面同名风险审计

**动机与验收**：`c56` 换上的正式 BGM 在实机**无声**，串口只看到 `BGM WARN: 'melody_town' missing in AUDIO.DAT`。根因：`pack_audio` 把 AUDIO.DAT 的 TOC 条目名写成 `name` 列的 **8.3 短名大写**（`melody_town → MELODY_T`，契约在 `pack_audio.py` docstring），而引擎三处查表拿**全名**直接调 `farchive_lookup_name()`，`farchive_name_match` 只大写不截断 → `MELODY_TOWN`(11) 对 `MELODY_T`(8) 逐字节失配。此前全部音频键（test1/chime/hi/piano 等）≤8 字符从不触发，`melody_town`/`icy_garden` 是首个踩中者。验收 = 引擎公式 ≡ 打包公式（新 `test_strutil.py`）+ pytest **741 passed / 1 skipped** + 实机复测 BGM 可播。

**1. 引擎新增 `str_toc8`（`core/lib/strutil.{c,h}`）**：脚本音频键 → AUDIO.DAT TOC 名的忠实镜像（大写 → 取最后一个 `.` 前的 base → 截 8 → 紧凑不补空格），与工具侧 `to_dos_name()[0].strip()` 逐字节一致；`core/engine/audio.c` 三处查表（`:137` FM patch 装载、`:225` `audio_bgm_start`、`:314` `pcm_play`）先 `str_toc8` 归一再查 `farchive_lookup_name`；WARN 仍打印原始键、注册校验 `audio_map_find` 保持全名。`nb.c` scene 查表与 image 查表**不动**。audio.c 净 +13 行，`test_devdoc_refs.py` whitelist 的 audio.c 行号重校（209/258/347/356 → 214/267/360/369）。

**2. 全素材面同名风险审计（结论：仅 AUDIO 有此类问题）**
- **IMAGE.DAT**（IMG/SPR/ANI/CG/THUMB）：引擎按 `farchive_lookup_id`（id 索引）取数，名字纯装饰 → 免疫。
- **SCENE.DAT**：按名查，但 TOC 名 = `{base8}.NB` 大写紧凑（`build_game.py`），场景基名 ≤8 强约束（§十一 + `test_dos_shortname`）+ 大写已有 `farchive_name_match` 归一 → 安全。
- **FONT.DAT/CJK.DAT**：单文件固定名直读、无 TOC → 不涉。
- **AUDIO.DAT**（BGM/SND/VC/FMP）：键可 >8，archives 按全名查 → **唯一有此 bug 的面，本轮修复**。

**3. 防复发守卫**：新 `tools/tests/test_strutil.py`（host gcc 编 strutil.c + ctypes），对键矩阵（melody_town/icy_garden/恰 8 字符/9 字符/带点多段/全大写/空串/短缓冲 NUL 终止）断言 `str_toc8` 输出 == `to_dos_name()[0].strip()` —— 钉死「引擎解析公式 ≡ 打包公式」；`test_audio_toolchain.py` 新增 `test_pack_audio_long_name_stored_as_8_3_toc_key`：长名键打包后 TOC 条目必须仍是 8.3 短名（两边永不漂移）。

**4. 文档同步**：AGENTS §二新增「音频三层命名与引擎归一」小节（源文件名 → 脚本键缩写 → DOS 8.3 TOC 名；引擎查 AUDIO.DAT 必须先 `str_toc8`）。`bump_version`：0.3.025 → **0.3.026**（全部项目同步）。

<a id="c56"></a>
### 0.3.025 — demo-a2 换用正式 BGM：场景 001/002 melody_town、003/004 icy_garden（去掉 test1/test2）

**动机与验收**：用户在 `assets/demo-a2/bgm/` 新增两首正式 BGM（`Melody Town Theme.mid`、`Icy Garden.mid`），要求插入场景——001/002 用「melody」、003/004 用「Icy」；同时删除占位的 `test1.mid`/`test2.mid` 与其登记。验收 = pytest 全绿（音频 key 登记守卫、8.3 短名、版本同步）。

**1. 资产侧**：删除 `assets/demo-a2/bgm/test1.mid`、`test2.mid`（git 跟踪删除）；`ASSETS.DB` 删除 `test1` 登记行（`test2` 从未登记无行可删）；幂等登记 `bgm/Melody Town Theme.mid` → `BGM/melody_town`、`bgm/Icy Garden.mid` → `BGM/icy_garden`（8.3 截断 `melody_to`/`icy_gard` 与既有名互异，`pack_audio` 未来构建不拒）。音频登记沿用 `wav_convert.register_asset`/`fm_patch.register_patch` 同源「查无则 INSERT」幂等模式。

**2. 场景侧（4 文件 NB 语法）**：`nbook001.nb:3`、`nbook002.nb:3` `bgm(){test1}` → `bgm(){melody_town}`（001 末尾 `bgm(stop)` 保留）；`nbook003.nb`、`nbook004.nb` 的 `bg(normal){beach1}` 后新增 `bgm(){icy_garden}`（`scene()`/`scene(end)` 自动停音频，无需 stop 行）。

**3. 构建留待用户**：本轮**只改源不构建**（用户自定手工 build）——`AUDIO.DAT` 下次 `./makegame.sh build demo-a2` 时由 `pack_audio` 自动带上两首新曲（登记已入库）。`bump_version`：0.3.024 → **0.3.025**（全部项目同步）。

验证：`tools/tests/test_audio_asset_paths.py`（每登记行可解析 + 场景音频 key 全登记 + 源根不漂移）、`test_dos_shortname.py`、`test_version_sync.py` 全绿。

<a id="c55"></a>
### 0.3.024 — 资产市场 `sync` 子命令：git blob-sha 差分同步（增/改/未变/可选 `--purge` 清孤儿）

**动机与验收**：市场仓库（`edouardlicn123/naiz_assets`）远程更新后，既有 `market.sh` 只是「下载器 + 跳过已存在」，被改过的已存在文件会静默 `SKIP (exists)` 停留在旧版、远程已删文件永不清理，不构成真正的「同步更新」。本轮给 `tools/naiz_market/market.py` 新增 `sync` 子命令，按 Git blob-sha 逐文件差分。验收 = `test_naiz_market.py` **35 passed**（既有 23 + 新增 12）+ 真实远程 `sync --dry-run` 预览 = `6 packs · added 125 · updated 0 · unchanged 42` + 全量 pytest + `fullaudit` 7/7。**本轮只升级脚本不下载**（用户自定手工拉包），`assets_samples/` 零写入。

**1. 差分依据 = tree API 的 blob-sha（零额外下载）**
- GitHub `git/trees` 每个 blob 自带 `sha` = git 对象 id（`sha1(b"blob <len>\0" + 内容)`）；新增 `_git_blob_sha()` 对本地文件算同名哈希即可精确判定「未变/已改」，无需全量重下。已知值 `_git_blob_sha(b"abc") == f2ba8f…` 硬编码断言防实现漂移。
- `packs()`（`(path, size)` 二元组）不动，新增 `packs_detailed()`（`(path, size, blob_sha)` 三元组）——既有调用/测试零破坏。

**2. `sync` 行为**
- 逐文件状态：`ADDED`（本地缺）/ `UPDATED`（size 或 sha 不同）/ `OK (unchanged)`（逐字节相同）。变更文件走既有 `.part` 原子写 + size 校验。
- 可选 `--purge`：清理「本次同步包目录内」已从远程删除的本地文件；**决不触及** dest 根文件（README/LICENSE）与未在同步集合的其它包目录；默认只报 `STALE (removed from remote; use --purge)` 不删。
- 包参数空 = 全部包；`--dry-run` 只预览不写入；LICENSE 随 sync 一并做 sha 差分刷新。`get`/`get-all`/`menu` 的「默认跳过」语义不受影响（AGENTS §13 既有强制规律与测试钉死）。

**3. 测试防复发（全 monkeypatch，不触网）**
- 新增 12 项：`_git_blob_sha` 已知值、`packs_detailed` 带 sha、sync 缺文件 ADDED、同字节跳过、同 size 异内容 UPDATED、异 size UPDATED、dry-run 零写入、未知包拒绝、无 `--purge` 保留 + 提示、`--purge` 删除、**purge 不碰根文件与其他包目录**、默认全包（LICENSE 随写）。

**4. 文档/规约同步**：`market.sh` 用法注释补 `sync`（+`--purge`）；AGENTS §13 市场块新增 sync 语义段落；`docs/B90` 资产市场行补 `sync`。`bump_version`：0.3.023 → **0.3.024**（全部项目同步）。

<a id="c54"></a>
### 0.3.023 — devdocs/124 MIDI→FM 通路 S6：默认音色内容（15 族 FMP patch + GM program→族映射数据 gm_map）

**动机与验收**：`c53` 遗留的 S6（音色内容 + `gm_map` 数据）本轮兑现。验收 = 15 个 `.fmp` 逐一遍过 C 校验器（`test_fm_patch.py`）+ 数据契约测试（新 `test_gm_map.py`）+ 全量 pytest **713 passed / 1 skipped** + `makegame.sh build` 后 `fmp_map` 15 行无 `__dummy__` + `fullaudit` 7/7 全绿。**音质试听明确归 S7**（NP2kai/实机），本轮只交付「结构合理、范围合法、许可干净」的默认值起点。

**1. 15 族默认 patch（`assets/demo-a2/fm/*.fmp`，文本单一事实源，族索引 = 注册序）**
- 按 GM 聚类覆盖 128 个 program、零空档：`piano`(0–7) `bell`(8–15) `organ`(16–23) `guitar`(24–31) `bass`(32–39) `strings`(40–46+48–54) `brass`(56–63) `reeds`(64–71) `flute`(72–79) `synlead`(80–87) `synpad`(88–95) `synfx`(96–103) `ethnic`(104–111) `perc`(47+55+112–119) `sfx`(120–127)。
- 每族设计依据（devdoc 124 §三）：谐波骨架（和声性 vs 打击性的 mul/dt）、反馈（并联堆过载边缘）、包络形状（ar 区分拨弦瞬起/持续慢起、d1r/d2r/sl 定衰减与恒持、rr 定收尾）、TL 摊配（近合成谐波低 TL 有效调制、纯音旁路高 TL 防失真）。
- 15 ≤ `FM_FAMILY_MAX`(16)；名字 ≤8 字符且 `to_dos_name` 互异。

**2. gm_map 数据（128 项 GM→族索引，与代码分离）**
- 新 `tools/naiz_audio/gm_families.py`：`FAMILIES` 聚类表（族名 → GM program 列表）+ `build_gm_map(order)`——**序必须恰为 FAMILIES 序**、128 项全覆盖、无重复，任一违例 `ValueError`（宁错勿错映射，禁止静默回落 patch 0）。
- `export_asset_table.py`：由与 `fmp_map` **同一次** `SELECT ... type='FMP' ORDER BY id` 生成 `fmp_gm_map[128]` 进 `nb_asset_table.h`（无 FMP 资产的项目全 0，等价旧行为）。
- 接线一行：`audio.c:466` `fmseq_init(..., fmp_gm_map, fm_unmapped, NULL)`——历史终态「`gm_map=NULL` 全映射 family 0」告终。

**3. 测试与防复发**
- `test_fm_patch.py` 增 `test_project_patch_library_compiles`（全部 15 源编译 32B + C 校验器）。
- 新 `test_gm_map.py`：FMP 行序 == FAMILIES 序、128 覆盖、族数 ≤ 引擎 `FM_FAMILY_MAX`（读 audio.c 宏）、8.3 唯一、DB filename ↔ fm 目录一致、`build_gm_map` 序错/空档/重复三路拒绝。
- 引擎侧 family 选择/越界回落沿用 `test_fm_seq.py::test_gm_family_selection`（c53 已证）。

**遗留（S7 实机/NP2kai）**：VOL1/VOL2 step 曲线、§1.5 五条判据、`FM TRACE` 宏开启的寄存器序列、15 族逐族音质试听与微调。`bump_version`：0.3.022 → **0.3.023**（全部项目同步）。

<a id="c53"></a>
### 0.3.022 — devdocs/123 MIDI→FM 通路 S0–S5 代码落地（fmopn/fmseq 主机可穷举 + hal_fm_* 端口层 + 音频引擎 FM 后端）

**动机与验收**：`c52` 拍板的 FM 通路（输入 = MIDI、后端 = 自动检测、v1 = FM 6 + SSG 3）进入实施。验收 = 每阶段主机测试（`pytest` 704 passed / 1 skipped）+ 引擎编译零 `.err` + `fullaudit` 7/7 全绿；其余判据（§1.5 五条、VOL step 曲线）属 S7 实机验证，接续。

**1. 最大风险削减点兑现：M1 `fmopn` + M2 `fmseq` 落 `core/lib/`，零 `outb()` 主机可穷举**
- `core/lib/fmopn.{h,c}`（12 单测 `test_fmopn.py`）：YM2608 FM 寄存器抽象纯逻辑层——F-number 编码（`freq×18432/975`，A4=4/520、C4=3/618、钳位 1023/7）、bend 相对当前 blk/fnum、算子内插（`base+3*(r&1)+8*(r>>1)+ch%3`）、keyon/安全 keyoff 值、32 字节 patch 解码与校验（错误位 `FMOPN_E_*`）、SSG 周期编码器。
- `core/lib/fmseq.{h,c}`（14 单测 `test_fm_seq.py`）：MIDI 事件→FM 声音分配器——16 声部（元数据）/6 FM + 3 SSG（`FMSEQ_MELODY_FM_CH=6`）；`Fmseq` 生命周期 `size/init/deinit` 暴露对齐；单声道→单 FM 声部双声道分配、SSG 固定声部、鼓（kick/hat/snare → SSG ch A/C/B）+ 音高 + bend + patch 装载 + pedal 语义（sustain_pending/breathe）；**抢声 free→pedal-pending→oldest（强制抢声先 keyoff，无残留 key 位）**；SSG 衰减 `FMSEQ_SSG_DECAY_PER_SEC`；`gm_family_selection`（family mask + clamp，128% family0 回落）。新增 `fmseq_finished()`（`cursor>=count`）作引擎 loop 点。
- **新教训（ctypes 段错误根因）**：`gm_family_selection` 崩溃 = `_UNMAPPED_FN(self._on_unmapped)` 内联创建未存 `self` → 被 GC → C 指针悬垂段错误。修复：`Seq.__init__` 存 `self._unmapped_cb`（`self._cb` 同型已有）。ad-hoc 脚本不设 `argtypes` 会 32 位截断指针同样崩溃，以 pytest 为准。

**2. M3 `hal_fm_*` 端口层（S2，`core/plat/hal_audio.c`）——引擎链路上 `outb()` 唯一出处**
- 端口宏：`FM_ADDR_LATCH 0x0188` / `FM_DATA_PORT 0x018A`（普通组：SSG/RHYTHM/系统/FM ch1–3）、`FM_EXT_ADDR_LATCH 0x018C` / `FM_EXT_DATA_PORT 0x018E`（扩展组：FM ch4–6/ADPCM）。
- `hal_fm_detect()`：能力 ID 回读（0xFF → 读回 1）探测 OPNA，不猜端口。`hal_fm_init()`：A460 bit0=1（2023 年起实机多为常开，写保险）+ VOL1/VOL2 初始满音量。`hal_fm_write_reg(bank,addr,val)`：bank0→0x188/0x18A、bank1→0x18C/0x18E。`hal_fm_shutdown()`：6 声道全 KEYOFF（`$28` 带 bit2 选 k3 组）+ SSG reg7 `0x3F` 全静音。`hal_fm_set_volume(atten)`：A466 写 `000b|atten`（VOL1 = FM 直接路径）。
- **A466 关键订正**：各路音量通路**各持独立 4-bit 衰减寄存器**（MAME 解码 `line_select=data>>5; m_vol[line_select]=data&0x0f`）——VOL1(000b)/VOL2(001b)/PCM(101b, `0xA0`) **互不覆盖**，「两条路径共用 A466 需统一收口」的担心不成立（devdoc 123 §2.4 旧结论推翻）。
- trace 改为**编译期 `FM_TRACE_ENABLED` 宏**（`hal_fm_set_trace` 运行时 API 删除，判据 5 排障重编译开启，避免 60Hz 刷屏）。

**3. M4 音频引擎接线（S5，`core/engine/audio.c`）**
- **后端自动检测**：`audio_init` 先 MPU-401 后 OPNA（`hal_fm_detect`）；MPU 在位走 MIDI 后端，无 MPU 且 FM 在位走 FM 后端（`g_bgm.fm=1`），都缺 → `AUD WARN` fail-loud + BGM 忽略。
- FM 泵走 `hal_wallclock_smooth_ms()`（devdoc 107 节拍安全，杜绝裸墙钟追帧音爆）；loop 经 `fmseq_finished()` 回绕（`wall0=now; fmseq_stop`）并报告残响（`fmseq_fm_voices` 行 `FM loop: N voices still ringing`）。
- patch 装载 `fm_load_patches()`：逐行 `fmp_map`（`core/engine/nb_asset_table.h`，`./makegame.sh build` 生成）→ `farchive_lookup_name` → size==`FMOPN_PATCH_BYTES`(32) → `fmopn_patch_validate`；跳过 `__dummy__`；全失败/无 FMP → 兜底 `g_fm_default_patch`（4 op MUL=1/TL=0/AR=31/RR=15、反馈/算法 0x01、pan 0xC0）。
- 音量：`bgm_apply_volume` FM 分支 `atten=(g_bgm_vol*15)/AUDIO_BGM_VOL_MAX; hal_fm_set_volume(15-atten)`（衰减倒序 0 最响；S7 实测 step 曲线）。
- `audio_stop_all` 增 `hal_fm_shutdown()`（消除死导出）；`BgmState` 增 `fm` 标志。
- fmseq 的 SSG 周期写区改用 `fmopn_ssg_period_fine/coarse` 编码器（单一事实源）→ 消 A 节候选。

**4. 文档/防复发同步**
- devdoc 123（允许修订的计划中）：状态「计划中」→「实现在完成中」，头部追加 `📌 实现记录` 表（M1/M2/S2/S3/S4/S5 逐项落地位置+测试数）、§2.4 写「A466 各路独立衰减已消解 + PCM 路径 `100b`→`101b` 订正」、§四「待建」注记改为「规格即现状」。
- `test_devdoc_refs.py`：whitelist 更新为现行行（audio.c:`209 g_bgm_on` / `258 audio_bgm_stop` / `347 g_snd_on` / `356 g_vc_on`）；新增 `SUPERSEDED_AUDIO_LINE_REFS` = {audio.c 105/147/233/242}（devdoc 119 正文不可改的历史行引用，并入 registered 不再红）。
- W138：`fmopn.h/fmseq.h/fmopn.c` 补文件尾换行。
- 上 `./makegame.sh build` 重建 `nb_config.h`（NAIZ_VERSION=0.3.022）/`nb_asset_table.h`（`fmp_map={"__dummy__",0}`），test_version_sync 依赖此步。

**遗留**：S6（FMP 音色内容 + `gm_map` 数据——现回落 family 0，纯内容轮）；S7（实机/NP2kai：VOL1/VOL2 step 曲线、§1.5 五条判据、`FM TRACE` 宏开启的寄存器序列验证）。`bump_version`：0.3.021 → **0.3.022**（全部项目同步）。

<a id="c52"></a>
### 0.3.021 — guildbook 新增 mc06「音频素材与 FM 通路」（格式 / AI 平台 / 软件工具集 + 引擎方案对比）

- **动机**：`c51` 末条留的「FM 作曲方法（格式选型 / tracker 资产入管线）明确留作下一步研究」，用户决定**暂不实现 FM 后端**、但要先把选型信息沉淀成文档。产物是一篇面向制作者的参考页，不含任何引擎改动。
- **新页面** `naiz-guildbook/pages/mc06-音频素材与FM通路.html`（归「基本概念」→ 机制段，续 `mc05` 前缀）。复用既有模板：`../style.css` + `../sidebar-reference.js` + `<blockquote>` 元信息（与既有 43 页一致）；**未改 `style.css`**（`mc` 段沿用 `b-tool` badge）。
  - §1 三条通路的硬件事实：MPU-401 扩展卡 / YM2608（FM 6 + SSG 3）/ 86 板 YM3433B PCM **单通道 FIFO**；两条关键推论——FM 与 PCM **硬件分离**故 BGM 走 FM 可与语音同时发声、PCM 侧 SE 与 voice 不可重叠；端口不重叠（`A4xx` vs `0188h`/DIP `0288h`）。补 YM2608 内部四模块（含常被忽略的**单通道 4-bit ADPCM 2–55 kHz**）。
  - §2 格式对照：开头 `.note-box` **纠正「FM 不是格式，是合成方法」**；MIDI / MML / S98 / VGM / WOPN / `.pcm` / ADPCM(PC8·P86·PPC) / `2608_*.WAV` 八种，标注本质·产出者·引擎侧代价。明确**能当作曲产物的是 MIDI/MML/VGM，WOPN 只是音色素材**。
  - §3 AI 平台分两栏：**可用**（能出 MIDI/符号）AIVA、NotaGen、MIDI-LLM、Magenta realtime 2；**不适用**（只出音频）Suno / Udio / MusicGen / ACE-Step / YuE / Stable Audio / DiffRhythm。`.note-box` 给出原因——WAV→FM 是**欠定的逆问题**，业界方向是反向的（按 FM 作曲再导出），DDSP 属正向可微合成、非反推。**三个子节**（见下「AI 平台成本与门槛核实」）。
  - §4 软件工具表：全部**逐条核对许可证**（见下）；§4.1 两个 `.note-box` 陷阱项（FamiTracker / FamiStudio）。
  - §5 工作流两条链路图（AI→MIDI→tracker/libOPNMIDI→OPNplug 试听→引擎；旁支 WAV→`wav_convert.py`→`.pcm`）。**MIDI 作交换格式、FM 只做渲染**是所有 AI 工具可用的唯一前提。
  - §6 引擎侧方案对比 A（MIDI→YM2608 映射，中工作量/高保真/生态全可用，**推荐**）/ B（VGM 寄存器流，保真最高，可作调试对照）/ C（MML·S98 播放器，工作量最大、生态最窄）/ D（离线渲 WAV 走 PCM，小工作量但**通道冲突不可行**）。
  - §7 许可须知 + §8 陷阱清单（6 复音上限、Rhythm 依赖 `2608_*.WAV` 故鼓组建议 FM+SSG、**GM 音色≠FM 音色**、WAV→FM 不可行、PCM 单通道、恒定音量素材使音量测试失效、**AI 产出不可直接当 BGM**、**选工具别只比价格（Udio ToS 禁下载）**、**磁盘先于显存成瓶颈**、FamiTracker 混淆）。交叉链接既有 `sc10-audio.html` 与 `cf07-图片登记.html`。
- **AI 平台成本与门槛核实（本轮第二轮补入 §3.1–§3.3，纠正上一轮的三处不准确表述）**：
  - **AIVA 不是「纯商业 SaaS」——它有永久免费档**（官方定价页原文 `Free, Forever €0` / `No credit card required`）。三档实测条款：**Free €0** = 3 次下载/月 + ≤3 分钟 + MP3&**MIDI** + 仅非商用 + **需署名 AIVA** + 版权归 AIVA；**Standard €11/月（年付 +VAT）** = 15 次/月 + ≤5 分钟 + 无需署名 + 版权归 AIVA；**Pro €33/月（年付 +VAT）** = 300 次/月 + ≤5 分 30 秒 + **全部格式含 WAV** + **版权归用户可商用**。另有学生/学校折扣（月付 15% / 年付 30%，需表单申请）。**订正上一轮「最成熟的商用选择」的说法**：3 次/月、且**含 MIDI**，对「几首 BGM 草稿」够用，故**先算账再订阅**（3→15 次要 €11/月起，完整版权 €33/月起）。
  - **「更便宜的平台」反而更没用**：Suno 官方页确认 Free = $0 + 50 credits/日（≈10 首）+ 仅 v4.5-all + **无商用权**，但**不提供 MIDI 输出**；Udio 官方页确认 Free = $0 + 10 credits/日 + 100/月 + 完整长度每日限 3 首，而 **Udio 自 2025-10-29（与 Universal 和解同日）起在 ToS 层面禁止下载任何输出**（「You may not download copies of any Output」），**付费档同样不能下载**——即「能生成」与「能带走」是两件事。故**「能否导出 MIDI」才是筛子**，比价格重要得多。
  - **两个开源模型的实际门槛（本机 4 GiB GTX 1650 两者都跑不动，不是「慢」而是显存溢出）**：MIDI-LLM（ISMIR '26，基于 Llama 3.2 1B）官方要求 **16 GB+ VRAM** + CUDA 12.x + Python 3.11（conda）+ `vllm`/`anticipation`/FluidR3 GM，**需 AVX512 才有较好 CPU 性能**；NotaGen 要求 **NotaGen-X 8 GB / large 24 GB** + `torch==2.3.0`/cuda 11.8 + Python 3.10。且 **NotaGen 产出 ABC 记谱而非 MIDI**，与 FM BGM 通路不同路；MIDI-LLM 示例提示词要求 electric guitar / church organ / saxophone 等通用配器，落到 YM2608 的 6 复音 + 128 个 4 算子 patch 上即 §8 陷阱 3 的「机器人音」。落地建议：**磁盘（需 10–20 GB）往往比显存更早成为瓶颈**；真要跑就走 Colab 等**按小时租 16 GB 卡**，本地只留 tracker 那一步。
  - **两条待核实线索（如实标注，不当已验证选项）**：Suno Studio（仅 Premier）被称含 MIDI 导出，但**官方定价页只写「Suno Studio」，未列 MIDI**；Veena / Mureka 被第三方竞品营销页称可导出 MIDI（Veena 免费档含、Mureka 标 $30/月 Premier 专属）——**可信度需自行核对官方条款**，页面上已写明「不要采信对比文章，包括这两个说法的来源」。
  - **顺带在 §5 补一条定位**：AI 的正确位置是「**旋律草稿**」而非成品——GM MIDI 必须在 tracker 里换 FM 音色、改织体、**删声部以适配 6 复音**；全程不用 AI 直接在 tracker 里作曲零成本零依赖、质量反而更高，**AI 不是必需品**。§8 同步补 3 条陷阱（AI 产出不可直接当 BGM / 别只比价格 / 磁盘先于显存成瓶颈）。
- **第三轮订正（用户实测推翻「AIVA 免费档拿不到 MIDI」+ 补入第四类工具 AMT）**：前两轮把 AIVA 的 MIDI 一律当作「官方定价页声称、待核实」。**用户在真实账户上实测后给出了两条决定性事实**，据此再订正：
  - **① MIDI 只在「旧版」界面给，新版看不到。** 实测：新版界面下载入口**只给 MP3**；**旧版（classic Songs）界面单曲点 Download 即出现 MIDI**。故「定价页与新版界面所见不符」**不是定价页写错，而是新旧界面并存、MIDI 留在旧版那条线上**。§3.1 免费档行的 MIDI 已从「官方声称」升为**实测可得**。这条同时订正了本轮中途的一个**错误推断**：我曾据 AIVA 用户手册「单曲点 Download 只下默认格式、需走文件夹才能选类型」推断「走文件夹就能拿到格式选择」，**实测证明该推断错误**（旧版单曲直接就有 MIDI）——**该错误只在对话中，未污染 `mc06` 正文**，已按 §九.6 如实记录。
  - **② 旧版入口已确认无法复现。** 用户当时能进入旧版，但**事后想不起进入路径**，故 §3.1 明确写「本页不给出操作步骤（给了也是误导）」，并提示换账号 / 清缓存 / 换浏览器均不保证找回。同时标注**旧版属 legacy 界面、有下架风险**，建议先把手头的 MIDI 存档、并可向官方询问生命周期。
  - **③ 「只出音频的平台」并非完全无用——原理层的措辞过宽，已收窄。** 原 §3 note-box 与 §8 陷阱 4 只说「WAV → FM 是欠定逆问题」，容易被读成「音频一律没救」。现改为**区分两件不同的事**：**WAV → FM 参数（音色/patch）** 是欠定逆问题、**无解**（FM 参数化模型 vs 任意波形，同一波形对应无穷多组参数）；**WAV → 音符（音高/时值/轨道）** 是**适定**问题、音高检测成熟、**可行**。两者不可混谈——**音符是「乐谱」，音色是「乐器」，后者才是那个无解的逆问题**。
  - **④ 新增 §3.4「第四类工具：音频 → MIDI 转写（AMT）」**。前三类是「生成」，AMT 是「转写」（把**已有音频**还原成音符），定位不同：它**不省「想旋律」的工夫，只省「把旋律敲进 tracker」的工夫**（§5 note-box 已同步补这句）。工具 **basic-pitch**（Spotify 音频智能实验室，ICASSP 2022）**Apache-2.0 或 GPL-3.0 双许可**（取 Apache-2.0）、`pip install basic-pitch`、CLI `basic-pitch <输出目录> <输入音频>`、支持复音与 pitch bend。**最有价值的工程细节：默认不装 TensorFlow**——官方 README 明确按平台选推理后端（**Linux 装 TensorFlowLite** / Windows ONNX / macOS CoreML，需完整 TF 用 `basic-pitch[tf]`），依赖体积远小于直觉，对本仓磁盘紧张环境友好；另有**浏览器内运行的免费在线 demo**（`basicpitch.spotify.com`），**无需安装、无需本地磁盘**，正好绕开本机仅约 740 MB 空闲的限制。**⚠️ 限制**：官方明确「一次只处理一件乐器效果最好」，故**整首管弦乐混音转写会很乱**，而**哼单音旋律非常干净**（demo 页自己就写着「对着麦克风哼一段小调」），写 BGM 旋律草稿走后者。**兜底价值**：AIVA 旧版一旦下架，此路仍通，因为它不依赖任何账号或订阅。
  - **⑤ 候选平台核实结论**：**Amper Music 已死**——被 Shutterstock 于 **2020-11-11** 收购、独立服务随后关停，但 2026 年仍有大量「最佳 AI 作曲工具」榜单在推荐它，故 §8 新增陷阱「榜单会推荐已经关停的服务」，并把这归为 §3.2「能生成 ≠ 能带走」的**第三种形态：连站都不在了**。**basic-pitch 是本轮唯一逐条核实到许可 / 安装方式 / 后端选择 / 限制条款的可用方案**；Suno Studio（第三方称有 piano roll/MIDI，但官方定价页只写「Suno Studio」未列导出）、Veena / Mureka（仅竞品营销页称支持 MIDI）**三条线索维持「待核实」标注不变**。
  - **⑥ §8 新增「官方文档也会过时，且实测优先于官方文档」**：AIVA 格式说明文章最后更新于 **2021-02-18**、**从不映射「格式 → 档位」**；其用户手册的下载路径描述与实测不符。凡涉导出格式与档位权限**以实测为准**。原陷阱「WAV → FM 不可行」同步收窄为「WAV → **FM 音色**不可行，但 WAV → **音符**可行」，避免连坐否定转写路线。
- **第四轮（AIVA 退出方案 + Mureka 纳入 + Magenta RealTime 2 错标修正）**：用户实测后判定 **AIVA「几乎不可用」，要求删除该方案**。`mc06` 中 AIVA 已**一个字不剩**（表格行、§3.1 整节含三档定价表与旧版界面坑、§3.2 两处引用、§3.4 两处兜底措辞、§8 以其为例的那条陷阱）。**本 CHANGELOG 内前三轮的 AIVA 记录按用户指示保留**（「不删除，那是历史」）——那些记录的是**已评估 → 已否决**的过程与其中的错误推断，属 §十 要求的订正留痕，不是仍生效的结论；此处另加本轮说明其去向，避免后人照旧的 AIVA 章节排查。
  - **AIVA 为何出局（定性，供后人不再回头）**：免费档的 MIDI **只挂在旧版界面**，新版只见 MP3；且**旧版入口实测已无法复现**（进得去、找不回路径），旧版又属 legacy、**有被下架的风险**。即「理论上免费可得、实操上不可依赖」，不具备可依赖性，故从方案中移除而非降级为备选。
  - **Mureka 由「待核实线索」升为 §3.1 正式章节（官方页面逐字核实）**：**路 A 网页端 Premier**——官方订阅页原文「通过对 Mureka Studio 和 **MIDI/WAV 导出的独家访问权限**，Premier 提供了专业音乐工作流所需的终极控制力」，据此确认**免费档无 MIDI、Pro 无 MIDI、Premier 才有**；**Premier 价格本页查不到**（官方页面价格数字由 JS 动态渲染，抓取结果只有能力表），坊间 $27/月等数字**未获官方证实，已如实标注不写入**。**路 B API 按量**——官方 `platform.mureka.ai` 的 **Export Stem Audio**：V1 `wav` $0.06/首（5 轨）、**V3 `wav, midi` $0.2/首（vocal + instrumental）**、**V2 `wav, midi` $0.7/首（12 轨）**，**无需订阅**；官方 FAQ 另确认**下载歌曲本身免费、仅分轨功能另付费**。API 四个代价亦按官方原文写明：**与网站会员两套独立计费不互通**、**credits 自最近充值起 12 个月有效且到期作废**、**一律不退款**、需预充值。
  - **一条关键认知（新增，写进 §3.1 与 §3.4）**：**Mureka 的 MIDI 本质是「先分轨、再转写」，不是符号生成**，故其质量上限与 AMT 同一个天花板；但**组合在原理上自洽**——basic-pitch 官方硬限制是「一次只处理一件乐器效果最好」，而 V2/V3 **恰恰把 instrumental 单独拆出**，正好化解整首混音转写最大的痛点。故 §3.4 的核心论点由「basic-pitch 一个工具」上升为「**分轨 → 单轨转写**的顺序」，并在 §5 补第三张链路图与**三条路按成本排序**（③ 哼唱零成本 → ② $0.2/首 → ① Premier 月费或需 Ableton 的 Magenta Studio），结论是**先走路③，别一上来就订阅**。
  - **独立修正：Magenta RealTime 2 被错列为「能出 MIDI」**（与 AIVA 无关的新错误，按 §十 就地订正）。HuggingFace 模型卡 `google/magenta-realtime-2` 的 `pipeline_tag` 是 **`text-to-audio`**，MIDI 是它的**输入**条件（每帧 128 维 multihot 向量，表 MIDI 状态）而非输出；权重约 **15.6 GB**。**已从「可用」表移入「只出音频」清单并标注常被误列**；同时补入真正本地产出 MIDI 的**另一个项目** `magenta/magenta-studio`（Apache-2.0，5 个模型 Continue / Generate / Groove / Drumify / Interpolate 作用于**已有 MIDI clip**，需 **Ableton Live 10.1+** 或其 standalone 版）。
  - **§8 陷阱重写**：原「榜单会推荐已关停的服务」与原「官方文档也会过时（以 AIVA 为例）」两条，按用户「彻底删干净」的指示合并为**一条通用陷阱「榜单与搜索摘要不可信，只认官方主域名」**——涵盖两种病源：① **Amper Music** 已被 Shutterstock 于 2020-11-11 收购、独立服务关停，2026 年仍被大量榜单推荐；② **山寨站编造互斥价格与型号**（本次核实 Mureka 时一次命中多个克隆站，给出 $6.4 / $15.96 / $19 / $26.9 / $49 等互斥数字并虚构「V9 / V10」型号）。仅 `mureka.ai` 与 `platform.mureka.ai` 为官方域名。
- **许可证逐条核实（两处纠正了我此前的错误认知）**：
  - **BambooTracker 是 GPL-2.0-or-later，不是 MIT**——GitHub API `spdx_id=GPL-2.0` 且其 README 明确「YM2608(OPNA) 向け」；仓库已迁至 `BambooTracker/BambooTracker`（旧 `OatmealBagel/` 路径 404）。定位为本项目 PC-98 作曲**首选**。
  - **FamiTracker 精确事实**（官方站点与更新日志逐字核对）：`http://www.famitracker.com/`，最后一版 **0.4.6 / 2015-02-04**，GPL，仅 NES/Famicom、Windows 独占。关键区分——官方仍列「MIDI input devices are supported」指的是 **MIDI 键盘实时输入**，**不是导入 `.mid`**；**MIDI import 已在 0.4.3（2014-06-07）移除**（更新日志原文「Removed MIDI import」），且**无任何 MIDI 导出**。故 FamiTracker 走「AI MIDI → FM」两头都缺。
  - **FamiStudio 不支持 YM2612**（仅 NES 侧 2A03/VRC6·VRC7/FDS/N163/MMC5/5E01）——常见误解，已单列陷阱框。
  - 其余核实结果：Furnace `tildearrow/furnace` = GPL-2.0/GPL-3.0 双许可（支持 YM2608 + RtMidi MIDI 输入 + VGM 导出）；libOPNMIDI `Wohlstand/libOPNMIDI` = LGPL-3.0；bambooCopy = MIT（2019 后停更）；mdxtools `vampirefrog/mdxtools` = GPL-3.0；pc98sndpmdtools = **非标准声明（`NOASSERTION`）需读 LICENSE**，故页面如实标注而非猜测；NotaGen `ElectricAlexis/NotaGen` = MIT；MIDI-LLM `slSeanWU/MIDI-LLM` = 非标准声明，如实标注。
  - **§7 强调 GPL 传染性只作用于代码、不作用于输出数据**（用 GPL tracker 做的曲子可进任何引擎），但**移植其代码是另一回事**——libOPNMIDI 主体 LGPL-3.0 却内嵌许可证不兼容的第三方核心（MAME YM2612/OPN、Genesis Plus GX），须逐文件核对 SPDX 而非只看顶层 LICENSE。对齐 §十。
- **接线（B91 §1 约定）**：`sidebar-reference.js` 机制段新增一条 `nav-item`；`manual.html` 机制段新增一张 `.index-card` 且 `page-intro` 补「音频素材」；按约定 `touch naiz-guildbook/*.html naiz-guildbook/pages/*.html`（49 个 HTML）。**`index.html` 无需改动**（只列 4 张分类卡，不列具体页）。
- **人工核验**：新页 3 个相对引用（`../style.css`、`sc10-audio.html`、`cf07-图片登记.html`，另有模板注入的 `../sidebar-reference.js`）全部可解析；15 类标签开闭全部配平 —— **第四轮（AIVA 移除 + Mureka 纳入）后的最终**计数：`table 11/11`、`tr 52/52`、`td 149/149`、`th 40/40`、`ul 6/6`、`li 25/25`、`pre 2/2`、`code 50/50`、`div 10/10`、`p 43/43`、`a 22/22`、`h2 8/8`、`h3 5/5`、`h4 2/2`（共 229 行）。全部 9 个 `§` 交叉引用（`§1 §3.1 §3.2 §3.3 §3.4 §4.1 §5 §7 §8`）均指向实存章节，无悬空引用；`<h4>` 两级子节（路 A / 路 B）位于 §3.1 之下，编号与目录层级一致。**全文 `grep -c AIVA` = 0**（AIVA 已彻底移除）。
- **未做（用户明确暂缓）**：FM 后端实现、OPNA 端口基址探针、devdoc 123。**§8 陷阱 6「恒定音量素材」对应的实测事实（`hi.pcm` 是 `chime.pcm` 前 5512 字节的逐字节副本、三个 PCM 动态范围仅约 0.3 dB）本轮按用户先前选择未写入文档**。
- **本轮补入的三处订正均为「我自己上一轮说错的」**，按 §十 结论推翻四步法的第 4 步就地订正：①「AIVA 是商业 SaaS」→ 有永久免费档，且免费档就含 MIDI；②「Suno/Udio 更便宜」→ 需补上 Udio 在 ToS 层面禁下载这一**定性事实**，否则「便宜」会被误读成可行选项；③「两个开源模型可选」→ 补显存/磁盘/依赖的真实门槛，并明示本机两者都跑不动。**第 2、3 条属新增事实而非推翻结论**，但同样按「宁可标注待核实、不可当已验证」处理（Veena / Mureka / Suno Studio 三条线索全部标注为需自行核对）。

验证：`make -C core` + `find core -maxdepth 1 -name '*.err' -size +0`（空）、`pytest tools/tests/` **642 passed, 1 skipped**、`./start.sh fullaudit` **7/7 全绿**（最终日志 `logs/fullaudit_20261005_002059.log`）、`./makegame.sh build demo-a2 && make -C core && ./makegame.sh make demo-a2`（HDI 重新注入）、`strings games/demo-a2/engine.exe | grep 0.3.021` 确认版本宏已编入。**过程实测到 §八 五禁之二的同型陷阱并被守卫拦下**：`bump_version` 后首跑 fullaudit 时 `test_version_sync::test_generated_nb_config_matches_project_version` 报 `nb_config.h says 0.3.020 but every project says 0.3.021`，按其提示先 `build` 重生成 `core/engine/nb_config.h` 再 `make -C core` 即恢复——证明该守卫有效。版本统一 bump 至 `0.3.021`（animatest / demo-a2 同步），**零引擎逻辑改动**。**第二轮补文档未再 bump 版本**：改动仅 `naiz-guildbook/pages/mc06-*.html` 与本 CHANGELOG，均非 §十六 列举的源代码文件（`.c`/`.h`/`.py`/`.nb`），且属同一未提交的 `c52` 轮次，故就地收敛 `c52` 正文而非另开 `c53`（避免两条条目共用一个版本号）。**第三轮（AIVA MIDI 实测 + §3.4 AMT）沿用同一处置**——同样只动 HTML + CHANGELOG + AGENTS.md，**不 bump 版本**，仍为 `0.3.021`。补文档期间为核实平台条款抓取了 AIVA / Suno / Udio 三个**官方定价页**，未安装任何软件、未改系统环境。**第三轮补充**：核实 basic-pitch 时抓取了 `spotify/basic-pitch` 的 README / PyPI / HuggingFace 与在线 demo 页，**未在本机 `pip install`**；FM 后端仍按用户先前决定**暂不实现**。**第四轮验证**：`pytest tools/tests/` **642 passed, 1 skipped**、`./start.sh fullaudit` **7/7 全绿**、文档侧 15 类标签配平 + 3 个相对引用可解析 + 10 个 `§` 引用无悬空 + 全文无 AIVA 残留。**本轮零引擎改动**。
- **第五轮（页面精简 + 去重）**：用户要求「重新整理这个页面，优化描述，删除不必要的内容」。核查发现前几轮叠加后**同一论点被重复陈述最多三次**，逐处收敛：
  ① **§3.4 三个 note-box 合并为两个** —— 原「TF 依赖 / 单乐器限制」「先分轨再转写」「WAV→FM vs WAV→音符」三框中，「一次只处理一件乐器」与「哼单音旋律」各被说了两遍；把「先分轨再转写」提为该节唯一核心论点（顺序公式改为独立一行），TF 依赖等工程细节并入表格的「关键工程事实」列，不再单列。
  ② **§3.1 与 §3.4 的重复论证删除** —— §3.1 原「关键认知」框与 §3.4 的分轨论证是同一段话，§3.1 压缩为一句并交叉引用 §3.4；「API 的四个代价」四条 `<li>` 收成一句三点（去重后只剩三代价：独立计费、12 个月作废、不退款）。
  ③ **§3.2 与 §8 的重复删除** —— 山寨站整段（§3.2）已由 §8 统一承载，§3.2 只留一句指向；Udio 的 ToS 事实与「能生成 ≠ 能带走」在两处各说一遍，§8 降为纯交叉引用。
  ④ **§1 表格与正文重复** —— 「YM2608 内部四模块」原在表格与紧随的段落里各写一遍，删段落、把四模块并入表格行；端口枚举（`A460`/`A466`/`A468`/`A46A`/`A46C`）对本页读者不可操作，压成一句「两组端口不重叠」。
  ⑤ **§5 note-box 删一段** —— 「转写（AMT）的定位」与 §3.4 开头重复，只保留其中独有的洞察（转写省的是敲音符的工夫，不是想旋律的工夫）。
  ⑥ **§5 流程图重绘** —— 原图竖线全部悬空（未接任何节点，且中文双宽导致列位算错）。改为「三入口汇入同一 MIDI 闸门」的树形，列位按 `east_asian_width` 实际显示宽度计算对齐；条目文案由「路①/②/③」改为「入口①/②/③」，避免与 §3.1 的「路 A / 路 B」撞名。
  ⑦ **§3.4 标题去歧义** —— 「第四类工具」易与 §3 表格中的 4 个平台混淆，改为「转写路线：音频 → MIDI（AMT）」。
  ⑧ **脆弱的「§8 陷阱 3」编号引用改为按名引用** —— 陷阱清单一旦增删条目，编号即失效，改为「见 §8「GM 音色 ≠ FM 音色」」。
  另修一处嵌套 `<strong>`（`<strong>…<strong>…</strong>…</strong>`）为单层。
  **净结果 253 → 229 行**；去重探针确认「一次只处理一件乐器」「欠定的逆问题」「12 个月」「不退款」等原先 2–3 次的表述现各出现 1 次。
  **第五轮验证**：`pytest tools/tests/` **642 passed, 1 skipped**、`./start.sh fullaudit` **7/7 全绿**、23 类标签开闭配平 + 4 个相对引用可解析 + 9 个 `§` 引用无悬空 + 无残留「陷阱 N」编号 + 全文无 AIVA 残留。**本轮零引擎改动、不 bump 版本**（仍为 `0.3.021`，与 `c52` 同轮次）。
- **第六轮（按用途拆分为两页）**：用户要求「拆分为两个文档，一个是机制解释，一个是可用的平台和工具」。原 229 行的 `mc06` 混装两类读者，按**用途**而非按「话题相邻」拆分：

| 新页 | 定位 | 收容章节 |
|---|---|---|
| `pages/mc06-音频通路机制.html` | **机制解释** —— 硬件事实、格式定义、原理边界、引擎侧取舍 | 原 §1 硬件三通路 / §2 格式对照（**整表留此**）/ §6 引擎侧方案对比 / §8 的机制类 7 条陷阱 |
| `pages/mc07-音频平台与工具.html` | **平台与工具** —— 选型事实与端到端做法 | 原 §3 全部（3.1–3.4）/ §4 软件工具 + §4.1 / §5 推荐工作流（**整节搬此**）/ §7 许可须知 / §8 的选型类 4 条陷阱 |

  - **文件重命名**：`mc06-音频素材与FM通路.html` → `mc06-音频通路机制.html`（保 `mc06` 编号与「机制」定位的连续性），新增 `mc07-音频平台与工具.html`。全仓仅 `manual.html` + `sidebar-reference.js` 两处活引用，两处均已改；`CHANGELOG` / `AGENTS.md` 中的旧文件名属历史叙述，按 §十 保留不改。
  - **两处跨页内容裁决**（原为同页内重复或含混）：
    ① 「音频 → FM 音色无解 / 音频 → 音符可行」的**原理框从 mc07 §3.4 移入 mc06 §3** —— 它讲数学性质（欠定逆问题 vs 适定问题）而非工具，属机制；mc07 §3.4 改为交叉引用，避免两页各写一遍。
    ② 「AI 的产出不能直接当 BGM」留 **mc06**（它由 YM2608 的 6 复音 / 128 patch 直接推出，与「GM 音色 ≠ FM 音色」同源）；mc07 §3 只留可操作建议（换音色 / 改织体 / 减声部）并引用 mc06。
  - **`§` 编号全量重算**：mc07 的 §3→§1、§4→§2、§5→§3、§7→§4、§8→§5，§3.1–3.4→§1.1–§1.4；mc06 的 §6→§4、§8→§5，并新增 §3（原理）。所有 `§x.y` 交叉引用同步改写，逐条验证无悬空。
  - **双向交叉引用**（⚠️ **计数订正于第八轮**：原文写「共 3 处」却列了 4 项、「共 5 处」实为 6 处，按脚本重计数订正为下述）：mc06 → mc07 共 **4** 处（开头、§2 表末「具体由哪个工具产出」、§3 note-box 两处「完整做法 / 见 mc07」）；mc07 → mc06 共 **6** 处（开头、§1.3 GM 音色、§1.4 原理、§3 两条要点与 note-box）。所有跨页链接经解析全部可打开。
  - **`manual.html` 布局无需改动**：机制段用 `index-grid-2`，卡片 5 → 6 张恰为 3 行整齐，未动 `style.css`。新增卡片「音频平台与工具 / AI 作曲平台、tracker 软件工具与端到端工作流」。
  - **无内容丢失**：以 159 条特征事实（硬件型号 / 价格 / 版本号 / 日期 / 许可标识 / 配额数字等）做并集校验，**全部命中**。唯一检出的 `A460`/`A466` 缺失系第五轮裁剪端口枚举时**有意删除**（非本次拆分丢失），已在第五轮条目留痕。
  - **第六轮验证**：两页各 23 类标签开闭配平（`meta` 为无结束标签的自闭合元素，不计入配平）；`mc06` 88 行 / `mc07` 171 行；相对链接全部可解析；`§` 引用 `mc06` 2 个 / `mc07` 9 个**均无悬空**；全文 AIVA 残留 0；`sidebar-reference.js` 与 `manual.html` 的 16 个条目**双向一一对应、无孤儿**（`tool-*` 系列归 `tools.html` 索引，不在本段）；`pytest tools/tests/` **642 passed, 1 skipped**、`./start.sh fullaudit` **7/7 全绿**。**零引擎改动、不 bump 版本**（仍为 `0.3.021`，与 `c52` 同轮次）。
- **第十三轮（用户拍板 FM 通路输入格式 = MIDI + 新建 `devdocs/123` 实现计划 + 清三处遗留错误描述）**：用户在第十二轮 F03 调研基础上拍板架构并要求「写 devdoc 详细制定具体计划，并修正文档的错误描述」。**纯文档轮次，零代码改动**。
  - **用户决策（四项）**：①**输入格式 = MIDI**（复用 `core/lib/midi.c`，不新写解析器）；②**后端选择 = 自动检测**（`hal_audio_detect()` 有 MPU-401 走现有 MIDI 通路，无则走 FM）；③**v1 范围 = FM 6 通道 + SSG 3 通道**（SSG 合成鼓），**RHYTHM 推迟**；④**音色内容另开 devdoc**，本轮只定格式与机制。
  - **新建 `devdocs/123-MIDI转FM通路实现计划.md`（12 章，状态：计划中，未实现任何代码）**。关键内容：
    - **§一 承接 122 §5.2 的 ERRATA**，含「症状 → 判定过程 → 根因 → 修复 → 验证」完整记录与五处订正表（E1 WAV 死路 / E2 SSG 通道数 / E3 音色通用过强 / E4 patch 许可断言无来源 / E5 `:213` 已收敛）。
    - **§二 现状坐标**：逐条钉住 `core/lib/midi.c:254`/`:238`、`core/engine/audio.c:97`/`:343`/`:362`、`core/plat/hal_audio.c:143`、`core/engine/nb_audio.c:17`、`core/plat/hal.h:142`/`:168`。
    - **§四 模块分解 M1–M6**，含「可否主机单测」列。**M1 `fmopn` / M2 `fmseq` 落 `core/lib/`、零 `outb()`、可在主机穷举单测** —— 这是最大风险削减点：**绝大部分验证不需要模拟器**。
    - **§七 分阶段 S0–S7 与硬门控**。**S0（消解 `0188h`–`018Fh` 逐端口分工，纯调研）只卡 S2 不卡 S1** —— 寄存器语义不依赖端口映射，故调研等待期不阻塞主线。
    - **§九 验证矩阵**逐条对齐 AGENTS §八 五禁（含「先 `build` 再 `make`」「不用点击计数当判别器」「门控须分别覆盖 BGM 与 voice 两通道」）。
    - **§十一 踩坑预登记 9 条**，其中 §2.2/§2.3 两条是**代码级既存陷阱**：FM 侧必须复用 `hal_wallclock_smooth_ms()`（devdoc 107 修过裸墙钟导致的追帧音爆），且 `hal_audio.c:143` 的 `A460h ← 0x01` **bit1 是「强制 OPNA 静音」**——改 PCM 代码时误动该写值会**静默静音整条 FM 通路而 PCM 一切正常**。
  - **一处架构级发现（利好，已写入 §2.4）**：`docs/refdocs/F02_86pcm_registers.md:100-101` 记载 `A466h` 电子音量有 **FM 路径**（`000b` VOL1 直接 / `001b` VOL2 间接）⇒ **`bgm_vol` 对 FM 生效不需要新增任何 pref 或设置界面项**，与 `pcm_vol` 共用端口不同路径码。但 step 编码与衰减曲线**未实测**，标为 S5 待确认（不得照抄 PCM 的倒序假设）。
  - **`docs/refdocs/F03_opna_fm_and_bgm_routes.md` 修 4 处**（382 → 438 行）：
    - **§4.6 重写**——初稿此处**自相矛盾**：先说「只需把输出后端从 UART 换成 OPNA 寄存器写入」，紧接又说「`midi.*` 的 SMF 解析器不能直接复用」。两句各自在**不同输入格式**下成立却并排出现且未说明前提。输入定为 MIDI 后后者已不作数。
    - §1.2 `选型建议(待决,非既定)` → **`选型结论(已决)`**，补决策表；删「这是一个未决架构选型」。
    - §4 标题 `MML 子集(作曲输入格式)` → `MML 子集(备选记谱法参考,非本项目输入格式)`；**§4.1 重构**为「为什么是 MML(**以及为什么本项目不用它**)」，用对照表说明 MML 会**丢掉 MIDI 侧已免费拿到的力度/弯音/CC**。
    - 新增 **§1.4**：v1 不做 RHYTHM 的理由（见下）。
  - **`naiz-guildbook/pages/mc06-音频通路机制.html` 修 7 处**（92 → 93 行）：
    - **⚠ 订正一处归因错误**：§2 表与 §5 原写「在 PC-98 上通常要另外备 `2608_*.WAV`，**缺了就完全没声音**」。实情是 `2608_*.WAV` 是 **NP2kai 模拟器侧**补 YM2608 内置 ROM 的文件，**真机零素材依赖**（鼓在芯片 ROM 里），且「完全没声音」过强——缺的只是鼓通道、FM 通道照样响。**该错误会让创作者误以为上真机还得准备素材，从而误判工作量**。
    - §3 导语「我们推荐第一条」→「**已经选定第一条（A）**」；§3 方案 A 标 `✅已选定`；§3 方案 C（MML/S98）降为**备选，暂不做**并补「它没有力度、没有弯音」的理由。
    - §2 表 MML 行标注本项目不用。
    - 新增 note-box 两条用户向说明：**为什么是 MIDI**（现成通路已留下力度/弯音/踏板，换 FM 音色近乎白捡），以及 **1b 的交付代价**（同一条 `bgm` 指令，装了 MIDI 卡的玩家与没装的玩家**听到的音色会不一样**，属固有代价非故障）。
    - 自查中**发现并修正自己引入的两个缺陷**：`<a href="#s3">` 是**死锚点**（本页无任何 `id="sN"`，且全 guildbook 无页内锚点先例）已改回本页既有的纯文本 `§N` 引用惯例；同页自引用链接 `href="mc06-…#s1"` 无先例亦已移除。另按 §九.7 去掉面向创作者的机制页里的 `devdocs/123` 内部编号（guildbook 仅 `sc15` 有一处引用 devdoc 的先例）。
  - **`devdocs/122-BGM本地静音根因与音频通路取舍.md` 仅头部追加 `⚠ ERRATA` 块（190 → 280 行，正文一字未改）**，严格走 AGENTS §十 四步路径：①头部追加 ERRATA ②新建接替文档 123 承载完整记录 ③CHANGELOG `c51` 条目加订正标记（**锚点 `c51` 与标题未动**）④AGENTS 加前向引用。**明确声明未受影响的部分**：§5.1「WAV → FM 不可行」结论仍成立、两条根因分析与 §四 代码侧缺口清单不受影响。
  - **`naiz-guildbook/manual.html` ui02 订正**：`settings.txt 配置` → `config.toml 项目配置 + USER.CFG 玩家偏好`（`settings.txt` 已于 devdoc 120 废止，项目配置编译进 `nb_config.h`、运行时零解析）。
  - **`AGENTS.md`**：头部「最新条目」补第十三轮摘要；**§十四 音频通路表加前向引用**（**表内现有行一字未改** —— 那些是 current-state 陈述，仍然准确：HAL 至今无任何 YM2203/YM2608 端口访问）。
  - **同步**：`docs/refdocs/README.md` 中 F03 描述的「MML 记谱法子集」改备选措辞。**`mc07` 经核查无需改动** —— §3 工作流图末尾已是 `└─▶ 引擎（YM2608 后端）`，方向与本决策一致；两处 MML 提及均在工具表内（`mml2mdx`、MML 语法参考），属事实登记，未声称是本项目输入格式。
  - **⚠ 本轮发现并按用户指示「按现状修正」清理的更大范围错误**：`settings.txt` 虽已废止，但 guildbook **共 7 页 15+ 处仍在描述它**（此前初扫只报 5 页，**漏掉 `cf04` 补漏 2 处与 `cf06` 整页 3 处**，见下）。**先取代码依据再改文档**：`core/engine/settings.c` / `settings.h` **已不存在**，`settings_load()` / `GameSettings` / `settings_save()` 全仓零命中，`nb_config.h` 实际宏为 `NAIZ_VERSION` / `NAIZ_DLGSTYLE` / `NAIZ_BTNSTYLE` / `NAIZ_BLACKLETTER_TITLE` / `NAIZ_BLACKLETTER_DIALOG` / `NAIZ_DEFAULT_LANG` / `NAIZ_TRANSITION_TYPE` / `NAIZ_TRANSITION_FRAMES`，`prefs.c:202-215` 的 `USER.CFG` 键为 `lang` / `text_speed` / `bgm` / `snd` / `vc` / `bgm_vol` / `pcm_vol`，`sys_*.txt` 实为 **9 种**语言。
    - **`ui02`（重构，本批最大改动）**：§1 由「settings.txt 键值对文件」整节改为**「配置文件分家」对照表**（`config.toml` 项目级 → 编译进引擎运行时零解析 / `USER.CFG` 玩家级 → `prefs_load()`+`prefs_save()`）；补「同键名跨归属相反的文件 = getter/setter 可各绑不同副本」这一 0.3.013 根因说明；§2/§3 由 `dlgstyle=N` / `btnstyle=N` 改为 `[dialog] style` / `[button] style`；§4 `lang` 明确归 `USER.CFG` 并**由 4 种语言补齐全部 9 种**（原表只有 eng/chi/jpn/kor，漏 cht/fre/ger/ita/spa/por），补「无 `USER.CFG` 回落 `default_lang`」与开机菜单选语言的机制原因；§5 澄清 `settingmenu` 未来只能改**玩家级**偏好。
    - **`cf01:113,115`**：注入 `settings.txt` → 编译进 `nb_config.h`；版本号链路由 `build_game.py` 更正为 `export_config.py`。
    - **`cf02:18,139,164`**：`:18` 「分配到 `settings.txt`」→ 生成 `nb_config.h` 宏；`:139` 表格行**工具列亦错**（`build_game.py` → `export_config.py`）、产物由 `version=` / `blacktitle=` / `blackdialog=` 改为三个 `NAIZ_*` 宏；`:164` 删除已不存在的 `settings_load()` / `GameSettings`（`settings.c`/`settings.h`）链路，改为编译期宏并说明构建只会 **unlink** 残留 `settings.txt`。
    - **`cf03:94`**：§3.1 标题与示例 `dlgstyle=3` → `config.toml` 的 `[dialog] style = 3`。
    - **`cf04:15,36,54,70`**：4 处（初扫只发现前 2 处）；`:54` 配置示例 `btnstyle=1/3` → `style = 1/3`；`:70` 交叉引用表的「`settings.txt` 完整配置参考」→ 改为「配置分家与 `settingmenu`」。
    - **`cf06:59,60,75`（初扫整页漏掉）**：`build_game.py` 写入 `settings.txt` 的 `blacktitle=`/`blackdialog=` → `export_config.py` 生成 `NAIZ_BLACKLETTER_TITLE`/`_DIALOG` 宏；「引擎启动时读取 `settings.txt`」→「运行时零解析，改开关必须重新编译」；`:75` 补 **`make` 也要跑**（§八 五禁之二：宏是编译期的，只 build 不 make 跑的是旧引擎）；顺带把 §5 的 `dlgstyle` 键名订正为 `[dialog] style`。
    - **顺带 2 处旧键名残留**（与 `settings.txt` 无关但同源）：`mc04:51`「对话框底色（`dlgstyle` 动态改色）」→ `[dialog] style`；`manual.html:47` 摘要里的「dlgstyle/btnstyle/lang」→ 「对话框/按钮样式、lang」。
    - **残留复查**：`settings.txt` 仅剩 3 处提及，**全部是刻意说明其已废止**（`ui02:19`「现已废止」/ `cf02:164`「已全部删除」/ `cf05:63`「无需 settings.txt」）；旧键名 `dlgstyle` / `btnstyle` / `blacktitle=` / `blackdialog=` **零残留**。
    - **⚠ 遗留（既存、非本轮引入，仅报告未擅自扩大范围）**：`fd01-引擎基本概念.html` 有一张表格行宽不一致（2/3 列混排）；已核实 `mc02` / `mc03` 指向 `fd01#1.4` 的锚点**确实存在**，系首版检查脚本未剥 URL fragment 造成的**误报**，非死锚。
  - **第十三轮验证**：`F03` 438 行、**全部 Markdown 表格列数配平**；`devdoc 123` 280→（新建）表格配平、§ 引用自洽；`mc06` 93 行、23 类标签开闭配平、**剩余 `<a href>` 全部指向真实存在的文件**（`cf07` / `mc07` / `sc10`）、死锚点与自引用残留均为 0；`devdoc 122` ERRATA 块表格配平且**正文原文抽查仍在**（`严重欠定的逆问题` / `切断一个循环依赖` / `2608 = 2612 的 6FM + 6SSG + ADPCM` 三处均在）；`manual.html` 已无 `settings.txt`；**未触碰任何 `.c`/`.h`/`.py`/`.nb`** ⇒ **不 bump 版本**（仍为 `0.3.021`）。`pytest tools/tests/` **642 passed, 1 skipped**、`./start.sh fullaudit` **7/7 全绿**。

- **第十二轮（新增 refdoc `F03`：OPNA FM 寄存器参考 + BGM 通路选型研究；据用户指示「将研究写成 refdoc，不动代码」）**：把 BGM 四条通路（PCM / MIDI / FM / PMD）在**实机与 NP2kai** 上的差异落成文档，并补完 FM 寄存器与音色格式调研，**产出「自研 FM 后端」的实现规格**。**纯新增文档，零代码改动**。
  - **新增 `docs/refdocs/F03_opna_fm_and_bgm_routes.md`（382 行）**，按 F 类（声音）归档并在 `docs/refdocs/README.md` 补索引行 + 6 条新来源。
  - **§1 选型结论（待决，非既定）**：**主线建议自研 FM(OPNA) 后端；MIDI 降级为「检测到 MPU-401 才启用」的可选通路；不引入 PMD 作为运行时依赖。** 三条硬理由：①**硬件可得性**——OPNA 是板载标配，而 MIDI 是 PC-98 从无内置、需扩展卡的路径（依据本仓 `F01_sound_boards.md:100-102` 板卡清单里 Qvision MidiMaster 明确标注为「WaveMaster 子卡」、`F02:33`「MIDI(BGM)在另一块卡上」）；②**架构相容性**——PMD 需从 32 位保护模式切回实模式调 INT 60h，撞 `docs/B91` §3 禁止表，且 PMD 独占 OPNA；③**已站在门口**——`core/plat/hal_audio.c:143` 已在写 OPNA mask 寄存器（`A460 ← 0x01`，bit1 = 强制 FM 静音 ⇒ **现成的 FM 静音通路已存在**）。**同时明确标注这是 `devdocs/122:213` 所列待研究项的输入，不构成实现授权。**
  - **§1.3 厘清「借用 PMD」的正确说法**：值得借鉴的**只有 MML 记谱法**（纯文本、diffable、通道即声部），**不是它的代码**——不捆绑 PMD（实模式互操作）、不读 `.M` 产物（`libopenpmd` 自述 **WIP** 且**只解析不管芯片输出**，输出那一半仍须自写）。方案形态 = `MML 文本 → 自研解析器 → 自研 FM 后端 → OPNA 寄存器`，正是当年 PC-98 的标准分工（`F01:109-110` FMP 管 FM、PPZ8 管 PCM）。
  - **§2–§3 寄存器参考**：bank 选择(A1A0) / 逐算子(`$30`–`$9F`) / 逐通道(`$A0`–`$B4`、`$28` KEYON) / 系统级 / SSG / RHYTHM+ADPCM / OPNA mask，主依据为 **ymfm（BSD-3-Clause，MAME 所用 FM 核）**。
  - **⚠ 纠正四个流传很广的错误前提**：①**YM2203 是 3 个 FM 通道不是 6 个**（ymfm 写死 `CHANNELS = IsOpnA ? 6 : 3`），只有 YM2608 才是 6 个；②**FM 通道 7/8 不存在于 OPN/OPNA**（属 YM2610/OPN2L）；③**OPNA 无「LFO 波形选择」**（`WAVEFORMS = 1`，可选波形是 OPL3/OPZ 特性）；④**OPNA 上不存在 `D2L`/`DT2L` 寄存器**（那是 OPM/YM2151 的名字，OPN 是 `AR/D1R/D2R/SL/RR`；FMP 文档把 `$70` 叫 SR 即 Yamaha 的 D2R）。
  - **⚠ 订正 FMP 官方文档一处错误**：其「音色直接変更(OPNA)」寄存器表把 **SR 范围写成 0–15**，而其音色定义页与 ymfm 均确认 `$70` 是 **5 bit、0–31**。**以 ymfm 为准**，并在 §3.3/§6 双处标注。
  - **§4 MML 子集**：通道分配（`A`–`F`=FM 1–6、`G`–`I`=SSG 1–3、`J`=PCM、`K`/`R`=节奏）、音符/时值/附点/八度/`#Tempo`（**每分钟二分音符数**）/`#Zenlen` 可整除约束、**音色定义 11 参数与取值范围**。**§4.4 给出「6 复音」的准确表述**：每通道单音但 4 音和弦吃 4 通道、`#FM3Extend` 的扩展 ch3 模式让 FM3 同发作 4 音（OPN 原生特性）、SSG 3 通道与 RHYTHM 6 通道不占 FM 通道 ⇒ **`mc06` 现有「6 复音」表述准确，不应被替换成「必须拆和弦使每声道单音」**。
  - **§4.5 收录 PMD 手册自身的 CPU 警告**（「全音符越长、时值种类越多，播放时耗 CPU 越多，**特别是要用作电子游戏场景 BGM 的曲目**」）——驱动作者自己给的告警，对本项目「渲染对白同时泵 PCM FIFO」的帧预算直接成立 ⇒ 建议 `#Zenlen` 取小值。
  - **§5 音色格式：结论是不可用**。**证伪一个流传很广的前提——不存在所谓「S98 `.DAT` 音色库」**：S98 是**寄存器转储日志**格式（OPN 版 VGM），根本没有乐器/tone 概念。现存 4-op 库为 **PMD `.FF`(32B)/ MUCOM88 `.DAT`(固定 0x2000)/ YM2612 Inst. Editor `.DAT`(寄存器列表)/ FMP(无文件)**；**未找到任何 CC0/公有领域 OPN patch 库**，全是受版权保护的商用或免费Ware 转储，且**转换工具许可不传递给数据**。⇒ **建议自研 32 字节音色格式**（覆盖 MUCOM88/PMD 全部能力并加 pan），存文本/JSON 进 `assets/<项目>/`。另记三个坑：**算子顺序被置换为 1/3/2/4**（错则静默音高全错）、**DT 编码跨格式不一致**（原始 0–7 vs 线性 −3..+3）、名字字段 6B vs 7B 不兼容。
  - **§5.6 收窄第十一轮的一处过宽表述**：彼时断言「无 PC-98/PMD 可用的 MIDI→MML 转换器」，**实情是 ConvFMML(`github.com/rerrahkr/ConvFMML`) 确实以 PMD 为输出目标之一**（mml-guide 原话 "including PMD"），把它归为「只面向别的方言」**是错的**。**但结论不变**，理由由「方向不对」改为「质量不够」：该工具**已停止维护**且只转序列、只支持极少命令。**第十一轮那条否决本身仍然成立**，仅其支撑子表述过宽，故在此追加订正而不改写历史条目。另确认 `pmd2mml` 是 **PMD 二进制→MML 反编译器**（LGPL-3.0）**而非 MIDI→MML**，第十一轮记录正确。
  - **§7 列出 10 条显式未确认项**，其中**第 1 条标为动手前的硬阻塞项**：`0188h`–`018Fh` **逐端口对应哪个 bank 的「地址」还是「数据」**未取得可靠出处（芯片侧 A1A0 bank 表可靠，端口窗口已由 `F02` §1 记录引自 NEC「PC-9801-86 未公開情報」，但**逐端口分工未证**）——**猜错则整个 FM 通路静默无声**。另含 **NP2kai FM 保真度已有投诉但未量化**（issue #112 实录其 FM 比独立 `np2fmgen` 「tinny / distorted」，作者归因 fmgen 与音量混音且仍在调 ⇒ 模拟器听感不作参考级音质）、ADPCM 采样率各来源说法不一、PMD/FMP 音色库授权条款、26K 与 86 板装机比例、FM 调度实测 CPU 占用、**RYO 规格未取得一手来源故本文件不含任何 RYO 断言**、EUPHONY `.FMB` 布局未证、YMPLAY/UNIMON 未取得一手来源。
  - **§6 陷阱清单 11 条**，其中与本项目直接相关的两条：**`A460h` bit1 = 强制 FM 静音**，故改 PCM 路径的 `A460` 写入值会**静默把 FM 一起静音**（当前写 `0x01`）；**SSG 的 `$0D`/`$0E` 是 GPIO 不是寄存器**，连续写会踩 GPIO 须先用 `$07` 设方向。
  - **许可纪律**：全文件**不搬运任何来源代码**；`YM2608-Tone-Editor`（**GPL-2.0-or-later**）**仅用于核对二进制字段偏移这一硬件无关事实，不作文本来源**（AGENTS §十 GPL v2 不得复制）；位域本身是硬件行为不受版权保护。
  - **第十二轮验证**：`F03` 382 行 / 17276 字符；**全部 Markdown 表格列数配平**（含转义竖线）；标题层级 `##`/`###` 共 32 项无跳级；引用的 `F01`/`F02` 均存在；13 项关键事实断言逐条在位（含 4 处错误前提纠正、FMP SR 订正、`硬阻塞项` 标注）；`docs/refdocs/README.md` 索引 + 6 条来源已补；**未触碰任何 `.c`/`.h`/`.py`/`.nb`**，`core/` 与 `tools/` 零改动 ⇒ **不 bump 版本**（仍为 `0.3.021`）。`pytest tools/tests/` **642 passed, 1 skipped**。

- **第十一轮（`mc07` §1.2 Suno 结论纠错：官方证实 Studio 可导 MIDI）**：用户从 Gemini 取得一批补充材料并询问可否写入。**逐条外部核对后按「错误与未经证实的内容不加入」原则取舍**——采纳 6 项官方可核实事实，否决 6 项，其中**修正了 `mc07` 里一处已知的错误结论**。
  - **⚠️ 修正既有错误结论（本轮最重要的变更）**：`mc07` §1.2 原写 Suno「**❌ 不提供 MIDI 输出**」，并把「Suno Studio 能否导 MIDI」列为「两条还没核实的线索」。**该结论已被 Suno 官方推翻**，按 `AGENTS.md` §十「任何地方还留着一个已知错误的结论，就是未完成」必须改。
    - **官方依据**：<https://help.suno.com/en/articles/8128193>（Suno 官方帮助中心「Exporting from Studio」）原文给出操作路径——**Stems 面板先拆成最多 12 条独立音轨 → 右键某条 stem → *Get MIDI*，每次消耗 10 credits** → 生成 `.mid`；官方产品页 <https://suno.com/landing/audio-editor> 同样写明可导出 stem 级 WAV 与 MIDI。
    - **表格 Suno 行改为按档位区分**：免费档「能下音频、**没有 MIDI**」，Premier 的 Studio「**能导 MIDI**」。Udio 行改为「**任何档都拿不到文件**」。小节标题由「『更便宜甚至免费』的平台为什么反而没用」改为「**免费档为什么帮不上忙**」，导语改为「能不能拿到取决于订到哪一档」，并补一句结论「**Suno 靠的不是降价，是加档**」。
    - **「两条未核实线索」→「只剩一条」**：删除 Suno Studio 那条（已证实），**保留 Veena**（本就标注未证实，符合本轮原则）。
    - **新增「性质提醒」note-box**：**Get MIDI 是「拿音频反推音符」，不是 AI 内部真正的作曲数据**，故与 basic-pitch、Mureka 分轨导出**属同一类**，**质量上限受转写精度限制**（引 `mc06 §4`）；同时指出它**天然满足「先拆轨、一次只处理一件乐器」的前提**。
    - **新增事实**：`Get MIDI` / `10 credits` 每次 / 最多 12 条 stem / Studio 2.0 于 **2026-08-13** 加入 MIDI 导入、录音、钢琴卷帘并可将 MIDI 片段用作生成提示 / 官方列出的四类用途（换乐器重弹、分析和声、重新编曲、连音频做成 sample pack）。
    - **§3 推荐工作流 ① 补入 Suno Studio**（原为「Mureka Premier / Magenta Studio」）——它现在确实能产出 MIDI。
  - **采纳的另 1 项（按用户指示）**：§1.2 山寨站警告后加一句实例——**本次核对遇到一个域名多一个 n 的仿冒站，声称「Premier 约 $24–30/月」并罗列 Studio 2.0 细节，看似极可信；该价格未证实，故不写入本文**。这是第八轮删除「选型陷阱」段后保留的第一个具体举证。
  - **否决的 6 项（错误或未经证实，逐条留痕）**：
    - `PMD2MML` 把 MIDI 转 `.mml` —— **方向反了**：真实 `pmd2mml`（`github.com/Blargzargo/pmd2mml`，LGPL-3.0）是 **PMD 二进制 → MML 反编译器**。
    - 用 `mid2mml` 转 MIDI→MML 喂 PMD —— **无 PC-98/PMD 可用工具**：查到的 MIDI→MML 全属别的方言（`midi2mml` 自述为 RP2040 玩具、`ConvFMML` 已停止维护、`PetiteMM` 是 TinyMM 替代、tom7 `midimml` 面向 NES/NSF）；**MML 是方言家族，PMD 方言不兼容这些产物**。
    - PMD 编译器在 `pmd.com` —— 域名查不到，**未经证实**（真实入口为 `mml-guide.readthedocs.io/pmd/`、`battleofthebits.com`）。
    - 完整流程「DAW → MML → `.M/.M2` → PMD 播放」—— 含上述错误，且终点是 **PMD 驱动接管音源**，与 `mc06 §3` 推荐方案 A「让引擎认 MIDI」冲突；属 `devdocs/122-…md:213` 已列的**未决架构选型**（FM 乐谱格式选型），不宜写成既成事实。
    - 「必须拆分和弦、确保每声道单音（Monophonic）」—— **表述误导**：每通道单音无误，但真正的约束是**同时最多 6 个音（6 复音）**，4 音和弦吃掉 4 个通道；`mc06` 现有表述更准，不替换。
    - 「量化到 1/16、1/32」—— 本身无害，但**依附于已否决的 MML 流程**，单独出现会暗示该流程为推荐路线。
    - **注**：本仓 `docs/refdocs/F01_sound_boards.md:110` 早已收录 PMD（FM 音源驱动/播放器 + MML 编译器）这一**背景事实**，本轮未改动该文件。
  - **连带订正**：`AGENTS.md` 头部原写「**Suno·Udio 为何无用**」，因 Suno 已有 MIDI 导出而失效，改为「免费档为何帮不上忙（按档位区分）」。CHANGELOG 第八轮条目内的历史表述**按规则不改写**，仅在本轮追加订正说明。
  - **第十一轮验证**：`mc07` 169 行（原 163）；23 类标签开闭配平；相对链接全部可解析；**新增 2 个官方外链**（`help.suno.com` / `suno.com`）；本页 `§` 引用无悬空；**被否决项零出现**（`pmd2mml` / `mid2mml` / `pmd.com` / `Mibake` / `.M2` / `FMPMD2000` / 快速 / 东方旧作 / Grounseed 各 0 次）；**新核实事实全部在位**；**旧错误表述「不提供 MIDI 输出」计数 0**；`mc06` 未改动（92 行，既有事实全在）；AIVA 残留 0；`pytest tools/tests/` **642 passed, 1 skipped**、`./start.sh fullaudit` **7/7 全绿**。**零引擎改动、不 bump 版本**（仍为 `0.3.021`）。

- **第十轮（`mc06` §1 导语精简 + §4 主题改为「WAV 能否转 MIDI」）**：用户两处指示——①删掉 §1 导语中「MIDI 那条通路本机没装卡、走不通。它们在硬件上是分开的，这一点是后面所有取舍的根源。」；②**指出 §4 的主题不该是「有两件事」而应是「WAV 是否可以转 MIDI」**，要求改标题与描述。
  - **① §1 导语由三句缩为一句**：`先记住分工：BGM 走 FM、音效语音走 PCM，MIDI 那条通路本机没装卡、走不通。它们在硬件上是分开的，这一点是后面所有取舍的根源。` → `先记住分工：**BGM（背景音乐）走 FM，音效和语音走 PCM**。`
    - **核对：被删的「硬件上是分开的」这一论点无信息丢失**，三处仍在：开篇「它们像三台**互不相干**的播放器」、表下第一条结论「因为它们根本**不是同一个部件**，各走各的」、§1 note-box「两组的**端口也不重叠**……这就是上面第一条结论的硬件依据」。
    - 表格内 `MIDI 音源 / 本项目走不通——本机没装这张卡` 一行**保留**（自解释，不依赖导语提及）。
  - **② §4 主题重定位**：标题 `4. 有两件事，一个做不到，一个做得到` → **`4. WAV 能转成 MIDI 吗？`**。诊断：原标题是抽象的二元对立，读者看不出在回答什么问题；而素材创作者真正会问的就是「手里这段 WAV 能不能转 MIDI」。
    - **导语改为「先给答案、再划边界」两段**：第一段直接回答（「**能**，而且有成熟工具可用——这条路原理上就走得通」）；第二段才划边界（「**能转成「音符」，不能转成「FM 音色」**……一混就会得出「AI 出的音频全都没用」这个错误结论」）。原「得拆成两问」的抽象铺垫删除。
    - **表格两行按「先肯定、后否定」调换行序**（原为 ❌ 在前、✅ 在后，与「能否转 MIDI」这一提问方向相反）：现第 1 行 `WAV / 音频 → MIDI（音符：音高 / 时长 / 分轨）` ✅，第 2 行 `WAV / 音频 → FM 音色（patch）` ❌。行标签由「声音 → 音符 / 声音 → FM 音色」改为 `WAV / 音频 →` 开头，与新主题同措辞。
    - 「为什么」「结论」两列内容与术语（`AMT` / `适定问题` / `欠定的逆问题` / `4 算子参数` 反推不出唯一答案）**原样保留，未删一字**；note-box 内四段（关键区别·音符是乐谱音色是乐器 / 业界做法反着来 / DDSP 是另一个方向 / 只能下载音频的平台不是死路）**全部保留**。
  - **连带同步（因改主题而措辞需对齐）**：`mc06` §5 陷阱「别因为『反推 FM 音色做不到』……别顺带认为『反推音符也做不到』」→「别因为『**WAV 转不成 FM 音色**』……别顺带认为『**WAV 也转不成 MIDI**』」（§ 编号不变）；`mc07` §1.4「为什么这条路原理上成立」→「为什么 **WAV 转 MIDI 原理上就成立**」。
  - **顺带修一处第九轮遗留**：§4 note-box 末句「可用的转写工具……顺序，见 mc07」原为**纯文本**，按第九轮「所有『见 mc07』一律可点」的规矩补成链接。现两页**未加链接的『见 mc07』计数为 0**。
  - **新增两处带编号的跨页引用**：`mc06` §4 导语与 note-box 末句均指向 `mc07 §1.4`（转写这条路：音频 → MIDI）——**这是 `mc06` 首次出现带章节号的跨页引用**（此前全为无编号「见 mc07」）。经核对 `mc07` 的 §1.4 标题真实存在。
  - **引用有效性复核**：全站对 §4 的引用**均为按编号**（`mc06` §5「见 §4」、`mc07` §1.4 与 §3「见 mc06 §4」），**无按标题引用**，故改标题不影响任何既有链接；改后逐个核对目标章节全部存在：mc06→mc07 §1.4；mc07→mc06 §1 / §2 / §4。
  - **第十轮验证**：`mc06` 92 行；23 类标签开闭配平；相对链接全部可解析；本页 `§` 引用无悬空；**49 条特征事实**全部在位（含 `欠定的逆问题` / `适定问题` / `DDSP` 与全部硬件参数）；**两页未加链接的「见 mc07」均为 0**；AIVA 残留 0；`pytest tools/tests/` **642 passed, 1 skipped**、`./start.sh fullaudit` **7/7 全绿**。**零引擎改动、不 bump 版本**（仍为 `0.3.021`）。

- **第九轮（`mc06` 三处按用户指示修改）**：①§1 表格新增「**适合放什么**」列并前置结论句；②**§3 与 §4 对调**（原理段后置于方案段之后）；③「产出工具见 mc07」补上链接。
  - **① §1「三个能发声的部分」新增用途列**：表格由 4 列扩为 5 列，新增 `<strong>适合放什么</strong>` 列并**排在「是什么」之前**（用途比硬件型号更需要先看到）；**行序也按重要性重排为 FM → PCM → MIDI**。三条的用途分别写明：FM = **「BGM（背景音乐）。本项目唯一一条能一边放音乐、一边放语音和音效的通路」**；PCM = **「音效和语音（`sound` / `voice`）。不能拿来放 BGM——会跟音效语音抢那唯一一条通道」**；MIDI = **「本项目走不通——本机没装这张卡」**。表前加一句结论式导语「**先记住分工：BGM（背景音乐）走 FM，音效和语音走 PCM，MIDI 那条通路本机没装卡、走不通**」，让读者看表前就拿到答案。原「一句话限制」列因新列已含限制语义而更名为「限制」，内容未删。
  - **② §3 / §4 对调**：新顺序为 §1 三个能发声的部分 → §2 音乐文件有哪几种 → **§3 引擎要吃哪种音乐** → **§4 有两件事，一个做不到，一个做得到** → §5 容易踩的坑。调换后逻辑更顺：**先在 §2 已列出的文件格式里挑「引擎吃哪种」（§3），再解释为什么「反推」这条路走不通（§4）**。
    - **连带修正因对调而失效的编号引用（3 处）**：`mc06` §5「见 §3：前者无解，后者有解」→ **§4**；`mc07` §1.4「为什么这条路原理上成立……见 mc06 §3」→ **§4**；`mc07` §3 要点「它没这个本事（原因见 mc06 §3）」→ **§4**（且该处原本是**纯文本、不是链接**，一并补成 `<a>` 链接）。经全站检索确认**再无残留 `mc06 §3` 指向原理段**；`mc07` 对 `mc06` 的编号引用现为 §1 / §2 / §4，逐个核对目标章节均存在。
  - **③ 「产出工具见 mc07」补链接**：§3 方案 B 说明列的「产出工具见 mc07」由**纯文本**改为 `<a href="mc07-音频平台与工具.html">mc07</a>`。同时把 §5「怎么落地见 mc07」也由纯文本补成链接，**使 `mc06` 内所有「见 mc07」一律可点**。
  - **第九轮验证**：`mc06` 91 行（内容增加但删去了空行，净持平）；23 类标签开闭配平；相对链接全部可解析（**跨页 mc07 链接由 3 处增至 5 处**）；本页 `§` 引用无悬空；跨页 `mc06 §` 引用（§1 / §2 / §4）目标全部存在；AIVA 残留 0；新增事实与既有事实抽查全部在位（`BGM（背景音乐）`、`sound` / `voice`、`不能拿来放 BGM`、`本项目走不通`、`6 复音`、`共用这一条 FIFO` 等）；`pytest tools/tests/` **642 passed, 1 skipped**、`./start.sh fullaudit` **7/7 全绿**。**零引擎改动、不 bump 版本**（仍为 `0.3.021`）。

- **第八轮（`mc07` 同样改用平实语言，并删除「选型陷阱」段）**：用户要求「同样地，对音频平台与工具进行改造，且删除选型陷阱段」。两件事一起做——**① 去程序员腔**（手法与第七轮 `mc06` 相同：换说法、不换事实，术语人话先行、原术语括注保留）；**② 删除 `mc07` 原 §5「选型陷阱」整段**。
  - **① 平实语言改写**（面向素材创作者，术语去实现腔）：
    - **开篇**改为呼应上一页的分工：「上一页讲了机制——**音乐该做成什么形状**。这一页讲现实：**用什么平台、用什么软件，能真的做出那种形状的东西来**」；页内导航句由「详见 mc06 / mc07 / sc10 / cf07」这类罗列改为一句话说明每页**回答什么问题**。
    - **§1.1 标题**「Mureka 的 MIDI 导出：Premier 是唯一入口」→「Mureka：拿到 MIDI 的两条路」；`Export Stem Audio` 括注「导出分轨音频」；「**分轨数**」→「**拆成几轨**」；「credits」→「**点数**」；「10 轨起」等表述改为「拆成几轨」。
    - **§1.2 标题**由「Suno/Udio 为何无用」→「**「更便宜甚至免费」的平台为什么反而没用**」——把结论直接写进标题；结尾由「音频产物可用 AMT 救回来，见 §1.4」改为「拿不到 MIDI 时还有 §1.4 的转写这条路——所以『只出音频』只是**不能直连**，不是**没有价值**」。
    - **§1.3 表格列名**「官方显存要求 / Python / 其他依赖」→「**要多少显存 / Python / 还要装什么**」；「ISMIR '26」展开为「**音乐信息检索会议 2026 的成果**」；「需 AVX512 才有较好 CPU 性能」→「**CPU 想跑得快还需要 AVX512 支持**」；`conda` 括注「conda 环境」。
    - **§1.4**「复音与 pitch bend」→「**支持多个音同时响，也支持弯音**（pitch bend）」；「按平台选推理后端」→ 按系统列出（Linux/Windows/macOS），并把「真需要完整 TensorFlow」的例外单独说明。
    - **§2 表格**「专为 PC-88/98 的 YM2608（OPNA）设计的跨平台 tracker」→「**专门为 PC-88/98 的 YM2608（OPNA）做的**作曲软件（Win / macOS / Linux 都有）」；「MIDI → OPN2 / OPNA 渲染库」→「把 MIDI **渲染成** OPN2 / OPNA 声音的库」；「XM2151（OPM）音色转换」补全为 YM2151；「X68000 MDX 生态」→「**X68000 的 MDX 圈子**」。
    - **§3 推荐工作流**：流程图节点去术语（「MIDI → OPN2 / OPNA 渲染」改为「渲染成 FM 声音」）；要点「不要试图让 AI 直接产出 FM 补丁」→「**别指望 AI 直接给你 FM 音色，它没这个本事**」。
    - **§4 许可须知**：`SPDX 头` → 「**每个文件顶部的 SPDX 许可声明**」；补一句人话总结「GPL 的『传染』只对**代码**生效、不对**产出的数据**生效……**不必因此开源你的引擎**」。
  - **② 删除原 §5「选型陷阱」**：整段 4 条全部删除。**删除前逐条核对，确认无信息丢失**——「能生成≠能带走」（§1.2 已有完整表格与 Udio 条款原文）、「磁盘比显存更早成为瓶颈」（§1.3 note-box ① 已含）、「FamiTracker MIDI 输入/导入混淆」（§2.1 已有更详细的官网原文 + 版本号）、「榜单与搜索摘要不可信 / 只认官方主域名」（§1.2 note-box 已保留该结论）。**连带修正 §1.2 note-box 中指向已删 §5 的悬空引用**（「见 §5」→ 改为自足表述）。
    - **随段删除而消失的具体举例（如需保留请说明）**：`Amper Music` 2020-11-11 关停 / 被 Shutterstock 收购的案例；山寨站报价区间 **$6.4–$49**；虚构型号 **V9 / V10**；「优惠券码属灰产」等 4 个具体数字与 2 个专名。**这些是 §5 独有的，§1.2 只保留了「山寨站会报互相矛盾的价格、只认官方主域名」的结论本身。**
  - **⑧ 章节编号无需重排**：删除的是末节（§5），现为 §1（含 1.1–1.4）/ §2（含 2.1）/ §3 / §4，`§` 引用无悬空；**`mc07` 侧 6 处对 `mc06` 的引用（§1 / §2 / §3 + 按名引用「GM 音色 ≠ FM 音色」）因 `mc06` 编号未变而继续有效**（已按「章节号 / 标题 / 按名 / 整页」四种语义逐处校验通过）。
  - **⑧ 连带订正**：第六轮条目里的跨页引用计数写错（写 3 实为 4、写 5 实为 6），按 `AGENTS.md` §十「任何地方还留着一个已知错误的结论，就是未完成」就地订正，并标注订正轮次。
  - **第八轮验证**：`mc07` 163 行（原 170）；**106 条特征事实**改写前后校验全部保留（价格 `$0.06` / `$0.2` / `$0.7`、Premier 三档能力、`2025-10-29` Udio 下线与其条款原文、`$27` 未证实声明、Suno `$0` / 50 点 / v4.5-all、Udio `$0` / 3 首、`v4.5` 模型、显存 8/16/24 GB、`torch==2.3.0` / cuda 11.8、`AVX512`、`15.6 GB`、`128 维`、`Ableton Live 10.1`、FamiTracker `0.4.6` / `2015-02-04` / `0.4.3` / `2014-06-07` / `Removed MIDI import`、FamiStudio 音源型号 2A03·VRC6·VRC7·FDS·N163·MMC5·5E01、8 项工具许可、及各项许可标识）；23 类标签开闭配平；5 个相对链接全部可解析；`§` 引用 6 个无悬空；**AIVA 残留 0**；**「选型陷阱」字样 0**；**全站已无指向已删 §5 的引用**（顺带确认 `naiz-guildbook` 内无任何页引用旧文件名 `mc06-音频素材与FM通路.html`）；`pytest tools/tests/` **642 passed, 1 skipped**、`./start.sh fullaudit` **7/7 全绿**。**零引擎改动、不 bump 版本**（仍为 `0.3.021`）。

- **第七轮（`mc06` 改用平实语言，去程序员腔）**：用户指出「音频通路机制文档不要太偏向程序员，用更多的人的话去解释问题」。定位为**面向素材创作者**的文档，却整篇用实现语言写成。改写原则是**换说法、不换事实**——每个术语都改成人话，原义作为括号内的标准术语保留（便于检索与对专业读者）。
  - **开篇改为从问题切入**：原稿以「本页汇总…」开头；改为「你想给游戏做一首 BGM，于是要面对一个现实问题：PC-98 上有**三个能发声的部分**……其中一个**一次只能播一个声音**」，并给三条通路一个统一比喻「像三台互不相干的播放器」。
  - **§1「三条通路的硬件事实」→「三个能发声的部分」**：表格列名由「通路 / 硬件 / 通道数 / 要点」改为「部分 / 是什么 / 能同时播几个 / 一句话限制」；「没有这张卡就完全不可用」→「没装这张卡就完全没有这个通路」；「共享同一条 FIFO」→「共用这一条 FIFO」。关键澄清用粗体点出：**背景音乐该走 FM 是为了「不跟别人抢」，不是为了音质**。端口地址（`A4xx` / `0188h`）降级进一个标注「只给要翻手册的人」的补充框，正文不再被打扰。
  - **§2「格式对照：先纠正一个概念」→「音乐文件有哪几种」**：列名「本质 / 引擎侧代价」→「它到底装了什么 / 我们要做的事」。「音符、音色号、控制器的事件序列」→「一张**清单**：什么时候弹哪个音、用什么音色……**里面没有声音**」；「寄存器写流」→「一串『**往芯片的哪个旋钮上写多少**』的指令」；「MML 编译产物（字节码）」→「翻译出来的**机器码**」；「可读性与 diff 友好」→「纯文本、读得懂、好比对版本差异」。
  - **§3 标题由「原理：哪些转换做得到，哪些做不到」→「有两件事，一个做不到，一个做得到」**：`欠定的逆问题` / `适定问题` **先用人话讲清再括注术语**（「同一条波形可以由无数组不同的参数生成出来，所以**反推不出唯一答案**」/「音高检测……答案是**唯一的**」）。补上原稿没有的**因果句**「混为一谈，就会得出『AI 出的音频全都没用』这个错误结论」，点明这一节为什么值得读。
  - **§4「引擎侧方案对比」→「引擎要吃哪种音乐」**：方案名由「A. MIDI → YM2608 映射 / D. 离线渲成 WAV 走 PCM」改为「A. 让引擎认 MIDI / D. 桌面端先渲染成 WAV，走 PCM」；「复用现有 SMF 解析器」→「引擎本来就会读 MIDI 文件」；「逐条写 OPNA 寄存器」→「照着指令逐条设置芯片」；「工作量 / 保真度」→「费不费劲 / 还原度」。
  - **§5「引擎侧陷阱」→「容易踩的坑」**：「必须实现通道分配与抢占策略」→「得先定好哪个声部占哪个通道、挤不下时先牺牲哪个」；「若测试用的 PCM 是恒定幅度合成音」→「如果测试用的采样是恒定幅度合成的」；「鼓组建议用 FM + SSG 合成」→「更省事的做法是用 FM + SSG 自己合成鼓」。
  - **保留而非删除的术语**（作为括号补充，兼顾可检索性与准确性）：`FIFO`、`6 复音`、`欠定的逆问题`、`适定问题`、`SSG`、`Rhythm`、`ADPCM`、`patch`、`GM 音色`、`DDSP`。**以 50 条特征事实做改写前后校验，全部保留**（含 `A4xx` / `0188h–018Fh` / `0288h` / `2–55 kHz` / `8 种算法` / `YM2149` / `128 个 4 算子 patch` / `mml2mdx` / `pc98sndpmdtools` / `wav_convert.py` / 底鼓·踩镲·军鼓 / 恒定幅度·阻尼·衰减 等硬件与参数事实）。
  - **`mc07` 未改**：该页是选型对照表，术语（显存要求、依赖包、许可标识）本就是要比对的内容，不属「解释」性质。若用户同样希望它更口语化可另开一轮。
  - **第七轮验证**：`mc06` 91 行；23 类标签开闭配平；5 个相对链接（含 3 处跨页 mc07）全部可解析；`§` 引用 2 个无悬空；全文 AIVA 残留 0；**mc07 侧对 mc06 的 3 处引用（§1 / §3 /「GM 音色 ≠ FM 音色」）因编号未变而继续有效**（已核对）；`pytest tools/tests/` **642 passed, 1 skipped**、`./start.sh fullaudit` **7/7 全绿**。**零引擎改动、不 bump 版本**（仍为 `0.3.021`）。

<a id="c51"></a>
### 0.3.020 — 002 场景补 BGM + `voice`/`sound` 单通道争用根修 + 音频 key 登记守卫（devdoc 122）

> ⚠ **订正（`0.3.021` 第十三轮追加，AGENTS §十 四步路径第 3 步）**：本条目「BGM 制作管线的结论」一节所依据的 **devdoc 122 §5.2 已被推翻**——它推荐「导出 WAV 进管线」作为主出口，而该路与本文自身根因二（PCM 单通道、`voice`/`sound` 后到覆盖）**直接冲突**，且 `mc06` §3 方案 D 早已标注 `❌ 行不通`。**两处文档结论长期互斥而无人发现**。另有 SSG 通道数错、FM 音色「基本通用」过强、patch 数据许可断言无来源、`:213` 待研究项已收敛四处。**完整订正见 `devdocs/122` 头部 `⚠ ERRATA` 块（正文一字未改）与接替文档 `devdocs/123-MIDI转FM通路实现计划.md` §一**。

- **BGM 本地静音的定性（不是 bug）**：`nbook001.nb:3` 的 `bgm(){test1}` 写法正确、执行正常，但本环境**无 MPU-401**。证据链：`logs/serial_demo-a2.log:13` 的 `AUD WARN: no MPU-401 (BGM disabled, PCM unchanged)`（由 `core/engine/audio.c:338` 打印，紧随 `:334` 的 `g_mpu_ok = hal_audio_detect()`）→ `core/plat/hal_audio.c:51-60` 的探测（reset `0xFF` + UART `0x3F`，各等 ACK `0xFE`；`:41-49` 轮询 status bit7，最多 `MPU_PROBE_ITER 20000` 次即 `:38`）→ 该文件头注释 `:5-8` **早已预告此失败模式**（"an NP2kai build with MIDI disabled, the status port reads back 0xFF and the probe times out -> 0"）→ `audio.c:109-112` 把**每个** `bgm(){key}` 静默丢弃。宿主侧根因：`~/.config/wxnp21kai/wxnp21kai.toml` 有 `mpu98en = true` 但 **`mpu98dev = ''`**，且无 `/dev/snd/midi*`、无 `/dev/seq`、未加载 `snd-seq`/`snd_midi`、无 fluidsynth/timidity —— 与 `docs/B91:289` 既有声明（MIDI 等无法验证）一致。**属设计内降级，脚本不修。**
- **`voice(){hi}` 听不见的真因（与上一条根因完全不同）**：86 板只有**一条** PCM FIFO，`sound`/`voice` 共用 `pcm_play()`（`audio.c:185`）与单一 `g_pcm_buf`，后到覆盖先到（`docs/B92:38` 已写「后到覆盖」）。`hi.pcm`（rate code 4 = 11025 Hz，payload 5512 B = **0.50 s**）与 `ding.pcm`（rate 2 = 22050 Hz，8820 B = 0.40 s）在 `nbook001.nb` 中曾是**相邻两行**，而 `cmd_voice`/`cmd_sound` 皆非阻塞、**同一 pass 内背靠背执行**（§十四.6/§十四.7）⇒ `ding` 毫秒级内顶掉 `hi`，`hi` 实际发声 <1 ms。对照组：`chime` 后接 `char`/台词行（不碰 PCM 通道），能完整播完 —— 与实机「chime/ding 可闻、hi 不可闻」的报告完全吻合。
- **场景改动**：`projects/demo-a2/scene/nbook001.nb` 把 `sound(){ding}` 由第 12 行移至第 13 行（`ira(){Really?...}` 之后），使 `hi` 在对白页期间播完；`projects/demo-a2/scene/nbook002.nb:3` 新增 `bgm(){test1}`（置于 `bg(normal){homeday}` 后，与 001 同序 `sceneconf`→`bg`→`bgm`）。**002 无需收尾 `bgm(stop)`**：`scene_switch()`（`core/engine/nb.c:300`）每次切换调 `audio_stop_all()`，故 ① 001:23 的 `bgm(stop` 实为冗余（下一行 `scene(002)` 本就会停）② 002 的 BGM 不会漏进 `nbook003`/`nbook004`。
- **防呆（音频 key 登记）**：`tools/naiz_build/nb_validator.py:80-85` 只加载 `IMG`/`ANI`/`CG` 三类 name 集，**不校验音频 key** —— 未登记的 key 能一路通过 `build`，只在实机表现为一行 `BGM WARN: '<key>' is not a registered BGM asset`（`audio.c:117-120`），即 §九.6 所称「假通过比失败更危险」。新增 `tools/tests/test_audio_asset_paths.py::test_scene_audio_keys_are_registered`：遍历 `projects/*/scene/*.nb`，经 `naiz_lib.nb_line.parse_nb_line` 取括号负载（**不手搓 `split(',')`**，§十四.9 逗号语义单一实现；`bgm(stop)` 无负载故跳过），要求 `ASSETS.DB img_map` 存在 `name`+`type` 为 `BGM`/`SND`/`VC` 的对应行，失败时报 `file:line` + key + 期望 type。**负例已验证**：临时投放含 `bgm(){nosuchtrack}`/`sound(){alsomissing}`/`voice(){ghost}` 的场景文件，守卫如期变红并逐条定位，删除后复跑通过（守卫不生效等于没有守卫）。
- **BGM 制作管线的结论（WAV→FM 不可行）**：FM 是参数化模型、WAV 是任意波形，由 WAV 反推 FM 参数是**严重欠定的逆问题**（不同音乐可产生相同波形，同一波形对应无穷多种 FM 解释，无唯一解），**不存在可用的自动转换工具**。业界方向是反向：用 tracker 按 FM 音色作曲（FamiTracker 内置 YM2612/OPN2，与 PC-98 YM2608/OPNA 的 FM 核心同源）并**导出 WAV/MIDI**，从而**使音乐资产与引擎播放通路解耦**——这能切断「引擎无 FM 通路 → 做不出音乐 → 无法验证 → 一直卡住」的循环依赖。许可提示：GPLv2 工具**生成的音频数据不被传染**（GPL 只覆盖代码）；若日后自研 FM 播放器/MML 解析器须另找许可干净的参考。内容↔格式硬约束：**语音/音效必须 PCM**（FM 只能出「机器人音」），**BGM 理应 FM**（PC-98 原生即 FMP/PMD 用 OPM 出曲 + PCM 驱动出语音，见 `docs/refdocs/F01_sound_boards.md:108-110`），而**当前 HAL 无任何 YM2203/YM2608 端口访问**。**FM 作曲方法（格式选型 / tracker 资产入管线）明确留作下一步研究**，本轮只记录结论。
- **PCM 不可当 BGM 的三重约束**（记录于 devdoc 122 §四.3，本轮不做实现）：① 单通道硬伤——BGM 若循环占用该通道，第一个 SE 就掐断且不自动恢复（`hi`/`ding` 即其最小复现）② 体积/内存——8bit 单声道 60 s 循环 44.1kHz ≈2.5 MB / 22.05k ≈1.26 MB / 11.025k ≈646 KB / 4.13k ≈242 KB，且 `audio.c:204` 的 `farchive_read_alloc` 把整条 malloc 进堆（峰值堆 = 曲目 + 其余全部，实际边界取决于 VEM486 DPMI，**须实测**）③ 代码缺口——`hal_pcm_play(..., loop)` 已支持 loop（`hal_audio.c:131`），但 `pcm_play` 硬编码 `loop=0`（`audio.c:224`）且脚本 `sound(){<key>}` 无 flags 参数。
- **新文档**：`devdocs/122-BGM本地静音根因与音频通路取舍.md`（完结）。含症状→判定→根因两段独立证据链、三通路与内容适配表、WAV→FM 结论、本轮落地、未决项 6 条、踩坑清单 5 条。按 §十 逐条核对并校准**全部 41 处 `file:line` 引用**（含承重引用的内容抽查，不止「行号可解析」）——注意 `tools/tests/test_devdoc_refs.py` 的白名单**只覆盖 devdoc 118/119/120**，本文不在其内，故引用正确性由本次人工核验保证。
- **文档同步**：`AGENTS.md` §十四新增「音频通路（PCM 单通道，devdoc 122）」小节（7 条：三通路分流表、`voice`/`sound` 不得相邻、BGM 静音先看 `AUD MPU OK`、BGM 不可走 PCM 循环、内容↔格式硬约束、WAV→FM 不存在、`scene()` 停全部音频、音频 key 须登记）；`docs/B92` 的 `bgm`/`voice` 两行补注 MPU 降级与相邻覆盖的实测坑；`AGENTS.md` 头部当前版本/最新条目更新至 `0.3.020`/`c51`。
- **零引擎改动**：`AUDIO.DAT` 与上轮基线 **sha256 逐字节一致**（`99599fbd…4863`，场景改动不触及音频资产），本轮唯一代码产物是测试；`SCENE.DAT` 因场景编辑如期更新。版本统一 bump 至 `0.3.020`（animatest / demo-a2 同步）。

验证：`make -C core` + `find core -maxdepth 1 -name '*.err' -size +0`（空）、`pytest tools/tests/` **642 passed, 1 skipped**（改前 641；+1 为本轮新增守卫）、`./start.sh fullaudit` **7/7 全绿**（含 nb_validator 全项目、symbol_audit A/B `--gate`、`make` 0 err / 0 warn）、`./makegame.sh build demo-a2 && ./makegame.sh make demo-a2`（HDI 重新注入，`disks/demo-a2.hdi` 23:07:56 晚于 `engine.exe` 23:06:55）、`strings games/demo-a2/engine.exe | grep 0.3.020` 确认引擎确实编入新版本宏（`bump_version` 后必须经 `build` 重生成 `core/engine/nb_config.h` 再重编，否则 `test_version_sync` 红灯——此为 §八 五禁之二「只 build 不 make 跑旧引擎」的同类陷阱）。实机复验（可选）：串口 `PCM start 'hi'` 与 `PCM start 'ding'` 不再相邻；BGM 仍打 `BGM WARN: 'test1' ignored (no MPU detected)`（预期）。

<a id="c50"></a>
### 0.3.019 — 音频源资产迁至 `assets/<项目>/`（BGM/SE/voice 三目录统一）+ guildbook 音频页 stub 描述订正

- **动机与依据**：`projects/<项目>/{bgm,se,voice}/` 是纯源目录，从不进 `games/<项目>/`、也不注入 HDI（`build_game.py` 只搬 `scene/*.nb` / `i18n/*.txt` / `IMAGE.DAT` / 字库 / `engine.exe`）；运行时只 `farchive_open("AUDIO.DAT")`（`core/engine/audio.c:24,323`），键名表由 `export_asset_table.py:178-213` 生成且**只 `SELECT id, name`、完全不读 `filename` 列**。故目录位置对引擎零影响，唯一耦合点是 `pack_audio.py` 的路径解析。`assets/<项目>/` 早已是位图源（`images.map`）与 `anim/` 帧素材的所在，音频源并入使「源素材在 assets、构建产物与脚本在 projects」成为无例外的单一约定。
- **封装（§九.10 先借后造）**：`tools/naiz_lib/__init__.py` 新增 `project_assets_dir(project_dir, repo_root=None)` —— 复用既有 `PROJECT_ROOT`，按项目名推导 `assets/<项目>/`，`repo_root` 供测试覆写；成为「音频源住哪」的唯一事实源，`pack_audio` 与 `wav_convert` 共用，不各自拼路径。
- **`pack_audio` 严格单源**：`tools/naiz_audio/pack_audio.py` 签名加 `assets_dir=None`（默认走 `project_assets_dir`），路径解析由 `project_dir` 改为 `assets_dir`，**不在项目目录回落**；缺文件时报错额外打印期望源根（原先只报拼错的路径，等于让人在错的目录里找）。开头打印一次解析到的源根，保持可观测。
- **`wav_convert` 写入口径归一**：`register_asset()` 加 `assets_dir` 参数，目标必须落在 `assets/<项目>/` 内（越界 `exit 1`，而不是留到 build 时才报「文件缺失」），入库 `filename` 归一为相对该根的 posix 路径（`bgm/x.mid` / `se/x.pcm` 形态）。
- **迁移**：`git mv` 三个目录共 4 文件（`bgm/test1.mid`、`se/chime.pcm`、`se/ding.pcm`、`voice/hi.pcm`），git 记为纯 rename。**`ASSETS.DB` 零改动** —— `filename` 值本就是相对路径（`bgm/test1.mid` 等），只是相对根换了；`id` / `type` / `name` 全不动。
- **防呆**：新增 `tools/tests/test_audio_asset_paths.py`（6 项）—— ①每个 `BGM/SND/VC` 行都能在 `assets/<项目>/` 解析到实际文件 ②`projects/*/` 下不得再有 `bgm` / `se` / `voice`（旧位置防回流，参数化 3 项）③`name` 非空且 `to_dos_name` 截断后互异（把 `pack_audio` 的运行期碰撞检查提到仓库级）④`project_assets_dir` 推导不漂移（含 `repo_root` 覆写路径）。另在 `test_audio_toolchain.py` 补 2 项：`pack_audio` 缺源文件必须 `SystemExit` 且不产出 `AUDIO.DAT`；`register_asset` 越界目标必须拒绝且不写库。
- **测试 fixture 迁移（诚实性说明）**：`test_audio_toolchain.py` 的 `_make_project` 原先把载荷写在项目目录下，改到 `tmp_path/assets/proj/` 并把 `assets_dir` 透传给 5 处 `pack_audio` 调用；`test_wav_convert_register_asset_idempotent` 改传真实路径并断言归一后的 `se/ding.pcm`。**改动前先验证过这 3 个旧测试确实会红**（新源码 + 旧 fixture → `3 failed`），确认它们真的在断言旧布局，而不是被顺手改绿。
- **顺带订正 guildbook 已知错误结论**：`naiz-guildbook/pages/sc10-audio.html` 原文称三个命令「当前实现为平台占位（stub），音频键会经 HAL 转出，暂不产生实际声音」，与 0.2.115 起的真实实现矛盾（AGENTS §十：任何地方还留着一个已知错误的结论就是未完成）。按代码事实重写为：BGM = SMF 运行时解析 → OPN/OPM 音源（16 通道，CC7 0–127 即时音量），SE/voice = `.pcm` 流式推 YM3433B FIFO（A466 衰减 0–15、方向相反、两者共用一条 PCM 通路故只有一档）；补三开关精确切断、BGM 循环 / SE·voice 不循环、资源登记（源在 `assets/<项目>/`、TOC 名须 8.3 互异）、以及「key 不得翻译 + `i18n_gen` 空值常驻的已知瑕疵 + WARN 诊断不崩溃」。按 §十三 约定 touch 全部 guildbook 文件。
- **文档同步**：`docs/B91 §1` 目录树**此前完全没有 `assets/` 条目**，补齐（`common/` + `<项目>/{images.map,png,setting,bgm,se,voice,anim}`，标注「源素材，不进部署树、不注入 HDI、构建只读」）；`docs/B90` 音频打包 / WAV→PCM / 测试 MIDI 三行补源目录与归一规则，并新增「音频源目录」一行登记 `project_assets_dir`；`docs/B92` 格式表与管线图补 `assets/<game>/{bgm,se,voice}/` 起点；`AGENTS.md §二` 新增「源素材在 assets/」小节（含素材对照表、8.3 豁免澄清、防呆索引）。
- **零运行时影响的硬证据**：改后 `build` 输出的 `games/demo-a2/AUDIO.DAT` 与改前基线 **sha256 逐字节一致**（`99599fbd…4863`，打包器自身也报「AUDIO.DAT 未变化（4 assets）」），`core/engine/nb_asset_table.h` 与改前快照 `diff` 为空 —— 即引擎、头文件、HDI 布局零改动。日志新增 `audio sources: <repo>/assets/demo-a2` 一行以证明解析到的根。

验证：`make -C core` + `find core -maxdepth 1 -name '*.err' -size +0`（空）、`pytest tools/tests/` **641 passed, 1 skipped**（改前 630 passed；+8 为本轮新增，3 项旧音频测试由红转绿）、`./makegame.sh build demo-a2 && ./makegame.sh make demo-a2`（HDI 重新注入成功）、`./start.sh fullaudit`。`build_game.py` 的改动刻意做成**行数中性**（docstring 保持单行）：首次写成多行 docstring 使后续行号整体位移 +4，触发 `test_devdoc_refs.py` 红灯并波及已完结 devdoc 118/119/120 的 `file:line` 规格，按 §十「校行号」回滚改为零位移，从源头避开对完结文档的改动。版本统一 bump 至 `0.3.019`（animatest / demo-a2 同步）。

<a id="c49"></a>
### 0.3.018 — 翻译/脚本文本长度上限收口（5 对话框容量）+ tr 截断 fail-loud + 容量守卫（devdoc 121）

- **容量上限抬升（单一事实源）**：`core/lib/tr.h` 新增 `TR_KEY_LEN 1024`、`TR_VAL_LEN 1280`、`TR_LINE_MAX`，`tr.c` 移除本地 128/256 定义改用 tr.h，行缓冲改 `char line[TR_LINE_MAX]`；`core/engine/nb_internal.h` `NB_LINE_MAX 256→1152`；`core/engine/nb_dialog.c` `dialog_text_buf[1024]→[TR_VAL_LEN]` 并补 `tr.h` include；`core/engine/layer_dialog.c` `dialog_render_text[1024]→[TR_VAL_LEN]` 并补 `tr.h` include（5 个对话框容量模型：key 855B→1024、value 1260B→1280）。
- **fail-loud（静默→响亮）**：`core/lib/tr.c` 增 `tr_trunc_count`，`tr_init()` 重置、`load_file()` 在 key/value/行未换行/条目超限四处计数，新增 `tr_get_truncations()` 导出至 `tr.h`；`core/engine/nb.c::nb_set_lang()` 于语言切换后（eng 回退合流）检查 `tr_get_truncations()>0`，输出 `WARN: %d translation entries truncated` 并 `hal_log("WARN: translation truncated\r\n")`。
- **容量守卫测试**：新增 `tools/tests/test_tr_capacity.py`（6 项），从源码读取常量断言 `TR_KEY_LEN≥1024`、`TR_VAL_LEN≥1280`、`NB_LINE_MAX≥1152`、两 dialog 缓冲≥TR_VAL_LEN、i18n 各行 key/val < 限额、`.nb` 行 < NB_LINE_MAX；先红后绿自证，配合现有容量无关守卫形成双层保护（pytest 全绿）。
- **文档对齐**：修订 `devdocs/120-*.md` 中对 `tr()` 空值注释的行号引用（`148-151`→`168`），`tools/tests/test_devdoc_refs.py` 白名单同步修正；`AGENTS.md` 头部当前版本/最新条目更新至 `0.3.018`/`c49`；版本统一 bump 至 `0.3.018`（全项目同步）。

验证：`make -C core` + `find core -maxdepth 1 -name '*.err' -size +0`（空）、`tools/tests/test_tr_capacity.py` + `test_devdoc_refs.py` 18 passed、`./start.sh fullaudit` 7/7 全绿（symbol_audit A/B --gate 通过）、`build && make` demo-a2 HDI 新鲜。按 devdoc 121 §八完成实现序列 1–4/7–9；其余实机验证（A/B `--forbid`）非本轮 CI 环境要求。



## 版本索引

| 条目 |
|------|
| [0.3.026 — 引擎按 8.3 短名解析音频键（str_toc8）：修 AUDIO.DAT 截断名失配 + 全素材面同名风险审计](#c57) |
| [0.3.025 — demo-a2 换用正式 BGM：场景 001/002 melody_town、003/004 icy_garden（去掉 test1/test2）](#c56) |
| [0.3.024 — 资产市场 `sync` 子命令：git blob-sha 差分同步（增/改/未变/可选 `--purge` 清孤儿）](#c55) |
| [0.3.023 — devdocs/124 MIDI→FM 通路 S6：默认音色内容（15 族 FMP patch + GM→族映射 gm_map 数据）](#c54) |
| [0.3.022 — devdocs/123 MIDI→FM 通路 S0–S5 代码落地（fmopn/fmseq 主机可穷举 + hal_fm_* 端口层 + 音频引擎 FM 后端）](#c53) |
| [0.3.021 — guildbook 新增 mc06「音频素材与 FM 通路」（格式 / AI 平台 / 软件工具集 + 引擎方案对比）](#c52) |
| [0.3.020 — 002 场景补 BGM + `voice`/`sound` 单通道争用根修 + 音频 key 登记守卫（devdoc 122）](#c51) |
| [0.3.019 — 音频源资产迁至 `assets/<项目>/`（BGM/SE/voice 三目录统一）+ guildbook 音频页 stub 描述订正](#c50) |
| [0.3.018 — 翻译/脚本文本长度上限收口（5 对话框容量）+ tr 截断 fail-loud + 容量守卫（devdoc 121）](#c49) |
| [0.3.017 — 全部剧情脚本 9 语翻译补齐（28 键 ×9 语 0 空值）+ `Ira,not Neon` 转义标签入表](#c48) |
| [0.3.016 — NB 字段逗号转义 `\,`（三处实现同步）+ 常用问题选项归类 sys/game + `tr()` 守卫去注释误判](#c47) |
| [0.3.015 — 角色名 9 语种补全 + `[LOCKED]` 系统键缺失与 ORPHANED 陷阱 + 字形覆盖守卫](#c46) |
| [0.3.014 — settings.txt 废止 / config.toml 单一配置源 + 启动菜单选繁体中文仍进英语根修（devdoc 120）](#c45) |
| [0.3.013 — i18n 译文宽度守卫：4/9 语言行标签 + 5 处值标签曾被静默裁剪（devdoc 119 §3.4/§5.1）](#c44) |
| [0.3.012 — devdoc 118 规格订正 + 文档一致性回归守卫 `test_devdoc_refs.py`（devdoc 119）](#c43) |
| [0.3.011 — 玩家偏好分家 USER.CFG + 游戏内设置扩展 7 行（三开关/双音量/阅读进度）+ 86 板 PCM 寄存器 refdoc（devdoc 118）](#c42) |
| [0.3.010 — 实机验证五禁写入 AGENTS + HDI 新鲜度双守卫 + 守卫自证不变量测试](#c41) |
| [0.3.009 — 单页对白不再重复 arm 打字机：CG 后首句首击即翻页（devdoc 117）](#c40) |
| [0.3.008 — 输入边界收口为单一 helper + anim 幽灵唤醒门控 + 阻塞元数据死标志标注（devdoc 116）](#c39) |
| [0.3.007 — 图片调色板不再侵占引擎 chrome 槽 248–255：Back 按钮跟随全局 btnstyle + 角标只显编号](#c38) |
| [0.3.006 — CG 画廊三修：真实缩略图（构建期生成）+ 预览返回调色板保序 + footer 统一](#c37) |
| [0.3.005 — 004 结局章末尾插入 cg01 + Neon 夸 Fei / Fei 回「色猫」七句对白](#c36) |
| [0.3.004 — 设置菜单九语言译文补齐：速度档标签入表 + tr() 化](#c35) |
| [0.3.003 — 游戏内设置菜单场景：Text Speed 迁出开机菜单 + settingmenu 落地](#c34) |
| [0.3.002 — 资产市场交互菜单启动清屏一次（TTY 守卫）](#c33) |
| [0.3.001 — 0.3 开版（minor 进位）](#c32) |
| [0.2.148 — 0.2 收官：devdocs 68–115 归纳为 0.2 版开发文档总结](#c31) |
| [0.2.147 — guildbook 新增两篇：cf07 图片登记 + tool-market 资产市场](#c30) |
| [0.2.146 — 删除旧背景 seasidebg/splbg（4 层清理）](#c29) |
| [0.2.145 — 新图 cover 全屏 + images.map 英文选项注释](#c28) |
| [0.2.144 — demo-a2 新增 4 图登记入库（3 背景 IMG + cg01 CG）](#c27) |
| [0.2.143 — 市场下载同名跳过 + `--force` 逃生口（market.py）](#c26) |
| [0.2.142 — 菜单增量 blit 跨行距拷贝根修 + VRAM 紧凑缓冲契约审计（devdoc 115）](#c25) |
| [0.2.141 — Special 菜单视觉修正：Back 文字截断根修 + 行按钮缩半居中（devdoc 114 反馈轮）](#c24) |
| [0.2.140 — Special 菜单落地：LOAD 范式全屏列表 + 菜单归属场景收口（devdoc 114）](#c23) |
| [0.2.139 — 资产市场工具落地：整包下载器 market.sh（独立 naiz_assets 仓库）](#c22) |
| [0.2.138 — 光标移动残影根治：splice 只进一次性书写副本，持久合成缓冲不烘烙（devdoc 111）](#c21) |
| [0.2.137 — 光标写入全程零缺窗：对话框合成缓冲预拼光标（devdoc 110）](#c20) |
| [0.2.136 — 光标揭示顿闪消除：写后直绘 + 不透明矩形快路径（devdoc 109）](#c19) |
| [0.2.135 — 软件光标层契约落地 + 对话框抹字根因收口（devdoc 108）](#c18) |
| [0.2.134 — 虚拟时钟下沉 HAL smooth 单一事实源 + 动画/BGM 时钟隐患收口（devdoc 107）](#c1) |
| [0.2.133 — 打字机逐字节拍去抖落地（devdoc 106 方案 A+）](#c2) |
| [0.2.132 — 串口工具链三项修复：残留清理 + 强制 --start + slave_fd 全开 + SERTEST.COM 端口直写](#c3) |
| [0.2.130 — 打字机墙钟兹帧节拍化](#c4) |
| [0.2.131 — 打字机墙钟改 DOS 系统时钟](#c5) |
| [0.2.129 — 打字机墙钟端口根修](#c6) |
| [0.2.128 — 打字机墙钟计速根修](#c7) |
| [0.2.127 — 打字机末页对白不显示根修](#c8) |
| [0.2.126 — 移除 demo-a2 CG 演示引用 + 引擎 CG_COUNT=0 编译防御](#c9) |
| [0.2.125 — 打字机文字落地（devdoc 105）](#c10) |
| [0.2.124 — nb_validator V1–V4 落地（devdoc 104）](#c11) |
| [0.2.123 — devdoc 103 独立小项落地](#c12) |
| [0.2.122 — 显示 op 化改造（devdoc 103 阶段 2）](#c13) |
| [0.2.121 — 交互收口与存档请求收敛（devdoc 103 阶段 1）](#c14) |
| [0.2.120 — 菜单 UI 整合落地（devdoc 102）](#c15) |
| [0.2.119 — powered 资产归位 `common/logo/` + 资产键统一](#c16) |
| [Bug 修复状态（R1–R30 综合摘要与历史子条目）](#c17) |

---

<a id="c48"></a>
### 0.3.017 — 全部剧情脚本 9 语翻译补齐（28 键 ×9 语 0 空值）+ `Ira,not Neon` 转义标签入表

**起因**：0.3.016 落地段内逗号转义后复核 `demo-a2` 的 `game_<lang>.txt`，发现剧情文本除韩文外**全为空**——9 语种中 8 语种的对白 / 旁白 / 章节标题 / 问题标题全部静默回落英文（`tr()` 对空值与缺键同样回落，这正是 AGENTS §八「静默失败」类）。

**1. 剧情文本 9 语补齐**

`game_<lang>.txt` 的 28 个故事键（对白 / `host` 旁白 / `sceneconf` 章节标题 / `question` 标题与选项标签）逐语翻译：chi / cht / jpn / fre / ger / ita / spa / por 八语种此前为空、本次补齐，韩文补新键。角色名按各语正字法与 `role_<lang>.txt` 保持一致（菲/艾拉/尼昂、フェイ/イラ/ネオン、페이/이라/네온、`Néon`/`Neón`…），**句内出现的角色名同样本地化**（如 `Good Morning,Fei.` → おはよう、フェイ。）。

**2. 音频资源键必须留空**

`sound(){chime}` 等 4 键（`chime`/`ding`/`hi`/`test1`）是资产名，`cmd_sound`/`cmd_bgm`/`cmd_voice` 不经 `tr()`、直接传给音频后端，翻译它们会让引擎去找不存在的音频文件。留空即按原名播放。**已知小瑕疵（本次未改）**：`i18n_gen.extract_texts()` 会把它们当可翻译键提取（与 `char/bg/cg` 的排除清单不同），故它们会以空值形式常驻 `game_<lang>.txt`。

**3. `Ira,not Neon` 新键与 `Ira` 旧键清理**

`nbook002.nb` 的问题选项标签由 `Ira` 改为 `Ira\,not Neon`（转义逗号）后，`i18n_gen` 保留了 `# ORPHANED: Ira=`；本次随内容重置清除，并补 `Ira,not Neon` 9 语译文。

**验证**：9 语 `game_*` **0 空值 / 0 ORPHANED**，`role_*`/`sys_*` 亦 0 空值；`i18n_gen` 重跑 md5 不变（幂等，键与引擎 `tr()` 逐字节一致）；`./makegame.sh build demo-a2` 按新语料重建 9 语 CJK 字库、**0 缺失字形 WARN**；`./makegame.sh make demo-a2` 注入 HDI（29 new / 3 updated / 32 total）；pytest **640 passed, 1 skipped**。`bump_version` 0.3.016 → 0.3.017。

---

<a id="c47"></a>
### 0.3.016 — NB 字段逗号转义 `\,`（三处实现同步）+ 常用问题选项归类 sys/game + `tr()` 守卫去注释误判

**起因**：`question()` 的选项段是 `label,var,op,delta` 逗号分隔，标签本身需要逗号（如人名带称号 `Ira, Jr.`）时无处安放——`nb_next_field()` 用 `strchr(p, ',')` 一刀切，标签被截断、后续字段全部错位。

**1. 字段转义 `\,`（引擎 + 提取器 + 校验器三处同步）**

- 引擎 `core/engine/nb_commands.c: nb_next_field()`：定位分隔符时跳过每个反斜杠对，拷贝时折叠 `\,`→`,`、`\\`→`\`，其它 `\x` 原样保留（`C:\path` 不被吞）；同时**新增字段首尾空白裁剪**，修好一处既存分歧（此前引擎保留 `"Yes  "` 而 `i18n_gen` 已 `.strip()`，`Yes ,v` 会静默查不到译文）。
- 新增 `nb_has_field_delim()`（C）与 `naiz_lib.nb_line.has_field_delim()`/`option_fields()`/`raw_fields()`（Python），把「是否还有未转义逗号」这一探测收口为单一 helper；`nb_scene.c` 三处裸 `strchr(',')`、`nb_validator.py` 两处 `split(',')` 全部改走它，消除与 `nb_next_field` 的语义分叉。
- `i18n_gen.extract_texts()` 的问题段标签提取改用 `next_field()`，使提取出的键与引擎 `tr()` 查的键逐字节一致（否则译文静默失效）。
- **问题标题（argv[0]）不参与逗号切分**，其中逗号是字面量、无需转义——已在 `i18n_gen` 注释与 B92 文档固化。

**2. 常用问题选项归类 sys/game**

`Yes`/`No`/`OK`/`Cancel`/`Back` 等 14 个通用词进 `COMMON_QUESTION_OPTS`，由 `i18n_gen` 归入 `sys_<lang>.txt`（跨场景复用）；问题标题与非通用答案仍归 `game_<lang>.txt`（剧情内容）。`demo-a2` 的问题更新为 `Go with whom?;Ira,...;Neon,...`，`Go?` 退为 ORPHANED、`Ira`/`Neon`/`Go with whom?` 补 9 语种译文。附带的意外收益：韩文答案由旧的 `응/아니` 统一到系统菜单既有语域 `예/아니오`。

**3. `tr()` 字面量守卫去注释误判**

`test_user_cfg_settings.py::_engine_tr_literals()` 原样扫描源码，注释里出现的 `tr("…")` 会被当成真实调用而误报。新增 `_strip_c_comments()`（识别字符串/字符字面量、`//`、`/* */`）后再扫描，守卫不再被注释文本左右。

**验证**

- 新增 `tools/tests/test_nb_field_escape.py`（36 项）：镜像 vs C 源逐项对齐、转义/未转义/双反斜杠/未知转义/空白、问题标题保留逗号、常用词归属、validator 接受合法转义且仍拒绝未转义/字段不足/坏变量/真空白、scene 目标解析。
- 实机（NP2kai，临时插桩后已还原）：`question-label[0]: raw='Ira, the cat' tr='イラ, 猫'`——`\,` 正确还原且 `tr()` 命中键并渲染含逗号译文；`interact: keyboard sel=0` 选中后剧本推进到 `exec[7]`。探针 `--clicks 0/按键` 下报 `INPUT_NOT_SAMPLED`，该门控只认主对白分支的 `[INPUT] Key confirmed`，不覆盖 `ui_interact` 自建循环，故不以探针 PASS 为据。
- `make -C core` + `core/*.err` 全空；pytest **640 passed, 1 skipped**；`.err` 诊断规则照旧。
- `bump_version` 全部项目 → 0.3.016。
- 文档同步：`docs/B92-NB脚本命令参考.md` 新增「字段转义（逗号）」节；guildbook `sc08-question.html`（新增 §1.1 转义 + §3 含逗号示例）、`sc04-scene.html`（字段转义说明）、`sc01-NB剧本概述.html`（格式约定）三页同步，并按 B91 §1 约定 `touch` 全部 guildbook 文件。

---

<a id="c46"></a>
### 0.3.015 — 角色名 9 语种补全 + `[LOCKED]` 系统键缺失与 ORPHANED 陷阱 + 字形覆盖守卫

**起因**：0.3.014 修好语言链路后实机复核，发现两件独立的事——（a）保存菜单译文其实**早已 9 语种齐全**（含 `Overwrite Slot %d?`），无需补；（b）**角色名一个都没翻**，`demo-a2` 的对白说话人名在所有语言下都回落英文。

**1. 角色名补全（8 语种，韩文原本已有）**

`characters.json` 的 `fei`/`ira`/`neon` 三个键，此前 `role_<lang>.txt` 只有 `role_kor.txt` 有值（페이/이라/네온），其余 8 语种全空。补齐：jpn フェイ/イラ/ネオン，chi 与 cht 菲/艾拉/尼昂，拉丁语族保留专有名词原形（fre/ger/ita 的 `Fei`/`Ira` 不变，仅 `Neon` 按各语正字法改为 `Néon`/`Neón`）。

**2. `[LOCKED]` 此前根本不在译文系统里**

`nb_cggallery.c` 用 `tr("[LOCKED]")` 渲染未解锁 CG 的格子标签，但该键**既未登记进 `i18n_gen.py` 的 `SYSTEM_UI_KEYS`，也不在任何 `sys_*.txt`**——即 9 语种全部回落英文 `[LOCKED]`。按 AGENTS §14.3 补登记 + 9 语种补译文（chi/cht `[未解锁]`/`[未解鎖]`、jpn `[ロック]`、kor `[잠김]`、fre `[VERROUILLÉ]`、ger `[GESPERRT]`、ita `[BLOCCATO]`、spa/por `[BLOQUEADO]`）。

**这里的真陷阱**：不登记进 `SYSTEM_UI_KEYS`，则下次 `i18n_gen` 重生成会把它当 `# ORPHANED` **注释掉**——补了译文也会在下一次生成时静默失效。已实测：`i18n_gen` 重跑后 `sys_*.txt` **零差异**。

**3. 根因级守卫（4 项，全部自证）**

原 `test_new_ui_keys_registered` 只检查一份**手工维护的清单** `NEW_UI_KEYS`——没人记得加的键就永远漏掉，这正是 `[LOCKED]` 长期缺失却无人察觉的原因。改为**从 C 源码发现** `tr()` 字面量：

- `test_every_engine_tr_literal_is_registered` —— 扫 `core/**/*.c` 的 `tr("…")`，全部须在 `SYSTEM_UI_KEYS`；
- `test_every_engine_tr_literal_is_translated_in_every_language` —— 须**存在且非空**（整键缺失也报，因为缺失正是 ORPHANED 的产物；`tr.c` 对缺失与空值同样回落英文）；
- `test_every_character_name_translated_in_every_language` —— `role_<lang>.txt` 键集须等于 `characters.json`，且无空值；
- `test_deployed_font_covers_translations` / `test_deployed_font_not_older_than_translations`（`test_cjk_font.py`）—— **出货字库必须覆盖出货译文**：解析 `games/<game>/CJK_<LANG>.DT` 的 range 表（`'CJKF'` + LE u16 区间数 + `count×(start,end,offset)`），核对每个译文值里的非 ASCII 码点都有字形，且字库不比译文旧。这是「缺字 → 画成空框、不报错不告警」那类静默失败的常态化拦截（AGENTS §11）。

四项均做了失败注入自证（摘 `SYSTEM_UI_KEYS` / 清空译文 / 删整键 / 塞字库没有的字 / 把字库时间戳改旧），逐个转红后还原。**其中「删整键」第一次注入时并未转红**——守卫当时只查「存在但为空」，漏了「整键不存在」这个更可能的形态，已补。

**4. `[LOCKED]` 译文宽度**

`[LOCKED]` 画在 `GAL_CELL_W`(144) 宽的画廊格子里，起点 `x+30`。按 `text_width()` 的字节高位规则实测 9 语种全部放得下（最宽法语 `[VERROUILLÉ]` 104px，界 114px）。已按 `test_i18n_label_width.py` 同规格加守卫（常量与几何全部从 `nb_cggallery.c` / `font.h` / `cjk.h` **读取**，不从 C 源码正则抠数字），并带失败注入自证。

**5. 顺带发现，未改（需许可）**

`nb_cggallery.c:173` 的 `draw_text(…, x + GAL_CELL_W - 30, …)` 把**绝对格坐标**传给了 `max_width`，而 `draw_text()` 内部按 `cx + 8 > x + max_width`（`x` = **文本自身**起点）使用它——坐标系不一致。故实际限宽是 `GAL_CELL_W - GAL_LABEL_INSET + cell_x`（首列 134px，且逐列不同），而非设计意图的 84px。当前所有译文都在两种解释下放得下，故不影响输出；但若有人「修正」这个调用而不同步缩短法语/西语/葡语译文，就会真的裁字。属显示管线（AGENTS §11 变更规则），**未擅自修改**，留待决策。另：`text_blackletter` 开启时拉丁字符按 16px 计（非默认），法语 `[VERROUILLÉ]` 将达 192px 溢出格子。

**5. 顺带堵住的版本假通过**

`bump_version` 只改 `config.toml`，而 `nb_config.h` 是 `export_config.py` 的**构建产物**、由 `make -C core` **不重新生成**。实测：`bump_version` 到 0.3.015 后跑 `make -C core`，`NAIZ_VERSION` 仍是 `"0.3.014"`，而 `test_version_sync.py` 照样全绿——因为它读的是 `config.toml`，从不读生成的头。已在 `test_version_sync.py` 加 `test_generated_nb_config_matches_project_version`（+ 自证），把「引擎报的版本号」与「项目版本号」绑在一起。

**验证**：`make -C core` 0 错 0 警（查 `core/*.err`）；pytest **604 passed, 1 skipped**（+27）；`./start.sh fullaudit --no-make` 7 步全绿；`tools/` 下 120 个 `.py` 语法全通过；`i18n_gen` 重生成后 `i18n/` 目录零差异；9 语种出货字库对出货译文**零缺字**；NP2kai 实机 `--boot-arrows 3 --boot-only` 确认 `[LANG] nb_set_lang lang='cht'`。`bump_version` 0.3.014 → 0.3.015。

---

<a id="c45"></a>
### 0.3.014 — settings.txt 废止 / config.toml 单一配置源 + 启动菜单选繁体中文仍进英语根修

**起因**：实机反馈「启动菜单选繁体中文，进入正式游戏仍是英语」。**根因是访问器不对称**——`settings_get_lang()` 读 `g_settings.lang`（`settings.txt`，项目默认），而 `settings_set_lang()` 写 `g_pref.lang`（`USER.CFG`，玩家偏好）。两者永不相遇：开机菜单把 `lang=cht` **正确落盘**，但没有任何代码读它。更深一层，`lang` 这个键名**同时存在于两个归属相反的文件**，使 getter/setter 可以各自绑定不同副本且互不报错。

**这不是补丁能解决的**：只要项目配置仍经由运行时文件传递、由 build 无条件覆盖，同型缺陷就还会长出来。故按 devdoc 120 拆解为「项目配置 / 玩家偏好」两条正交通道。

**结构改动**

- `settings.txt` **彻底废止**。项目配置只存于 `projects/<game>/config.toml`，经 `tools/naiz_build/export_config.py` 生成 `core/engine/nb_config.h` 的 `NAIZ_VERSION` / `NAIZ_DLGSTYLE` / `NAIZ_BTNSTYLE` / `NAIZ_BLACKLETTER_TITLE` / `NAIZ_BLACKLETTER_DIALOG` / `NAIZ_DEFAULT_LANG` **编译进引擎**，运行时零解析。样式键由 `[style]` 拆为 `[dialog] style` / `[button] style`；项目语言默认改用 `[i18n] default_lang`。
- `USER.CFG` 成为**全系统唯一的运行时可写文件**（`prefs_load()` / `prefs_save()`）。`build` 不再注入任何项目键，只 `stale_settings.unlink()` 剪除部署树里的死 `settings.txt`（**只许 unlink，不许写**）。
- 重命名：`settings.c/h` → `prefs.c/h`，`settings_menu.c/h` → `bootmenu.c/h`，`settings_load/save` → `prefs_load/save`，全部 `settings_get_*` / `settings_set_*` → `prefs_get_*` / `prefs_set_*`，`SETTINGS_*` 宏 → `PREFS_*`。

**行为**：玩家在开机菜单确认语言后即固化，`default_lang` 后续变更不影响该玩家（删除 `USER.CFG` 恢复出厂默认）。

**验证**

- `make -C core` — 0 errors, 0 warnings。
- `pytest tools/tests/` — **575 passed, 1 skipped**。
- 导出器负例：`default_lang` 无译文、非法语言码、`button.style=9` 均明确报错并 exit 1。
- **守卫自证**：把 `prefs_get_lang()` 改回读另一个字段后，`test_audio_settings_invariants.py` 立即 2 red（`test_prefs_lang_getter_and_setter_share_one_field` / `test_prefs_lang_falls_back_to_project_default`）——守卫确实测的是目标物，不是恒真断言。
- 新增守卫：`test_settings_txt_is_gone_from_the_build_path`、`test_config_toml_owns_every_project_value`、`test_default_lang_has_translations`、`test_lang_lives_only_in_user_cfg`、`test_export_config_emits_every_project_macro`、`test_retired_truth_table_stays_declared_void`；`test_devdoc_refs.py` 新增 `RETIRED_FILE_QUOTES` 分类（改名前坐标**故意不解析**，否则等于默许失效行号继续冒充现状），现行真值表改为断言 devdoc 120 §九。
- 顺带修掉 `test_devdoc_refs.py::test_cited_docs_exist` 的引用正则：原先用惰性 `[^`]+?` 匹配，遇到标题含 `.` 的文档名（`config.toml`）会截断成不存在的路径，报错指向错误原因，后人大概会去改文档名而不是改守卫。

**文档订正（AGENTS.md §十 四步）**：devdoc 118 追加 0.3.014 ERRATA（§6.1 归属表整行作废、§三 键集失效、新增第 3 条「同型缺陷第二处」）；devdoc 119 追加 0.3.014 ERRATA（**§二 整张行号真值表因改名整体作废**、§3.2「设计门控不充分」）；接替文档 `devdocs/120-settings.txt废止与config.toml单一配置源与启动菜单语言根修.md` 承载订正后完整记录与**现行行号真值表 §九**；AGENTS.md §十一、B90、B91 就地订正。

**实机 A/B（NP2kai + 串口 + XTEST，三轮）**：`np2kai_ab.py` 原先无法对启动期标记下断言（`--target`/`--forbid` 都从 `--advance-to` 匹配结束处起算，而语言标记在 `nb_init start` 之前发出），故新增 `--boot-expect` / `--boot-forbid` / `--boot-only`，并在 `nb_set_lang()`（`prefs_get_lang()` 在真实游戏路径上的唯一消费者）加确定性标记。轮次 A（`USER.CFG` 预置 `cht`）**PASS** exit 0；轮次 B（无 `USER.CFG`，菜单内 Right×3 选 `cht`）**PASS** exit 0；轮次 C（故意把 getter 改回读另一份）**BUG_SIGNATURE_PRESENT** exit 1，且复现原始症状 `bootmenu: enter (default lang=eng)`——证明前两轮不是恒真断言。顺带修掉探针两个真实缺陷：`--forbid` 声明可选却无条件传给 `_wait_for`，省略时 `TypeError` 崩掉整个探针；`_report` 在 `--boot-only` 下格式化 `None` 正则再崩一次。

**⚠ 本轮未覆盖：`demo-a2` 中日韩剧本文本根本没翻。** 这是与「语言选择不生效」**相互独立**的第二个缺陷，A/B 全 PASS 之后剧情仍是英文——`game_jpn/chi/cht.txt` 各 37 键中 **36 键译文为空**，`role_*.txt` 3 键**全空**（仅 `sys_*.txt` 49 键已全译）。`tr()` 对空译文**回落源串**（`core/lib/tr.c:148-151`），故修好配置后开机菜单与设置界面确实是繁体中文，**但剧情台词与角色名仍是英文**。用户看到的现象只会从「菜单也是英文」变成「菜单中文、剧情英文」。补齐这些译文是**内容工作**，需要单独进行；详见 devdoc 120 §6.3。

**新增长期规则**：新增 `prefs_get_*` / `prefs_set_*` 访问器对时，**必须**登记进 `test_audio_settings_invariants.py` 的同源守卫——devdoc 118 已在 `audio_get_*` 上犯过一次，0.3.014 在 `lang` 上犯了第二次，测试全绿并不能证明访问器绑定的是同一份状态。

---

<a id="c44"></a>
### 0.3.013 — i18n 译文宽度守卫：4/9 语言行标签 + 5 处值标签曾被静默裁剪（devdoc 119 §3.4/§5.1）

**起因**：用户问「还有什么未完成」时做只读审计，按 `text_width` 的真实规则（ASCII 8px / **字节高位即 CJK 16px**，故德语 `ä` 算 16px）逐条量了 9 语言的设置行文案，结论：**0.3.011 声称「15 个新 key × 9 语言已交付」，实际 4/9 语言的行标签放不下会被裁剪**。

| 区域 | 限宽 | 溢出 |
|---|---|---|
| 行标签 `SET_LABEL_W` | 170px | `fre` 248 / `ger` 208 / `por` 184 / `spa` 184（`Sound & Voice Volume`） |
| 值列 `SET_VAL_W` | 80px | `por`+`spa` `Instant` 96 / `fre`+`spa` `Off` 88 / `fre` `Instant` 88 |

**根因**：`test_new_ui_keys_translated_everywhere` 断言「每个 key 在 9 个文件里都有**非空**译文」——校验了**存在性**，没校验**可用性**。且违反项目早已写下的成例 `nb_saveload.c:44`「Box width grows with the translated text so long CJK/European strings are not clipped」，只是没人把那条成例推广到设置行。

**修复**（一律改译文，不动行几何——值列两侧紧邻 `SET_ARR_LX`=330 / `SET_ARR_RX`=450 箭头，加宽余量不足）：
- 基准 key `Sound & Voice Volume` → `Sound & Voice Vol`（144px）；`fre`/`ger`/`por`/`spa` 译文缩短至 ≤152px；`ita` 由 168px（仅 2px 余量）收紧为 `Volume effetti/voce`
- 值列改用各国惯用短形并**保持配对称谓**：`fre` `Actif`/`Inactif`、`Immédiat`；`spa` `Inactivo`、`Inmediato`；`por` `Imediato`。`On`/`Off`/`Instant` 经确认**仅**用于设置行（`nb_setting.c:99`、`settings.c:44`），无其他 UI 依赖

**新增守卫**：
- `tools/tests/test_i18n_label_width.py`（6 函数 / 14 项）——宽度常量从 `core/lib/font.h`、`core/lib/cjk.h` **读取**，行几何从 `nb_setting.c` **读取**，行标签与值标签从 C 源码**正则解析**，测试跟踪引擎而非二次冻结数字；`test_row_labels_parsed_from_engine` 防「正则失效→检查空转」；`test_high_bit_letters_cost_cjk_width` 冻结字节高位规则
- `test_devdoc_refs.py` 补 `test_every_devdoc_ref_is_registered`（9→10 项）——**关闭白名单的开放世界**：原 `_devdoc_line_refs()` 定义了却从未被调用，白名单只保护「有人记得登记的引用」，新章节里写的引用无人检查。写 §3.4 时把 `nb_setting.c:241` 写成 `:240` **全绿通过**，正是这个缺口。新增 `STALE_QUOTED_REFS`（22 条）容纳**故意引用的失效值**：真值表左列（118 的错值）与变异表——118 §一/§3/§6/§8 不许改（§十 步骤 1），故错值只能引用不能修
- `AGENTS.md` §十四 i18n 新增第 5 条「译文必须放得下，不只非空」：记 `text_width` 的字节高位规则、优先改译文而非改几何、指向宽度守卫

**守卫自证**：改回 `fre` 原长串 → 标签列与值列断言**同时**转红（`2 failed, 12 passed`）；把 119 的 `241` 改成 `242` → 封闭性测试转红并指名 `nb_setting.c:242` 未归类。均恢复后全绿。**加上封闭性测试的第一件事**就是抓出 2 条漏登记的真引用（`build_game.py:474`、`render_text.c:235`），证明非空转。

**验证**：`pytest tools/tests/` **569 passed / 1 skipped**；`NAIZ_CHECK_HDI=1` 下 **570 passed / 0 skipped**；`./start.sh fullaudit` 7/7；`make -C core` 0 err / 0 warn；`build+make` 全部通过。`bump_version` 0.3.012 → 0.3.013。

**未完成（不因本次修正而改变）**：118 §十 的实机验证五项（PCM 四档听感、CC7 是否被 MPU-98II 采纳、音量即时生效、7 行分页手感、`USER.CFG` 实机存活）仍未做；「跳过已读 / Backlog / 手柄 / 分辨率 / 字号」按 §四 明确排除。详见 devdoc 118 §十、119 §3.4。

---

<a id="c43"></a>
### 0.3.012 — devdoc 118 规格订正 + 文档一致性回归守卫（devdoc 119）

**起因**：0.3.011 收口时只核对了「新增的 31 项测试是否存在」（全绿），没核对 devdoc 118 正文的声明与代码是否一致。事后逐条对照发现 118 虽标「完结」，却含**未做的声称**、**夸大的守卫强度**、**不存在的产物**与**20 处失效行号**。

**根因（本轮唯一可复用的教训）**：把「`pytest` 全绿」当成了「文档正确」的证据——**没有任何测试读 `devdocs/`，二者无因果关系**。而 `devdocs/` 的规则只规定「已完成的文档禁止修改」，从未规定**谁在何时校对规格与实现的一致性**，这个双源之间的收敛环节无人负责。118 写于代码改动之前，§六/§七 描述的是**改动后**状态却保留了**改动前**行号（`settings.c` +221/-81、`nb_setting.c` +202/-47），我收口时只刷新了 §十一 验证结果，没回头校引用。

**最隐蔽的一类**：§九 声称「roundtrip 目标改为 `USER.CFG`、`_parse_speed`/`_save_line` 拆两段」，实际**只改了模块 docstring**（`git diff` 8 增 2 删全在注释里，函数体一行未动）。**新增文件容易核对（文件在不在一目了然），而「既有文件被改过」这个事实会掩盖「改的是不是声称的那一处」**。

**修复**（AGENTS.md §十 四步路径，**118 正文一字未改**，仅加 ERRATA 块）：

| 步骤 | 落地 |
|------|------|
| 1 原文档加 `> ## ⚠ ERRATA` | `devdocs/118` 头部，四类不符逐条列明 + 指向 119 |
| 2 新建接替文档 | `devdocs/119-用户偏好分家实装订正与设计门控与规格双源守恒.md`（含 33 处引用逐行核对、26 行行号真值表、计划落差分析） |
| 3 CHANGELOG 加订正标记 | 本条 c42 内「⚠ 订正」小节 |
| 4 AGENTS 就地订正 | §十 新增「**规格与实现的收敛责任**」：收口流程固定为「实现 → 逐条核对声称 → 校行号 → 标状态」，并写明 pytest 全绿不构成文档正确的证据 |

**防呆**：`tools/tests/test_devdoc_refs.py`（8 函数 / 9 项）把不可测的「文档对不对」变成可测——行号引用须解析到**含该符号的非空行**、§九 类声称须与测试文件事实相符、**ERRATA 块不得被静默删除**、被引用文档须存在。其中 `test_devdoc_claims_match_test_files` 专门冻结订正后的事实，防止后人照 118 §九 的错声称去「修正」测试代码。

**守卫自证**（4 组变异，全部按预期转红后恢复）：真值表改回失效行号 → 1 红；删 ERRATA 块 → 1 红；白名单塞入指向空行的引用 → 1 红；给 `test_text_speed_settings.py` 加第二个 `_parse_*` 函数（模拟后人照旧文档改代码）→ 1 红。

**过程中我自己又犯了两次同类错误，已记入 119 §五**：① 写白名单时留了占位垃圾 `("nb_setting.c", 178 - 79)`，其值恰是 99 那个失效行号，被守卫当场抓住；② 用 `git checkout` 恢复变异时**连带回退了上一轮尚未提交的 docstring 成果**（`git diff` 变空才发现），已重写——**变异自证后恢复源码必须逐文件核对 `git diff`，不能整文件 checkout**。

**验证**：`pytest tools/tests/` 554 passed / 1 skipped（`NAIZ_CHECK_HDI=1` 下 555 passed）；`./start.sh fullaudit` 7/7；`make -C core` 0 err / 0 warn。**未改动任何 `.c`/`.h`。**

<a id="c42"></a>
### 0.3.011 — 玩家偏好分家 USER.CFG + 游戏内设置扩展 7 行（三开关/双音量/阅读进度）+ 86 板 PCM 寄存器 refdoc（devdoc 118）

**起因**：勘察游戏内设置场景时撞上两件事——设置页只有 1 行可用（`SETTING_ROWS=4` 的布局里 `g_rows[]` 仅 `Text Speed`），以及一个既存设计缺陷：`settings_save()` 写的是 `games/<game>/settings.txt`，而 `build_game.py` 每次**无条件**用 `projects/<game>/scene/settings.txt` 覆盖它 ⇒ 玩家改的 Language / Text Speed 每次 build 都被打回默认值。第二点决定了整个方案的形态：不先分家，加进去的每一行持久化设置都是「下次构建即丢失」的新增项。

**根因**：`settings.txt` 同时承担两个生命周期方向相反的职责——项目配置（随 commit 走，由 `config.toml` 注入 `version`/`blacktitle`/`blackdialog`）与玩家偏好（随玩家走，运行期回写）。共处一文件 ⇒ 玩家的选择在**设计上**不可能存活。不是某次忘了同步，是结构性问题。

#### 持久化分家

| 文件 | 归属 | 键 |
|------|------|-----|
| `settings.txt` | 构建期维护（**不再被运行期回写**） | `dlgstyle` `btnstyle` `version` `blacktitle` `blackdialog`，以及 `lang` 项目默认 |
| `USER.CFG`（新建，8.3 安全） | 运行期回写 | `lang` `text_speed` `bgm` `snd` `vc` `bgm_vol` `pcm_vol` |

- 载入顺序：`settings.txt` → 叠加 `USER.CFG`（玩家优先）；缺任一文件为合法首启态，两种情况均有 `hal_log` 诊断。
- `settings_save()` 改为只写 `USER.CFG` 7 键；三个调用点（`main.c` / `nb_mainmenu.c` / `nb_setting.c`）签名与位置不动。
- `build_game.py` 增「`USER.CFG` 已保留」分支：**只探测、只打印，不绑定变量名、不写入**。
- 抽出 `read_kv()` 供两文件共用，畸形行行为完全一致（消除原先 `feof(stdout)` 的错误句柄）。
- 语言回落链保留：玩家未选 ⇒ 继承 `settings.txt` 的 `lang` 项目默认。

#### 设置场景 1 行 → 7 行（2 页）

| 页 | 行 |
|----|-----|
| 1 | Text Speed · BGM · Sound Effect · Voice |
| 2 | BGM Volume · Sound & Voice Volume · Read Progress |

- `SettingRow` 增加 `kind`（`ROW_ENUM` / `ROW_READOUT`）与 `text()`。**只读行不画 `<`/`>`、不响应 step、不响应箭头命中**——原实现是无条件画箭头、无条件循环，必须显式分叉。
- **补上分页状态**（勘察时误判「翻页器已实现」）：原文件头注释明写「没有分页状态」且 `cmd_settingmenu` 有 `N_SETTING_ROWS > SETTING_ROWS` 直接 return 的硬门。现照 `nb_saveload.c` 范式补 `page` / `setting_row_count()` / `setting_row_abs()` / `setting_row_at()`，键盘用 Tab 换页（无 Shift-Tab：HAL 不提供修饰键查询，双键绑定不可靠）、只读行与 Back 焦点上的 LEFT/RIGHT 翻页，鼠标走 `menu_page_hit()`。键位说明同步更新。
- 阅读进度复用 `sys_save_is_cg_unlocked()`，遍历照 `cg_map` 范式，分子按 `CG_TOTAL=99` 夹逼（解锁位图 99 位而资产表可能更多，C6/C29）；`0/0` 零资产兜底。纯数字格式串 ⇒ §十四.2 例外，不经 `tr()`。

#### 三条开关与两条音量（硬件依据 `docs/refdocs/F02_86pcm_registers.md`）

- 状态归 `audio.c`，三入口 `audio_bgm_start` / `audio_snd_play` / `audio_vc_play` 开头加门（已核实 `nb_audio.c` 全经此三处，无旁路）。BGM 关额外 `audio_bgm_stop()`（16 通道 all-notes-off）。
- **精确切断**：新增 `g_pcm_channel`（NONE/SND/VC），`pcm_play` 赋值、`pcm_release` 清零，关闭某通道**仅当匹配**才 `pcm_release()` ⇒ 关音效不会误伤正在播的语音。
- BGM 音量 = MIDI **CC7** 三档 `0/64/127` → `0%/50%/100%`（照 `audio_bgm_stop` 的 16 通道循环范式，起播与变更各下发一次，运行期即时生效）。
- PCM 音量 = 86 板 **A466h** 电子音量四档 `0/5/10/15` → `Max/High/Mid/Low`（新增 `hal_pcm_set_volume()`，夹逼 0..15；`hal_pcm_play` 原有硬编码 `0xA0` 改为跟随当前 step）。
- **标签刻意不同形**：BGM 用百分比是行业惯例且 0 档真静音；PCM 是 4bit 衰减器、不存在 0 音量、衰减曲线未记载 ⇒ 写 `25%` 是假信息，故用词档。
- 写入前 `bgm_vol` 吸附到最近档位，手改 `USER.CFG` 也无法让菜单显示一个不可选的数值。

#### 顺带订正三处「代码对、注释错」的术语陷阱（F02 §5.2）

| 位置 | 原写法 | 实际语义 |
|------|--------|---------|
| `hal_audio.c` | `PCM_CTRL_A46A_FIFO` / 「A46A programs fifosize」 | bit5 是 **FIFO 中断许可**；置 1 时 A46A 解码为**中断间隔**寄存器 |
| `hal_audio.c` | `PCM_CTRL_FIFOSIZE_MAX` 0xFF | 数值对，但写的是中断间隔寄存器 |
| `hal_audio.c` | `outb(A460, 0x01)` / 「board enable」 | A460 写是 **OPNA mask**（bit0 选 OPNA），无「板卡使能」语义 |

`hal_pcm_play` 的六步初始化协议**原本就走对了**（先置 bit5 写间隔、再清 bit5 写 D/A），但靠错误注释掩护——后人照注释改必踩雷。

#### 验证

- `make -C core`：0 err / 0 warn
- `pytest tools/tests/`：**546 passed**（新增 31 项，`test_user_cfg_settings.py` 14 + `test_audio_settings_invariants.py` 17）
- `./start.sh fullaudit`：**7/7 通过**（`logs/fullaudit_20260930_114516.log`）
- `build demo-a2` + `build animatest` + `make demo-a2`：通过
- `NAIZ_CHECK_HDI=1 pytest tools/tests/`：**546 passed**（无 skip）
- **实机回归**（`build` 前写入 `USER.CFG`，`build` 后逐字节比对）：内容不变，build 输出「`USER.CFG` 已保留（玩家偏好，不覆盖）」
- **守卫自证**（临时改坏源码，验证测试转红后恢复）：`hal_pcm_play` 恢复硬编码满音量 → `test_pcm_play_honours_the_stored_volume` 红；`pcm_disable` 改无条件切断 → `test_disable_only_releases_its_own_channel` 红；`settings_save` 改写 `settings.txt` → 2 项红；`settings_load` 误从 `settings.txt` 读 `text_speed` → `test_settings_load_reads_both_files_in_order` 红；`build_game.py` 恢复删除 `USER.CFG`（含绑定变量名的隐蔽写法）→ 2 项红

#### 未验证（不得当作已通过）

- **PCM 四档实际听感**：A466h 的 4bit 衰减**连模拟器都未实现**（MAME 源码 TODO 明列 `Make volume work`，`m_vol[]` 存了但未接 DAC 增益）。`0/5/10/15` 等距划分只是中性做法，等距于听感并非等距。
- **CC7 是否被 MPU-98II 采纳**：CC7 是标准 GM 通道音量、MAME 的 mpu401 已实现，但 Yamaha 该卡在 UART 模式下的实际响应需实机听；若不采纳，BGM Volume 需退回纯开关。
- 音量改动在播放中的即时性、7 行布局与翻页手感、`USER.CFG` 跨 build 存活的实机确认：**均待用户实机验证**。

**产出文档**：`devdocs/118-玩家偏好分家与音频开关音量设置场景.md`（完结）、`docs/refdocs/F02_86pcm_registers.md`（新建，A–H 分类 F 声音类）+ `docs/refdocs/README.md` 索引。

#### ⚠ 订正（规格侧，见 `devdocs/119`；实现条目本身继续有效）

本条的实现部分无误，但**其规格来源 devdoc 118 存在四处与代码不符**，收口时未被发现：

1. 118 §九 声称的两处改动（`test_text_speed_settings.py` 的 roundtrip 改指 `USER.CFG`、`_parse_speed`/`_save_line` 拆两段）**未落地**——实际只改了模块 docstring；
2. 118 §九 把 build 守卫描述为「直接跑 `build_game.py` 部署段」，实际是**源码文本断言**，部署级验证是人工逐字节比对（见上「实机回归」）；
3. 118 §七 点名的「`USER.CFG` 路径常量」**不存在**，且漏列 `build_game.py` 与两个测试文件；
4. 118 §一/§三/§六/§八 的 **20 处行号**因实现位移失效（真值表见 119 §二）。

**根因**：把「`pytest` 全绿」当成了「文档正确」的证据——没有任何测试读 `devdocs/`，二者无因果关系。**已落地防线**：`tools/tests/test_devdoc_refs.py`（9 项）把「文档行号引用可解析」「声称与测试文件事实相符」「订正块不得被静默删除」「引用文档存在」变成可测对象；`AGENTS.md` §十 新增「规格与实现的收敛责任」。**本轮未改动任何 `.c`/`.h`**，`pytest` 554 passed / 1 skipped（`NAIZ_CHECK_HDI=1` 下 555 passed）与 `fullaudit` 7/7 依旧通过。

**接替文档**：`devdocs/119-用户偏好分家实装订正与设计门控与规格双源守恒.md`。118 按 §十 步骤 1 正文一字未改，仅加 ERRATA 块。

<a id="c41"></a>
### 0.3.010 — 实机验证五禁写入 AGENTS + HDI 新鲜度双守卫 + 守卫自证不变量测试

**起因**：0.3.009 的 A/B 一度让**故意回退的构建报 PASS**（`c40` A/B 表里对照组是 `BUG_SIGNATURE_PRESENT`，但更早几轮曾整体报 PASS）。根因不在探针、也不在断言，而是**只跑了 `makegame.sh build`**：它只部署 DOS 树，注入 `disks/<game>.hdi` 的是 `make`，而模拟器启动的是 HDI。探针因此在测**上一个引擎**——而旧引擎的日志**一切正常**，于是「构建不对」这件事在整轮运行里没有任何表征。这一次经历直接催生了本条：把踩过的坑固化成规则 + 自动守卫。

**变更**

1. **`makegame.sh test` HDI 新鲜度门控** — 在 `exec … test-hdi` 之前比对 `disks/$GAME.hdi` 与 `games/$GAME/engine.exe` 的 mtime（`[ "$HDI_PATH" -ot "$ENGINE_PATH" ]`），过期则打印修复步骤并 `exit 1`。位置关键：**必须在启动模拟器之前**，放在 `exec` 之后就是死代码。
2. **探针 `preflight()` 增 `STALE_HDI` 门控** — 同一比对，命中即返回门控名（`preflight` 失败一律 `sys.exit(1)`）。**顺带修一处既有缺陷**：`preflight` 的失败分支原为 `print(1 if gate in ("NOBOOT","NOWINDOW") else 0)`，即**除两个已废弃门控外所有门控都退出 0**——门控失败却对调用方报成功，正是本轮一直在根治的病；那两个门控名在探针重写时已不存在，故该分支实际等价于「永远返回 0」。
3. **修 `NO_HDI` 错误路标** — 原文案是「run makegame.sh build」，而 `build` 只部署 DOS 树、**根本不产生 HDI**（`make` 才 inject）。这个错路标正是「只 build 不 make」这一错误认知的诱因之一，现文案改为 `build` + `make` 两步。
4. **新增 `tools/tests/test_hdi_freshness_guard.py`** — 断言**守卫本身存在且接在文档化入口上**（`makegame.sh` test 分支含 `-ot` 且位于 `test-hdi` 之前；探针 `preflight()` 含 `STALE_HDI` + mtime 比对；门控失败 `sys.exit(1)` 而非 `print`；`NO_HDI` 文案指向 `make`）。
   **刻意不做**「HDI 过期即 pytest 失败」：那会让**每次改代码都红**（`engine.exe` 变新即过期），噪声源必然被加 skip 或忽略，门控等于没加。状态级断言改为 `NAIZ_CHECK_HDI=1` **可选**启用，产物缺失则 `pytest.skip`（沿用 `test_palette_reserved_slots.py` 惯例）。
5. **AGENTS.md 新增「实机验证五禁」（§八）** — 五条各自对应 0.3.009 的一次误判，每条给**现象 → 正确判据 → 出处**：
   - 禁把串口 trace 一次性观察当因果证据（`[INPUT]` 是输入被消费，不等于用户点了；正确判据看 `[MOUSE] b=0/b=1` 轮询序列，原始 trace 是 37 次 `b=0`）；
   - 禁只 build 不 make（＝跑旧引擎且日志正常）；
   - 禁用竞态指标当判别器（点击计数 vs 短句 0.6s 打字窗口；改用引擎侧确定性标记 + 探针 `--forbid`）；
   - 禁门控只覆盖单一输入通道（键盘 `[INPUT] Key confirmed` / 鼠标 `b=1`），且门控失败必须非零退出；
   - 禁结论推翻后留下互相矛盾的文档。
   另：§九.6「消灭静默失败」补一句「验证必须证明它测的是目标物，**假通过比失败更危险**」；§十三补录探针（此前 AGENTS 全文未收录该工具）。
6. **AGENTS §十 新增「结论推翻时的文档订正」** — 这是被 devdoc 116 逼出来的规则空洞：「已完结文档禁止修改」与「结论被推翻」正面冲突，当时只能破例加 errata。现固化为四步路径：原文档正文一字不改 + 顶部 `⚠ ERRATA` 指路 / 新建编号+1 接替文档 / CHANGELOG 加订正标记（锚点与索引号只增不改）/ AGENTS 对应规则就地订正。判定标准：**任何地方还留着一个已知错误的结论，就是未完成**。

**验证**

- 守卫**正向生效**：`touch games/demo-a2/engine.exe` 造过期态后，`./makegame.sh test demo-a2 --serial` 打印 `ERROR: HDI 过期` 并 `exit 1`（未启动模拟器）；探针返回 `VERDICT = STALE_HDI` 且 `exit 1`。`make` 恢复后两者均放行，`preflight()` 返回 `(True, '', '')`。
- 不变量测试**自证**：临时删除 `makegame.sh` 守卫后 `test_makegame_test_branch_gates_stale_hdi` 转红，恢复后全绿——避免留下又一个没人验证过的守卫。
- `make -C core` 0 err/0 warn；`pytest tools/tests/` **514 passed / 1 skipped**（新增 5 项，其中 `NAIZ_CHECK_HDI` 状态检查默认 skip）；`./start.sh fullaudit` **7/7**；`bash -n makegame.sh` 通过。

---
<a id="c40"></a>
### 0.3.009 — 单页对白不再重复 arm 打字机：CG 后首句首击即翻页（devdoc 117）

**症状**：`projects/demo-a2/scene/nbook004.nb` 第 10 行 `neon(){Hey,you really have a great figure.}`（串口日志 0 基 `line[9]`，紧随 `line[8] cg(){cg01}`）在 CG 之后**首击无效**，需再点一下才翻页。0.3.008 曾把该症状误判为「点击 FIFO 在 blit 期间堆积导致无输入自动翻页」，实机 A/B 已推翻（判定过程见 [0.3.008](#c39) 顶部订正段），本条为真实根因与修复。

**根因**：`core/engine/nb_dialog.c` `dialog_show()` 中，能装进一页的整句先由 `layer_dialog_render_page()` **一次性完整绘制**（`next < 0`），但 `reveal_active` 仍按「非 INSTANT 速度」无条件置位，于是走进「Typewriter on」分支调用 `dialog_render_reveal()`，**用空前缀覆盖刚画好的整页**（只剩对话框盒 + 角色名），再逐字重打。两个后果：

1. **视觉**：整页文字 → 瞬间清空 → 逐字重现，即用户所说的「一闪而过」；
2. **输入不一致**：`main.c:165-168`（鼠标）与 `main.c:198-201`（键盘）共用同一判定——若点击落在打字机进行中，首击走 `nb_dialog_reveal_finish()`（补完打字、**不翻页**），第二次才 `vm_request_process()`；若打字已打完，首击直接翻页。**同一句对白的行为随点击时机而变**，这正是它长期无法定案的原因；短句的打字机约 0.6s 打完，故「点得慢就正常、点得快要两下」。

**修复**：单页行（`page_start == 0 && next < 0`）不再 arm 打字机，整句一次显示，首击即翻页；**多页行所有页（含末页）保持打字机**，效果统一不变。条件提取为 `single_page` 局部标志，使 arming 分支能同时报告页型。

**新增运行时标记**：`dialog_show()` 现输出 `dialog_show: typewriter armed|off (single|paged page)`。此前该回归**只能靠点击计数观察，而点击计数本身是竞态**（短句 0.6s 内打完，探针开销即可错过窗口）——0.3.009 的 A/B 正是先被这个假通过骗过。标记把「单页行是否 arm 打字机」变成串口日志里的确定性事实。

**诊断工具入库**：`tools/diag/np2kai_ab.py`（NP2kai + xdotool 串口 A/B 探针）。关键设计（均为实测踩坑后固化）：

- `--forbid` 否定断言为**确定性判别**，`--clicks` 点击计数仅作辅助；
- 按通道取输入采样标记：键盘看 `[INPUT] Key confirmed`、鼠标看 `b=1`——只认鼠标标记会把成功的键盘轮次误报为 `INPUT_NOT_SAMPLED`；
- 按键走 **XTEST**（`xdotool key` 的 XSendEvent 合成事件会被 wxWidgets 丢弃），且用 `keydown`/`keyup` 显式保持 150ms——`xdotool key` 的按下+抬起仅约 12ms，落在两次 BIOS 端口轮询之间则完全采不到；
- `--advance-to` 之后从**标记匹配结束位置**而非「当前末尾」开始找 `--target`，否则 CG blit 期间已写出的目标行永远等不到；
- `STUCK_BOOT_MENU` 等门控失败时打印输入采样数与窗口片段，便于自解释。

**A/B 实证**（`disks/demo-a2.hdi`，同一场景同一参数，仅回退/应用 `!single_page` 一处）：

| 构建 | 标记 | 1 次输入后 `line[10]:` | 判定 |
|------|------|----------------------|------|
| 回退 | `typewriter armed (single page)` | 未出现 | `BUG_SIGNATURE_PRESENT` |
| 修复 | `typewriter off (single page)` | 出现 | `PASS` |

**验证**：`make -C core` 0 err/0 warn；`pytest tools/tests/` **510 passed**（`test_single_page_line_is_not_re_revealed` 对回退灵敏、对修复通过，已双向确认）；`./start.sh fullaudit` **7/7**；`makegame.sh build demo-a2` + `make demo-a2` 成功；探针 A/B 如上表。`bump_version` → `0.3.009`。

**遗留**：`playanima → waitanima` 的 `anim_stop()` 幽灵唤醒门控（0.3.008 变更 3）尚缺专项实机回归，本次 A/B 未覆盖。

---
<a id="c39"></a>
### 0.3.008 — 输入边界收口为单一 helper + anim 幽灵唤醒门控 + 阻塞元数据死标志标注（devdoc 116）

**本条性质**：重构 + 预防性防护。

> ⚠ **本条因果判定已于 0.3.009 订正**。原标题为「CG 后首句对白一闪而过根修」，并把根因归给「点击 FIFO 在 `cmd_cg` 整屏 blit 期间堆积」。**该判定被实机 A/B 推翻**：真实根因是单页对白行被重复 arm 打字机（见 [0.3.009](#c40) / `devdocs/117`）。`devdocs/116` 正文按存档规则保留原样，其顶部 errata 指路。

**被推翻的判定（留痕）**：`cmd_cg` 的整屏 blit 期间不调 `hal_mouse_update()` 属实，但**点击并不会因此堆积**——`mouse_update()` 是纯轮询、无 IRQ 路径，鼠标状态只在轮询瞬间被采样，一次完整的「按下 + 释放」若整体落在两次轮询之间就根本采不到。原始证据 `logs/serial_demo-a2_trace.log` 在 CG 之后先出现 **37 次 `b=0` 轮询**，随后才是两次真实点击的 `b=1`，与「无输入自动翻页」的用户自述不符。故原根因段所称「堆积点击被当作新页输入」在物理上不成立；首击是否被吞取决于点击是否落在打字机进行中，因此**症状随点击时机而变**，这也是它长期难以定案的原因。

**保留的变更（各自独立成立，与本症状无因果关系）**

1. **新增 `core/engine/input_boundary.{h,c}`** — 剧本边界统一丢弃用户输入的**单一入口** `input_drain_boundary()` = `hal_kbd_drain_advance()` + `hal_kbd_set_ignore_frames(2)` + `hal_mouse_flush()`。三 call 缺一不可：`kbd_drain_advance()` 内含 `kbd_bios_reset()` 会擦 BIOS 环，但固定延时后即返回、**不等物理释放**，仍按住的方向键/推进键其自动重复码会泄入下一帧（键盘侧确有此路径）；鼠标侧**根本没有清点击 FIFO 的 drain**（`hal_mouse_drain()` 只清 dx/dy 累加器），尽管 blit 期间轮询停摆使点击无从堆积，此 call 仍用于兜住其它来源的陈旧点击。`core/Makefile:35` 为 wildcard，新文件零构建改动。
2. **10 处入口统一调用**：`nb_save_dialog.c` / `nb_saveload.c` / `nb_setting.c` / `nb_special.c` / `layer.c` 五处补齐三件套（前三类均读 `hal_mouse_was_clicked` 而原先无 flush，菜单刚打开即可能被陈旧点击命中——属**卫生性加固**，非本 bug 根因），加已具备三件套的 `nb_menu.c` / `nb_interact.c` / `settings_menu.c` / `nb_cggallery.c` 统一走 helper。**保持原样**（语义不同）：`main.c` ESC 前 `hal_kbd_flush()`、F7 dump 后 drain、输入等待消费**之后**的 `hal_mouse_flush()`；`nb_saveload.c:show_error_msg()` 的 `drain+wait_any+drain` 三连；`settings_menu.c` 分页内节流。
3. **`core/engine/nb_anim.c` — anim 幽灵唤醒门控**：`anim_stop_internal()` 尾部 `vm_request_process()` 改为**仅在清零 `a->wait` 之前捕获到 `was_waiting` 时**发出，即只有待决的 waitanima 持有态才恢复脚本（与函数头注释的既定意图一致）。此前无条件唤醒：普通 `anim` 结束后若紧跟 `bg`/`cg`（二者均隐式 `anim_stop()`），残留 `VMFLAG_PROCESS` 在下一条命令不开对白页时会让剧本**无输入自行前进**——与本 bug 症状相似但根因不同，属**独立缺陷**，此处一并根除以免后续误判为「未修干净」。
4. **死标志标注**（`nb_commands.c`）：`nb_commands_dispatch()` 经核实**不读任何元数据位**，`CMD_BLOCKING` / `CMD_NEEDS_INPUT` / `CMD_TOUCHES_AUDIO` / `CMD_TERMINATES_SCENE` **仅作文档用**。危险点在于 `tools/tests/test_cmd_meta.py:42` 把它们列入「合法标志集」，使命令表**看起来被测试覆盖**而实际语义零强制——新增阻塞 handler 若漏写自暂停，剩余脚本会在单个 pass 内跑完。已在 enum 处与 `nb_commands_dispatch()` 处加注释明示「阻塞由 handler 自行实现，引擎侧唯一暂停点是 `nb_process()` 的 `nb_dialog_pending()`」。**不删标志**：删除需动约 20 行表项 + 改测试标志集，性价比不划算。
5. **文档**：`docs/B90` 新增「输入边界收口 → `input_boundary.c`」节 + 标注 `mouse_drain()` 与 `mouse_flush()` 不可互换 + `anim_stop_internal()` 门控契约 + `nb_commands_dispatch()` 元数据警示；`docs/B92` 新增「剧本编写陷阱」小节（3 条剧本层即可触发的约束：cg/bg 后须紧跟对白行、playanima 后接 bg/cg、delay 期间不接受翻页输入）；`devdocs/116` 完整开发文档（**其根因段已被 0.3.009 推翻，见该文档顶部 errata**）。

**一处误判纠正**：排查中曾按不存在的符号名 `vm_delay_set` 判定「delay 路径是死代码」，实为 `cmd_delay` → **`vm_set_delay()`**（`nb_commands.c:358`），且 `delay(1.5)` 在 `logo.nb` / `op.nb` 正在使用。`vm_delay_active()` 门控输入等待**正是 delay 的既定语义**（延迟期间不接受翻页、到点自动继续），行为正确，**无需任何改动**——该排除结论已在 devdoc 116 §三记录留痕。

**验证**：`make -C core` 0 err/0 warn；`pytest tools/tests/` **509 passed**；`nb_validator` 两项目 0 errors；`makegame.sh build demo-a2` + `make demo-a2` 成功；`./start.sh fullaudit` **7/7 通过**（`logs/fullaudit_20260929_114418.log`）。`bump_version` → `0.3.008`。
---

<a id="c38"></a>
### 0.3.007 — 图片调色板不再侵占引擎 chrome 槽 248–255：Back 按钮跟随全局 btnstyle + 角标只显编号

0.3.006 遗留的两个用户可见问题：画廊格子角标显示成「CG 01」（应为「01」），以及 **Back 按钮不跟随全局 `btnstyle` 配色**（demo-a2 为 `btnstyle=2` 绿，实测 Back 框全黑）。

**根因（0.3.006 的注释把因果讲反了，本轮一并纠正）**

`btn_update_palette()`（`layer_dialog.c:103`）是 249/252/253 三个按键色槽的**唯一所有者**，只有两个调用方：`layer_bg_change()`（`layer_bg.c:168`）与 `btn_set_style()`（`layer_dialog.c:141`）。而 `image_set_palette()`（`image.c`）对非 sprite 图写满 `num_colors=256` 项 —— 用 `mag.c` 自己的公式解析 MAG 头确认 `cg01.MAG` / `cg01_t.MAG` 的 `num_colors` **均为 256**（此前记录的「246 色」是共享调色板里**实际被用到**的颜色数，不是 `num_colors`），配合 `pack_images.py` 把 248–255 写成黑占位，于是**任何一次图片载入都会把 249/252/253 抹成黑**。

`gallery_draw_grid()` 的绘制顺序是「先 12 格（每格已解锁 → `image_load(thumb)` → 三个按键槽变黑），**再** `menu_back_draw(352, focus, emboss=1, …)`」，而 0.3.006 的 `gallery_apply_widget_palette()` 只恢复 250/251/255/254、**恰好漏掉 249/252/253** → Back 框全黑。

**load 菜单为什么正常（即反馈中的「参考」）**：`blacktitle=0`（`games/demo-a2/settings.txt:61`）时它不载入标题图，chrome 紧跟 `layer_bg_change()` 之后绘制，三个槽仍是绿色。它并非用了更高明的写法，只是**恰好没有 image_load 卡在 `btn_update_palette()` 与 chrome 绘制之间**。反推：`blacktitle=1` 时它会以完全相同方式坏掉（12 个槽框 + Back 全黑），属潜伏同类（`blackletter_title` 目前仅 `settings_load()` 一处赋值，无 UI 入口）。

**同根因排查（§十七）**：`image_set_palette()` 写满 0..255 的行为对**所有**图类型成立，sprite 分支只跳过 7/15、照写 248–255，故 `layer_sprite.c` 三处（`:119`/`:145`/`:207`）同属该类 —— 角色显示后再弹确认框时 Yes/No 按钮会变黑。`nb_special.c` / `nb_setting.c` 虽同样用 `BTN_FILL_IDX`，但绘制途中不载入图片，继承 `layer_bg_change()` 的正确值，不受影响；开机菜单 `settings_menu.c` 不用 emboss，亦不受影响。

**变更**

1. `core/engine/image.c` — **咽喉点收敛**：`image_set_palette()` 对**所有**图类型跳过 248–255（新增 `IMG_CHROME_PAL_FIRST/LAST` 局部常量，不 include `render.h`/`scene_layers.h` 以免 `image.c` 反向依赖 UI 层）。这与 sprite 分支已有的「跳过 7/15 保留引擎白」是同一意图的补完：`pack_images.py` 已把 248–255 定义为 `248-255=menu` 保留槽并写黑占位，作品像素实测最大索引 **247 从不引用它们**。一处改好画廊 / load 菜单潜伏路径 / sprite 三处，**零运行时开销**（仅在既有循环里多两个 `continue`），且不碰动画热路径。
2. `core/engine/nb_cggallery.c`
   - `gallery_draw_badge()`：`"CG %02d"` → `"%02d"`，底板宽随 `text_width()` 实测自动 48→24px。
   - **删掉**每格缩略图载入后的 `gallery_apply_widget_palette()` 调用：改 1 后图片已不触碰 248–255，且入口已设定过，该调用成为每格 4 次冗余 `hal_set_palette`（12 格满屏重绘 ×4），留着还会诱导后来者以为「图片载入会抹掉 chrome」。
   - `gallery_apply_widget_palette()` 保留但**职责收窄**：现在只「设定」画廊自有的 250/251/254/255，按键色 249/252/253 与对话框 248 **交还 `btn_update_palette` / `dlg_update_palette` 真正所有者**，不再重述（否则与全局设置脱钩）。
   - 修正四处**事实错误/过期注释**：文件头布局（`cell 144x100, y=32/136/240` → `144x84, y=44/132/220`）、槽位所有权说明、`gallery_apply_widget_palette()` 契约、`gallery_exit_preview()` 里「`layer_bg_change` 抹黑保留槽」的因果。
3. `tools/tests/test_palette_reserved_slots.py`（**新增**）— 锁住改 1 的前提：`image_set_palette()` 跳过 248–255 只有在「无 artwork 像素引用该区间」时成立，否则这类像素会渲染成 chrome 颜色。逐个解码 `projects/*/images/*.MAG`，断言 `max(pixels) < 248`（**35 条**）；另断言引擎侧 `IMG_CHROME_PAL_FIRST/LAST` 与测试常量一致、且跳过是**无条件**的（把守卫改成 sprite-only 即失败，已做变异验证）。MAG 解码复用 `naiz_lib.mag_codec.decode_mag_full()`，未新增解码逻辑。

**验证**：`make -C core` 0 err/0 warn；`pytest tools/tests/` **509 passed**（新增 36 条）；`nb_validator` 两项目 0 errors；`makegame.sh build demo-a2` 成功；`makegame.sh make demo-a2` 成功；`./start.sh fullaudit` **7/7 通过**。附带确认缩略图尺寸无接缝：MAG 头 `right-left+1` = **144**、`bottom-top+1` = **84**，与 `GAL_CELL_W/H` 一致。`bump_version` → `0.3.007`。

---

<a id="c37"></a>
### 0.3.006 — CG 画廊三修：真实缩略图（构建期生成）+ 预览返回调色板保序 + footer 统一

收掉 devdoc 92/94 挂起的「二期真缩略图」，并修掉两个真实显示 bug。

**根因（均为调色板/几何层面，非笔误）**

- **返回预览后标题与格子变黑**：`pack_images.py` 生成共享调色板时把 **248–255 全部写成 (0,0,0) 黑**（246 量化色 + 10 保留槽），而 `image.c:225-239` 的 `image_set_palette()` 对**非 sprite 图应用全部 256 色**（`num_colors=256`）。画廊里**任何一次图片载入**（`gallery_exit_preview()` 的 `layer_bg_change(gallery_bg)`，以及本轮新增的每次缩略图载入）都会把 250（`MENU_PAL_WHITE`→标题）、255（`GAL_FILL_UNLOCKED`→格子）、254 抹成黑；旧代码只在画廊入口调一次 `menu_save_item_palette()` / `gallery_palette_save()`，退出后从未重建 → 违背 devdoc 92 「恢复背景 + 调色板保序」的原设计。
- **Back 旁左下白块**：`nb_cggallery.c` 调 `menu_back_draw(356,…)` 画出 x66..145/y356..385 的按钮，紧随其后的 `menu_pagenav_draw(370,370,…)` 触发 `nb_menu.c` 里 `menu_layer_erase_to_base(56,370,16,16)`（x56..71/y370..385），与按钮左缘**重叠 6×16 px** 并把 base 快照拷回（画廊背景近白，实测 RGB 253,254,249）→ 白块；且 `CG_COUNT=1` 时 `page>0` 不成立、`<` 不绘制，擦除留下空洞。画廊是**唯一**传 `arrows_y=370` 的调用方（saveload/special/setting 均为 318/352）。
- **缩略图纯蓝**：devdoc 92/94 明确记载的二期顺延（"真缩略图顺延二期"）——`gallery_draw_cell()` 只做 `fill_rect` + 编号文字，从不画图。**关键前提修正**：因 `pack_images.py` 已让全部图片共享同一 256 色调色板，缩略图**无需任何调色板切换**，只在构建期降采样即可。

**变更**

1. `core/engine/nb_cggallery.c`
   - 新增 `gallery_apply_widget_palette()` 单一所有者，重申 250(白)/251(黄)/255(蓝)/254(黑)；三个调用点：画廊入口、`gallery_exit_preview()` 的 `layer_bg_change()` 之后、每次载入缩略图之后。
   - 几何 `GAL_CELL_H` 100→**84**、`GAL_STEP_Y` 104→**88**（`GAL_GRID_BOTTOM` 自动得 304，网格底 304 < 箭头带 318，留 14px）；footer 统一为与其余三个系统菜单**完全一致**的 `menu_pagenav_draw(318, 330, …)` + `menu_back_draw(352, …)`，并把 352/318/330 提为具名常量（`gallery_draw_cells_range` 另两处硬编码 356 与两处 `menu_page_hit(370,…)` 一并收口）；`[LOCKED]` 按新高度重新居中。
   - 新增 `gallery_draw_badge()`：左上角「CG %02d」序号，**深底板 + 白字**。底板宽随 `text_width()` 实测（`FONT_GLYPH_W=8`，"CG 01"=40px → 48×20 板），因画廊背景与 CG 缩略图实测均值亮度 ~178（偏亮），裸白字不可读。底板色复用 `PAL_CURSOR_BLACK`(254) 并纳入 apply 契约。缩略图与蓝底回退两条路径统一绘制。
   - `gallery_draw_cell()` 走 **`menu_layer_blit_sprite()`** 而非 `vram_blit()`：网格在 `menu_layer_begin_draw()`…`menu_layer_blit()` 之间绘制，`menu_layer_blit()` 只把 fill/pset/字形路由进合成缓冲，而 `vram_blit` 直写 VRAM → 会被合成缓冲整屏覆盖、缩略图不可见。`menu_layer.c:171` 已有该原语（双轴裁剪安全 + 层未开时回退 VRAM），**无需新增封装**。`PAL_NO_TRANSPARENCY` 作跳过哨兵与 `vram_blit` 语义一致；实测缩略图最大像素索引 **247**（< 248 保留区），哨兵安全。
2. `core/engine/nb_menu.c` — `menu_pagenav_draw()` **仅在对应箭头确实要绘制时才擦该侧**；计数器擦除保持无条件（计数器总是绘制）。这条同时修掉所有单页菜单的同类空洞，属通用修复。
3. `tools/naiz_build/cg_thumb.py`（**新增**）— 构建期画廊缩略图生成器：读 ASSETS.DB `type='CG'` 行 → 经 `assets/common/images.map` + `assets/<game>/images.map` 反查源 PNG（项目树覆盖 common）→ `resize_to_screen(..., cover=True)` **cover 裁切**到 **144×84**（无黑边）→ 复用 `convert_image(no_resize=True, reserved=PROTECTED_IDX_ALL)` 编码（先借后造，未给 `mag_convert` 加新参数）→ 输出 `images/<name>_t.MAG`、upsert `type='THUMB'` 行、增量跳过（`.cg_thumb_state.json`）。**8.3 守卫**：`<name>_t` 超 8 字符或短名碰撞即 `RuntimeError` 硬失败；CG 找不到源 PNG 亦硬失败。
4. 管线接线 — `build_game.py` 在两次 `convert_png_to_mag()` 之后、`export_asset_table()`/`pack_images()` 之前调用 `build_cg_thumbs()`（`THUMB` 类型白名单同步放行）；`pack_images.py` 的 types 元组加 `'THUMB'`（否则不入包）；`export_asset_table.py` 生成 **`cg_thumb_map[]` + `CG_THUMB_COUNT`**，按名（`<cg_name>_t`）关联 cg_map，**与 cg_map 逐下标平行**，缺图输出 `id=0` 而非压缩数组（避免整体错位），引擎据此回退蓝底。
5. `tools/tests/test_cg_thumb_size.py`（**新增**）— 守住跨语言常量重复：`THUMB_W/H == GAL_CELL_W/H`，并断言网格底 `< GAL_ARROWS_Y`、footer 三 y 递增。

**验证**：`make -C core` 0 err/0 warn；`pytest tools/tests/` **473 passed**（新增 4 条）；`nb_validator` 0 errors；`makegame.sh build demo-a2` 成功（`[29] cg01_t.MAG` 入包，`IMAGE.DAT palette verification OK (30 entries, shared 256-colour palette)`）；`makegame.sh make demo-a2` 成功（30 new / 3 updated / 33 total）；`./start.sh fullaudit` **7/7 通过**。缩略图数值校验：与源图同 cover 裁切参考的平均亮度 178.5 vs 179.0、逐像素平均差 13.8（≈ 246 色量化噪声），占用满 246 个可用色槽。`bump_version` → `0.3.006`。

---

<a id="c36"></a>
### 0.3.005 — 004 结局章末尾插入 cg01 + Neon 夸 Fei / Fei 回「色猫」七句对白

`nbook004.nb`（`bond_neon` 分支的结局章）末尾、既有 3 句对白之后 `scene(end)` 之前，追加 `char(hideall)` → `cg(){cg01}` → 7 句英文对白：Neon 主动夸 Fei 身材，Fei 以 `You perverted cat.`（色猫）回嘴，Neon 再反将一军。

- **顺序硬性**：`char(hideall)` 必须在 `cg()` **之前**。`display_apply_cg()` → `layer_bg_change()` 内含 `layer_redraw_sprites()`（`scene_display.c:166`），立绘层独立于背景层，不先隐藏则 fei/neon 立绘会叠在 2048×1152 的 CG 上。
- **衔接既有设定**：Neon 反驳句复用「the sea」，回扣本场她 `I just want to stay at the beach` 的别扭性格；Fei 末句反击 `you are the one wearing the swimsuit`，回扣她本场是 `swimming` 立绘。全部行 ≤70 字符（`NB_LINE_MAX`=256）。
- **CG 副作用（知情告知）**：`cmd_cg()` 绘制前即 `sys_save_unlock_cg(1)`（`nb_cg.c:73`）→ 玩家只要走到 004 结局分支，**cg01 即永久解锁进画廊**（`cg01` 在 `ASSETS.DB` 中为 CG 类、id=28，`cg_id`=1 首位槽位），无法再补解锁。
- **i18n（仅英文，留空待译）**：`source_lang="eng"`，7 句新对白以英文为基准入库 `game_<lang>.txt` 空值，运行时 `tr()` 回退英文——与既有剧情对白现状一致（全库仅 `Special` 等少数系统项有译文）。用户明确本轮不补译文。
- **顺带根治 i18n 提取遗漏**：`cg(){key}` 的花括号负载是**资产 key**（同 `bg`/`char`），此前未列入 `extract_texts()` 的排除元组，导致一旦有场景用 `cg()` 就会往 9 个 `game_*.txt` 注入伪键（本次即产生 `cg01=`）。已在排除元组补 `'cg'`，并定点清除该残留键；`i18n_gen` 重生成后 `game=37`（30+7）、**无 `# ORPHANED`**。
  - 附记：`i18n_gen --force` 是**破坏性**的——先 `unlink()` 模板再 merge（`i18n_gen.py:250-254`），会连同 `Special=特别篇` 等全部既有译文一起清空，不可用于清理孤立键。
- 未动 `expressions.json` / `characters.json` / `variables.json`（不新增表情、不引好感度变量）；未改 B92（未增删改 NB 命令）/ B90（无 C 改动）。
- 验证：`nb_validator` 0 errors；`i18n_gen` 9 语言 `sys=34 role=3 game=37` 且无 ORPHANED；`makegame.sh build/make demo-a2` 成功；`./start.sh fullaudit` 7/7 全绿；`bump_version` → 0.3.005（demo-a2/animatest 同步）。
---

<a id="c35"></a>
### 0.3.004 — 设置菜单九语言译文补齐：速度档标签入表 + tr() 化

`#c34` 落地设置场景时，三档速度标签按 AGENTS.md §十四「纯数字」例外留作未译的 `16/s`/`32/s`/`64/s`；本轮把它们正式纳入翻译体系——单位随语言书写（`字/秒`、`자/초`、`car./s`、`Z./s`），符合「系统界面文字一律经 tr()」的强制范围。

- 标签入表（与取值同源同长）：`settings.h` 新增 `extern const char *const SETTINGS_TEXT_SPEED_LABELS[SETTINGS_TEXT_SPEED_N]`，`settings.c` 定义为 `{"Instant","16/s","32/s","64/s"}`（English `tr()` key）。两数组共用 `SETTINGS_TEXT_SPEED_N` 长度宏 → **下标错位无法编译**，`values[i]` 与 `labels[i]` 恒成对。
- `nb_setting.c` 表驱动化：`SettingRow` 删 `const char *(*label_of)(int value)` 回调、增 `const char *const *labels` 字段，绘制改走 `tr(r->labels[r->cur])`；`speed_label()` 的 if 链随之删除。取值文案由「每设置一个函数」降为「纯数据」，加一项设置仍只加一条表项，且值→文案不再散落。
- i18n：`i18n_gen.py` `SYSTEM_UI_KEYS` 增 `"16/s" "32/s" "64/s"`；九语言 `sys_*.txt` 补译 —— chi/cht `16 字/秒`、jpn `16字/秒`、kor `16자/초`、fre/ita/spa/por `16 car./s`、ger `16 Z./s`（32/64 同形）。`i18n_gen` 重生成 9 语言 `sys=34` 全齐、无 `# ORPHANED`；CJK 字库自动吸收新字（jpn 128→129、chi 118→119、cht 117→118、kor 210→211 codepoints）。
- 前置核查：`tr()` 为纯 `strcmp` 精确匹配线性扫描（`core/lib/tr.c:147`），载入侧只跳过空行/`#` 注释并按首个 `=` 切分（`load_file`），**数字开头的 key 无特殊处理** → `16/s` 作为 key 安全。
- 文档同步：`docs/B90` `cmd_settingmenu()` 条目补「labels 与 values 索引对齐、经 tr() 渲染」；`docs/B92` `settingmenu` 行同补。
- 验证：`make -C core` 0 errors / 0 warnings；`nb_validator` OK；`pytest tools/tests/` 469 passed；`./start.sh fullaudit` 7/7 全绿；`bump_version` → 0.3.004（demo-a2/animatest 同步）。
---

<a id="c34"></a>
### 0.3.003 — 游戏内设置菜单场景：Text Speed 迁出开机菜单 + settingmenu 落地

主菜单 `settings` 按钮不再打 TODO 日志，接到新的游戏内设置场景（`setting.nb` → `cmd_settingmenu`）；开机菜单（`settings_menu.c`）保留 Language + Start Game，**Text Speed 移入新场景**。视觉/交互范式对齐 LOAD 范式（`nb_saveload.c` / `nb_special.c`）：凹刻行全屏列表 + 行内 `< 值 >` + Back + `focus_on_back`。

- 新增 `core/engine/nb_setting.c`：表驱动 `SettingRow`（`label`/`values`/`n_values`/`cur`/`current`/`label_of`/`commit`），加一项设置只需加一条表项，文件内无设置专属分支。行矩形 `(120,y,400,44)`，`y={90,146,202,258}`，焦点符 x=126，标签 x=140/宽 170，`<` x=330，值区 x=350..430 居中，`>` x=450，Back y=352。
- 交互：`↑↓` 移焦（行 ↔ Back）；`←→` 步进聚焦行取值（环形）；设置行上 `Enter`/`Space`/`Xfer` **无操作**（取值就地生效，无可确认项），仅 Back 聚焦时退出；`Esc` 任意位置退出。`←→` 已被调档占用，故**无键盘翻页**，翻页箭头在行数超 `SETTING_ROWS`(4) 时自行出现（当前仅 1 项 1 页）。调档走 `commit` 立即生效（下一段对话即新速度），退出时仅在 `dirty` 时调**一次** `settings_save()`。
- 单一事实源：`settings.h` 新增 `SETTINGS_TEXT_SPEED_N` / `extern const int SETTINGS_TEXT_SPEEDS[]`，`settings_set_text_speed()` 与 `settings_load()` 的校验均改为遍历该表（原先三处各自硬编码 `{0,16,32,64}`）。返回值越界仍回退默认。
- 开机菜单 `settings_menu.c` 精简：删 `SPD_VALUES`/`N_SPEEDS`/`SPD_Y`/`SPD_NAME_SAVE_*`/`IND_CLEAR_Y_SPD`/`SPD_CLEAR_*`/`FOCUS_SPEED` + `speed_label()`/`find_speed_index()`，`menu_hittest` 由 5 分支收为 3 分支（0=左箭头/1=右箭头/2=Start/−1 无），`full` 由 3 态收为 2 态（全量 / 焦点），三处重复的指示符「擦+重绘」抽为 `settings_draw_indicator()`。
- **Language 永久留在开机菜单**：该菜单运行于 `tr_init()` + CJK 字库加载**之前**，必须纯 ASCII，且语言须在翻译表存在前选定；`nb_setting.c` 表内不得新增 Language 行（文件头注释与 AGENTS.md §十四 已固化）。
- 接线：`nb_mainmenu.c` 删旧桩 `cmd_settingmenu`（`nb_commands.h` 原型保留，实现迁至 `nb_setting.c`），`settings` 分支改 `nb_set_menu_return("")` + `scene_switch("setting.nb", SCENE_SWITCH_MENU)`；`nb_commands.c` 标志 `0` → `CMD_BLOCKING | CMD_NEEDS_INPUT | CMD_TOUCHES_DISPLAY`。新增 `projects/demo-a2/scene/setting.nb`（`sceneconf(){Settings, menu}` + `bg(normal){yellow_grid}` + `settingmenu()`，背景沿用 special 菜单）。`animatest` 无 settings 入口且 `i18n.targets=[]`，未改。
- 退出归属：`setting_return_home()` 在**退出时**读 `nb_get_menu_return()`，空则回落 `mainmenu.nb`（同 `gallery_return_home`），杜绝陈旧值被下次进入消费。
- i18n：`i18n_gen.py` `SYSTEM_UI_KEYS` 增 `"SETTINGS"`；九语言 `sys_*.txt` 补译（chi 设置 / cht 設定 / fre PARAMÈTRES / ger EINSTELLUNGEN / ita IMPOSTAZIONI / jpn 設定 / kor 설정 / por CONFIGURAÇÕES / spa AJUSTES）。取值标签 `16/s`/`32/s`/`64/s` 为纯数字+单位，按 AGENTS.md §十四 例外**不译**。`i18n_gen` 重生成 9 语言 `sys=31` 全齐、无 `# ORPHANED`。
- 文档同步：`docs/B92` `settingmenu` 行由「TODO 桩」改为实际语义；`docs/B90` 新增 `cmd_settingmenu()` 条目、`cmd_mainmenu()` 行去掉旧桩；AGENTS.md §十四 固化 Language 归属规则 + 头部版本 0.3.003。
- 验证：`make -C core` 0 errors / 0 warnings（`NB_DEBUG` 展开 `snprintf`，`debug.h` 不含 `stdio.h`，故本文件保留 `<stdio.h>`）；`bump_version` → 0.3.003（demo-a2/animatest 同步）；`pytest tools/tests/` 23 passed；`./start.sh fullaudit` 7/7 全绿。
---

<a id="c33"></a>
### 0.3.002 — 资产市场交互菜单启动清屏一次（TTY 守卫）

资产市场交互菜单（`market.sh` 无参 / `market.sh menu`）启动时清屏一次，取代原先「每轮重绘前打一个空行」的凑合分隔；下载日志留在菜单上方，菜单在其下重绘。

- `tools/naiz_market/market.py`：新增常量 `CLEAR_SCREEN = "\033[2J\033[H"` + 助手 `clear_screen()`（Helpers 段），`Menu.menu()` 在 `while` 循环**之前**调用一次（早于 `packs()` 取树，错误信息也落在干净屏幕上）；`first` 标志取代无条件 `print("")`，首屏不多打空行。
- 守卫：`sys.stdout.isatty()` 为假（重定向 / 过管道）或 `TERM=dumb` 时直接返回 → `list`/`cats`/`get`/`get-all` 与管道输出不受影响（本就未接入）。纯 `sys.stdout.write` 转义，不引 `os.system`/子进程（P14）；`market.sh` 保持纯包装未改。
- `tools/tests/test_naiz_market.py`：新增 4 例 —— TTY 发转义 / 非 TTY 不发 / `TERM=dumb` 不发 / `menu()` 跑满两轮（`input` 返 `1` 再 `0`）清屏计数 `== 1`（钉死「一次」而非「每轮一次」）。`pytest tools/tests/test_naiz_market.py` 23 passed。
- 文档同步：`docs/B90-参考-函数索引.md` market 行、`naiz-guildbook/pages/tool-market.html` `menu` 行 + 清屏作用域说明。
- 验证：`bump_version` → 0.3.002（demo-a2/animatest 同步）；`./start.sh fullaudit` 全绿。
---

<a id="c32"></a>
### 0.3.001 — 0.3 开版（minor 进位）

`bump_version --minor`（0.2.148 → 0.3.000）+ `bump_version`（→ 0.3.001），双项目同号；0.2 收官文档见 `#c31`，待实施/挂起项（72/83/95/96/97/100/101/102、94/98）转 0.3 输入。
---

<a id="c31"></a>
### 0.2.148 — 0.2 收官：devdocs 68–115 归纳为 0.2 版开发文档总结

0.2 版开发结束 characteristic 归档：`devdocs/0.2版开发文档总结.html`（65KB，仿 0.1 模板样式/分组/卡片结构），7 组 48 篇全覆盖（程序校验 doc id 68–115 无缺号、无残留占位）。

- 一、调研审计与早期方案（68–72）；二、NAIZ_ANIM 动画链（73–83，73–76 标已过时由 77 取代）；三、层管理统一/调试导出/CJK 加载（84–87）；四、CG 全功能链（88–95，94 挂起 2 实机项 + 二期缩略图）；五、对话框图层化/CJK 精简/整合审计（96–99，96 未实施、98 目检挂起）；六、归档/音频/分离改造/打字机（100–107，100/101/102 待实施）；七、光标契约系列 + Special 菜单（108–115）。
- 原 md 零改动（只读归纳，遵守已完结文档禁改规则）；待实施/挂起项在状态签与落点中如实标注，转 0.3 输入。
- `bump_version` → 0.2.148（demo-a2/animatest 同步）。
---

<a id="c30"></a>
### 0.2.147 — guildbook 新增两篇：cf07 图片登记 + tool-market 资产市场

`images.map` 与 `market.sh` 此前在 guildbook 无网页说明，补两篇（仿既有模板与卡片样式，链接闭环已验）：

- `pages/cf07-图片登记.html`（基本概念/配置）：格式实例、六选项表、入库三步（map→ASSETS.DB→build）、8.3/key/剧本引用约束、退役 4 层；注册进 `sidebar-reference.js` 配置节 + `manual.html` 加卡。
- `pages/tool-market.html`（制作工具）：包定义与显示名规律、`market.toml`、list/cats/menu/get/get-all 子命令表、通用参数与 `--force` 覆盖、素材入库衔接；注册进 `sidebar-tools.js` + `tools.html` 加卡（intro 从三篇改为四篇）。
- `bump_version` → 0.2.147（demo-a2/animatest 同步）。
---

<a id="c29"></a>
### 0.2.146 — 删除旧背景 seasidebg/splbg（4 层清理）

`beach1/homeday/homenite` 上线后，旧背景 `seasidebg`（id=7）、`splbg`（id=0）退役：删前确认 scene/*.nb、expressions.json（引用 id 1,2,3,8–12）、tests 零引用。

- `assets/demo-a2/images.map` 去 2 行；源 PNG 2 个 + `projects/.../images` 下 MAG 2 个删除；`ASSETS.DB img_map` DELETE 2 行；`.mag_conv_state.json` 去 2 签名。
- **验证**：`./makegame.sh build demo-a2` 全绿（0 转换/validator 0 errors）；IMAGE.DAT 29 entries 中两图消失（删位留空槽，存量 asset id 不漂移，`cg01`=28 稳定）；968553 bytes。
- `bump_version` → 0.2.146（demo-a2/animatest 同步）。
---

<a id="c28"></a>
### 0.2.145 — 新图 cover 全屏 + images.map 英文选项注释

demo-a2 新增 4 图（beach1/homeday/homenite/cg01）之前按默认 contain 转出，居中贴留黑边；现 4 行补 `--cover`（`resize_to_screen` 按长边缩放占满 640×400、居中裁溢出，保持比例无变形），重转后解码验证皆为 640×400，IMAGE.DAT 重打 29 entries，validator 0 errors。

- `assets/demo-a2/images.map` 头注释改写为英文完整说明：格式、8.3 约束、增量重转规则、`--256color/--sprite/--cover/--dither/--no-resize/--filter-white` 六选项语义；`assets/common/images.map` 头加指向全文的英文短注（条目零改动，不触发重转）。
- `bump_version` → 0.2.145（demo-a2/animatest 同步）。
---

<a id="c27"></a>
### 0.2.144 — demo-a2 新增 4 图登记入库（3 背景 IMG + cg01 CG）

`assets/demo-a2/png/` 下 4 个未跟踪新素材完成注册并入库：`bg/bg-beach1.jpg`、`bg/bg-home-day.jpg`、`bg/bg-home-night.jpg`（JPG，`mag_convert` 经 PIL 直转）→ `type='IMG'`；`cg/cg01.png`（3.7MB）→ `type='CG'`（进 `cg_map`，`cg()`/画廊可用）。

- `assets/demo-a2/images.map` +4 行：8.3 约束下 MAG 短名取 `beach1/homeday/homenite/cg01`（`bg-beach1` 等原名超 8 字符，截断会撞 HDI 短名）。
- `projects/demo-a2/ASSETS.DB img_map` +4 行（id=25–28，key 与短名同名小写）；删无源孤儿 `projects/demo-a2/images/cg02.MAG`（无 scene/json 引用，`cg01.MAG` 旧 11KB 占位被新转 141KB 覆盖）。
- **验证**：`./makegame.sh build demo-a2` 全绿（4 MAG 新转、IMAGE.DAT 29 entries 含新图、`nb_asset_table.h cg_map={"cg01",28}`、调色板无违规、validator 通过）。
- `bump_version` → 0.2.144（demo-a2/animatest 同步）。
---

<a id="c26"></a>
### 0.2.143 — 市场下载同名跳过 + `--force` 逃生口（market.py）

`tools/naiz_market/market.py` 下载行为变更：目标路径已存在（同名文件）时**默认跳过**，不重复下载、不覆盖；需要刷新时加 `--force` 强制重新下载并原子覆盖。

- `download_pack`：每个文件先查 `target.exists()`，命中且未 `--force` → 打印 `SKIP (exists)` 并 `continue`（实跑与 `--dry-run` 均生效，检查纯本地无网络）；`n` 计数仍含跳过文件，`Done: N packs · M files` 语义不变。
- `copy_license`：同样 `target.exists()` 跳过（返回 1 计入文件数），`--force` 覆盖。
- CLI：四个子命令（list/cats/menu/get/get-all）统一新增 `--force`（`add_common`），`Market.__init__` 增加 `force` 参数；`market.sh` 透传无需改动（`"$@"`）。
- 测试：`test_download_overwrites_existing` 改为 `test_download_skips_existing`（存量内容保持不动 + SKIP 输出）；新增 `test_download_force_overwrites`、`test_license_skipped_when_present`；一并更新模块 docstring 措辞。
- **验证**：pytest 465 passed（原 463 + 新 2）；`./start.sh fullaudit` 7/7 `[✓]`。`makegame.sh build + make demo-a2` 更新 HDI（版本号同步）。
- `bump_version` → 0.2.143（demo-a2/animatest 同步）。

---

<a id="c25"></a>
### 0.2.142 — 菜单增量 blit 跨行距拷贝根修 + VRAM 紧凑缓冲契约审计（devdoc 115）

NP2kai 目检：从 special 菜单返回主菜单后 continue/start 两键花屏（杂点/横线乱码）。根因为**跨行距拷贝**（`vram_read/write` 契约 = 紧凑缓冲，行距必须等于参数 `w`）：

- **`menu_layer_blit_rect`（menu_layer.c:139，不透明分支，唯一实测 bug）**：把 640 行距的 composite **切片**当紧凑缓冲传给 `vram_write(..., w=按钮宽100, h=34)` → 第 0 行正确、第 1..h-1 行全部错位 → 键面横线乱码。触发面 = `menu_label_draw`（nb_menu.c:220），`menu_show` 类菜单（主菜单/设置）**按任意方向键即花**；special/LOAD/画廊只走全量 blit 不受影响。「返回后才花」仅是当时按过一次 ↓（sel 0→2，重绘 continue+start）。修复 = 不透明分支改**逐行 `vram_write`（h==1，行距无关）**。
- **`cursor_composite_splice`（cursor.c:333，同族潜患一并拔除）**：保存光标盒下背景用一块 24×24=576 连续字节 memcpy，源行距却是 480 → 必然跨行；鼠标完整移入叙述框后离开时 `cursor_erase` 用损坏背景擦除旧盒 → 框内斜纹残影（文本静止时持续）。修复 = 24 行逐行拷贝。光标常态路径（24×24 紧凑）本就正确。
- **同族全量审计**：全代码库 `vram_read/write` 九处调用方 + bg/dialog/sprite/transition 各拷贝面逐条核对，仅上述两处需动（devdoc 115 §4 表）。透明 blit 分支、`menu_layer_erase_to_base`（显式 640 行距）、对话框 480×115 紧凑缓冲均合规。
- **验证**：`make -C core` 0 errors / 0 warnings；pytest 463 passed；`./start.sh fullaudit` 7/7 `[✓]`。`makegame.sh build + make demo-a2` 更新 HDI。
- `bump_version` → 0.2.142（demo-a2/animatest 同步）。

---

<a id="c24"></a>
### 0.2.141 — Special 菜单视觉修正：Back 文字截断根修 + 行按钮缩半居中（devdoc 114 反馈轮）

NP2kai 目检反馈两处问题并修复：

- **Back 文字空白根修（共享 UI bug）**：`menu_back_draw`（nb_menu.c:96）调用 `draw_text(tr("Back"), 0, tx, y+7, 80, **30**, 1, color)`——`draw_text` 的第 6 参是 **y 坐标截断**（`render_text.c:136 if (y >= max_y) return`），常量 `30` 使 y=352+7=359 ≥ 30 恒早退 → **所有菜单（LOAD/special/CG 画廊）的 Back 文字从未画出**，只剩凹刻框。改传 `y+30`（按钮底边坐标，与行文字 `y+36` 同语义）。此 bug 同样影响 LOAD/画廊 Back，一并根治。
- **special 行按钮布局**：宽度 480→**240**（`(640-240)/2 = 200` 居中，SPECIAL_BTN_X/W）；行标签按 `text_width` **居中于各自按钮**（`lx = 200 + (240-lw)/2`，焦点 `>` 指示条留守按钮内左缘 206），鼠标命中区同步改 `[200,440)`。
- 渲染管线：凹刻（全量）+ 指示条/居中标签（增量）仍在 `menu_layer_begin_draw/commit/blit` 两阶段内，翻页全量重绘 + cursor_force 保持（AGENTS §十四 / C17）。
- **验证**：`make -C core` 0 errors / 0 warnings；pytest 463 passed；`./start.sh fullaudit` 全 `[✓]`；`makegame.sh build + make demo-a2` 更新 HDI。NP2kai 目检：Back 返回文字可见、3 行按钮 240 宽、标题（音乐/music 等）居按钮正中。
- `bump_version` → 0.2.141（demo-a2/animatest 同步）。

---

<a id="c23"></a>
### 0.2.140 — Special 菜单落地：LOAD 范式全屏列表 + 菜单归属场景收口（devdoc 114）

主菜单重设计：新增 special 菜单承载 gallery/scenes/music，主菜单只留 continue/load/start/special/settings/exit；special 的布局/行为/显示方式完全对照 LOAD 读档场景。

- **引擎**：新建 `core/engine/nb_special.c` 命令 `specialmenu(gallery,scenes,music)`——LOAD 范式全屏列表：`draw_title_large` 标题 + 凹刻行 `draw_rounded_emboss(80,row_y[i],480,44,SAVE_SLOT_R)` + 分页条 `menu_pagenav_draw` + Back + `focus_on_back` 模型，两阶段增量渲染（§十四 合规）；条目经 `tr()` 渲染（sys_<lang> 已有 gallery/scenes/music/Back 译文）。
- **保留分页**（用户定案）：每页 4 行复用 slot_y 几何，`menu_pagecount(argc,4)` 总页、首/末页箭头自动隐藏、`%d/%d` 恒显；Left/Right 切页、鼠标箭头同 LOAD；翻页全量重绘 + `hal_mouse_draw_cursor_force()`（C17）。
- **路由**：`gallery`→`nb_set_menu_return("special.nb")` + cgview.nb；`scenes`→CAPTURE_TEMP + OPEN_LOAD（Esc 靠 temp 快照回 special 画面）；`music`→TODO 桩；Back/Esc→mainmenu.nb；未知项 NB_DEBUG 告警（消灭静默失败）。
- **菜单归属场景**：`g_menu_return[64]` + `nb_set/get_menu_return()`（str_copy 收口，C32）；`nb_cggallery.c` 两处退出改 `gallery_return_home()` 读父场景，空回退 mainmenu.nb；mainmenu special/gallery 分支先清归属（读写点相邻，无陈旧污染）。
- **场景脚本**（demo-a2）：mainmenu.nb 按钮序列 → `continue,load,start,special,settings,exit`（exit 末位约定保持）；新建 special.nb：`sceneconf(){Special, menu}` + `bg(normal){yellow_grid}`（id13）+ specialmenu。
- **i18n**：`i18n_gen.py` menu_options 收集扩展 `cmd in ('mainmenu','specialmenu')`（specialmenu 全量 args，mainmenu 依旧 args[4:] 跳坐标）；`SYSTEM_UI_KEYS` 登记标题键 `"SPECIAL"`（§十四 规则 3，防重生成 ORPHANED）。
- **守卫测试**：新增 `tools/tests/test_i18n_menu_options.py`（+3 例 = 463）：mainmenu 引擎按钮收集 / specialmenu 条目收集 / 条目不作对白泄漏，全部基于真实项目场景文件；`test_cmd_meta.py` 自动覆盖新命令 flags（BLOCKING|NEEDS_INPUT|TOUCHES_DISPLAY）。
- **验证**：`make -C core` 0 errors / 0 warnings；pytest 463 passed；`./start.sh fullaudit` 全 `[✓]`（6/6 节）；`makegame.sh build demo-a2` 含 special.nb / yellow_grid / i18n 重生成。NP2kai 目检：主菜单 6 键、special 黄色网格 LOAD 式列表、gallery/scenes/Back 返回路径、每场景切换黑屏。
- `bump_version` → 0.2.140（demo-a2/animatest 同步）。

---

<a id="c22"></a>
### 0.2.139 — 资产市场工具落地：整包下载器 market.sh（独立 naiz_assets 仓库）

新工程基建：独立公开市场仓库 `edouardlicn123/naiz_assets`（MIT）落地根级市场工具，供项目按需拉取外置资源包（图片等），不占用本仓体积。

- **工具链**：根 `market.sh`（venv 转发，无参数默认 `menu`）+ `tools/naiz_market/market.py`（stdlib 零新依赖）+ `market.toml`（`[market] repo="edouardlicn123/naiz_assets" ref="main" dest="assets_samples"`）。落点 `assets_samples/` 已入 .gitignore。
- **模型与规律（AGENTS §十三 强制，脚本必须遵守）**：市场仓库**顶层目录 = 一个资源包**，整包下载、不做文件级选择；**包显示名规律** = 目录名按 `_` 切分、首段 `()` 包裹、余段空格连接（`images_sample_scenebg` → `(images)sample scenebg`）；`list`/`menu` 一律按此显示，包解析接受 原始目录名 / 后缀种类名（公共前缀 `images_sample_` 剥离后 `scenebg`）两种。
- **下载语义**：Trees API（`truncated` 校验）取清单 → `raw.githubusercontent.com` 逐文件；`Path` 边界校验（拒 `..`/绝对路径，`resolve().is_relative_to`）；`.part` 原子写 + 与清单 size 比对后 `os.replace`；**总是覆盖**；每次下载运行统一写 `<dest>/LICENSE`；网络/HTTP/size 不符/未知包 → `MarketError` + `exit 1` 硬失败（消灭静默失败）。
- **CLI**：`menu` 交互式数字编号（`N`/`N,M`/`N-M`，`a` 全选，`0`/`q` 退出，EOFError 容错）/ `list` / `cats` / `get <包>...` / `get-all`；`--repo/--ref/--dest/--config/--dry-run`（dry-run 只列计划不动盘）。
- **守卫测试**（`tools/tests/test_naiz_market.py`，+17 例 = 460）：命名规律、公共前缀与 kinds 回退、根级文件过滤、包解析（精确/种类/未知报错）、整包落盘与**覆盖原子写**、size 不符拒绝、dry-run 零写入、LICENSE 拷贝、路径穿越防线、菜单解析（含降序区间拒绝）、配置缺失报错。网络层全 monkeypatch 离线。
- **验证**——`pytest 460 passed`（443+17）、`py_compile` 双文件通过、`bash -n market.sh` 通过、`list` 实联（trees API）成功列包、dry-run get 走通、`make -C core` 0 err/0 warn、`./start.sh fullaudit` 全绿；ob repo 22 资产（scenebg 14 + charactor_schoolgirl 8）。**doc**：docs/B90 §三 登记 `tools.naiz_market.market` 行、AGENTS §十三 增强制规律条目、AGENTS 头版本同步。`bump_version` 双项目 → 0.2.139。真机 `market` 实下载整包入 `assets_samples/` 留人工（资源属外置、不入 HDI）。

---
### 0.2.138 — 光标移动残影根治：splice 只进一次性书写副本，持久合成缓冲不烘烙（devdoc 111）

0.2.137 后用户反馈：**「暂时不闪烁了，但鼠标移动有残影」**——c20 忙于以零缺窗替换缺窗，却给下个问题埋了雷。**根因**：c20 的 `cursor_composite_splice` 把活箭头就地混进**跨 pass 持久化**的合成缓冲 `dialog_layer`；demo-a2 使用 dither 对话框样式（`projects/demo-a2/scene/settings.txt` `dlgstyle=5`），`dialog_paint_box` 的 dither 孔位像素**保留缓冲旧内容**，且 `layer_dialog_clear()`/`layer_dialog_show()` 不做 `dialog_seed_base()` 全幅重绘 → 鼠标移动后旧位置箭头像素残留在持久缓冲里，随后被任意一次 `dialog_layer_blit` 写回 VRAM / 被下次 splice 的 `memcpy` 采作 `cursor_saved.buf` 背景 → 移动残影（C18 快路径副作用核对缺失：splice 把「含箭头的缓冲」拷进防残影基准，等于永久化了自我的污染）。devdoc 110 的「透明/部分缓冲禁止 splice」只堵了部分缓冲，漏掉**不透明+洞（dither）**的持久缓冲自污染路径。

- **方案（箭头只进一次性书写副本）**：新增 `static unsigned char *dialog_blit_tmp`（layer_dialog.c）——`dialog_layer_blit()` 的 opaque touch 之后改为 `memcpy(dialog_blit_tmp, dialog_layer, W*H)` → `cursor_composite_splice(dialog_blit_tmp, LAYER_DIALOG_W, ...)` → `vram_write(dialog_blit_tmp, ...)`；**持久 `dialog_layer` 永不含箭头**，残影无源。顺序仍 touch < splice < vram_write，无 vblank、无额外 VRAM 流量（只多一次 55KB RAM memcpy）；tmp 未分配（OOM 降级）时回退直接写 `dialog_layer`（不 pre-compose）。`layer_dialog_show()` 首次分配块追加 `dialog_blit_tmp = layer_snapshot_alloc_dialog("dialog_blit_tmp")`，`layer_dialog_reset()` 配套释放。
- **守卫测试**（`tools/tests/test_cursor_layer.py`，+1 例 = 443）：`test_dialog_blit_tmp_buffers_arrow_away_from_persistent_composite`（体内**不出现** `cursor_composite_splice(dialog_layer`、`memcpy` 在 splice 之前、tmp 在 show 分配/reset 释放）；原 `test_dialog_layer_blit_splices_before_vram_write` 改为断言 splice 目标是 `dialog_blit_tmp` 且仍位于 touch 与 `vram_write` 之间。
- **验证**——make 0 err/0 warn（engine.exe+engine_a.exe 双变体）、pytest **443 passed**（442+1）、`./start.sh fullaudit` 7/7 全绿（日志 `logs/fullaudit_20260922_113636.log`）、**AUTOEXIT 无头回归**（串口 `End` + `VE:0..5` 收尾）→ 回归后 build/make 复原正常引擎入 HDI（`games/demo-a2/engine.exe` md5 == `core/engine.exe` = `3e501f92…`）；`bump_version` 双项目 → 0.2.138。

---

<a id="c20"></a>
### 0.2.137 — 光标写入全程零缺窗：对话框合成缓冲预拼光标（devdoc 110）

0.2.136 后用户仍报告两症状：①打字机揭示时鼠标停在对话框上**仍闪烁**；②人物切换表情时鼠标**消失**。**根因（0.2.136 只修了一半）**：光标箭头只在每次 pass 末尾 `hal_mouse_draw_cursor()` 被重建——pass 中段所有覆盖/擦除它的写入（reveal 的 `dialog_layer_blit` 480×115 composite 经 DOS/4GW bank 切换 VRAM 窗口整块 `vram_write`，NP2kai 上数 ms~十几 ms；表情切换 `layer_sprite_face` 的 invalidate 擦除 + bg restore + `vram_blit_sprite` 突发）一发生箭头即缺席，直到 pass 末才回补。0.2.136 的 stale 同位置直绘只消除了 `cursor_render` 尾部 ≤16ms vblank 等待，**写入自身时长窗口依旧**：~20 pass/s 下箭头每帧缺失一大段 = 低抖闪（①）；一次性毫秒级粉丝突发时 = 「鼠标消失」一闪（②，光标停角色/舞台区 y<280 时最明显）。两症状同源：pass 末回补太晚，写入期间零覆盖。

- **方案（把光标拼进合成缓冲，写入全程零缺窗）**：新 `int cursor_composite_splice(unsigned char *buf, int stride, int fx, int fy, int fw, int fh)`（cursor.c/cursor.h）——当当前光标盒**完整落入**上报的矩形 `(fx,fy,fw,fh)` 时：①先从**缓冲 RAM** 把盒区域原文（对话框正文）拷为 `cursor_saved.buf`（防残影基准）；②按 `is_fill_pixel→PAL_WHITE` / `is_cursor_pixel→PAL_CURSOR_BLACK` / 透明→保留缓冲内容，把箭头画进缓冲盒偏移处（与 `cursor_draw` 同混合模型）；③置 `valid=1`、更新位置。**无 vblank、无 erase、无额外 VRAM 流量**；未命中返回 0。
- **`dialog_layer_blit`（layer_dialog.c）**：opaque touch 之后、`vram_write` 之前调 `cursor_composite_splice(dialog_layer, LAYER_DIALOG_W, LAYER_DIALOG_X, ...)` → 一次 `vram_write` **全程带着箭头**登陆，写入再慢也无缺窗；pass 末 `cursor_render` 因 `valid && 同位` 早退。跨边盒仍走 touch erase + pass 末直绘；透明/部分缓冲**禁止** splice（活箭头会被烘进持久背景重演 devdoc 108 残影）。精灵/舞台侧（bug ②）保留 0.2.136 pass 末 immediate 直绘兜底（缺窗=精灵写入时长，一次性毫秒级），真机目检复核留人工。
- **守卫测试**（`tools/tests/test_cursor_layer.py`，+2 例 = 442）：`test_dialog_layer_blit_splices_before_vram_write`（splice 调用位于 touch 与 `vram_write` **之间**）；`test_cursor_composite_splice_blends_and_adopts_bg`（实现含 `is_fill_pixel`/`is_cursor_pixel`/`memcpy`（背景先存后拼）/`valid = 1`，且**不含 `hal_vblank_wait`**）。
- **验证**——make 0 err/0 warn（engine.exe+engine_a.exe 双变体）、pytest **442 passed**（440+2）、`./start.sh fullaudit` 7/7 全绿、**AUTOEXIT 无头回归**（串口至 `End` + `VE:0..5` 收尾）→ 回归后 build/make 复原正常引擎入 HDI（`games/demo-a2/engine.exe` md5 == `core/engine.exe`）。
- **无头回归操作修正（本轮踩坑）**：深屏锁屏会抢焦点致 xdotool 完全不可达——需解锁后重试；NP2kai 鼠标整合需 toml `Mouse_sw = true`（`~/.config/wxnp21kai/wxnp21kai.toml`，`write_emulator_toml` 保留该键）**且指针先在窗口内点击一次**才能把绝对坐标写入 PC-98 鼠标口（`nx/ny` 才非 0），随后拆分 mousedown/mouseup 点 Settings Start（跨 poll ≥0.4s，click 12ms 丢边坑不变）。
- **doc**：devdoc 110 落定「已落地」（109 保持「已落地」不改）、B90 增 `cursor_composite_splice` 行、AGENTS 头版本同步。版本 0.2.136→0.2.137（bump_version 统一 animatest+demo-a2）。

<a id="c19"></a>
### 0.2.136 — 光标揭示顿闪消除：写后直绘 + 不透明矩形快路径（devdoc 109）

用户 bug 报告「文字逐个打出（打字机揭示）时，鼠标在聊天框会闪烁」。**根因（阅读代码确认）**：reveal 激活期间 `dialog_layer_blit()`（layer_dialog.c:217）**每 pass 无条件**执行（即使该 pass 未推进字符）→ 其前置 `hal_mouse_touch_cursor(对话框矩形)` 与光标 24×24 保存区重叠 → `cursor_erase()` **立即**把旧背景写回 VRAM（箭头像素从扫描管消失，该写不与 vblank 同步）；随后 `vram_write` 写新文字；而本 pass 末尾 `hal_mouse_draw_cursor()` → `cursor_render()`（cursor.c:138）先在 `hal_vblank_wait()` **等下一次垂直消隐（至多 ~16ms）** 再重画光标 → 每 pass 光标缺席**≈一整帧**，reveal 约 20 pass/s → 箭头 ~20Hz「闪没-重现」= 闪烁。**方案 B（写后直绘 + 不透明矩形快路径）**：
- **`cursor_touch_opaque(x,y,w,h)`**（cursor.c/cursor.h/hal.h/hal_mouse.c，0.2.136）：`cursor_touch` 的**不透明变体**——调用方断言其写入会**逐像素覆盖整个上报矩形**（composite `vram_write` 等，非透明/部分写入）。重叠并经新辅助 `cursor_covered_fully()`（24×24 盒完整落入上报矩形）判定 → **跳过前置 erase** 仅 `valid=0`（写者像素替光标清场）；跨边（盒探出矩形）→ 照旧 erase+invalid。¥「跳过 erase」的权利只授予真正的全像素不透明写者——若授予 `render_blit_transparent`/OOM 部分文本等会重演 devdoc 108 残影（旧箭头被快照进背景），故其余写者一律维持 `cursor_touch`。
- **`cursor_render` stale 同位置直绘**：`!valid && draw_x==saved.x && draw_y==saved.y`（touch 失效且位置未动的稳态）→ **跳过 `hal_vblank_wait()` 立即 `cursor_draw()`**——擦/写均已在本 pass 发生、背景已由写者定型，无需再与 erase 配对同步 → 缺席区间从 ~16ms 缩至微秒级；移动/传送/`force` 路径保留原 vblank 同步防撕裂不变式。
- **`dialog_layer_blit` 改用 `hal_mouse_touch_cursor_opaque`**（其 composite vram_write 本就全像素覆盖整个对话框矩形，是 reveal 唯一热路径）。
- **C18 核对**：全 touch 调用点的「上报矩形 == 实际写入」逐站审计——`fill_dialog_bg`(fill_rect/fill_rect_pattern 全填)、`dialog_layer_blit`/`menu_layer_blit_rect`/`menu_layer_close`(vram_write 全矩形)、`layer_dialog_show` OOM(box 全填+描边) 为全像素；`menu_layer_blit`(render_blit_transparent) 与 `layer_dialog_render_page` OOM(draw_text 部分) 为透明/部分 → 只让前者进 opaque 快路径，后者维持 touch。

**守卫测试**（`tools/tests/test_cursor_layer.py`，+2 例 = 440）：`test_cursor_touch_opaque_skips_erase_when_covered`（`cursor_covered_fully` 谓词驻留、`!cursor_covered_fully` 才 erase、仍过 overlap 门）；`test_cursor_render_stale_redraw_skips_vblank`（stale 同位置直绘分支**不含 `hal_vblank_wait`**、移动路径仍保留同步对）；test 1 常量更新为 `hal_mouse_touch_cursor_opaque(LAYER_DIALOG_X,` 且仍先于 `vram_write`；`test_hal_forwards_touch` 增 opaque 透传断言。**验证**——make 0 err/0 warn（engine.exe+engine_a.exe 双变体）、pytest **440 passed**（438+2）、`./start.sh fullaudit` 7/7 全绿、**AUTOEXIT 无头回归**（串口至 `End` + `VE:0..5` 收尾，xdotool 拆分 mousedown/mouseup 消解 settings Start——click 12ms 内 press+release 落同一 poll 丢边）→ 回归后 build/make 复原正常引擎入 HDI（`games/demo-a2/engine.exe` md5 == `core/engine.exe`）。版本 0.2.135→0.2.136（bump_version 统一 animatest+demo-a2）。doc：devdoc 109 落定「已落地」、B90 `cursor_touch` 注解 + `hal_mouse_touch_cursor` 行补 opaque、AGENTS 头版本同步。真机 NP2kai 目检「打字机揭示时光标无闪烁」留人工。

<a id="c18"></a>
### 0.2.135 — 软件光标层契约落地 + 对话框抹字根因收口（devdoc 108）

用户 bug 报告「鼠标在剧情字幕上时，有时候会把文字抹去」。**现状确认：无独立光标图层**——软件侧光标是 cursor.c 的裸 VRAM save/restore 重叠层（`cursor_draw` 存 24×24 背景 / `cursor_erase` 恢复，不进 `LAYER_Z_*`，layer.c 只是 active 标志数组）；硬件侧 PC-98 GDC 直接扫描 VRAM **无光标/sprite 覆盖平面** → 真正的「扫描级独立层」不可行，只能软件合成。**根因（证据链）**：①光标停字幕上时 `cursor_draw` 存下当帧文本快照（cursor.c:113）；②打字机推进/翻页/`dialog_show` 时 `dialog_layer_blit()`（layer_dialog.c:209）把 480×115 合成区**直接 vram_write** 到 VRAM、覆盖光标像素，而 `cursor_render` early-return（cursor.c:149）不重画 → **静止光标消失**；③用户一动鼠标 `cursor_erase` 把**过期文本快照**恢复到新揭示的字上 → **抹字**。`dialog_layer_blit` 是对话框文字唯一 VRAM 写入漏斗却漏了前置 invalidate（B13 散点纪律失效的温床）。**方案：软件光标层契约**——把 save/restore 重叠层升级为带重叠检测的层：新增 `cursor_touch(x,y,w,h)`（cursor.c/cursor.h，四向相交 `bg->x < x+w && bg->y < y+h` 判定，**重叠才 erase+invalid 否则纯 no-op**）+ hal 透传 `hal_mouse_touch_cursor`（hal.h/hal_mouse.c）；契约=「任何写 VRAM 像素的模块必须先上报写矩形」。**落地**：①根治 `dialog_layer_blit` vram_write 前置 touch 对话框矩形；②同文件 OOM 直写路径补 touch（`layer_dialog_show` box、`layer_dialog_render_page` OOM 文本、`fill_dialog_bg` 存档槽位）；③menu_layer.c 三处 blit（`menu_layer_blit`/`menu_layer_blit_rect`/`menu_layer_close` restore）前置 touch；④既有 `layer_sprite×(5)`/`scene_display×(2)`/`layer_dialog_hide`/`scene_end` 的 `hal_mouse_invalidate_cursor` 强形式保留；拒绝 blit 后 `cursor_refresh` 备选（光标形状探出对话框上/左边界时残影被当背景存下 → 移动后幽灵，touch 重叠即擦整块无此窗口）。**守卫测试**：新 `tools/tests/test_cursor_layer.py`（5 例，解析 C 源码惯例——dialog_layer_blit touch 先于 vram_write、OOM/fill_dialog_bg 契约、cursor_touch 四向重叠消除无条件擦除、hal 透传、menu_layer 三 blit 前置）。验证——make 0 err/0 warn（engine.exe+engine_a.exe 双变体）、pytest **438 passed**（433+5）、`./start.sh fullaudit` 7/7 全绿；版本 0.2.134→0.2.135（bump_version 统一 animatest+demo-a2）+ build/make 重注入 + **AUTOEXIT 无头回归**（`test --auto --serial` 直启串口至 `End`：settings 经 xdotool 点击 Start 消解 → `scene(op)` → 主菜单 auto-select exit → `End` + `VE:` 收尾，无崩溃/无回归，回归后 build/make 复原正常引擎入 HDI）；devdoc 108 落定「已落地」；真机 NP2kai 目检「鼠标停字幕上推进/翻页后再移动」留人工。

<a id="c1"></a>
### 0.2.134 — 虚拟时钟下沉 HAL smooth 单一事实源 + 动画/BGM 时钟隐患收口（devdoc 107）

0.2.133 的虚拟时钟钳制只存在 `nb_dialog.c` 本地（`REVEAL_PASS_*_MS`），仅护打字机一处；动画 `anim_tick` 与 BGM/MIDI 调度 `audio_bgm_poll` 仍直接吃 raw 单次 delta，在同一 NP2kai 时钟洞（冻结 3-6s + 成块猛跳）里同样"冻结-爆发"——**H1**（洞内 δ=0 → 动画冻结；补齐瞬间 `steps`~250 被 180 clamp → 整 3s 动画 1 帧内跳完；时长漂移）、**H2**（`cur=now−wall0` 洞内停滞 → 音乐静默；补齐 → 事件背靠背连发；loop 复位 `wall0=now` 同吃洞）、**H4**（`hal_wallclock_ms()` 契约缺口：宏观秒级正确 ≠ 单次 delta 平滑，`now==0` 兜底在 NP2kai 是死代码）、**H3**（delay/选项超时按 pass 计数在 NP2kai 拉长 3 倍——**登记为已接受语义，不动代码**）。**方案（单一事实源 + 下沉 HAL）**：新增 `hal_wallclock_smooth_ms()`（hal_pc98.c / hal.h，常量 `SMOOTH_CLOCK_MIN_MS 40UL / MAX_MS 100UL`）——对 `hal_wallclock_ms()` 每 pass 增量钳制后单调累计，首 pass 返回 0（基线）；`delta==0`→MIN 地板续帧、`>MAX`→MAX 天花板防爆发，宏观 ≈ raw ≤0.1s/洞 相位误差、真机 DL≈55ms 两界不触发（smooth ≡ raw）。三消费方统一迁移（删 nb_dialog 本地钳制常量/回绕分支；anim 删 `now==0` 兜底与 `now<last_ms` 回绕、`steps>180` clamp 留纯防御；audio 的 `wall0` 起点与 loop 复位同源）。**验证**——make 0 err/0 warn；pytest **433 passed**（test_reveal_final_page.py 改 2 例增 2 例：`test_smooth_wallclock_bounds_in_hal` 解析 hal 断言钳制分支+常量驻留防回退、`test_reveal_no_wrap_reanchor_needed` 断言无回绕）；`./start.sh fullaudit` 7/7 全绿；AUTOEXIT 无头回归 HDI 直启串口至 `End`（settings 菜单改用 xdotool 鼠标点击 Start 消解——按键 Return 在无头 xdotool 下焦点不可靠）；**NP2kai `[AN]` 探针实证（probe build `NAIZ_CLOCK_PROBE` + `NAIZ_DEBUG=OFF` 清串口洪泛）：24 采样 `now` 单调 40→1080、delta ∈ {40,100} ⊂ [40,100]、无 0/负/千毫秒级跳变、无 180 帧爆发**——判据全过；`[BGM]` 因模拟器无 MPU-401（BGM disabled）无法采集，由单元测试+代码审查覆盖（同源 smooth，AN 实证等价证明单调性）；探针用毕零残留（`grep -n 'NAIZ_CLOCK_PROBE' core/` 为空），临时场景 `nbookprobex.nb` 与 op.nb 临时改点全部还原。devdoc 107 状态「已落地」+ §6 探针数据/实证注记回填；文档回填 B19（§1 五迭代结论、§2.4 smooth 下沉、§3.1 smooth 契约五铁律 + pass-rate 耦合旋钮、§5 消费方表、§6 教训 10「凡微秒节奏一律走 smooth」/11「make 不因 CFLAGS 重编译」、§7 索引）、B90（`hal_wallclock_smooth_ms` 行 + reveal/anim/audio 三处 0.2.134 注解）、FAQ §7.4（delay/选项拉长已接受语义）；版本 0.2.133→0.2.134（animatest+demo-a2 同步 bump）+ build/make demo-a2 重注入。

<a id="c2"></a>
### 0.2.133 — 打字机逐字节拍去抖落地（devdoc 106 方案 A+）

用户实测长句逐字输出"卡一下再继续"，按 devdoc 106 先探针后实施方案。**Step 0 探针根因（推翻 0.2.131 沿用前提）**：NP2kai 上 `INT 21h AH=2Ch` 百分秒字段 `dl` 恒为 0（6/6 采样）、BIOS tick `0x40:0x6C` 在 DOS/4GW 下恒读 0，唯一可用读数只剩**整秒且成块交付**——时钟冻结 3-6 真实秒后一次跳 +1000..+6000ms（now 序列 `0→1000→2000→3000→7000→10000→11000→15000→19000`；原始 delta 直方图 `{1000×172, 0×18, 16×4}`）。四路时钟源全不可用：DOS 2Ch（整秒量子+成块冻结）、BIOS tick（DOS/4GW 恒 0）、PIT（0.2.129 永久否决）、vblank（pass 率 20.5Hz 慢 3 倍）——平滑节拍只有主循环 pass 节奏。**方案 A+（绝对期望位置 + 虚拟时钟钳制）**：`nb_dialog_reveal_tick` 改绝对目标 `target = speed×(vnow−page_ms)/1000`（每 pass 直接用虚拟时钟算目标，`target` 只进不退）；新增 `REVEAL_PASS_MIN_MS 40UL / REVEAL_PASS_MAX_MS 100UL` 钳制喂给目标的每 pass 增量——`delta_raw==0`（时钟洞内整秒边界）地板 40ms 保持按 pass 节奏逐字、`delta_raw>100ms`（时钟补齐猛跳）天花板 100ms 丢弃追赶盈余，单 pass 至多追 3-4 字；删 `reveal_ms_frac` 累加器与 `while(>=1000)` 循环；翻页用 `reveal_page_ms = now − reveal_char_count*1000/speed` 重锚、回绕分支重锚虚拟时钟；真实硬件（DL≈55ms）两界不触发。**验证**——make 0 err/0 warn（engine.exe+engine_a.exe）；pytest 432 passed（test_reveal_final_page.py 增 4 例改 1 例全绿）；`./start.sh fullaudit` 7/7 全绿；AUTOEXIT 无头回归 HDI 直启串口至 `End`；**NP2kai 实机复测（A+ 版长句页 52 探针样本）：页内逐字宿主间隔 N=51、min=2ms p50=114ms p90=179ms max=202ms avg=97ms → max/avg=2.09 ≤2.5 门限**（修复前同场景 max/avg ≥19）；`de` 直方图 `{40×35, 100×17}` 证钳制生效、`target` 单调无回绕；探针用毕移除（`grep -rn '\[RV\]' core/` 为空）。附注：~3-4s 长间隔均出现在**翻页处**（点按→下一页揭开延迟）非页内打字机节拍，不在本次范围；探针环境 NAIZ_DEBUG=ON 串口刷屏占用 guest 时间致绝对速率 ~10 字/s（名义 32 字/s 在关调试/真机成立），不影响节拍平滑性结论。devdoc 106 状态置「已落地」+ 证据回填；版本 0.2.132→0.2.133（bump_version 统一）。

<a id="c3"></a>
### 0.2.132 — 串口工具链三项修复：残留清理 + 强制 --start + slave_fd 全开 + SERTEST.COM 端口直写

用户反馈"串口通讯尝试多次才连上"。调研发现系统里残留 3 个 `wxnp21kai` 实例各持已删除 PTY、且工具链有两处可复现的串口静默根因与一处错误归因在案——①**残留实例无清理**：`env_test.py`/`np2kai_serial.py` 启动前均不 `pkill`，旧实例退出回写 config 覆盖工具刚写入的 `com1_m_o/com1_m_i`（指向死 PTY）→ 下次启动读到失效串口（0.2.130 已知 `pkill -f` 自匹配杀 shell 的教训当时只加了口头规避）；②**PTY slave 提前关闭**：`env_test.py` 在 `Popen` 前 `os.close(slave_fd)`，而 NP2kai 在 fork 后按路径打开 slave 端点——端点已关则打不开 → 串口静默 0 字节（对照实验：close 后 0 字节 vs 保持开 5.4KB 引擎串口）；③**`--porttest` 的 SERTEST.COM 用 INT 14h 输出**——PC-9821 BIOS **不含 INT 14h 处理函数**（FAQ §9.3 早已记载，引擎因此用直接 uPD8251 端口 I/O `0x30/0x32`），故 `sertest.com` 自诞生从未通、0.2.129 误归因"会话环境问题"。**修复**：①`tools/naiz_lib/np2kai_capture.py` 新增 `kill_stale_emulators()`（`pgrep`+`pkill -9 -x` 精确匹配进程名，返回清理数）；②`np2kai_serial.py`/`env_test.py` 串口启动前调用清理 + 启动命令无条件追加 `--start`（避免停在配置界面等手动点击）；③`env_test.py` 移除 Popen 前 `os.close(slave_fd)`，改为捕获全程保持、结束后关闭；④`gen_com.make_serialwrite()` 重写为直接端口 I/O（对齐 `serial.c` 复位序列：0x40 复位→0x4E 9600 8N1→0x27 使能），逐字节轮询 TXRDY（状态位 bit0）后再发并带 0xFFFF 超时守卫，输出 `Hello from DOS!\r\n` 全 17 字节到位（经验证 `loop`/`jnz` 跳转位移 objdump 反汇编正确）。验证——`makegame.sh test demo-a2 --porttest` RESULT: `Hello from DOS!` boot chain OK（此前 0 字节）；`test-hdi --serial` 引擎串口 44KB/27KB 两次单次连通（boot 链 `Naiz engine`→`Pal chk OK`→`Img OK` 完整）；残留实例自动归零；pytest 429 passed 无回归。版本 0.2.131→0.2.132（animatest+demo-a2 同步 bump）。B90 三处工具索引同步（np2kai_serial/np2kai_capture/gen_com/env_test 均标注新行为）；FAQ §9.1 补"残留实例/slave 提前关闭/缺 --start"三个排查方向、新增 §9.1b SERTEST.COM 根因条目；B19 §4.2 补"串口链前置三条件"、§6 补教训 8（串口静默先查三元组而非环境）。

<a id="c4"></a>
### 0.2.130 — 打字机墙钟兹帧节拍化

0.2.129 端口修正后用户要求先出验证构建确认 NP2kai 的 PIT 语义再定墙钟源。串口链路在 0.2.129 期间意外 100% 静默（`makegame.sh test --serial` 两次 0 字节；`sertest.com` 同样 0 字节）——当时归因**会话环境问题**并沿用此结论（`pkill -f wxnp21kai` 匹配到含同名字样的调用命令行把 shell 进程自身杀掉导致命令超时；后改 `pkill -x` 精确匹配 + 用 PTY 独立脚本 `write_emulator_toml` + `wxnp21kai --start` 直启，引擎串口即通）。**注**：`sertest.com` 的 0 字节在 0.2.132 重查实为另一根因——它用 INT 14h（PC-9821 BIOS 无此处理函数）输出，与引擎串口链路无关；两链共用同一"残留实例/slave_fd/--start"前置。用 PTY 捕获到全量串口：引擎主循环鼠标 8255 轮询洪水刷屏之外，**`[PITVERIFY]` 探针数据如下**——`samples F12B 92F0 AF8E C31C 60BB F548`（vblank 60 帧×3、忙循环 4M×2 交替采样）、`dVB(60x2+60) = 24123 25185`、`dLOOP(4M) = 4294959970 4294929267`。**判定（关键）**：①60 次 vblank 等待计数变化 2.4 万/2.5 万、4M 忙循环计数反而**反向跳动**−7326/−38029——即使端口已正确（PC-98 系统定时器 8253 在 **0x71/0x77**，0x40/0x43 是打印/键盘区，见 refdocs B02），NP2kai IA32 核心的 PIT 计数 = `nevent_getremain(NEVENT_ITIMER)/pccore.multiple`，由**模拟 CPU 时钟**驱动（`clk_mult=20` 倍频缩放），与真实墙钟无稳定比例，读数非单调——**任何端口下 PIT 都不是模拟器里的真墙钟**。修复（方案 A，用户选中）：`hal_wallclock_ms()` 改为**帧节拍**——`hal_vblank_wait()` 递增 `wallclock_frames`（60Hz 垂直回扫），墙钟 = `delta_frames×1000/60` 毫秒（32-bit 帧计数回绕 ~27 个月，调用方按现有回绕语义重校准）；帧节拍在模拟器与真机一致、不随 CPU 倍频漂移。`nb_dialog_reveal_tick`/`anim_tick` 的 `now==0` 兜底注释由"PIT unavailable"改为"clock not yet ticking"（逻辑不变）。回归：`test_reveal_final_page.py` 重写 `test_wallclock_reads_pc98_system_timer`（0x40/0x43+298295 断言）为 `test_wallclock_paced_by_vblank_frames`（断言 `wallclock_frames`/`1000UL/60UL`/`hal_vblank_wait` 递增、PIT 宏不得残留）→ 仍 7 例。B90 reveal 注解与 hal 函数说明同步帧节拍表述。验证——make 0 err/0 warn、pytest 429 passed、fullaudit 7/7 全绿、nb_validator 双项目通过、test_version_sync 9 例通过；版本 0.2.129→0.2.130。实测 @64/s 真 64 字/秒留人工目检；0.2.129 植入磁盘的 PIT 端墙钟构建由本次 build+make 重注入替换。

<a id="c5"></a>
### 0.2.131 — 打字机墙钟改 DOS 系统时钟

0.2.130 帧节拍墙钟交付后用户实测 **@32/s 仍达不到每秒 32 字**——串口复验定位根因：`hal_vblank_wait()` 每主循环 pass 只 `wallclock_frames++` 一次，而 devdoc 82 §5.2 早有实测 **NP2kai pass 率仅 ~20.5Hz**（每 pass ~49ms = 等 VSYNC + 引擎工作 + NP2kai 解释核渲染/解释开销）——两次 `vblank_wait()` 之间实际跨越近 3 个 VSYNC 周期，中间翻转在 busy-wait 轮询下**全部漏计**，`wallclock_frames` 每真实秒只增 ~20.5 → `hal_wallclock_ms()` 每秒只推进 `20.5×16.7ms ≈ 342ms` → reveal_tick 的 `delta_ms` 每秒只累 342ms → @32/s 实为 ~11 字/秒（慢 3 倍）。帧节拍对"pass 率=60Hz"隐含假设，在 NP2kai 下等同 0.2.127 的"60 pass/s"错误同源换皮。**修复（用户选中方案）**：`hal_wallclock_ms()` 改 **DOS 系统时钟**——`int386(0x21, AH=2Ch)`（DPMI-reflected DOS 中断，与 video.c 已用的 INT 18h 同通道）：读 CH=时 CL=分 DH=秒 DL=百分秒，**折叠为当日毫秒**（`(h×3600+m×60+s)×1000 + dl×10`）后按差值单调累加（跨午夜 `now<prev` 重校准、`now==0`/未初始化首 pass 记基线）；10ms 粒度对 32 字/s=31.25ms/字足够。devdoc 82 §5.3 早已实测此法在 DOS/4GW DPMI 下 guest 时钟精确 5000ms 整。`hal_vblank_wait()` 恢复纯 VSYNC 等待（移除帧计数职责），`wallclock_frames` 相关换算全删。**串口量化复验（关键，非目测）**：临时 `[CLK]` 探针（settings 菜单等待循环 + 主循环每 1000 墙钟 ms 打点）× PTY 宿主秒（`time.monotonic`）对拍 58s——53 个样本逐秒 `guest +1000ms ↔ host ~0.99s`，**比率 ≈1000ms-per-host-s（±2.5% 抖动）**，较帧节拍的 ~342ms 提升 ~3 倍、达真实秒速；探针用毕移除（C 文件零残留）。回归：`test_reveal_final_page.py` 重写 `test_wallclock_paced_by_vblank_frames` 为 `test_wallclock_backed_by_dos_system_time`（断言 `int386`+`0x2C`、`wallclock_frames` 静态声明不得复现、PIT 宏不得残留）→ 仍 7 例。B90 reveal 注解与 hal 函数说明同步 DOS 时钟表述（含时钟源三段历史）。验证——make 0 err/0 warn、pytest 429 passed、fullaudit 7/7 全绿、nb_validator 双项目通过；版本 0.2.130→0.2.131，build+make demo-a2 重注入。实测 @32/s 真 32 字/秒留人工目检。

<a id="c6"></a>
### 0.2.129 — 打字机墙钟端口根修

0.2.128 墙钟计速上线后用户实测 **@32/s 仍仅 1-2 字/秒**——上一轮修对了 reveal 的调用层，却没核 `hal_wallclock_ms()` 这个共享时间源本身（从诞生起就在 PC-98 上读错端口）。根因（G04_98_tewaza.md §2 本地证据）：PC-98 系统定时器 8253 沿用 IBM 布局 **0x40(数据)/0x43(模式控制)**，而 hal 把 latch 命令写到 **0x44**（打印机区）→ 计数器从未被 latch → 读到正在跳动的值 → `now < reveal_last_ms` 回绕分支几乎每 pass 丢弃时间 → 墙钟爬行、reveal 按乱数只推 1-2 字/秒；二级错误：换算除数用 **IBM 1.193182MHz**，而 PC-98 系统定时器输入时钟 = 1.193182MHz/4 ≈ **298,295Hz**（reload 5965→50Hz 自洽）。修复（`core/plat/hal_pc98.c`）：`PIT_CMD_PORT 0x44→0x43`、`PIT_FREQ 1193182UL→298295UL`，补端口/时钟注释引用 G04；latch→读低→读高结构、0 兜底与回绕守卫原样保留。附带疗效：`anim_tick`（动画时长）与 MIDI 计速同步转真（此前一直静默走 PIT==0 兜底）。部署：`makegame.sh build+make demo-a2` 重注入磁盘（上一轮植入磁盘的恰是坏端口的 0.2.128）。回归：`test_reveal_final_page.py` 增 1 例断言 `hal_pc98.c` 含 `PIT_CMD_PORT 0x43` 与 `298295`（防回退 0x44/1.19MHz）→ 共 7 例。B90 reveal 注解补正 0.2.128 语句（明确墙钟端口）。验证——make 0 err/0 warn（engine.exe+engine_a.exe 双变体）、pytest 429 passed（428+1）、fullaudit 7/7 全绿、nb_validator 双项目通过、磁盘注入 27 新/3 更新；版本 0.2.128→0.2.129。实测 @32/s ≈ 真 32 字/秒（~31ms/字）留人工目检。

<a id="c7"></a>
### 0.2.128 — 打字机墙钟计速根修

用户反馈 64 档仍太慢——定位**计速前提错误**：devdoc 105 reveal 用"每 tick +speed、满 60 推 1 字"的分数累加器，分母 60 隐含 60 pass/s；而 devdoc 82 早有实测 **NP2kai 真机 pass 率仅 ~20.5Hz**（动画 `anim_tick` 当时即为此改造为墙钟步进，`nb_anim.c:541` 注释为证），故真机 16/32/64 档实际仅 ~5.5/11/21 字/秒——慢 3 倍即根因。修复：`nb_dialog_reveal_tick()` 计速改用 **PIT 墙钟 `hal_wallclock_ms()`**（仿 `anim_tick` 模式）：每个 pass 读墙钟算 `delta_ms`，按 `reveal_ms_frac += speed × delta_ms`、满 1000 推 1 字定点累积 → 档位 N 在任何循环节奏下都是真 N 字/秒；首 pass 校准基线（`reveal_armed`，防 `==0` 歧义，动画同款）、跨 midnight 回绕重校准、PIT 不可用（`hal_wallclock_ms()==0`）回退 16.7ms/帧防冻结；`dialog_show` 翻页改 `reveal_armed=0` 重校准（原 `reveal_frac=0`），`reset` 同步清 `reveal_last_ms/reveal_ms_frac`。0.2.127 的页界守卫/finish 门三处根因守卫原样保留。回归：`test_reveal_final_page.py` 重写为 6 例——新增"tick 必须调用 `hal_wallclock_ms`、不得复现旧 `reveal_frac` 60Hz 累加器"，其余 5 例（tick/finish 不依赖 `text` 指针、页界守卫、无每帧 floor、翻页重校准）形态同步新实现。B90 reveal 接口注解补墙钟计速。验证——make 0 err/0 warn（engine.exe+engine_a.exe 双变体）、pytest 428 passed（427+1）、fullaudit 7/7 全绿、nb_validator 双项目通过；版本 0.2.127→0.2.128。实测手感（64 档应从 ~21 字/秒升至真 64 字/秒）与是否需要追加 128 档留人工/后续决定。

<a id="c8"></a>
### 0.2.127 — 打字机末页对白不显示根修

实机/逻辑推演定位 devdoc 105 打字机 reveal 的**末页正文永不显示**根因——`dialog_show()` 在末页（含单页对白）渲染返回 `next<0` 后按设计置 `dialog_state.text=NULL`（正文已整体进 `dialog_text_buf`），而 `nb_dialog_reveal_tick()` 首帧即 `if (!dialog_state.text) { reveal_active=0; return; }` 提前停工 → 末页/单行台词正文永远空白（只剩框+角色名），`finish` 的同款 `text` 守卫亦让点击"跳满"在末页失效。修复：①tick 守卫删 `text==NULL` 早退，改按页字节界 `page_end<=page_start` 判断"无正文"——揭示只依赖 `dialog_text_buf` 的 `page_start/page_end`，与 `text` 指针是否空无关，末页照常逐字揭示；②finish 守卫改 `reveal_end != page_end`（推进量门，非 `text` 门）——末页点击跳满也能整页补画，Ren'Py 语义恢复；③删上一轮置于早退之后的"每帧保底 +1 字" floor 块（其"vsync 永不累积满 60 tick"前提不成立——`reveal_frac` 按调用次数累加必达 60；且每帧强制 +1 字使 16/32 档在真机 60Hz 下全变 60 字/秒、架空速度档）及 tick 末尾不可达死代码；④`dialog_show` 置 `reveal_active=1` 时 `reveal_frac=0`（翻页余数归零，杜绝下页首字突进）；⑤新增 `tools/tests/test_reveal_final_page.py`（5 例——tick/finish 均不得依赖 `text` 指针、页边界守卫存在、无每帧 floor、翻页余数归零，旧形态即红）。验证——make 0 err/0 warn（engine.exe+engine_a.exe 双变体）、pytest 427 passed（422+5）、fullaudit 7/7 全绿、nb_validator 双项目通过；版本 0.2.126→0.2.127。实机 NP2kai 单行 @32/s 逐字揭示留人工目检。

<a id="c9"></a>
### 0.2.126 — 移除 demo-a2 CG 演示引用 + 引擎 CG_COUNT=0 编译防御

`makegame.sh build demo-a2` 在 `pack_images` 硬失败定位——`ASSETS.DB` 登记 id 19/20（`images/cg01.MAG`/`images/cg02.MAG`, type='CG'）但源图全仓库不存在（`*.MAG` 被 .gitignore 忽略、images.map 无记录、Git 历史无源 PNG，CG 特性 d9d3a3d 接入时遗留的素材缺失）。按用户裁定**移除 CG 演示引用**：①数据——`demo-a2 ASSETS.DB` 删 2 条 CG 行、`nbook001.nb` 删 `cg(){cg01}`、重导出 `nb_asset_table.h`（`cg_map[]`→`__dummy__` 哨兵 + `CG_COUNT 2→0`）；i18n 模板重生成将 `cg01=` 自动标 `# ORPHANED`（源串已消失的标准行为）；②引擎编译防御——`nb_cggallery.c:62` `gal_unlock_cache[CG_COUNT]` 在零 CG 项目下数组零维触发 Watcom E1020，改 `[CG_COUNT > 0 ? CG_COUNT : 1]`（全部下标已有 `i < CG_COUNT` 运行时守卫、`cmd_cgvmenu` 亦有 CG_COUNT==0 早退，唯尺寸表达式需保护常量折叠）；③验证——make 0 err/0 warn（engine.exe+engine_a.exe 双变体）、pytest 422 passed、demo-a2 全量 build 通过（IMAGE.DAT 21→19 条目、无 ERROR）；版本 0.2.125→0.2.126。声明：本修改仅移除 demo-a2 的 CG 素材登记与脚本引用，CG 引擎特性（cg 命令/画廊/解锁）整体保留，未来补素材只需 images.map+PNG+ASSETS.DB 登记（devdoc 88 §素材登记）。

<a id="c10"></a>
### 0.2.125 — 打字机文字落地（devdoc 105）

按 devdocs/105-打字机文字方案.md 完成逐字揭示——**①`DialogState` 扩展**：nb_dialog.c 增 `page_start/page_end/reveal_end/reveal_active`（`page_start`＝本页起点、`page_end`＝本页尾独占、`reveal_end`＝已揭示字节、`reveal_active`＝揭示进行中；渲染前后 `text_offset` 双语义不动，页起点单独留存）；`dialog_show` 末页/翻页分支按 `next` 定 `page_end` 后在非 AUTOEXIT 下置 `reveal_end=page_start + reveal_active=(text_speed!=0)`，揭示激活时用截断串**覆画**合成缓冲（整帧 1 次 blit）。**②揭示推进**：新 `nb_dialog_reveal_tick/active/finish`——60Hz 分数累加器（每 tick +speed，满 60 推进 1 字）按 **UTF-8 步进**（lead byte 定 1..3 字节，越界夹逼 `page_end`，剥续字节后置尾早已安全）推进，每次实进 `dialog_render_reveal()`（取 `[page_start,reveal_end)` 子串 ≤1KB 栈缓冲、`layer_dialog_render_page(name,截串,0)` + `dialog_layer_store_render` 同步揭示态投影 + `dialog_layer_blit()`）——**方案 A 调用侧截断，`draw_text` 核心零改动**；`finish` 整页跳满（`reveal_end=page_end` + 重画 + blit）。**③输入接缝**：main.c wait loop 鼠标/SPACE/ENTER/XFER 分支在 `vm_request_process()` 前插 `nb_dialog_reveal_active()`→是则 `finish`（跳满不翻页）否则放行——揭示中点击仅跳满、整页后再点翻页/收尾（Ren'Py 语义）；wait loop 与外层双循环各挂 `nb_dialog_reveal_tick()`（仿 `anim_tick`）；AUTOEXIT 构建 `#else` 分支不编译、`reveal_active` 恒 0 → **直通语义零变化**。**④速度设置**：`GameSettings.text_speed`（0/16/32/64，默认 32）+ settings.txt `text_speed=` 读写校验（未知值回退默认）+ `settings_get/set_text_speed()`；设置菜单 settings_menu.c 加 **Text Speed 第三行**（y=SEL_Y+30，focus 状态机 LANG→SPEED→START 三态、`FOCUS_SPEED`、hittest 增 3/4 速度行箭头、full=3 动态擦区+`SPD_*`/`IND_CLEAR_Y_SPD` 宏、档位显示 `Instant`(i18n)/`16/s`/`32/s`/`64/s` 居中、上下移聚焦左右调档、退出写回）。**⑤i18n**：`SYSTEM_UI_KEYS` 增 "Text Speed"/"Instant"，9 语言 `sys_<lang>.txt` 补译文，i18n_gen 重生成零 ORPHANED（sys=29 无漂移）。**⑥测试**：新 `tools/tests/test_text_speed_settings.py`（7 例——合法档位全集/非法回退默认/保存读取回环/永不写非法值/i18n 键登记/9 语言译文非空）；版本 0.2.124→0.2.125，pytest 422 passed（415+7）、fullaudit 7/7 全绿、make 0 err/0 warn（engine.exe+engine_a.exe 双变体）、B90 登记 reveal 三接口/速度访问器；AUTOEXIT 直通与 §3.7 行为矩阵实机 NP2kai 目检留人工。

<a id="c11"></a>
### 0.2.124 — nb_validator V1–V4 落地（devdoc 104）

按 devdocs/104 完成纯逻辑剧本 Lint 四项能力——**V1 变量值域**：`load_reference` 增读 `variables.json`（`var_tbl`，每变量 initial/min/max 注册）返回 7 元组；`validate_scene` 增 `check_var_segment`——`cmd_var` 手写改走 SIGNATURES 表内 var 分支，`set` 值与 `+/-` 增量式初值+delta 两端夹逼，越界/未知 id/非法 op/非数值增量逐项报错（demo-a2 三个 bond_* 0..100/initial 0 全绿）；**V2 question 深查**：改走引擎 `nb_parse_line_semi` 同源 `split_semi`（nb_line.py 新 helper，对齐 nb_parser.c:130-156 顶级 `;` 分段语义），`question` 深查提示词非空 + 选项 1..10（对齐 nb_question.c:38-89 段上限 10/静默丢段）+ 每选项 `label,var,op,delta` 四段逐一过 `check_var_segment`（op∈{=,+,-} 对齐 nb_commands.c:305-338）；**V3 delay 正数**：`delay` 负/0/非数值报"must be a positive number"（对齐 nb_commands.c:340-361 负/0→1 帧）；**V4 白名单**：`load_accepted`/`filter_accepted`——`nb_lint_accepted.txt` 行格式 `file:lineno|pattern`（pattern 可空即整行使豁免），命中仅打印 `(accepted:)` 不计分；**接入 start.sh**：fullaudit 6 步→**7 步**，validator 置 [3/7]（pytest 后）`for d in projects/*/`（ASSETS.DB 存在才跑）校验各项目 scene 静态零误报、returncode≠0 即整体硬失败，--no-make 分支同步编号；新 `tools/tests/test_nb_lint.py`（20 例：V1 越界/未知 id/非法 op/非数值/无表跳过、V2 缺 delta/错 op/未知 var/超 10 段/空提示、V3 三否定、V4 豁免/不匹配/集成计数）；版本 0.2.123→0.2.124，pytest 415 passed（395+20）、fullaudit 7/7 全绿（animatest/demo-a2 双项目校验通过、animatest 无 variables.json→var 校验跳过）、make 0 err/0 warn、B90（split_semi/load_accepted/filter_accepted 登记）/B91（§2 fullaudit 补 nb_validator 步）同步。

<a id="c12"></a>
### 0.2.123 — devdoc 103 独立小项落地

完成 devdocs/103 §7 落地清单剩余三项——**B 未知命令常开 WARN**：`nb_commands_dispatch`（nb_commands.c）未知命令由 `NB_DEBUG`（仅 NAIZ_DEBUG 可见）改为无条件 `hal_logf("WARN: unknown command ...")`，对齐 `var` handler 既有先例，落实「消灭静默失败」；**F 命令表↔文档防漂移测试**：新 `tools/tests/test_cmd_doc_sync.py`——解析 `cmd_table` 命令名集合（nb_commands.c）与 docs/B92 §1 命令对照表（`fei/ira/neon` 同格合并）双向断言一致，漂移即红，对标 `test_langdefs_sync`，首跑即绿（无既有漂移）；**K 存档 slot 元数据侧车**：裁定 `slot_info()`（save.c，纯 `save_read_header` + 零全局状态 + 不触发重跑，配合 R22 页级槽位缓存）已满足「读档列表页走纯数据接口」目标，无需新 API——结论经文档记录而非新增代码（B90 slot_info 行加注）；版本 0.2.122→0.2.123，make 0 err/0 warn、pytest 395 passed（393+2）、fullaudit 6/6 全绿、B90/B92 同步；实机 NP2kai 回归仍留人工。

<a id="c13"></a>
### 0.2.122 — 显示 op 化改造（devdoc 103 阶段 2）

按 devdocs/103 完成阶段 2 五项落地——①**G `scene_switch` 场景切换单入口**：nb.h 新增 `SceneSwitchReason{}`（INIT/SCRIPT/HOTKEY/APPLY/MENU）+ `scene_switch(name,reason)`（nb.c：日志 reason + `audio_stop_all()` + `nb_load()`）；启动 `nb_init`、脚本 scene×3、读档 apply、存档菜单/热键 F5-F6-ESC、主菜单×3、画廊×2 全部调用点收敛，**E 音频归属**随之上移：`audio_stop_all()` 仅存于 scene_switch，`layer.c scene_end` 删除音频清理；`nb_load` 因无外部调用者改 static（dead-export gate）。②**B 删逐帧重绘 + 对话框 pending 让位**：`dialog_show` 不再内部 `vm_pause_process()`（AUTOEXIT 与普通分支皆移除），改置 `DialogState.pending`；新增 `nb_dialog_pending()/nb_dialog_dismiss()`（reset 一并清 pending）；nb.c `nb_process` 删逐帧重绘块改 pending 块（续页→dialog_show+pause+break；末页→dismiss+continue），dispatch 后补 pending 让位检查——行为等价推演：单页 1 次点击、多页 n 次、AUTOEXIT 整页直显逐帧推进均同旧。③**A 显示 op 窄接口**：新 `scene_display.h/.c` `display_apply_bg/cg/sprite/dialog`——命令侧只做格式串整段执行+尾参解析，facade 吸收 anim_stop/hal_mouse_invalidate_cursor/palette_reset_reserved/layer_bg_change/layer_dialog_hide/nb_dialog_reset/scene_dialog_restore 处置；cmd_bg/host/dialogue/char/cg 改经 display_apply_*（cg 的 `sys_save_unlock_cg` 留命令侧、先于显示）；决策：facade 非双账本，layer_* 仍唯一事实源。④**C 命令元数据声明位**：`CmdEntry` 增 `unsigned char flags`，cmd_table 全行补齐 `CMD_BLOCKING/CMD_NEEDS_INPUT/CMD_TOUCHES_DISPLAY/CMD_TOUCHES_AUDIO/CMD_TERMINATES_SCENE`；新 `tools/tests/test_cmd_meta.py`（解析 cmd_table 断言显式 flags、flag 字面量合法、非 TOUCHES_DISPLAY 命令 handler 函数体无渲染接口调用）。版本 0.2.121→0.2.122，make 0 err/0 warn（engine.exe+engine_a.exe 双变体，修 scene_display W138）、pytest 393 passed（390+3）、fullaudit 6/6 全绿、B90/B92 同步（scene_switch/display_apply_*/nb_dialog_pending/CmdEntry 声明位）；实机 NP2kai 串口/截屏比对留人工回归。

<a id="c14"></a>
### 0.2.121 — 交互收口与存档请求收敛（devdoc 103 阶段 1）

按 devdocs/103 完成阶段 1 三项落地——①**`ui_interact()` 交互收口**：新 `core/engine/nb_interact.c`，`UiRequest`+`int ui_interact(const UiRequest*)`（声明进 nb_internal.h，对齐 devdoc §4 结构：labels 已 tr()、n=0 纯确认框预留给后续）——收起 `cmd_question` 的选项渲染（emboss 描边+draw_text）、命中测试（base_x+448 溢出无、几何原样）、600 帧超时、鼠标/键盘/翻页三输入单点分发；`interact_draw_opt`/`interact_hittest` 为原 `question_draw_opt`/`question_hittest` 同语义 static 本地化；②**cmd_question 阻塞循环收敛**：nb_question.c 仅保留段解析、>4 截断、提示词直绘、`menu_save_item_palette`/`menu_restore_item_palette` 包围、`nb_set_last_choice`、`apply_option`（R8/C22 INT_MIN clamp 原样）——原地阻塞循环删除，行为等价（含 timeout→-1→last_choice(-1)）；存档确认框维持 P3 `menu_confirm_input` 基础（devdoc §5 既定继承，不改）③**A 存档请求收口**：nb_saveload.h 新增 `SlotOp` 枚举 + `int save_request(SlotOp,int)`（实现于 nb_saveload.c，补 `#include "nb_saveload.h"` 自包含）——F5/F6/ESC（`CAPTURE_TEMP→OPEN_SAVE/OPEN_LOAD/OPEN_MAINMENU`）、载入确认框（`SLOT_LOAD/SLOT_SAVE`）、Back/ESC/鼠标退回（`RESTORE_TEMP`）、保存对话框确认（`SLOT_SAVE`）、主菜单 continue（`SLOT_LOAD`）/load（`CAPTURE_TEMP→OPEN_LOAD`）全部改走入口；保留直调 `nb_load`：`from_mainmenu=1` 场景返回分支（当前调用方均传 0 不可达，属阶段 2 G scene_switch 收口）与 cgview/mainmenu 场景跳转（同 G 范畴）；§十七逐一复查（C13 新 static 均已用、C35 nb_question 冗余几何已随 ui_interact 收敛、C17 cursor 惯例不变）；make 0 err/0 warn（修新文件缺末尾换行 W138）、pytest 390 passed、fullaudit 6/6 全绿、docs/B90 增 `ui_interact`/`save_request`、bump 0.2.121

<a id="c15"></a>
### 0.2.120 — 菜单 UI 整合落地（devdoc 102）

按 devdocs/102-菜单UI整合机会审计与封装方案.md 完成八项整合（P1–P8）：**P1** `menu_finish()`（menu_layer_close(1)+hal_mouse_flush+menu_restore_item_palette 收口为共享退出契约）注入载入/画廊/主菜单；**P2** 共享分页条+Back widget——`menu_pagenav_draw/menu_page_hit`（箭头+页码，计数器 x 归一 310）+`menu_back_draw/menu_back_hit`（emboss 全量/文本增量两态）；**P3** 共享确认状态机 `menu_confirm_input()` + `MenuConfirmCfg`（action(slot) 返 1=退出/0=留下刷新/-1=失败），载入菜单错误框位置归一 (260,346)，save_load 的 `save_load_confirm_action/g_sl_confirm_cfg` 与保存对话框的 `save_dlg_confirm_action/g_dlg_confirm_cfg`（mouse_yes_always）接入；**P4** `text_title_width()`（原 gallery_title_width 迁 render_text.c/render.h 共享，LOAD/SAVE/CG GALLERY 标题居中公式化）；**P5** `tools/naiz_lib/langdefs.py` 语言表单一事实源（i18n_gen VALID_LANGS / gen_cjk_font RUNTIME_LANGS+CJK/LATIN_FAMILY 改 import）+ `tools/tests/test_langdefs_sync.py` 防漂移（正则解析 settings_menu.c C 表比对）；**P6** `save_load_slots_on_page()`/`menu_pagecount()` 替换全部分页夹逼与总页数计算；**P7** `slot_chapter_label()` 共享替换两处 chapter_title/filename 三元（删 nb_saveload.h 重复声明源，SlotInfo 属 save.h）；**P8** nb_save_dialog.c 网格导航去重——`save_dlg_row_hop/save_dlg_col_wrap/save_dlg_slot_hit/save_dlg_draw_header`；exit_on_yes 死字段移除（退出语义由 action 返回码承载）；nb_internal.h 增 `#include <stdint.h>`（uint8_t 参数类型修正）；C22 修复（80L-tw 长整型）+C35 消除（GAL_LAST_CELL_IDX、save_dlg_draw_header）；make 0 err/0 warn、pytest 390 passed、fullaudit 6/6 全绿、docs/B90 函数索引同步、bump 0.2.120

<a id="c16"></a>
### 0.2.119 — powered 资产归位 `common/logo/` + 资产键统一

`assets/demo-a2/png/bg/powed.png` 移至 `assets/common/logo/powed.png`（新增 `logo/` 目录，common 共享：demo-a2 / animatest 均注入）；`ASSETS.DB` `img_map.id=6` 登记名 `powed`→`powered`（与 `logo.nb:{powered}` / `op.nb:{powered}` 脚本键对齐），重导出 `nb_asset_table.h`（`{"powered",6}`）；`IMAGE.DAT` 重注入 `POWED.MAG`；make 0err/0warn、demo-a2 build 通过、bump 0.2.119

<a id="c17"></a>
### Bug 修复状态（R1–R30 综合摘要与历史子条目）

已完成 7 轮穷举静态分析 + 针对性修复（R1–R7），另完成整合修复（Bug-1/Bug-2/i18n 管线/工具链去重）与**查 bug 系统升级**（Tier1 + Tier2，R8）与**拆分整合重构**（R9）与**日志/审计范围增强**（R10）与**cg 双形态语法**（R11）与**对象/参数括号规范化**（R12）与**全项目查 bug（R13）**与**再次全项目查 bug（R14）**与**针对漏网 bug 的 Tier3 规则扩充（R15）**与**拆分/封装机会落库（R16）**与**背景CG换图自动复位对话框（R17）**与**运行目检修复：伪透明恢复+cg 换图自动关框（R20）**与**layer_sprite 小封装（R21）**与**菜单 P0 改进（R22）**与**菜单 UI 图层化 menu_layer（R23）**与**语言全路径收口 nb_set_lang（R24）**与**i18n 8.3 短名化（R25）**与**存档/读档错误提示 i18n+可读性（R26）**与**菜单标题字模 RAM 目标修正（R27）**与**对话框内保存菜单剧情字残留（R28）**与**全项目整合机会审计与落地（R29）**与**整合机会规则落地（R30）**与**CG 画廊四项显示修复（0.2.109）**与**画廊背景 cover 占满屏幕（0.2.110）**与**记忆体/剧本 TOC 化调研与设计（devdoc 100）**与**归档打包侧 TOC 化落地（P4，0.2.111–0.2.112）**与**归档读取侧 TOC 化 P1+P2（farchive + image.c 按需读，0.2.113）**与**P1+P2→P5 音频后端（devdoc 101，0.2.115）**与**bg_load 读档界面背景 + 全屏保存菜单核实（0.2.116）**与**load 菜单翻页/confirm 残影修复（0.2.117）**与**菜单 UI 整合落地（0.2.120）**与**交互收口与存档请求收敛（devdoc 103 阶段 1，0.2.121）**与**显示 op 化改造（devdoc 103 阶段 2，0.2.122）**与**devdoc 103 独立小项落地（0.2.123）**。
- 归档读取侧 TOC 化 P1+P2（devdoc 100，0.2.113）: **共享读取库 `core/lib/farchive.{c,h}`**——纯 lib 零平台依赖零日志（沿用 naiz_file/tr/font 静默先例，失败以返回码上抛、引擎调用方 hal_log），`farchive_open`(TOC 常驻≤8192、truncated 标志)/`close`/`lookup_id`/`read_alloc`(绝对偏移+file_size 双夹逼、size=0 空洞返 NULL、malloc 失败/seek/fread 错误均返 NULL)；**image.c 整档→按需**——删 `file_read_all` 整档常驻 + `g_image_data/size/count/toc_off`/`image_get_entry`/`TOC_ENTRY_SIZE`，改 `g_image_arc`(FArchive) + 单槽 `g_blob`（`g_blob_id` 判重缓存）；`image_load` miss 路径改 `farchive_read_alloc` 瞬时读（decode 后 free，mag_decode 失败也 free 防泄漏），`image_init` 调色板一致性校验逐项瞬时读（原 `g_image_data+offset` 直读），`image_raw_blob` 借用期由「至下次 init/close」收缩为「至下次 raw_blob/init/close」——核对唯一借用方 nb_anim.c:319 先 `anim_stop_internal()`(置 `a->blob=NULL`) 再取新 blob，播放期无竞争者，单槽安全；B90 图片管理节/B92 playanima 容器直读行同步；pytest 374 passed、make 0 err/0 warn、fullaudit 6/6 全绿、bump 0.2.113
- **load 菜单翻页/confirm 残影修复（0.2.117）**: 目检全屏读档菜单（`save_load_menu`，nb_saveload.c）翻页后页导航消失侧残影——根因=**条件绘制元素消失侧无擦除**：`<`(page>0)/`>`(page<total_pages-1)（:143-144）与 confirm 弹层（prompt+Yes/No emboss 按钮，:149-154/:175-183）在 menu_layer opaque 全屏层合成缓冲中增量保留，翻到首/末页时退出侧箭头、退出 confirm 后 prompt/按钮残留为 ghost；**修复**：`save_load_draw` full 分支各条件绘制前无条件 `menu_layer_erase_to_base` 擦五区（箭头×2 (56/576,318,16,16)、页码防御 (310,330,20,14)、confirm prompt 带 (260,314,160,16)+按钮带 (250,370,140,22)），层关闭直绘 fallback 下 erase 为空操作（OOM 异常路径保持旧行为）；**全库同类问题排查结论**——画廊（整带 erase_to_base 三带先行）、对话框保存（confirm 出态 `fill_dialog_bg` 全内容区重刷）、settings（焦点指示双区 erase）、主菜单与 question（sel 双侧重绘）、musicmenu/settingmenu（未实现桩）均无此问题，nb_saveload 为**唯一**未被擦除保护的条件绘制 layer；页码 `%d/%d` 本身无条件等宽重画不残留、仅防御性擦除；make 0 err/0 warn、pytest 386 passed、fullaudit 6/6 全绿、bump 0.2.117
- **bg_load 读档界面背景 + 全屏保存菜单核实（0.2.116）**: 参考画廊背景（`bg_gallery`）接入方式把 `assets/common/png/bg/bg_load.png` 登记为 `images/bg_load.MAG`（images.map 追加 `--256color --cover` 行、demo-a2 ASSETS.DB IMG 表 id=16 插入、export_asset_table 再生 asset_map 增 `bg_load`=16）；`loadscen.nb` 读档界面背景 `bg(){yellow_grid}`→`bg(){bg_load}`（cover 占满屏幕、读档界面本体零改动）；**全屏保存菜单核实结论**——命令表/资产表/场景脚本全扫描确认现有**无任何全屏保存入口**：唯一全屏槽位菜单 `save_load_menu` 仅被 `loadscene` 命令以读档模式（is_load=1）调用（F6/主菜单 load→loadscen.nb），保存仅 F5 对话框版 `save_dialog_menu`；`nb_saveload.c` 内 `is_load=0` 保存分支自古无入口（历史亦查无 `save_load_menu(0,..)`/`cmd_save`），判定无需删除、保持现状（读档全屏场景与对话框保存菜单均保留）；IMAGE.DAT 21 资产（bg_load.MAG 21557B cover）、SCENE.DAT LOADSCEN 已更新、HDI 已重注入（28 new/3 updated）；pytest 386 passed、make 0 err/0 warn、fullaudit 6/6 全绿、bump 0.2.116——**P1** `core/lib/midi.{c,h}`（SMF format 0 解析：MThd/MTrk 校验、多轨合并、running status 展开、tempo map tick→ms 夹逼、delta 累积单调递增；`core/lib/endian.h` 新增 `read16_be/read32_be`；host 编译通过）；**P2/P3** `core/plat/hal_audio.c`（P2: `hal_audio_init`/`detect`/`hal_midi_out`；P3: `hal_pcm_play(data,len,rate,loop)/tick/stop`/`hal_audio_shutdown`——4 参收口：SE/voice 恒 loop=0 one-shot（devdoc 101 §4.3 调用方语义），loop=1 回绕为 HAL 预留能力当前无素材使用；0x0488 bit0 使能→base 0x04D0；`MPU_PROBE_ITER 20000`；`PCM_TICK_MAX_BYTES 2048`；86 板 A460/A466/A468/A46A/A46C；dactrl 8bit mono=0x50；速率码 0..7；g_pcm 静态状态机；EOF loop=0 自动停/loop=1 复位 pos；Make 0 err/0 warn）；**P4** `core/engine/audio.{h,c}`（AUDIO.DAT 常驻 farchive 8192；BGM：事件表（16ch）运行时 tick→ms 调度、song 数组循环回绕（wall0 重置 now）、`audio_tick()` 60Hz 驱动；16ch All-Notes-Off 停止；PCM 泵：`audio_stop_all()`/`audio_snd_play()`/`audio_vc_play()`；**P5** 工具链：`tools/naiz_audio/{wav_convert,gen_test_midi,pack_audio}.py`——WAV→.pcm（8B magic `NAIZPCM\x00`+rate 码+flags+6B 保留+数据）、测试 MIDI（format 0、480 PPQN）、AUDIO.DAT（复用 `toc_archive.py::make_toc_archive`；8.3 短名碰撞硬拒）；`export_asset_table` 新增 `AudioAssetMap`+三音频表；`build_game` 接入 `pack_audio()`；demo-a2 ASSETS.DB 登记 BGM×1+SE×2+voice×1；`nbook001.nb` 演示 `bgm()`/`sound()`/`voice()`/`bgm(stop)`；AUDIO.DAT 21148B/4 assets 已注入 HDI）；`tools/tests/test_audio_toolchain.py` 11 例全绿；**音频硬件**：MIDI=MPU-PC98 兼容（数据口 base+0、命令/状态 base+2、ACK=0xFE、UART 命令=0x3F）；PCM=86 板 YM3433B FIFO（bit7 输出使能、bit7 FIFO 满；bit5 选择、bit2-0 速率码；fifosize=(val+1)<<7）；BGM 走 MIDI MPU、SE/voice 走 86 板 PCM；SE 与 voice 共享单通道后到覆盖；PCM 数据由调用方持有至 play/stop 不自 free；MIDI 事件表常驻、.pcm 头 16B 常驻；引擎仅经 hal.h 访问音频硬件（`outb/inb` 限 plat 层）；ASSETS.DB `img_map` 新增 `BGM/SND/VC` 三类；pytest 386 passed、make 0 err/0 warn、fullaudit 6/6 全绿；**收尾（part1→part2，2026-09-18）**：`hal_pcm_play` 签名为 4 参 loop 版本后补全套回归验证（此前 fullaudit 停留于 3 参时期）——make 强制全量重编 0 err/0 warn、pytest 386 passed、fullaudit 6/6 全绿；B90/B91 已同步 4 参签名；`assets/common/png/bg/bg_load.png` 由用户后续自行处理；devdocs/101 属历史存档未改
- 归档读取侧 TOC 化 P3（devdoc 100，0.2.114）: **nb.c 接 SCENE.DAT**——`farchive_lookup_name`/`read_buf`/`name_match`(8.3 大小写不敏感)按 devdoc 回加；`g_scene_arc`/`g_scene_arc_open` 状态 + helper `nb_scene_archive_read`(lookup→read_buf 有界拷贝 cap-1 留 NUL、size≥cap 置 truncated、未命中返 -1)；`nb_init` 于 logo.nb 前 `farchive_open("SCENE.DAT",8192)` 成功置标志、失败 hal_log 警告继续；`nb_load` 重构为**归档优先/散文件回退单尾段**——归档命中整段拷贝进 nb.buf + NUL 收尾 + `num_lines='\n' 计数 + (前缀非空且末字节≠'\n' 时 +1)`（与 fgets 路径精确等价：nb_get_line 按 '\n' 分段、末行无换行也计 1，随机多组 LF/无\n 边界已推演验证）+ truncated 打 WARN（对齐现状文案），未命中走原 `fopen（"r"→文本模式）`+fgets 循环原样保留、失败路径零改动；**CRLF 防御落地**（devdoc §9.4）：pack_scenes 检测到 `\r` 即 WARN + 归一化 LF（归档读取仅认 '\n'；DOS 文本模式散文件路径本就剥 \r），测试 +1 例（CRLF→LF 字节断言）；B92 §3 数据文件/管线两行更新、B90 farchive 行补 lookup_name/read_buf；pytest 375 passed、make 0 err/0 warn、fullaudit 6/6 全绿、bump 0.2.114
- 归档打包侧 TOC 化落地（devdoc 100 P4，0.2.111–0.2.112）: 将 devdoc 100 归档方案**打包侧先行**——①**共享写包** `tools/naiz_lib/toc_archive.py::make_toc_archive()`（IMAGE.DAT/SCENE.DAT 共用布局：uint32 count + count×20B TOC {name[12],off,size} + 数据，复用 image_dat 常量）；`pack_images.py` 写出块重构为调用它（字节等价，映像输出 680442 B/21 项不变）②**场景归档** `pack_scenes()`（build_game.py）：`scene/*.nb` → `games/<game>/SCENE.DAT`（8.3 base 截断后判短名互异防 R25 类相撞、跳过 0 字节残留、单脚本 <32 KiB NB_BUF_SIZE、增量写出），`deploy_runtime` 接入；引擎读取顺延 devdoc 100 P1–P3 ③**散文件自动净化** `_prune_stale_scenes()`：删除 games/ 根目录不在当前 scene 源集合的 `.nb`，并与拷贝循环"跳过 0 字节源文件+WARN"配合，**games/*.nb ≡ scene/*.nb 非空子集**——demo-a2 历史残留 nbook005-020.nb/nopbook.nb 共 16 个 0 字节文件被清，下次 make 从基座重建 HDI 自动净化（inject.py 每次 copy2 干净基座）④**测试** `tools/tests/test_toc_archive.py`（字节向量/往返/旧 writer 字节一致回归/>12 名拒绝/collision/32K/增量/prune 5 例）；B90/B92 §3 更新；pytest 374 passed、make 0 err/0 warn、fullaudit 全绿、HDI --list-files 确认无残留
- CG 画廊背景 cover（0.2.110）: 画廊背景需**保证长宽比的前提下占满屏幕**——`mag_convert.py resize_to_screen` 增 `cover` 模式（scale=max 后**中心裁剪**到目标屏）、`convert_file`/CLI `--cover`/`build_game.py` images.map 行内选项透传，images.map gallery 资产加 `--cover` 重转；与 0.2.109 的 `cover` 无关（同属显示修复）；pytest/fullaudit 全绿
- CG 画廊四项显示修复（0.2.109）: 目检 CG 画廊（`cmd_cgvmenu`，nb_cggallery.c）四项显示缺陷——①背景显示异常：画廊首次进入 Previews 墙背景绘错（gallery 资产路径未入库/取错），注册 `gallery` 资产（images.map + ASSETS.DB id=15）并让 `gallery_exit_preview` 换回 `gallery`；②画廊内背景经 `.mag` 调色板**索引覆盖**保留位（248-255/7/15 被图像调色板冲成黑/白、按钮/文字/焦点色错乱）：`nb_cggallery.c` 所有绘制颜色改保留索引（蓝 255/黑 254/白 250/黄 251），进出画廊 `palette_save/set/restore`，预览底图索引裁剪（PR 区 clip 覆盖二次采样边界）；③标题不居中/下移：`draw_title_large` 居中改用 `text_width` 计算、GAL_ORIGIN_Y 32→44；④预览叠加残留：当前帧不归零，进出画廊用 `erase_to_base` 擦三段（标题带/墙带/预览带）；menu_layer opaque 全屏会话；pytest 334+、make 0 err/0 warn、fullaudit 全绿
- R30（整合机会规则落地，0.2.108）: R29 §8.3 建议落地——①**新增 4 条 C 规则**（39→43）：**C32**（AUTO）`strncpy()` 仅允许在 `core/lib/strutil.c` 内出现（R29④ str_copy 单一事实源回归守卫）；**C33**（HEUR）相邻 `layer_dialog_show();`+`dialog_layer_blit();` 对（`layer_dialog_clear()` 函数体内除外）→ 改用 `layer_dialog_clear()`；**C34**（HEUR）同文件重复静态数组初始化表（归一化内容 ≥2 处）→ 并单一事实源（slot_y/slot_ys 类）；**C35**（HEUR）同文件常量算术表达式重复（≥1 操作数为宏、≥3 处）→ 建议具名宏/常量（LAYER_DIALOG_CONTENT_* 类）②**symbol_audit `--gate`**：A/B 节任一输出即 exit 1（tools/diag/symbol_audit.py main 增 `--gate`，section_a/b 返回计数），`start.sh` fullaudit 第 5 步改 `-s A,B --gate`（此前只 `-s A` 且恒 exit 0、B 节死导出从未纳入判据）；`start.sh audit` 本色不带 gate ③规则基线登记：C35 首扫 10 候选全部核实为良性（缓冲尺寸/右边缘/掩码，layer_debug/layer_dialog/layer_sprite/nb_cggallery/nb_save_dialog/render/render_text/render_vram/settings_menu/keyboard），预存 C8/C9 5 候选核实良性，`--note` verify=ok 清零 open；pytest 362 passed、make 0 err/0 warn、fullaudit 全绿
- R29（全项目整合机会审计与落地，0.2.107）: devdocs/99 全量整合审计——按"重复必须收敛单一事实源、惯用式必须收口、死代码必须删净"三原则落地 7 组改动：①**死导出清零**（`symbol_audit` A/B 归零）：删 `layer_dialog_restore`（R28 后 0 调用方，R28 记账"保留供外部"裁定作废）、`menu_layer_is_open`/`menu_layer_pixels`（menu_layer.c，内部无依赖）、`layer_bg_snapshot_valid`（layer_internal.h，内部 :41 用静态 `snapshot_valid` 不经过函数）②**内容几何单一事实源**：scene_layers.h 新增 `LAYER_DIALOG_CONTENT_X/W/Y/H` 宏，替换 13+7 处 `X+INDENT`/`W-INDENT-RIGHT` 表达式（nb_save_dialog×6、nb_question×4、layer_dialog×4、nb_saveload+1）+ nb_save_dialog 两处 content_x/y/w/h 四元组 ③**nb_saveload 槽位内聚**：`slot_y[4]`(:98) 与 `slot_ys[4]`(:315) 并一份文件级 `slot_y[SLOTS_PER_PAGE]`；新增 `SLOTS_PER_PAGE`/`slot_abs(page,row)` helper 替换 9 处 `page*4+…` 与 `(SAVE_SLOTS+3)/4`、缓存数组维数 ④**干净盒正式收口**：`dlg_clean_box` static helper（R28）→ 提升为公共 `layer_dialog_clear()`（=show+blit，layer_dialog.c），nb_question:116-117 两行合一并顺带消 2 行 ⑤**标题双分支去重**（nb_saveload:112-126 if/else 尾段相同 `draw_title_large` → `drawn` 标志单调用）⑥**`str_copy(dst,n,src)` 新 lib 封装**（core/lib/strutil.c/h）：收口 26 处 `strncpy+NUL` 惯用式（11 文件）；行为差异=不零填充余量字节，逐站核过无依赖；⑦**菜单退出序列统一**：nb_menu 两处与 nb_cggallery 退出改为 `close(1)→flush→restore_palette`（对齐 nb_saveload），三个菜单出口补契约注释（settings 不触碰——palette 未改属正常差异）；B90/B93 同步；pytest 358 passed、make 0 err/0 warn、fullaudit 6/6 全绿、HDI 引擎 md5 一致；检讨：可整合内容大多不属 39 条"单点错误"型规则能力范围（见 devdocs/99 §8，建议"高重复表达式阈值"HEUR 规则 + symbol_audit A/B 纳入 fullaudit 判据）
- R28（对话框内保存菜单剧情字残留，0.2.106）: 目检对话框内 12 槽保存菜单（`save_dialog_menu`，nb_save_dialog.c）——打开与进入 confirm 时**剧情文字（角色名行+正文）透出、悬留**。根因=**`layer_dialog_restore()` 语义误用**：它只是 `dialog_layer_blit()`（把**含当前页剧情文字**的 480×115 合成原样盖回 VRAM，layer_dialog.c:301-304），被保存菜单当成"清空"用；`save_dlg_draw_slots` 的 `fill_dialog_bg` 只覆盖 `TEXT_Y`(28) 起的正文区（y308+），**角色名行 y286-300 从未被覆盖而残留**；`save_dlg_draw_confirm` 再 restore 把剧情文字全量盖回后 Prompt/槽位信息/Yes-No 直接叠画其上**不垫背景**→剧情正文从菜单字下透出。修复：抽静态 helper `dlg_clean_box()`= `layer_dialog_show()`+`dialog_layer_blit()`（合成重画干净框、无文字，即 nb_dialog.c:54,68 / nb_question.c:116,117 既有"新开一页"模式）替换两处 `layer_dialog_restore()`（入口 :58 与 confirm 入口 :237）；菜单进出两态底子均为干净盒，出口重建剧情页逻辑零改动；HDI 注入引擎 md5 与构建一致、fullaudit 6/6 全绿（续：R29 将 `layer_dialog_restore` 删除、static helper 提升为公共 `layer_dialog_clear`）
- R26（存档/读档错误提示 i18n+可读性，0.2.104）: 目检发现 `show_error_msg` 4 处硬编码英文（`nb_saveload.c:280/376` "No save data."、`:217/319` "Load failed."）未走 `tr()` 且不在 `SYSTEM_UI_KEYS`——i18n 管线不感知、CJK 语料缺字，同时以菜单「聚焦选中」黄（MENU_PAL_YELLOW）绘在自以为黑的盒上辨识度差、盒顶端 4px 压到页面指示器 `1/5` 与第三槽行。修复：①`show_error_msg` 文案改 `tr(msg)`、绘白底黑字（`fill_rect` 用 `PAL_WHITE`）；**文字黑必须用保留索引 `PAL_CURSOR_BLACK`(254)**——目检反证过两轮：先用调色板索引 0 误以为黑，但菜单/背景图调色板中 0 实际是白，白底白字不可读；`palette_reset_reserved` 仅保证 7/15/254 三色，黑字只能取 254（palette.c:54 断言驱动）；②三处 `(260,298)` toast 下移至 `(260,346)`——彻底避开槽行文本(≤294)/页面指示器(≤344)/Back(x 区间不含)/确认键(仅在 confirm 态)；confirm-fail 处（`LAYER_DIALOG_X+INDENT+168, TEXT_Y-10`，对话框白底内 toast）保持原位；③`SYSTEM_UI_KEYS` 增补 "No save data."/"Load failed."（对齐 "No CGs available." 先例），9 语言 `sys_<lang>.txt` 提供译文（简 暂无存档数据/加载失败、繁 暫無存檔資料/載入失敗、日 セーブデータがありません/ロードに失敗しました、韩 저장된 데이터가 없습니다/로드 실패、法/德/意/西/葡各一）；④**盒宽动态化**——固定 120px 盒裁掉超长译文（白日文 224px/韩 192/西 184/德意 152-160/法 144/葡 136，仅简繁 96 装得下），`show_error_msg` 改 `text_width()`（render.h:78 已导出、UTF-8 感知、CJK16/ASCII8）+ `tw+24` 内边距 + 最小 120 + `LAYER_SCREEN_W` 越屏左移 clamp + `draw_text` 裁窗同步 `x+w-12`；HDI 复读确认 4 语言 CJK 字库新字形齐备（CHI 106→112、CHT 106→111、JPN 117→122、KOR 211→216 codepoints）；pytest 358 passed、make 0 err/0 warn、fullaudit 全绿
- R23（菜单 UI 图层化 menu_layer，0.2.093）: 菜单按键 UI 图层化为**自包含可复用封装 `menu_layer`**（新 `menu_layer.c/.h`，`scene_layers.h` 引入；头部契约注释含最小接入示例）——①**渲染目标化**：`render_set_target(buf,w,h,stride,offx,offy)`/`render_set_target_vram()` 全局切换，`render.c` fill_rect/fill_rect_pattern/vram_pset_addr 增 RAM 分支（屏幕 clip+buffer 双重 C6 钳制），ui.c emboss 零改动自动跟随；②**透明 blit 原语** `render_blit_transparent()`（逐像素跳透明索引，VRAM_SET_BANK 宏分段）；③**menu_layer API 全套**：`open(x,y,w,h,transparent)`（clamp 屏幕、重复 open=重建、OOM 返 -1 调用方降级直绘 VRAM+C14 日志）/`begin_draw`（重接双 target）/`commit`/`blit`/`blit_rect`（自动求交幂等）/`close(restore)`（幂等置 NULL）/`is_open`/`pixels`/`erase_to_base`/`blit_sprite`（RAM 直拷，层未开降级 vram_blit_sprite）；**opaque**=base 快照（vram_read×2）+blit 含底+close(1) 整底还原，**transparent**=composite 填 PAL_TRANSPARENT 镂空、无 base、close 恒不还原；④**四菜单全部接入**（均全屏 opaque）：主菜单 menu_show（open→全量→blit，焦点移动增量会话 begin_draw→commit→blit_rect）、加载 nb_saveload（draw 包裹层化+标题 sprite 走 blit_sprite）、设置 settings_menu（删 bg_lang_name/ind/start_ind 三快照数组改 erase_to_base 语义）、画廊 nb_cggallery（preview 进出 close(0)→layer_bg_change 全屏→重新 open+draw_grid）；内容禁用调色板索引 15；pytest 334 passed、make 0 err/0 warn、fullaudit 全绿
- R27（菜单标题字模 RAM 目标修正，0.2.105）: 目检「读取」菜单标题异常——R23 菜单图层化（全屏 opaque `menu_layer_open(0,0,640,400,0)`）后帧内容入层缓冲、commit 整块 `vram_write` 盖回，但 **`draw_title_large` 的 2x 缩放字模路径（`draw_glyph_scaled`/`draw_cjk_scaled`，render_text.c）只直写 VRAM、无 `text_tgt_buf` RAM 分支**（R19 阶段 A 仅给 `draw_glyph_internal` 分流，1x 与 2x 路径分叉泄漏）→ 标题先直绘 VRAM、紧接 opaque blit 用缓冲（标题区=基底背景像素）整块覆盖 → 标题被抹、显示异常。西文黑体标题走 `menu_layer_blit_sprite` 入缓冲故无征兆，**CJK 语言 100% 触发**（读/存 LOAD/SAVE 文字标题 + CG 画廊 "CG GALLERY" 同为文字路径同样中招）。修复：两缩放函数位循环前经新 helper `title_pset(px,py,color)` 落点——`text_tgt_buf` 非空时屏幕坐标→缓冲坐标（`-offx/-offy`）越界剪裁后写缓冲、返回 1；否则返回 0 走原 VRAM 路径（层退化直绘/VN 场景零行为变化）；2×2 块四像素统一经 helper。pytest 358 passed、make 0 err/0 warn、fullaudit 全绿
- R25（i18n 8.3 短名化，0.2.100）: 「繁体字占空位」最后一根实锤——**HDI 注入 8.3 截名相撞**：`system_chi.txt`/`system_cht.txt` 基名 10 字符，`to_dos_name` 双截成 `SYSTEM_C.TXT`，注入时后写覆盖先写者，幸存内容与运行语言脱钩→简体字库配繁体文案，「開/載」空位、「始/入」正常（与 R24 的语言→字形路径无关，是部署管线文件命名缺陷）。修复：①系统表文件名全链路 `system_<lang>.txt`→`sys_<lang>.txt`（基名≤7 互异）：tr.c `i18n/sys_%s.txt`、i18n_gen 输出基名、gen_cjk_font.collect_cps 前缀 `("sys","role","game")`、项目与 games 部署 i18n 9 文件重命名、settings.txt/B92 注释同步（role_*/game_* 基名恰 8 字符不受截断影响）②**防呆**：`inject_common` 抽 `_check_dos_collision()` 覆盖**根目录+子目录**整批校验（此前子目录循环漏检，正是故障通道），碰撞即 RuntimeError 硬失败③**新测试** `tools/tests/test_dos_shortname.py`：注入校验函数、每项目 i18n 短名互异/基名≤8、system_ 遗留清零、scene 脚本 8.3（引擎启动文件 `startsetting`→`startset.nb`、`loadscene`→`loadscen.nb` 并同步 main.c/nb_mainmenu.c 字面量，validator 命令名不变）；AGENTS.md §十一 新增「游戏运行文件命名（8.3 强制）」硬性规则；pytest 358 passed、make 0 err/0 warn、fullaudit 全绿
- R24（语言全路径收口 nb_set_lang，0.2.099）: 简体修复后繁体仍报"部分文字缺失（占空位）"——静态穷举确认非字库覆盖（4 CJK system 译文 100% 命中各 CJK_*.DAT）非绘制路径（draw_text/draw_title_large 均已 CJK 化）；根因=**语言→字形脱钩**：CJK 字库仅 `cmd_startsetting`（nb_mainmenu.c）一条路径跟随语言变更，而**读档路径 `save_apply`（save.c）调 `nb_set_lang(s->lang)` 只重载翻译表不重载字库**，存档语言与当前字库部分重叠即"有的可见、有的占空位"（continue/读档可达）。修复：`nb_set_lang()` 收口为语言驱动渲染态**唯一事实源**（strncpy→tr_init+eng 回退→`cjk_load_for_lang(nb.lang)`→`text_set_blackletter(settings_blackdialog && !nb_lang_is_cjk())`），`nb_init` 手写语言块替换为 `nb_set_lang(settings_get_lang())`、`cmd_startsetting` 语言变更分支删冗余 cjk+blackletter 行（nb.c 增 #include "cjk.h"，nb_mainmenu.c 删未用 cjk.h）——启动/书内设置/continue/读档四条路径全部收敛；pytest 351 passed、make 0 err/0 warn、fullaudit 全绿
- R22（菜单 P0 改进，0.2.092）: 多图层落地后的菜单清点（plans/menu-p0-improvements.md），4 项行为等价改动——①**删死代码 `layer_get_bounds`+`LayerBounds`**（0 调用方，SPRITE/ANIM 分支残留 Option X 的 clip y<280 语义，与 R20 全高绘制冲突，误导维护；连带修 scene_layers.h 两处过时注释）②**`nb_saveload.c` 页级槽位缓存**：`slot_label_cache[4][128]`+`slot_exists_cache[4]` 按 `slot_cache_page` 键翻页失效，焦点/confirm 每帧不再 4×`slot_info` 读盘解析，save_game_slot 后失效重建 ③**`nb_cggallery.c` 解锁位图缓存**：`gal_unlock_cache[CG_COUNT]` 每次进入 cmd_cgvmenu 重建一次，cell/preview 不再每帧读 SYSTEM.SAV ④**`nb_question.c` 抽 `apply_option()`**：鼠标/键盘两路变量应用（lookup+`=`/`-`/`+`+INT_MIN 守卫）合一，-18 行；pytest 334 passed、make 0 err/0 warn、fullaudit 全绿
- R21（layer_sprite 小封装，0.2.091）: 最新 symbol_audit（20260910）A/B 节全空、E 节大簇裁决不拆（layer_dialog 内聚单模块/hal_mouse HAL 薄接口/accessor 簇平坦/bg·sprite·vars 已是拆分产物，与 R9/R16 先例一致）——仅执行 3 项行为等价微重构：①抽 `sprite_blit_full()` 收口 show/replace/redraw 三处 `image_load→vram_blit_sprite→mag_release` 重复；②face/replace 的 alloc 分支改走既有 `sprite_entry_update`（删手写 4 字段赋值）；③`layer_sprite_hide` 删与 `layer_bg_restore_rect` 内部快照守卫重复的外层预查；face/clip/NAIZ_DEBUG 探针逻辑零改动；pytest 334 passed、make 0 err/0 warn、fullaudit 全绿
- R20（运行目检修复：伪透明恢复 + cg 换图自动关框，0.2.090）: 目检推翻 devdoc 96 两项裁定——①**撤销 Option X 立绘裁剪**（对话框开启时精灵不再整层剪到 y<280；show/replace/redraw 恢复全高绘制、与对话框矩形相交，z 序=立绘在下、对话框合成在上）；伪透明经新**活动底 `dialog_occluder`**（480×115=under_dialog 纯底+立绘框内像素，与 dialog_layer 同生灭）恢复：`dialog_seed_base()`/recompose 改从 occluder 取底，PAT75 dither 孔透出立绘腿；`layer_sprite_sync_dialog_base()` 于每次精灵变更（show/replace/redraw/hide/hide_all）与开框时重建 occluder（reset 纯底→逐 active 精灵 RAM 落底→recompose 框+当前页盖回）；face 保留上半身 clip 不碰腿；replace/hide 的背景还原仍 clip_dialog=1 不盖框；`layer_bg_change` 经 redraw 尾 sync 自动重建底；动画帧不触对话框区无需复位；menu/option/save overlay 退出后洞仍透立绘。②**反转裁决 A 对 cg**——`cmd_cg` 资产分支恢复 `layer_dialog_hide()`+`nb_dialog_reset()`（`cg(){key}`=全屏事件并自动收起对话框、清空当前对白，下一句台词重新开框；`bg{}` 仍跨图存活，`cg(hidedialog)` 保留为显式收口指令）；`docs/B92` cg 两行语义更新、`docs/B90` 登记 occluder 三接口；pytest 334 passed、make 0 err/0 warn、fullaudit 全绿
- R19（对话框图层化四阶段落地，0.2.089）: 按 devdoc 96 分阶段完成——**阶段 A**（render_text.c `draw_glyph_internal` 末级写分流 RAM/VRAM，`text_set_target()`/`text_set_target_vram()`，`dialog_paint_box` 收 layer_dialog.c static）；**阶段 B**（layer_dialog.c 复合缓冲 480×115=框+当前页文字，删防腐账本 `dialog_snapshot`/`dialog_snapshot_valid`/`dialog_dirty`/`layer_dialog_snap`/`layer_dialog_mark_dirty`，`layer_dialog_refresh`/`restore` 归一为 `dialog_layer_blit`，`layer_dialog_show` 每页重画框清上一页文字，`nb_question.c` 开框后补 blit）；**阶段 C**（layer_bg.c 重写：`under_dialog` 改名保留换源直取 MagImage RAM**零 VRAM 回读**，删旧 `layer_capture_bg`/`layer_capture_bg_dialog_from_bg`，`layer_capture_bg_dialog_from_image` 行内拷贝钳制修 C9 越行 memcpy；`layer_bg_change` = blit+capture+redraw+recompose 尾 blit；删 `layer_dialog_clear`；Option X 收口——dialog 开启时精灵**整层剪裁 y<280**（show/replace/face/redraw/hide-restore 一律不碰对话框矩形，精灵变更零 dialog blit）、`layer_dialog_hide` 关闭时精灵**全身重绘**（裁决 B）；C28 行跨距读仍由 src_row-src_y 与 img_h 夹逼）；**阶段 D**（回退 R17：删 `cmd_bg`/`cmd_cg` 资产分支的 auto `nb_dialog_reset()`，`bg(){x}`/`cg(){x}` 换图后对话框**跨图存活**——`layer_bg_change` 的 recompose 分支重种 under_dialog 并经 `dialog_layer_store_render` 渲染投影（角色名/正文/偏移，dialog_show 与存档还原时写入）用 `layer_dialog_render_page` 重绘框+当前页文字，裁决 A 达成**框+当前页文字完整存活**；`bg(hidedialog)`/`cg(hidedialog)` 恢复为**必需**的收起指令；`nb_save_dialog.c` 读档恢复文字收口到 `layer_dialog_render_page`+投影+blit（菜单为暂态 VRAM 覆盖，缓冲为持久态），删 `layer_dialog_target` 死导出；`docs/B92` 两行语义回退、`docs/B90` 符号表更新；R18 移除的 demo-a2 `.nb` 尾随行按新语义不再还原）；pytest 334 passed、make 0 err/0 warn、fullaudit 全绿
- R18（范例脚本清理，0.2.088）: R17 已使 `bg(){x}`/`cg(){x}` 自身完成对话框全套复位——删除 demo-a2 `nbook001.nb` 中 `cg(){cg01}` 后的尾随 `cg(hidedialog)` 空转行（全项目 `.nb` 仅此一处），范例不再示范冗余写法；`bg(hidedialog)`/`cg(hidedialog)` 指令本体保留（语法/校验器/引擎零改动）
- R17（背景/CG 换图自动复位对话框，0.2.087）: `bg(){key}`/`cg(){key}` 全屏 blit 覆盖对话框区后,`layer_capture_bg→layer_dialog_clear` 仅复位图层状态、NB 翻页状态残留,脚本被迫尾随 `hidedialog` 且其 55KB 还原写属自写自读冗余——①`cmd_bg`/`cmd_cg` 资产分支补 `nb_dialog_reset()`(show 命令自身完成全套复位);②`layer_dialog_hide()` 加 `!dialog_drawn` 早退(layer_dialog.c:192,对话框未绘制时跳过 55KB 冗余写入,并修"对话框关闭态下精灵被纯背景误盖"潜在 bug,char(hideall) 可达);③`bg(hidedialog)`/`cg(hidedialog)` **保留为可选独立指令**(语法/校验器/脚本零改动),show 后尾随降为无害空转;`docs/B92` 两处语义补注;make 0 err/0 warn、pytest 全绿、fullaudit 全绿(detail: devdocs/95)
- R15（Tier3 规则扩充，0.2.085）: `test_bug_corpus.py` 原语料仅固化 R1-R8 真 bug——实测 R13/R14 共 8 个修复 bug **无一命中既有 35 条规则**（覆盖缺口实证）。新增 4 条 HEUR 规则固化：**C26** 所有权分离 free（mag_release 池 struct 逃逸 is_pool 守卫）/ **C27** 计数派生负下标（cmd_char `argv[argc-1]` 无 `argc<1` 守卫）/ **C28** 行跨距读无高度边界（cine 对话框 OOB，`img_w` 齐全但无 `img_h` 夹逼）/ **C29** 结构体指针仅起始越界检查（mag `off_img` 缺 `sizeof` 项）；另 `rules_c.py` 手动清单增 **C30** 对话框/sprite 背景恢复（layer_sprite_hide 幽灵）/ **C31** 菜单画廊焦点重绘（Back 残留）。四条规则均：旧形态命中、修复形态静默、全库 0 误报；语料 +4（8 个 R13/R14 bug 全部入册，规则退化即失败）、单元测试 test_c26–test_c29；规则总数 35→39、pytest 334 passed、fullaudit 全绿
- R14（再次全项目查 bug，0.2.084）: ①**调色板轨 cine + 对话框堆 OOB 读（高）**——`layer_capture_bg_dialog_from_image` 仅对 `src_row` 做屏幕高度（400）边界检查、未对图片自身高度限定；调色板轨 cine（640×280，`atype==1`）对话框打开时 `anim_rebuild_dialog_if_open`（nb_anim.c）逐帧把对话框区（y=280..394，115 行）从 280 行图读走 → 越界读最多约 72KB 堆后；修复为函数新增 `img_h` 参数并以 `src_row-src_y`（图像行索引）与 `img_h` 夹逼，cine 图不覆盖 280 以下的区域则跳过保留原快照 ②**mag.c `off_img` 边界检查加固（低）**——`off_img` 仅判起始是否越界，struct 尾部可能溢出；令判定覆盖 `off_img+sizeof(MagImage)` ③**nb_anim.c 重复字段赋值清理（非 bug）**——`playanima` 武装状态下同一批 `a->*` 字段被赋值两次（值相同）；去除前一份冗余 ④**审计候选清零**——本轮（③）去重致 2 条行号漂移 + 12 条既有候选（layer.c:80 switch 无 default 但初值兜底 / layer_debug.c:35 fwrite 诊断导出 / nb_anim.c:477 malloc 已判空 / mp4_to_ani.py:122 与 image_dat.py:36-37 与 env_utils.py:121 惰性导入 / gen_cjk_font.py:251-268 自校验读取失败即 loud）全部 `--note` 登记 verify=ok，open 37→0；make 0 err/0 warn、pytest 322 passed、fullaudit 全绿
- R13（全项目查 bug 修复，0.2.083）: ①**mag 池释放堆破坏（高）**——`mag_release` 对 `is_pool=1` 的图也执行 `free(img)`，而池图 struct/pixels 位于调用方 `decode_buf`（`nb_anim` 像素轨 `mag_decode_into`）内 → free 内部指针 + 与 `decode_buf` 双重释放，`playanima` 每推进一帧触发；修复为 `is_pool` 时跳过全部释放、由调用方整体释放 ②**cmd_char argv[-1] 越界读（中）**——R12 门禁下 `char()`/裸 `char`（argc=0、brace_arg=-1）时 `-1 != -1` 放行后执行 `name=argv[argc-1]`，补 `argc<1` 守卫（对齐 `cmd_bg`/`cmd_sceneconf`）③**layer_sprite_hide 幽灵残影（中）**——dialog 未绘制分支仅 deactivate 不恢复背景，`char(hideall)` 可达；补 `layer_bg_restore_rect` 恢复 ④**CG 画廊 Back 焦点残留（低）**——focus 从 Back 移回 cell 时未把 Back 从黄绘回白，补 `PAL_WHITE` 重绘 ⑤**mag.c off_img 多算 `sizeof(MagImage)`（低，潜在越界）**——struct 应紧贴 cropped 之后；令 `off_img = off_cropped + cropped_size`；均经 `--note` 登记/verify、make 0 err/0 warn、pytest 322 passed、fullaudit 全绿
- R12（对象/参数括号规范化，0.2.082）: 将 R11 的"对象在花括号负载、括号=参数±keyword"惯例扩展到全部资源类命令——`bg(effect[,transition]){key}`（fx/transition 回位参数槽，现为占位）、`char(pos[,expr[,type]]){name}`、`bgm(){key}`/`bgm(stop)`、`sound(){key}`、`voice(){key}`、`sceneconf(){title[,type]}`（paren 别名删除，仅花括号形态）；引擎 `cmd_bg`/`cmd_char`/`cmd_sceneconf`/`cmd_bgm`/`cmd_sound`/`cmd_voice` 均以 `nb_get_last_brace_arg()==argc-1` 硬性门禁，括号承载对象形态被拒绝；`nb_validator.py` 相应 6 命令签名+判定重写；脚本全量迁移 29 处（demo-a2 bg 11/char 12 + animatest bg 3，nbook001 补 bg）；CG 画廊 `cmd_cgvmenu` 引擎直调渲染不受影响；pytest 322 passed、make 0 err/0 warn、fullaudit 全绿
- R11（cg 双形态语法，0.2.081）: `cg(){<asset_key>}` 花括号负载展示 CG，`cg(hidedialog)` 关对话框还原背景（与 `bg(hidedialog)` 平行）；**括号位预留给未来参数、硬性拒绝 `cg(key)` 括号形态**——`nb_parse_line()` 新增 `brace_arg` 出参 + `nb.c` 文件级 `last_brace_arg` 访问器 `nb_get_last_brace_arg()`（`nb_internal.h`），`cmd_cg` 检查负载来源；根修 `layer_bg_change()` 移除 `!layer_dialog_drawn()` 门控、blit 后总是重采 `bg_dialog_snapshot`（对话框打开时展示 CG 后 hidedialog 回填旧 bg 矩形残影之根因）；`nb_validator.py` `cg` 签名改 `(0,1,'cg(){key}|cg(hidedialog)')` + 新旧形态判定；脚本 `nbook001.nb` `cg(cg01)+bg(hidedialog)` → `cg(){cg01}+cg(hidedialog)`；pytest 322 passed、fullaudit 全绿
- R1–R2: 36 项基础修复（B1–B5, E1–E11, N1–N28）
- R3: 13 项修复（P1–P17，含调色板泄漏、存档校验、VRAM HAL 封装等）
- R4: 13 项修复（Q1–Q10, L1–L7，含 off-by-one、死代码、溢出等）
- R5: 10 项修复（shell 注入+引用、offsetof、mag 解码健壮性、Python 工具链）
- R6: 9 项修复（save.c offsetof 回归、makegame.sh argparse 空串、make_base_clean 传播、mag 颜色流、nb_vars 溢出等）
- R7: verify CLI 修复（--note 自含 spec `REL:LINENO:VERDICT[:TEXT]`，根除多 note 共享单 --verdict 导致 verify_notes.json 数据污染）、image.c:65 补 hal_log 消除 fsize<4 静默失败、shell case 词加引号硬化（makegame.sh:165 / start.sh:271/304）、误报项 verify=ok 批量登记（S1/S5/P5/P8 共 24 条）、pending 候选计数负值 clamp
- R8（查 bug 系统 Tier1+Tier2 升级）: Tier1=①Bug 语料回归 `test_bug_corpus.py`（R1-R7 真实 bug 固化，规则退化即失败）②verify v2 行级 STALE（note 记录核验行文本，无关编辑不再整文件失效；v1 记录 sha8 兜底兼容）③RESULT 统一"violations + 全量 Verification 两行"，state v2 存 findings 明细 ④`--since <git-ref>` 新代码聚焦门禁（仅审计变更行，新违规照样 exit 1）；Tier2=新增 C22 INT_MIN 取负 / C23 同路径双重 free / C24 memcpy 尺寸交叉核对（AUTO）+ C25 use-after-free（HEUR），规则总数 35；**C22 首跑即抓到 R7 漏网真 bug**（nb_question.c:150/185 `-opt_deltas[hit]/[sel]`，已按 INT_MIN 守卫格式修补并补 `#include <limits.h>`）；内部清理 reset 后 32 候选全部 verify=ok 归零
- 整合修复: Bug-1（save checksum 偏移参数化）、Bug-2（venv 路径统一）、i18n 管线（tr 空值回退、nb_set_lang 重载翻译表、question/title 文本提取、i18n_gen 纳入 build）、工具链去重（B2/B3 toml 写入、B6 hdi walk 复用、B9 FONT.DAT 容器共享）、C2 text 死桩移除、C4 死常量删除、SAVETMP 死代码清理
- R9（拆分整合重构，全机会）: A=移除 `anim_playing()` 死导出；#1=`render_internal.h` 增 `vram_fill_row`（rep stosb）/`vram_row_write`（rep movsb）static inline，消 render.c/render_vram.c/render_blit.c 三处整行拷贝副本；#2=`palette_reset_reserved()` 收口 PAL_WHITE/TRANSPARENT/CURSOR_BLACK 三色重置（nb_commands.c/nb_cg.c 各消 3 行重复）；#3=CG 画廊自 nb_mainmenu.c 拆为独立 `nb_cggallery.c`（GAL_* 常量+6 static 辅助+`cmd_cgvmenu`）；#5=`slot_info` 头部解析收口到 `save_io.c` 新 `save_read_header()`（offsetof+SEEK_SET 直跳，槽位查询不再手搓偏移）；#4/#7 审计判定不需拆分；make 0 error、pytest 322 passed、fullaudit 全绿；symbol_audit A/B 节均空
- R10（日志/审计范围增强）: R9 复盘发现 `.h` 头文件完全在规则审计扫描之外（`collect_files` 只收 core/*/*.c + tools/*.py + shell）；已扩展 `tools.audit.audit.collect_files` 纳入 `core/**/*.h`（+42，files 125→167），C13(unused static)/C14(must hal_log) 对头文件门控排除（单头文件无法判定跨 .c 使用、inline helper 无日志义务）；R9 相关 3 条 open 候选（nb_anim.c:490 C1 / nb_commands.c:320 C8 / nb_commands.c:134 C9）经人工核实后 `--note` 登记 verify=ok（open 17→14）；头文件首扫 0 新候选、AUTO 违规 0；pytest 322 passed、fullaudit 全绿
- 动画制作工具链（2026-08-21，devdoc 77/78 制作侧；2026-08-23 裸名字查库制；2026-08-24 项目化架构；同日 `.na` 分离修订，devdoc 79）: 动画项目目录 `animation/projects/<项目名>/{config.toml,scripts/,db/}`（`tools.naiz_build.anim_project` 为架构单一事实源：`load_project` 校验 config.toml `[project] name`=目录名、`iter_projects`、`scaffold`；`anima.sh init <项目>` 创建骨架）+ **动画脚本 `.na` 后缀**（专属动画脚本、与剧本脚本 `.nb` 严格分离：解析器 `parse_anim_script` 入口拒绝非 `.na`（F1 门禁），脚本放 `scripts/<名>.na`，引擎零改动；原 naizbook/*.nb 约定废止）+ 脚本解析（animaconf/frame/base/pal 裸括号语法，F1+V1–V8 校验）+ `.ANI` 容器 v1（逐帧 tick 表取代固定 fps，L1–L5 装载校验，`tools/naiz_lib/anim_container.py` 权威实现）+ `anim_register.py`/`anim_import.py`/`anima.sh`（init/register/check/build `<项目>/<脚本>`/buildall/list；无参数进多级交互菜单：项目列表→操作菜单[check 检查登记/register 同步/生成动画]→脚本子菜单→build[/--sync]；`--sync` 构建前同步登记库；`check` 只读双向对账未登记/失效行/待更新，有差异 exit 1）；帧素材放 `assets/<项目名>/anim/`，产物全局 `animation/output/`；脚本花括号内写**裸名字**（无路径无扩展名），经 `./anima.sh register <项目>` 登记进 `animation/projects/<项目>/db/<项目>.db` 名字索引库（复合主键 (name,kind)，仅存索引不存图像字节，与游戏 ASSETS.DB 独立）后由解析器查库映射到具体文件；多图 `{f1,f2}` 显式交错序列共用秒数；pixel/palette 双轨端到端冒烟；播放侧（nb_anim/打包入库三件套）顺延

