# Phase 2：核心引擎系统

## 目标

实现完整的场景 VM、GPI 图像解码、字体加载、文本渲染、调色板系统，在 NP2kai 上运行完整示范场景（背景 + 对话 + 选项 + 分支）。

## 前置依赖

- ✅ Phase 1 完成（Hello World 画面）

## 参考项目

| 项目 | 查阅内容 | 用途 |
|------|----------|------|
| MHVNVisualNovelEngine | `MHVN98/src/` 下全部 .c / .h | 各子系统实现参考 |
| MHVNVisualNovelEngine | `pc98_vnengine.txt` | 完整数据格式规范（ROOTINFO、font、scene bytecode、text、BG/sprite、SE/GPI） |
| MHVN98 分析文档 | `MHVN98/04~11` | 各子系统架构理解 |
| master.lib | `libsrc/pal*.asm` | 调色板端口操作 |

## 实施步骤

### Step 1：ROOTINFO.DAT 解析

`engine/rootinfo.c` + `.h` — 读取 ROOTINFO.DAT，解析 VN 配置和各数据文件路径。

ROOTINFO.DAT 格式（参考 `pc98_vnengine.txt`）：

```
0x00  char[4]   magic          "MHVN"
0x04  uint16    VNflags
0x06  uint16    numstvar_glob
0x08  uint16    numflags_glob
0x0A  uint16    numstvar_loc
0x0C  uint16    numflags_loc
0x0E  uint16    format_norm
0x10  uint16    format_char
0x12  uint16    format_menu_notsel
0x14  uint16    format_menu_sel
0x16  char[12]  font_file       (null-terminated)
0x22  char[12]  scenedat_file
0x2E  char[12]  langdat_file
0x3A  char[12]  bgdat_file
0x46  char[12]  sprdat_file
0x52  char[12]  musdat_file
0x5E  char[12]  sedat_file
0x6A  char[12]  systemdat_file
```

- [x] `engine/rootinfo.c` — ROOTINFO.DAT 读取 + 校验 magic
- [x] `engine/rootinfo.h` — `RootInfo` 结构体 + `extern rootInfo`

### Step 2：调色板系统

`engine/palette.c` + `.h` — 三层调色板架构 + YUV 运算。

#### 三层 palette：

```
mainPalette[16]  ←  场景预设调色板（从 GPI palette_table 加载）
mixPalette[16]   ←  淡入淡出目标 / 色调旋转 / 饱和度修改
outPalette[16]   ←  最终写入 GDC 的硬件 palette
```

#### YUV 色彩空间运算（参考 MHVN98 `palette.c`）：

- `RGBToYUV()` / `YUVToRGB()` — 2.14 定点 YUV 转换矩阵
- `SetMainPalette()` — 设置 base palette
- `SetMixPaletteToSingleColour()` — mix palette 设为纯色
- `SetMixPaletteToMainAdd()` / `LuminosityMod()` / `SaturationMod()` / `HueMod()` / `Invert()` / `Colourise()`
- `MixPalettes(mixAmt)` — 0x00~0xFF 线性插值 main → mix
- `SetDisplayPaletteToOut()` — out → GDC（4bpc 转换）
- `SetDisplayPaletteToOutBrightnessModify(add)` — 亮度偏移后写入
- `SetDisplayPaletteToOutHueRotate(mod)` — 色调旋转后写入
- 5bpc 输入版本转换表 `c5bpcto8bpcTable[32]`
- 8bpc→2.14 定点表 `c8bpcto2p14pcTable[256]`

- [x] `engine/palette.c` — 三层 palette 管理
- [x] `engine/palette.c` — YUV 变换
- [x] `engine/palette.c` — 淡入淡出 + 色调旋转 + 饱和度修改

### Step 3：GPI 图像解码

`data/gpimage.c` + `.h` — GPI 格式图像解码。GPI 格式规范见 `pc98_vnengine.txt`。

```
0x00  char[3]  magic          "GPI"
0x03  uint8    flags
0x04  uint16   width           (实际值 - 1)
0x06  uint16   height          (实际值 - 1)
0x08  uint16   numTiles        (实际值 - 1)
0x0A  uint16   planeMask       位 0-3 = B/R/G/I planes, 位 8 = mask plane
0x0C  uint16   planeFilterMask 同 planeMask 布局，标记哪些 plane 用 RLE 压缩
```

