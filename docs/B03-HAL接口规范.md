# HAL 接口规范

## 1. 概述

HAL（Hardware Abstraction Layer）是引擎与平台之间的唯一边界。
`core/plat/hal.h` 声明全部接口，引擎核心（`core/engine/`）**只通过 hal.h 与平台交互**——
`outportb()`、`int 0x18` 等硬件操作代码禁止出现在 `core/engine/` 中。

### 现有后端

| 后端 | 路径 | 状态 |
|------|------|------|
| PC-98 (DOS/4GW 32-bit) | `core/plat/hal_pc98.c` 等（见下表） | ✅ 可用 |

**平台层文件职责（0.4.011 起）**

| 文件 | 职责 |
|------|------|
| `hal_pc98.c` | `hal_init`、调色板、VRAM bank 窗口 |
| `hal_clock.c` | `hal_wallclock_ms` / `hal_wallclock_smooth_*` / `hal_vblank_wait` / `hal_vblank_poll`（vclock 委托 `lib/vclock.c`） |
| `hal_log.c` | `hal_log` / `hal_logf` |
| `hal_probe.c` | `hal_irq_probe_run` / `hal_dpmi_probe_run`（`#if NAIZ_IRQ_PROBE`） |
| `hal_irq.c` | Timer-B ISR（`#if NAIZ_BGM_IRQ`） |
| `hal_internal.h` | 平台内部声明（仅 `hal_clock_init`），禁止 engine include |
| `mouse.c` / `keyboard.c` / `video.c` | `hal_mouse_*` / `hal_kbd_*` / `hal_video_*` 的直接实现（原三个转发层已删除） |

---

## 2. HAL 接口清单

```c
void hal_init(void);
void hal_log(const char *s);
void hal_set_palette(int idx, uint8_t r, uint8_t g, uint8_t b);
void hal_read_palette(int idx, uint8_t *r, uint8_t *g, uint8_t *b);
```

| 函数 | 契约 | PC-98 实现 |
|------|------|------------|
| `hal_init` | 平台初始化（串口等） | 调用 `serial_init()` |
| `hal_log` | 调试输出到串口 | 调用 `serial_puts()` |
| `hal_set_palette` | 设置调色板（0-255, 8-bit RGB） | 写端口 0xA8/0xAA/0xAC/0xAE |
| `hal_read_palette` | 回读调色板（0-255, 8-bit RGB） | 调用 `gdc_read_palette()`（端口 0xA8/0xAC/0xAA/0xAE） |

**规范**：
- `hal_init()` 必须在其他 HAL 函数之前调用
- `hal_log()` 输出到 COM1 串口（9600 8N1），用于调试
- `hal_set_palette()` / `hal_read_palette()` 的 `idx` 范围 0-255，对应 PEGC 256 色模式

---

## 3. 添加新后端

### 步骤

1. 在 `core/plat/` 下创建新文件（如 `hal_sdl2.c`）
2. 实现 `hal.h` 中声明的全部 4 个函数
3. 在 `core/Makefile` 中添加新后端的 `.o` 文件

### 验证清单

- [ ] `hal_init` 初始化成功
- [ ] `hal_log` 输出可见
- [ ] `hal_set_palette` / `hal_read_palette` 调色板读写一致

---

## 4. 渲染层（render.h）

`render.h` / `render.c` 是 VRAM 操作的实现层，位于 `core/engine/` 但直接操作硬件。
它是 HAL 的补充——引擎通过 `render.h` 的 API 进行像素操作，通过 `hal.h` 进行平台初始化和调色板设置。

### API 清单

```c
void fill_rect(int x, int y, int w, int h, uint8_t color);
void draw_rect(int x, int y, int w, int h, int t, uint8_t color);
/* 字形绘制函数已内联为 render.c 内部宏（draw_ascii/draw_ascii_b/draw_cjk/draw_cjk_b） */
int  draw_text(const char *s, int byte_start, int x, int y,
               int max_width, int max_y, int bold, uint8_t color);
int  text_width(const char *s, int bold);
void draw_rounded_rect(int x, int y, int w, int h, int r,
                        uint8_t fill, uint8_t border, int border_w);
void draw_rounded_emboss(int x, int y, int w, int h, int r,
                          uint8_t fill, uint8_t highlight, uint8_t shadow);
void vram_blit(const MagImage *img, int x, int y);
void vram_blit_sprite(const MagImage *img, int x, int y,
                      uint8_t transparent_idx, int mirror, int clip_h);
void fill_rect_pattern(int x, int y, int w, int h,
                       const uint8_t pattern[8], uint8_t color);
void vram_read(int x, int y, int w, int h, uint8_t *buf);
void vram_write(const uint8_t *buf, int x, int y, int w, int h);
void vram_pset_addr(int addr, uint8_t color);
```

