# 97 — CJK 按语言语料精简字库与拉丁语系准备方案

> 日期：2026-09-11（v2 细化复核）
> 前置：devdoc 87（CJK 按语言加载与游戏前设置菜单方案）、devdoc 96（对话框图层化）、B92 §3（数据管线）、B11
> 版本起点：0.2.093
> 状态：设计文档（仅设计，未实施；实施另立变更单）
> 复核结论：本版已逐条对照 `cjk.c` / `tr.c` / `font.c` / `render_text.c` / `settings_menu.c` / `gen_cjk_font.py` / `build_game.py` / `i18n_gen.py` 源码核实，原 v1 发现 2 处事实错误（构建时序、拉丁基座区间）并已修订。

---

## 〇、TL;DR

引擎**架构上已经是「选定语言后只加载该语言的一份字库」**（`cjk_load_for_lang` 单缓冲、切语言先释放旧缓冲）。真正的内存问题在于：**没有任何按语言生成的字库**，于是所有语言（含 eng）都回退加载全量 `CJK.DAT`（1,040,586 B ≈ 1.0 MB，含整块汉字区 656 KB + 日文假名 + Hangul 349 KB）。

本方案把「按语言字库」从"只切文件、内容仍全量"升级为"**按该语言实际语料收集码位**"：
- 韩语字库只含**用到的 Hangul 音节 + 用到的少量汉字 + 标点**（不含整块汉字区/日文假名），目标 <100 KB；
- 拉丁语系（fre/ger/ita/spa/por）**做好准备**：重音字形源可插拔（unifont.hex 优先生成、全量 CJK.DAT 子集兜底、缺失码位 WARN），pipeline 全通、只欠字形数据；
- 删除游戏产物中的全量 `CJK.DAT`（软盘省 ~1 MB，`tools/naiz_font/CJK.DAT` 保留作字库源图集）；
- 顺带：`tr_table` 静态 384 KB → 按需动态分配；`MAX_CJK_RANGES` 128→2048；`nb_lang_is_cjk` 补 "cht"。

---

## 一、背景与目标

### 1.1 背景

devdoc 87（0.2.065）确立了"按语言加载一个 CJK 文件、设置菜单选语言"的架构，并实现了：
- `settings.c` 语言持久化 + `settings_menu.c` 10 语言切换；
- `core/lib/cjk.c` 的 `cjk_load_for_lang()`：`CJK_<lang>.DAT` → `CJK_EN.DAT` → `CJK.DAT` 三级回退；
- 启动与设置菜单切换时按语言重载。

但 devdoc 87 的生成侧只"按语言预设整块范围"（KR 预设含完整 CJK 汉字区 20,992 码位 = 656 KB），且**从未真正生成/部署过任何 `CJK_<lang>.DAT`**——仓库只有全量 `CJK.DAT`，因此回退链必然命中全量字库。

### 1.2 目标

1. 选定语言后，内存中**只存在该语言的紧凑字库**，内容局限为该语言语料实际用到的字符。
2. 韩语加载时**不包含中文字符区/日文假名**。
3. 拉丁语系（含重音字母）渲染管道**就绪**，字形数据源可插拔。
4. 游戏产物不再携带全量 1.0 MB 字库。
5. 文本层常驻内存显著下降：当前「全量 CJK.DAT 1.0 MB + tr_table 384 KB」≈1.4 MB → 目标 <150 KB（按语料规模波动）。
6. 全部能力通过测试与 fullaudit 门禁。

---

## 二、现状盘点（2026-09-11 源码核实）

### 2.1 语言选择 → 字库加载路径（已满足目标 1 的文字描述）

| 时机 | 代码 | 行为 |
|------|------|------|
| 引擎启动 | `main.c:87-89` `settings_load()` → `settings_menu_run()` → `settings_save()` | 每次启动都跑语言菜单（含首次启动可改语言） |
| 启动加载 | `main.c:92` `cjk_load_for_lang(settings_get_lang())` | 按菜单选定的语言加载一份字库；失败 `ENGINE_EXIT(1)` |
| 设置菜单改语言 | `nb_mainmenu.c:94-102 cmd_startsetting` | `settings_menu_run()` → 语言变化则 `cjk_load_for_lang(新)` + `nb_set_lang()`（重载翻译表） |
| 加载器内部 | `cjk.c:95-99` | 新文件读入前 `free(cjk_data)` 旧缓冲；`cjk_data` 为唯一静态渲染字形缓冲 |
| 检索 | `cjk.c:123-155` | 单缓冲区上**二分查找**（前提：区间表按 start 升序），命中返回 32 B 字形 |

