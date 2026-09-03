# B92 — NB 脚本命令参考 & 关键常量

> **状态**：活跃维护
> **最后更新**：2026-08-07（从 AGENTS.md §15.4/15.3 聚合）
>
> 本文是 NB 脚本命令的**唯一集中参考源**，并收录引擎关键常量速查。
> 命令处理函数的 C 实现索引见 `docs/B90-参考-函数索引.md`。

---

## 1. NB 脚本命令参考

命令表 `cmd_table[]` 定义位置：`core/engine/nb.c`

| 命令 | 处理函数 | 签名 | 说明 |
|---|---|---|---|
| `bg` | `cmd_bg` (nb.c) | `bg <asset_key>` | 加载背景，capture_bg |
| | | `bg(hidedialog)` | 关闭对话框，还原背景区域 |
| `char` | `cmd_char` (nb.c) | `char <name> <l\|c\|r> [expr] [body\|face]` | 显示/替换立绘，auto-detect body/face |
| | | `char(hideall)` | 隐藏所有立绘 + clean reset |
| `scene` | `cmd_scene` (nb.c) | `scene <id\|"end">` / `scene <var,op,val,target;...;default>` | 无条件/条件链跳转，id → nbook{id}.nb。默认值约定：最后一段无逗号→显式默认；无显式默认→fallback 到第一段 target |
| `sceneconf` | `cmd_sceneconf` (nb.c) | `sceneconf <title>[,type]` | 场景配置：章节标题 + 类型（normal/cg/menu，默认 normal），随存档记录标题，type=menu 时禁用存档热键 |
| `mainmenu` | `cmd_mainmenu` (nb.c) | `mainmenu <x> <y> <w> <h> <opt1> <opt2> ...` | 主菜单，"start"→game, "exit"→end |
| `question` | `cmd_question` (nb.c) | `question <text;opt,var,op,delta;...>` | 选项+变量操作(+/-/=)，结果存 nb.last_choice |
| `var` | `cmd_var` (nb.c) | `var <id> <=/+|/-> <value>` | 变量读写（赋值/加减），需在 variables.json 定义 |
| `settingmenu` | `cmd_settingmenu` (nb.c) | — | 设置菜单（TODO） |
| `cg` | `cmd_cg` (nb_cg.c) | `cg <asset_key>` | 展示 CG（type='CG' 资产，用法同背景图），绘制后永久解锁该 CG 至 SYSTEM.SAV |
| `cgvmenu` | `cmd_cgvmenu` (nb_mainmenu.c) | — | 打开 CG 画廊（由 cgview.nb 调用）：网格浏览 + 锁定占位 + 翻页 + 全屏预览，ESC/Back 回主菜单 |
| `musicmenu` | `cmd_musicmenu` (nb.c) | — | 音乐菜单（TODO） |
| `host` | `cmd_host` (nb.c) | `host <text>` | 系统旁白（无角色名） |
| `loadscene` | `cmd_loadscene` (nb.c) | — | 打开读档选单（由 loadscene.nb 调用） |
| `fei` / `ira` / `neon` | `cmd_dialogue` (nb.c) | `<name>{<text>}` 或 `<name>(<text>)` | 角色台词 |
| `bgm` | `cmd_bgm` (nb_commands.c) | `bgm <key>` | BGM 播放 |
| `sound` | `cmd_sound` (nb_commands.c) | `sound <key>` | SE 播放 |
| `voice` | `cmd_voice` (nb_commands.c) | `voice <key>` | 语音播放 |
| `playanima` | `cmd_playanima` (nb_anim.c) | `playanima{name}` / `playanima(once\|loop[,sec]){name}` | 播放 .ANI 动画；省略修饰=once；sec 为总时长秒数（覆盖容器 tick 表），loop 时到期重置 | 
| `waitanima` | `cmd_waitanima` (nb_anim.c) | `waitanima{}` | 暂停剧本推进直至动画播完 |
| `stopanima` | `cmd_stopanima` (nb_anim.c) | `stopanima{}` | 立即停止当前动画并唤醒剧本 |
| `delay` | `cmd_delay` (nb_commands.c) | `delay(seconds)` | 暂停剧本推进指定秒数（60Hz 帧计数，最长60秒） |

### 命令格式

- `cmd(arg1, arg2, ...)` — 括号参数
- `cmd{text content}` 或 `cmd(){text content}` — 文本参数

