# 73-图片序列帧动画（NAIZ_ANIM）方案

> ⚠️ **已过时，仅供参考。** 已由 `devdocs/77-动画与转场系统统一文档.md` 取代并合并（含 ANI 容器修订），仅存留作历史记录，勿作为实施依据。
>
> 状态：方案定稿，未实现。等待后续实施指令。
> 决策记录：需求「类似 galgame opening」；选定「引擎内建 anim 系统」；动画分两类 **fullscreen（占满 640×400 显示区域）** 与 **cine（对话框上方区域 y<280，不占对话框）**，两类并行实现，由 `anim` 命令的 type 参数驱动播放位置；动画帧素材由内容方自备单帧图；「单文件打包多帧（SPS 式）」暂缓评估。
> 加载方式决策：naiz 现有 `vram_blit_sprite` 逐行覆盖写 VRAM 且无 vblank 同步，全屏帧在循环动画中会产生「从上往下滚动覆盖 + 撕裂」；参考 unlove/Love 双轨解法 —— **调色板轨（循环首选）**：像素只 blit 一次底图、每帧仅换调色板（全屏瞬时、零撕裂、不触发对话框重建）；**像素轨**：整帧替换 + `vblank_wait()` 硬约束。

## 一、需求

用一组静态图片按时间顺序连续展示得到动画（序列帧动画），面向「类似 galgame opening」的过场体验。

动画按目标区域分为两类：

- **fullscreen**：动画帧可占满整个 PC-98 显示区域（640×400）。若对话框已打开，动画需与伪半透明对话框正确共存（见 §5.6）。
- **cine**：不占据对话框区域，只在对话框上方（y ≥ 0 且 y+h ≤ 280）播放的区域动画。永不触碰对话框区域，无对话框交互负担。

两类并行实现、互不冲突。共同诉求：

- 逐帧前进；支持一次性播放与循环播放
- 与 NB 脚本同步（`waitanim` 阻塞）
- 帧率可控（fps 参数）

## 二、现有管线速查（复用基础）

| 环节 | 现状 | 复用点 |
|---|---|---|
| 图片资源 | `images/*.MAG` → `ASSETS.DB`(SQLite `img_map`: id/type IMG\|SPR/name) → `IMAGE.DAT` | 帧走同法进 `${id}` 即 asset 引用 |
| 资产表 | `export_asset_table.py` → `nb_asset_table.h`（asset_map/spr_asset_map/char_map/expr_map） | 动画定义表走同一生成链路 |
| 图片解码 | `core/engine/image.c` `image_load(id)`，LRU 8 槽（image_cache.c），`mag_retain`/`mag_release` 引用计数 | 按需解码 + 只持当前帧引用 |
| 精灵 | `layer_sprite_show/face/replace/hide_all`，`layer_bg_restore_rect` 恢复旧区，`vram_blit_sprite`（带 `clip_h`；`calc_sprite_clip_h` 逻辑见 layer_sprite.c） | cine 类换帧的脏区恢复与越 280 裁剪 |
| 帧循环 | `core/engine/main.c` 主循环每帧必调 `nb_process()`；对话框翻页经 `vm_delay_*`/`vm_flags` 暂停 | `nb_process` 帧首为动画 tick 挂载点；waitanim 复用 pause 语义 |
| NB 命令 | `nb_commands.c cmd_table[]`（注册先例：nb_scene.c/nb_question.c 独立文件） | `anim`/`waitanim`/`stopanim` 以独立文件注册 |

## 三、方案选型（决策记录）

- A. 纯 NB 脚本逐帧：零改动，但 cmd_table 无循环/跳转命令，帧序列只能全展开、帧率不可控 → 弃
- B. **引擎内建 anim 播放器**：新模块 + 命令 + 工具链，一次投入可复用 → 采纳
- C. 动画打包为独立资源类型（单文件多子图 + 头部偏移表，SPS 式）：**暂缓评估**。

