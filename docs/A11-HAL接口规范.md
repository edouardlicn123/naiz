# HAL 接口规范

## 1. 概述

HAL（Hardware Abstraction Layer）是引擎与平台之间的唯一边界。
`core/plat/hal.h` 声明全部接口，引擎核心（`core/engine/`）**只通过 hal.h 与平台交互**——
`outportb()`、`int 0x18` 等硬件操作代码禁止出现在 `core/engine/` 中。

### 现有后端

| 后端 | 路径 | 状态 |
|------|------|------|
| PC-98 | `core/plat/pc98/` | ✅ 可用 |
| SDL2 | `core/plat/sdl2/` | 📋 规划中 |

---

## 2. HAL 接口清单

### 2.1 视频

```c
void hal_video_init(void);
void hal_video_set_palette(int idx, unsigned char r, unsigned char g, unsigned char b);
void hal_video_fill_rect(int x, int y, int w, int h, int color);
void hal_video_vsync_wait(void);
void hal_video_clear_screen(void);
void hal_video_deinit(void);
```

| 函数 | 契约 | PC-98 实现 |
|------|------|------------|
| `hal_video_init` | 初始化显示模式（640×400, 16色），安装 VSync 中断，启用 IRQ | GDC 模式设置 + PIC 中断启用 |
| `hal_video_set_palette` | 设置指定索引的调色板 | `gdc_set_palette_colour()` |
| `hal_video_fill_rect` | 用 `color`（0-15）填充矩形区域 | 4 位平面 `rep stosw` |
| `hal_video_vsync_wait` | 等待下一次垂直同步，超时后继续 | 等待 `vsynced` 标志置位 |
| `hal_video_clear_screen` | 全屏清除（同 `fill_rect(0,0,640,400,1)`） | 调用 `fill_rect` |
| `hal_video_deinit` | 关闭显示，清理中断 | 复位 GDC 中断 |

**规范**：
- `hal_video_init` 必须在其他视频函数之前调用
- `color` 值 0-15，映射到 4 个位平面（B=bit0, R=bit1, G=bit2, I=bit3）

---

### 2.2 输入

```c
void hal_input_init(void);
int  hal_input_poll(void);
int  hal_input_state(int scancode);
```

| 函数 | 契约 | PC-98 实现 |
|------|------|------------|
| `hal_input_init` | 初始化键盘/输入子系统 | 空操作（BIOS 已初始化） |
| `hal_input_poll` | 轮询输入事件；返回 0 = 无事件 | 返回 0（暂未实现） |
| `hal_input_state` | 查询按键当前状态；返回 0/1 | 读 `0x052A` BIOS 键状态数组 |

**规范**：
- `hal_input_state` 使用 BIOS 键状态数组 (`0x052A`)，由 INT 09h 中断维护，与 FIFO 读取无冲突
- `scancode` 值见 `core/plat/pc98/pc98_keyboard.h` 中的 `KC_*` 常量

---

### 2.3 文件 I/O

```c
int  hal_file_open(const char *path, unsigned char mode);
int  hal_file_read(int fd, void *buf, int count);
int  hal_file_write(int fd, const void *buf, int count);
int  hal_file_close(int fd);
int  hal_file_seek(int fd, unsigned char method, unsigned long len, unsigned long *newpos);
```

| 函数 | mode / method | 契约 | PC-98 实现 |
|------|---------------|------|------------|
| `hal_file_open` | 0: 只读 / 1: 创建 / 2: 追加 | 返回 fd（≥0）或 -1 | DOS INT 21h AH=3Dh/3Ch |
| `hal_file_read` | — | 返回读取字节数或 -1 | DOS INT 21h AH=3Fh |
| `hal_file_write` | — | 返回写入字节数或 -1 | DOS INT 21h AH=40h |
| `hal_file_close` | — | 返回 0 或 -1 | DOS INT 21h AH=3Eh |
| `hal_file_seek` | 0: 开头 / 1: 当前 / 2: 末尾 | 返回 0 或 -1，通过 `newpos` 输出新位置 | DOS INT 21h AH=42h |

