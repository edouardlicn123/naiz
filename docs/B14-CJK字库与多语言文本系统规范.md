# B14 — CJK 字库与多语言文本系统规范

> **状态**：活跃 — CJK.DAT 字库 + CJK 渲染已实现。TXA 多语言 / LANGUAGE.DAT / text_table_* 标注为"从未实现"（NB 引擎的对话文本直接来自 `.nb` 脚本文件）。
> 本文 §3/§4/§6.2 描述的是旧 `scene.c` 架构的预留设计，当前引擎使用 NB 脚本解释器 + tr.c/tr.h 翻译模块方案。
> **创建**：2026-06-11
> **关联**：devdocs/0.1版开发文档总结.html#doc-16、`core/engine/tr.c` + `tr.h`（翻译模块实现）

---

## 1. 概述

### 1.1 解决的问题

1. 引擎需要支持 8×16 ASCII + 16×16 CJK 字形混合渲染（**已实现**：`cjk_init("CJK.DAT")` + UTF-8 感知 `draw_text()`）
2. 多语言支持（**已实现**：`tr.c`/`tr.h` 翻译模块，对话文本直接来自 `.nb` 脚本的 `tr{}` 标记；旧 `text_table`/`SCENE.DAT`/`LANGUAGE.DAT` 方案从未实现）

### 1.2 系统架构

```
┌──────────────┐   LANGUAGE.DAT（语言配置）
│ text_init()  │────→ "zh"
└──────┬───────┘
       │ text_table_load("LANG/zh.txa")
       ▼
┌──────────────┐   ┌──────────────────┐
│  text_table  │──→│ SCENE.DAT        │
│  [ptr array] │   │  text 0, text 1  │
└──────┬───────┘   └──────────────────┘
       │ text_table_get(idx)
       ▼
┌──────────────┐   ┌──────────────────┐
│ draw_text()  │──→│ CJK.DAT          │
│ UTF-8 感知   │   │ + FONT.DAT(ascii)│
└──────┬───────┘   └──────────────────┘
       │ pset / blit
       ▼
       VRAM
```

### 1.3 三层分离（预留设计，从未实现）

> 当前引擎使用 NB 脚本 + `tr.c`/`tr.h` 翻译模块替代此方案。

| 层 | 内容 | 跨语言共享 |
|---|------|-----------|
| SCENE.DAT | 场景字节码（opcode + 文本索引） | ✅ 一份 |
| TXA | 字符串表（索引 → UTF-8） | ❌ 每种语言一份 |
| CJK.DAT | 16×16 点阵字形 | ✅ 一份 |

---

## 2. CJK.DAT 字库格式

### 2.1 动机

MHVN98 的 FONT.DAT 格式每个字符都有独立的 `(offset, width, height)` 字段（4 字节/字），对 ~34,000 字的 CJK 字库多出 ~136 KB 冗余开销。由于 CJK 字形统一为 16×16，改为密度优先的格式。

### 2.2 文件布局

```
[Header: 10 bytes]
  magic        "CJKF" (4B)
  range_count  uint16 (2B)    ← range 条目数，最大 128
  reserved     uint32 (4B)    ← 对齐填充，当前 0x00000000

[Range List: 16 × range_count bytes]
  Each entry:
    start_cp      uint32 (4B)    ← Unicode codepoint 起始
    end_cp        uint32 (4B)    ← Unicode codepoint 结束（含）
    glyph_offset  uint32 (4B)    ← 该 range 首个字形在文件中的字节偏移
    reserved      uint32 (4B)    ← 对齐填充

[Glyph Data: 32 × total_glyphs bytes]
  Dense array, each glyph = 16 rows × 2 bytes (big-endian, 1 bit/pixel)
    row[0] = MSB←像素→LSB (byte 0: 左 8 像素, byte 1: 右 8 像素)
    row[1]
    ...
    row[15]
```

