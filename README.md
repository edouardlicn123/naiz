<p align="center"><img src="assets/logomini.png" alt="Naiz" width="520"></p>

# Naiz — PC-98 Visual Novel Engine

**English** | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

> **Naiz** (ナイズ) — a visual novel engine for PC-98 (NEC PC-9801/9821), powered by the plain-text NB (Naiz Book) scripting format.

---

## Overview

Naiz is a visual novel (ADV) authoring suite for PC-98: scripts and configuration are plain text you can edit directly, and assets are ordinary image and audio files. Built as a **32-bit protected-mode** program, it runs on real PC-9801/9821 hardware or in the NP2kai emulator.

Highlights:

- **32-bit protected mode** — runs under DOS/4GW in PC-98 protected mode, free from the 640 KB real-mode memory limit and the 64 KB segment limit; long scripts and large asset sets no longer require careful budgeting
- **Naiz Queue unified execution model** — an ISR-owned independent clock + producer–consumer queue + frame pump decouple BGM, animation, sprites, transitions, and typewriter effects into independent transactions; the next scene's resources are preloaded automatically during transitions, eliminating synchronous blocking and burst drains, so long stalls do not disturb the clock cadence
- **Plain-text scripts** — write the story in `.nb` files: change a line, rerun the build, and see the result; no dedicated editor required
- **Mouse and keyboard** — both input methods are available at the same time
- **Multi-language releases** — write once and ship in 10 languages (English, Simplified Chinese, Traditional Chinese, Japanese, Korean, French, German, Italian, Spanish, Portuguese), selected by the player in the boot menu
- **Out-of-the-box toolchain** — dedicated scripts for environment setup, building and packaging, emulator testing, animation authoring, and asset downloads

---

## Quick Start

Set up the environment first (Python venv, NP2kai, Open Watcom toolchain):

```bash
./start.sh          # interactive setup menu
./start.sh check    # environment check only
```

The first run creates a shared Python virtual environment at `~/venv`; a sibling `naiz-studio` directory reuses the same venv instead of creating another one.

Build and run the demo project:

```bash
./makegame.sh build demo-a2            # assets → MAG → IMAGE.DAT → compile engine → deploy DOS tree
./makegame.sh make  demo-a2            # package disks/demo-a2.hdi
./makegame.sh test  demo-a2 --serial   # launch NP2kai with serial log output
```

`build` only deploys to `games/<game>/`, while `make` injects the deployment tree into the HDI. The emulator boots the HDI, so run both after changing the engine.

---

## Toolchain

| Entry point | Purpose |
|---|---|
| `start.sh` | Environment setup (check / pip / deps / np2kai / retroarch / watcom / djgpp / mirror), `audit` symbol-encapsulation audit, `fullaudit` whole-project rule audit |
| `makegame.sh` | `build` compiles a project, `make` packages the HDI, `makegame` does both, `test [--serial]` launches the emulator, `audio` adjusts emulator audio latency |
| `anima.sh` | `.na` animation scripts → `.ANI` containers (init / register / check / mp4 / build / buildall / list) |
| `market.sh` | Whole-package asset downloads from the public asset market (list / get / get-all / sync / menu) |
| `~/naiz-studio` | Web-based NB script IDE (separate repository, must be a sibling of this repository; launch via `./studio.sh`) |
| `tools/` | Python toolchain: `naiz_img` image injection, `naiz_build` data packing and validation, `naiz_conv` format conversion and i18n, `naiz_audio` audio, `diag` diagnostics, `env_setup` environment installation |

See `docs/B90-参考-函数索引.md` for the package-level index.

---

## Derived Projects

| Project | Repository | Description |
|---|---|---|
| Naiz Script Studio | https://github.com/edouardlicn123/naiz-studio | Web-based NB script IDE; must be a sibling of this repository and shares `~/venv`; launch via `./studio.sh` |
| naiz-openpack | https://github.com/edouardlicn123/naiz-openpack | Open-source build asset pack (FreeDOS(98) chain + open-source base HDI); `./start.sh openpack` downloads and extracts it to `tools_open/` |
| naiz_cmpack | https://github.com/edouardlicn123/naiz_cmpack | Commercial build asset pack (MS-DOS 5 + PC-9821 BIOS); `./start.sh commercial` downloads and extracts it to `tools_commercial/` |
| naiz_assets | https://github.com/edouardlicn123/naiz_assets | Public asset market repository; `./market.sh` downloads assets by package into `assets_samples/` |

---

## References

- [MHVNVisualNovelEngine](https://github.com/maxotaku11niku/MHVNVisualNovelEngine) — MIT, scene-format reference
- [98Bridge](https://github.com/NullMagic2/98Bridge) — MIT, HDI injection design reference
- [ADV98](https://github.com/yarufu/pc98) — MIT, PC-98 ADV engine; reference for game-side PMD integration and BGM lifecycle
- [ADVS98](https://alammofm.com/advs98/) (Adventure System 98) — source not public; in-browser editor + `p98c` compiler + built-in emulator (WASM, works offline) for PC-98 visual novels and command-driven ADV; reference for its web-based visual editing experience (script on the left, live machine screen on the right)
- [98fmplayer](https://github.com/myon98/98fmplayer) — BSD-2-Clause, reference for PMD/FMP drivers and OPN register implementation
- [NP2kai](https://github.com/AZO234/NP2kai) — MIT, emulator host and fmgen FM core (hardware oracle)
- [ymfm](https://github.com/aaronsgiles/ymfm) — BSD-3-Clause, Yamaha FM emulation core (offline timbre oracle, vendored under `tools/vendor/ymfm`)

License: MIT — see `LICENSE`.
