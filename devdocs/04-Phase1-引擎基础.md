# Phase 1：引擎基础

## 目标

建立完整的编译框架和 PC-98 平台层，在 NP2kai 上输出 Hello World 画面（纯色填充 + 兼容性检查通过）。

## 前置依赖

- 环境安装完成（gcc-ia16、NP2kai）

## 参考项目

| 项目 | 查阅内容 | 用途 |
|------|----------|------|
| MHVNVisualNovelEngine | `MHVN98/src/main.c`、`MHVN98/src/platform/` 全部 | 入口点、平台层实现 |
| MHVNVisualNovelEngine | `MHVN98/Makefile`、`MHVN98/wholeprog.c` | 构建系统参考 |
| master.lib | `libsrc/`（grcg、egc、gdc、key） | EGC/GRCG/GDC 编程模式 |
| MHVN98 分析文档 | `MHVN98/03-平台抽象层.md`、`MHVN98/14-中断处理.md` | 架构理解 |

## 实施步骤

### Step 1：HAL 接口定义

编写 `core/plat/hal.h`，声明引擎与 PC-98 的全部边界。

```c
#ifndef HAL_H
#define HAL_H

/* 视频初始化 */
void hal_video_init(void);
void hal_video_set_palette(int idx, unsigned char r, unsigned char g, unsigned char b);
void hal_video_fill_rect(int x, int y, int w, int h, int color);
void hal_video_vsync_wait(void);
void hal_video_clear_screen(void);

/* 输入（键盘） */
void hal_input_init(void);
int  hal_input_poll(void);         /* 0=无键, 其他=键码 */
int  hal_input_state(int scancode); /* 0/1 */

/* 文件 I/O */
int  hal_file_open(const char *path, unsigned char mode);
int  hal_file_read(int fd, void *buf, int count);
int  hal_file_close(int fd);
int  hal_file_seek(int fd, unsigned char method, unsigned long len, unsigned long *newpos);

/* 内存 */
void *hal_mem_alloc(unsigned short segments);
void  hal_mem_free(void *ptr);

/* 中断 */
void hal_interrupt_set(unsigned char vector, void (*handler)(void));
void hal_interrupt_get(unsigned char vector, void (**handler)(void));

/* 定时 / VSync */
void hal_vsync_enable(void);
void hal_vsync_disable(void);
int  hal_vsync_count(void);   /* 返回自上次调用后的 VSync 次数 */

/* 兼容性检查 */
int hal_check_compatibility(void);  /* 0=不支持 */

#endif
```

- [ ] `core/plat/hal.h` 编写完成

### Step 2：构建系统

参考 MHVN98 的构建方式，输出 MZ .EXE。

```makefile
CC     = ia16-elf-gcc
AS     = ia16-elf-as
CFLAGS = -march=i386 -mcmodel=small -Os -ffreestanding -nostdlib \
         -Iengine -Iplat -I.
LDFLAGS = -Wl,-melf_i386_msdos_mz,-M,-static,--relax,-n,--no-dynamic-linker,--print-memory-usage
LDLIBS  = -li86
OUTPUT  = engine.exe

PLAT_OBJS = build/x86strops.o build/memalloc.o build/filehandling.o \
            build/pc98_gdc.o build/pc98_grcg.o build/pc98_egc.o \
            build/pc98_keyboard.o build/pc98_chargen.o build/isr.o

ENGINE_OBJS = build/main.o build/lz4.o

OBJS = $(ENGINE_OBJS) $(PLAT_OBJS)

all: $(OUTPUT)

$(OUTPUT): $(OBJS) | build
	$(CC) $(LDFLAGS) -o $@ $(OBJS) $(LDLIBS)

build/%.o: engine/%.c | build
	$(CC) $(CFLAGS) -c -o $@ $<

build/%.o: plat/pc98/%.c | build
	$(CC) $(CFLAGS) -c -o $@ $<

build/%.o: plat/pc98/%.asm | build
	$(AS) -o $@ $<

build:
	mkdir -p build

clean:
	rm -rf build $(OUTPUT)
```

