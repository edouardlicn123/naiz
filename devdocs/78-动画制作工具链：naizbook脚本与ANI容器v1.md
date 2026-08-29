# 78-动画制作工具链：naizbook脚本与ANI容器v1

> 状态：**活动文档 — 制作侧已实施**（2026-08-21 立稿并当日落地，见 §八实施记录）。本文档细化 devdoc 77 §四 NAIZ_ANIM 的**制作侧**（脚本语法 + 容器格式 + 工具链），并**修订** 77 §4.5 容器定义（新增逐帧 tick 表）与 §4.6 素材组织（目录约定改为 naizbook 脚本驱动）。77 的播放侧章节（§4.7 引擎设计）仍为播放接入时的权威参考，实施顺延。
>
> 决策记录汇总（2026-08-21）：
> - **范围**：仅制作侧。播放命令（anim/waitanim/stopanim）、引擎改动、ASSETS.DB 注册、IMAGE.DAT 打包全部不做，留待播放接入轮次。
> - **语法形态**：每个动画一个 naizbook 脚本（NB 风格），逐帧声明 `图片, 秒数`；花括号载荷（与 `host(){…}` 惯例一致）；头部用 `animconf(){…}` 单行声明。
> - **时长**：逐帧可变（秒），换算 60Hz tick；容器相应新增逐帧 tick 表（对 77 §4.5 的偏离，见 §4.3）。
> - **目录**：仓库根新建 `animation/{naizbook,output}`；脚本平铺单层放 `animation/naizbook/<动画名>.nb`（不按项目分子目录）；素材统一放仓库根 `assets/<项目名>/`（与构建管线同址，如 `assets/animatest/frame001.png`）；脚本内路径相对 `assets/` 解析。（2026-08-21 修订：原 `assets/aniframe/<动画名>/` 约定废止，冒烟夹具 test/glowtest 已删除，由 animatest 项目取代）
> - **产物**：仅生成独立 `.ANI` 文件到 `animation/output/`，不入库不打包。
> - **入口**：新增仓库根 `anima.sh`（仿 makegame.sh 骨架；2026-08-21 升级：无参数进入交互式制作菜单——脚本编号列表 → 操作子菜单 build / build --project（列项目选择）→ Enter 返回，与 makegame.sh 工作流同构；子命令 build/buildall/list 保留供脚本化调用）。
> - **pal 文件格式**：显式索引 4 列 `<index> <R> <G> <B>`（稀疏差异条目），非 77 §4.6 的隐式逐行全表——差异链语义要求可定位条目。

---

## 一、范围与非目标

**做**：
1. naizbook 动画脚本语法定义与解析器
2. `.ANI` 容器 v1 格式（含逐帧 tick 表）
3. 脚本 → `.ANI` 组装工具（Python）+ shell 入口（anima.sh）
4. 测试素材（2 张 PNG）+ 冒烟产物 TEST.ANI + pytest

**不做**（播放接入时另行立档或回填 B92）：
- NB 播放命令 `anim/waitanim/stopanim` 与 `core/engine/nb_anim.c`
- `VMFLAG_ANIMWAIT` / main.c 输入等待守卫 / fullscreen×对话框重建路径
- img_map type='ANI' 注册、pack_images ANI 旁路、image_dat/image_init 校验跳过
- export_asset_table anim_map 导出

## 二、目录布局

```
/home/edo/naiz/
├── animation/                      # ★ 专用动画文件夹
│   ├── naizbook/                   #   动画脚本（平铺单层，每动画一个 .nb）
│   │   └── animatest.nb
│   └── output/                     #   生成的 .ANI
│       └── ANIMATEST.ANI
├── assets/
│   └── animatest/                  # ★ 素材（按项目名，与构建管线同址）
│       ├── frame001.png            #   蓝底黄星（640×400）
│       ├── frame002.png            #   蓝底白星（同位置）
│       └── images.map              #   同批 PNG 兼注册进项目构建管线
└── anima.sh                        # ★ shell 入口（无参数 = 交互菜单）
```