首版范围：
- 两类（fullscreen / cine）并行实现
- 双轨（track）播放：调色板轨（pixel 帧只 blit 一次、每帧换调色板，循环首选）与像素轨（整帧替换 + vblank 同步）并行
- 全局单一活动动画（一次只播一段）
- type 参数驱动播放位置：fullscreen 全幅 + 对话框重建；cine 自动裁剪可见区到 y<280
- 帧数长动画内存安全：按需解码、仅持当前帧
- 打包（SPS 式）与显示逻辑解耦，不作为第一版前提

## 四、参考项目：unlove / Love（Escalator）引擎经验

对 `~/unlove`（PC-98 恋爱游戏 Love 的反编译研究目录）的已验证结论，作为序列帧动画的真实范例：

1. **全屏序列帧动画（ECG）**：`BE01_A.ECG` ~ `BE01_G.ECG` 为同一场景 7 帧 **640×400 全屏图**（与 naiz 分辨率一致）。
   - 帧间像素差异实测：B=38% → E=68% → G=4%，确认是连续动画（末帧回落、可回到首帧循环）。
   - 每帧压缩后约 6–20KB（16 字节头 + RLE/块压缩），原始全屏 256KB → 压缩率极高。naiz 的 MAG 已是压缩格式，同样满足。
2. **单文件打包多子图（SPS）**：`OPTCG.SPS`（67KB）= 头部 `N×u32 偏移表` + 各段子图。相关图组打进一个文件按偏移索引。
   - 这是方案 C（打包资源）的真实形态；当前判断为**可选存储优化**，与显示逻辑解耦，暂缓。
3. **OP 动画由脚本指令驱动（PCL 帧 + EQA）**：`OP.EQA`（opening 脚本）按序引用 `OP11/OP01B/OP01R/OP02/OP06…` 帧文件，动画切换/时序全在脚本指令层（资源加载指令 + PUSH 参数 + jump）。naiz 的 `anim`/`waitanim`/`stopanim` 命令思路一致。
4. **PCL 带调色板索引映射表（已确证）**：`OP01R.PCL` 头部（4 字节长度后）即一串 `0x77 (from,to)` 索引对：
   ```
   77 03 07 77 0c 0f 77 1e 1f 77 31 3f 77 43 47 77 5f 63 77 6d 6f …
   ```
   即按帧把像素索引范围重映射到新的调色板条目上；配合 `OP.EQA` 的 `52/50/54` 调色板写命令（逐条改写 palette 条目：`52 00 00 06 01 01 …`、`54 00 54 01 54 02 54 03 …`）实现闪烁/明暗/色相流动。**这是 Love OP 动画的主体 —— 像素不动、只换调色板。**

**差异警示**：Love 引擎未确认存在伪半透明 VN 对话框；naiz 的伪半透明对话框（PAT75 抖动）依赖对话框区域背景像素，与全屏动画帧交互复杂。本方案以 **fullscreen / cine 分类**主动隔离此差异：cine 类永不进入对话框区域；fullscreen 类的对话框重建流程单独设计（§5.6）。

### 4.1 加载/显示方式与循环动画（unlove 双轨解法）

**naiz 现状问题**：`image_load(id)`（image.c:144）整帧解码进 RAM 的 `MagImage`，之后 `vram_blit_sprite()`（render.c:113）`for (py=0..dh)` **逐行从上到下**写 VRAM，且 **blit 本身不调 `vblank_wait()`**。单次显示尚可；全屏 640×400=256KB 写入会跨多个垂直回扫周期，显示器边扫边画，人眼看到「下一帧从顶部逐行滚下来覆盖上一帧」。循环动画时每帧都滚一遍 + 帧间撕裂，观感怪异。**根因 = 写 VRAM 与扫描输出无同步 + 逐行覆盖。**

**unlove/Love 的双轨解法**：

