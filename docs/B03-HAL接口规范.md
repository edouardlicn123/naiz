# HAL 接口规范

## 1. 概述

HAL（Hardware Abstraction Layer）是引擎与平台之间的唯一边界。
`core/plat/hal.h` 声明全部接口，引擎核心（`core/engine/`）**只通过 hal.h 与平台交互**——
`outportb()`、`int 0x18` 等硬件操作代码禁止出现在 `core/engine/` 中。

### 现有后端

| 后端 | 路径 | 状态 |
|------|------|------|
| PC-98 (DOS/4GW 32-bit) | `core/plat/hal_pc98.c` | ✅ 可用 |

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

---

## 6. 来源声明

HAL 设计参考 MHVNVisualNovelEngine (MIT) 的兼容性检查逻辑。
