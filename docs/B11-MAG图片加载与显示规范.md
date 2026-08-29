# B11 — MAG 图片加载与显示规范

> **状态**：设计文档
> **创建**：2026-06-09
> **依赖**：`B02-显示管线规范.md`（VRAM 布局、调色板）、`B10-键盘交互与文本表设计.md`（对白颜色保护）
> **参考**：love es×××× `vram.c:VramDrawGrayscale()`（VRAM 内联 blit 方式）
> **关联开发计划**：`devdocs/0.1版开发文档总结.html#doc-12`

本文定义 Naiz 引擎的 MAG 图片加载、归档存储、调色板管理、VRAM 输出及场景指令的完整技术规范。

---

## 1. MAG 格式概述

MAG (MAKI02) 是日本 PC-98 平台的主流图像格式，由 Woody Rinn 开发。格式支持 16 色和 256 色：

| 组件 | 16 色 | 256 色 |
|------|-------|--------|
| 压缩像素数据 | 4bpp (Flag A/B + color stream) | 8bpp |
| 嵌入式调色板 | 16 组 GRB 三元组 | 最多 256 组 |
| 屏幕模式 | screen_mode=0x00 (bit 7=0) | screen_mode=0x80 (bit 7=1) |
| 尺寸信息 | 左上/右下边界，支持非全屏 | 同左 |

MAG 解码器已实现于 `core/lib/mag.c`，API：`mag_decode(data, size, &img)` → `MagImage *`。

**本引擎使用 256 色模式**（PEGC, bpp=8, num_colors≤256）。

---

## 2. 归档格式：IMAGE.DAT

### 2.1 设计目标

- 将多张 MAG 文件打包为单一归档，减少 HDI 根目录条目
- 引擎通过逻辑 ID 直接索引，O(1) 查找
- 构建时由 SQLite 映射表驱动，运行时无 SQLite 依赖

### 2.2 二进制结构

```
偏移      大小      字段                        说明
─────────────────────────────────────────────────────────
0x00      4         count : uint32 LE            归档文件数
0x04      20×N      TOC[N]                       按 logical_id 顺序排列
          12        TOC[i].name                   8.3 文件名，\0 填充（调试用）
          4         TOC[i].offset : uint32 LE    MAG 数据起始偏移
          4         TOC[i].size : uint32 LE      MAG 数据字节数
TOC_end   variable  data[]                       原始 MAG 字节拼接
```

**约束**：
- TOC 条目数组索引 = logical_id（引擎通过 `id` 直接数组寻址）
- `count=0` 为合法值，表示空 IMAGE.DAT
- 文件字节序：全部 LE（PC-98 x86 原生）
- TOC 条目数 = count
- `data[]` 区紧接 TOC 之后，各文件按 TOC 条目顺序连续排列

### 2.3 查找算法

引擎侧 `image_load(id)` 查找：

```
1. id >= count → return NULL
2. entry = TOC[id]
3. buf = data_base + entry.offset
4. mag_decode(buf, entry.size, &img)
5. return img
```

无需文件名匹配——`id` 即 TOC 数组索引。

---

## 3. 素材映射：ASSETS.DB + characters.yaml

### 3.1 图像映射表：ASSETS.DB

ASSETS.DB 只保留 `img_map` 表，管理图像资源索引：

```sql
CREATE TABLE img_map (
    id       INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    type     TEXT DEFAULT 'IMG'      -- 'IMG'=背景/图片, 'SPR'=精灵
);
```

| 列 | 说明 |
|----|------|
| `id` | logical_id，场景 `bg`/`char` 命令参数值 |
| `filename` | 素材路径，相对于 `projects/<game>/` |
| `type` | `'IMG'`=图片（加载上传播色板）, `'SPR'`=精灵 |
| `name` | 引擎脚本中使用的键（如 `bg splbg` 中的 `splbg`） |

### 3.2 角色与表情：characters.yaml

角色定义和表情映射不再使用 SQLite，改为 YAML 文件：

```yaml
# projects/<game>/characters.yaml
characters:
  - id: 7
    key: scene
    name: Scene
    type: system       # system: NB 系统角色（scene/menu）
  - id: 9
    key: fei
    name: Fei
    type: story        # story: 故事角色

char_expressions:
  - char_id: 9
    expr: normal
    asset_id: 1        # 指向 img_map.id
```

### 3.3 使用方式

```bash
# 向 img_map 添加图像资源
sqlite3 projects/demo-a2/ASSETS.DB <<'SQL'
INSERT INTO img_map VALUES (0, 'images/splbg.MAG', 'IMG', 'splbg');
INSERT INTO img_map VALUES (1, 'images/fei-normal.MAG', 'SPR', 'fei-normal');
SQL

# 角色定义在 characters.yaml 中直接编辑
```