全仓无其它地方再载入字库。**行为层面「只加载对应语言」已经成立**；缺口在字库内容与部署。

### 2.2 当前部署实测

| 文件 | 大小 | 说明 |
|------|------|------|
| `tools/naiz_font/CJK.DAT` | 1,040,586 B | 全量字库（6 ranges、32,515 码位），同时是唯一字形源图集 |
| `tools/naiz_font/FONT.DAT` | 5,120 B | MHVN98 格式 ASCII 8×16；解析后缓存 `glyph_cache[256][32]`（`font.c:25`，+8 KB 常驻） |
| `tools/naiz_font/BLACK.DAT` | 6,972 B | 可选黑花体拉丁 16×16；加载后 `alt_glyph_cache[256][32]`（`font.c:122`，+8 KB 常驻） |
| `games/*/CJK.DAT` | 1,040,586 B | `build_game.py:222` 把全量从源目录拷贝部署；**没有任何 `CJK_<lang>.DAT`** |

CJKF 头（`cjk.c:10-14`）：魔数 4 B + 区间数 uint16 + 保留 4 B = 10 B；每区间 16 B（start/end/glyph_offset/保留）；字形 32 B/字。全量 = 10 + 6×16 + 32,515×32 = 1,040,586 B ✓。

### 2.3 全量 CJK.DAT 内容分解

| 区间 | 码位数 | 字节 | 占比 | 韩语是否需要 |
|------|--------|------|------|------|
| Basic Latin U+0020-007E | 95 | 3 KB | 0.3% | ✗（引擎 ASCII 路径走 FONT.DAT，`render_text.c:151`） |
| CJK Symbols U+3000-303F | 64 | 2 KB | 0.2% | ✓（基座） |
| Hiragana U+3040-309F | 96 | 3 KB | 0.3% | ✗ |
| Katakana U+30A0-30FF | 96 | 3 KB | 0.3% | ✗ |
| CJK Ideographs U+4E00-9FFF | 20,992 | 656 KB | 64.6% | ✗（只用少量汉字） |
| Hangul Syllables U+AC00-D7A3 | 11,172 | 349 KB | 34.3% | ✓ 但只用一部分 |

### 2.4 文本层常驻内存分解

| 项 | 大小 | 性质 |
|----|------|------|
| 全量 CJK.DAT（`cjk_data`，`cjk.c:36`） | 1,040,586 B | 常驻（语言无关，全部语言回退命中） |
| `tr_table[1024]`（`tr.c:28`，1024 × 384 B） | 393,216 B（384 KB） | **编译期静态数组**，与已载条目数无关 |
| `nb.buf`（`nb_internal.h:16`，`NB_BUF_SIZE`） | 32,768 B | 常驻静态 |
| `glyph_cache[256][32]`（`font.c:25`） | 8,192 B | 常驻静态 |
| `alt_glyph_cache[256][32]`（`font.c:122`） | 8,192 B | BLACK.DAT 加载时 |
| 合计（文本常驻） | ≈ 1.49 MB | — |

> 侧记：`image.c` 的 `g_image_data` 整载 IMAGE.DAT（demo ≈ 630 KB）是另一大类常驻，不在本方案范围。`cjk_ranges[128]`（16 B×128 = 2 KB）与 `font alt` 均为常量级。

### 2.5 渲染路径（决定"字库该收什么字符"）

`render_text.c draw_text`（`draw_text` 结构见 :116-231）：
- `*p < 0x80`（单字节 ASCII）→ `font_get_glyph()` / 黑花体 `font_get_glyph_alt()`（FONT.DAT/BLACK.DAT）；**CJK 字库无需收 ASCII**。
- UTF-8 多字节 → 解码码位 → `cjk_get_glyph(cp)`（16×16）。**未命中返回 NULL 时照常 `cx += 16` 空白跳过**（:225-227），无崩溃 → "缺字形=空格"语义在引擎侧天然成立。

推论：韩语音节 U+AC00–D7A3、中文 U+4E00–9FFF、日文假名、**拉丁重音字符（é＝U+00E9，UTF-8 双字节）** 全部走 CJK 字库；拉丁重音字符在全量 CJK.DAT 中**不存在**（无 Latin-1 补区）→ FR/DE/IT/ES/PT 重音字符当前一律空白。

