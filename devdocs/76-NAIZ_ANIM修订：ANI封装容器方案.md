# 76-NAIZ_ANIM 修订：ANI 封装容器方案

> ⚠️ **已过时，仅供参考。** 已由 `devdocs/77-动画与转场系统统一文档.md` 取代并合并，仅存留作历史记录，勿作为实施依据。
>
> 状态：**规划稿 v1**（可作为后续补充细节的基础，补充完成前不视为定稿）
> 决策记录：基于 devdoc 73 的双轨（PIXEL/PALETTE）× 双型（fullscreen/cine）架构，**采纳 73 暂缓的方案 C（SPS 式单文件打包多帧）**，参考 `~/unlove`（Love/Escalator 反编译项目）打包容器概念，确立 **naiz 自建 `.ANI` 动画容器**。
> 2026-08-20 四项决策：① 格式取向 = naiz 自建 .ANI（不与 Love 位级兼容）；② 调色板轨数据 = 容器内嵌原始表，旁路共享调色板不变量；③ 落地 = 新写本文档取代 73（73 保留为历史存档，不改写）；④ 帧编解码 = 复用 MAG（mag_codec/mag_decode）。

---

## 一、背景与修订缘由

### 1.1 devdoc 73 原案要点

- 需求：类 galgame opening 的序列帧动画，逐帧前进、一次性/循环、与 NB 脚本同步（`waitanim` 阻塞）、fps 可控
- 双型：**fullscreen**（占满 640×400，对话框已开走重建路径）/ **cine**（仅对话框上方 `y+h ≤ 280`，永不触对话框区）
- 双轨：**PIXEL**（每帧整图替换 + `vblank_wait()` 硬约束）/ **PALETTE**（底图 blit 一次、每帧仅写调色板端口，循环首选、零撕裂）
- 命令：`anim` / `waitanim` / `stopanim`，`nb_process()` 帧首挂 `anim_tick()`
- **暂缓项（方案 C）**：单文件打包多帧（SPS 式）——当初判定为「可选存储优化，与显示逻辑解耦」

### 1.2 unlove 调研结论（引用依据）

`~/unlove` = 商业游戏 Love（Escalator）反编译项目，`extracted/LOVE/EAR_FILES/` 实证：

| 格式 | 数量 | 事实（已实测） |
|---|---|---|
| `.ECG` | 702 | 单帧整图；头 4 字节魔数 **`5A 46 43 1A`（"ZFC\x1a"）**；数据 ~6–20KB/帧（原始 256KB，极高压缩率） |
| `.SPS` | 11 | **单文件打包多子图容器**（MOUSE/BOOTMENU/NAMEENT/DTSELECT/OPTMUS/OPTCG*）；如 OPTCG.SPS=u32 count(16)+子图偏移(0x41E0/0x8388/0xC5F4)+子图数据，子图头 `10 1c XX fa 00 10` 模式 |
| `.PCL` | 89 | 调色板重映射表：头部后一串 `0x77 (from,to)` 索引对 |
| `.EQA` | 63 | 编排脚本（资源加载 + 跳转 + 调色板写命令 `52/50/54`），驱动 OP 逐帧切换 |

**关键结论**：
1. Love 的动画主体是「SPS/ECG 打包容器 + PCL 调色板轨迹 + EQA 脚本驱动时序」
2. **上游 RE 完整性不足**：unlove 的 EQA 指令语义仍标「假设」、`STAGE_3/README` 明确「ECG 格式未知」，ecg 解码为试探性启发式且未确认 → **Love 逐字节格式不可产出，位级兼容不可行**
3. devdoc 73 §四.2「OPTCG = 头部 N×u32 偏移表」与实测（偏移段长度 ≠ count）**不完全吻合**，因此 73 的 SPS 描述仅作**概念参考**，不作格式蓝本

### 1.3 naiz 侧管道约束（影响容器设计）

- `pack_images.py` 对 **ALL** img_map 条目构建**共享调色板**并逐图 remap；`image.c` 加载后 `image_set_palette` → **调色板轨（每帧独立 256×3 表）与共享调色板不变量冲突**
- 结论：调色板轨的每帧调色板表**不能走 img_map/MAG 共享调色板路径**，必须存入 `.ANI` 容器内作为原始数据旁路

