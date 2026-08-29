# Naiz — PC-98 Visual Novel Engine

> **なにいえ** — 基于 PC-98（NEC PC-9801/9821）的电子小说引擎，使用 NB 纯文本剧本格式。
> A PC-98 visual novel engine with NB (Naiz Book) text-based scripting.

---

## Overview

Naiz 是一个运行在 PC-98 DOS/4GW 32-bit 保护模式下的视觉小说引擎。使用 NB 纯文本格式编写剧本，支持背景切换、角色立绘、对话分页、场景跳转和菜单交互。

核心特性：
- **NB 剧本解释器** — 纯文本 `.nb` 文件，命令分发表架构
- **256 色 PEGC** — MAG 图像解码 + 调色板管理
- **CJK 文字渲染** — UTF-8 解码 + 8×16 ASCII / 16×16 CJK 字形
- **对话系统** — 自动分页 + 等待按键翻页
- **菜单系统** — 方向键选择 + Enter 确认

---

## Build & Test

```bash
# 编译引擎 + 部署游戏文件
makegame.sh build demo-a2

# 打包 HDI 镜像
makegame.sh make demo-a2

# 在 NP2kai 中测试
makegame.sh test demo-a2

# 串口调试输出
makegame.sh test demo-a2 --serial
```

### Build Commands

| Command | Description |
|---------|-------------|
| `make -C core` | 仅编译引擎 |
| `makegame.sh build <game>` | 完整构建 (素材→MAG→IMAGE.DAT→编译→部署) |
| `makegame.sh make <game>` | 仅打包 HDI |
| `makegame.sh test <game>` | 启动 NP2kai 测试 |

---

## Architecture

### Engine Initialization

```
hal_init()             → 串口调试通道
font_init("FONT.DAT")  → 8×16 ASCII 字形
cjk_init("CJK.DAT")    → CJK 字形
kbd_init()             → 键盘中断驱动
video_init()           → PEGC MMIO + BIOS 模式设置
hal_set_palette()      → 调色板
image_init("IMAGE.DAT")→ 图片归档加载
nb_init()              → NB 解释器初始化 (读取 settings.txt + logo.nb)
scene_process 循环     → 场景执行
```

### Runtime

- **32-bit 保护模式** — DOS/4GW v4.45
- **内存管理** — VEM486.EXE
- **显示** — PEGC 256 色, 640×400
- **VRAM** — Bank 切换, 0xA8000 窗口

### HAL Interface

引擎通过 `core/plat/hal.h` 访问硬件：
```c
void hal_init(void);
void hal_log(const char *s);
void hal_set_palette(int idx, uint8_t r, uint8_t g, uint8_t b);
```

---

## Compiler

- **Open Watcom v2.0** — `wcl386 -bt=dos -l=dos4g`
- **C 标准** — C89 (无混合声明)
- **编译开关** — `-DUSE_NB_INTERPRETER` (NB 解释器), `-DAUTOEXIT` (自动退出测试)

---

## Reference Projects

- [MHVNVisualNovelEngine](https://github.com/maxotaku11niku/MHVNVisualNovelEngine) — MIT, 场景格式参考
- [98Bridge](https://github.com/NullMagic2/98Bridge) — MIT, HDI 注入设计参考

## License

引擎代码 (`core/`) 和工具链 (`tools/`) 为全新书写，使用 MIT License。

参考项目遵守各自许可证，详见 `AGENTS.md`。
