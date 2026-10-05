# Naiz — AI 编程规则

> **当前版本**: `0.3.021`（`projects/demo-a2/config.toml`）
>
> **最新条目**: `CHANGELOG.md` `c52` — **第十三轮：用户拍板 FM 通路输入格式 = MIDI + 新建 `devdocs/123-MIDI转FM通路实现计划.md`（12 章，计划中，零代码）+ 清三处遗留错误描述**。四项决策：**输入 = MIDI**（复用 `core/lib/midi.c` 不新写解析器）、**后端 = 自动检测**（有 MPU-401 走 MIDI，无则走 FM）、**v1 = FM 6 通道 + SSG 3 通道（RHYTHM 推迟）**、**音色内容另开 devdoc**。**devdoc 123 关键项**：M1 `fmopn` / M2 `fmseq` 落 `core/lib/` **零 `outb()` 可主机穷举单测**（最大风险削减点——绝大部分验证不需模拟器）；**S0（消解 `0188h`–`018Fh` 逐端口分工）只卡 S2 不卡 S1**（寄存器语义不依赖端口映射，调研等待期不阻塞主线）；**§2.4 架构级发现：`F02:100-101` 的 `A466h` 有 FM 音量路径（VOL1/VOL2）⇒ `bgm_vol` 对 FM 生效无需新增任何 pref 或设置项**（step 编码未实测，S5 确认）；**§2.3 代码级既存陷阱：`hal_audio.c:143` 的 `A460h ← 0x01` bit1 = 强制 OPNA 静音 —— 改 PCM 代码误动该值会静默静音整条 FM 通路而 PCM 一切正常**；FM 侧必须复用 `hal_wallclock_smooth_ms()`（devdoc 107 修过裸墙钟追帧音爆）。**文档修正四处**：**F03 §4.6 重写**（初稿自相矛盾：「只需换输出后端」紧接「解析器不能复用」，两句分属不同输入格式）、F03 §1.2 已决化、**mc06 订正 `2608_*.WAV` 归因**（是 **NP2kai 侧**补 YM2608 内置 ROM 的文件，**真机零素材依赖**；原写「PC-98 要另外备、缺了完全没声音」会让创作者误判工作量）、mc06 方案 A 已选定 / C 降备选 + 1b 交付代价 note、**devdoc 122 仅头部追加 `⚠ ERRATA`（190→280 行，正文一字未改）**，走 §十 四步路径 —— §5.2 推荐的「导出 WAV 进管线」**与本文自身根因二（PCM 单通道）直接冲突**且 `mc06` §3 方案 D 早已判死，两处结论长期互斥；另有 SSG 通道数错（2608=3 / 2612=9，非 6）、FM 音色「基本通用」过强、patch 许可断言无来源、`:213` 已收敛。`manual.html` ui02 的 `settings.txt` → `config.toml` + `USER.CFG`。**`mc07` 经核查无需改**（§3 工作流图末尾已是 `└─▶ 引擎（YM2608 后端）`）。**⚠ 另发现并已清理的更大范围错误**：`settings.txt` 已废止，但 guildbook **共 7 页 15+ 处仍在描述它**（初扫只报 5 页，**漏 `cf04` 补漏 2 处与 `cf06` 整页 3 处**）。据用户指示「按现状修正」已全部清理：**先取代码依据再改文档**——`settings.c`/`settings.h` **已不存在**、`settings_load()`/`GameSettings` **全仓零命中**，现状是 `config.toml` 经 `export_config.py` → `nb_config.h` 的 `NAIZ_*` 宏**编译进引擎、运行时零解析**（项目级）＋ `USER.CFG` 七键经 `prefs_load()`/`prefs_save()`（玩家级），语言实为 **9 种**（原 `ui02` 表只有 4 种）。`ui02` §1 整节重构为「配置文件分家」对照表、`cf01` 2 处、`cf02` 3 处（含**工具列 `build_game.py`→`export_config.py` 亦错**、删除已不存在的 `settings_load()` 链路）、`cf03` 1 处、`cf04` 4 处、`cf06` 3 处（初扫整页漏掉，`:75` 已补「**`make` 也要跑**」，见 §八 五禁之二），另顺带 `mc04:51` 与 `manual.html:47` 两处旧键名 `dlgstyle`/`btnstyle`。**残留复查**：`settings.txt` 仅剩 3 处且**全部是刻意说明其已废止**，旧键名零残留。**遗留未清（既存非本轮引入）**：`fd01` 一张表格行宽 2/3 不一致。前序  `docs/refdocs/F03_opna_fm_and_bgm_routes.md`（BGM 通路选型 + OPNA FM 寄存器参考，382 行，纯文档零代码）**：§1 四条通路（PCM/MIDI/FM/PMD）在**实机 vs NP2kai** 的对照与**待决**选型建议——**主线走自研 FM(OPNA) 后端、MIDI 降级为「检测到 MPU-401 才启用」的可选通路、不引入 PMD 作为运行时依赖**；三条硬理由：**OPNA 是板载标配而 MIDI 需扩展卡**（本仓 `F01:100-102` 板卡清单里 Qvision MidiMaster 标注为「WaveMaster 子卡」、`F02:33`「MIDI(BGM)在另一块卡上」）、**PMD 需从 32 位保护模式切回实模式调 INT 60h 撞 `B91` §3 禁止表且独占 OPNA**、**`hal_audio.c:143` 已在写 OPNA mask 寄存器**（bit1 = 强制 FM 静音 ⇒ 现成的 FM 静音通路已存在）；并厘清「借用 PMD」只借 **MML 记谱法**不借代码（`libopenpmd` 自述 WIP 且**只解析不管芯片输出**）。**纠正四个流传很广的错误前提**：YM2203 是 **3** 个 FM 通道不是 6 个（只有 YM2608 是 6）、**FM 通道 7/8 不存在于 OPN/OPNA**（属 YM2610）、**OPNA 无 LFO 波形选择**、**OPNA 无 `D2L`/`DT2L`**（OPN 是 `AR/D1R/D2R/SL/RR`）；**订正 FMP 官方文档**：其 SR 范围写 0–15 有误，实为 0–31（以 ymfm 为准）。§5 **证伪「S98 `.DAT` 音色库」**（S98 是寄存器转储日志，OPN 版 VGM），现存为 PMD `.FF`/MUCOM88 `.DAT`/Inst. Editor `.DAT`/FMP 内嵌；**未找到任何 CC0/公有领域 OPN patch 库且工具许可≠数据许可 ⇒ 建议自研 32 字节音色格式**；另记算子顺序被置换 **1/3/2/4**（错则静默音高全错）与 DT 编码跨格式不一致。§4.5 收录 **PMD 手册自身的 CPU 警告**（时值种类越多播放越耗 CPU，**游戏场景 BGM 尤其**）⇒ 建议 `#Zenlen` 取小值。**并订正第十一轮「无 PMD 可用 MIDI→MML 工具」的过宽表述**——ConvFMML 确以 PMD 为输出目标，结论改为「已停止维护 + 只转序列」故仍不可依赖。**§7 列 10 条未确认项，其中 `0188h`–`018Fh` 逐端口分工为「动手前硬阻塞项」（未取得可靠出处，猜错则 FM 通路静默无声）**。前序 **按用途拆为两页**：`mc06-音频通路机制`（机制解释（第八轮已改为人话、第九轮调整章节顺序）：三个能发声的部分 / 音乐文件有哪几种 / 引擎要吃哪种音乐 / **边界（第十轮改题）：WAV 能转 MIDI（适定、有解），但转不成 FM 音色（欠定逆问题、无解）** / 容易踩的坑）+ `mc07-音频平台与工具`（选型事实，第八轮已改为人话：Mureka 两路 / Magenta Studio / **免费档为何帮不上忙（Suno 按档位区分：Premier 的 Studio 已证实可 Get MIDI）** / 开源模型门槛 / AMT basic-pitch / tracker 工具 / 推荐工作流 / 许可须知；原 §5「选型陷阱」已于第八轮删除）。**AIVA 已按用户判定退出方案并从全部页面彻底移除**（免费档 MIDI 只挂旧版界面、入口实测无法复现、legacy 有下架风险 = 不可依赖）；调查与错误推断的留痕保留在 CHANGELOG 前三轮。**Mureka 官方证实 MIDI/WAV 导出为 Premier 专属**；API `Export Stem Audio` **$0.2/首可拿 `wav+midi`**、无需订阅，Premier 价格官方页面 JS 渲染查不到故不写入。**独立修正 Magenta RealTime 2 错标**：它是 `text-to-audio`、MIDI 是输入而非输出；本地产出 MIDI 的是 `magenta/magenta-studio`（Apache-2.0，需 Ableton）。**第十一轮 `mc07` §1.2 纠错（据 Gemini 材料逐条外部核对）**：**官方证实 Suno Studio 可 Get MIDI**（Stems 面板先拆最多 12 轨 → 右键单轨 *Get MIDI*，**10 credits/次**），故**修正「Suno ❌ 不提供 MIDI 输出」这一既有错误结论**、小节改为按档位区分、流程图 ① 补入 Suno Studio，并新增性质提醒（**Get MIDI 属转写非原始谱**，与 basic-pitch / Mureka 同类，受 mc06 §4 上限约束）；「两条未核实线索」缩为只剩 Veena；**否决 6 项错误或未证实内容**（`pmd2mml` 方向反、`mid2mml` 无 PC-98 版、`pmd.com` 未证实、完整 MML/PMD 流程与方案 A 冲突且属未决架构选型、「每声道单音」表述误导、量化建议依附已否决流程）；并按用户指示为山寨站警告补一个具体实例（仿冒站声称 $24-30/月，未证实故不写入）。前序 **第十轮 `mc06` 两处按用户指示修改**（§1 导语三句缩为一句、被删的「硬件上分开」论点核对无丢失；§4 主题由「有两件事」改为「**WAV 能转成 MIDI 吗？**」——导语改为先给答案再划边界、表格按 ✅ 在前 ❌ 在后调换行序、§5 与 mc07 §1.4 措辞对齐、note-box 末句补链接；**新增 mc06 → mc07 §1.4 编号引用**）。前序 **第九轮 `mc06` 三处按用户指示修改**（§1 表格新增「适合放什么」列、行序改为 FM→PCM→MIDI、表前加结论句；§3 与 §4 对调为「先选格式、再讲原理」；「产出工具见 mc07」补链接，连带修正 3 处因对调失效的编号引用）。前序 **第八轮 `mc07` 同样改写为人话并删除原 §5「选型陷阱」段**（4 条陷阱逐条核对确认已在 §1.2 / §1.3 / §2.1 有更完整表述故无信息丢失，§1.2 中指向已删 §5 的悬空引用已修正；随段消失的 Amper 案例与山寨站具体报价未保留，如需复现需另加；106 条特征事实改写前后校验全部保留；连带订正第六轮记错的跨页引用计数 3→4、5→6）。前序 **第七轮 `mc06` 改写为人话**（面向素材创作者、去掉实现腔：术语换说法不换事实，`FIFO`/`6 复音`/`欠定的逆问题` 等作为括注保留，50 条特征事实改写前后校验全部保留；当轮 `mc07` 未改，后于第八轮改造）。前序 `c52` 六轮 **`mc06` 核心论点为「分轨 → 单轨转写」的顺序**（Mureka 分轨恰好满足 basic-pitch「一次一件乐器」前提）。**第五轮精简**：原 253 行页面中同一论点最多重复陈述三次，§3.4 三个 note-box 合并为两个、§8 与 §3.2/§3.3 的重复删除、§5 流程图按 `east_asian_width` 实算列位重绘（原先竖线全部悬空）、「§8 陷阱 3」这类**按编号引用改为按名引用**（清单增删即失效）。前序 `c51` — 002 场景补 BGM + `voice`/`sound` 单通道争用根修（`hi` 被相邻 `ding` 瞬顶）+ 音频 key 登记守卫（devdoc 122，0.3.020）。前序 `c50` 音频源资产迁至 `assets/<项目>/`（BGM/SE/voice 三目录统一）+ guildbook 音频页 stub 描述订正（0.3.019）。前序 `c49` 翻译/脚本文本长度上限收口（5 对话框容量）+ tr 截断 fail-loud + 容量守卫（devdoc 121，0.3.018）。前序 `c48` 全部剧情脚本 9 语翻译补齐（28 键 ×9 语 0 空值）+ `Ira,not Neon` 转义标签入表（0.3.017）。前序 `c47` NB 字段逗号转义 `\,`（引擎/`i18n_gen`/`nb_validator` 三处同步）+ 常用问题选项归类 sys/game + `tr()` 守卫去注释误判（0.3.016）。
>
> **开发历史已移至 [`CHANGELOG.md`](CHANGELOG.md)**: R1–R30、0.2.109–0.2.117 及动画工具链等全部 Bug 修复/功能演进记录均以条目形式存于根目录 `CHANGELOG.md`，**本文件（AGENTS.md）不承载任何开发历史摘要，只存规则与当前版本**；历史速查一律读 CHANGELOG.md（最新：c52 / 0.3.021），新条目追加到 CHANGELOG.md 顶部而**不是**本文件。
>
> **防复发机制**: 见 §十七 — 每次修改后必须对照 C16/P11/S7 等 39 条规则逐一检查；**写完 devdoc 另须过 §十「规格与实现的收敛责任」**（行号校准 + 声称逐条落地，pytest 全绿不算证据）。
>
> **构建验证**: `make -C core` + **`core/*.err` 全为空**——诊断走 `.err` 文件，**不在 stdout**（0.3.014 教训，见下）。Python 工具链全部 `.py` 文件语法通过（`tools/` 下 120 个，含 `tools/diag/symbol_audit.py`，不含 venv/`__pycache__`）。pytest **642 passed, 1 skipped**。

