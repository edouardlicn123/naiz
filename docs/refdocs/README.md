# PC-98 参考知识文档

Naiz 引擎项目整理的外部 PC-98 知识参考资料。

## 文档列表（分类索引）

### A — 系统架构 (System Architecture)

| 文件 | 内容 |
|------|------|
| `A01_architecture.md` | PC-98 硬件架构总览：GDC/GRCG/EGC/PEGC 世代、机型兼容性 |

### B — 内存与 I/O (Memory & I/O)

| 文件 | 内容 |
|------|------|
| `B01_memory_map.md` | 系统内存映射：VRAM 布局、BIOS 数据区、扩展卡地址、中断向量表 |
| `B02_io_ports.md` | I/O 端口参考：按功能分类的端口地址速查，含扩展端口 |
| `B03_memory_switches.md` | Memory Switches 配置：SW1–SW6 所有位定义、地址、默认值 |

### C — 显示系统 (Display)

| 文件 | 内容 |
|------|------|
| `C01_display_system.md` | **最关键**：GDC 命令、VRAM 4 平面、GRCG/EGC 编程、调色板、CRTC、硬件演进史、PEGC 256 色 |

### D — 输入设备 (Input)

| 文件 | 内容 |
|------|------|
| `D01_keyboard.md` | 键盘 8251A 接口：make/break 码、命令协议、引脚、流程图、布局 |
| `D02_kanji_display.md` | PC-9800 汉字显示：JIS 编码、Shift-JIS 转换、文字 VRAM 写入 |

### E — 存储与引导 (Storage & Boot)

| 文件 | 内容 |
|------|------|
| `E01_boot_disk.md` | IPL/引导：引导记录格式、启动流程、HDI 兼容性、启动快捷键、DIP 设置 |

### F — 声音 (Audio)

| 文件 | 内容 |
|------|------|
| `F01_sound_boards.md` | PC-9801-26K (OPN) + PC-9801-86 (OPNA) 声卡：跳线、DIP、兼容性 |
| `F02_86pcm_registers.md` | 86 板 PCM(86PCM)寄存器级参考：A460/A466/A468/A46A/A46C/A66E 位域、A46A 双用途陷阱、本项目现状对照与未确认项 |
| `F03_opna_fm_and_bgm_routes.md` | **选型决策 + FM 通路调研**：BGM 四条通路（PCM/MIDI/FM/PMD）在实机与 NP2kai 的对照与建议；OPNA 寄存器参考（bank 选择/逐算子/逐通道/SSG/RHYTHM/ADPCM/OPNA mask）；MML 记谱法子集（**备选参考，非本项目输入格式**——已定输入为 MIDI）；4-op 音色格式与许可结论；陷阱清单与 10 条未确认项 |
| `F04_opna_timer_a_b_specs.md` | **Timer A/B 硬件规格**（F03 未收段）：`$24-$27`/`$29`(SCH+IRQ ENABLE)/`$2D-$2F` 预分频；tA/tB 公式（9µs/144µs@8MHz）；PC-98 端口 0x188-0x18E 与 FM timer→IRQ3 事实；devdoc 131 方案 C 的硬件基础；含 $29 默认位行为待核实项 |
| `F05_pmd_driver_architecture.md` | **PMD 常驻驱动架构与 Timer-B 节拍模型**：GAME.BAT 预加载 + AH 功能号 API（ReC98 实证）、`#Timer`/`#Tempo`/`#Zenlen` 语义与 TimerB 公式、`.M` 序列二进制格式；解释「原版游戏为什么不颤」——音乐节拍由 Timer-B 中断驱动，与主循环解耦 |
| `F06_pmd_mml_manual_en.md` | PMD 4.8 MML Command Manual 英译**全文落盘**（原著 M.Kajihara，英译 Blaze and Pigu）：通道-音源对应表/@ 乐器定义/全部 MML 命令参考。**注意 PMD 是驱动输入语言，本项目 BGM 输入已定 MIDI**，本文作音乐生态参考 |
| `F07_opn_timer_clock_reference.md` | **OPN Timer 计时口径定论（2304 clk vs 手册 1152）**：手册 2× 之谜（φM/2 计数）+ ymfm / Nuked-OPN2 / BlastEm / NP2kai 四实现逐行对照 + PMD `10800000` / MUCOM88 `t198` 软件侧反证 + 86 板与 PC-8801 同为 7.9872 MHz ⇒ NB=200 真机 16.154 ms vs NP2kai 16.128 ms（−0.16%）+ 工程取值 **258 units**（旧值 129 是半个周期）+ 未确认项 |