### 2.6 命名机制不统一（今日不爆雷的原因：分语言文件都不存在）

| 处 | 位置 | 代码 | 与 ① 的差异 |
|----|------|------|------|
| ① 运行时语言码 | `settings_menu.c:44-47` | `eng jpn chi cht kor fre ger ita spa por` | 基准；`cjk.c:107-111` 大写化拼 `CJK_<lang>.DAT`；`tr.c:95-104` 拼 `i18n/system|role|game_<lang>.txt` |
| ② gen_cjk_font preset | `gen_cjk_font.py:43-54` | `EN FR DE IT ES PT JP CN CT KR` | JP vs JPN、CN vs CHI、CT vs CHT、KR vs KOR |
| ③ build_game 部署循环 | `build_game.py:231` | `EN FR DE IT ES PT JP CN CT KR` | 同 ②；且 `tools/naiz_font` 下并无这些文件（`:234 src.exists()` 恒假） |
| ④ i18n_gen 语言码 | `i18n_gen.py:22-25` `VALID_LANGS` | `eng chi cht jpn kor fra deu esp ptp ptb ita rus pol` | 欧洲码 fra/deu/esp/ptp/ptb 与 ① 的 fre/ger/spa/por 不一致 |

细节：
- **`kor`、`ita` 在 ④ 中合法**，故 demo 加 `targets += "kor"` 今天即可用（i18n_gen 不报未知码）——这与此前"④ 与 ① 冲突"的笼统说法需要细分：冲突仅存在于 4 个欧洲码（fra/deu/esp/ptp/ptb）；eng/chi/cht/jpn/kor/ita 两方一致。
- **规范统一为 ① settings 词条码**：字库文件名、i18n 文件名、构建机标识的单一事实源。②③ 属执行期清理对象；④ 为低优先对齐项（见 §十）。

### 2.7 三个附带的现状缺陷

| 缺陷 | 位置 | 影响 |
|------|------|------|
| `MAX_CJK_RANGES = 128` | `cjk.c:24,66` | 按语料收集后，零散韩语音节生成大量小区间，超限即 `cjk_init` 返回 -1 加载失败（见 §3.6 的量级推算） |
| `nb_lang_is_cjk()` 缺 "cht" | `nb.c:105-110` | 繁体中文语言下黑花体错误启用（黑花体仅拉丁，`config.toml` 注释也写明 chi/jpn/kor 才回退） |
| DEMO 无韩语译文 | `config.toml:27 [i18n] targets=["chi","jpn"]` | 没有 `i18n/*_kor.txt`，韩语字库只有基座；译文加入后每次 build 自动扩字 |

---

## 三、设计方案

### 3.1 总体：语料驱动的紧凑字库

```
        scene/*.nb ─┐
     i18n/*_<lang>.txt（值列）─┴─▶ collect_cps() ── 排序+合并连续码位 ──▶ ranges[]
                                                                         │
     字形源：unifont.hex 优先 ─┐                                        ▼
     全量 CJK.DAT 子集兜底 ─────┴─▶ 每码位 32B 字形 ──▶ CJKF v1 ──▶ CJK_<lang>.DAT
                                                                        │
              覆盖率复查（收集码位全部有槽位，缺字形码位逐条 WARN）
```

-CJKF v1 二进制格式不变，**引擎加载侧零格式改动**；CJK 语言基座恒含 U+3000–303F，拉丁语言基座恒含 U+00A0–00FF（Latin-1 补区全块）。

### 3.2 收集器 `collect_cps(files, lang)`

**输入文件**（`proj_dir` 为工程目录）：
- `scene/*.nb`：所有命令的 `text` 负载（含 sceneconf 标题、question 选项、mainmenu 选项——凡引擎会渲染多字节的文本）。
- `i18n/*_<lang>.txt`：三个文件 `system_<lang>.txt`、`role_<lang>.txt`、`game_<lang>.txt`。**只取 '=' 右侧的值列**（引擎 `tr.c:114-129` 显示的是翻译值；key 是英语源文，不含 CJK）。

**i18n 解析规则**（复刻 `tr.c load_file` 与 `i18n_gen merge_translations` 的约定，保证三方认知一致）：
- 跳过空行与 `#` 开头的行（含 `# ORPHANED:` 行）。
- 取第一个 `=` 的右侧；值空（`key=` 未译条目）不贡献任何码位。