**重要一致性约束**：第一个 range 的 `glyph_offset` 必须等于 `10 + range_count × 16`。
引擎 `cjk_init()` 加载时若检测到不匹配，会拒绝加载并输出串口错误。
参见 `core/lib/cjk.c` 末尾校验逻辑和 `tools/naiz_font/gen_cjk_font.py` 输出后的回读验证。

### 2.3 Range List 示例

覆盖中/日/韩所需的最小 range 集：

| start_cp | end_cp | 名称 | 字数 |
|----------|--------|------|------|
| 0x0020 | 0x00FF | ASCII + Latin-1 | 224 |
| 0x1100 | 0x11FF | 韩文 Jamo | 256 |
| 0x3130 | 0x318F | 韩文兼容 Jamo | 96 |
| 0x3400 | 0x4DBF | CJK 扩展 A | 6,592 |
| 0x4E00 | 0x9FFF | CJK 统一汉字 | 20,992 |
| 0xAC00 | 0xD7A3 | 韩文音节 | 11,172 |
| 0xF900 | 0xFAFF | CJK 兼容表意文字 | 512 |
| 0xFF00 | 0xFFEF | 半角/全角形式 | 240 |

**glyph 索引算法**：

```c
const uint8_t *cjk_get_glyph(uint32_t cp) {
    for (int i = 0; i < range_count; i++) {
        if (cp >= ranges[i].start_cp && cp <= ranges[i].end_cp) {
            uint32_t offset = (cp - ranges[i].start_cp) * FONT_CJK_BYTES;
            return glyph_base + offset;
        }
    }
    return blank_glyph; // 替代：全零（空格）
}
```

### 2.4 常量

```c
#define FONT_CJK_W      16
#define FONT_CJK_H      16
#define FONT_CJK_BYTES  32
```

### 2.5 生成方式

**CJK.DAT 源**：GNU Unifont `.hex` 文件（https://unifoundry.com/unifont/）
  ```bash
  python3 tools/naiz_font/gen_cjk_font.py /tmp/unifont_jp.hex -o tools/naiz_font/CJK.DAT
  ```

**CJK.DAT 工具**：`tools/naiz_font/gen_cjk_font.py`

**FONT.DAT（ASCII）源**：Uni1-VGA16 (`/usr/share/consolefonts/Uni1-VGA16.psf.gz`)
  ```bash
  zcat /usr/share/consolefonts/Uni1-VGA16.psf.gz > /tmp/uni1vga16.psf
  python3 tools/naiz_conv/psf2font.py --ascii-all /tmp/uni1vga16.psf tools/naiz_font/FONT.DAT
  ```

**FONT.DAT 工具**：`tools/naiz_conv/psf2font.py`

> **规范来源**：ASCII 字体源固定为 IBM VGA 改进位图字体 Uni1-VGA16，不得使用 TrueType 渲染替代（`gen_font.py` 已标注废弃/实验性）。详细理由见 `devdocs/0.1版开发文档总结.html#doc-11`。

**流程**：
1. 从 `.hex` 或 `.psf` 中提取字形
2. 按 range 分组，密集排列，写入 CJK.DAT 或 FONT.DAT
3. 后验证：`glyph_offset == 10 + range_count × 16`

---

## 3. TXA 文本包格式

### 3.1 文件布局

```
[Header]
  magic     "TXA1" (4B)
  count     uint16 (2B)    ← 文本条目总数
  hdr_sz    uint16 (2B)    ← header 总大小（含本字段）

[Index Table: count × 4 bytes]
  Each entry:
    offset   uint32 (4B)   ← 该条目 UTF-8 字符串在 [String Pool] 中的偏移

[String Pool]
  <entry 0 bytes> [无终止符]
  <entry 1 bytes>
  ...
```

- 字符串无 `\0` 终止：长度由 `entry[n+1].offset - entry[n].offset` 推算
- 最后一条的长度由文件总大小减去其 offset 得到
- 文本编码：UTF-8（无 BOM）

### 3.2 源文件格式（工具链输入）

```
idx<TAB>text
```

示例：