`pack_images.py` 读取 `img_map` 将列出的文件打包为 `IMAGE.DAT`，同时对 `characters.yaml` 中每个角色的多套表情自动做 **y≥280 一致性校验**（见 `C03-立绘与角色.md §3.5`）。

---

## 4. 引擎图像 API

**文件**：`core/engine/image.c` + `image.h`

### 4.1 `image_init(const char *path)`

```
int image_init(const char *path);
```

- 打开 `path`（通常为 `"IMAGE.DAT"`）
- `fread` 全文件到内存缓冲区
- 解析 header → 获取 `count`、TOC 数组指针、data 基址
- 文件不存在时返回 0（不计为错误，引擎正常继续）
- 返回值：0=成功, ≠0=失败

### 4.1a `mag_read_palette()` (新增，2026-06-18)

```
int mag_read_palette(const uint8_t *data, int size,
                     uint8_t pal_r[256], uint8_t pal_g[256], uint8_t pal_b[256]);
```

轻量函数，只解析 MAG header + palette 段，不做像素解码。返回 palette 颜色数（16–256），失败返回 -1。

用于 `image_init()` 启动时的共享调色板一致性校验（见 §12.7）。

### 4.2 `image_load(unsigned short id)`

```
MagImage *image_load(unsigned short id);
```

1. `id >= count` → 返回 NULL
2. 取 `TOC[id].offset`, `TOC[id].size`
3. `mag_decode(data + offset, size, &img)`
4. 若 `img->num_colors == 16 && img->bpp == 4`：
   - 调用 `image_set_palette(img)`（见 §5）
5. 返回 `img`

### 4.3 `image_close(void)`

```
void image_close(void);
```

释放 `image_init()` 分配的内存缓冲，清理模块内部状态。

---

## 5. 调色板管理

### 5.1 PC-98 256 色调色板约束

引擎初始化阶段设置的默认调色板（256c 模式下，MAG 图像可有 1–256 色）：

| 索引 | 颜色 | 用途 |
|------|------|------|
| 0 | 黑 `#000000` | 初始对话框背景 |
| 7 | 白 `#FFFFFF` | 对白文字、对话框边框 |
| 15 | 黑 `#000000` | 精灵透明色（`vram_blit_sprite` 跳过） |
| 248 | 黑/蓝（动态） | 对话框底色（`dlgstyle` 切换） |
| 249–255 | — | 备用 UI 色（预留） |

### 5.2 `image_set_palette()` — 安全覆盖策略

```c
void image_set_palette(const MagImage *img);
```

遍历 MAG 的调色板，**逐一调用 `hal_set_palette()` 更新硬件调色板**：

```c
void image_set_palette(const MagImage *img)
{
    int i, nc = img->num_colors;
    if (nc > 256) nc = 256;
    for (i = 0; i < nc; i++) {
        if (img->is_sprite && (i == 7 || i == 15)) continue;
        if (i == 7 || i == 15 || i >= 248) continue;
        hal_set_palette(i, img->palette_r[i],
                        img->palette_g[i], img->palette_b[i]);
    }
}
```

| 图像类型 | 行为 | 说明 |
|----------|------|------|
| **BG**（非 sprite） | 应用全部 256 色调色板 | 背景图像 palette 直接写入硬件，包括索引 7/15/248–255 |
| **SPR**（sprite） | 跳过索引 7、15 | 保留引擎预设白色（7=文字色，15=透明色） |

> **注意**：BG 图像也写入索引 248–255。这意味着 250/251（菜单色）会在每次 `bg` 命令加载背景时被 MAG 的 palette 覆盖。菜单模块（`nb.c`）在打开时通过 `menu_save_item_palette()` 保存并重设 250/251，关闭时恢复。见 §12 的构建时保护与运行期 save/restore 配合机制。

**设计理由**：
- BG 图像部分使用索引 7/15 作为真实颜色（如白色背景），必须应用完整 palette 才能正确显示
- SPR 跳过 7/15：保留引擎白色用于 sprite 透明（索引 15）和文字（索引 7）
- 256 色量化后 BG 的 palette[248–255] 在构建时已被 `pack_images.py` 清空或 remap，因此写入它们不会破坏 UI 色（见 §12.2）

### 5.4 bg 调色板时序（强制执行）

场景切换或 `bg` 命令加载新背景时，执行顺序**必须严格遵循**：