> **注意**：原版 MHVN98 还提供了 `wholeprog.c` 可选编译方式（`-fwhole-program` 将所有 .c 合并编译以获得更好优化），Phase 1 暂不使用此方式，后续 Phase 按需启用。

- [ ] `core/Makefile` 编写完成
- [ ] `make all` 零错误零警告

### Step 3：基础平台工具

参考 MHVN98 的 `platform/` 目录，实现 x86 字符串操作、DOS 文件 I/O、内存分配等。

| 文件 | 参考源 | 功能 |
|------|--------|------|
| `plat/pc98/x86strops.h` | `platform/x86strops.h` | near/far memset/memcpy（REP STOSW/MOVSW） |
| `plat/pc98/x86segments.h` | `platform/x86segments.h` | DS/ES/SS 段寄存器 inline asm |
| `plat/pc98/x86ports.h` | `platform/x86ports.h` | inb/outb 端口 I/O inline |
| `plat/pc98/x86interrupt.h` | `platform/x86interrupt.h` | GET/SET 中断向量 |
| `plat/pc98/doscalls.h` | `platform/doscalls.h` | INT 21h 完整封装（打开/读/写/关闭/寻址/内存） |
| `plat/pc98/filehandling.c` + `.h` | `platform/filehandling.c` + `.h` | DOS 文件 I/O 封装层 |
| `plat/pc98/memalloc.c` + `.h` | `platform/memalloc.c` + `.h` | DOS 内存分配（INT 21h AH=48h/49h/4Ah）|

- [ ] `plat/pc98/x86strops.h`
- [ ] `plat/pc98/x86segments.h`
- [ ] `plat/pc98/x86ports.h`
- [ ] `plat/pc98/x86interrupt.h`
- [ ] `plat/pc98/doscalls.h`
- [ ] `plat/pc98/filehandling.c` + `filehandling.h`
- [ ] `plat/pc98/memalloc.c` + `memalloc.h`

### Step 4：PC-98 HAL 后端实现

| 文件 | 参考源 | 实现功能 |
|------|--------|----------|
| `plat/pc98/pc98_gdc.h` + `.c` | `platform/pc98_gdc.h` + `.c` | GDC 图形模式设置、调色板写入、VSync 状态、显示/绘制页面、SCROLL 滚动、显示模式设置（640×400 56.4Hz） |
| `plat/pc98/pc98_grcg.h` | `platform/pc98_grcg.h` | GRCG RMW 模式、Tile 寄存器设置、清屏 |
| `plat/pc98/pc98_egc.h` + `.c` | `platform/pc98_egc.h` + `.c` | EGC 启用/禁用、清屏、单色绘制模式、VRAM blit 模式 |
| `plat/pc98/pc98_keyboard.h` + `.c` | `platform/pc98_keyboard.h` + `.c` | 键盘 INT 18h BIOS、shift 状态、按键查询 |
| `plat/pc98/pc98_chargen.h` + `.c` | `platform/pc98_chargen.h` + `.c` | PC-98 硬件字库读取（INT 18h AH=19h）|
| `plat/pc98/pc98_crtbios.h` | `platform/pc98_crtbios.h` | CRT BIOS INT 18h（显示模式、行缩放）|
| `plat/pc98/pc98_interrupt.h` | `platform/pc98_interrupt.h` | PIC IMR 读写（IRQ 2 控制）|
| `plat/pc98/isr.asm` | `MHVN98/src/isr.asm` | VSync 中断处理程序（INT 0Ah / IRQ 2）|

#### GDC 模式设置步骤（参考 `main.c` `GDCSetDisplayMode(640, 400, 440)`）：