**UTF-8**：逐文件按 UTF-8 解码（`errors='replace'`，与 `i18n_gen.py:43` 一致）。

**过滤**：只收集 >= 0x80 的多字节码位；ASCII 抛给 FONT.DAT 不收（引擎 ASCII 路径不查 CJK）。

**聚合输出**：
- 并按 (码位) 去重、升序排序后，**合并连续码位为 run** → `[(start,end), ...]`。
- 区间表按 start 升序输出——这是 `cjk_get_glyph` 二分查找的前提（`cjk.c:131`），且首个区间的 `glyph_offset` 必须等于 `10 + n×16`（头校验 `cjk.c:85-93`，不满足引擎直接拒载）。
- 0 码位合法：生成 10 B 空字库（`cjk_init` 接受 fsize≥10、count=0；`cjk_get_glyph` 一切查找返回 NULL，即"空白"）。

### 3.3 字形源与优先级（可插拔）

| 优先级 | 源 | 覆盖 | 说明 |
|--------|----|------|------|
| P1 | `tools/naiz_font/unifont*.hex`（GNU Unifont，实施时下载） | 全 BMP（含 Latin-1 补区） | 复用现有 `load_unifont()`（`gen_cjk_font.py:68-100`，自动把 8px 字形居中到 16×16）；本仓库无该文件时跳过 |
| P2 | 全量 `CJK.DAT`（保留作源图集） | 现 6 ranges 内码位 | 新增 `subset_from_atlas()`：解析头+区间表，按 32 B/字取槽；无需 .hex 也能离线出中文/日文/韩文子集 |
| 兜底 | — | 其他码位 | **零填 + 逐码位 WARN**（`[font] U+XXXX 无字形源`），永不静默 |

组合规则：逐码位按 P1→P2→兜底取首个可用字形。**基座整块缺失**（如拉丁基座无 hex）属更严重情形：该块全零 → 汇总行升级为醒目警告（`WARNING: Latin base U+00A0-00FF zero-filled (no unifont.hex)`），但不阻断出包。

现有 `generate_cjk_file()`（:121-151）已具备"缺失即零填 + 计数缺失"，本方案将其扩展为**逐码位归集缺形清单**并支持调用方传入字形 dict（P1/P2 合并结果），避免重复实现（先借后造原则）。

### 3.4 基座与语言映射（命名全按 ① settings 词条码）

| lang | 基座（永远包含） | 语料驱动 | 预期 CJK_<lang>.DAT |
|------|------------------|-----------|----------------------|
| eng | —（ASCII 归 FONT/BLACK） | 语料多字节 | ~0–2 KB（通常仅 U+3000 全角空格等） |
| jpn | U+3000–303F | 语料假名+汉字 | 按语料，目标 <150 KB |
| chi / cht | U+3000–303F | 语料汉字 | 同上 |
| kor | U+3000–303F | 语料 Hangul 音节 + 少量汉字 | 典型剧本几百~2千音节 → <100 KB |
| fre/ger/ita/spa/por | **U+00A0–00FF**（Latin-1 补区全块） | 语料重音+ASCII | hex 就位后 ~2–6 KB |

> 基座说明：现 `gen_cjk_font.py:35` 的 `EXTENDED_LATIN` 只到 **U+00C0–00FF**，漏掉 U+00A1（¡）、U+00BF（¿）、U+00D7（×）、U+00F7（÷）等。本方案以**全 Latin-1 补区 U+00A0–00FF**（96/95 码位，3 KB）替代，是对既有 preset 的修订（西班牙语必需 ¡¿）。
> 0x80–0x9F 控制区不收（无可见字形）。

### 3.5 构建接入与产物清理（`tools/naiz_build/build_game.py`）

**时序修正（v2 关键修订）**：现 `build_game()` 中 `deploy_runtime`（:417）跑在 `i18n_gen`（:420，刷新翻译模板）与 `deploy_i18n`（:421，拷贝 i18n → games）**之前**。若把收集放在 `deploy_runtime` 内，首构建时 `i18n/*_kor.txt` 还不存在/是旧版 → 收集缺料。故**新增独立步骤 `deploy_cjk_fonts()` 插在 `deploy_i18n` 之后**：

```
pack_images → palette 校验 → deploy_runtime(去掉 CJK.DAT/分语言拷贝)
   → i18n_gen(刷新模板) → deploy_i18n(拷贝 i18n) → deploy_cjk_fonts(新步骤) → 完成
```

