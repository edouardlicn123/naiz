# 80 - ANI 播放侧：playanima 语法与尺寸定死方案

> 状态：**活动文档**（NB 播放侧语法权威 + 实施计划载体；实施落地后按实际代码复核修订本档）。
> 前序关系：devdoc 77 §4.7（引擎蓝图）→ 78（制作侧细化）→ 79（.na 分离重组）→ **本档**（播放语法定稿 + 路线 S 尺寸策略 + 三阶段实施计划）。
> 冲突裁决：凡本文与 77 §4 系冲突之处，以本文为准；77 其余章节（palette 原语/转场）不受影响。

---

## 一、决策记录（2026-08-24 会话定稿）

| # | 决策 | 来源 / 理由 |
|---|------|------------|
| D1 | 命令名定为 `playanima` / `waitanima` / `stopanima` | 用户指定。与制作工具链 `anima.sh` 同族命名；取代 77 §4.7 的 `anim/waitanim/stopanim` |
| D2 | 动画名走花括号载荷：`playanima(){name}` | 用户指定（"具体的动画应该在后面的花括号指定"）。仿台词主载荷形态 `fei(Fei){text}`；括号只留修饰参数 |
| D3 | 播放修饰参 `once \| loop`，缺省 `once` | 用户指定。容器 v1 的 `reserved1=0`（loop 策略归播放器）由此在调用点落地 |
| D4 | 类型自省：命令不声明 fullscreen/cine/track/fps | 用户否决显式 type 参数（"动画本身已经定义了内容格式，为何还要在播放命令里定义？多此一举"）。容器头是类型/轨道/尺寸的唯一事实源 |
| D5 | **路线 S 尺寸定死**：fullscreen ≡ 640×400 @(0,0)；cine ≡ 640×280 @(0,0)。坐标机制整体不存在 | 用户选择。cine 语义从 77 §4.1"约束区内任意子区域"收敛为"固定占据对话框上方整条"。`.na` 无坐标参数、容器保持 v1 不升版、命令零位置参数 |
| D6 | `.ANI` 成品存放游戏项目 `ani/` 目录：`projects/<game>/ani/*.ANI` | 用户指定（"ani文件应该存放在项目的ani目录里"），与 `images/` 存 MAG 同构 |
| D7 | playanima 参数严格判定：未知关键字、缺名、多余参数一律拒启 + 日志，脚本继续；waitanima/stopanima 为零参命令，收到参数时告警并忽略之、功能照常（幂等命令无歧义空间，拒绝执行反而造成"该停未停"的更大意外） | 消灭静默失败原则（§九 AI 协作原则 6） |
| D8 | `waitanima` 作用于 loop 动画时告警 | 线性脚本下循环永不"播完"，阻塞续行不可达属作者错误。**告警触发点细化：在 `waitanima` 执行且当前活动动画带 loop 时 WARN 并仍阻塞**（`playanima(loop)` 本身不告警——环境特效即发即忘是一等公民用法，不应制造噪音） |
| D9 | 范例双脚本 `testfull` / `testcine`，素材同源派生 | 用户指定命名。同一 PNG 无法同时合法服务两种定死尺寸（尺寸互斥），故 cine 版帧由原帧顶部裁剪派生 |
| D10 | playanima 增第三形式 `playanima(once\|loop,sec){name}`：sec=总时长秒数，引擎按 `ceil(sec×60)` 换算 tick 预算；loop 到期重置预算继续，once 到期即停；省略时回退容器 tick 表自然节奏 | 2026-08-25 实施会话用户追加。tick 表仍是逐帧节奏唯一事实源，sec 仅限定总播放窗口 |

---

## 二、NB 命令规范（最终）

### 2.1 语法形式

```
playanima(){name}            # 缺省 once：播完自动停止
playanima(once){name}        # 显式一次（等价缺省）
playanima(loop){name}        # 循环播放（即发即忘）
playanima(once,sec){name}    # 限定总时长 sec 秒（D10，once 到期即停）
playanima(loop,sec){name}    # 循环 + 每轮预算 sec 秒（到期重置继续）
waitanima()                  # 阻塞至当前动画播完或被 stopanima；无活动动画时直接通过
stopanima()                  # 停止并释放当前动画；无活动动画时直接通过
```

### 2.2 参数解析规则