```
image_set_palette(img)    ← 第1步：应用 palette
vram_blit(img, 0, 0)      ← 第2步：写入像素
layer_redraw_sprites()     ← 第3步：用新 palette 重绘所有精灵
/* 恢复对话框底色 */
hal_set_palette(248, ...)  ← 第4步：因步骤1覆盖了 248，需恢复
layer_capture_bg()         ← 第5步：保存背景快照
```

**为什么 palette 先于像素（第1步→第2步）**：
- 若先写入像素再改 palette，屏幕上已有像素的索引对应的是旧 palette 值 → 颜色瞬间跳变，肉眼可见为"闪烁"
- 先改 palette 再写入像素 → 新像素写入时直接匹配新 palette → 无颜色跳变

**为什么 palette 后需要恢复 248（第4步）**：
- `image_set_palette()` 对所有非 SPR 图像写入全部 256 个条目 → 对话框底色（248）被覆盖
- 调用者需要根据 `g_dialog_style` 重新设置 248 的颜色（黑/蓝）

**Agent 强制规则**：任何实现"加载图像"功能的代码必须遵守 palette→pixels→sprites→dialog 的顺序。不得在 palette 设置完成之前写入 VRAM。精灵必须在 palette 更新后重绘，否则颜色与背景不同步。

### 5.3 调色板颜色还原

MAG 调色板在解码阶段已由 `expand_comp()` 将限定比特数的分量扩展为 8-bit：5-bit 用 `(v<<3)|(v>>2)` 重叠复制（`0x10` → `0x84`），4-bit 用 `(v<<4)|(v>>4)`（`0xB` → `0xBB`），3-bit 因右移位数不足改用 MSB-first 循环复制以与 `mag_codec.py` 一致（`5` → `0xB6`）。`hal_set_palette()` 将 8-bit 分量直写 NP2kai 的 `anareg[48+]`，经 `pal_make9821()` 转为 RGB565。端到端无精度损失。

---

## 6. VRAM 批量输出：`vram_blit()`

**文件**：`core/engine/render.c` + `render.h`

```c
void vram_blit(const MagImage *img, int dst_x, int dst_y);
```

### 6.1 算法（PEGC 256c packed-pixel）

通过 PEGC bank 窗口（`0xE0004` + `0xA8000`）逐像素写入，每字节 = 1 个像素（8-bit 调色板索引）：

```c
void vram_blit(const MagImage *img, int x, int y)
{
    int py, px, addr;
    for (py = 0; py < img->height && y + py < 400; py++) {
        for (px = 0; px < img->width && x + px < 640; px++) {
            addr = (y + py) * 640 + (x + px);
            *PEGC_BANK = (uint16_t)(addr >> 15);
            VRAM_WIN[addr & (BANK_SZ - 1)] =
                img->pixels[py * img->width + px];
        }
    }
}
```

### 6.2 性能

- 全屏 640×400 背景：256,000 像素写入，每像素 1 次 bank 端口写 + 1 次 VRAM 写
- 当前实现逐像素 bank 切换（每像素 1 次端口 I/O）
- 后续可按 §7.7 算法优化为按行分块（全屏可从 256,000 次降至 ~9 次 bank 选择）

### 6.3 颜色索引直接映射

PEGC 256c 模式下，MAG 解码后的 `pixels[]` 值为 0–255 的 8-bit 调色板索引，**直接对应硬件调色板索引**——无需额外颜色映射或位平面拆分。

### 6.4 Sprite Blit：`vram_blit_sprite()`

**文件**：`core/engine/render.c` + `render.h`

```c
void vram_blit_sprite(const MagImage *img, int dst_x, int dst_y,
                      uint8_t transparent_idx, int mirror, int clip_h);
```

#### 6.4.1 算法（PEGC 256c packed-pixel + 水平翻转 + 裁剪）

```c
void vram_blit_sprite(const MagImage *img, int x, int y,
                      uint8_t transparent_idx, int mirror, int clip_h)
{
    int py, px, addr, sx;
    uint8_t c;
    int max_h = (clip_h > 0 && clip_h < img->height) ? clip_h : img->height;
    for (py = 0; py < max_h && y + py < 400; py++) {
        for (px = 0; px < img->width && x + px < 640; px++) {
            c = img->pixels[py * img->width + px];
            if (c == transparent_idx) continue;
            sx = mirror ? (img->width - 1 - px) : px;
            addr = (y + py) * 640 + (x + sx);
            *PEGC_BANK = (uint16_t)(addr >> 15);
            VRAM_WIN[addr & (BANK_SZ - 1)] = c;
        }
    }
}
```