`deploy_cjk_fonts(proj_dir, game_dir)`：
1. 语言全集固定 ① 的 10 个词条码（不依赖 config targets——保证设置菜单可选语言**每种都有字库**，回退链不触发）。
2. 收集源 = `proj_dir/scene/*.nb` + `proj_dir/i18n/*_<lang>.txt`（工程侧源文件，不依赖 game_dir 拷贝状态）。
3. 逐语言生成 `CJK_<LANG>.DAT` **直接写入 `game_dir`**（构建现场生成，无缓存/失效问题）。
4. 生成后覆盖率复检：收集码位全部有槽位（必然）；逐缺形码位 WARN 汇总（见 §3.3）。
5. 调用方式与既有 `export_asset_table.py`/`export_config.py` 一致：`subprocess.run([VENV_PYTHON, gen_cjk_font.py, ...], check=True)`。

**`deploy_runtime`（:218-301）同步改造**：
- `for font_name in ("FONT.DAT", "CJK.DAT", "BLACK.DAT")`（:222）→ 删除 `"CJK.DAT"`。
- 删除分语言拷贝循环（:230-239）与 `lang_codes = ("EN",...)`（:231）——分语言字库由新步骤在 game_dir 现场生成。
- 底部署后校验（:295-297）：`FONT.DAT/CJK.DAT not deployed` 警告 → 改为 `FONT.DAT/BLACK.DAT` 必在、**10 个 `CJK_<lang>.DAT` 必在**（缺失即 ERROR，杜绝回退链断裂）。
- 删除 `has_lang_cjk` "fallback to CJK.DAT" INFO 分支（:298-301，语义不再合法）。

### 3.6 引擎改动（极小型）

| 文件 | 改动 | 理由 |
|------|------|------|
| `core/lib/cjk.c` | `MAX_CJK_RANGES` 128→2048（:24；静态 `cjk_ranges` 2 KB→32 KB，BSS） | 承载语料驱动零散韩语音节区间（见下推算）；`cjk_init` 超限检查（:66）同宏自动生效；二分步数 log₂2048≈11 无感 |
| `core/engine/nb.c` | `nb_lang_is_cjk()` 增判 `"cht"`（:107-109） | 繁体中文属 CJK，应回退黑花体 |
| 加载/检索逻辑 | **零改动** | 格式不变、单缓冲不变、回退链保留（实际不触发） |

**韩语音节区间的量级推算（2048 上限的合理性）**：Hangul 音节 U+AC00–D7A3 的码位布局 = 按「初声×中声」分组、组内 28 个终声连续排列 ⇒ **单个 run 至多 28 码位**（同一初声×中声把全部 28 终声都用时才并成一个 run）。因此 run 数 ≈ 文本中「初声×中声」组合数（通常几百），2048 给出 5–10× 余量。防御：生成器断言区间数 ≤ 2048，超限报错不写盘（可再涨或走 §十 稀疏格式）。

### 3.7 `tr_table` 动态化（`core/lib/tr.c`）

现状：`static TrEntry tr_table[TR_MAX_ENTRIES]`（:28，1024 × 384 B = 384 KB）编译期整块存在，即使 0 条目；`load_file` 写入受 `tr_count >= TR_MAX_ENTRIES` 中断（:60）。

方案：

```c
static TrEntry *tr_table = NULL;   /* heap, grow on demand */
static int      tr_count = 0;
static int      tr_cap    = 0;

#define TR_MAX_ENTRIES 1024      /* 保留硬上限（与 load_file 中断语义一致） */
#define TR_INIT_CAP     64       /* 首块 64×384 B = 24 KB；满后 realloc ×2 */
```

- `tr_init()`（:83-107）：首行 `free(tr_table); tr_table = NULL; tr_count = 0; tr_cap = 0;`（切语言重载释放旧表，与现状"清零重建"语义一致）；`load_file` 首满 `tr_cap` 时 `realloc` 翻倍，达 `TR_MAX_ENTRIES` 即 break（现状行为）。
- `tr()`/`tr_get_count()`（:114-135）API 与遍历逻辑零改动（基于 `tr_count` 线性扫描）。
- 效果：demo 实际条目数十级 → 首块 24 KB（省 ~360 KB）；空语言更趋 0。
- 附带说明（本轮不改）：`load_file` 对缺失翻译文件是**静默跳过**（:42 `if (!f) return;`）——语言无译文=原样显示源文，语义可行；是否补 `hal_log` WARN 列入 §十 可选项。