## 一、Git 限制

- **禁止自动 commit / push**。只在用户说"提交""推送"时才执行。

## 二、目录结构

参考数据（目录树、guildbook 更新约定）已移至 `docs/B91-构建环境与参考速查.md §1`。
要点：代码严格按 core/tools/games/docs/devdocs 归类；`devdocs/` 为历史存档——**已完成的文档禁止修改**（头部状态标记完结/归档），未完成的文档（计划中/规划中/细化中）可继续修订。

### 源素材在 `assets/`，构建产物与脚本在 `projects/`（0.3.019 起）

`assets/<项目>/` 是**源素材唯一位置**（构建只读，不进部署树、不注入 HDI），与 `images.map` 的 PNG 源、`anim/` 帧素材同根：

| 素材 | 源位置 | 构建产物 |
|---|---|---|
| 位图 | `assets/<项目>/png/`（+ `images.map`） | `projects/<项目>/images/*.MAG` → `IMAGE.DAT` |
| BGM | `assets/<项目>/bgm/*.mid` | `AUDIO.DAT` |
| 音效 | `assets/<项目>/se/*.pcm` | `AUDIO.DAT` |
| 语音 | `assets/<项目>/voice/*.pcm` | `AUDIO.DAT` |
| 剧本 / i18n / config | — | `projects/<项目>/{scene,i18n}/`、`config.toml`（手写源，留在此处） |

- **`ASSETS.DB` 的 `filename` 列对 BGM/SND/VC 相对 `assets/<项目>/`**（`naiz_lib.project_assets_dir()` 单一事实源），对 IMG/SPR/CG/THUMB/ANI 仍相对 `projects/<项目>/`。`pack_audio()` **只认 assets 根**，不在项目目录回落；`wav_convert.register_asset()` 拒绝落在该根之外的目标。
- **音频源文件不注入 HDI**，故不受 §十一 的 DOS 8.3 约束（8.3 只作用于 `AUDIO.DAT` 的 TOC 条目名 = `name` 列，由 `pack_audio` 硬拒碰撞）。
- **防呆**：`tools/tests/test_audio_asset_paths.py` 断言 ①每行都能在 `assets/<项目>/` 解析到实际文件 ②`projects/*/` 下不得再有 `bgm|se|voice` ③`name` 非空且 8.3 截断后互异 ④源根推导不漂移。

## 三、构建与测试

参考数据（命令职责、引擎编译、编译隔离、pytest、基座 HDI、运行时链）见 `docs/B91-构建环境与参考速查.md §2`。

核心验证命令：
```bash
make -C core               # 引擎编译
find core -maxdepth 1 -name '*.err' -size +0   # 诊断在这里，不在 stdout（应无输出）
tools/env_setup/venv/bin/python -m pytest tools/tests/   # Python 单元测试
./makegame.sh build <game>  # 数据构建（games/<game> 部署树，含字库/i18n）
./makegame.sh make <game>    # HDI 注入（承接 build 产物）
```