**关键设计点**：
- 透明像素**完全跳过** VRAM 读-改-写——保留 VRAM 原有值（即背景或对话框）
- `transparent_idx` 由 `MagImage.is_sprite` 推导，引擎约定为 **索引 15**
- 对于 16 色 sprite，15 个实际颜色（索引 0–14）+ 1 个透明色（索引 15）
- 精灵可在任意位置 (`dst_x`, `dst_y`) 绘制

详见 `C03-立绘与角色.md` 的制作者透明色约定。

---

## 7. 场景指令：`bg`（NB 命令）

### 7.1 字节码定义

| 字段 | 值 |
|------|-----|
| Opcode | `0x30` |
| 字节数 | **3**（1 字节 opcode + 2 字节 operand） |
| Operand | `uint16 LE` — IMAGE.DAT 中的 logical_id |
| 行为 | 加载 ID 对应的 MAG → 设调色板（`image_set_palette`）→ blit 全屏 → 重绘精灵 → 恢复对话框底色 → 保存背景快照 |

### 7.2 实现

实际引擎中，背景加载由 NB 脚本的 `bg` 命令触发（`core/engine/nb.c:cmd_bg`）：

```c
static void cmd_bg(int argc, const char **argv, const char *cmd_name)
{
    int id = resolve_asset(argv[0]);
    MagImage *img = image_load(id);
    if (!img) return;
    /* Apply palette FIRST to avoid color flash */
    image_set_palette(img);
    vram_blit(img, 0, 0);
    layer_redraw_sprites();
    mag_free(img);
    /* Restore dialog palette index 248 */
    dlg_update_palette();
    layer_capture_bg();
}
```

`bg` 命令不再自动绘制对话框。背景加载后调用 `layer_capture_bg()` 保存 256KB VRAM 快照。
对话框延迟到首次 `dialog_show()` 时通过 `layer_dialog_open()` 绘制，**确保立绘在对话框之下**。
完整渲染顺序：背景 → 立绘 → 对话框 → 文字（五趟，含菜单为第六趟）。详见 `B12-VRAM渲染策略.md`。

### 7.3 旧 MHVN98 兼容性

opcode `0x30` 是 MHVN98 规范中的背景加载指令，当前 NB 引擎通过 `bg` 命令实现，不再使用二进制 opcode 分发表。

---

## 8. 初始化序列（更新后）

参见 `B02-显示管线规范.md` §2。`image_init()` 位于调色板设置后、场景加载前：

| 序 | 调用 | 串口标记 |
|----|------|----------|
| 1 | `hal_init()` | — |
| 2 | `font_init("FONT.DAT")` | — |
| 3 | `cjk_init("CJK.DAT")` | — |
| 4 | `kbd_init()` | — |
| 5 | `video_init()` | Vid OK |
| 6 | `hal_set_palette(0/7/15/248, ...)` + `fill_rect(0,0,640,400,0)` + `video_check_palette()` | Pal OK |
| 7 | **`image_init("IMAGE.DAT")`** | **Img OK** |
| 8 | `nb_init()`（NB 脚本引擎初始化，加载 logo.nb） | Scene OK |
| 9 | `nb_process()` 循环 | — |

> **注意**：当前引擎启动调色板设 0=黑, 1=蓝, 2=绿, 3=红, 7=白, 15=白, 248=黑；全屏填充为黑底而非蓝底。`image_init()` 时会做 palette 一致性校验（`mag_read_palette()` 遍历全部 TOC 条目）。`bg` 命令不自动绘制对话框，对话框由首次 `dialog_show()` 通过 `layer_dialog_open()` 触发（见 `B15-图层渲染与换装机制.md` §3.1）。

---

## 9. 构建管线

```
makegame.sh build demo-a2
  │
  ├─ mag_convert.py                ← PNG → MAG（由 images.map 驱动）
  ├─ make -C core clean all        ← 编译引擎
  ├─ pack_images.py                ← ASSETS.DB → IMAGE.DAT
  │   1. 打开 ASSETS.DB，读取全部 img_map
  │   2. 解码全部 MAG → 收集所有非透明像素
  │   3. 构建全局共享调色板
  │      a. PIL median-cut 量化 2079+ 色 → 246 色
  │      b. merge_similar_palette() 近色合并降噪
  │      c. 插入 10 个保护位 (7/15/248–255)
  │   4. 全部图像（BG + SPR）统一 remap 到共享调色板
  │   5. 后校验 verify_shared_palette()
  └─ cp → games/demo-a2/
```

`pack_images.py` 内部逻辑：