解码流程：
1. 读 header → 解析宽高/tiles/plane mask
2. 为每个 plane 分配内存
3. 按 plane 逐个解码（RLE 解压或直读）
4. 支持 1-4 色 plane + 1 透明 mask plane

- [x] `data/gpimage.c` — GPI 文件打开与解码
- [x] `data/gpimage.h` — `GPIInfo` 结构体 + `GPI_HEADER_SIZE`

### Step 4：图像管理系统

`engine/graphics.c` + `.h` — 背景/精灵/文本框的加载、注册、绘制请求。

子系统组件：
- `ImageInfo` 结构体（boundRect, plane[0-3], mask, flags, layer）
- `LoadBGImage(sceneNum)` — 从 BG data archive 加载背景 GPI
- `DoDrawRequests()` — 遍历 ImageInfo 链表，将标记 `IMAGE_DRAWREQ` 的图像绘制到 VRAM
- `RedrawEverything()` — 强制重绘所有图像
- 9-slice 文本框系统：`RegisterTextBox()` / `RegisterCharNameBox()` / `RegisterChoiceBox()`
- `Draw9SliceBoxInnerRegion()` — 填充文本框/选项框的内部区域

- [x] `engine/graphics.c` — ImageInfo 链表管理
- [x] `engine/graphics.c` — BG 加载 + 绘制请求
- [x] `engine/graphics.c` — 9-slice 文本框注册与绘制

### Step 5：数学工具

`engine/stdbuffer.c` + `.h` — 定点数学函数和共享缓冲区。

函数：
- `Sin(x)` / `Cos(x)` — 2.14 定点正弦/余弦（256 条目查表，x 为 1.15 圈数）
- `Atan2(y, x)` — 1.15 定点反正切（16×16 查表 + 象限处理）
- `Sqrt(x)` — 整数平方根（查表 + Newton 迭代）

全局共享缓冲区（跨 .c 文件使用）：
- `smallFileBuffer[1024]` — 临时文件 I/O 缓冲区，由 rootinfo.c / textengine.c / graphics.c 等共享

- [x] `engine/stdbuffer.c` — 定点数学 + 共享缓冲区

### Step 6：字体系统

`data/fontfile.c` + `.h` — 字体文件加载。

字体格式（参考 `pc98_vnengine.txt`）：

```
0x00  uint32[]  char_ranges     Unicode 范围列表 = RangeEntryFile 数组
                                RangeEntryFile { uint16 first, uint16 last }
                                0x00000000 终止
var   uint32[]  char_infos      每 glyph 4 字节：
                                位 0-19 = 数据偏移（字节）
                                位 20   = 宽度（0=8px, 1=16px）
                                位 21-23 = y 偏移（行）
                                位 24-27 = 高度 - 1
var   uint8[]   glyph_data      1-bit bitmap（big-endian，逐行）
```

运行时子系统（参考 `unicode.c`）：
- **ASCII 永久缓存**：`asciiCharacterCache[94 × 16]` — 硬编码 0x21-0x7E 字模，始终常驻
- **LRU glyph 缓存**：32 字节 × 256 entry 环形缓存 + hash 存在性映射，自动驱逐
- `UTF8CharacterDecode()` — 1-3 byte UTF-8 解码（跳过 4-byte 超 BMP 字符）
- `LoadGlyphFromFile()` — 二分搜索 char_ranges，读取 glyph bitmap
- `UnicodeGetCharacterData(code, buffer)` — 返回 glyph 数据 + 宽度
- `SwapCharDataFormats()` — 切换 byte order（big-endian ↔ little-endian）

- [x] `data/fontfile.c` — 字体文件加载 + char_range 解析
- [x] `data/fontfile.h` — `FontInfo` 结构体

### Step 6：文本渲染引擎

`engine/textengine.c` + `.h` — 文本渲染管线。

管线流程：
```
text 字符串 → UTF-8 解码 → glyph 查找（ASCII 缓存 → Unicode font fallback）
→ glyph 缓存（glyphCache[32×256] LRU 环形缓存）→ EGC 单色绘制模式 blit 到 VRAM
→ Bayer 4×4 抖动实现文字淡入
```