## 四、运行时约束

参考数据（32-bit 保护模式必须/禁止表）见 `docs/B91-构建环境与参考速查.md §3`。
核心：**32-bit 保护模式**（DOS/4GW 首选，VEM486 DPMI 备选），PC-98 平台（NP2kai IA32 核心）。

## 五、架构约束

参考数据（HAL 边界接口表、平台无关 lib 模块表）见 `docs/B91-构建环境与参考速查.md §4`。
核心：`core/engine/` 只能通过 `core/plat/hal.h` 访问硬件；`outb()`/`inb()`/`int 0x18` 只能在 `core/plat/` 中调用。

## 六、refdocs/ 分类索引

PC-98 外部知识参考文档见 `docs/refdocs/README.md`（按 A–H 类分组：系统架构/内存I/O/显示/输入/存储/声音/编程参考/PDF摘要）。

## 七、关键参考

参考数据（参考项目、开发文档、NP2kai 模拟器、调试速查）见 `docs/B91-构建环境与参考速查.md §5`。

## 八、调试与实机验证纪律

见 `docs/B91-构建环境与参考速查.md §5.4`。串口输出（`makegame.sh test <game> --serial`）是最可靠通道。

### 实机验证五禁（0.3.010 起，出处 devdoc 117 §五）

这五条来自 0.3.009 一次根因误判的完整过程——**每一条都曾让错误的结论看起来完全正常**。诊断「一闪而过 / 无输入自行推进 / 首击无效」类症状时逐条对照：

1. **禁：把串口 trace 的一次性观察当因果证据。** `[INPUT] Mouse clicked` 是**输入被消费**的记录，不等于「用户点了」。0.3.009 之前把 CG 后的两次 `[INPUT]` 读成「无输入自动翻页」，据此定案「点击 FIFO 堆积」，而实际上那两次是用户真实点击。
   **正确判据**：看 `[MOUSE] g=0/0 d=0/0 b=0/…` 的**轮询序列**——`b=1` 之前若有一长串 `b=0`，则期间无输入被采样（原始 trace 是 37 次 `b=0`）。
2. **禁：只 `build` 不 `make`。** `build` 只部署 DOS 树（`games/<game>`），**`make` 才注入 `disks/<game>.hdi`**，而模拟器启动的是 HDI。只 build 不 make ⇒ 实机跑的是**旧引擎**，而旧引擎的日志**一切正常**，于是 A/B 报 PASS、结论全废却毫无报错。改引擎后必须 `./makegame.sh build <game> && ./makegame.sh make <game>`。**两道守卫已落地**：`makegame.sh test` 比对 HDI 与 `engine.exe` 的 mtime，过期即 `exit 1`；`tools/diag/np2kai_ab.py` 的 `preflight()` 返回 `STALE_HDI` 门控（由 `tools/tests/test_hdi_freshness_guard.py` 守护，删守卫即红）。
3. **禁：用竞态指标当判别器。** 「点几下才翻页」不是稳定判据——短句打字机约 0.6s 打完，探针自身开销即可错过窗口，回退版照样 PASS。
   **正确判据**：用引擎侧确定性标记（本例 `dialog_show: typewriter armed|off (single|paged page)`）做**否定断言**（探针 `--forbid`），点击计数仅作辅助。
4. **禁：门控只覆盖单一输入通道。** 采样门控只认鼠标 `b=1` 时，成功的键盘轮次会被误报为 `INPUT_NOT_SAMPLED`。门控标记必须与被测通道一致（键盘 `[INPUT] Key confirmed` / 鼠标 `b=1`）；同理，门控失败必须**非零退出**（`sys.exit`，不是 `print` 一个码）。
5. **禁：结论推翻后留下互相矛盾的文档。** 错因写在 CHANGELOG 标题、devdoc 正文、AGENTS 三处，后人会照错的排查。订正路径见 §十「结论推翻时的文档订正」。

> 反面教材与完整踩坑清单（含 XTEST vs XSendEvent、12ms 按压落在轮询间、点击落点落在窗口右边界、`--target` 起点选错）：`devdocs/117-单页对白重复arm打字机根修与输入边界收口订正.md` §五。

## 九、AI 协作原则

1. **先问再做**：不确定时提问，有更简方案主动提出
2. **至简至上**：最少量代码解决，不添加凭空想象的功能
3. **外科手术**：只改必须改的，保持现有风格一致
4. **结果导向**：定义成功标准，迭代至验证通过
5. **先读后写**：完整理解相关代码后再修改
6. **消灭静默失败**：异常/逻辑未命中时必须明确报错。**验证同样适用**：门控失败必须非零退出，且必须证明「测的是目标物」——**假通过比失败更危险**（实测：跑旧引擎的 A/B 报 PASS，日志一切正常）。详见 §八 实机验证五禁
7. **保持一致性**：命名、架构、意图与全局一致
8. **中文沟通**：compact 后自动切换中文
9. **英语注释**：日后所有 `.c` 和 `.py` 文件的代码注释统一用英语书写，不再使用中文注释
10. **先借后造**：开发新功能时优先检索项目内已有的可复用封装（`symbol_audit` B/D 节、B90 函数索引、`grep` 同前缀函数）；确无可用封装时，倾向制作可供后续复用的小而专的封装功能，而非内联零散逻辑

## 十、项目规则

- 代码严格按目录归类（core/tools/games/docs/devdocs）
- **所有项目统一入口为 `engine.exe`**，无 demo/其他之区分
- **每个场景切换时自动清屏为黑屏**（引擎层保证，无需脚本手动清屏）
- GPL v2 代码不得复制（传染性），优先借鉴思路
- 复制代码必须附来源项目 + GitHub + 许可证注释
- 安装失败先查 `logs/env_install.log` 末尾 200 行
- **用户要求"写 devdoc"时**：在 `devdocs/` 目录写入带数字前缀的开发文档（编号接续现有最大编号 +1，格式 `NN-描述.md`，如 `67-封装改进访问器收口与模块边界固化.md`）。devdocs/ 为历史存档，**已完成的文档禁止修改**（头部状态标记完结/归档），未完成的文档（计划中/规划中/细化中）可继续修订；编号由工具/人工按当前最大号顺延

### 结论推翻时的文档订正

「已完结文档禁止修改」与「结论被推翻」会正面冲突（0.3.008 的 devdoc 116 就是这么被逼出错因长期留存）。**唯一合规的订正路径**，四步缺一不可：

1. **原文档正文一字不改**，仅在头部状态行下追加 `> ## ⚠ ERRATA（<版本> 追加）` 块：写明被推翻的结论、错在哪、正确结论是什么、指向新文档；
2. **新建接替文档**（编号 +1）承载订正后的完整记录，含「症状 → 判定过程 → 根因 → 修复 → 验证」与踩坑清单；
3. **CHANGELOG 对应条目加订正标记**并链接新文档；条目标题若本身含错因（标题是历史速查入口），**允许连带改写标题，但锚点号与索引编号只增不改**；
4. **AGENTS 对应规则条目就地订正**——留在错误规则里的后果最严重，后人一定照它排查。

判定标准：**任何地方还留着一个已知错误的结论，就是未完成**。详见 §八 五禁之五。

### 规格与实现的收敛责任（0.3.011 起）

标为「完结」的 devdoc 同时是一份**规格**，故其正文中的 `file:line` 引用、函数名、符号名**必须与当前代码一致**——否则它是「已知错误的结论」，按上一条判定即未完成。

- **收口流程固定为**：实现 → **逐条核对规格中每项声称** → 校行号 → 标状态。`pytest` 全绿**不构成文档正确的证据**（无任何测试读 `devdocs/`，二者无因果关系）。
- **最容易漏的是「改动既有文件」类声称**：新增文件容易核对（文件在不在一目了然），而「文件被改过」这个事实会**掩盖「改的是不是声称的那一处」**——实测 `git diff` 全在注释里、函数体一行未动。
- **行号会随实现位移**：写于改动之前的勘察/设计文档，其行号对当时成立；改动后必须重校，尤其是描述**改动后**状态的章节。
- **防呆**：`tools/tests/test_devdoc_refs.py`（9 项）持续断言——行号引用可解析到含该符号的非空行、声称与测试文件事实相符、订正块未被静默删除、被引用文档存在。删守卫或改坏即红（devdoc 119）。

## 十一、显示管线约定

本节为**硬性规定**，未经明确许可不得更改。完整规范见 `docs/B02-显示管线规范.md`。

