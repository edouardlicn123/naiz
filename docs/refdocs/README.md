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

### H — PDF 摘要 (PDF Summaries)

| 文件 | 内容 |
|------|------|
| `H01_pdf_bible.md` | 『98を98%使う本』摘要 + 本地 PDF (`pc98_bible.pdf`, 19MB) |
| `H02_pdf_bios_techdata.md` | Technical Data Book BIOS 篇摘要 + 本地 PDF (`pc98_bios.pdf`, 73MB) |
| `H03_pdf_hw_techdata.md` | Technical Data Book Hardware 篇摘要 + 本地 PDF (`pc98_hw.pdf`, 35MB) |

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
| bauxite wiki | https://bauxite.sakura.ne.jp/ | 技术 Wiki |

## 使用说明

- 这些文档是 PC-98 开发的知识参考，而非 Naiz 引擎的规格文档
- 引擎架构决策和实现笔记请参见 `devdocs/` 和 `docs/`
- 本地缓存的 PDF 可直接在 `docs/refdocs/` 中阅读
- 后续从外部获取的参考材料（PDF、文档、链接等）统一放在 `docs/refdocs/` 下，保持组织一致