---

## 二、帧数定义（60Hz 基准）

PC-98 标准 640×400 非隔行模式 = 水平 24.8kHz、**垂直同步 ≈ 60Hz**；引擎以 `hal_vblank_wait()` 为每帧节拍 → 动画更新以 60Hz 为基准，上限 60fps。

### 2.1 fps 合法集

`fps` 必须是 60 的整约数（`tick = 60/fps` 恒定整数，60Hz CRT 无 cadence 抖动）：

```
{ 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60 }
```

- 非约数（如 24）：**拒绝**。`anim_import.py` 导出时显式报错；引擎 `anim_start` 二次校验 `hal_log` 拒播
- `{1..6}` 慢节奏仅限调色板轨循环特效（呼吸/闪烁/明暗），导入器输出警告日志
- 未传 `--fps` → 按下表默认档

### 2.2 默认与允许档

| 区域 type | 轨 track | 默认 fps | 允许档 | 备注 |
|---|---|---|---|---|
| fullscreen (640×400) | PIXEL | **12** | 10 / 12 / 15 | 全帧 MAG 解码 + 整幅 blit 需多个 vsync 窗口，486 上限档 |
| fullscreen | PALETTE | **30** | 30 / 60 | 每帧仅调色板端口写（768 字节），可满帧 |
| cine (y<280) | PIXEL | **20** | 15 / 20 / 30 | 区域小、blit 快，可爬高 |
| cine | PALETTE | **30** | 30 / 60 | 同全屏调色板轨 |

---

## 三、ANI 容器格式（v1，全小端）

```
Header（28 字节）
  0x00  magic   u32   0x5A494E41  ("ANIZ")
  0x04  version u16   1
  0x06  type    u8    0=fullscreen / 1=cine
  0x07  track   u8    0=pixel / 1=palette
  0x08  fps     u8    须为 60 的整约数（§2.1）
  0x09  loop    u8    0=一次 / 1=循环
  0x0A  nframes u16   帧数
  0x0C  w       u16   帧宽（导入校验用）
  0x0E  h       u16   帧高
  0x10  palsz   u32   palette 轨 = nframes×768；pixel = 0
  0x14  nblob   u32   数据块数：pixel = nframes；palette = 1（仅底图）

帧偏移表   nblob × u32      各 MAG 数据块首字节（相对文件头）
帧数据     nblob × MAG      MAG 编码帧（复用 mag_codec；pixel 帧共享场景调色板语义=SPR）
调色板表   [palette 轨]     nframes × 256 × 3 原始 RGB（旁路共享调色板不变量）
```

说明：
- PIXEL 轨：每块 = 一帧 MAG（帧共享场景调色板，与 SPR 资产同一语义）；`palsz=0`
- PALETTE 轨：仅一块底图 MAG + 尾部 per-frame 调色板表；换帧只读表
- 尺寸/type/track/fps/loop 均以容器头为准（脚本不传 track/fps）

---

## 四、数据管线

### 4.1 素材组织（内容方输入，与 73 相同）

```
PIXEL 轨： projects/<game>/anim/<片段名>/frame_001.PNG  frame_002.PNG …
PALETTE 轨：projects/<game>/anim/<片段名>/base.PNG  pal_001.pal  pal_002.pal …
```

- 文件名按字典序即播放顺序（建议两位以上补零）；同段帧尺寸一致（fullscreen=640×400；cine 任意）
- PALETTE 轨 `pal_*.pal`：每帧 256 行 "R G B"；可只含差异条目，工具补全为完整 256 表

### 4.2 anim_import.py（新增 `tools/naiz_build/`）

- 入参：`<project> <anim_dir> --name <名字> [--type fullscreen|cine] [--track pixel|palette] [--fps N] [--loop]`
- PIXEL：帧 PNG 按字典序 → `naiz_lib/mag_codec` 编码（共享场景调色板）→ 组装 `.ANI` → 输出 `projects/<game>/anim/<name>.ani`
- PALETTE：`base.PNG` 转 MAG + `pal_*.pal` 解析为 per-frame 表 → 组装 `.ANI`
- 校验：帧尺寸一致、**fps ∈ 合法集（§2.1）**、palette 表条目补全、色表一致性
- 遵守 Python 规约（P1–P11：with open、异常类型、Path 对象等）