### 3.8 覆盖率与「欠字」语义

- **槽位覆盖**：收集码位 = 字库槽位必要集，构建时必然全部落槽；引擎 `cjk_init` 的「首区间 glyph_offset=头大小」校验确保文件一致。
- **字形覆盖**：真正风险是"有槽位无字形"（源缺失→零填）。构建期逐码位 WARN（§3.3）。
- **运行期**：引擎零新增路径——无字形 = 空白格子（`render_text.c:225-227` 现状语义即如此）。脚本运行期不会出现"字库外字符"：字库由构建现场生成、与部署内容同源。
- **运维约定**：改台词/译文后须重建游戏数据（`makegame.sh build <game>`）；未重建时 i18n 值缺字风险由构建期 WARN 暴露。

---

## 四、语言—文件—范围映射（预期）

| 语言（词条码） | CJK 文件 | 基座 | 语料驱动 | 预期大小 |
|----------------|----------|------|----------|----------|
| eng | CJK_ENG.DAT | — | English 多字节 | ~0–2 KB |
| jpn | CJK_JPN.DAT | U+3000-303F | 假名+汉字 | <150 KB |
| chi | CJK_CHI.DAT | U+3000-303F | 汉字 | <150 KB |
| cht | CJK_CHT.DAT | U+3000-303F | 汉字 | <150 KB |
| kor | CJK_KOR.DAT | U+3000-303F | Hangul 音节+少量汉字 | <100 KB |
| fre | CJK_FRE.DAT | U+00A0-00FF | 重音+ASCII | ~3–6 KB（含 hex） |
| ger | CJK_GER.DAT | U+00A0-00FF | 同上 | ~3–6 KB |
| ita | CJK_ITA.DAT | U+00A0-00FF | 同上 | ~3–6 KB |
| spa | CJK_SPA.DAT | U+00A0-00FF | 同上（含 ¡¿） | ~3–6 KB |
| por | CJK_POR.DAT | U+00A0-00FF | 同上 | ~3–6 KB |

> Latin-1 补区基座全收：10 支拉丁语言的并集即全块，恒定收整块（字形数据仍按源可缺失告警）。

---

## 五、内存对比

| 场景 | 现状（全量字库+静态 tr） | 方案后 |
|------|--------------------------|--------|
| 默认 eng | 1.0 MB + 384 KB | ~0–2 KB + ~24 KB |
| 韩语（译文就位） | 1.0 MB + 384 KB | <100 KB + ~24 KB |
| 中文 | 1.0 MB + 384 KB | <150 KB + ~24 KB |
| 拉丁语 | 1.0 MB + 384 KB | ~6 KB + ~24 KB |
| 文本常驻合计 | ≈ 1.49 MB | ≈ 30–175 KB（按语言/语料） |

软盘侧：`games/<game>/` 删除 1.0 MB `CJK.DAT`，新增 10 个小字库（合计 <500 KB），净省 ≥0.5 MB；1.44 MB 盘面含 `IMAGED`（IMAGE.DAT）、DOS4GW、engine.exe 等，受益明显。

---

## 六、改动清单（文件级）

**新增**
| 文件 | 说明 |
|------|------|
| `tools/naiz_font/unifont*.hex` | 实施时下载（unifoundry.com 官方发布页），作拉丁/全量字形源（P1） |
| `tools/naiz_font/UNIFONT-LICENSE.txt` | GNU Unifont 许可说明（GPL-2.0 + 字体嵌入例外），参照现有 OFL.txt 惯例 |

**修改（工具）**
| 文件 | 改动 |
|------|------|
| `tools/naiz_font/gen_cjk_font.py` | 新增 `collect_cps()`（.nb+i18n 值列收集）、`subset_from_atlas()`（CJK.DAT 子集）、多字形源 P1/P2 合并 + 逐码位缺形 WARN；CLI 新增 `--collect-lang`（收集并生成单语言）/`--atlas <path>`（P2 源）；`hex_file` 已是可选位置参数（`nargs="?"`，:157），新模式下缺省即跳过 P1。**全仓无外部调用方（已核实）**，CLI 改动安全；`LANG_RANGES` 命名键对齐 ①（JP→JPN、CN→CHI、CT→CHT、KR→KOR、FR→FRE…）；`EXTENDED_LATIN` 扩为 U+00A0–00FF；既有 `--range/--lang/--all-langs/--list-ranges` 行为不变 |
| `tools/naiz_build/build_game.py` | `deploy_runtime`：:222 去掉 `"CJK.DAT"`；删 :230-239 分语言拷贝与 :231 旧 `lang_codes`；:295-301 校验改「FONT.DAT/BLACK.DAT 必在 + 10 个 `CJK_<后期命名>.DAT` 必在，缺失即 ERROR」；新增 `deploy_cjk_fonts()` 插到 `deploy_i18n`（:421）之后 |

