<p align="center"><img src="assets/logomini.png" alt="Naiz" width="520"></p>

# Naiz — PC-98 Visual Novel Engine

> **ナイズ** — 基于 PC-98（NEC PC-9801/9821）的电子小说引擎，使用 NB 纯文本剧本格式。
> A PC-98 visual novel engine with NB (Naiz Book) text-based scripting.

---

## Overview

Naiz 是面向 PC-98 的视觉小说（ADV）制作套件：剧本与配置都是可直接编辑的纯文本，素材就是普通的图片与音频文件，构建后以 **32-bit 保护模式**程序的形式，在真机 PC-9801/9821 或 NP2kai 模拟器上运行。

核心特色：

- **32 位保护模式** — 用 DOS/4GW 运行在 PC-98 的保护模式下，摆脱实模式 640 KB 内存与 64 KB 段上限，长剧本与大批素材不必再精打细算
- **纯文本剧本** — `.nb` 文件里写剧情，改一行、重跑一次构建就能看到效果，无需专用编辑器
- **多语言发行** — 一次编写，可同时发行 10 种语言（英语、简中、繁中、日、韩、法、德、意、西、葡），玩家在开机菜单自选
- **鼠标与键盘** — 两种操作方式同时可用
- **开箱即用的工具链** — 环境配置、构建打包、模拟器测试、动画制作、素材下载均有独立脚本

---

## 快速开始

首次使用先配置环境（Python venv、NP2kai、Open Watcom 工具链）：

```bash
./start.sh          # 交互式配置菜单
./start.sh check    # 仅环境检测
```

构建并运行演示项目：

```bash
./makegame.sh build demo-a2            # 素材 → MAG → IMAGE.DAT → 编译引擎 → 部署 DOS 树
./makegame.sh make  demo-a2            # 打包 disks/demo-a2.hdi
./makegame.sh test  demo-a2 --serial   # NP2kai 启动，串口日志输出
```

`build` 只部署到 `games/<game>/`，`make` 才把部署树注入 HDI；模拟器启动的是 HDI，因此改引擎后两者都要跑。

---

## 工具链

| 入口 | 作用 |
|---|---|
| `start.sh` | 环境配置（check / pip / deps / np2kai / retroarch / watcom / djgpp / mirror）、`audit` 符号封装审计、`fullaudit` 全项目规则审计 |
| `makegame.sh` | `build` 编译项目、`make` 打包 HDI、`makegame` 二合一、`test [--serial]` 启动模拟器、`audio` 设置模拟器音频延迟 |
| `anima.sh` | `.na` 动画脚本 → `.ANI` 容器（init / register / check / mp4 / build / buildall / list） |
| `market.sh` | 从公开市场仓库整包下载素材（list / get / get-all / sync / menu） |
| `tools/` | Python 工具链：`naiz_img` 镜像注入、`naiz_build` 数据打包与校验、`naiz_conv` 格式转换与 i18n、`naiz_audio` 音频、`diag` 诊断、`env_setup` 环境安装 |

包级索引见 `docs/B90-参考-函数索引.md`。

---

## Reference Projects

- [MHVNVisualNovelEngine](https://github.com/maxotaku11niku/MHVNVisualNovelEngine) — MIT, 场景格式参考
- [98Bridge](https://github.com/NullMagic2/98Bridge) — MIT, HDI 注入设计参考
- [ADV98](https://github.com/yarufu/pc98) — MIT, PC-98 ADV 引擎；游戏侧 PMD 集成与 BGM 生命周期参考
- [ADVS98](https://alammofm.com/advs98/) — 闭源（无公开仓库）, PC-98 视觉小说网页编辑器（浏览器内编译与模拟器）；`studio/` 剧本工坊的界面设计参考
- [98fmplayer](https://github.com/myon98/98fmplayer) — BSD-2-Clause, PMD/FMP 驱动与 OPN 寄存器实现参考
- [NP2kai](https://github.com/AZO234/NP2kai) — MIT, 模拟器宿主与 fmgen FM 核（实机 oracle）
- [ymfm](https://github.com/aaronsgiles/ymfm) — BSD-3-Clause, Yamaha FM 模拟核（离线音色 oracle，已 vendor 于 `tools/vendor/ymfm`）

License: MIT — see `LICENSE`.