```
0	これは…
1	Naiz は美少女ゲームエンジンです。
2	ねぇ、ちょっと…
```

工具：`tools/naiz_build/text_pack.py`

### 3.3 API

```c
// text.h
int  text_table_load(const char *path);   // 返回条目数，-1 失败
void text_table_free(void);
const char *text_table_get(int idx);      // 返回 UTF-8 字符串，越界返回 NULL
```

### 3.4 目录结构

```
projets/<game>/
├── scene/
│   └── main.sca                ← 场景源（指令含 text 0, text 1...）
├── lang/
│   ├── zh/
│   │   └── main.txt            ← 中文文本源
│   ├── ja/
│   │   └── main.txt            ← 日文文本源
│   └── ko/
│       └── main.txt            ← 韩文文本源
```

构建后 HDI 目录结构：

```
LANG/zh.txa
LANG/ja.txa
LANG/ko.txa
LANGUAGE.DAT
```

---

## 4. LANGUAGE.DAT 语言配置

### 4.1 格式

```
[Header]
  magic     "LANG" (4B)
  lang_id   char[4] (4B)    ← 语言代码，空格填充

[Lang IDs 定义]
  "zh  " → 中文
  "ja  " → 日文
  "ko  " → 韩文
  "en  " → 英文（fallback）
```

### 4.2 加载流程

```c
void text_init(void)
{
    char lang_id[4];
    int i, len;
    read_language_dat("LANGUAGE.DAT", lang_id);  // 读语言配置
    for (len = 0; len < 4 && lang_id[len] && lang_id[len] != ' '; len++);
    char path[32];
    snprintf(path, sizeof(path), "LANG/%.*s.txa", len, lang_id);
    text_table_load(path);                    // 加载文本表
}
```

---

## 5. 渲染管线

### 5.1 draw_text_utf8

```c
void draw_text_utf8(const char *s, int x, int y, uint8_t color);
```

| 入参 | 说明 |
|------|------|
| s | UTF-8 字符串 |
| x, y | 左上角 VRAM 坐标 |
| color | 前景色 palette index |

**逻辑**：

```
const unsigned char *p = (const unsigned char *)s;
const unsigned char *end = p + strlen(s);
while (p < end):
    cp = text_decode_utf8(&p, end)     // 复用 text.c 解码器
    if cp < 0x80:
        glyph = font_get_glyph(cp)     // 8×16 ASCII
        draw_glyph(glyph, x, y, color)
        x += 8
    else:
        glyph = cjk_get_glyph(cp)      // 16×16 CJK
        draw_glyph_16x16(glyph, x, y, color)
        x += 16
```

### 5.2 draw_glyph_16x16

#### 5.2.1 预展开优化

应用 B02 §7.7 批量写入优化，避免逐像素 `pset()`。monochrome 1bpp → 256-color 8bpp 预展开：

```
输入：1 byte = 8 pixel bits
输出：8 bytes = 8 pixel indices（0 = 背景色, color = 前景色）
```

#### 5.2.2 算法

采用 B02 §7.7 相同的 bank 边界切割块写入。字形 16×16 像素跨越 VRAM bank 边界时（在行 51/102/153/...附近），自动分块：

```c
void draw_glyph_16x16(const uint8_t *glyph, int x, int y, uint8_t color)
{
    uint8_t buf[16 * 16];
    int row, i, j, bank, bank_end, chunk, len, addr, end, vp;

    // Step 1: 预展开 monochrome → 256-color
    for (row = 0; row < 16; row++) {
        uint16_t word = (glyph[row * 2] << 8) | glyph[row * 2 + 1];
        for (j = 0; j < 16; j++)
            buf[row * 16 + j] = (word & (1u << (15 - j))) ? color : 0;
    }

    // Step 2: 块写入（同 B02 §7.7 算法）
    for (row = 0; row < 16 && y + row < 400; row++) {
        addr = (y + row) * 640 + x;
        end  = addr + 16;
        i = row * 16;
        while (addr < end) {
            bank     = addr >> 15;
            bank_end = (bank + 1) << 15;
            chunk    = (end < bank_end) ? end : bank_end;
            len      = chunk - addr;
            *PEGC_BANK = (uint16_t)bank;
            vp = addr & (BANK_SZ - 1);
            for (j = 0; j < len; j++)
                VRAM_WIN[vp + j] = buf[i + j];
            addr = chunk;
            i += len;
        }
    }
}
```