子系统：
- `WriteString(str, x, y, format)` — 直接绘制完整字符串（同步）
- `StartAnimatedStringToWrite(str, x, y, format)` — 启动动画绘制
- `StringWriteAnimationFrame(skip)` — 逐帧绘制（逐字符 + 淡入动画）
- Format 格式字：`FORMAT_BOLD` / `ITALIC` / `UNDERLINE` / `SHADOW` / `FADE(n)` / `COLOUR(n)`
- 阴影色表 `shadowColours[16]`
- 角色名 box / 文本框 / 选择框的位置管理
- 内部缓冲区：`stringBuffer1[512]` / `stringBuffer2[512]`（文本处理）、`animCharBuf[16×16]`（逐字缓存）

- [x] `engine/textengine.c` — `WriteString()` 直接绘制
- [x] `engine/textengine.c` — 动画绘制系统
- [x] `engine/textengine.h` — 格式字定义 + `TextInfo` 结构体

### Step 7：场景字节码 VM

`engine/scenevm.c` + `.h` — 场景字节码加载与解释执行。

#### VM 控制流

```
vmFlags（8 位）：
  位 0 = Z flag（比较结果零）
  位 1 = N flag（比较结果负）
  位 6 = TEXTINBOX（文本框不为空）
  位 7 = PROCESS（执行中）

asyncActions（8 位）：
  位 0 = ASYNC_FADE      — 亮度淡入淡出 / 色调旋转
  位 1 = ASYNC_PALETTE   — 调色板淡入淡出
  位 2 = ASYNC_SCROLL    — 屏幕震动
  位 7 = ASYNC_USER      — 等待用户输入

执行循环：
  while (vmFlags & VMFLAG_PROCESS) {
    取 opcode → 执行 → 可能设置 ASYNC_USER / 清除 PROCESS
  }
  SceneAsyncActionProcess()  // 每帧更新异步效果
```

#### 完整操作码表（参考 MHVN98 实现全部 opcode 0x00-0x3F）

| 范围 | 指令 | 参数 | 实现 |
|------|------|------|------|
| `0x00` | gotoscene | `uint16` | FULL |
| `0x01` | jmp | `int16` | FULL |
| `0x02-0x07` | je/jne/jl/jge/jle/jg | `int16` | FULL |
| `0x08-0x0E` | palsetcol/paladdcol/palsetlum/palsetsat/palsethue/palcolourise/palinvert | 2/1 byte | FULL |
| `0x0F` | nowait | — | FULL |
| `0x10` | nexttext | — | FULL |
| `0x11` | text | `uint16` | FULL |
| `0x12` | charname | `uint16` | FULL |
| `0x13` | deltext | — | FULL |
| `0x14-0x17` | ynchoice/choice2-4 | var | FULL |
| `0x18-0x1B` | bfadein/out, wfadein/out | 1 byte | FULL |
| `0x1C-0x1D` | pfadein/out | 1 byte | FULL |
| `0x1E` | phuerotate | 1 byte | FULL |
| `0x1F` | shake | 2 byte | FULL |
| `0x20-0x22` | lut2/lut3/lut4 | var | FULL |
| `0x23` | swapzn | — | FULL |
| `0x24-0x2D` | setvi/vv, csetvi/vv, cmpvi/vv, addvi/vv, subvi/vv | var | FULL |
| `0x2E-0x2F` | ldflg/stflg | `uint16` | FULL |
| `0x30` | setbg | `uint16` | FULL |
| `0x31-0x32` | addbgvar/subbgvar | `uint16` | **STUB** |
| `0x34-0x3E` | setspr0-2, addspr0-2var, subspr0-2var | `uint16` | **STUB** |
| `0x33/0x37/0x3B/0x3F` | (reserved) | — | SKIP |
| `0x40-0xFF` | (reserved) | — | SKIP |

#### 变量地址空间

```
0x0000-0x0007   Scratch variables  (8 个 int16)
0x0008-0x001F   Scratch flags      (24 位，bitpacked)
0x0020-0x00FF   Global variables   (224 个 int16)
0x0100-0x03FF   Global flags       (768 位)
0x0400-0x05FF   Local variables    (512 个 int16)
0x0600-0x0FFF   Local flags        (2560 位)
```

#### 异步操作