### 角色名映射

角色名 → display_name 映射在 `core/engine/nb_asset_table.h` `char_map[]`：
```
fei → "Fei", ira → "Ira", neon → "Neon"
```

### 文本缓冲与解析限制

- 文本缓冲：`dialog_text_buf[1024]`
- 解析器限制：`NB_ARGS_MAX = 20`，一次 `cmd(...)` 最多 20 个参数。`mainmenu` 需要 4 固定 + N 项，所以最多容纳 16 个菜单项。若需更多，增大此值即可。

---

## 2. 关键常量速查

### 2.1 渲染区域

```
LAYER_DIALOG_X = 80,   Y = 280, W = 480, H = 115
LAYER_SPRITE_W = 200, H = 400
LAYER_SCREEN_W = 640, H = 400
LAYER_MAX_SPRITES = 16
```

### 2.2 调色板

```
PAL_WHITE = 7, PAL_TRANSPARENT = 15
对话框填充色 = 248
```

对话框样式 `g_dialog_style`：
```
bit 0 = dither enable (0=fill_rect solid, 1=PAT75 pattern)
bits 1-3 = color index (>> 1)
PAT75 = { 0xEE, 0x77, 0xBB, 0xDD, 0xEE, 0x77, 0xBB, 0xDD }
```

### 2.3 VRAM 访问

```
Bank 寄存器 = 0xE0004 (word)
VRAM 窗口   = 0xA8000 (32KB)
Bank 索引   = addr / 32768
线性地址    = y * 640 + x
```

> 详细显示管线与 VRAM 规范见 `docs/B02-显示管线规范.md`。

---

## 3. 数据管线与格式参考

数据文件：
```
MAG       → core/lib/mag.c/h            MAKI02 图像，透明色=15
FONT.DAT  → core/lib/font.c/h           8×16 ASCII 字形
BLACK.DAT → core/lib/font.c/h           黑花体 16×16 ASCII 字形（FONT.DAT 版式，备选表 font_load_alt）
CJK.DAT   → core/lib/cjk.c/h            16×16 CJK 字形
IMAGE.DAT → core/engine/image.c/h       图片归档（pack_images.py 打包；image_raw_blob 供 ANI 直读）
.ANI      → tools/naiz_lib/anim_container.py  动画容器 v1（制作+播放侧已落地，devdoc 77/78/80）
.nb       → core/engine/nb.c/h          纯文本脚本（直接加载执行）
```

管线：
```
PNG → naiz_conv/mag_convert.py → MAG
ASSETS.DB → naiz_build/pack_images.py → IMAGE.DAT
ASSETS.DB → naiz_build/export_asset_table.py → core/engine/nb_asset_table.h（asset/spr/char/expr/anim/cg_map 六表 + CG_COUNT 常量）
assets + .nb → naiz_build/build_game.py → games/<game>/
games/<game>/ → naiz_img/inject.py → disks/<game>.hdi
animation/projects/<项目名>/scripts/<名>.na + animation/projects/<项目名>/db/<项目名>.db → anima.sh build <项目>/<脚本>（naiz_build/anim_import.py）→ animation/output/<NAME>.ANI
```

### 3.1 .ANI 容器 v1（制作侧）

动画项目架构（`anima.sh init <项目>` 创建，config.toml 的 `[project] name` 必须与目录同名，作为项目判定依据）：

```
animation/projects/<项目名>/
├── config.toml             # 项目标识: [project] name/version/description
├── scripts/<名>.na         # 该项目的动画脚本（.na 后缀专属动画脚本，与剧本 .nb 分离）
└── db/<项目名>.db           # 该项目的素材登记库
assets/<项目名>/anim/        # 帧素材（png/pal，与游戏构建管线同址，不迁入）
animation/output/            # .ANI 产物（全局共享）
```

动画脚本语法（花括号内为**裸名字**，无路径无扩展名）：

```
animaconf(<区域>,<轨道>,<项目名>)                       # 头部，恰好一次且为首条命令，裸括号形式
frame(<秒数>){<名>[,<名>...]}                          # pixel 轨帧（≥1），显式序列，各名共用秒数
base(){<名>}                                           # palette 轨底图（恰好 1）
pal(<秒数>){<名>[,<名>...]}                            # palette 轨差异表（≥1），链式继承
```