解析器行为（`core/engine/nb_parser.c::nb_parse_line`）：空括号 `()` 推进过右括号后 `{text}` 成为 `argv[0]`，故：

| 源文本 | argc | argv |
|--------|------|------|
| `playanima(){op}` | 1 | `["op"]` |
| `playanima(loop){op}` | 2 | `["loop", "op"]` |
| `playanima(once){op}` | 2 | `["once", "op"]` |
| `playanima(once,5){op}` | 3 | `["once", "5", "op"]` |
| `waitanima()` / `stopanima()` | 0 | `[]` |

处理函数判定表：

| 条件 | 行为 |
|------|------|
| playanima，argc==1 | name=argv[0]，mode=once，启动流程 |
| playanima，argc==2 且 argv[0] ∈ {"once","loop"} | mode=argv[0]，name=argv[1]，启动流程 |
| playanima，argc==3 且 argv[0] ∈ {"once","loop"} 且 sec>0（D10） | mode/sec/name=argv[0]/argv[1]/argv[2]，sec 换算 tick 预算后启动 |
| playanima，其余（argc==0、argc>3、argv[0] 非法关键字、sec≤0） | 拒启 + 日志（含实际收到内容），脚本继续 |
| waitanima/stopanima，argc != 0 | `hal_log` 告警（列出多余参数）后忽略之，幂等功能照常执行（D7 修订口径） |

### 2.3 语义细则

| 规则 | 行为 |
|------|------|
| 名字解析 | 脚本引用名经生成表 `anim_map[]` 线性查找（`anim_find(name)`，机制同 `cmd_bg` 的 `resolve_asset`）；未命中 → 拒启 + 日志，脚本继续 |
| 容器装载校验 | 引擎侧复刻 L1–L5 校验（magic/version/type/track/nblob/palsz/offset/tick，规则同 `tools/naiz_lib/anim_container.py::parse_ani`）；任何一步失败整体放弃，不留半初始化状态 |
| 尺寸校验（路线 S） | 容器头 `w×h` 与 type 定死值不符（fullscreen≠640×400 或 cine≠640×280）→ 拒启 + 日志 |
| 隐式停止 | 新 `playanima` 启动前先隐式停止旧动画；`bg` 载入新背景、`scene` 切换（`scene_end`）同样引擎层保证停止，脚本无需手动 stop |
| 首帧 | `playanima` 成功后立即绘制首帧（PIXEL 轨含 `hal_vblank_wait()`）；不阻塞脚本行推进 |
| loop 归调用点 | 容器头不含 loop 字段（reserved1 必须 0）；同一 .ANI 可在不同调用点分别以 once/loop 使用 |
| waitanima × loop | 见 D8：执行时若活动动画为 loop → WARN 后仍阻塞，直到 `stopanima` 唤醒 |
| AUTOEXIT 构建 | 头版每帧无条件 `vm_request_process()`（main.c:104），故 waitanima 在 headless 测试构建中自动放行——与对话分页的既有豁免策略一致，非 bug |

### 2.4 典型脚本示例

OP 过场（一次性全屏）：

```
sceneconf(op, normal)
playanima(){op_kaijo}
waitanima()
bg(splbg)
fei(Fei){……}
```

对话中环境特效（循环 cine，即发即忘）：

```
bg(room_night)
playanima(loop){lamp_flicker}
fei(Fei){……}
stopanima()
```

---

## 三、尺寸与区域规则（路线 S）

### 3.1 合法集

| type | 尺寸 | 锚点 | 与图层关系 |
|------|------|------|-----------|
| fullscreen | 640×400（`LAYER_SCREEN_W×LAYER_SCREEN_H`，render.h:30-31） | (0,0) | 整屏，含对话框区域 |
| cine | 640×280（`LAYER_DIALOG_Y`=280，scene_layers.h:25 上方整条） | (0,0) | 永不触碰 y ≥ 280 |

### 3.2 语义演化记录

- 77 §4.1 原案：cine = "y≥0 且 y+h≤280 约束内的任意子区域"，预留启动坐标校验（L6）。
- 本档收敛（D5）：cine = 固定上方整条。理由：位置信息归制作方且无子区域摆放需求时，坐标机制（`.na` 参数 / 容器字段 / 命令参数三处）可整体删除，全链路最简。
- 代价：小尺寸特效需满幅透明像素填充（MAG 色游程压缩对透明大块极友好，体积代价小；blit 为整幅 640×280，成本可接受）。若日后实测不可接受，再启路线 P（子区域定位 + 容器 v2），本档预留该退路但不实施。

