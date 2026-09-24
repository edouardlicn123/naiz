# 98 — CJK 按语言语料精简字库：实施进度与换机续作计划

> 日期：2026-09-12
> 前置：devdoc 97（设计方案，本号为其实施进度记录）
> 版本：0.2.093 → 0.2.094（本轮 bump）
> 状态：实施主体完成；剩余「NP2kai 运行期目检」因本机串口环境不可用而挂起，待换机完成

## 〇、TL;DR

devdoc 97 的实施已完成除「串口确认切语言仅加载对应字库」外的全部软件改动与自动化验证（pytest 351 passed、make 0 err/0 warn、fullaudit 全绿、build 产物核对通过）；韩语译文与字库已就位。
唯一遗留是**运行期的人工目检**——本机两套串口 harness 均恒 0 字节（环境层问题，历史日志亦全空），改走截图像素分析证实 kor 语言下主菜单确实渲染（背景 + 两段白字文本带），但字形精读需目检，建议换机完成。

## 一、实施完成项（对照 devdoc 97 §十一 清单）

### 数据源
- [✓] `tools/naiz_font/unifont-17.0.05.hex`（官方发布页下载，P1 字形源，全 BMP）+ `UNIFONT-LICENSE.txt`
- [✓] `tools/naiz_font/CJK.DAT` 保留作 P2 图集源「仅源角色」，不再部署到游戏产物

### 工具链
- [✓] `gen_cjk_font.py`（重写）：
  - 公开 `load_sources()`（原私有 `_load_sources`）
  - `collect_cps(files, lang)`：`.nb` 多字节 + i18n 值列（`=` 右、跳 `#`/`# ORPHANED:`/空值）收集
  - `subset_from_atlas()`：CJK.DAT 图集子集；`merge_glyph_sources()`、`merge_ranges()`（相邻并 run、升序）
  - `generate_cjk_file()` 扩展：逐码位缺形 WARN（首个 60 条）、区间数 >2048 断言不写盘
  - 预设 `LANG_RANGES`：ENG 空；拉丁族 `[U+00A0-00FF]`；CJK 族 `[U+3000-303F]` + 语料；`--list-ranges`/`--atlas`/`--collect-*`
  - 实施期修 2 bug：`range_entries` 4 元组解包、预设残留 Basic Latin
- [✓] `build_game.py`：`deploy_runtime` 去 `CJK.DAT` 部署 + 删分语言拷贝 + 校验改 `FONT.DAT/BLACK.DAT`；新 `deploy_cjk_fonts()` 置于 `deploy_i18n` 之后（固定 10 语言全集、现场生成写 game_dir、10 文件缺失 ERROR、移除过时 CJK.DAT）

### 引擎
- [✓] `cjk.c` `MAX_CJK_RANGES` 128→2048
- [✓] `nb.c` `nb_lang_is_cjk()` 补 `"cht"`
- [✓] `tr.c` `tr_table` 静态 1024 条 → 堆动态（首 64、×2、上限 1024；`tr_init` 首行 free+置 NULL）

### 语料与配置
- [✓] `projects/demo-a2/config.toml` `[i18n] targets += "kor"`
- [✓] 韩语译文：`system_kor.txt`(9)/`role_kor.txt`(3)/`game_kor.txt`(26)，格式 `EnglishKey=KoreanValue`（曾反向书写被 `# ORPHANED:` 捕获并已重写修回）

### 验证
- [✓] `tools/tests/test_cjk_font.py` 新增 17 单测（修 4 个测试自身 bug：U+8A9E、jpn 文件名、merge cap、MAX_RANGES 边界、`_read_back` 计数）；全套 pytest **351 passed**
- [✓] `make -C core` 0 err / 0 warn；`start.sh fullaudit` 6/6 全绿
- [✓] `makegame.sh build demo-a2` 产物核对：`games/demo-a2/` **无 CJK.DAT**；10 个 `CJK_<lang>.DAT` 合计 29,860 B（KOR 8,138 B = 124 区间 / 192 码位；CHI/JPN 语料空→仅 64 码位基座；拉丁族 96 码位基座）+ stale CJK.DAT 移除生效
- [✓] 引擎契约 Python 仿真：CJK_KOR.DAT 头 1,994 B、124 区间 ≤2048、区间升序、首区 glyph_offset==头大小、fsize 8,138 == 10+124×16+192×32、kor i18n 全部 120 个韩文字值均可查非零字形（U+AC00 样例 34 像素）
- [✓] B92 §3.0 新增 + 数据表行改 `CJK_<lang>.DAT`；B90 四行更新；`bump_version` 0.2.094（重建注入 version=0.2.094）