1. **调色板轨（主）**：屏幕像素 blit 一次底图后不再动，每帧只写调色板端口（PC-98 0xA8–0xAE；即 naiz `hal_set_palette`）。调色板刷新**全屏瞬时统一生效，无「逐行覆盖」概念，循环零撕裂**，且带宽极小（每帧仅 256×3 字节）。Love 的 OP 闪烁/渐隐/色相流动全部由此实现（§四.4 的 PCL `0x77` + EQA `52/50/54`）。
2. **像素轨（辅）**：真正必须动像素的帧（如 BE01_A..G）整帧解码后一次性替换（day9: 0x01A7D = 读 ECG → 解码 → 写 VRAM → 刷新），靠 **vblank 同步**让每帧尽量在一次回扫窗口内写完；循环帧（G→A 回落 4%）靠**帧间差异小**保证平滑。

**对 naiz 的结论**：
- 循环动画**首选调色板轨**；像素轨仅用于帧间差异大的真动画
- 像素轨每次 blit 前必须 `vblank_wait()`（对齐 §5.6 fullscreen 现有约定，升级为全局硬约束）
- 调色板轨不触碰 VRAM 像素，天然不触发对话框重建，全屏动画 + 对话框共存时也最省心（对话框随调色板整体变色，视觉自然）

## 五、引擎设计

### 5.1 新文件

- `core/engine/nb_anim.h`：`AnimDef`/`AnimDefType` 声明、`anim_tick()`、`anim_start/anim_stop/anim_wait`、命令处理函数声明
- `core/engine/nb_anim.c`：实现
- `nb_anim_table.h`：生成头（Makefile 依赖条目 `build/nb_anim.o: engine/nb_anim_table.h`）

### 5.2 类型与轨道定义

```c
/* type —— 区域语义（脚本层，内容方操作），只决定渲染区域与对话框相互作用 */
typedef enum {
    ANIM_TYPE_FULLSCREEN = 0,  /* 占满 640x400；对话框已开时走重建路径(§5.6) */
    ANIM_TYPE_CINE      = 1    /* 对话框上方区域；可见区强制 y+h<=LAYER_DIALOG_Y */
} AnimDefType;

/* track —— 播放机制（素材属性，由 anim.json 导入时指定），与 type 正交 */
typedef enum {
    ANIM_TRACK_PIXEL   = 0,    /* 像素轨：每帧整图替换（vblank 同步），帧间差异大的真动画 */
    ANIM_TRACK_PALETTE = 1     /* 调色板轨：底图只 blit 一次，每帧仅换调色板（循环首选） */
} AnimTrackType;
```

`type` 与 `track` 正交：type 决定画到哪里，track 决定怎么画。

### 5.3 状态

```c
typedef struct {
    int          active;      /* 0=空闲 */
    const AnimDef *def;
    int          frame;       /* 当前帧下标 */
    int          tick;        /* 帧间隔剩余计数 = 60/fps */
    AnimDefType  type;        /* 区域类型（来自定义表） */
    AnimTrackType track;      /* 播放轨道（来自定义表） */
    int          x, y;        /* cine: 显示起始坐标；fullscreen: 固定(0,0) */
    int          w, h;        /* cine: 帧显示区域（dirty 区）；fullscreen: 全屏 */
    int          base_blitted;/* 调色板轨：底图是否已 blit（每段动画仅一次） */
    MagImage    *img;         /* 当前帧 mag_retain 引用，收尾 release */
} AnimState;
static AnimState g_anim;      /* 全局单一活动动画 */
```

cine 类帧的显示区域由 type 保证：blit 高度钳制到 `min(h, LAYER_DIALOG_Y - y)`，`y >= LAYER_DIALOG_Y` 时拒绝启动（参数校验，见 §8）。

### 5.4 NB 命令（注册进 cmd_table）

