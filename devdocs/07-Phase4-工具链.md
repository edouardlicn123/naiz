# Phase 4：Python 工具链

## 目标

用自研 Python 工具链替代 MHVN98 原 C++ 工具链，完整数据管线可工作。

## 前置依赖

- ✅ Phase 2 完成（引擎可运行场景）

## 参考项目

| 项目 | 查阅内容 | 用途 |
|------|----------|------|
| MHVNVisualNovelEngine | `MHVNSCAS/`、`MHVNTXAR/`、`MHVNIMGP/`、`MHVNLINK/` | 各工具源码 + .odat/.otxa 中间格式规范 |
| MHVNVisualNovelEngine | `pc98_vnengine.txt` | ROOTINFO.DAT/数据 archive 完整格式规范 |
| MHVNVisualNovelEngine | `MHVNTEST/masterdesc.txt` | masterdesc.txt 示例 |
| xsys35c | GPL v2，仅参考 | 脚本编译器架构参考 |
| 98imgtools | Unlicense | PC-98 磁盘/打包格式参考 |

## 工具依赖关系

```
原始素材：
  *.mhn (场景脚本)  *.txt (文本)  *.png (图像)  *.ttf (字体)
        │               │              │            │
        ▼               ▼              ▼            ▼
  script_compiler   text_archiver   img_converter  font_builder
        │               │              │            │
        │               │              ▼            │
        │               │          .gpi 文件        │
        │               │              │            │
        ▼               ▼              ▼            ▼
  ┌──────────────────────────────────────────────────────┐
  │              MHVNLINK (linker)                       │
  │  组合 ROOTINFO.DAT + SCENE.DAT + TEXT.DAT +          │
  │        BG.DAT + SPR.DAT + FONT.DAT + ...             │
  └──────────────────────────────────────────────────────┘
                        │
                        ▼
                  out/ 数据目录
```

各工具输出格式（与原版 .odat/.otxa 兼容）：

| 工具 | 输出格式 | 被输入到 |
|------|----------|----------|
| `script_compiler` | `.odat`（含 scene 数据 + link info） | linker |
| `text_archiver` | `.otxa`（含 text 数据 + link info） | linker |
| `img_converter` | `.gpi` 文件 | （直接由 engine 加载，或在 archive 中打包） |
| `font_builder` | `.fnt` 文件 | （直接由 engine 加载） |
| linker | `ROOTINFO.DAT` + `*.DAT` | 最终数据 |

## 实施步骤

### Step 1：场景脚本编译器

`tools/script_compiler/` — `.mhn` 文本源码 → `.odat` 中间文件。

输入格式：参考 MHVN98 场景汇编语法：
- `.scene name` — 声明场景
- `.vnentry` — 入口场景
- `.globvar/.globflag/.localvar/.localflag` — 变量/标志声明
- `label:` — 标签
- `instruction args` — 操作码指令

输出：`.odat` 中间文件，格式：
```
0x00  uint64   link_info_ptr
0x08  [scene data 内容]       ← 字节码 + 未解析链接占位符
link_info:
      uint16   num_chars
      uint16   num_scenes
      uint16   numstvar_glob / numflags_glob / numstvar_loc / numflags_loc
      uint16   num_bg / num_spr
      char[]   charname_labels
      ...
```

- 词法分析 / 语法分析
- 与 Phase 2 VM opcode 匹配的字节码生成
- LZ4 压缩输出

- [ ] `tools/script_compiler/` — 词法/语法分析
- [ ] `tools/script_compiler/` — 字节码生成 + symbol table
- [ ] `tools/script_compiler/` — .odat 输出

### Step 2：文本归档器

`tools/text_archiver/` — 文本源码（UTF-8）→ `.otxa` 中间文件。

输入格式参考 MHVNTXAR：
- `@[label]` — 开条目
- `@]` — 关条目
- `@s(name)` — 声明场景
- `@n(name)` — 声明角色名
- `@f/f/@cn/@wn` 等格式化转义序列

输出：`.otxa` 中间文件，格式：
```
0x00  uint64   link_info_ptr
0x08  [text data 内容]
link_info:
      uint16   num_chars / num_scenes
      uint64[] scene_linkdatptrs
      char[]   scene_labels
```

- [ ] `tools/text_archiver/` — 文本解析 + UTF-8 验证
- [ ] `tools/text_archiver/` — .otxa 输出

### Step 3：图像转换器

`tools/img_converter/` — PNG → GPI 格式转换。

输入：PNG 图像 + 配置
输出：GPI 文件（格式见 Phase 2 Step 3）

功能：
- PNG 解码（Pillow）
- 16 色量化 + 调色板提取
- RLE 行压缩（可选，根据 planeFilterMask）
- 调色板数据输出为 palette_table 格式

- [ ] `tools/img_converter/` — PNG → GPI 转换
- [ ] `tools/img_converter/` — 16 色量化 + palette 提取

### Step 4：字体构建器

`tools/font_builder/` — TTF → 引擎字体文件。

输出格式参考 `pc98_vnengine.txt` font 格式：
```
char_ranges[]      ← Unicode 范围列表
char_infos[]       ← 每 glyph 元数据（偏移/宽度/高度/y-offset）
glyph_data[]       ← 1-bit bitmap
```

功能：
- TTF 渲染（Pillow + freetype）
- glyph 位图提取（单色 1-bit）
- 字符范围 packing

- [ ] `tools/font_builder/` — TTF → 引擎字体

### Step 5：数据打包器（Linker）

`tools/linker/` — 接收所有 .odat/.otxa/.gpi/.fnt 文件 + masterdesc.txt，输出最终数据。

masterdesc.txt 格式（参考 MHVN98 `masterdesc.txt`）：
```
format_norm = bold italic shadow colourF mask8
format_char = colourF
format_menu_notsel =
format_menu_sel = colour0
cg_gallery = no
music_room = no
custom_info = no
```

功能：
- 读取 masterdesc.txt 生成 ROOTINFO.DAT
- 组合 .odat 场景数据 → SCENE.DAT（LZ4 压缩）
- 组合场景文本 → TEXT.DAT
- 组合 GPI 文件 → BG.DAT / SPR.DAT
- 生成语言索引文件 LANG.DAT

- [ ] `tools/linker/` — ROOTINFO.DAT 生成
- [ ] `tools/linker/` — 场景/文本/图像/音乐/SE archive 打包

### Step 6：项目脚手架

`tools/scaffold/` — `mhn new project_name` 初始化新游戏项目。

功能：
- 生成 `src/`、`img/`、`text/`、`font/` 目录
- 复制模板 `masterdesc.txt` + 最小 `.mhn` 脚本
- 生成项目级 `Makefile`

- [ ] `tools/scaffold/` — 项目初始化

### Step 7：替换验证

- 用自研工具链重新编译 `projects/example/` 数据
- 产出的数据应与原工具链功能一致
- **✅ M4**：自研工具链可完整构建 example 项目

- [ ] 自研工具链构建 example 项目
- [ ] **✅ M4** 确认

## 产出物

```
tools/
├── script_compiler/     ← .mhn → .odat
├── text_archiver/       ← .txt → .otxa
├── img_converter/       ← PNG → .gpi
├── font_builder/        ← TTF → .fnt
├── linker/              ← 所有中间文件 → final data
└── scaffold/            ← mhn new
```

## 验证

回到 `03-编译example项目方案.md` 确认 M4 里程碑。