### 4.3 ASSETS.DB / pack_images.py

- `img_map.type` 文本增 `'ANI'`（无 DDL 变更）
- `pack_images.py`：`type='ANI'` 行**跳过** `build_shared_palette` 构建与逐图 remap、跳过 `decode_mag_full` 校验；原样写入**单条 TOC**（`*.ANI` 名，8.3）
- 校验点：ANI 条目在 pack_images/export/build **全链路禁止当作 IMG/SPR 处理**

### 4.4 export_asset_table.py

- 新增 `anim_map`（`SELECT id, name FROM img_map WHERE type='ANI'`）
- 生成 `core/engine/nb_asset_table.h`（anim_map）或独立 `nb_anim_table.h`（`AnimDef` 数组引用 ANI asset id）

---

## 五、引擎设计

### 5.1 新文件

- `core/engine/nb_anim.h`：`AnimDef`/`AnimDefType`/`AnimTrackType`/`AnimState`、`anim_tick()`、`anim_start/stop/wait`、命令处理函数声明
- `core/engine/nb_anim.c`：实现（命令注册进 cmd_table，独立文件先例：nb_scene.c/nb_question.c）
- 动画表：`nb_asset_table.h`（anim_map）或 `nb_anim_table.h`（Makefile 依赖条目）

### 5.2 类型与状态

```c
typedef enum { ANIM_TYPE_FULLSCREEN = 0, ANIM_TYPE_CINE = 1 } AnimDefType;
typedef enum { ANIM_TRACK_PIXEL = 0, ANIM_TRACK_PALETTE = 1 } AnimTrackType;

typedef struct {
    int          active;
    const AnimDef *def;
    int          frame;        /* 当前帧下标（palette 轨 = 调色板表下标） */
    int          tick;         /* 帧间隔剩余计数 = 60/fps */
    AnimDefType  type;
    AnimTrackType track;
    int          x, y;         /* cine: 起始坐标；fullscreen: 固定 (0,0) */
    int          w, h;
    int          base_blitted; /* palette 轨：底图是否已 blit */
    MagImage    *img;          /* 当前帧 mag_retain 引用，收尾 release */
} AnimState;
static AnimState g_anim;       /* 全局单一活动动画 */
```

### 5.3 image.c 容器读取辅助

- IMAGE.DAT TOC 无 type 字段 → 引擎经 `anim_map` 拿 ANI asset id，用独立辅助**按 id 取 TOC 原始块**（校验落在 `g_image_data` 范围内）
- ANI 条目不触发 `image_set_palette`（不经 `image_load` 的 is_sprite 判定路径）

### 5.4 NB 命令（注册进 cmd_table）

- `anim(type, 名字, [x, y])`：type ∈ `fullscreen`/`cine`；查 anim 表启动（track/fps 取容器头，脚本不传）；已有活动动画先 `stopanim`；首帧立即绘制；cine 校验位置（越 280 拒启 + `hal_log`）
- `waitanim`：阻塞语义（复用 `vm_pause_process` 风格）；停止/播完续行
- `stopanim`：释放当前帧引用、清 active；fullscreen 后切静态背景时显式收尾

### 5.5 每帧推进（nb_process 帧首调 anim_tick）

- `anim_tick()`：未活动直接返回；`tick--` 至 0 则 `frame++`（间隔 = 60/fps），到末帧按 loop 回卷或停止（释放引用，waitanim 唤醒）
- 换帧按 track 分派：
  - **PIXEL**：按 type 走 §六像素路径（整帧 blit + 区域边界处理 + 对话框重建）
  - **PALETTE**：每帧仅 `palette_set_all(每帧表)`；第一帧负责 blit 底图（`base_blitted` 置位）

### 5.6 内存策略