- `anim(type, 名字, [x, y])`：type ∈ `fullscreen`/`cine`；查 `anim_defs` 启动（track 取自定义表，脚本不传）；若已有活动动画先 `stopanim`；首帧立即绘制；cine 类校验位置参数（越 280 拒启并日志）
- `waitanim`：阻塞语义 —— 动画未完成时暂停脚本推进（复用 `vm_pause_process` 风格）；停止/播完续行
- `stopanim`：释放当前帧引用、清 active；供 fullscreen 动画后切入静态背景时显式收尾

### 5.5 每帧推进

- `nb_process()` 帧首调用 `anim_tick()`
- `anim_tick()`：未活动直接返回；`tick--` 至 0 则 `frame++` 换帧（间隔 = 60/fps），到末帧按 loop 回卷或停止（释放引用，waitanim 唤醒）
- 换帧按 track 分派：
  - **像素轨**：按 type 走 §5.6 像素路径（整帧 blit + 区域边界处理）
  - **调色板轨**：每帧仅 `hal_set_palette` 换色（见 §5.6 调色板路径）；第一帧负责 blit 底图（`base_blitted` 置位）

### 5.6 换帧路径（硬约束）

**像素轨 · cine（对话框上方区域）**
1. `vblank_wait()`
2. `layer_bg_restore_rect(x, y, w, h, 0)` 恢复旧区（用于 x,y 与帧宽高一致的固定区域）
3. `vram_blit_sprite(新帧, x, y, PAL_TRANSPARENT, 0, clip_h)`，`clip_h` 按 `calc_sprite_clip_h` 逻辑钳制，保证**绝不写入 y ≥ LAYER_DIALOG_Y**
4. 无对话框交互：不触碰 `dialog_snapshot`/`bg_dialog_snapshot`

**像素轨 · fullscreen（全屏）**
1. `vblank_wait()` → `vram_blit(新帧, 0, 0)` 全幅
2. 若 `layer_dialog_drawn()`，执行**对话框区域重建**：
   - 更新 `bg_dialog_snapshot`：从当前动画帧的对话框区域截取（`layer_capture_bg_dialog()` 已在 VRAM 上重建后读回；或直接置为「动画期无效」并由 §5.7 接管）
   - 伪半透明合成：`scene_draw_dialog()`（`fill_dialog_bg` PAT75 抖动 + 白边框）
   - 文本重绘：经 `dialog_show` 同一路径重放当前 charname/text（`nb_dialog_get_*`）
   - `dialog_snapshot` 即时重截取，`dialog_dirty` 复位——**不得使用动画之前的过期快照**
3. 帧自身不含对话框内容时同样执行（对话框区域像素来自动画帧背景 + 伪半透明）

**调色板轨（循环首选，type 任意）**
- 首帧（`base_blitted == 0`）：`vblank_wait()` → 按 type 区域 blit **底图**（cine: clip_h 钳制；fullscreen: 全幅）→ 若底图区域与对话框区域重叠且 `layer_dialog_drawn()`，执行一次对话框重建（同像素轨 fullscreen 步骤 2）→ `base_blitted = 1`
- 后续每帧：**仅 `hal_set_palette` 换色**（改写当前帧 palette 表），不动 VRAM 像素、无 vblank 需求（调色板端口 0xA8–0xAE 写入瞬时全屏生效）、不触碰 `dialog_snapshot`（像素索引不变，重建后的快照保持有效）
- 停止/循环结束：恢复静态背景（`bg` 命令），同 §5.7

**全屏动画期间 `bg`/`scene_end` 会破坏动画源** → 脚本须先 `stopanim`；动画期间静态背景快照（`bg_snapshot`）视为不可用，播完再由后续 `bg` 命令重建。

**通用硬约束**：任何动 VRAM 像素的帧（像素轨每帧、调色板轨首帧底图）blit 前必须 `vblank_wait()`，避免「从上往下滚动覆盖 + 撕裂」。

### 5.7 对话框 × fullscreen 交互状态机（待实现细化）

按 track 区分重建频次：