### 显示管线（固定）

```
video_init()          → PEGC MMIO + BIOS INT 18h AH=30h/40h + VRAM 清除
hal_set_palette()     → 模拟调色板端口（0xA8/0xAA/0xAC/0xAE），8-bit 值
fill_rect(0,0,640,400,0)  → 全屏黑底（VRAM Bank 切换，packed-pixel）
layer_dialog_open()   → VN 对话框黑底 + 白边（由首次 op_text 触发）
draw_text()           → 字模绘制到 VRAM 图形层
```

- 文字输出**禁止使用** `printf` / DOS 文本层——在 DOS/4GW + VEM486 DPMI 保护模式下不可见
- 只能用 `render.h` / `render.c` 提供的 VRAM 像素操作（`pset` / `fill_rect` / `draw_rect` / `draw_text` / `vram_blit` / `vram_blit_sprite` / `vram_pset_addr`）
- `font_get_glyph()` 从 `font.c` 获取 8×16 字形数据

### 引擎初始化顺序（固定）

```
hal_init()             → 串口调试通道
font_init("FONT.DAT")  → 8×16 字形加载
cjk_init("CJK.DAT")    → CJK 字形加载
kbd_init()              → 键盘中断驱动
mouse_init()            → 鼠标 8255 端口初始化（无 TSR 依赖）
video_init()             → PEGC MMIO + BIOS 模式设置 + VRAM 清除
hal_set_palette()        → 调色板（0=黑, 1=蓝, 7=白等）
fill_rect 全屏蓝底       → VRAM 初始蓝色背景
image_init("IMAGE.DAT")  → 图片归档加载
nb_init()                → NB 剧本引擎初始化（logo.nb 加载）
nb_process 循环          → NB 剧本解释器执行
for(;;)                  → idle 死循环
```

### 启动方式（固定）

- `AUTOEXEC.BAT` 启动（`engine.exe` 位于 AUTOEXEC 末行）
- **禁止使用** `INSTALL=` 方式（CONFIG.SYS 的 INSTALL= 会导致 NP2kai 黑屏）
- 所有项目入口统一为 `engine.exe`

### Sprite 对话框约束

- `layer_sprite_face()` **不得写入 y ≥ LAYER_DIALOG_Y (280) 的 VRAM 区域**。如需写入对话框区域（全身替换），必须用 `layer_sprite_replace()` 并主动调 `layer_dialog_refresh()`。
- `vram_blit_sprite()` 的 `clip_h` 参数（>0 时限定绘制行数）是保证此约束的架构级手段。新增 sprite blit 调用时必须传入正确的 `clip_h`。

### 游戏运行文件命名（8.3 强制）

**凡引擎运行期读取、注入 HDI 的文件（`projects/<game>/scene` 与 `projects/<game>/i18n` 源文件、`games/<game>` 部署产物、引擎启动帧文件等）必须满足 DOS 8.3 约束**：

- 文件名基名 ≤8 字符、扩展名 ≤3 字符；
- 同一目录下所有文件的 `to_dos_name()` 短名结果**互异**——杜绝截断同名的静默覆盖。

反例（本规则诞生的直接事故）：`system_chi.txt` 与 `system_cht.txt` 基名 10 字符，`to_dos_name` 双双截成 `SYSTEM_C.TXT`，HDI 注入后写者覆盖先写者，运行语言与幸存译文内容脱钩 → 简体字库渲染繁体文案，「開/載」占空位（R25 已改 `sys_<lang>.txt` 修复）。

**防呆**：`tools/naiz_img/inject_common._check_dos_collision()` 在根目录与子目录注入前整批校验，发现碰撞即 `RuntimeError` 硬失败（不得静默覆盖）；`tools/tests/test_dos_shortname.py` 对全部项目 i18n/scene 文件做 8.3 与短名互异回归。

**新增文件/改名的规则**：运行相关文件名一律直接取 8.3 安全基名（如 `sys_*`/`role_*`/`game_*`、`nbook*.nb`），不得依赖注入层截断来"擦边"。

### 配置分家：`config.toml`（项目）+ `USER.CFG`（玩家）（0.3.014 起）

`settings.txt` **已废止**（devdoc 120）。项目配置**不再经由任何运行时文件传递**：

| 载体 | 归属 | 内容 | 到达引擎的方式 |
|------|------|------|--------------|
| `projects/<game>/config.toml` | **项目** | `[project] version`、`[dialog] style`、`[button] style`、`[blackletter] title/dialog`、`[i18n] default_lang` | `export_config.py` 生成 `core/engine/nb_config.h`（`NAIZ_*` 宏）→ **编译进引擎**，运行时零解析 |
| `USER.CFG` | **玩家** | `lang` `text_speed` `bgm` `snd` `vc` `bgm_vol` `pcm_vol` | `prefs_load()` / `prefs_save()`，**全系统唯一的运行时写入点** |

- **`lang` 键全系统只有一个，在 `USER.CFG`。** 项目默认叫 `[i18n] default_lang`（键名不同，故永不冲突）。**这不只是命名洁癖**：0.3.013 之前 `lang` 同时存在于 `settings.txt` 与 `USER.CFG`，而 `settings_get_lang()` 读前者、`settings_set_lang()` 写后者 → 开机菜单选繁体中文后仍以英语启动。**同键名横跨两个归属相反的文件 = getter/setter 可各自绑定不同副本**，是本轮实机故障的直接根因。
- **禁止在构建/注入路径复制、注入、清理或绑定变量名后删除 `USER.CFG`**——那会让每次 `build` 重置玩家设置。直接事故：0.3.010 之前 `settings_save()` 写 `settings.txt`，而 `build_game.py` 无条件覆盖它（devdoc 118）。`build` 现在只**剪除**部署树里的死文件 `settings.txt`（`stale_settings.unlink()`），**只许 unlink，不许写**。
- 运行期写入只走 `prefs_save()`；缺 `USER.CFG` 为合法首启态（回落 `NAIZ_DEFAULT_LANG` / `TEXT_SPEED_DEFAULT`）。
- 重置玩家设置 = 删除 `USER.CFG`。改项目配置 = 改 `config.toml` 后重新 `build`（宏是编译期的，只 `build` 不 `make` 跑的是旧引擎，见 §八 五禁之二）。
- **防呆**：`tools/tests/test_user_cfg_settings.py::test_build_never_writes_user_cfg` 逐行守卫（允许 `.exists()` 探测与日志行，**「先绑定变量名再 unlink」这种写法同样被拒**），删守卫或改坏即红；同文件另有「`settings.txt` 不得复现部署路径 + 必须存在 unlink」「`lang` 只存在于 `USER.CFG`」「`config.toml` 拥有全部项目键」三项守卫。
- **访问器同源守卫**：`tools/tests/test_audio_settings_invariants.py` 断言 `prefs_get_lang()` 与 `prefs_set_lang()` 引用同一 struct 成员、且 getter 空值回落 `NAIZ_DEFAULT_LANG`。**任何新增的 `prefs_get_*`/`prefs_set_*` 对都必须登记进该守卫**——devdoc 118 已在 `audio_get_*` 上犯过一次，0.3.014 在 `lang` 上犯了第二次。

### 变更规则

对以上四节（显示管线、初始化顺序、启动方式、游戏运行文件命名）的任何修改，必须先提问、得到明确许可后再执行。

## 十二、独立项目说明

naiz_midi / naiz_music 已作为独立项目移出到 `~/`。详见 `docs/B91-构建环境与参考速查.md §6`。

## 十三、Token 优化参考

- 完整函数索引与 Python 工具入口：`docs/B90-参考-函数索引.md`
- NB 脚本命令参考（唯一集中源）与关键常量：`docs/B92-NB脚本命令参考.md`
- 数据管线与格式参考：`docs/B92-NB脚本命令参考.md §3`、`docs/B04-工具链API参考.md`、`docs/B11-MAG图片加载与显示规范.md`
- 开发历史精炼总结（devdocs 00–67 历史存档替代索引）: `devdocs/0.1版开发文档总结.html`
- 错误排查：`docs/FAQ.md`
- 快速查找：`grep -n '^void \|^int \|^uint \|^static ' core/engine/*.c core/lib/*.c core/plat/*.c | grep '('`；NB dispatch 用 `grep -n 'cmd_table' core/engine/nb.c`
- 封装/拆分审计（**替代**逐个 grep 手查 public/static 与跨文件引用，单次扫描 39 源 + 36 头输出 A/B/C/D/E 五节报表）：
  `python -m tools.diag.symbol_audit`（A=static 候选，B=死导出，C=耦合/拆分视图，D=符号清单，E=拆分簇；`-s A,E` 只出指定节）