- **PIXEL**：容器一次装载（TOC 块指针），逐帧 `mag_decode` + `mag_retain`/`mag_release`，仅持当前帧
- **PALETTE**：底图 `MagImage` 只取一次持有；每帧调色板表为容器内静态段（768 字节/帧）
- 不做全帧预载；**LRU 例外**：动画帧**不经 image_cache**（避免逐帧污染 8 槽缓存）——与 73 声明微调
- cine/fullscreen 均逐帧解码，仅当次帧驻留

---

## 六、对话框 × fullscreen / cine 交互（沿用 73 §5.6/5.7）

- **cine 像素轨**：`vblank_wait()` → `layer_bg_restore_rect` 恢复旧区 → `vram_blit_sprite`（clip_h 按 `calc_sprite_clip_h` 钳制，**绝不写入 y ≥ LAYER_DIALOG_Y**）→ 不触碰 dialog/bg_dialog snapshot
- **fullscreen 像素轨**：`vblank_wait()` → `vram_blit(全幅)` → 若 `layer_dialog_drawn()` 执行对话框区域重建（更新 `bg_dialog_snapshot`/伪半透明合成/文本重绘/即时重截取快照）——**不得复用动画前过期快照**
- **调色板轨**（type 任意）：仅底图 blit 时执行一次对话框重建；之后每帧只换色，对话框随整体变色，快照保持有效
- **通用硬约束**：任何动 VRAM 像素的帧（PIXEL 每帧、PALETTE 首帧底图）blit 前必须 `vblank_wait()`
- 全屏动画期间 `bg`/`scene_end` 会破坏动画源 → 脚本须先 `stopanim`

---

## 七、验证

1. `make -C core`：0 errors / 0 warnings（`wildcard engine/*.c` 自动收录 nb_anim.c）
2. `tools/env_setup/venv/bin/python -m pytest tools/tests/`
3. `./makegame.sh build demo-a2`（data 构建 + HDI 注入）
4. NP2kai 实机目检：
   - PIXEL fullscreen：一段 OP（无对话 / 有对话字幕）
   - PIXEL cine：对话框上方区域动画，验证不越 280、对话框不被扰动
   - PALETTE fullscreen + cine：循环零撕裂、像素只 blit 一次、对话随整体变色
5. 串口日志（`makegame.sh test demo-a2 --serial`）：anim 启动/换帧/结束 + cine 越界拒启日志

---

## 八、实施顺序

1. 本文档（76）成稿 → 本篇先行，后续补充细节
2. 工具层：`anim_import.py` + `pack_images.py` ANI 旁路 + `export_asset_table.py` anim_map → pytest
3. 引擎：`image.c` 容器读取辅助 + `nb_anim.h/c` + 命令注册 + tick 挂载 → `make -C core` 0/0
4. 内容：demo-a2 像素轨（fullscreen/cine）+ 调色板轨样例 → `./makegame.sh build` → NP2kai 目检 + 串口
5. 文档与版本：B90（函数/工具索引）、B92（anim 命令 + §3 .ANI 格式/§2 帧数表）、`bump_version`

---

## 九、防复发要点

- 新 C 文件过 C1–C25（malloc 检查、数组边界、clip_h、引用释放路径等）
- **cine 位置校验**：`y >= LAYER_DIALOG_Y` 或 `x < 0` 拒绝启动并 `hal_log`（C6/C14）
- **cine blit 钳制**：可见高度 `min(h, LAYER_DIALOG_Y - y)`，绝不写入 y ≥ 280（对齐 AGENTS §十一）
- **像素轨 blit 前必须 `vblank_wait()`**；PALETTE 后续换色仅写调色板端口，**禁止**动 VRAM 像素
- **PALETTE 首帧**：`base_blitted` 不置位不能换色；对话框重建只在底图 blit 时执行一次（C18 快路径副作用检查模式）
- **fps 合法性**：导入器 + 引擎双重校验（60 约数集 §2.1），非约数显式报错/拒播
- **shared-palette 旁路**：ANI 条目在 pack_images/export/build 全链路不得当作 IMG/SPR 处理
- **fullscreen 对话框重建**：不得复用动画前 `dialog_snapshot`/`bg_dialog_snapshot` 过期快照；重建后即时重截取（消灭静默失败，明确日志）
- `waitanim` 唤醒路径必须有明确日志
- 新工具/扩展过 P1–P11

---