- **像素轨**：
  - 动画启动且对话框已开：记录对话框状态（文本/charname/offset），动画期间**每帧**重建（§5.6）
  - 动画启动且对话框未开，动画中 `dialog_show` 被调用：对话框照常打开，后续每帧走重建路径
- **调色板轨**：仅底图 blit 时执行一次重建；之后每帧只换调色板，对话框随整体变色，快照保持有效
- 动画停止/循环结束（两轨同）：恢复静态背景（`bg` 命令），对话框快照按 `layer_capture_bg` 语义重建

### 5.8 内存策略

- **像素轨**：逐帧 `image_load(id)` 仅当次取帧；上一帧 `mag_release`；`g_anim.img` 只持当前帧，结束/停止即 release
- **调色板轨**：底图 `MagImage` 只取一次并持有（动画期间不 release）；每帧调色板表为小体积静态数据（每帧 256×3 字节，可直接进生成头），无逐帧解码开销
- 不做全帧预载（几十帧全屏 = N×256KB 会爆扩展内存）；MAG 解码开销小，逐帧可接受
- LRU 8 槽缓存沿用：像素轨毗邻帧天然驻留，不额外侵入 image_cache

## 六、数据管线设计

### 6.1 帧素材组织

**像素轨**（帧间差异大的真动画）：
```
projects/<game>/anim/<片段名>/frame_001.PNG
                              frame_002.PNG
                              ...
```

**调色板轨**（循环首选：共享底图 + 每帧调色板表）：
```
projects/<game>/anim/<片段名>/base.PNG          # 底图（blit 一次）
                              pal_001.pal       # 每帧调色板表（256 行 "R G B"）
                              pal_002.pal
                              ...
```

文件名按序即播放顺序（工具按字典序排序，建议两位以上补零）。同一段动画的帧尺寸一致；fullscreen 类为 640×400，cine 类可为任意尺寸（引擎按 type 控位）。调色板轨各帧表可只含差异条目（未列出索引沿用上一帧），工具补全为完整 256 表。

### 6.2 anim_import.py（新工具，`tools/naiz_build/`）

- 入参：`<project_dir> <anim_dir> [--type fullscreen|cine] [--track pixel|palette] [--fps N] [--loop]`
- 流程（像素轨）：
  1. 读取 `anim/<片段名>/frame_*.PNG`（复用 `naiz_lib/mag_codec` 转 MAG）
  2. 批量写入 `ASSETS.DB img_map`（type 按参数，name 形如 `<片段>_fNN`），得各帧 asset_id
  3. 生成/合并 `projects/<game>/anim.json`（含 type/track/fps/loop）
- 流程（调色板轨）：
  1. `base.PNG` 转 MAG 入 `img_map`（底图 asset）
  2. `pal_*.pal` 解析为每帧 256×3 调色板表，写入 `projects/<game>/anim/<片段>.pal`（合并静态表，供后续生成头）
  3. 生成/合并 `anim.json`（`track:"palette"`，frames 仅含底图 asset，palette 表独立引用）
- 校验：PNG 尺寸一致、色表一致性（沿用 image.c 共享调色板不变量）
- **工具自动从帧序列提取共享像素 + 每帧调色板——暂缓**（不内联，内容方显式提供两轨素材）
- 遵守 Python 规约（P1/P2/P3/P7/P9/P10）

### 6.3 anim.json 定义

```json
{
  "anims": [
    {"name": "op_bg", "type": "fullscreen", "track": "pixel", "fps": 24, "loop": false,
     "frames": ["op_bg_f01", "op_bg_f02", "..."]},
    {"name": "op_shimmer", "type": "fullscreen", "track": "palette", "fps": 6, "loop": true,
     "base": "op_shimmer_base", "palettes": "op_shimmer.pal"}
  ]
}
```

`frames`/`base` 用 img_map 的 `name`；`export_asset_table.py` 解析时转 asset_id，`type` 映射为 `AnimDefType` 值、`track` 映射为 `AnimTrackType` 值。

