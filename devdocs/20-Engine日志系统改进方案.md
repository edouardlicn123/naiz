# Engine 日志系统改进方案

## 1. 当前实现

日志通过 `core/engine/log.c` + `log.h` 实现，底层走 HAL 的 DOS 文件 I/O（INT 21h AH=3Ch/40h/3Eh）。

```
main.c → log_write("...") → raw_write() → hal_file_write() → INT 21h AH=40h → 磁盘
```

每次调用 `log_write()` 都触发一次 DOS 磁盘写入。

## 2. 现存问题

| # | 问题 | 影响 |
|---|------|------|
| 1 | 每次 log_write() 都做 DOS 磁盘 I/O | 60fps 循环中写日志会严重拖慢帧率 |
| 2 | 无格式化输出 | log_write("x=") + log_write_dec(x) 链式调用繁琐 |
| 3 | 无 \r\n 封装 | 到处写 "\r\n"，容易漏 |
| 4 | 日志只在 HDI 里，关模拟器后才能提取 | 开发迭代慢，无法实时查看 |
| 5 | 无日志级别 | 调试日志和错误日志混在一起 |
| 6 | 无 hex 输出 | 调试硬件寄存器时需要自己转 |

## 3. 改进方案

### 3.1 Buffer I/O（高优先级）

加一个 256 字节的静态环形 buffer，写入先填 buffer，满了才触发一次 DOS 写。

```
改进前:   log_write("A") → INT 21h → 磁盘
          log_write("B") → INT 21h → 磁盘
          log_write("C") → INT 21h → 磁盘

改进后:   log_write("A") → buffer[0] = 'A'
          log_write("B") → buffer[1] = 'B'
          log_write("C") → buffer[2] = 'C'
          log_flush() → INT 21h → 磁盘 ("ABC")
```

- IO 次数减少 5-10 倍
- 新增内存：~258 字节（buffer + 指针）
- 关闭时自动 flush，崩溃时最多丢失 buffer 内未 flush 的内容（~256 字节）

### 3.2 log_printf 格式化输出（高优先级）

```c
void log_printf(const char *fmt, ...);
```

支持格式：

| 格式 | 含义 | 例子 |
|------|------|------|
| `%s` | 字符串 | `log_printf("file=%s", path)` |
| `%d` | 无符号十进制 | `log_printf("count=%d", n)` |
| `%x` | 十六进制 | `log_printf("reg=%x", ax)` |
| `%c` | 字符 | `log_printf("key=%c", ch)` |
| `%%` | 字面量 % | |

把：
```c
log_write("B OK\r\n");
log_write("elapsed=");
log_write_dec(elapsed);
log_write("s\r\n");
```
变成：
```c
log_printf("B OK\n");
log_printf("elapsed=%ds\n", elapsed);
```

- 新增内存：运行时栈上临时 buffer 128 字节
- 依赖 `<stdarg.h>`（编译器内置，无需 libc）

### 3.3 log_nl 换行封装（低优先级）

```c
void log_nl(void);
```

等价于 `log_write("\r\n")`，减少重复字符串字面量。

### 3.4 文本 VRAM 屏幕输出（中优先级）

PC-98 的文本 VRAM 分两层：
- `0xA000:偏移` — 字符码（1 字节）
- `0xA200:偏移` — 属性字节（前景色 / 背景色 / 闪烁）

即使 GDC 处于图形模式，文本层仍可独立显示（由 GDC 模式寄存器控制叠加）。

实现：
```c
void log_write_screen(const char *s);
```
在图形模式的底部或顶部预留几行文本区域，日志同时写入文件 + 屏幕。

- 新增内存：0 字节（直接写显存）
- 好处：NP2kai 窗口里直接看到日志，无需提取 HDI

### 3.5 日志级别（低优先级）

```c
enum log_level { LOG_DEBUG, LOG_INFO, LOG_WARN, LOG_ERROR };
void log_set_level(enum log_level lvl);
```

低于当前级别的消息自动丢弃。适合运行时控制详细程度，正式发布时调到 WARN 以上。

## 4. 内存影响总览

| 组件 | 额外内存 |
|------|---------|
| 缓冲输出（256B buffer + pos） | ~258 字节 |
| log_printf（栈上临时 buffer） | ~128 字节（运行时临时） |
| log_nl | 0 字节 |
| 文本 VRAM 输出 | 0 字节（无 buffer，直接写显存） |
| 日志级别（枚举 + 全局变量） | ~2 字节 |
| **合计** | **~260 字节常驻 + 128 临时** |

在 640KB DOS 内存中占比 < 0.06%。

## 5. 优先级排序

| 优先级 | 方案 | 原因 |
|--------|------|------|
| P0 | Buffer I/O | 直接影响帧率，不改没法在循环里写日志 |
| P0 | log_printf | 最大幅减少调用方代码量 |
| P1 | Text VRAM 输出 | 开发时实时可见，提速迭代 |
| P2 | log_nl | 微优化 |
| P3 | 日志级别 | 正式发布前做即可 |

## 6. 当前日志写入点（demo-A1 main.c）

| 点 | 内容 |
|----|------|
| main 入口 | `OPEN %datetime%` |
| hal_check_compatibility 前 | `A` |
| hal_check_compatibility 后 | `B OK` / `B FAIL` |
| hal_video_init 前 | `C VIDEO_INIT` |
| fill_rect 循环前 | `D FILL_LOOP` |
| 退出 | `F DONE %elapsed%s` |