### 3.3 违例双保险

1. 制作端：`anim_script.py` 解析期校验帧尺寸 ≡ type 定死值（V8 规则，见 §六.1）。
2. 播放端：引擎 `playanima` 启动期二次校验容器头 w×h，不符拒启 + `hal_log`（防绕过制作链的手工容器）。

---

## 四、数据管线

### 4.1 目录约定

```
projects/<game>/images/*.MAG     # IMG/SPR 帧（既有）
projects/<game>/ani/*.ANI        # 动画容器（本档新增，D6）
```

### 4.2 ASSETS.DB 登记

`img_map` 新增 `type='ANI'` 行（无 DDL 变更，type 为 TEXT）：

| 字段 | 值 |
|------|----|
| id | 复用 img_map 自增主键 |
| name | 小写脚本引用名（如 `op_kaijo`），供 anim_map 导出 |
| filename | `ani/<NAME>.ANI`（NAME 为 8.3 大写产物名） |
| type | `'ANI'` |

登记方式留白（实施轮次二选一）：① 手工 SQL（文档给出模板语句）；② 新增小工具（如 `makegame.sh animreg <game> <file> <name>`，含查重）。IMG/SPR 行现状同为仓库外维护，不构成本档阻塞项。

IMAGE.DAT TOC 名事实（实测 projects/demo-a2/IMAGE.DAT）：TOC 名取 basename ASCII，**超过 11 字节截断至 11**、NUL 填充 12（pack_images.py 截断逻辑），截断后冲突即构建失败。`TESTFULL.ANI`(12B) 入 TOC 变为 `TESTFULL.AN`——**无碍功能**：引擎一律按 asset id 检索，TOC 名仅作唯一键（现存 `fei-normal.`、`mainmenu.MA` 同理）。

### 4.3 pack_images ANI 旁路要点

`load_img_map_assets` / `pack_images` 对 `type='ANI'` 行：
1. 跳过 `decode_mag_full`（.ANI 非 MAG，解码必失败）；
2. 跳过共享色板贡献与逐图 remap；
3. 原样字节进 TOC 单条目（Step 3 现有 `result is None → RuntimeError("MAG decode failed")` 分支须先判 ANI 再透传 raw）；
4. 全链路禁止把 ANI 条目当 IMG/SPR 处理。

**校验链两处连带修正（2026-08-24 复查发现的真缺陷，随 1.1 一并修）**：

| 缺陷 | 现状 | 修正 |
|------|------|------|
| `image_dat.py::verify_shared_palette`（:45-55）对全部 TOC 条目跑 `decode_mag_palette` | ANIZ 魔数非 MAG → 报 "palette size" 错 → **IMAGE.DAT 构建失败** | 循环内加魔数探测：条目头 8 字节 ≠ `MAG_SIGNATURE` 即 skip |
| `build_game.py`（:373-379）取共享色板基线时取首个非空条目并无条件 break | ANI 恰为 id=0 时基线为空 → 源图色板比对被**静默跳过** | 基线探测改为"首个 MAG 条目"（同样魔数探测），未找到 MAG 基线才跳过比对 |

### 4.4 anim_map 导出

`export_asset_table.py` 在 `nb_asset_table.h` 追加第四张表（与 asset_map/char_map/expr_map 同代生成，复用 c_header 样板）：

```c
typedef struct { const char *name; unsigned short id; } AnimMapEntry;
static const AnimMapEntry anim_map[] = {
    {"op_kaijo", 17},
    {NULL, 0}
};
```

`SELECT id, name FROM img_map WHERE type='ANI' ORDER BY id`。引擎 `anim_find(name)` 线性扫描，查无返回 -1 + `hal_log`。Makefile 补一行 `build/nb_anim.o: engine/nb_asset_table.h`（模式同 build/nb.o:72）。

### 4.5 管线全景

```
animation/projects/<项目>/scripts/<名>.na ──anima.sh build──▶ animation/output/<名>.ANI（独立成品）
        │ copy
        ▼
projects/<game>/ani/<名>.ANI ──登记(img_map type='ANI')──▶ ASSETS.DB
        │                                                    │
        │            ┌───────────────────────────────────────┘
        ▼            ▼
pack_images.py（ANI 旁路）──▶ IMAGE.DAT          export_asset_table.py ──▶ nb_asset_table.h (anim_map)
        │                                        │
        ▼                                        ▼
   inject.py → HDI ◀──────── games/<game>/ ────▶ core/engine/nb_anim.c 运行期
```