### G — 编程参考 (Programming Reference)

| 文件 | 内容 |
|------|------|
| `G01_pc98dos_hwprogramming.md` | PC98 DOS ハードウェアバリバリ編：DOS 功能/中断/键盘/EMS/XMS/图形(GDC/GRCG/EGC/256)/声音 |
| `G02_quickguide_hardware.md` | NEC PC-9800 Quick Guide Hardware：硬件世代比较、I/O 移植 |
| `G03_at_vs_98_diff.md` | AT → PC-98 移植差异：BIOS/硬件/内存/显示/键盘 对照表 |
| `G04_98_tewaza.md` | いまさらPC-9801小手先技巧講座：GDC/GRCG/EGC/VSYNC/I/O 汇编技巧 |
| `G05_fuga_rpg_tips.md` | FUGA System Game Station：RPG 高速图形、EGC BitBLT、滚动 |
| `G06_bauxite_wiki.md` | bauxite PC-98x1 技术 wiki：开发环境、调试、排错、优化 |
| `G07_djgpp_pc98_toolchain.md` | DJGPP on PC-98/NP2kai 技术分析：保护模式链路 (VCPI)、NP2kai 兼容性验证、Open Watcom vs DJGPP 对比 |
| `G08_dos4gw_interrupt_and_pit.md` | **DOS/4GW 挂中断与 PIT 改频**：`_go32_dpmi_*`/`__dpmi_*` DPMI API、锁内存硬约束、bi-modal handler（Watcom §5.8）、expiredpopsicle PIT 改频模板（除数/mode/累计 18.2Hz/EOI）、INT 1Ch 软挂点局限；devdoc 131 方案 C 的软件侧前置 |
| `G09_timing_vsync_audio_engineering.md` | **时钟源候选谱 + PC-98 vsync 中断 + 流式音频工程证据**：XtoF 定时技术全谱（对照 B19 已淘汰项）、ReactOS/DOSBox-X 的 0x64→IRQ2、DOSBox-X #342 级联 IRQ ACK 全记录（FM=IRQ12/鼠标=IRQ13/电平触发）、Scali latched-timer 事件线、DCEmulation 分片解码（尖峰 60%→25%）、Defold 预载隐藏、MIDAS 屏幕同步三回调 |

### H — PDF 摘要 (PDF Summaries)

| 文件 | 内容 |
|------|------|
| `H01_pdf_bible.md` | 『98を98%使う本』摘要 + 本地 PDF (`pc98_bible.pdf`, 19MB) |
| `H02_pdf_bios_techdata.md` | Technical Data Book BIOS 篇摘要 + 本地 PDF (`pc98_bios.pdf`, 73MB) |
| `H03_pdf_hw_techdata.md` | Technical Data Book Hardware 篇摘要 + 本地 PDF (`pc98_hw.pdf`, 35MB) |

### I — DOS 基座 (DOS Base)

| 文件 | 内容 |
|------|------|
| `I01_freedos98_base_sources.md` | **FreeDOS(98) 基座生态拆解**：kernel INT 陷阱机制源码级定案（0x40-0xFE 全陷阱 + 4C7F 终止 + 转储顺序修正）；官方源码/镜像落盘清单（`/media/edo/data/studysource/`，KWC8616.sys 与盘上 KERNEL.SYS 逐字节相同）；文档原文在 `raw/`（nec98int/sys_fd98/emm386 README/bauxite 页快照）；对 step2 的帮助评估与两条 kernel 级修复路线 |