### 6.4 export_asset_table.py 扩展

- 读取 `anim.json`，对每条动画查询 `img_map` 得帧 id 数组（像素轨）或底图 id（调色板轨）
- 追加生成 `core/engine/nb_anim_table.h`：
  - `struct AnimDef { const char *name; int type; int track; int fps; int loop; int nframes; const int *frames; const PaletteEntry *pals; }`
  - 像素轨：`nframes` = 帧数，`frames` 为帧 id 数组；调色板轨：`nframes` = 调色板帧数，`frames` 仅底图 id、`pals` 指向每帧 256×3 调色板静态表（`nb_anim_table.h` 内嵌）
  - `static const AnimDef anim_defs[]`（含帧数组/调色板表静态初值）
  - `#define ANIM_INDEX_<NAME>` 或 `anim_find(name)` 下标常量
- 头风格沿用 `nb_asset_table.h`（preamble/footer 同 `naiz_build/c_header.py`）

## 七、验证

1. `make -C core`：0 errors / 0 warnings（Makefile `wildcard engine/*.c` 自动收录新 .c；为 nb_anim.o 增加 `nb_anim_table.h` 生成头依赖）
2. `tools/env_setup/venv/bin/python -m pytest tools/tests/`
3. `./makegame.sh build demo-a2`（data 构建 + HDI 注入）
4. NP2kai 实机目检各处样例：
   - 像素轨 fullscreen：一段全屏 OP（无对话框）+ 一段「全屏动画 + 对话框字幕」验证 §5.6/§5.7
   - 像素轨 cine：一段对话框上方区域动画，验证裁剪不越 280、对话框不被扰动
   - 调色板轨（fullscreen + cine 各一）：验证循环零撕裂、像素只 blit 一次（首帧后仅换色）、对话框随整体变色
5. 串口日志（`makegame.sh test demo-a2 --serial`）核对 anim 启动/换帧/结束日志与 cine 越界拒启日志

## 八、实现顺序（待指示后执行）

1. 工具：anim_import.py（含调色板轨） + export_asset_table.py 扩展 → pytest
2. 引擎：nb_anim.h/c + cmd_table 注册（anim/waitanim/stopanim）+ nb_process 挂 tick + type/track 分派（含调色板轨换色）+ Makefile 依赖 → make
3. 内容：demo-a2 各一段像素轨（fullscreen/cine）与调色板轨样例 → 构建 → NP2kai 目检
4. 文档与版本：B90（函数/工具索引）、B92（anim 命令 + §3 管线）、bump_version

## 九、防复发要点

- 新 C 文件过 C1-C18（malloc 检查、数组边界、clip_h、引用释放路径等）
- **cine 类位置校验**：`y >= LAYER_DIALOG_Y` 或 `x < 0` 拒绝启动并 `hal_log`（C6/C14）
- **cine 类 blit 钳制**：可见高度 `min(h, LAYER_DIALOG_Y - y)`，绝不写入 y ≥ 280（对齐 AGENTS §十一 sprite 对话框约束风格）
- **像素轨 blit 前必须 `vblank_wait()`**（像素轨每帧 + 调色板轨首帧底图），防止「从上往下滚动覆盖 + 撕裂」；调色板轨后续换色仅写 0xA8–0xAE 端口，**禁止**动 VRAM 像素
- **调色板轨首帧**：`base_blitted` 不置位就不能换色；对话框重建只在底图 blit 时执行一次，之后快照保持有效（C18 快路径副作用检查模式）
- **fullscreen 对话框重建**：不得复用动画前的 `dialog_snapshot`/`bg_dialog_snapshot` 过期快照；重建后即时重截取（消灭静默失败，明确日志）
- `waitanim` 唤醒路径必须有明确日志
- 新工具/扩展过 P1-P11（with open、异常类型、路径 Path 等）