**规范**：
- 所有 DOS 调用后检查 CF 进位标志
- 返回值 -1 表示失败
- `path` 为 MS-DOS 风格路径（`\` 分隔，8.3 文件名）

---

### 2.4 内存

```c
void *hal_mem_alloc(unsigned short segments);
void  hal_mem_free(void *ptr);
```

| 函数 | 契约 | PC-98 实现 |
|------|------|------------|
| `hal_mem_alloc` | 分配 `segments` 个段（每段 16 字节）的远内存，返回远指针或 NULL | ❌ 暂未实现（返回 NULL） |
| `hal_mem_free` | 释放由 `hal_mem_alloc` 分配的内存 | ❌ 暂未实现 |

**规范**：
- `segments` = 分配的段数（1 段 = 16 字节，64KB 以内 = 4096 段）
- 返回 `void __far *`（PC-98 实模式远指针）
- 失败返回 NULL

---

### 2.5 中断

```c
void hal_interrupt_set(unsigned char vector, void (*handler)(void));
void hal_interrupt_get(unsigned char vector, void (**handler)(void));
```

| 函数 | 契约 | PC-98 实现 |
|------|------|------------|
| `hal_interrupt_set` | 设置中断向量 | 写 IVT（`0x0000:vector*4`）= handler 的 offset+segment |
| `hal_interrupt_get` | 读取中断向量 | 读 IVT，通过 `handler` 指针返回 |

**规范**：
- `vector` 范围 0x00-0xFF
- 安装前应 `hal_cli()`，安装后 `hal_sti()`

---

### 2.6 VSync / 定时

```c
void hal_vsync_enable(void);
void hal_vsync_disable(void);
int  hal_vsync_count(void);
```

| 函数 | 契约 | PC-98 实现 |
|------|------|------------|
| `hal_vsync_enable` | 启用 VSync 中断 | 设置中断向量 + PIC 启用 IRQ |
| `hal_vsync_disable` | 禁用 VSync 中断 | PIC 禁用 IRQ |
| `hal_vsync_count` | 返回自上次调用后的 VSync 次数 | ❌ 暂未实现（返回 0） |

---

### 2.7 兼容性检测

```c
int hal_check_compatibility(void);
```

| 返回值 | 含义 |
|--------|------|
| 非 0 | 平台兼容，引擎可继续运行 |
| 0 | 平台不兼容，引擎应退出 |

**PC-98 实现**：调用 INT 1Ah AX=1000h 检测 PC-98 BIOS，失败则返回不兼容。

---

## 3. 添加新后端

### 步骤

1. 在 `core/plat/` 下创建新目录（如 `sdl2/`）
2. 实现 `hal.h` 中声明的全部函数
3. 在 `core/` 的 Makefile 中添加新后端的构建目标
4. 修改链接配置，链接新后端的 `.o` 文件

### 验证清单

- [ ] `hal_check_compatibility` 在新平台上返回非 0
- [ ] `hal_video_init` + `hal_video_fill_rect` 输出正确画面
- [ ] `hal_input_state` 能检测到按键
- [ ] `hal_file_open/read/write/close/seek` 能读写文件
- [ ] `hal_interrupt_set/get` 能正确安装中断

---

## 4. PC-98 后端文件索引

| 文件 | 负责的 HAL 函数 | 依赖 |
|------|-----------------|------|
| `hal_pc98.c` | 全部 HAL 函数（主调度） | 其余 pc98/ 模块 |
| `pc98_gdc.c` | `hal_video_*` | GDC 寄存器 |
| `pc98_egc.c` | 图形加速（被 `fill_rect` 调用） | EGC 寄存器（端口 0x4A0） |
| `pc98_chargen.c` | 字符发生器（备用） | GDC |
| `pc98_keyboard.c` | `hal_input_state` | BIOS 0x052A |
| `filehandling.c` | `hal_file_*` | DOS INT 21h |
| `memalloc.c` | `hal_mem_alloc/free` | DOS INT 21h AH=48h/49h |
| `isr.asm` | VSync 中断处理 | PIC |

---

## 5. 来源声明

`core/plat/pc98/` 各模块参考以下项目的设计思路独立实现：

- MHVNVisualNovelEngine (MIT) — 兼容性检查、模式初始化逻辑
- master.lib（源码公开）— EGC/GRCG/GDC 编程模式