## 来源索引

| 来源 | URL | 类型 |
|------|-----|------|
| pc98.ne.jp DevDocs | https://pc98.ne.jp/devdocs/ | 入口页 |
| radioc.web.fc2.com | http://radioc.web.fc2.com/column/pc98bas/index_en.htm | HTML 文档 |
| printf.neocities.org | https://printf.neocities.org/programming | 编程参考索引 |
| UNDOCUMENTED 9801/9821 Vol.2 | https://www.webtech.co.jp/company/doc/undocumented_mem/index.html | I/O + 内存文本文件 |
| PC-9800 Technical Data Book (BIOS) | `pc98_bios.pdf`（来自 https://pc98.ne.jp/devdocs/） | PDF ✓ 本地缓存 |
| PC-9800 Technical Data Book (Hardware) | `pc98_hw.pdf`（来自 https://pc98.ne.jp/devdocs/） | PDF ✓ 本地缓存 |
| PC-9801 Programmer's Bible | `pc98_bible.pdf`（来自 https://pc98.ne.jp/devdocs/） | PDF ✓ 本地缓存 |
| UNDOCUMENTED 9801/9821 Vol.1 | https://archive.org/details/undoc98vol1floppy | 存档页 |
| MASTER.LIB | http://www.koizuka.jp/~koizuka/master.lib/ | 库 + 手册 |
| μPD7220 Datasheet | http://www.vintagecomputer.net/fjkraan/comp/qx10/doc/nec7220.pdf | PDF |
| MPC PC98 DOS Programming | https://web.archive.org/web/20000709114152/http://www2.muroran-it.ac.jp/circle/mpc/pc98dos/ | 教程（全5部分）|
| なむら漢字表示 | https://printf.neocities.org/pc98/99_kanji.html | HTML 文档 |
| Quick Guide Hardware | https://web.archive.org/web/20210413232841/https://www.retropc.net/mm/pc88/98quick/index.html | HTML 文档 |
| 吉崎 PC-9801 技巧 | https://web.archive.org/web/19990224092301/http://www.asahi-net.or.jp/~FZ6Y-YMTR/ | 汇编技巧 |
| FUGA RPG 开发 | https://web.archive.org/web/20021206125421/http://www.asahi-net.or.jp/~KC2H-MGR/rpg/source/ | RPG 编程资料 |
| Yamaha YM2608 OPNA Application Manual(英译) | http://nemesis.hacking-cult.org/MegaDrive/Documentation/YM2608J%20Translated.PDF（原站 404；可用镜像 https://csclub.uwaterloo.ca/~pbarfuss/YM2608J_Translated.PDF ） | PDF |
| ymfm(YM FM 模拟核,MAME 所用) | https://github.com/aaronsgiles/ymfm | 源码(BSD-3-Clause) |
| FMP 官方文档 | http://fmpdoc.fmp.jp/ | HTML 文档 |
| PMD MML 手册英译(PMD 4.8) | https://pigu-a.github.io/pmddocs/pmdmml.htm | HTML 文档(全文落盘于 F06) |
| ValleyBell pmd_SeqFormat(.M 二进制格式) | https://raw.githubusercontent.com/ValleyBell/MidiConverters/master/pmd_SeqFormat.txt | 文本(格式说明) |
| ReC98 博客:TH04 PMD 加载(常驻驱动 API) | https://rec98.nmlgc.net/blog/2021-05-12 | 博客 |
| QEMU pc98 OPNA 设备(awemorris fork) | https://github.com/awemorris/qemu-pc98 | 源码(GPL-2.0,仅取事实) |
| mml-guide PMD 篇 | https://mml-guide.readthedocs.io/pmd/ | HTML 文档 |
| Battle of the Bits PMD Effects | https://battleofthebits.org/lyceum/View/Professional%20Music%20Driver%20Effects%20Commands | HTML 文档 |
| bauxite wiki | https://bauxite.sakura.ne.jp/ | 技术 Wiki |
| YM2203 寄存器(FM音源編,滴了庵日録) | https://lipoyang.hatenablog.com/entry/20131112/p1 | 博客(日文) |
| ManualMachine:YM2608 User Manual(网页版) | https://manualmachine.com/yamaha/ym2608/5410883-user-manual/ | HTML 文档 |
| DJGPP v2 FAQ 18.9(硬件中断挂接) | https://www.delorie.com/djgpp/v2faq/faq18_9.html | HTML 文档 |
| Open Watcom C/C++ Programmer's Guide 1.9(§5.8 bi-modal) | https://open-watcom.github.io/open-watcom-1.9/pguide.html | HTML 文档 |
| expiredpopsicle《DOS Timer Stuff》 | https://expiredpopsicle.com/articles/2017-04-13-DOS_Timer_Stuff/2017-04-13-DOS_Timer_Stuff.html | HTML 文档 |
| XtoF*Timing on the PC family under DOS* | https://www.xtof.info/Timing-on-PC-familly-under-DOS.html | HTML 文档(Freeware) |
| Scali's OpenBlog(VGM latched timer / VBI myth) | https://scalibq.wordpress.com/2017/02/24/putting-the-things-together/ ; https://scalibq.wordpress.com/2022/12/06/the-myth-of-the-vertical-retrace-interrupt/ | 博客 |
| ReactOS pc98 video.h(doxygen) | https://doxygen.reactos.org/d6/d70/sdk_2include_2reactos_2drivers_2pc98_2video_8h.html | 源码引用 |
| DOSBox-X issue #342(PC-98 级联 IRQ ACK 实录) | https://github.com/joncampbell123/dosbox-x/issues/342 | issue |
| DCEmulation《Streaming Music Playback CPU Usage》 | https://dcemulation.org/phpBB/viewtopic.php?t=105823 | 论坛 |
| Defold 论坛(加载 stutter 两帖) | https://forum.defold.com/t/sound-stutter-while-loading-a-collection-factory-solved/14271 ; https://forum.defold.com/t/sound-stops-while-loading-collection-proxy-solved/3565 | 论坛 |
| MIDAS Sound System prgguide §5.1(屏幕同步定时器) | https://files.mpoli.fi/pub/unpacked/skene/music/mutils/midas061.zip/doc/html/prgguide/node21.html | HTML 文档 |
| lpproj/fdkernel(FreeDOS(98) kernel 源码+镜像, I01 主源) | https://github.com/lpproj/fdkernel/tree/nec98test ; release: https://github.com/lpproj/fdkernel/releases/tag/test-20220120-cherrypick | GitHub 源码 |
| lpproj/freecom_dbcs2(FreeCom DBCS) | https://github.com/lpproj/freecom_dbcs2/ | GitHub 源码 |
| lpproj/emm386.nec(EMM386 98 版) | https://github.com/lpproj/emm386.nec | GitHub 源码 |
| lpproj/himemx.nec(HimemX 98 版) | https://github.com/lpproj/himemx.nec/ | GitHub 源码 |
| bauxite.sakura.ne.jp FreeDOS 方面(lpproj 配布页, raw/ 快照) | http://bauxite.sakura.ne.jp/software/dos/freedos.htm | HTML 文档 |
| tori FreeDOS(98) 原版 | http://www.retropc.net/tori/freedos/ | HTML 文档 |
| Wikibooks NEC PC Programmers Reference: Sound BIOS | https://en.wikibooks.org/wiki/NEC_PC_Programmers_Reference/Sound_BIOS | ⚠ **未获取**(网络不可达;G08 列为待核实) |

## 使用说明

- 这些文档是 PC-98 开发的知识参考，而非 Naiz 引擎的规格文档
- 引擎架构决策和实现笔记请参见 `devdocs/` 和 `docs/`
- 本地缓存的 PDF 可直接在 `docs/refdocs/` 中阅读
- 后续从外部获取的参考材料（PDF、文档、链接等）统一放在 `docs/refdocs/` 下，保持组织一致