---

## 五、引擎设计要点

继承 77 §4.7 骨架，以下为本档修订后的实施口径。

### 5.1 文件与数据结构

- 新建 `core/engine/nb_anim.h` / `nb_anim.c`（`wildcard engine/*.c` 自动收录；命令处理函数注册进 `nb_commands.c` 的 cmd_table:346）。

```c
typedef struct {
    int           active;
    int           wait;          /* waitanima 挂起标志 */
    int           loop;          /* 调用点 once/loop（D3） */
    int           frame;         /* 当前帧下标 */
    int           tick;          /* 当前帧剩余计数，重装值 = ticks[frame] */
    int           type, track;   /* 取自容器头 */
    int           base_blitted;  /* PALETTE 轨底图已绘标志 */
    MagImage     *img;           /* PIXEL：当前帧引用；PALETTE：常驻底图引用
                                    （mag_retain/release，停止时释放） */
    const uint8_t *pals;         /* PALETTE 轨：容器内调色板表首址（768B/帧），
                                    换帧按 frame 偏移取表；PIXEL 轨为 NULL */
} AnimState;
extern AnimState *anim_state(void);   /* main.c 轮询用 */
```

单一 `img` 字段双角色复用（PIXEL=易变当前帧 / PALETTE=常驻底图），由 track 区分生命周期语义，避免两轨各设字段带来的状态冗余。

### 5.2 容器读取辅助（image.c）

现公开面仅 `image_load(id)`（image.h:21）。新增：

```c
const uint8_t *image_raw_blob(unsigned short id, uint32_t *len);
/* 返回 g_image_data 内 TOC 条目原始字节指针（下次 image_init 前有效）；
   id 越界返回 NULL + hal_log。不触发 image_set_palette、不经 image_cache。 */
```

### 5.3 挂载点与阻塞唤醒（77 未覆盖的实施关键）

`nb_process`（nb.c:252 `while (VMFLAG_PROCESS)`）暂停期间行执行停摆，动画必须在其外推进：

- **`anim_tick()` 挂载于 main.c 外层主循环帧首**：AUTOEXIT 分支（main.c:99–110）在 `hal_mouse_update()`（:101）之后、`vm_request_process()` 之前；常规分支（:112 起）同样置于 `hal_mouse_update()` 之后、`nb_process()` 之前——保证脚本暂停/等待期间动画照常走帧。
- **waitanima 实现**：置 `g_anim.wait=1` + `vm_pause_process()`（复用对话分页暂停机制）。
- **唤醒**：`anim_stop_internal()`（播完/stopanima/被新动画顶替/bg·scene 隐式停止共用出口）检查 `wait` → 清零 + `vm_request_process()`。
- **输入等待分支互斥**：main.c:124 进入点击等待循环的条件补 `&& !anim_waiting()`——否则 waitanima 期间会跌入只认鼠标点击的等待环，动画冻帧。等待期间外层循环持续旋转（anim_tick 每帧推进 + nb_process 空转），播完自动恢复。
- AUTOEXIT 豁免见 §2.3 末行。

### 5.4 每帧推进

```
anim_tick():
    if (!active) return;
    if (--tick > 0) return;
    /* 启动时装载：playanima 成功路径置 frame=0、tick=ticks[0]、立即绘首帧 */
    if (++frame < nframes) { tick = ticks[frame]; draw_frame(); return; }
    if (loop) { frame = 0; tick = ticks[0]; draw_frame(); return; }
    anim_stop_internal();                 /* release 引用、清标志、唤醒 wait */
    hal_log("anim: finished");
```

注意：重装值恒取**当前帧** tick 表项（78 修订），头部 fps 字段仅标称显示（变时长为 0），禁止参与时序计算。

### 5.5 绘制分派