```python
def pack_images(project_dir):
    rows = db.execute('SELECT id, filename, type FROM img_map ORDER BY id').fetchall()
    image_data = load_all_mags(project_dir, rows)    # 解码全部 MAG
    shared_pal = build_shared_palette(image_data)      # PIL 量化 → 256 色共享调色板

    for id, filename, type, raw, result in image_data:
        pixels, w, h, old_pal = result
        new_pixels = remap_pixels_to_palette(          # 最近色重映射
            pixels, w, h, old_pal, shared_pal,
            transparent_idx=15 if is_sprite else None,
            protected_indices=PROTECTED_IDX)
        mag = encode_mag(new_pixels, w, h, shared_pal,  # 所有 MAG 用同一调色板编码
                         user_string=b"sprt\x1a" if is_sprite else b"naiz\x1a",
                         bpp=8, filter_white=False)
        toc.append((id, mag))

    write_image_dat(toc)                                # 写 TOC + 数据
    verify_shared_palette(out_path)                     # 后校验
```

---

## 10. 与其他文档的耦合

| 文档 | 关系 |
|------|------|
| `B02-显示管线规范.md` | VRAM 平面地址（B/R/G/E）、调色板端口（0xA8-0xAE）、像素图元（`fill_rect`, `vram_blit` 等） |
| `B10-键盘交互与文本表设计.md` | 对白调色板保护：索引 7（白）= 文字+提示、索引 8（灰）= Ctrl 提示 |
| `C01-引擎基本概念.md` | 制作者视角的对白/背景概念 |
| `devdocs/0.1版开发文档总结.html#doc-01` | MAG 格式完整技术规范 |
| `devdocs/0.1版开发文档总结.html#doc-12` | 实施计划、测试步骤 |
| `C03-立绘与角色.md` | 立绘制作与透明色约定 |

---

## 11. Sprite / 立绘加载

### 11.1 引擎侧检测：User String 约定

MAG 文件头部的 16 字节 user 域（`0x0C-0x1B`, `\x1A` 终止，固定 `MagImage[12]` 字段）用于标识图像类型：

| User String | 图像类型 | 引擎行为 |
|-------------|----------|----------|
| `"naiz\x1a"` | 背景/全屏 | `image_set_palette()` + `vram_blit()` |
| `"sprt\x1a"` | 立绘/精灵 | **不调** `image_set_palette()` + `vram_blit_sprite(idx=15)` |

**mag.c 修改**：`mag_decode()` 解析 user string → 设置 `MagImage.is_sprite` 标志位。引擎在 `image_load()` → `mag_decode()` 之后检查此字段即知是否需要透明 blit。

### 11.2 MagImage 结构更新

```c
typedef struct {
    int      width;
    int      height;
    uint8_t *pixels;
    uint8_t  palette_r[256];
    uint8_t  palette_g[256];
    uint8_t  palette_b[256];
    int      num_colors;
    int      bpp;
    uint8_t  is_sprite;      /* NEW: 1 = sprite (index 15 transparent) */
} MagImage;
```

### 11.3 共享调色板原则

Sprite 加载时**不调用** `image_set_palette()`——精灵与背景共享同一套 256 色调色板。这是设计选择：

| 原则 | 解释 |
|------|------|
| 全局共享 | 整个场景（背景+精灵+对话框）共用 256 色调色板 |
| 精灵不设调色板 | `image_load()` 检查 `img->is_sprite` → 跳过 `image_set_palette()` |
| 背景先加载 | `bg` 命令加载背景时设置全场景调色板 |
| 精灵后加载 | `char` 命令加载精灵时只写像素到 VRAM，以背景调色板渲染 |

### 11.4 image_load() 分支逻辑

```c
MagImage *image_load(unsigned short id)
{
    // ... TOC lookup + mag_decode ...

    if (!img->is_sprite) {
        image_set_palette(img);       /* 背景：设置全场景调色板 */
    }
    /* 精灵：跳过 palette 设置，共享背景调色板 */

    return img;
}
```

### 11.5 NB 场景指令：`char`（替换旧 `op_body` / `op_face` / `op_mirror`）

NB 脚本使用 `char` 命令替代旧 `op_body`/`op_face`/`op_mirror` 等二进制 opcode：

```nb
char fei l face     # 左位脸部立绘（自动选择 face 表情）
char ira c body     # 中位全身立绘
char(hideall)       # 隐藏全部立绘
```

引擎内部由 `cmd_char()` → `layer_sprite_show()` / `layer_sprite_face()` / `layer_sprite_replace()` 处理。
精灵水平镜像由 `char` 命令的位置参数（`l`/`c`/`r`）隐式决定（左位镜像），无需独立 `mirror` 指令。
详见 `docs/C03-立绘与角色.md`。

### 11.6 渲染顺序（四趟）