- 封装工作流：用户运行 `start.sh audit` → 审计日志存 `logs/symbol_audit_<时间戳>.log` 并同步输出终端 → AI 读取最新日志的 A/B/E 节 → 核实后执行封装/拆分
- **规则审计工作流**（§十七 固化）：用户运行 `start.sh fullaudit [--no-make]` → 6 步流水线（规则增量审计/`start.sh audit` 同款 `./start.sh fullaudit`/pytest/py_compile/`bash -n`/symbol_audit/make）整体复用 `tools.audit.audit` 引擎（sha256 增量，状态存 `audit_state.json`，文件哈希不变则 SKIP；扫描范围 `core/*/*.c` + `core/**/*.h` + `tools/**/*.py` + shell，头文件对 C13/C14 门控排除）与 `start.sh audit` 的 symbol_audit 步骤，仅 `--no-make` 跳过 make 节；全部通过后按 `pytest`/`py_compile`/`bash -n`/`symbol_audit`/`make` 顺序输出 `[✓]`。**symbol_audit 第 5 步带 `-s A,B --gate`**：A（未用 static 候选）/B（死导出）节任一输出即 exit 1 判失败（R30），`start.sh audit` 本色保持信息用途不带 gate。AI 修改源码后应主动运行 `./start.sh fullaudit` 验证无回归。AI 核验启发式候选后应主动 `--note REL:LINENO:VERDICT[:TEXT]` 登记到独立 `verify_notes.json`（带**行级**快照，被核行文本未变则无关编辑不 STALE；v1 整文件 sha8 快照兼容加载；单条也可用 `--note rel:line --verdict ok/fixed/todo`）；新代码审查用 `--since <git-ref>`（仅审计变更行，新增违规 exit 1，未变更文件保留既往记录）
- **市场脚本 `tools/naiz_market/market.py`（根 `market.sh` 包装）**：从市场仓库（`market.toml` `[market] repo`，默认 `edouardlicn123/naiz_assets`）按需整包下载资源到 `<dest>/`（默认 `assets_samples`，gitignored）。**强制规律**：市场仓库**顶层目录 = 一个资源包**，整包下载、不做文件级选择；**包显示名规律**——目录名按 `_` 切分，首段 `()` 包裹、余段以空格连接（`images_sample_scenebg` → `(images)sample scenebg`）；`list`/`menu` 一律按此显示包名，包解析接受 原始目录名 / 后缀种类名 两种。后续更新本脚本必须保持此规律。**下载去重**：目标路径已有同名文件时默认跳过（打印 `SKIP (exists)`，不下载不覆盖）；需刷新用 `--force` 强制覆盖。四个子命令均支持 `--force`。**清屏**：仅交互 `menu` 在进入循环前调 `clear_screen()` 清屏一次（菜单重绘不再清，下载日志留在菜单上方），`isatty()` 为假或 `TERM=dumb` 时不发转义（管道/重定向保持纯文本）。
- **交互 A/B 诊断探针 `tools/diag/np2kai_ab.py`**（`python -m tools.diag.np2kai_ab`，0.3.010，devdoc 117）：NP2kai + xdotool 串口 A/B 探针。`--advance-to` 推进到前置标记 → `--target` 等目标状态 → `--clicks` 次输入 → `--quiet` 静默窗内判 `--expect`。**`--forbid` 否定断言为确定性判别，点击计数仅作辅助**（短句打字机约 0.6s 打完，点击计数是竞态）。任一门控（`STALE_HDI`/`NO_*`/`NEVER_REACHED_*`/`INPUT_NOT_SAMPLED`/`BUG_SIGNATURE_PRESENT`）一律**不报判定并 `exit 1`**。按键走 XTEST + 显式 150ms 保持（`xdotool key` 的 XSendEvent 被 wxWidgets 丢弃；12ms 按压落在 BIOS 端口轮询之间采不到）。需 `DISPLAY` + `xdotool`，**不进 CI**。用法与踩坑清单见 devdoc 117 §五/§六

### 变更后更新规约

每次修改涉及以下内容时，需同步更新对应文档：

- 增删改 C 函数 → 更新 `docs/B90-参考-函数索引.md`
- 新增/删除/修改 NB 命令 → 更新 `docs/B92-NB脚本命令参考.md`
- 新增/修改数据管线 → 更新 `docs/B92-NB脚本命令参考.md §3`
- 新增/移动 Python 工具 → 更新 `docs/B90-参考-函数索引.md`
- 新增/删除/修改构建环境/参考 → 更新 `docs/B91-构建环境与参考速查.md`
- **每轮 Bug 修复 / 功能演进完成 → 在根目录 `CHANGELOG.md` 的 `---` 分隔线下方第一条位置追加变更摘要条目**（含版本号、验证结果、`bump_version`），并同步 AGENTS.md 头部「当前版本」；**开发历史唯一载体 = `CHANGELOG.md`**，R1 起全部历史均已迁入，任何新历史条目（含修复/演进/工具）一律只写进 CHANGELOG.md，禁止再写入 AGENTS.md（AGENTS.md 只存规则与当前版本）
- **CHANGELOG.md 条目格式**：每条以 `### <版本号> — <标题>` 标题行开头（例：`### 0.2.135 — ...`），标题行上一行挂 `<a id="cN"></a>` 锚点（新条目取当前最大锚点号 +1）；同一步骤在顶部「版本索引」表**首行插入** `[<版本号> — <标题>](#cN)`（表序 = 新→旧）；正文整段或分小节均可（含版本号、验证结果、`bump_version`）。**锚点号只增不改，禁止改写历史条目的标题/锚点/索引编号**（历史速查依赖锚点与索引稳定）

## 十四、编码规约

### 输入循环
1. **入口 drain 一律调 `input_drain_boundary()`**（`core/engine/input_boundary.c`），**禁止裸调 `hal_kbd_drain_advance()`**。它 = `hal_kbd_drain_advance()` + `hal_kbd_set_ignore_frames(2)` + `hal_mouse_flush()`，三 call 缺一不可：
   - `kbd_drain_advance()` 虽擦 BIOS 环，但固定延时后即返回、**不等物理释放**，仍按住的方向键/推进键其自动重复码会泄入下一帧；
   - 鼠标侧**根本没有对应 drain** —— `hal_mouse_drain()` 只清 dx/dy 累加器，**不动 `mouse_click_fifo`**，只有 `hal_mouse_flush()` 清；注意 `blit` 期间不轮询是**采不到**而非**堆积**（`mouse_update()` 纯轮询、无 IRQ，一次按下+释放若整体落在两次轮询之间即完全不被采样）