- 名字解析：裸名字查 `animation/projects/<项目名>/db/<项目名>.db`（assets 表，frame/base→kind='png'、pal→kind='pal'），映射到 `assets/<项目名>/anim/<文件名>`
- 脚本分离：动画脚本必须 `.na` 后缀且位于项目 `scripts/` 目录，解析器入口拒绝其他后缀（devdoc 79）；剧本脚本 `.nb` 与动画工具链互不可达
- 素材登记：`./anima.sh register <项目>`（扫描 `assets/<项目>/anim/` 下 *.png/*.pal 建/同步名字索引库）；`anim_import --sync` 构建前自动同步；`./anima.sh check <项目>` 只读双向对账（未登记/失效行/待更新，有差异退出码 1）。库仅存 name↔filename 索引（复合主键 (name,kind)，同名 png/pal 共存），图像字节不入库；与游戏 ASSETS.DB 完全独立
- `<项目名>` 必须与 `animation/projects/` 下同名目录一致（须先 init），兼作共享色板推导来源
- 多图语义：`{f1,f2,f1,f2}` 写什么播什么（显式序列），各图共用括号内秒数；循环由播放器/引擎管理，不写入脚本与容器
- tick = max(1, round(秒×60))，逐帧可变时长
- pal 文件：4 列整数 `<index> <R> <G> <B>` 稀疏差异条目，链式继承
- pixel 轨共享色板：`projects/<项目名>/ASSETS.DB` 已构建时自动推导；否则退化为各帧自带色板并 WARN。`build <项目>/<脚本>` 自动传 `--project` 作一致性校验

容器布局（全小端）：28B 头（magic "ANIZ"=0x5A494E41/version/type/track/fps 标称/reserved1 恒 0/nframes/w/h/palsz/nblob/reserved）→ 偏移表 nblob×u32 → tick 表 nframes×u16 → MAG 块（bpp=8, user_string=b"naiz\x1a"）→ [palette 轨] nframes×768 RGB。

> 权威定义与校验细则：`devdocs/78-动画制作工具链：naizbook脚本与ANI容器v1.md` §三/§四；编解码实现 `tools/naiz_lib/anim_container.py`。

### 3.2 .ANI 播放侧（引擎）

- 命令：`playanima` / `waitanima` / `stopanima`，处理函数在 `core/engine/nb_anim.c`，注册于 `nb_commands.c` cmd_table
- 名字解析：`nb_asset_table.h` `anim_map[]`（export_asset_table.py 从 ASSETS.DB `img_map WHERE type='ANI'` 生成）
- 容器直读：`image_raw_blob(id, &len)` 零拷贝返回 IMAGE.DAT 内原始字节；引擎按权威布局解析头/tick 表/调色板表（L1–L4 复验 + 路线 S 尺寸复验：fullscreen 640×400、cine 640×280）
- 时长参数：`(int)(sec*60+0.999999)` 向上取整为 tick 预算；带 sec 时到期一律结束（loop 模式仅表示帧序列回绕，不续期）；无 sec 的 once 自然播完即停，无 sec 的 loop 持续至 stopanima/场景切换
- 主循环节拍：vblank 心跳 60Hz（main.c 内外层循环顶部 `vblank_wait()`），`anim_tick`/`vm_delay`/输入轮询均按帧节拍推进
- 调色板轨：底图 blit 一次，后续每帧 `hal_set_palette` ×256；pixel 轨逐帧 vram_blit
- 等待语义：对白等待期间活动动画持续走帧（内层输入循环驱动 `anim_tick`）；`waitanima` 暂停窗口内点击/空格被吞（不跳行不杀动画），once 播完自动续行无需按键；解释器侧 `nb_process` 入口有 `anim_waiting()` 守卫，任何误唤醒都不会越过等待
- 导入侧 V8 尺寸定死校验在 `anim_import.py::_final_dimension_check`
- 成品登记（手动 SQL 模板，devdoc80 §4.2 定案）：

```sql
-- 前置: projects/<game>/ani/<NAME>.ANI 已就位（anima.sh build 产物拷入）
INSERT INTO img_map (filename, type, name) VALUES ('ani/<NAME>.ANI', 'ANI', '<脚本引用名小写>');
```

> 权威规范：`devdocs/80-ANI播放侧playanima语法与尺寸定死方案.md`。

> 详细格式规范见 `docs/B11-MAG图片加载与显示规范.md`、`docs/B04-工具链API参考.md`。