```
1. vram_blit(bg, 0, 0)                ← 背景全屏（bg）
2. vram_blit_sprite(sprite, x, y, 15) ← 立绘（char）
3. scene_draw_dialog()                 ← 对话框（首次 dialog_show → layer_dialog_open）
4. draw_text()                         ← 文字（dialog_show 翻页）
```

立绘在对话框之下，文字始终在最前面。对话框延迟到首次 `dialog_show()` 时绘制。
精灵更换（`face`/`replace`/`hide`）通过 `bg_snapshot` 恢复背景，避免全屏重绘。
详见 `B15-图层渲染与换装机制.md`。

### 11.7 mag_convert.py 精灵转换

```bash
python3 -m tools.naiz_conv.mag_convert character.png -o CHR_HIME.MAG --sprite --256
```

- 读取 RGBA 通道 → alpha<128 区域 = 透明
- 透明区映射为索引 15（合成亮洋红 → 量化 → 调换索引）
- **不 resize**（保持精灵原始尺寸）
- 写入 `"sprt\x1a"` user string

### 11.7 精灵镜像

NB 脚本中，精灵镜像由 `char` 命令的位置参数隐式决定：
- `l`（左位）→ `mirror=1`（角色面朝右，朝向屏幕中央）
- `c`（中位）→ `mirror=0`
- `r`（右位）→ `mirror=0`

旧 `op_mirror` opcode（`0x34`）已被废弃。

**素材约定**：所有立绘假定为**右站位**（角色面朝左/中，适合右位显示）。左位显示时引擎自动镜像，角色即面向右（朝向中），与右站位形成对称。

**场景脚本示例**：
```nb
char fei l face       # 左立绘（自动镜像）
char ira c body       # 中立绘（不镜像）
char neon r body      # 右立绘（不镜像）
```

---

## 12. 调色板预留机制

256 色模式下，所有图像像素 + UI 元素共享同一个 256 色调色板。为避免 UI 色（对话框底色、透明色、文字色）与图像像素冲突，引擎采用**三段预留机制**。

### 12.1 动机

对话框底色使用 palette index 248（以前用 index 8）。如果背景图或精灵的像素数据使用了相同的索引，切换对话框颜色（如黑→蓝）会导致图像对应区域也变色。

```
背景图 palette[8] = 深褐色                    精灵 palette[15] = 紫红色
          ↓  index 8 被改为蓝色 (对话框蓝底)            ↓  index 15 被引擎跳过 (透明标记)
背景中所有 palette[8] 像素变蓝 ✗              精灵透明区域显示背景 ✓
```

根本原因：**图像像素数据使用的索引与 UI 索引重叠**。

### 12.2 预留索引表

以下 10 个 palette 索引为 UI 专用，图像像素数据永远不会使用：

| 索引 | 默认色 | 用途 | 保护方 |
|------|--------|------|--------|
| 7 | `#FFFFFF` 白 | 文字、边框、提示文字 | `image_set_palette()` 跳过 |
| 15 | `#000000` 黑 | 精灵透明色（引擎 blit 时跳过） | `vram_blit_sprite()` + `image_set_palette()` |
| **248** | `#000000` 黑 | **对话框底色**（6 种样式动态改色） | `image_set_palette()` 跳过 |
| **250** | `#FFFFFF` 白 | **菜单文字色**（`nb.c` 初始化时注册，运行时不变） | `image_set_palette()` 跳过 + pack_images 全量 remap |
| **251** | `#FFFF00` 黄 | **菜单选中项色**（同上） | `image_set_palette()` 跳过 + pack_images 全量 remap |
| 249, 252–255 | — | 备用 UI 色（未来扩展） | `image_set_palette()` 跳过 |

**Agent 强制规则**：任何新增 UI 元素若需专属 palette 索引，必须同时（1）将索引加入 `PROTECTED_IDX` 列表（三份：`pack_images.py`、引擎 `image_set_palette()`、前处理工具）；(2) 重新构建所有图片数据以确保 evacuation；(3) 在 B02 §5.2 注册该索引的默认色值。

引擎侧初始值设置（`main.c`）：

```c
hal_set_palette(7,   0xFF, 0xFF, 0xFF);  // 白色
hal_set_palette(248, 0x00, 0x00, 0x00);  // 对话框底色（SOLID_BLACK）
```

`dlgstyle` 运行时通过 `dlg_update_palette()` 动态更新 index 248 的色值。

### 12.3 三段保护层次

预留机制在三个独立阶段实施，任何一个阶段都可阻止索引冲突：