- 两级目录由工具运行时自动创建（`Path.mkdir(parents=True, exist_ok=True)`），无需预置占位文件
- 素材放 `assets/aniframe/` 无构建污染风险：`convert_png_to_mag` 为 images.map 清单驱动（build_game.py:86-88），不扫目录，帧 PNG 不会被误转 MAG
- assets 根定位：`Path(__file__).resolve().parents[2] / "assets"`（tools/naiz_build/*.py 上溯两级 = 仓库根），CLI 可用 `--assets-root` 显式覆盖（测试用）

## 三、naizbook 脚本语法

### 3.1 命令集

pixel 轨示例：

```
# test.nb —— # 整行注释；行内注释在 {} 外生效（与 NB 一致）
animconf(){fullscreen,pixel,once}            # 头部声明，恰好一次
frame(){aniframe/test/frame001.png,0.5}      # pixel 轨帧：路径,秒数
frame(){aniframe/test/frame002.png,0.5}
```

palette 轨示例：

```
animconf(){cine,palette,loop}
base(){aniframe/glow/bg.png}                 # 底图，恰好一次
pal(){aniframe/glow/pal001.pal,0.1}          # 帧调色板差异表,秒数
pal(){aniframe/glow/pal002.pal,0.1}
```

| 命令 | 轨道 | 载荷字段 | 次数 |
|---|---|---|---|
| `animconf` | 两者 | `区域类型,轨道,循环` = fullscreen\|cine , pixel\|palette , loop\|once | 恰好 1 |
| `frame` | 仅 pixel | `<png路径>,<秒数>` | ≥1 |
| `base` | 仅 palette | `<png路径>` | 恰好 1 |
| `pal` | 仅 palette | `<pal路径>,<秒数>` | ≥1 |

### 3.2 解析规则

1. **解析器复用** `naiz_lib/nb_line.parse_nb_line`：`cmd(){payload}` 形式载荷落在 `NbLine.text`，逗号切分由 anim_script 自行完成（nb_line 不切 text）；括号内参数形式 `frame(x)` 不接受（载荷必须走 `{}`，否则按未识别行报错）
2. 行内注释剥离：复刻 nb.c:289-299 的 `{}` 深度感知逻辑（`#` 在 `{}` 外才截断）
3. **文件编码**：UTF-8；容忍 CRLF；UTF-8 BOM 存在则剥离并继续
4. **未知命令**：报错（与引擎 dispatch 的 WARN 不同——制作侧是构建期工具，必须硬失败）
5. **路径解析**：相对 assets 根（即 `frame(){aniframe/x/f.png}` → `<repo>/assets/aniframe/x/f.png`）；解析后 `resolve()` 必须仍在 assets 根之内（拒绝 `..` 越界与绝对路径）
6. **tick 换算**：`ticks = max(1, round(sec*60))`；`abs(sec*60 - ticks) > 0.005` 时输出非整告警（不阻断）；`sec ≤ 0` / 非数 / NaN / inf → 报错
7. **报错风格**：`anim_script: <文件名>:<行号>: <原因>`，`raise SystemExit(1)`（消灭静默失败）

### 3.3 校验规则表

| # | 规则 | 失败处理 |
|---|---|---|
| V1 | animconf 恰好一次且为首条命令（之前允许注释/空行） | 报错 |
| V2 | 三字段枚举合法（fullscreen/cine、pixel/palette、loop/once） | 报错 |
| V3 | 交叉轨命令拒绝（pixel 见 base/pal；palette 见 frame） | 报错+行号 |
| V4 | pixel：frame ≥1；palette：base 恰好 1 且 pal ≥1 | 报错 |
| V5 | 引用文件存在且可解析（PNG 可开；pal 行格式合法） | 报错+行号 |
| V6 | pixel 全帧尺寸一致；fullscreen 必须 640×400；cine 任意但 w,h ∈ [1,640]×[1,400] | 报错 |
| V7 | pal 文件：每行 4 列整数 `<index> <R> <G> <B>`，index∈[0,255]、RGB∈[0,255]，≤256 行，同文件索引重复即报错，`#` 注释与空行跳过 | 报错+行号 |

### 3.4 pal 差异链语义（palette 轨）

- 第 0 帧完整表 = 底图量化色板（256 条）⊕ pal001 覆盖项
- 第 N 帧完整表 = 第 N-1 帧完整表 ⊕ pal(N+1) 覆盖项（链式继承，未列条目沿用）
- 组装时写入容器的仍是**完整 768B/帧**（瘦身存增量属开放项，见 §十二）

## 四、`.ANI` 容器格式 v1（全小端）

### 4.1 头部（28 字节）

```
偏移   类型   字段      说明
0x00   u32   magic    0x5A494E41（字节序 "ANIZ"）
0x04   u16   version  1
0x06   u8    type     0=fullscreen / 1=cine
0x07   u8    track    0=pixel / 1=palette
0x08   u8    fps      标称帧率：全帧 tick 相等 t → round(60/t)；变时长 → 0（round 结果 <1 时取 1，防与变时长标记 0 冲突）
0x09   u8    loop     0=once / 1=loop
0x0A   u16   nframes  帧数
0x0C   u16   w        帧宽
0x0E   u16   h        帧高
0x10   u32   palsz    palette 轨 = nframes×768；pixel = 0
0x14   u32   nblob    pixel = nframes；palette = 1
0x18   u32   reserved 固定 0（补齐 28 字节头）
```

### 4.2 区段顺序（偏移均相对文件首）

```
帧偏移表   nblob × u32   各 MAG 块起始
tick 表    nframes × u16 每帧 60Hz tick 数（≥1）★ 本版新增
帧数据     nblob × MAG   mag_codec.encode_mag(bpp=8, user_string=b"naiz\x1a")
调色板表   [palette 轨]  nframes × 768 原始 RGB（R,G,B 序）
```

> tick 表紧随偏移表（固定偏移 `28+nblob×4`）：引擎无需解析任何 MAG 头即可 O(1) 寻址帧时长。
> 调色板表紧随末块之后、**无间隙**（parse_ani 按末块终点定位调色板表；build_ani 保证此布局）。

### 4.3 与 devdoc 77 §4.5 的差异

| 项 | 77 §4.5 | 本版 v1 | 原因 |
|---|---|---|---|
| 帧时序 | 固定 fps（60 约数集） | **逐帧 u16 tick 表**；fps 字段退化为标称值 | naizbook 语法天然支持逐帧可变时长 |
| fps 合法集校验 | 导入器+引擎双校验 | 取消硬校验；tick≥1 即合法 | 变时长下无单一 fps |
| 素材组织 | 目录约定 frame_NNN.PNG | naizbook 脚本显式声明 | 用户决策 |
| 区段顺序 | 偏移表→MAG→调色板 | 偏移表→**tick 表**→MAG→调色板 | tick 表定位于固定偏移，引擎免解析 MAG 长度即可寻址 |
| pal 输入 | 隐式逐行全表 | 显式索引稀疏差异文件 | 差异链语义需要可定位条目 |

### 4.4 装载校验细则（供播放侧实施时引用）

| # | 校验 | 失败处理 |
|---|---|---|
| L1 | magic == 0x5A494E41 且 version == 1 | 拒载+日志 |
| L2 | type ≤1、track ≤1 | 拒载+日志 |
| L3 | nframes ≥1；pixel: nblob==nframes 且 palsz==0；palette: nblob==1 且 palsz==nframes*768 | 拒载+日志 |
| L4 | 偏移表逐项 ≥ 28+nblob×4+nframes×2 且 < len(data)；末块 offset+块长(MAG 头解析) ≤ len(data) | 拒载+日志 |
| L5 | tick 表逐项 ≥1 | 拒载+日志 |
| L6 | fullscreen: w==640 且 h==400；cine 播放位 y+h≤280 由启动参数校验 | 拒启+日志 |

## 五、工具链实现

### 5.1 `tools/naiz_lib/anim_container.py`（新增，库层）

仿 `image_dat.py` 先例：二进制格式的唯一权威实现，不含文件 IO 与业务逻辑。

```python
ANI_MAGIC = 0x5A494E41
ANI_VERSION = 1
ANI_HEADER_SIZE = 28

@dataclass
class AnimContainerDef:
    type: int                    # 0=fullscreen / 1=cine
    track: int                   # 0=pixel / 1=palette
    loop: int                    # 0=once / 1=loop
    width: int
    height: int
    blobs: list                  # list[bytes]，MAG 块（pixel: nframes 个；palette: 1 个）
    ticks: list                  # list[int]，len == nframes，每项 ≥1
    palettes: object             # palette 轨: list[bytes] 每个 768B；pixel 轨: None

    @property
    def fps_nominal(self) -> int  # 全帧 tick 相等 t → round(60/t)，否则 0
    @property
    def nframes(self) -> int
    @property
    def palsz(self) -> int
    @property
    def nblob(self) -> int

def build_ani(def_: AnimContainerDef) -> bytes
    # 组装前自检 L3/L5（内部一致性），违者 ValueError
def parse_ani(data: bytes) -> AnimContainerDef
    # L1–L5 全量校验，失败 raise ValueError("anim_container: <偏移/字段>: <原因>")
```

### 5.2 `tools/naiz_build/anim_script.py`（新增，解析层）

```python
@dataclass
class AnimStep:
    kind: str          # 'frame' | 'pal'
    path: str          # 脚本中的原始路径串
    resolved: Path     # 相对 assets 根解析后的绝对路径
    seconds: float
    ticks: int
    line: int          # 脚本行号（报错用）

@dataclass
class AnimScriptDef:
    name: str          # 脚本 stem（如 "test"）
    type: str          # 'fullscreen' | 'cine'
    track: str         # 'pixel' | 'palette'
    loop: bool
    base: Path | None  # palette 轨底图绝对路径
    steps: list        # list[AnimStep]
    warnings: list     # tick 非整告警等（不阻断）

def parse_anim_script(script_path: Path, assets_root: Path) -> AnimScriptDef
    # 按 §3.2/§3.3 解析+校验；失败 SystemExit(1)（带 文件:行号）
```

- 解析器保持纯文本职责：不做 PNG/pal 内容加载（内容校验在组装层，V5 的存在性检查除外）

### 5.3 `tools/naiz_build/anim_import.py`（新增，CLI 组装层）

```
用法: python -m tools.naiz_build.anim_import <script.nb>
             [--out PATH] [--project GAME] [--assets-root DIR]
```

流程：

1. `parse_anim_script` 得定义
2. 加载图像：
   - PIXEL 帧 / palette 底图：PIL 打开 → RGB → `mag_convert.convert_image(no_resize=True, num_colors=256, bpp=8)` → `decode_mag_full` 取 `(pixels, w, h, own_pal)`
   - pal 差异链补全按 §3.4
3. **PIXEL 轨共享调色板重映射**：
   - `--project G`：读 `projects/G/ASSETS.DB` img_map 全部 IMG/SPR 行 → 加载各 MAG → `decode_mag_full` → 复用 `pack_images.build_shared_palette` 推导共享色板 → `remap_pixels_to_palette(..., protected_indices=PROTECTED_IDX)` 逐帧重映射 → 以共享色板 `encode_mag(bpp=8, user_string=b"naiz\x1a")`
   - 缺省：以动画自身帧量化色板编码，输出**醒目警告**（播放时若场景共享色板不同则颜色会偏；项目后续新增 IMG/SPR 后需重导入）
4. palette 轨：底图以自身量化色板编码为唯一 blob；nframes×768 完整表追加尾部
5. `anim_container.build_ani` 组装 → 写 `--out`（缺省 `animation/output/<STEM大写>.ANI`，目录自动创建）
6. 尺寸报表（stdout）：

```
=== ANI 组装报告: TEST ===
  type=fullscreen track=pixel loop=once  640x400  2 帧  总时长 1.000s
  帧 1  frame001.png  tick=30 (0.500s)  MAG 24,381 B
  帧 2  frame002.png  tick=30 (0.500s)  MAG 23,974 B
  容器: 48,431 B（头 28 + 偏移表 8 + 块 48,355 + tick 表 4）
  原始 RGBA 参考: 512,000 B → 压缩率 9.5%
  调色板: 共享色板 (--project demo-a2)
→ animation/output/TEST.ANI
```

规约：P1–P11 全过（with-open、Path 对象、顶层 import、无裸 except、无 assert、无 shell=True）。

### 5.4 `anima.sh`（新增，仓库根）

```bash
用法:
  anima.sh                           # 交互式制作菜单（无参数时）
  anima.sh build <name>              # animation/naizbook/<name>.nb → animation/output/<NAME>.ANI
  anima.sh buildall [--project G]    # 编译 naizbook/ 下全部脚本（汇总结果）
  anima.sh list                      # 列出可用动画脚本
```

骨架照搬 makegame.sh：

- `set -euo pipefail`
- `ROOT="$(cd "$(dirname "$0")" && pwd)"` + `core/engine/main.c` 存在性校验（S4）
- `source tools/env_setup/ensure_venv.sh` 注入 `$VENV_PYTHON`，缺失时报错提示 `bash start.sh pip`
- 子命令 case + 中文 usage；flag 用数组条件追加透传（S7）；全部变量引用（S1）
- 纯 Python 工具链，无 watcom 依赖（不需要 check_wcl386）
- `buildall`：逐个执行，单脚本失败不中断，末尾汇总 `N ok / M failed`，M>0 则 exit 1

**交互菜单**（2026-08-21 升级，镜像 makegame.sh 工作流）：无参数进入两层循环——外层列出 `animation/naizbook/*.nb`（编号选择，默认 1，0 退出）；内层为选中脚本的操作子菜单（1=build 自身色板 / 2=build --project 列 projects/ 二级选择 / 0 返回），动作复用子命令、按 Enter 返回。与 makegame 的唯一偏差：动作用 `if ! "$0" build …` 包裹，构建失败显示错误后回菜单而非退出整个脚本（实验工具频繁试错）。

## 六、测试素材与冒烟验证

> **2026-08-21 注**：本节记录的 test/glowtest 冒烟夹具（`assets/aniframe/`、对应 .nb 与 .ANI）已删除，由 **animatest 项目**取代为现行示例（蓝底黄星/白星 640×400 对，`assets/animatest/frame00{1,2}.png` + `animation/naizbook/animatest.nb`，双路构建断言均过）。下文保留为历史验证记录。

| 产物 | 规格 |
|---|---|
| `assets/aniframe/test/frame001.png` | 640×400 RGB，红底 (200,30,30) 白圆（圆心居中 r=120），PIL 生成 |
| `assets/aniframe/test/frame002.png` | 640×400 RGB，蓝底 (30,60,200) 黄三角 (255,210,0)，与 A 视觉差异明显 |
| `animation/naizbook/test.nb` | `animconf(){fullscreen,pixel,once}` + 两行 frame()，各 0.5s |
| `animation/output/TEST.ANI` | `./anima.sh build test` 冒烟产物 |

- PNG 由 venv 内 PIL 一次性生成（临时脚本跑完即弃，不新增长期工具）
- 冒烟回读断言清单：
  1. magic/version/type/track/loop/nframes=2/w=640/h=400/palsz=0/nblob=2
  2. fps 标称 = round(60/30) = 2
  3. 偏移表两项严格递增且首项 ≥ 28+2×4=36、末项+块长 ≤ 文件长
  4. tick 表字节精确 = `[30, 30]`（LE u16 ×2，位于 28+8）
  5. `mag_decode(blob_i)` 成功且 w/h 一致；**中心像素取色**：帧1 ≈ 白 (255,255,255)、帧2 ≈ 黄 (255,210,0)（容差 ±8）。
     注：默认路径经 `convert_image(reserved=PROTECTED_IDX_ALL)`，MAG 内嵌色板的保留槽位（7/15/248-255）按管线约定置黑、白色像素迁移至非保留索引——故不能断言 idx7 为白；`--project` 共享色板路径下 idx7 恒为白。

### 6.1 palette 轨冒烟（glowtest，2026-08-21 补验）

素材（PIL 一次性生成）：`assets/aniframe/glowtest/base.png`（64×64 cine 底图）+ `pal001.pal`（固定索引覆盖 10→红、11→绿）+ `pal002.pal`（追加 20→蓝，不触碰 10/11）；脚本 `animation/naizbook/glowtest.nb`（cine/palette/loop，各 0.1s）。

回读断言（全部通过，产物 GLOWTEST.ANI 2,621 B）：
1. 头部 type=1/track=1/loop=1/nblob=1/nframes=2/palsz=1536/w=h=64/fps 标称=10；tick 表 `[6,6]`
2. **链式继承**：帧1 表 idx10=(255,0,0)、idx11=(0,255,0)；帧2 表 idx10/11 保持红绿（继承自 pal001）、idx20=(0,0,255)
3. 两帧表差异条目集合恰为 `{20}`——未覆盖条目逐字节不变
4. 底图 blob 解码 64×64 bpp=8

> 固定索引法要点：断言目标索引（10/11/20）不依赖量化结果，且避开保留槽位（7/15/248-255），断言完全确定。pixel 轨与 palette 轨组装路径至此均已端到端验证。

## 七、pytest 测试计划

| 文件 | 覆盖 |
|---|---|
| `tools/tests/test_anim_script.py` | 正例：pixel/palette 最小脚本、变时长 tick 换算（0.5→30、0.1→6、0.016→1）、行内注释剥离、loop/once 枚举、CRLF/BOM 容忍；反例：V1–V7 各分支、缺 animconf、重复 animconf/base、交叉轨命令、sec≤0/NaN、路径越界 assets 根、未知命令、pal 索引越界/重复 |
| `tools/tests/test_anim_container.py` | 合成小容器（真实 encode_mag 小帧）：头部字段字节精确、L3 内部一致性拒收、偏移单调有界、tick 表 LE 字节、palette 表字节、L1–L5 各拒载分支、parse↔build 往返一致 |

测试风格遵循现有约定：conftest.py 已注入 sys.path；扁平 `test_*` 函数 + `pytest.mark.parametrize` + tmp_path 构造素材。

## 八、实施顺序

1. [x] `naiz_lib/anim_container.py`（格式权威实现）
2. [x] `naiz_build/anim_script.py`（解析器）
3. [x] `naiz_build/anim_import.py`（组装 CLI）
4. [x] `anima.sh`
5. [x] pytest 两件套 → 全绿
6. [x] 测试素材生成 + test.nb + `./anima.sh build test` 冒烟 + 回读断言
7. [x] 文档同步（§十）+ 版本号 + fullaudit

### 实施记录（2026-08-21）

- 新增文件：`tools/naiz_lib/anim_container.py`、`tools/naiz_build/anim_script.py`、`tools/naiz_build/anim_import.py`、`anima.sh`、`tools/tests/test_anim_{container,script}.py`
- 素材/产物：`assets/aniframe/test/frame00{1,2}.png`、`animation/naizbook/test.nb`、`animation/output/TEST.ANI`（19,831 B，压缩率 1.0%）
- 验证：新增 65 例 pytest 全绿（全量 243 绿）；冒烟回读断言全过；`--project demo-a2` 共享色板路径 idx7 白 ✓；`./start.sh fullaudit` 6/6 通过；版本 0.2.037 → **0.2.038**
- 实施中修订本文档两处（见 §4.1/§4.2/§4.3 与 §六）：① tick 表定位于偏移表之后（固定偏移 `28+nblob×4`，引擎免解析 MAG 长度即可寻址帧时长）；② 冒烟断言 5 改为中心像素取色——默认路径经 `convert_image(reserved=PROTECTED_IDX_ALL)`，MAG 内嵌色板保留槽位按管线约定置黑，不能断言 idx7 为白

## 九、验证命令

```bash
tools/env_setup/venv/bin/python -m pytest tools/tests/
python -m py_compile tools/naiz_lib/anim_container.py \
                     tools/naiz_build/anim_script.py \
                     tools/naiz_build/anim_import.py
bash -n anima.sh
./start.sh fullaudit
python -m tools.naiz_build.bump_version demo-a2
```

## 十、文档同步（实施落地时执行）

- `docs/B92-NB脚本命令参考.md` §3：naizbook 语法 + .ANI v1 格式（含 tick 表偏离说明）
- `docs/B90-参考-函数索引.md`：anim_container/anim_script/anim_import 三模块条目
- `docs/B91-构建环境与参考速查.md`：anima.sh 入口与 animation/ 目录约定

## 十一、防复发要点

- Python 侧 P1–P11 逐一过（重点：P2 with-open、P3 assert→RuntimeError、P6 Path、P8 顶层 import、P10 sys.exit(1)+print）
- anima.sh 过 S1–S7（全变量引用、数组条件追加、无 eval/readlink/which、shift 前查参）
- 二进制读写全走 `struct` 显式小端；parse 侧逐项边界检查（L1–L5，对应 C6/C24 思想）
- 所有失败路径显式报错（文件名+行号/字段偏移），消灭静默失败
- PIXEL 轨重映射缺省路径必须输出颜色偏差警告（C18 快路径副作用思维：默认路径不得伪装等价）
- `build_shared_palette`/`remap_pixels_to_palette` 从 pack_images **import 复用**，禁止复制实现（先借后造；两处实现漂移会导致导入色板 ≠ 打包色板）

## 十二、开放项

- [ ] palette 轨容器内是否存增量条目而非完整 768B/帧（当前存全表；瘦身沿袭 77 开放项，待播放侧定版）
- [ ] MAG vs 专用 RLE 帧编码权衡（沿袭 77；以 TEST.ANI 及后续真实素材尺寸报表为判定依据）
- [ ] 打包入库三件套（img_map type='ANI' + pack_images 旁路 + image_dat/image_init 校验跳过）——播放接入轮次实施
- [ ] cine 尺寸多样性下的播放位校验（y+h≤280）属引擎侧，届时随 nb_anim 落地
- [ ] `--project` 共享色板推导的资产集快照机制（当前依赖导入时点，资产变更需重导入；可选：把推导所用资产 id 清单写入 .ANI 旁注或 sidecar 文件以便检测过期）