## 十、与 devdoc 73 的差异表

| 项 | 73 原案 | 76 修订 |
|---|---|---|
| 动画文件 | 逐帧 `frame_*.PNG` 单独入 img_map + 外部 pal 文件 | **单个 `.ANI` 封装容器**（头+偏移表+MAG 帧+可选调色板表） |
| 资产注册 | 每帧一个 asset id | **ANI 整体一个新资产类型**（img_map type='ANI'） |
| IMAGE.DAT | 逐帧 TOC 条目 | 单 TOC 条目（ANI 块），**排除共享调色板 remap** |
| 引擎加载 | 逐帧 `image_load(id)` | 容器一次装载 + 偏移表逐帧解码 / 读调色板表 |
| anim_defs | frames 帧 id 数组 | 单 ANI asset 引用 + 头内帧率/尺寸 |
| 帧编解码 | — | **复用 MAG**（mag_codec/mag_decode） |
| LRU | 「LRU 8 槽沿用」 | 动画帧**不经 image_cache**（防污染） |
| fps | 示例 24 / 6（非 60 约数） | **严格 60 约数集** + 默认档（§2） |

---

## 十一、待补充细节（占位）

后续迭代补充项（按需追加）：
- [ ] anim 命令与 NB 脚本集成细节（参数校验、错误分支、与 `bg` 交互时序）
- [ ] 循环动画回卷语义（末帧过渡、回卷时期间调色板/背景行为）
- [ ] 对话框重建状态机细化（§6 全屏 + 对话的每帧重建流程伪代码）
- [ ] 容器 `nblob`/偏移表边界校验细则（C6/C24，防畸形 .ANI）
- [ ] `.ANI` 与 IMAGE.DAT TOC 名称映射（8.3 `*.ANI`）与 asset id 分配规则
- [ ] mag_codec 编码参数字（共享调色板 remap 时 per-frame 一致性保证）
- [ ] **帧编码权衡（决策④复核：MAG vs 专用 RLE）**：
  - 现状：决策④ = 帧数据复用 MAG（`mag_codec` 编码 / 引擎 `mag_decode` 解码，4bpp+filter+RLE 码流）；全屏 640×400 原始 128KB，压缩后约 20–50KB/帧
  - 触发点：若内容规模大（如几十帧全屏 OP）导致 `.ANI` / IMAGE.DAT 镜像明显膨胀，可评估**专用轻量帧压缩**（类 Love ECG 全屏 6–20KB 量级），代价 = 新增一套 .c/.py 编解码器、维护双码路，且与现有 img 管线解耦
  - 判定依据：demo-a2 各轨素材**实测压缩后总量**（导入器输出 .ANI 尺寸报表）后再定；未定版前维持 MAG
  - 落点：定版后写入 `docs/B92 §3` 的 .ANI 格式定义（帧编码字段）
- [ ] **调色板瘦身技术组合**：
  - ① **PALETTE 轨帧表 → 差异条目（默认启用）**：`.ANI` 存 `(index, r, g, b)` 增量而非完整 256×3=768B 表（`pal_*.pal` 本就支持只列改动条目，导入器补全）；典型闪烁 8–16 色 → 16–48B/帧；引擎新增 `palette_apply_delta()`（palette.c 现仅全表写/插值）
  - ② **PIXEL 轨剥离 MAG 内嵌调色板段（v1 不启用）**：MAG(MAKI02) 内嵌 256×3 调色板段（GRB 变位深，头部据此定位像素流）；每帧省 ~768B，但需「像素流变体」新编解码路径，成本高 → v1 仅由导入器尺寸报表监测，不拆解
  - ③ **引擎侧参数化调色板特效（后置）**：亮度/暗度斜坡、色相旋转、循环延迟由底图+头参数推导、per-frame 表→0；偏离「逐帧任意配色」，限特效族
  - 佐证：`anim_import.py` 输出 `.ANI` 尺寸报表（各段/表/差异条目占比），兼作帧编码权衡判定依据
  - 落点：定版后写入 `docs/B92 §3` 的 .ANI 格式定义（调色板表编码字段）
- [ ] 内容样例规格（demo-a2 各轨素材尺寸/帧数清单）