```
阶段 1：素材生成期
  tools/naiz_conv/mag_convert.py --reserved     → MAG 文件的像素数据本身不含预留索引
  （根源防护：PNG → MAG 量化时就避开）

阶段 2：归档打包期
  tools/naiz_build/pack_images.py     → 所有图像（sprite + BG）remap 避开 PROTECTED_IDX
  （兼容防护：即使 MAG 碰巧用了预留索引，build 时也能 remap）

阶段 3：引擎运行期
  core/engine/image.c                 → image_set_palette() 跳过预留索引
  （最终防护：MAG 的 palette 值不会覆写 UI 色）
```

#### 12.3.1 阶段 1：`mag_convert.py --reserved`（推荐）

这是最干净的方案——在 PNG→MAG 转化时，量化器只使用 256−10 = 246 色，预留的 10 个索引在 palette 中置零。效果：

```
splbg.MAG 转化前：palette[7] = 深褐色, palette[15] = 暗紫色 ...
splbg.MAG 转化后：palette[7] = (0,0,0), palette[15] = (0,0,0) ... （像素已 remap）
```

#### 12.3.2 阶段 2：`pack_images.py` `PROTECTED_IDX`

当图像 remap 到 master palette 时，最近色搜索跳过 PROTECTED_IDX。该逻辑覆盖所有图像类型：精灵的 master palette 合并阶段将 PROTECTED_IDX 对应的源 palette 条目淘汰；而 BG 图像（独立 palette）在像素重映射时也将落入 PROTECTED_IDX 的像素逐点替换为最近的非保护色。精灵编码时 `filter_white`/`merge_similar_palette` 可能将非保护索引合并回保护索引，因此在编码后增加后检查，用 `remap_pixels_to_palette(pal, pal, transparent_idx=15, protected_indices=PROTECTED_IDX)` 清除残留。三段校验保证 IMAGE.DAT 中的数据永不包含预留索引：

```python
PROTECTED_IDX = {7, 15, 248, 249, 250, 251, 252, 253, 254, 255}

def _nearest(r, g, b):
    for i, (mr, mg, mb) in enumerate(master_palette):
        if i in PROTECTED_IDX:
            continue  # 跳过，找次近色
        ...
```

#### 12.3.3 阶段 3：引擎 `image_set_palette()`

```c
for (i = 0; i < nc; i++) {
    if (i == 7 || i == 15 || i >= 248)
        continue;  /* 永不覆写 */
    hal_set_palette(i, img->palette_r[i], ...);
}
```

### 12.4 `mag_convert.py --reserved` 详解

#### 12.4.1 CLI 参数

```
--reserved 7,15,248,249,250,251,252,253,254,255
```

逗号分隔的索引列表，量化完成后，`_remap_reserved_indices()` 将落在这些索引上的像素 remap 到 palette 中最接近的非预留色。

#### 12.4.2 `_remap_reserved_indices()` 函数

```python
def _remap_reserved_indices(pixels, palette, reserved):
    non_reserved = [i for i in range(len(palette)) if i not in reserved]
    # 对每个被预留的像素，在 non_reserved 中找最近色
    @lru_cache(maxsize=256)
    def nearest(idx):
        r, g, b = palette[idx]
        return min(non_reserved,
                   key=lambda ni: (r-palette[ni][0])**2
                                  + (g-palette[ni][1])**2
                                  + (b-palette[ni][2])**2)
    return [nearest(p) if p in reserved else p for p in pixels]
```

随后将预留索引的 palette 条目置零：

```python
for i in reserved:
    if i < len(palette):
        palette[i] = (0, 0, 0)
```

#### 12.4.3 对 `quantize_to_palette()` 的影响

使用 `--master-mag` 共享 palette 时，`quantize_to_palette()` 的最近色搜索也跳过预留索引：

```python
skip = set(reserved) if reserved else set()

def nearest(r, g, b):
    for i, (mr, mg, mb) in enumerate(master_rgb):
        if i in skip:
            continue
        ...
```

### 12.5 参考命令

#### 背景 MAG（抖动 + 256 色 + 预留）

```bash
python -m tools.naiz_conv.mag_convert assets/demo-a2/png/bg/splbg.png \
    -o projects/demo-a2/images/splbg.MAG \
    --dither --256 \
    --reserved 7,15,248,249,250,251,252,253,254,255
```

#### 精灵 MAG（无抖动 + 256 色 + 预留 + 透明色 index 15）

```bash
python -m tools.naiz_conv.mag_convert assets/demo-a2/png/char/fei-normal.png \
    -o projects/demo-a2/images/fei-normal.MAG \
    --sprite --256 \
    --reserved 7,248,249,250,251,252,253,254,255
```

> **注意**：精灵的 `--reserved` **不包含** 15，因为精灵需要在 index 15 存储透明标记。