## 二、运行期印证现状与本机限制

- 串口：`makegame.sh test demo-a2 --serial` 与 `tools.diag.np2kai_serial` 均**恒 0 字节**（sertest.com 亦 0）；仓库历史 serial 日志全为空 → 环境层问题，非本轮引入。devdoc 97 §十一 末项「串口切语言验证」在本机**无法完成**。
- 截图替代：`tools.naiz_screendig --launch -w 20` 截得 kor 启动 640×459 窗 → **`docs/runtime-shots/kor-mainmenu-20260912.png`**（190,892 B，自 /tmp 归档入仓）。像素分析：屏区 100% 非黑、背景采样 137 色、两段白字文本带 y76–204（4,734 白像素）与 y207–408（4,584 白像素）→ **kor 菜单确实渲染**。eng 对照帧 **`docs/runtime-shots/eng-boot-early-20260912.png`** 仅 9,545 B（截帧过早，黑屏），对比未完成。字形级「是否为韩文」需人工目检。

## 三、环境状态快照（交接用）

- 版本：`projects/{demo-a2,animatest}/config.toml` = 0.2.094
- `games/demo-a2/settings.txt`：**已还原 `lang=eng`** 并重新注入 HDI（kor 测试后）；场景源仍 eng
- HDI：10 字库在、无 CJK.DAT、无 sertest.com；内容与 `games/demo-a2/` 同步（清理后最后一次注入 43 new/3 updated/46 total）
- 遗留物：`games/demo-a2/sertest.com`（np2kai_serial 生成并已注入 HDI）——**已于写本 doc 当日删除并重注入**（见 §四 3）
- git：本任务改动 **全部 uncommitted**（tools/naiz_font/gen_cjk_font.py、tools/naiz_build/build_game.py、core/lib/cjk.c、core/lib/tr.c、core/engine/nb.c、projects/demo-a2/config.toml、projects/demo-a2/i18n/*_kor.txt、tools/naiz_font/unifont-17.0.05.hex、tools/naiz_font/UNIFONT-LICENSE.txt、tools/tests/test_cjk_font.py、docs/B90、docs/B92、audit_state.json）；另有 `docs/B02/B11/B12/B15/B16/B18` 的未提交改动属**上一任务**，勿混入本任务提交；commit 需用户授权
- AGENTS.md 头版本仍为 0.2.093/R23，**尚未更新**（待补本轮摘要）

## 四、续作计划（换机）

1. 运行期目检（有可用串口的机器优先）：`makegame.sh test demo-a2 --serial`，核对启动 `cjk_load_for_lang("eng")` → `CJK_ENG.DAT`；设置菜单切 kor → `CJK_KOR.DAT`；kor 菜单韩文字形无黑块
2. 无串口则补完截图法：等 30s+ 启动完成、多帧采样截 eng 菜单，屏区与 kor 截图双图比对；kor 韩文与否最终人工目检
3. [✓ 已执行 2026-09-12] 清理：删 `games/demo-a2/sertest.com` 并重注入（HDI 47→46 files，回正常计数）；settings 保持 eng
4. [✓ 已执行 2026-09-12] 归档截图至 `docs/runtime-shots/`（防 /tmp 丢失）
5. AGENTS.md 头更新：版本 0.2.094 + 本轮摘要（对应 R24 轮次）
6. 提交（需授权）：本任务相关文件一次 commit，照仓库日志惯例
7. 后续可选项（本轮不做，devdoc 97 §十）：i18n_gen 语言码对齐（fra/deu…→fre/ger…）、tr 缺失文件 WARN、Latin Extended-A