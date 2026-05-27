# Phase 6：跨平台移植

## 目标

实现 SDL2 HAL 后端，使同一套场景数据可在 PC-98（NP2kai）和现代 OS（SDL2）上运行。

## 前置依赖

- ✅ Phase 2 完成（引擎核心稳定）
- ✅ Phase 3 完成（音频系统）
- ✅ Phase 4 完成（数据管线）

## 参考项目

| 项目 | 查阅内容 | 用途 |
|------|----------|------|
| xsystem35-sdl2 | GPL v2，仅参考 | SDL2 后端 blit/palette/effect/输入处理 |
| pmdmini | GPL v2（SDL2 后端可链接使用） | SDL2 音频播放 |

## 关键技术方案

PC-98 的 VRAM 是 4 个独立位平面（B/R/G/I），每个像素 4 位。SDL2 后端的核心是将 4 平面渲染映射为 32-bit RGBA surface：

```
PC-98 VRAM 布局：                    SDL2 等效：
  plane0 (B) @ 0xA800                uint32 pixel;
  plane1 (R) @ 0xB000                像素 0:  (p0>>7) | ((p1>>6)&2) | ((p2>>5)&4) | ((p3>>4)&8)
  plane2 (G) @ 0xB800                像素 1: ...
  plane3 (I) @ 0xE000
```

## 实施步骤

### Step 1：SDL2 HAL 后端

`core/plat/sdl2/` — 完整 SDL2 平台层。

| 文件 | 对应 PC-98 文件 | 功能 |
|------|-----------------|------|
| `sdl2/video.c` | `pc98/pc98_gdc.c` + `pc98_grcg.h` + `pc98_egc.c` | SDL2 窗口、surface 管理、4-plane 模拟 blit、调色板 4bpc→32bpp 映射 |
| `sdl2/input.c` | `pc98/pc98_keyboard.c` | SDL2 事件 → 引擎键码映射 |
| `sdl2/file_stdio.c` | `filehandling.c` + `doscalls.h` | stdio fopen/fread/fclose 替代 DOS INT 21h |
| `sdl2/audio_pmdmini.c` | `audio_pmd.c` + `audio_beep.c` | pmdmini 集成（PMD/MDX 播放）+ fm synthesis |

- [ ] `plat/sdl2/video.c` — 窗口创建 + surface blit
- [ ] `plat/sdl2/input.c` — 键盘/鼠标事件映射
- [ ] `plat/sdl2/file_stdio.c` — stdio 文件操作
- [ ] `plat/sdl2/audio_pmdmini.c` — pmdmini 音频

### Step 2：SDL2 构建系统

`core/Makefile.sdl2` — SDL2 版本编译配置。

```makefile
CC      = gcc
CFLAGS  = -Iengine -Iplat $(shell sdl2-config --cflags) -O2
LDFLAGS = $(shell sdl2-config --libs) -lSDL2_mixer
OBJS    = build/main.o build/rootinfo.o build/palette.o build/scenevm.o \
          build/textengine.o build/graphics.o build/gpimage.o build/fontfile.o \
          build/lz4.o build/audio.o build/audio_adpcm.o \
          build/sdl2_video.o build/sdl2_input.o build/sdl2_file_stdio.o \
          build/sdl2_audio_pmdmini.o
```

- [ ] `core/Makefile.sdl2`

### Step 3：验证

- 同一份 `out/` 数据在 SDL2 窗口上正确渲染
- 与 NP2kai 表现一致（画面、文本、选择、音频）
- **✅ M6**：同一场景数据可在 PC-98 和 SDL2 上运行

- [ ] SDL2 版本编译通过
- [ ] NP2kai 与 SDL2 输出对比验证
- [ ] **✅ M6** 确认

## 产出物

```
core/plat/sdl2/
├── video.c
├── input.c
├── file_stdio.c
└── audio_pmdmini.c
core/Makefile.sdl2
```

## 验证

回到 `03-编译example项目方案.md` 确认 M6 里程碑。