#### 完整构建

```bash
# 从 PNG 生成 MAG
python -m tools.naiz_conv.mag_convert ... --reserved ...

# 从 MAG 打包 IMAGE.DAT
./makegame.sh build demo-a2

# 编译引擎 + 注入 HDI + 测试
bash core/build.sh
./makegame.sh make demo-a2      # 与上面 build 二选一（make 包含 build）
./makegame.sh test demo-a2 --serial
```

### 12.6 共享调色板

从 v3.0 起，`pack_images.py` 不再从 id=0 的单张背景提取主调色板，而是：

1. **解码全部 MAG**，收集所有非透明（index ≠ 15）像素的 RGB 值
2. **PIL median-cut 量化** 到 246 色（256 - 10 保护位）
3. `merge_similar_palette()` 合并近色 → 消除重建间的抖动
4. 插入 10 个保护位 → 得到 256 色共享调色板
5. **全部图像（BG + SPR）统一 remap** 到这个共享调色板

效果：

| 之前 | 之后 |
|------|------|
| 主调色板来自 id=0（仅海边场景），精灵颜色被迫映射到海边色系 | 主调色板来自全部图像（含肤色/发色/衣服色），精灵颜色正确 |
| 背景 MAG 保留独立调色板，编码时 `filter_white=True` 导致调色板不一致 | 所有 MAG 存储同一套 256 色调色板，编码时 `filter_white=False` |
| 背景可部分不变（保持 raw data） | 全部重新编码，调色板一致 |

引擎侧 `image_load()` 对非 sprite 调用 `image_set_palette()` 设置硬件调色板。所有图像共享同一套 256 色调色板，无论哪张 BG 最后加载，设置的都是对的。

### 12.7 共享调色板验证体系（三重防御）

为阻止日后改动意外破坏"所有 MAG 共享同一套调色板"的不变量，引擎从三个层面实施校验：

| 层 | 时机 | 机制 | 失败后果 |
|----|------|------|----------|
| **1 — 构建时** | `pack_images.py` 写完 IMAGE.DAT 后 | `verify_shared_palette()`：逐一读回所有 MAG 调色板，检查长度=256、全部一致、保护位正确 | `sys.exit(1)` 中止构建 |
| **2 — 诊断工具** | 独立运行 | `naiz_lib/image_dat.verify_shared_palette()`：读取 IMAGE.DAT，执行与层 1 相同的检查 | exit code 1，手动排查 |
| **3 — 引擎启动时** | `image_init()` TOC 解析后 | 用 `mag_read_palette()` 遍历所有非空 TOC 条目，比较 palette，检查 idx 7/15=white、248–255=black | 串口输出 `WARN: IMAGE.DAT palette mismatch`（非致命，引擎继续运行） |

层 1 在构建时直接阻断错误，层 2 用于事后排查，层 3 在运行期监警——三层覆盖了从开发到运行的全链路。

### 12.8 验证方式

1. **打包时检查**：`makegame.sh build` 输出不应有 `remapped indices` 警告
2. **运行时检查**：切换对话框样式（SOLID_BLUE / SOLID_BLACK），背景图不受影响
3. **精灵透明检查**：精灵边缘背景正确穿透，无白色/黑色边框
4. **动态改色检查**：切换不同 `dlgstyle`（0/2/4/6/8），对话框内部正确变色

---

## 13. 来源声明

MAG 格式规范参考 98imgtools（Unlicense）及 mooncore.eu 的 MAKI/MAG 文档。

VRAM 批量 blit 算法参考 love es×××× 引擎 `vram.c:VramDrawGrayscale()` 技术思路，重新实现为 PEGC packed-pixel 版本。

调色板管理策略为 Naiz 原创设计（三段保护机制）。

---

## 14. 修订历史

| 版本 | 日期 | 修改内容 |
|------|------|----------|
| 1.0 | 2026-06-09 | 初版：MAG 格式、IMAGE.DAT 归档、调色板管理、vram_blit、场景指令、初始化序列 |
| 2.0 | 2026-06-12 | 全线更新到 PEGC 256c |
| 2.1 | 2026-06-12 | 渲染顺序更新（背景→立绘→对话框→文字）；op_bgload 不再调用 scene_draw_dialog；新增 layer_capture_bg() 和 B15 引用 |
| 3.0 | 2026-06-18 | **共享调色板**：pack_images 从全部图像构建 256 色共享调色板（而非仅 id=0），所有 MAG 统一 remap。新增 `mag_read_palette()` 轻量 palette 读取。新增三重验证：构建时 `verify_shared_palette()`、诊断 `check_palette.py`、引擎启动时 palette 一致性校验 |