**加速比**：~8–10× 相对逐像素 pset，且满足 486/33MHz 帧预算（一行 40 CJK 字 < 2ms）。

---

## 6. 文本表与场景 VM 的接口

### 6.1 op_text（scene.c）

**【当前实现】** — `scene.c` 中 `op_text` 使用硬编码的中文文本表：

```c
/* text_table[] 在 scene.c 中静态定义，内容为中文 */
case 0x11:  // text
    draw_text(text_table[num].str, 0,
              LAYER_DIALOG_X + LAYER_DIALOG_INDENT, LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y,
              LAYER_DIALOG_W - LAYER_DIALOG_INDENT - LAYER_DIALOG_RIGHT_INDENT,
              LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y + 60, 0, 7);
```

**【预留设计】** — 迁移至 TXA 加载后：

```c
case 0x11:  // text
    uint16_t idx = fetch_uint16(pc);
    const char *str = text_table_get(idx);
    if (str) draw_text_utf8(str, 0, x, y, max_w, max_y, 0, TEXT_COLOR);
```

同时移除 `scene.c` 中的 `static TextEntry text_table[MAX_TEXT_ENTRIES]` 和 `text_table_init()`，改为在 `text.c` 中实现 `text_table_load()` / `text_table_get()` / `text_table_free()`（API 见 §3.3）。`op_text()` 的字符串来源从 `text_table[num].str` 改为 `text_table_get(num)`。

### 6.2 场景字节码不变

SCENE.DAT 字节码格式不改变，`text 0`、`text 1`、`charname` 等现行 opcode 不变。只改变取字符串的来源——从硬编码数组变为 `text_table_get(idx)`。

---

## 7. 内存与存储明细

> 设计：启动时语言选择 → 仅加载选定语言的 TXA，其余语言仅存于 HDI，不占用内存。

### 7.1 固定内存（语言无关，始终加载）

| 项目 | 大小 | 说明 |
|------|------|------|
| CJK.DAT（全字库） | ~1,100 KB | 34,000 字形 × 32 字节 + range list |
| SCENE.DAT（字节码） | ~100 KB | 一份，语言无关 |
| FONT.DAT（ASCII 8×16） | ~4 KB | UI 提示专用 |
| 引擎代码 + 堆栈 | ~200 KB | text.c, scene.c, render.c 等 |
| **固定合计** | **~1,404 KB** | |

### 7.2 TXA 文本内存（按语言，仅加载一种）

> 估算基于 UTF-8 存储：中文平均 ~2.9 B/字，日文 ~3.6 B/字（含送假名），韩文 ~3.8 B/字（含助词）。单条文本平均 20 CJK 字 + 标点。

| 游戏规模 | 条目数 | 中文 TXA | 日文 TXA | 韩文 TXA |
|---------|-------|---------|---------|---------|
| 演示 | 500 | ~48 KB | ~60 KB | ~63 KB |
| 中型 | 3,000 | ~276 KB | ~348 KB | ~366 KB |
| 完整游戏 | 6,000 | ~551 KB | ~692 KB | ~727 KB |

**韩文 > 日文 > 中文 的原因**：

- 韩文助词/语尾更丰富（은/는, 이/가, 을/를 等），同义表达 UTF-8 字节数多 20–30%
- 日文有送假名（食べる → たべる），比纯中文词多 ~25%
- 中文词最短（二字词居多，无词形变化）

### 7.3 峰值内存（4MB 实机验证）