2. 超时保护：忙等循环引用 `KBD_WAIT_MAX_ITER`
3. 语义查询：`kbd_is_pressed()`（非消耗）vs `kbd_is_down()`（消耗）
4. scene 切换：`nb_load()` 末用 `input_drain_boundary()`
5. **例外（语义不同，勿合并）**：ESC 前 `hal_kbd_flush()`、dump 后 drain、**消费之后**的 `hal_mouse_flush()`；`nb_saveload.c:show_error_msg()` 的 `drain+wait_any+drain` 三连；分页内节流
6. **阻塞命令元数据是死的**：`nb_commands_dispatch()` 不读 `CMD_BLOCKING`/`CMD_NEEDS_INPUT`/`CMD_TOUCHES_AUDIO`/`CMD_TERMINATES_SCENE`（仅作文档用，`test_cmd_meta.py` 只强制 `CMD_TOUCHES_DISPLAY`）。阻塞命令**必须自建输入循环**，返回时脚本才可继续；引擎侧唯一暂停点是 `nb_process()` 的 `nb_dialog_pending()`。漏写自暂停 → 剩余脚本在单个 pass 内跑完（详见 CHANGELOG 0.3.008 / devdoc 116）
7. **`cg`/`bg` 之后须紧跟对白行**：长耗时非阻塞显示操作后若不接对白页，剧本会在同一 pass 内连续跑过多条命令，玩家来不及看清新画面；对白页的 page-yield 同时是消费者的等待点。连写多个非对白命令（`cg` + `char` + `delay`）会跳过这个等待点。`playanima` 后接 `bg`/`cg` 亦须留意 `anim_stop()` 唤醒门控（0.3.008 起仅 `was_waiting` 时唤醒）
8. **单页对白不 arm 打字机**（`0.3.009` 根修）：`dialog_show()` 中「能装进一页的整句」（`page_start == 0 && next < 0`）已被 `layer_dialog_render_page()` 完整绘制，**不得再进 typewriter 分支**——那会用空前缀覆盖整页再重打（视觉「一闪而过」），并使首击被 `nb_dialog_reveal_finish()` 吞成无效操作、需两下才翻页；多页行所有页（含末页）则保持打字机。`dialog_show()` 输出 `typewriter armed|off (single|paged page)` 标记，改动该处后**用 `tools/diag/np2kai_ab.py` 的 `--forbid` 判定，不要靠点击计数**（短句约 0.6s 打完，点击计数是竞态）
9. **段内字段逗号须转义 `\,`**（`0.3.016`）：`question`/`scene` 的段内字段逗号分隔，字段内容含逗号写 `\,`（`\\`→字面反斜杠，其它 `\x` 原样保留）；问题标题（argv[0]）不切逗号、无需转义。逗号语义**只有一份实现**，任何新增的「取第 N 个字段」代码必须走 `nb_next_field()`/`nb_has_field_delim()`（C）或 `naiz_lib.nb_line.next_field()`/`has_field_delim()`/`option_fields()`（Python）——`nb_validator` 曾因自建 `seg.split(',')` 把合法 `Ira\, Jr.` 误判为「5 fields」，`nb_scene.c` 三处裸 `strchr(',')` 同型。`i18n_gen` 取键必须与引擎 `tr()` 查键逐字节一致，否则译文静默失效（`test_nb_field_escape.py` 守护）

### 菜单 UI 渲染（两阶段绘制）
1. 入口全量绘制一次（`draw_rounded_emboss` 等昂贵原语只画一次），循环内只增量改文字颜色/指示符
2. 光标：`mouse_draw_cursor()` save/restore，禁止 `mouse_draw_cursor_ez()`
3. 全量重绘前调 `vblank_wait()`，重绘后调 `mouse_draw_cursor_force()`
4. 反例：循环内 `draw_rounded_emboss()` / `fill_rect(0,0,640,400,0)` / `slot_info()` 全量刷新
5. 参考：`nb_menu.c: menu_show()`、`nb.c: save_load_menu()`

### 系统界面 i18n（强制翻译）
1. 系统界面文字（按钮/标题/确认框/画廊/存档界面等**硬编码字符串**）一律以**英文为基准文案**，并必须经 `tr()` 渲染
2. 禁止硬编码英文直绘（`draw_text` / `draw_text_outlined` / `draw_title_large`）；例外仅限纯数字/格式串（`%d/%d`、`<` `>`、`CG %02d`）、语言自名、版本号
3. 新增 UI 字符串必须同步登记 `tools/naiz_conv/i18n_gen.py` 的 `SYSTEM_UI_KEYS`，否则 `i18n_gen` 重生成时被标 `# ORPHANED` 使译文失效
4. 必须为 `config.toml` `i18n.targets` 各语言在 `sys_<lang>.txt` 提供对应译文；空值视为未完成（运行时回退英文）
5. **译文必须「放得下」，不只「非空」**——`draw_text` 在 x1/y1 处**静默裁剪**，超宽不报错、不编译警告，只会看板上少字。凡有固定宽度的绘制区域（设置行标签区 `SET_LABEL_W`、值列 `SET_VAL_W`、按钮、对话框），新增/修改译文后必须确认各语言 `text_width` 均在限宽内：
   - 度量须与渲染器同规则：`text_width()`（`render_text.c`）按**字节高位**判定，`FONT_GLYPH_W`=8 / `CJK_GLYPH_W`=16——**变音符拉丁字母（`ä`/`é`/`ã`）按 16px 计**，不是 8px；
   - 优先**改译文**而非改几何：几何一动牵连箭头/命中区/居中公式；确有成例可循（`nb_saveload.c:44` 错误框按 `text_width` 动态加宽）时才动几何；
   - **防呆**：`tools/tests/test_i18n_label_width.py` 从 `font.h`/`cjk.h`/`nb_setting.c` **读取**宽度常量与行几何，对 9 语言的行标签（7 个）与值标签（13 个）断言不超限；删守卫或改坏即红（devdoc 119 §3.4）
6. 含 `%d` 等格式串整句翻译（译文保留 `%d`），经 `snprintf(buf, tr(fmt), n)` 展开
7. 角色名与剧情文案的**原文基准遵循项目设定**（脚本原文 / `char_map` 规范名 / `source_lang`），其翻译照常经 `role_<lang>.txt` / `game_<lang>.txt` 提供——本节强制范围仅限**系统界面文字**（`sys_<lang>.txt`，8.3 安全基名）

### 语言选择（Language）归属
- **Language 行永久留在开机菜单**（`settings_menu.c` / `startsetting`），游戏内设置场景（`settingmenu` / `nb_setting.c`）**不得新增 Language 行**
- 机制原因：开机菜单运行于 `tr_init()` + CJK 字库加载**之前**，必须纯 ASCII 绘制；且语言须在翻译表存在**之前**选定，故游戏内无法安全改语言
- 开机菜单仍每次启动显示（Language + Start Game），只承载语言选择；其余设置项（Text Speed 等）走游戏内设置场景

### 对话框文字清除
- 标准方法：`layer_dialog_restore()`，禁止 `fill_rect` / `fill_rect_pattern` / `scene_draw_dialog()`
- 原理：快照 `dialog_snapshot[]` 按 `g_dialog_style` 恢复，无 ghost 残留

### 音频通路（PCM 单通道，devdoc 122）

三条通路硬件不同，**「有声音」不能推出「BGM 通路正常」**，排障时先分流：

| 通路 | 硬件 | 引擎 | 现状 |
|---|---|---|---|
| BGM | **MIDI over MPU-401**（PC-98 扩展卡） | `core/lib/midi.*` + `hal_midi_out()` | 本地静音（宿主无 MIDI 设备，`hal_audio_detect()` 返回 0） |
| BGM（**规划中**） | **FM over 86 板 OPNA**（板载标配） | **未实现** —— 计划见 `devdocs/123` | HAL 至今**无任何 YM2203/YM2608 端口访问**，FM 通路不存在；`0188h`–`018Fh` 逐端口分工未证（动手前硬阻塞项） |
| SE / 语音 | **86 板 YM3433B PCM**（标配） | `pcm_play()` + FIFO 泵 | 可闻 |

1. **86 板只有一条 PCM FIFO，`sound` 与 `voice` 共享、后到覆盖**（`audio.c` 单一 `g_pcm_buf`；`docs/B92` §命令表）。**`voice`/`sound` 不得相邻两行**——两者非阻塞（§十四.6/§十四.7），会在同一 pass 内背靠背执行，后者把前者顶掉、实际发声 <1 ms。中间至少隔一个对白页。反面教材：`nbook001.nb` 的 `voice(){hi}` 曾被紧邻的 `sound(){ding}` 瞬顶（`hi` 0.50 s / `ding` 0.40 s，PCM 单通道，devdoc 122 §三）。
2. **BGM 静音先看串口有没有 `AUD MPU OK`**（`audio.c` init 成功分支）。见到 `AUD WARN: no MPU-401` 即已定性，**不必再怀疑脚本、key 登记或 `AUDIO.DAT`**。BGM 在无 MPU 环境静音是**设计内降级**，不是 bug。
3. **BGM 不可走 PCM 循环**：单通道会被任意 SE 掐断且不自动恢复（规则 1 的推广）；且 `pcm_play()` 硬编码 `loop=0`，脚本 `sound(){<key>}` 无 flags 参数。
4. **内容与格式的对应是硬约束**：语音/音效**必须** PCM（人声波形复杂，FM 只能合成「机器人音」）；BGM 理应 FM（PC-98 原生即 FMP/PMD 用 OPM 音源出曲 + PCM 驱动出语音，见 `docs/refdocs/F01_sound_boards.md`）。当前 HAL **无任何 YM2203/YM2608 端口访问**，FM 通路不存在。
5. **不存在可用的 WAV→FM 自动转换**：FM 是参数化模型、WAV 是任意波形，反推是欠定的逆问题、无唯一解。业界方向是反向——用 tracker（如 FamiTracker，YM2612 与 PC-98 YM2608 的 FM 核心同源）按 FM 音色作曲并导出 WAV/MIDI，**使音乐资产与引擎播放通路解耦**。详见 devdoc 122 §五。
6. **`scene()` 会停所有音频**（`scene_switch()` → `audio_stop_all()`）。不要指望 BGM/语音跨场景延续，也不要在每个场景末尾堆 `bgm(stop)`（`scene()` 本就会停）。
7. **音频 key 必须登记**：脚本里每个 `bgm`/`sound`/`voice` 的花括号 key 都要有 `ASSETS.DB` 中 `type` 为 `BGM`/`SND`/`VC` 的行。`tools/naiz_build/nb_validator.py` 只校验 `IMG`/`ANI`/`CG`，**不查音频 key**——未登记的 key 能通过 `build`，只在实机表现为一行 `BGM WARN: '…' is not a registered BGM asset`。防呆：`tools/tests/test_audio_asset_paths.py::test_scene_audio_keys_are_registered`。