1. `GDCSetDisplayMode(640, 400, 440)` — 设置 640×400 分辨率，`scannedLines = 440`（56.4 Hz）
2. `GDCStopText()` — 关闭文本层
3. `GDCStartGraphics()` — 开启图形层
4. `GDCSetGraphicsLineScale(1)` — 不缩放
5. `GDCSetMode1(GDC_MODE1_LINEDOUBLE_ON | GDC_MODE1_COLOUR)` — 行倍 + 彩色
6. `GDCSetGraphicsDisplayPage(0)` + `GDCSetGraphicsDrawPage(0)`
7. `GDCSetMode2(GDC_MODE2_16COLOURS)` — 16 色模式
8. `GDCSetDisplayRegion(0x0000, 400)` — 全屏显示区
9. `GDCScrollSimpleGraphics(0)` — 无偏移

- [ ] `plat/pc98/pc98_gdc.h` + `.c`
- [ ] `plat/pc98/pc98_grcg.h`
- [ ] `plat/pc98/pc98_egc.h` + `.c`
- [ ] `plat/pc98/pc98_keyboard.h` + `.c`
- [ ] `plat/pc98/pc98_chargen.h` + `.c`
- [ ] `plat/pc98/pc98_crtbios.h`
- [ ] `plat/pc98/pc98_interrupt.h`
- [ ] `plat/pc98/isr.asm`
- [ ] 每文件开头添加版权注释（复制自参考项目时）

### Step 5：基础引擎模块

| 文件 | 参考源 | 实现功能 |
|------|--------|----------|
| `engine/main.c` | `MHVN98/src/main.c` | `main()` 入口：兼容性检查 → HAL init → 主循环（VSync → fill_rect → 键盘退出）→ HAL deinit |
| `engine/lz4.c` + `.h` | `MHVN98/src/lz4.c` + `.h` + `lz48086.asm` | LZ4 块解压缩（调用 Trixter 8086 汇编实现） |

`main.c` Hello World 最小流程：

```c
int main(void)
{
    int result = hal_check_compatibility();
    if (!result) return 0xFF;

    hal_video_init();        // GDC 模式设置 + 默认调色板
    hal_video_clear_screen(); // EGC 清屏（背景色 0x0 = 黑）

    while (1)
    {
        hal_video_vsync_wait();
        hal_video_fill_rect(0, 0, 640, 400, 1);  // 蓝色全屏

        if (hal_input_state(0x01)) break;  // ESC 退出？用简单键检测
    }

    hal_video_clear_screen();
    return 0;
}
```

- [ ] `engine/main.c`
- [ ] `engine/lz4.c` + `lz48086.asm`

### Step 6：里程碑验证

1. 编译 `make all` 通过
2. `engine.exe` 复制到 NP2kai 虚拟磁盘
3. NP2kai 启动，显示：
   - 兼容性检查通过（不输出错误信息）
   - 蓝色全屏画面（`fill_rect(0,0,640,400,1)`）
   - 按键退出返回 DOS
4. **✅ M1**：NP2kai 显示蓝色画面（纯色填充）

- [ ] 编译通过
- [ ] NP2kai 运行验证
- [ ] **✅ M1** 确认

## 产出物

```
core/
├── Makefile
├── engine/
│   ├── main.c
│   └── lz4.c + lz48086.asm
├── plat/
│   ├── hal.h
│   └── pc98/
│       ├── x86strops.h
│       ├── x86segments.h
│       ├── x86ports.h
│       ├── x86interrupt.h
│       ├── doscalls.h
│       ├── filehandling.c + filehandling.h
│       ├── memalloc.c + memalloc.h
│       ├── pc98_gdc.h + pc98_gdc.c
│       ├── pc98_grcg.h
│       ├── pc98_egc.h + pc98_egc.c
│       ├── pc98_keyboard.h + pc98_keyboard.c
│       ├── pc98_chargen.h + pc98_chargen.c
│       ├── pc98_crtbios.h
│       ├── pc98_interrupt.h
│       └── isr.asm
└── build/
    └── engine.exe       ← 最终产出（MZ .EXE）
```

## 验证

完成后回到 `03-编译example项目方案.md` 确认 M1 里程碑。