字形绘制（`draw_glyph`/`draw_glyph_cjk`）不再是公开 API——已内联为 `render.c` 内部宏。`pset()` 因无调用者已移除，单像素写入使用 `vram_pset_addr()`。

### 性能优化

所有内层循环使用 bank 缓存——跟踪当前 bank，只在 bank 变化时调用 `bank_select()`。
全屏操作从 ~256,000 次端口写入降到 ~8 次。

---

## 5. 平台无关库（core/lib/）

以下模块零平台依赖，可被任何 C 项目复用：

| 模块 | 文件 | 功能 |
|------|------|------|
| **endian** | `lib/endian.h` | LE 16/32-bit 内联读取 |
| **naiz_file** | `lib/naiz_file.c/h` | 文件读取辅助（file_read_all） |
| **mag** | `lib/mag.c/h` | MAKI02 图像解码 |
| **font** | `lib/font.c/h` | ASCII 8×16 字形加载 |
| **cjk** | `lib/cjk.c/h` | CJK 16×16 字形加载（可选日志回调） |
| **tr** | `lib/tr.c/h` | i18n 翻译表加载/查询 |
| **vclock** | `lib/vclock.c/h` | 平滑虚拟时钟（BGM/打字机/动画的节拍器） |

---

## 5.1 虚拟时钟的契约与禁区（devdoc 211）

`hal_wallclock_smooth_ms()` 是**节拍器**，不是秒表。它的三条保证（`vclock.h:11-23`）：

1. 相邻两次推进的差值 ≤ `VCLOCK_SLEW_UNITS`（步长平滑，BGM 不颤）
2. 平台时钟冻结时不卡死、跳变时不分批倾泻
3. **长期平均**速率与真实时间一致

注意第 3 条限定词是「长期平均」——`vclock.h:36-40` 明确写了：

> only the clock's **rate** matters, never its **phase** against the platform's reading

### 可以拿来做什么

BGM 事件调度、打字机 reveal、动画帧、`waitanima` 超时——这些是**闭环**消费方，只关心「速率」，相位偏差会被自己纠正。

### 绝对不能拿来做什么

**任何「截止时间 / 超时 / 安全阀」语义**。原因：时钟一旦失准（见 devdoc 211：实测快 3.9 倍），超时就会变成「静默跳过并推进剧情」，而这类 bug 只在**玩家不操作**时才显形。

如果确实要用它做截止时间，必须配一条健康度校验：

```c
/* d = 真实 − 虚拟；超过阈值说明 vclock 已失准，此时不要相信 deadline */
long drift = (long)(hal_wallclock_ms() - hal_wallclock_smooth_ms());
```

### 铁律

| 规则 | 说明 |
|---|---|
| **`vclock_advance()` 必须每帧恰好调用一次** | 由 `engine_frame_pump()` 独占（`frame.c:62`）。这是**只写不查的契约**——违反后没有任何报错 |
| **`vclock_advance()` 与 `vclock_advance_fixed()` 不得混用于同一 `VClock`** | 前者按真实时间测量，后者按硬件定时器硬编码（ISR 路径，`hal_irq.c:224`）。切换时必须复位基线（`vclock_reset_baseline()`，devdoc 211 §7.3） |
| **不要用 `[FPS]` 的 `ms` 当真实时间** | 它累加的是 `smooth_ms()` 差（`render.c:265`），是**虚拟时间**。真实漂移只看 `[AP]` 的 `d` |

### 快速自检

```bash
# 抓串口，看 [AP] 行的 d 字段（每秒一行）
grep '\[AP\]' logs/serial_*.log | tail -20
```

`d` 稳定在 ±500 ms 内 = 健康；持续为负且绝对值增长 = 时钟跑快了。
详细排查顺序见 `B09-引擎开发与调试全流程.md` §5.3.1。

---

## 6. 来源声明

HAL 设计参考 MHVNVisualNovelEngine (MIT) 的兼容性检查逻辑。