## 十五、Token 管理

- 对话超过 70% token 限制时需主动 compact

### 分析阶段
```
Output format: file:line — one-line description. No explanations, no code snippets.
```

### 验证阶段
```bash
make -C core && python -m py_compile tools/...file.py ...
```

## 十六、版本号管理

### 自增规则

- 版本格式 `X.Y.ZZZ`（如 `0.1.001`），ZZZ 为三位补零
- **自增时机**：每次 AI 修改 `.c` / `.h` / `.py` / `.nb` 等源代码文件后，需主动调用
  ```bash
  python -m tools.naiz_build.bump_version [game]
  ```
  一次调用即**作用于 `projects/` 下全部项目**：统一目标 = 所有项目当前版本的最大值 +1（`--minor` 则对最大值做 minor 归零），历史版本漂移在下次 bump 时自动自愈收敛到同一号（按行替换写回，保留全部 `#` 注释）。`[game]` 为可选兼容参数，仅校验该项目存在
- **手动编辑禁止**：`config.toml` 的 `version` 行由工具自动维护，禁止手动修改
- **所有项目版本同步**：`projects/` 下所有项目的版本号必须与引擎版本保持一致（`tools/tests/test_version_sync.py` 仓库不变量测试守护，fullaudit 的 pytest 步骤自动校验）；`bump_version` 一次调用即同步全部项目，无需逐个执行

### 编译带入

- `makegame.sh build <game>` 中 `build_game.py` 自动从 `config.toml` 读取 version
- `config.toml` 的 `[project] version` 经 `export_config.py` 编译成 `NAIZ_VERSION` 宏（**不再运行时解析**）
- 引擎 `settings_load()` 解析后存入 `GameSettings`，`settings_get_version()` 供主菜单右上角显示
- 此环节已就绪，无需额外修改

## 十七、Bug 防复发规则（强制）

每次修改源代码文件（`.c` / `.h` / `.py` / `.sh`）后，必须按以下清单逐一检查。任何违反规则的情况必须修复才能提交。

### Bug 排查原则

发现 bug 时，先分析其**根因**（是越界/未初始化/类型错误/逻辑遗漏等），然后主动在**其他文件/模块**中搜索是否存在同一根因的同类型 bug。修复一个实例不等于根除，同类模式可能在代码库中反复出现。

### C 代码

| # | 规则 | 检查方法 | 反例 |
|---|------|----------|------|
| C1 | `malloc`/`calloc`/`realloc` 返回值必须检查 NULL | `grep -n 'malloc\|calloc\|realloc' *.c \| grep -v 'if.*== NULL\|if.*!= NULL\|if (!'` | `mag.c:219` 早期版本未检查 `calloc` |
| C2 | `fopen` 返回值必须检查，失败日志并 return | `grep -n 'fopen(' *.c` | `nb.c` 早期版本未检查 |
| C3 | `fread`/`fwrite`/`fgets` 返回值必须检查 | 同上 | `save.c` 早期版本需验证 |
| C4 | `strncpy` 后必须手动 NUL 终止 | `grep -n 'strncpy(' *.c \| grep -v 'buf\[sizeof'` | `save.c:239-242` 之前缺少 `buf[...] = '\0'` |
| C5 | `snprintf` 代替 `sprintf` | `grep -n 'sprintf(' \| grep -v 'snprintf'` | 历史代码中使用 `sprintf` |
| C6 | 数组下标/指针运算必须先验证边界 | 对照目标缓冲区大小检查所有下标 | `mag.c:301` 有符号溢出 |
| C7 | 结构体偏移量用 `offsetof` 而非硬编码 | `grep -n '^ *int.*skip\|^ *int.*off\|fseek.*[0-9]'` | `save.c:222` 使用 `sizeof` 计算而非 `offsetof` |
| C8 | 有符号整数加法前检查溢出 | 检查所有 `+` 运算，尤其是 `int + int` | `nb_vars.c:31` 有符号溢出 UB |
| C9 | `memcpy`/`memmove` 确保目标缓冲区足够 | 验证大小参数不超过目标 | `keyboard.c` 系列 |
| C10 | `switch` 必须有 `default` 分支 | `grep -n 'switch' \| awk ...` | `nb_commands.c:93` 缺少 default |
| C11 | `assert` 禁止使用（可能被 NDEBUG 禁用） | `grep -n 'assert('` | R4 中 `scene_layers.c`(→layer.c，现 layer_dialog.c/layer_sprite.c) assert 替换 |
| C12 | 函数无返回值时（`void` 函数）不能使用返回值 | 编译器警告 | — |
| C13 | `static` 函数如未使用需移除 | `grep -n '^static' *.c`，验证是否被调用 | R3-R4 移除了 4 个死函数 |
| C14 | OOM/fail 路径需有 `hal_log` 诊断 | 检查所有 error/return 前有日志 | `scene_layers.c:175`(→layer.c/layer_dialog.c) 之前无日志 |
| C15 | 文件操作 `fclose` 确保在每条提前 return 前 | 检查所有 `fopen` 后的 return | `save.c` 已修复 |
| C16 | `offsetof` 跳转距离需验证：读取位置 + skip = 目标字段 offset | 对照 struct 布局逐字段加算偏移 | `save.c:222` R6 中 `read_hdr` 多算了 4 字节 |
| C17 | `mouse_invalidate_cursor()` 前必须确保旧光标区域将被后续绘制完全覆盖；否则先用 `mouse_erase_cursor()` 显式擦除 | 检查所有 `invalidate` → `force_draw(新位置)` 模式中旧光标区域是否被覆盖 | `nb_save_dialog.c:56` R7 残影 bug — invalidate 后对话框局部重绘未覆盖旧光标 |
| C18 | 新增 shortcut/cache 路径时，必须逐一验证原慢路径的所有**外部副作用**（硬件状态、全局变量等）是否在快速路径中保留 | 对比新旧路径的每步操作，确认所有硬件写入/全局赋值在快路径中存在 | `image.c:175-178` R8 — cache 命中跳过 `image_set_palette()` 导致白底变黑 |
| C21 | `strcpy`/`strcat`/`gets` 禁止（无界拷贝）——用 `snprintf`/`strncpy` + 显式 NUL | `grep -n 'strcpy\|strcat\|gets'` | 工具化后 AUTO 黑名单（仓库现存 0 违规） |
| C22 | 有符号局部变量取负（`-v`/`0 - v`）可能越过 INT_MIN → 用 `(v == INT_MIN) ? INT_MIN : -v` 守卫 | AUTO 规则（识别函数局部声明，含 `-arr[idx]` 下标形式，排除赋值/下标/函数调用差值） | `nb_question.c:150/185` R8 — `-opt_deltas[hit]` 为 R7 同型漏网，已修补 |
| C23 | 同路径双重 free 禁止（两次 free 之间未置 NULL 且未重新 malloc，且无 return/break/continue/goto/exit 分隔成互斥路径） | AUTO 规则（互斥错误路径模式依法豁免） | R8 新增；cjk.c/font.c/mag.c "每错误路径各 free+return" 属合法豁免 |
| C24 | `memcpy` 尺寸与被拷目标字节数组维度交叉核对（字面量/`sizeof` 拷贝 vs `char a[8]` 声明） | AUTO 规则（RE_BYTE_ARRAY_DECL 匹配 char/uint8_t/int8_t/BYTE/byte 数组字面量维度；指针目标仍由 C9 启发式兜底） | R8 新增 |
| C25 | use-after-free：free 之后到块终止符（`}`/return/break/continue/goto/exit）之间若解引用（`->`/`[`/`(`）且未重赋值即违规 | HEUR 规则 | R8 新增 |
| C26 | 所有权分离 free：`if (guard) free(x->field);` 之后同路径无条件 `free(x)`，即 guard 逃逸导致 base 在错误所有权下释放 | HEUR 规则（成员 free + 未防护 base free） | R15 新增（R13 mag_release 池 struct 逃逸） |
| C27 | 计数派生负下标：`arr[count - K]` 之前的守卫须覆盖 `count < K`（`if (argc < 1)` / `argc == 0`），缺则越界读 | HEUR 规则 | R15 新增（R13 `argv[argc-1]`） |
| C28 | 行跨距读无高度边界：函数含 `width` 类跨距乘法（如 `row * img_w`）但作用域内无任何 height 提及（参/局部/宏）→ 行索引未对图像自身高度夹逼 | HEUR 规则（只认小写 height 名，`LAYER_DIALOG_H` 等全大写宏不误判） | R15 新增（R14 cine 对话框 OOB） |
| C29 | 结构体指针仅起始越界检查：guarded `(T *)(buf + off)` 的守卫只有 `off > size`、缺 `off + sizeof(T)` 项，struct 尾部可溢出 | HEUR 规则 | R15 新增（R13/R14 mag `off_img`） |
| C32 | `strncpy()` 仅允许在 `core/lib/strutil.c` 内使用（R29 收口后），其余文件一律 `str_copy()` | AUTO 规则 | R29 后续新增（str_copy 单一事实源回归守卫） |
| C33 | 相邻 `layer_dialog_show();`+`dialog_layer_blit();` 对（`layer_dialog_clear()` 函数体内除外）→ 改用 `layer_dialog_clear()` | HEUR 规则 | R29 后续新增（干净盒惯用式回归守卫） |
| C34 | 同一文件内重复的静态数组初始化表（内容归一化完全相同，≥2 处）→ 并单一事实源 | HEUR 规则 | R29 后续新增（slot_y/slot_ys 类回归守卫） |
| C35 | 同一文件内常量算术表达式重复（≥1 操作数为宏、≥3 处）→ 建议具名宏/常量 | HEUR 规则 | R29 后续新增（LAYER_DIALOG_CONTENT_* 类回归守卫） |