- PIXEL：`hal_vblank_wait()` → fullscreen `vram_blit` 全幅 / cine 全幅 blit（640×280 终行 y=279，路线 S 下天然不触对话框区，无需 clip）→ fullscreen 且对话框已开时逐帧执行 77 §4.7 `rebuild_dialog_over_anim()` 流程（快照重截取，不复用过期快照）。
- PALETTE：首帧 blit 底图一次（含一次对话框重建）+ `base_blitted=1`；此后每帧仅 `palette_set_all(每帧 768B 表)`；回卷继续读表，零撕裂。
- 光标：帧绘制沿用主循环 `hal_mouse_draw_cursor()`（main.c:121）统一重绘；cine 局部 blit 前无需额外失效。

### 5.6 内存策略

- 容器字节常驻 `g_image_data`（指针引用，零拷贝）；帧解码走 `mag_decode` + `mag_retain`/`mag_release`，PIXEL 仅持当前帧，PALETTE 底图持有至停止。
- 动画帧**不经 image_cache**（8 槽 LRU 防逐帧污染）。
- 全局单活动动画（`g_anim`），无队列。

---

## 六、制作侧配套

### 6.1 帧尺寸校验（V8）

现有校验体系 F1 + V1–V7（规则编号挂 `anim_script.py:32` 文档口径）。新增 **V8**：pixel 轨帧图 / palette 轨 base 图的实际像素尺寸必须等于 animaconf type 的定死值（fullscreen 640×400 / cine 640×280）。**实现落点为 `anim_import.py` 组装期**（全链路唯一读图处；`anim_script.py` 为纯文本解析不读图），读图解码后取 w/h 比对，违者 SystemExit(1)，错误消息含期望值与实际值。

### 6.2 范例重组执行清单（testfull / testcine）

| 步骤 | 操作 |
|------|------|
| 1 | `git mv animation/projects/animatest/scripts/animatest.na scripts/testfull.na`；animaconf 改 `animaconf(fullscreen,pixel,animatest)`；帧声明与头注释速查块不动 |
| 2 | 新建 `scripts/testcine.na`：复制头注释块 + `animaconf(cine,pixel,animatest)` + `frame(0.5){cine001,cine002}` |
| 3 | 生成素材：原帧 PIL `crop((0,0,640,280))` → `assets/animatest/anim/cine001.png`、`cine002.png`（中心点 y=200 存活，视觉内容保持） |
| 4 | `./anima.sh register animatest`（register 即同步，无需 --sync；--sync 是 build 的旗标） |
| 5 | `./anima.sh build animatest/testfull` → `animation/output/TESTFULL.ANI`；`build animatest/testcine` → `TESTCINE.ANI` |
| 6 | 删除遗留产物 `animation/output/ANIMATEST.ANI`（源脚本已不存在，防误导） |

### 6.3 存量违例记录

ANIMATEST.ANI 曾以 `cine` 声明携带 640×400 帧（违反 77 §4.1 y+h≤280；制作链彼时无尺寸校验，L6 推迟播放侧导致漏网）。经 §6.2 重组后消除；V8 上线后此类错误在生产端即拦截。

---

## 七、完整实施计划（三阶段）

> **实施状态（2026-08-25）**：阶段 1 全部完成（1.4 范例重组落地、1.5 定案手动 SQL 模板并入 B92 §3.2、demo-a2 已登记 testfull/testcine 两条并构建通过）；阶段 2 完成（含 bg/scene 隐式停止、D7/D8 告警、L5 引擎复验、对话框快照重建、帧直解不经 image_load/image_cache）；阶段 3 的 3.1/3.2 完成，**3.3 NP2kai 实机目检待执行**（构建与数据链已就绪）；§八.7 F5 存档交互开放项随 3.3 一并确认。

### 阶段 1 · 工具链

| # | 任务 | 验证 |
|---|------|------|
| 1.1 | pack_images/load_img_map_assets ANI 旁路 **+ 校验链两处连带修正**（§4.3，含 verify_shared_palette 魔数跳过、build_game 基线探测改首 MAG 条目） | pytest（新增用例：ANI 行旁路不解码、raw 进 TOC、含 ANI 条目的 IMAGE.DAT 过 verify_shared_palette、ANI 居 id=0 时色板比对仍执行） |
| 1.2 | export_asset_table anim_map 导出（§4.4） | pytest + 目检生成的 nb_asset_table.h |
| 1.3 | anim_import V8 帧尺寸校验（§6.1；规则编号 V8 计入 .na 校验体系文档口径） | pytest（三种违例：fullscreen 尺寸不符/cine 尺寸不符/palette base 尺寸不符） |
| 1.4 | 范例重组 §6.2 六步 | 双 build 成功 + `check` 对账干净 |
| 1.5 | img_map 登记方式定型（手动 SQL 模板或小工具） | 登记 demo-a2 试跑一条 |