**修改（引擎）**
| 文件 | 改动 |
|------|------|
| `core/lib/cjk.c` | `MAX_CJK_RANGES` 128→2048（:24） |
| `core/engine/nb.c` | `nb_lang_is_cjk()` 补 `"cht"`（:107） |
| `core/lib/tr.c` | `tr_table` 静态→动态（:28；首 64、×2、上限 1024、`tr_init` 先 free），`load_file` 中断改用 `tr_cap` |

**配置**
| 文件 | 改动 |
|------|------|
| `projects/demo-a2/config.toml` | `[i18n] targets` 增加 `"kor"`（`kor` ∈ VALID_LANGS，不触发 ④ 冲突；译文本体由外部补充后，构建自动扩字） |

**文档**
| 文件 | 改动 |
|------|------|
| `docs/B92-...md §3` | 字库部署改「按语言构建现场生成」、全量移除说明、命名规范（①） |
| `docs/B90-...md` | 登记 `collect_cps`/`subset_from_atlas`、gen_cjk_font 新模式、`deploy_cjk_fonts` |

---

## 七、测试与验证计划

**单元（pytest，`tools/tests/`）**
- 收集：空语料；纯 ASCII → 0 码位；多字节混合；**i18n 值列**（`key=值` 只取值；`#` 注释/`# ORPHANED:`/空值跳过）；重复码位去重；排序稳定。
- 区间合成：连续码位并 run；散射合成 run 数正确；升序；首区间 `glyph_offset == 10 + n×16`；**区间数 > 2048 时报错不写盘**。
- 字形源：P2 atlas 子集命中；P1 缺失→兜底+缺形清单；整块基座缺失→醒目警告。
- 基座：CJK 语言含 U+3000-303F；拉丁语言含 U+00A0-00FF。
- 引擎（C）行为：仓库无 C 单元测试框架（pytest 只覆盖 Python 工具链，`cjk.c` 不链接进测试可执行体），故引擎侧验证走 **`make -C core` 编译 + NP2kai 串口日志**（`makegame.sh test <game> --serial`）：堆造 0 区间（10 B）小字库与 >128 区间手工文件放入 game_dir，观察 `cjk_load_for_lang` 成功（`cjk: loaded ...`）；`nb_lang_is_cjk("cht")` 的切换用运行期改语言+黑花体回退行观察。
- tr：动态增长至满、超上限 break、`tr_init` 重载释放无泄漏（断言/Valgrind，视现有基建）。
- 常量镜像：`test_engine_constants.py` 只解析 `.h` 头文件宏并与 `naiz_lib` Python 镜像比对——`MAX_CJK_RANGES` 是 `cjk.c` 内的私有 `#define`，不在镜像范围，本轮不受影响（无需同步）。

**构建**
- `make -C core`：0 errors / 0 warnings。
- `./start.sh fullaudit`：pytest / py_compile / bash -n / symbol_audit / make 全绿。
- `./makegame.sh build demo-a2` 后核对：
  - `games/demo-a2/` 无 `CJK.DAT`；存在 10 个 `CJK_<lang>.DAT`，尺寸符合 §四；
  - `CJK_KOR.DAT` 在韩语译文未加入前仅为基座+语料（< ~5 KB）。

**运行时（NP2kai 串口日志）**
- eng 启动：`host` 阶段 `cjk_load_for_lang("eng")` → 加载 `CJK_ENG.DAT` 成功；改 kor 后 `CJK_KOR.DAT`。
- 韩语文本（译文就位）：音节字形正确、无黑块。
- 拉丁语（hex 就位）：é à ç ¡ ¿ 等正确；hex 缺失时日志出现基座 WARN 且不崩溃。

---

## 八、版本与合规

