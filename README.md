# Naiz — PC-98 Galgame Engine

> **なにいえ** — 一个基于多个开源参考项目构建的 PC-98（NEC PC-9801/9821）电子小说引擎。  
> A PC-98 visual novel / galgame engine built from scratch, drawing inspiration from multiple open-source reference projects.

---

## Overview | 概述

This project builds a **PC-98 real-mode galgame engine** targeting the NEC PC-9801/9821 series (IA32, gcc-ia16). The engine source lives in `core/`, auxiliary Python toolchain in `tools/`, and game projects in `projects/`.

The **reference projects** in `ref_projects/` are read-only git submodules — studied for design ideas but never directly linked or `#include`d. Any code copied from them into `core/` or `tools/` must carry an attribution header (see `AGENTS.md`).

本项目从零构建一个 PC-98 实模式 Galgame 引擎。`ref_projects/` 是只读参考子模块，可借鉴学习，但不得直接链接引用。

---

## Directory Layout | 目录结构

```
Naiz/
├── core/                    # Engine source (C, gcc-ia16)
│   ├── engine/              #   Cross-platform core logic (log, lz4, main)
│   ├── plat/                #   HAL — Platform Abstraction Layer
│   │   ├── pc98/            #     PC-98 backend (EGC/GRCG/GDC/file I/O)
│   │   └── sdl2/            #     Future SDL2 backend
│   ├── crt0.s               #   Assembly entry (_start: BSS zero, stack init, call main)
│   ├── msdos.ld             #   Custom linker script
│   └── build/               #   Build output
├── tools/                   # Python toolchain
│   ├── naiz_img/            #   HDI/FAT toolchain (inject.py, hdi.py, fat.py, ...)
│   ├── ref_config/          #   CONFIG.SYS
│   ├── env_setup/           #   NP2kai build / test scripts (install_env.py)
│   └── base_msdos5_scsi_48m.hdi           #   Base HDI image (read-only)
├── projects/                # Game project containers
│   └── demo-A1/             #   Demo project (main.c, Makefile)
├── games/                   # Deployable game files
│   └── demo-A1/             #   Compiled engine.exe (linked from core/ + projects/)
├── disks/                   # Generated HDI disk images
├── docs/                    # Specifications (A01-A04)
├── devdocs/                 # Development notes (numbered 01-20, MHVN98/)
├── AGENTS.md                # AI agent rules & attribution policy
├── make_hdi.sh              # （已删除，由 makegame.sh 替代）
├── makegame.sh              # Game build/test workflow (make/test/build)
├── setup_env.sh             # 开发环境安装菜单
└── start.sh                 # Launcher menu
```

---

## Reference Projects | 参考项目

Each project in `ref_projects/` has its own `README.md` with name, URL, and license. Below is a summary:

| Project | Repository | License | Purpose |
|---------|-----------|---------|---------|
| **MHVN98** | [maxotaku11niku/MHVNVisualNovelEngine](https://github.com/maxotaku11niku/MHVNVisualNovelEngine) | MIT | Core VN engine reference (VM, text, palette, GPI, LZ4) |
| **master.lib** | [koizuka/master.lib](https://github.com/koizuka/master.lib) | Source available | PC-98 hardware library (EGC/GRCG/BEEP/input) |
| **ReC98** | [nmlgc/ReC98](https://github.com/nmlgc/ReC98) | — | Touhou PC-98 reverse engineering, code structure |
| **pmdmini** | [mistydemeo/pmdmini](https://github.com/mistydemeo/pmdmini) | GPL v2 | PMD/MDX music playback (SDL2 backend audio) |
| **xsystem35-sdl2** | [kichikuou/xsystem35-sdl2](https://github.com/kichikuou/xsystem35-sdl2) | GPL v2 | AliceSoft System 3.x SDL2 port |
| **xsys35c** | [kichikuou/xsys35c](https://github.com/kichikuou/xsys35c) | GPL v2 | System 3.x script compiler reference |
| **np21w** | [SimK98/np21w](https://github.com/SimK98/np21w) | Modified BSD | Neko Project 21/W emulator — hardware model differences |
| **98fmplayer** | [myon98/98fmplayer](https://github.com/myon98/98fmplayer) | BSD 2-Clause | OPNA/OPN3 FM player — native audio programming |
| **98imgtools** | [tsdko/98imgtools](https://github.com/tsdko/98imgtools) | Unlicense | Disk image tools (HDI/NHD/HDD/SLH) for distribution |
| **djlsr** | [PC-98/djlsr](https://github.com/PC-98/djlsr) | GPL v2 / LGPL 2.1 | DJGPP libc PC-98 patches |
| **gdc_test** | [tyama501/gdc_test](https://github.com/tyama501/gdc_test) | — | GDC hardware test code |
| **ps2busmouse98** | [tyama501/ps2busmouse98](https://github.com/tyama501/ps2busmouse98) | MIT | PS/2 → PC-98 bus mouse driver |

See `AGENTS.md` for the attribution policy when using code from these projects.  
关于引用参考项目代码时的版权注释要求，详见 `AGENTS.md`。

---

## Build Requirements | 构建需求

- **Engine (PC-98 real mode):** [gcc-ia16](https://github.com/tkchia/gcc-ia16) (IA-16, 16-bit real-mode), ia16-elf-as, Make
- **Toolchain:** Python 3.x
- **Emulator (testing):** [NP2kai](https://domisan.sakura.ne.jp/article/np2kai/np2kai.html) — IA32 core (`wxnp21kai`)
- **Base HDI:** MS-DOS 5.0 (`tools/base_msdos5_scsi_48m.hdi`, read-only)

---

## Development Flow | 开发流程

```
Source → engine.exe → HDI → NP2kai boot → test
┌─────────────┐    ┌─────────────┐    ┌──────────┐
│ core/       │    │ inject.py   │    │ NP2kai   │
│ projects/   │───→│ ref_config/ │───→│ IPL →    │
│ gcc-ia16    │    │ (CONFIG.SYS)│    │ MS-DOS → │
│ crt0.s      │    │ base_msdos5_scsi_48m.hdi  │    │ ENGINE   │
│ msdos.ld    │    │             │    │          │
└─────────────┘    └─────────────┘    └──────────┘
```

## Quick Start | 快速开始

```bash
# Build engine, inject into HDI, test in NP2kai
cd projects/demo-A1 && make        # compile engine
./makegame.sh make demo-A1         # inject HDI
./makegame.sh test demo-A1         # boot in NP2kai
```

See `docs/A04-HDI制作方案.md` for HDI details and `docs/A03-引擎开发与调试全流程.md` for full dev cycle.

---

## Roadmap | 开发路线

| Phase | Focus | Status |
|-------|-------|--------|
| 1 | Core basics (HAL, graphics, LZ4, entry/stack, HDI pipeline) | ✅ Done |
| 2 | Engine runtime (VM, text, palette, GPI, scene flow) | 🔄 In progress |
| 3 | Audio (BEEP, PMD.COM interface) | 📋 Planned |
| 4 | Python toolchain (script compiler, img converter, archive builder) | 📋 Planned |
| 5 | Cross-platform SDL2 backend | 📋 Planned |
See `devdocs/01-项目计划.md` for the full plan (Chinese).

---

## License | 许可证

The engine code in `core/` and tools in `tools/` are written from scratch — their license is TBD (to be determined).

Reference projects in `ref_projects/` are subject to their respective licenses. See each project's `README.md` for details.

本项目引擎代码为全新书写，许可证待定。参考项目遵守各自许可证，详见其 `README.md`。