### 阶段 2 · 引擎

| # | 任务 | 验证 |
|---|------|------|
| 2.1 | image.c `image_raw_blob` 辅助（§5.2） | make 0/0 |
| 2.2 | nb_anim.h/c：AnimState、L1–L5+尺寸装载校验、anim_tick、draw_frame 双轨分派、stop_internal | make 0/0 + 串口日志 |
| 2.3 | cmd_table 注册三命令 + §2.2 判定表 | 串口日志核对拒启路径 |
| 2.4 | main.c 双分支挂载 anim_tick + :124 条件补 anim_waiting + waitanima/唤醒闭环（§5.3） | NP2kai 实机目检：等待期间帧流畅、播完自动续行 |
| 2.5 | bg/scene 隐式停止接线 | 目检切场景无残留 |

### 阶段 3 · 文档与总验证

| # | 任务 |
|---|------|
| 3.1 | B92 §1 追加三命令条目（含本档差异注记）、§3 管线行补 ani/ 与 anim_map；B90 函数索引补 nb_anim.* 与 image_raw_blob |
| 3.2 | `bump_version demo-a2`；`make -C core` 0 err/warn；pytest 全绿；`./start.sh fullaudit` 六节全过 |
| 3.3 | demo-a2 内容样例：接入一个 fullscreen OP + 一个 cine 循环特效 → `makegame.sh build demo-a2` → NP2kai 目检（四象限：fullscreen/cine × pixel/palette 中至少前三者）+ `--serial` 核对启动/换帧/结束/拒启日志 |

---

## 八、防复发要点

1. **尺寸合法集四处同步**：任何类型/尺寸调整必须同时改 容器文档（78 §4）/ V8 校验 / 播放器拒启常量 / B92——漏一处即产生两端不一致。
2. **loop 策略永不入容器**：reserved1=0 是解析硬校验（parse_ani L2）；未来需求一律走调用点修饰参。
3. **ANI 条目两永不**：永不触发 `image_set_palette`（旁路共享色板不变量）、永不进 image_cache。
4. **tick 时序唯一来源**：换帧重装值只准读 `ticks[frame]`；头部 fps 字段禁入时序计算。
5. **waitanima×loop WARN（D8）不可省**：线性脚本的软锁只能靠提示预防。
6. **隐式停止出口唯一**：一切终止路径（播完/stopanima/顶替/bg/scene）汇入 `anim_stop_internal()` 单点，唤醒逻辑不得散落。
7. **开放项（实施期实机验证）**：动画活动期间按 F5 呼出存档菜单、以及存档/读档后的动画状态恢复策略（容器引用是否随存档快照失效）——77/本档均未覆盖，阶段 2.4 目检时专项确认，发现问题回写本档。

## 九、与 77 §4.7 差异表

| 项 | 77 原案 | 本档定稿 |
|----|---------|----------|
| 命令名 | anim / waitanim / stopanim | **playanima / waitanima / stopanima**（D1） |
| 名字位置 | `anim(type,名,[x,y])` 括号参 | **花括号载荷** `playanima(mod){name}`（D2/D3） |
| type 参数 | 显式传 fullscreen/cine | **删除**，容器头自省（D4） |
| loop | 容器头 0x09 字节 | **调用点 once/loop 关键字**（78 修订延续 + D3） |
| cine 几何 | 约束区任意子区域 + 启动坐标校验（L6） | **固定 640×280 左上锚定**，坐标机制不存在（D5 路线 S） |
| 尺寸校验 | 仅 fullscreen=640×400 一条 | 两类型均精确匹配，生产端 V8 + 播放端双重 |
| 阻塞挂载 | "nb_process 帧首调 anim_tick" | **main.c 外层帧首**（nb_process 暂停期间仍推进）+ 输入等待分支互斥 + AUTOEXIT 豁免（§5.3，实施关键修正） |
| 动画表 | anim_map 或独立 nb_anim_table.h 二选一未定 | **并入 nb_asset_table.h 第四表**（§4.4） |
| 资产目录 | 未指明成品落位 | `projects/<game>/ani/`（D6） |