```
最坏情况（完整游戏 6,000 条，韩文）：
  固定 1,404 KB + TXA 727 KB = 2,131 KB  ← 运行时峰值
  DOS/4GW + VEM486 空余           ~1.9 MB  ← 堆栈 + 临时分配
  总 RAM 4 MB                     = 4,096 KB

结论：4MB 实机绰绰有余，空余 ~1.9 MB。
```

### 7.4 切换语言

```
text_table_free()          → 释放当前 TXA（如 727 KB）
text_table_load("ko.txa")  → 重新分配 727 KB
峰值不增加（同一块 buffer 复用）。
```

### 7.5 HDI 存储

| 项目 | 大小 | 备注 |
|------|------|------|
| CJK.DAT | 1,100 KB | 所有语言共享 |
| FONT.DAT | 4 KB | ASCII 后备 |
| zh.txa + ja.txa + ko.txa | ~180 KB | 三份独立文件 |
| SCENE.DAT | 50–100 KB | 一份 |
| LANGUAGE.DAT | 8 B | 语言配置 |
| **HDI 合计** | **~1.4 MB** | |

### 7.6 渲染耗时（估计，486/33MHz）

| 操作 | 耗时 |
|------|------|
| 1 个 CJK 字（预展开 + blit） | < 0.05 ms |
| 1 行 40 CJK 字 | < 2 ms |
| 4 行对话刷新 | < 8 ms |
| 帧预算（60fps） | 16.6 ms |

---

## 8. 文件清单

| 文件 | 类型 | 说明 | 实现状态 |
|------|------|------|---------|
| `core/lib/cjk.h` | 引擎 | CJK 字库查询 API | ✅ 已实现 |
| `core/lib/cjk.c` | 引擎 | `cjk_init()`, `cjk_get_glyph()` | ✅ 已实现 |
| `core/lib/font.h` | 引擎 | 不变，继续使用 | ✅ 已实现 |
| `core/lib/font.c` | 引擎 | 不变 | ✅ 已实现 |
| `core/engine/render.h` | 引擎 | `draw_glyph_cjk()` 等 | ✅ 已实现 |
| `core/engine/render.c` | 引擎 | UTF-8 感知渲染（整合在 `draw_text()`） | ✅ 已实现 |
| `core/engine/text.h` | 引擎 | `text_table_load()/free()/get()` | ❌ 预留 |
| `core/engine/text.c` | 引擎 | TXA 解析 + 文本表管理 | ❌ 预留 |
| `core/engine/scene.c` | 引擎 | `op_text` 当前使用硬编码中文文本表 | ✅ 已实现（硬编码） |
| `core/engine/main.c` | 引擎 | 初始化序列加入 `cjk_init` | ✅ 已实现 |
| `tools/naiz_font/gen_cjk_font.py` | 工具 | Unifont → CJK.DAT | ✅ 已实现 |
| `tools/naiz_build/text_pack.py` | 工具 | UTF-8 源文本 → TXA 二进制 | ❌ 预留 |
| `makegame.sh` | 构建 | 集成 CJK.DAT + TXA 注入 | ❌ 预留 |

---

## 9. 向后兼容

| 场景 | 兼容性 |
|------|--------|
| 无 CJK.DAT | `cjk_init` 失败，回退显示 ASCII 版 |
| 无 TXA 文件（当前状态） | 保持现有硬编码中文文本表 |
| 纯 ASCII 项目 | 不生成 CJK.DAT、不调 `text_table_load`即可 |
| 旧 SCENE.DAT | 字节码格式不变，`text 0` 等 opcode 含义不变 |

---

## 10. 修订历史

| 版本 | 日期 | 修改内容 |
|------|------|----------|
| 1.0 | 2026-06-11 | 初版：CJK.DAT 字库格式、TXA 文本包、LANGUAGE.DAT、渲染管线、内存预算 |
| 1.1 | 2026-06-12 | 状态更新为"部分实现"：标记 CJK 字库 + CJK 渲染为 ✅ 已实现；TXA 多语言 + LANGUAGE.DAT 为 ❌ 预留；更新 §1.1、§6.1、§8 文件清单 |
