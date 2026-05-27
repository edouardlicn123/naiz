# Phase 3：音频系统

## 目标

实现 PMD 音乐接口、534ADPCM 音效解码、PC-98 蜂鸣器系统音效，使场景中可播放 BGM 和 SE。

## 前置依赖

- ✅ Phase 2 完成（场景可运行）

## 参考项目

| 项目 | 查阅内容 | 用途 |
|------|----------|------|
| MHVNVisualNovelEngine | `MHVN98/src/pmd.h` | PMD.COM 接口定义 |
| MHVNVisualNovelEngine | `pc98_vnengine.txt` - SE data archive 格式 | 534ADPCM 音效格式规范 |
| master.lib | `libsrc/b_*.asm` | 蜂鸣器频率控制 |
| pmdmini | **GPL v2**（仅参考接口，不复制代码） | PMD/MDX 格式解析 API |
| 98fmplayer | BSD 2-Clause | OPNA/OPN3 FM 芯片编程范例 |

> **GPL 注意**：pmdmini 使用 GPL v2 许可证。PMD 的调用方式有两种：
> 1. **[推荐] 外部 PMD.COM 进程调用** — 引擎通过 DOS EXEC 或 `int 2Fh` 调用 PMD.COM 播放音乐，PMD.COM 不被链接进引擎，不触发 GPL 传染
> 2. **[备选] 内嵌 pmdmini 库** — 需全项目 GPL 开源

## 实施步骤

### Step 1：PMD 音乐接口

`engine/audio_pmd.c` + `.h` — PMD.COM 调用封装。

PMD 接口（参考 `pmd.h`）：
- `PMD_Load(filename)` / `PMD_Play()` / `PMD_Stop()` / `PMD_FadeOut()`
- 通过 DOS `EXEC`（INT 21h AH=4Bh）或内存驻留通信调用

`engine/audio.c` — 引擎音频抽象层：

```c
void audio_play_bgm(int track);
void audio_stop_bgm(void);
void audio_set_volume(int vol);
```

PC-98 后端通过 PMD.COM 实现。
SDL2 后端通过 pmdmini 集成（见 Phase 6）。

- [ ] `engine/audio.c` — 音频抽象接口
- [ ] `engine/audio_pmd.c` — PMD.COM 调用封装
- [ ] `engine/audio_pmd.h` — PMD 函数声明

### Step 2：534ADPCM 音效

`engine/audio_adpcm.c` — 534ADPCM 音效解码与播放。

534ADPCM 格式（参考 `pc98_vnengine.txt`）：
```
ADPCM 4-bit 压缩格式，每采样 4 位
支持 534Hz ~ 44.1kHz 采样率
单声道
```

- 加载 SE 数据 archive（`sedat_file`）
- 场景触发 SE 时解码 + 通过 PC-98 可编程声音源播放
- 支持全局 SE 和场景专属 SE

- [ ] `engine/audio_adpcm.c` — 534ADPCM 解码
- [ ] `engine/audio_se.c` — SE 数据 archive 加载 + 触发

### Step 3：蜂鸣器系统音效

`plat/pc98/audio_beep.c` — PC-98 蜂鸣器控制。

功能：
- PIT 8253 定时器设置（端口 0x3FDBh/0x3FDFh）
- 单音播放（频率 + 时长）
- 按键确认提示音
- MML 解析（参考 master.lib `b_*.asm`）

- [ ] `plat/pc98/audio_beep.c` — 蜂鸣器驱动

### Step 4：场景集成

- 在 VM 中添加 `bgm` / `se` / `fadeout` 指令支持（opcode 扩展或现有 opcode 覆盖）
- 场景中可播放 BGM 和 SE
- **✅ M3**：场景中可播放 BGM 和 SE

- [ ] VM 集成音频指令
- [ ] **✅ M3** 确认

## 产出物

```
core/engine/
├── audio.c             ← 音频抽象
├── audio_pmd.c + .h    ← PMD 接口
├── audio_adpcm.c       ← 534ADPCM 解码
└── audio_se.c          ← SE archive 管理

core/plat/pc98/
└── audio_beep.c        ← 蜂鸣器驱动
```

## 验证

回到 `03-编译example项目方案.md` 确认 M3 里程碑。