### Python 代码

| # | 规则 | 检查方法 | 反例 |
|---|------|----------|------|
| P1 | `except:` 必须指定异常类型 | `grep -n 'except\s*:' \| grep -v 'except.*as\|except Exception\|except OSError'` | 禁止裸 except |
| P2 | `open()` 必须使用 `with` 语句 | `grep -n "open("` | 早期代码有裸 open |
| P3 | `assert` 替换为 `if ...: raise RuntimeError()` | `grep -n 'assert '` | `gen_cjk_font.py:149` R4 修复 |
| P4 | `struct.pack_into`/`struct.unpack_from` 需验证偏移+大小不超界 | 检查 offset + size 不超过 buffer | `fat.py:96-104` off-by-one |
| P5 | 二进制数据读取后需验证长度 | 检查 read 后数据长度是否符合预期 | R2 中 fat.py 多次修复 |
| P6 | 文件路径用 `Path` 对象而非字符串拼接 | — | `build_game.py:26` 硬编码路径 |
| P7 | `subprocess.Popen`/`run` 优先用 list 形式，避免 `shell=True` | `grep -n 'shell=True\|sh -c'` | `env_build.py` f-string 注入修复 |
| P8 | 避免在函数体内 import（延迟 import 需在顶部） | 检查 import 语句位置 | `inject_common.py:294` 不在顶部的 import |
| P9 | 可变默认参数禁止（`def f(x=[])`） | `grep -n 'def.*=\[\]\|def.*={}'` | — |
| P10 | `sys.exit(string)` 需改为 `print(...); sys.exit(1)` | `grep -n 'sys.exit(' \| grep -v 'sys.exit(0)\|sys.exit(1)'` | `mag_convert.py:500` |
| P11 | 可变状态（如 `next_free`）跨函数传递时需返回更新值或用可变容器 | 检查所有 int/str 按值传递后在调用者是否被更新 | `fat_table.py:38` `alloc_next_free` 必须返回更新游标（R6 曾修复 `make_base_clean.py` 中 `next_free` 未传播的同类 bug） |
| P14 | 禁止 `eval`/`exec`/`os.system`/`os.popen`（动态代码/子 shell 转义）；`subprocess.Popen` 用 list argv 属合法 | `grep -n 'eval(\|exec(\|os.system(\|os.popen('`（排除 venv） | 工具化后 AUTO 黑名单（仓库现存 0 违规） |

### Shell 脚本

| # | 规则 | 检查方法 | 反例 |
|---|------|----------|------|
| S1 | 变量扩展全部用 `"$var"` 引用 | `grep -n '\$' *.sh \| grep -v '"\$'` | `makegame.sh:87` 未引用的 `$SERIAL` |
| S2 | 禁止 `eval` | `grep -n 'eval '` | `detect_watcom.sh:16` R5 修复 |
| S3 | 用 `command -v` 替代 `which` | `grep -n '\bwhich\b'` | `makegame.sh:33` R5 修复 |
| S4 | 用 `$(cd "$(dirname "$0")" && pwd)` 替代 `readlink -f` | `grep -n 'readlink'` | `build.sh:3` R5 修复 |
| S5 | `shift` 前确保 `$# > 0` | 检查 shift 场景 | `makegame.sh:50` 脆弱的 shift |
| S6 | 循环多字符变量时用数组而非未引用字符串 | 检查 for 循环中的未引用变量 | `detect_watcom.sh:15` R5 修复 |
| S7 | 可选 flag 用数组条件追加，避免空串位置参数 | `grep -n '"[^"]*\$[A-Z][^"]*"' *.sh \| grep -v '\[\[ \|if \|echo'` | `makegame.sh:87` R6 中 `$SERIAL` 空串被 argparse 拒绝 |

### 提交前自检命令

```bash
# C 编译
# 注意：wcl386 把诊断写进 core/<unit>.err，make 的 stdout 只有命令行。
# 0.3.014 教训：`make -C core 2>&1 | grep -E 'Error|Warning'` 在一个刚
# 报出 W131 的构建上照样输出 0 —— 假通过，且恰好伪造了本项要证明的东西。
# 实测漏网：`nb_mainmenu.c(113) W131: No prototype found for 'bootmenu_run'`。
make -C core && find core -maxdepth 1 -name '*.err' -size +0   # 应无输出

# Python 语法
for f in $(find tools -name '*.py'); do python -m py_compile "$f" 2>&1 | grep -v 'OK'; done

# Shell 检查
shellcheck core/*.sh makegame.sh start.sh 2>&1 | grep -v 'SC'
```

### 已弃用但保留的代码

以下代码为**有意保留**的废弃代码（B5 拆分时归档 + 全项目死文件审计时确认，非遗漏）。日后代码审查中 **C13/P11 等"未使用需移除"规则不适用于它们，无需再检查是否删除**：

| 位置 | 说明 |
|------|------|
| `tools/env_setup/env_np2kai.py::cmd_build_i286` | 废弃的 i286 核心编译命令（仅 16-bit 保护模式，无法运行 32-bit DOS/4GW 引擎）。无 start.sh 入口，install_env.py 仍保留该 CLI 子命令以兼容历史用法 |
| `tools/env_setup/env_toolchains.py::_install_gcc_ia16_deepin` | 无调用。deepin 发行版专用 gcc-ia16 安装路径，暂不维护 |
| `core/plat/vram.c` | 被 `core/Makefile` `filter-out` 排除、`vram_init()`/`vram_plane()` 无任何调用方。pc98.h 注明是有意保留的 opt-in 参考实现（`VRAM_DPMI_MAP` 映射方案），供未来 DPMI VRAM 直写实验参考。删除需经用户确认 |
| `tools/naiz_screendig/`（6 文件） | 独立手工截图诊断工具（`python -m tools.naiz_screendig`），无自动化入口，仅 docs 引用；功能与 `naiz_lib/np2kai_capture` 重叠但被 docs 列为 P0 截图工具，保留 |
| `tools/diag/read_fat16.py` | FAT16 手工诊断工具（复用 `naiz_img`），仅 `docs/B90` 索引，无脚本调用；手工排查基座 HDI 时使用，保留 |