- 按 §十六 `bump_version`（改动引擎 `.c` 与工具 `.py`），一次调用同步全部项目。
- 无 GPL 代码拷贝：仅下载/引用字形数据文件（GNU Unifont：GPL-2.0 + 字体嵌入例外），不做代码传播；许可文件随数据落地（`.hex` 非代码，嵌入例外允许字库分发）。
- devdocs/ 为历史存档，本设计不修改任何既有 devdoc（含 87）。

---

## 九、风险与规避

| # | 风险 | 等级 | 规避 |
|---|------|------|------|
| R1 | 韩语音节零散导致区间数超 2048 | 低 | 量级推算（§3.6）给出 5–10× 余量；生成器超限报错不写盘 |
| R2 | 拉丁重音在 hex 未就位期间仍空白 | 中（可接受） | 明确为"准备态"；基座整块缺失升级醒目 WARN（§3.3）；`docs/B92` 注明"拉丁重音需 unifont.hex" |
| R3 | 删除全量 CJK.DAT 后某语言字库缺失 → 回退链全断 → CJK 空白 | 低 | 构建固定生成 10 语言全集（不依赖 config targets）；`deploy_runtime` 校验 10 文件必在（缺失 ERROR） |
| R4 | 收集/部署时序：收集跑了但 i18n 还没生成 | 已规避（v2） | `deploy_cjk_fonts` 置于 `i18n_gen` + `deploy_i18n` 之后（§3.5 修订时序） |
| R5 | 脚本/译文改动未重建数据 → 新字符欠字形 | 低 | 构建即生成（同源）；构建期 WARN 暴露；文档注明重建动作 |
| R6 | tr 动态化回归（切语言后旧指针悬垂被 `tr()` 使用） | 低 | `tr_init` 首行 free+置 NULL；`tr()` 基于 `tr_count` 无悬垂 |
| R7 | `MAX_CJK_RANGES` 双处（宏+静态数组）不同步 | 低 | 单宏定义共用；生成器断言 +>128 区间引擎测试双重护栏 |
| R8 | 删分语言拷贝后 `tools/naiz_font` 旧 `CJK_<③命名>.DAT` 残留被误用 | 低 | `deploy_cjk_fonts` 一律现场生成写 game_dir，不读源目录分语言文件；旧文件补清理动作 |

---

## 十、后续可选项（不随本轮）

- **CJKF v2 稀疏索引**：只存有字形码位+索引（4 B/字开销），无区间上限/零散顾虑、任意子集通用；代价=格式+加载器+全语言字库重建+v1 兼容。对本场景与 2048 上限的容量差 ≈十几 KB，工程收益低，留作未来多语言通用字号库候选。
- **i18n_gen 语言码对齐**（④ `fra/deu/esp/ptp/ptb` → ① `fre/ger/spa/por`）：低优先清理项，demo 未触发（`kor`/`ita` 已一致）。
- **tr 缺失翻译文件的 hal_log WARN**：`tr.c:42` 静默跳过改「文件缺失时一行日志」，低风险顺手项。
- **Latin Extended-A（œ/Œ、Š、Ž 等 >U+0100）**：语料收集天然覆盖（收集到即入字库），无需预设。
- **CJK 字库运行时解包到 RAM 直读**（PC-98 驱动器慢）：对本单游戏场景收益低，不推荐起步采用。

---

## 十一、验收清单（可勾选）

- [ ] `tools/naiz_font/unifont*.hex` + UNIFONT-LICENSE.txt 落地
- [ ] `gen_cjk_font.py`：`collect_cps`/`subset_from_atlas`/P1P2 合并/逐码位 WARN/新 CLI；hex 改为可选
- [ ] preset 键对齐 ①、`EXTENDED_LATIN` → U+00A0-00FF
- [ ] `build_game.py`：`deploy_runtime` 去 CJK.DAT/去分语言拷贝；新 `deploy_cjk_fonts` 置于 `deploy_i18n` 后；10 字库必在校验（ERROR）
- [ ] `cjk.c` `MAX_CJK_RANGES=2048`
- [ ] `nb.c` cht 判定
- [ ] `tr.c` 动态表
- [ ] config.toml targets + "kor"
- [ ] pytest 新增单测全绿；`make -C core` 0 err/0 warn；fullaudit 全绿
- [ ] build demo 核对：无 CJK.DAT、10 个小字库、尺寸符合 §四
- [ ] 串口确认切语言仅加载对应字库
- [ ] B92 §3 / B90 更新；`bump_version`