- `SceneAsyncActionProcess()` — 每帧调用，更新 fade / palette / shake
- 淡入淡出使用 `10.6` 定点（`curBFadeAmt` / `curWFadeAmt` / `curFadeTarget` / `curFadeSpeed`）
- 色调旋转使用 `1.15` 定点（`curHueRotationFactor` / `curHueRotationSpeed`）
- 屏幕震动使用 `8.8` 定点振幅 + `1.15` 相位角 + `2.14` 阻尼

- [x] `engine/scenevm.c` — VM 主循环 + opcode 0x00-0x0F
- [x] `engine/scenevm.c` — opcode 0x10-0x17（text/charname/choice）
- [x] `engine/scenevm.c` — opcode 0x18-0x2F（fade/palette/variables/jumps）
- [x] `engine/scenevm.c` — opcode 0x30-0x3F（bg/sprite — setbg FULL，其余 STUB）
- [x] `engine/scenevm.c` — `SceneAsyncActionProcess()` 异步动画
- [x] `engine/scenevm.h` — `SceneInfo` 结构体 + status 常量

### Step 8：集成联调

### Step 8：按键输入

`pc98_keyboard.c` 提供边缘检测（参考 `pc98_vnengine.txt`）：

- **BIOS 键盘状态**：地址 `0x0040:0x0017`，16 字节，每字节对应一个按键 SCAN CODE
- `prevKeyStatus[16]` — 上一帧的键盘状态快照
- `keyChangeStatus[16]` — `prevKeyStatus ⊕ 当前状态`（key down 检测）
- `UpdatePrevKeyStatus()` — 每帧开始时调用，拷贝当前 BIOS 状态到 prevKeyStatus
- `key_pressed(scancode)` — 检查 keyChangeStatus 中某 bit 是否置位

- [x] `plat/pc98/pc98_keyboard.c` — `UpdatePrevKeyStatus()` + `key_pressed()`

### Step 9：主循环整合

主循环整合（参考 `main.c` 原始流程）：

```c
int main(void)
{
    if (!hal_check_compatibility()) return 0xFF;
    hal_video_init();

    ReadInRootInfo();
    InitFontFile();
    SetupSceneEngine();
    // ...文本/调色板/图像初始化...

    while (1)
    {
        hal_vsync_wait();
        DoDrawRequests();

        int status = SceneDataProcess();
        SceneAsyncActionProcess();

        if (status & SCENE_STATUS_FINALEND) break;
        if (status & SCENE_STATUS_RENDERTEXT) {
            StringWriteAnimationFrame(textSkip);
        }
        if (status & SCENE_STATUS_MAKING_CHOICE) {
            // 接收按键选择
        }

        // 按键处理（Enter/Up/Down/Esc）
        if (key_pressed(...)) { ... }
    }
    return 0;
}
```

- [x] 整合主循环：main.c 调用所有子系统
- [x] 复制 engine.exe + Phase A 产生的 `out/` 数据到 NP2kai 磁盘
- [x] 修复 case 0x10 PC-- 回退导致 load_new_scene 越界（devdocs/21）
- [x] 修补 ROOTINFO.DAT font_path（inject.py 自动修补）
- [x] HAL 架构整顿 P1-P3（devdocs/22）：文件 I/O、内存分配、兼容性检查、日志埋点规范化
  - ⚠️ P2c（hal_video_fill_rect 矩形填充）未完成，仍填满全屏
  - ⚠️ P1b（hal_mem_alloc/free）缺少 clobber 列表：`hal_mem_alloc` 缺 `"%bx"`，`hal_mem_free` 缺 `"%es"`、`"%ax"`
- [ ] **M2**：NP2kai 上运行完整示范场景（背景 + 对话 + 选项 + 分支）

## 产出物

```
core/engine/
├── main.c              ← 更新后的主循环
├── stdbuffer.c + .h    ← 新增（定点数学 + 共享缓冲区）
├── rootinfo.c + .h     ← 新增
├── palette.c + .h      ← 新增
├── graphics.c + .h     ← 新增
├── scenevm.c + .h      ← 新增
├── textengine.c + .h   ← 新增
└── lz4.c + .h          ← Phase 1

core/data/
├── gpimage.c + .h      ← 从 Phase 1 移入
├── fontfile.c + .h     ← 从 Phase 1 移入
└── font_ascii.c        ← 新增（方案 B 过渡）
```

## 验证

完成后回到 `03-编译example项目方案.md` 确认 M2 里程碑。
