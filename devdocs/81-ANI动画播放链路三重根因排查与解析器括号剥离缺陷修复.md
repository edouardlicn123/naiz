# 81 — ANI 动画播放链路三重根因排查与解析器括号剥离缺陷修复

> 日期：2026-08-25
> 项目：animatest（四场景动画流程测试项目）
> 版本：0.1.006 → 0.1.007
> 结果：fullaudit 6/6 通过；`playanima(once){testfull}` 全屏动画端到端可见、可等待、自然结束后场景才推进

---

## 一、任务背景与症状

animatest 四场景流：`logo.nb`（naizlogo→powered）→ `op.nb`（playanima TESTFULL.ANI + waitanima）→ `mainmenu.nb` → `nbook001.nb`（对话间 playanima TESTCINE.ANI）。

上线即坏的表象群：

1. op.nb 处黑屏约 2 秒后直接进主菜单，动画帧从未可见；
2. waitanima 完全不起作用——即使把时长探针加到 `(once,10)`（10 秒上限），菜单仍在派发后 ~1.75 秒出现；
3. 诊断版剧本 `bg(animatest-f1) + playanima(...)` 却能画出蓝色帧——同一容器、同一 id，行为却不同；
4. 早期版本动画帧以"自上而下逐行扫描显影约 1 秒"的方式出现（后续被证实为独立根因 A）。

## 二、排查历程（按时间序）

### 2.1 数据侧三层验证 —— 全部无罪

- `ASSETS.DB` img_map：id0/1=f1/f2 (IMG)，id5=testfull / id6=testcine (ANI)；
- `IMAGE.DAT`：ANIZ @212868(TESTFULL)、@233026(TESTCINE)，TOC offset/size 与文件本体逐字节一致；
- `nb_asset_table.h` 生成的 `anim_map[]={{"testfull",5},{"testcine",6}}` 编译进引擎。
- 制作侧闭环：按引擎切片逻辑（末帧直通文件尾）对 .ANI 切出的 4 个切片全部被 Python `decode_mag_full` 成功解码；内嵌 MAG 与游戏内正常显示的 bg MAG 结构完全同构。**.ANI 容器格式彻底排除**。

### 2.2 测量假象三连（取证方法论教训）

| 假象 | 机理 | 对策（已固化） |
|------|------|----------------|
| 新实例黑屏"冻结" | timeout 杀外层脚本留孤儿 wxnp21kai（父变 systemd），多实例争抢同一 HDI | 每轮前后 `pkill -9 -x wxnp21kai`（**必须 `-x`**，`-f` 会匹配自身命令行杀死 shell） |
| 死窗口拍出"冻结画面" | 模拟器退出后窗口 ID 变幽灵，`import` 截图仍成功 | live_windows() 三重校验：名称含 IA-32 + 尺寸>400 + import rc==0 |
| 串口取证全灭 | NP2kai 二进制有 com1_m_o/m_i/com1port/com1para/com1_bps 配置键，但 PTY 重定向与**普通文件重定向均无效**（0 字节），INT 14h 直写也收不到 | 放弃串口；改见 2.5 文件日志 |

另：逐 pass 串口日志洪水曾把主循环拖到 ~2Hz（每 pass ~119 字符 × 201 次端口陷入），已移除 nb.c/main.c 三处 per-pass NB_DEBUG。

### 2.3 根因 A（真修复）：vram_blit_sprite 逐字节 volatile 写过慢

逐字节 volatile 存储在 NP2kai 解释执行核上全屏 blit 需 ~1 秒且自上而下逐行显影。新增 `vram_row_copy()`（render.c）：bank 窗口是普通 RAM 无副作用，去 volatile 安全，`rep movsb` 按 bank 段批量拷贝；不透明非镜像路径走快路径。修复后动画帧瞬间完整出现。

### 2.4 根因 B（真修复）：pixel 轨动画帧无调色板编程

pixel 轨（track==0）帧经 mag_decode 直出（注释明说不走 image_load），而调色板编程只存在于 image_load 中——动画帧像素索引被前一背景的调色板错误解释，渲染成黑。已在 `anim_draw_frame` track==0 分支 blit 前，按帧自带 MAG 调色板做 256 色 `hal_set_palette` 循环（对齐 image_set_palette 行为）。

### 2.5 取证手段升级：HDI 文件日志（本轮决定性工具）

视觉面包屑（fill_rect 角标色块）有两个致命缺陷：颜色随当前调色板漂移（idx252 在某时刻渲染为近黑）、会被全屏图像吞没。垂直速率条同样不可靠（列测量被窗口边框/logo 白底污染，出现两次"冻结在完全相同 318px"的假读数）。

**最终方案：引擎直接 fopen("DBG.LOG","a") 写面包屑，跑完后用 `NAIZFatFS.resolve_path/read_file` 从 disks/animatest.hdi 抽取。** DOS int21h 文件写在 NP2kai 下完全可用（save_io.c 先例）。与调色板无关、与时序无关、与窗口生命周期无关，一轮定位：

```
[OPEN]
play argc=3 a0='once' a1='10' a2='{testfull}'   ← 花括号没剥！
play grammar ok name='{testfull}' mode=0 dur=600
play MAPMISS name='{testfull}'                   ← anim_map 必然查找失败
wait active=0 loop=0                             ← waitanima 直接放行
```

### 2.6 根因 C（总根因）：nb_parser.c 括号循环吞并花括号载荷

`playanima(once,10){testfull}` 的解析轨迹：

1. cmd 提取 `playanima`，p 停在 `(`；
2. 括号参数循环：args[0]="once"、args[1]="10"；第二个参数扫到 `)` 时，循环体内 `if (*p==')') { NUL; p++; }` 把 p 推过 `)` 指向 `{`；
3. **while 条件只检查 `*p != ')'`**——`{` 不是 `)` 也不是 NUL，循环继续第三轮，把 `{testfull}` 整体当作第三个括号参数吞下（扫到串尾无逗号无右括号才退出）；
4. 花括号处理分支（剥 `{` `}`、NUL 终止）永远执行不到。

结果 argv = ["once","10","{testfull}"]。cmd_playanima 取 `name=argv[argc-1]` 做 anim_map 查找 → 必然 MAPMISS → 静默 return → active 从未置位 → waitanima 看到 active=0 直接放行 → 菜单提前、动画隐身。

**为何此前从未暴露**：

- `bg(animatest-f1)` 单参数时 args[0] 恰好干净（braced 文本落在 args[1]），而 bg 类 handler 读的是首个位置参数——**碰巧幸存**；
- `sceneconf(){,menu}` / `waitanima{}` 括号为空，p 直接落在 `{`，brace 分支正常工作——**空括号路径掩盖了非空路径的缺陷**;
- 只有"非空括号参数 + 花括号载荷 + handler 读 argv[argc-1]"三者同时成立才引爆，全库当时仅 playanima 一个命中者。

**修复**（core/engine/nb_parser.c:39）：括号循环条件补 `*p != '{'`，消费完 `)` 后停在花括号开启符上，交还 brace 分支处理。修复后 DBG.LOG：

```
play argc=3 a0='once' a1='10' a2='testfull'
play id=5 blob=ok len=20158
play img=ok dur=600 ticks=600
wait active=1 loop=0
HOLD begin
STOP natural end at tick n=65        ← 2帧×30tick 自然播完，600 上限未触发（符合设计：dur 是上限）
```

### 2.7 最终回归（原版 `(once)` 剧本）

截图时间线：logo 白屏(t4–t6.8) → 黑场(t6.9) → **深蓝动画帧完整在屏(t7.7–t10.3，含黄色图形)** → 自然结束清屏(t10.4) → 主菜单淡入(t11.6)。时序全对，临时探针零残留，make 0 err / 0 warn，版本 bump 至 0.1.007，fullaudit 全过。

## 三、修改文件清单

| 文件 | 性质 |
|------|------|
| core/engine/nb_parser.c | **根因 C 修复**：括号循环条件加 `!= '{'` |
| core/engine/render.c | **根因 A 修复**：新增 vram_row_copy()（B90 已登记） |
| core/engine/nb_anim.c | **根因 B 修复**：anim_draw_frame pixel 轨 blit 前编程帧调色板 |
| core/engine/main.c | 移除 per-pass 串口日志洪水；AUTOEXIT/普通双循环补 vblank_wait 心跳 + 输入等待期 anim_tick 驱动 |
| core/engine/nb.c | 同上日志清理 |
| projects/animatest/* | 场景剧本/资源映射/DB（数据侧，均已验证） |

## 四、潜在问题与遗留风险（重要）

1. **TESTCINE（cine/palette 轨）未做端到端验证**。nbook001.nb 的 `playanima(loop,5){testcine}` 位于对话流程中，本轮回归截图在主菜单后即止（AUTOEXIT 时长所限）。palette 轨走 vram_blit_sprite 路径，调色板策略与 pixel 轨不同——根因 B 的修复**只覆盖了 track==0**。下次跑对话场景时应专项确认。
2. **解析器修复的行为面变化**：`cmd(a,b){x}` 此前 argv=[a,b,{x}]，现 [a,b,x]。读 argv[argc-1] 的 handler 由坏变好；但若有 handler 依赖"braced 尾参"或固定 argc 计数（如要求 argc==3），行为会变。已核查 animatest/demo-a2 全部剧本，仅 playanima 使用该形式，暂无受影响者；**其他项目剧本引入此语法前应先 grep handler 的 argv 取用方式**。
3. **"碰巧幸存"类地雷仍在**：单括号参数 + 花括号载荷的旧解析会把 braced 文本塞进 args[1]。若某 handler 同时读 argv[0]（位置参）和 argv[argc-1]（载荷），历史上可能写出依赖错误结构的代码。建议日后审计所有 `cmd(x){y}` 形态命令的 handler 参数取用。
4. **Python 校验器与 C 解析器的语义盲区**：nb_validator.py 只查 arity，不建模括号剥离/分词语义。"校验器认为合法"与"C 端实际解析结果"之间无一致性保障，本轮缺陷正是从这个缝隙漏过去的。建议未来做 parser parity 测试（同一批行喂 Python 模型与真实引擎比对 argv）。
5. **AUTOEXIT 主循环无条件 `vm_request_process()`**：会穿透一切仅靠 VMFLAG_PROCESS 的阻塞原语。waitanima 目前靠 nb_process 顶部 `anim_waiting()` 守卫再挂起而幸存——这是隐式契约。今后新增阻塞类命令必须同步在 nb_process 守卫链中登记，否则 headless 下会被穿透、真实模式下行为分叉。
6. **vblank_wait 实际速率未量化**：GDC 状态位轮询在 NP2kai 下的返回频率未实测。动画 tick 以它为心跳，标称 60 tick/秒的播放时长可能与墙钟有偏差（观测 2 帧≈2.6s，含每帧 MAG 解码耗时，无法拆分归因）。对节奏敏感的演出（如逐帧动画精确时长）需先校准此速率。
7. **STOP natural end at tick n=65**：2×30=60 外多 5 tick（~83ms），来自 tick 初值/递减顺序细节，无感知影响，记录备查。
8. **串口通道死亡属环境级未解问题**：com1_m_o/m_i 键的真实语义不明（PTY、普通文件两种猜测均失败）。引擎内 NB_DEBUG 输出目前事实上不可观测。如需再次引擎内取证，复刻 DBG.LOG→HDI→Python 抽取管线即可（fopen/fprintf/fclose 到 cwd 即 boot 盘根目录）。
9. **测量纪律**（防复发）：模拟器观测一律以 live_windows() 三重校验为准；索引色屏幕探针不可信（调色板劫持）；跨进程清理只用 `pkill -x`。

## 五、防复发对照（§十七）

- C2/C3/C15：DBG.LOG 临时代码已整体拆除，现存 fopen 均有 NULL 检查与 fclose 收口；
- C13：g_dbg_ticks / anim_dbg_log / dbg_passes 等临时代码零残留（grep 验证）；
- C14：MAPMISS/BADDUR 等 reject 路径本就有 NB_DEBUG 诊断（虽串口不可达，规则满足）；本次教训是**诊断输出必须有可达通道**，已用文件日志验证过完整链路；
- 解析器改动对照 C6/C8：循环条件收紧只会提前退出，无越界/溢出新面；
- fullaudit（35 条规则 + pytest + py_compile + bash -n + symbol_audit + make）2026-08-25 17:53 全过：logs/fullaudit_20260825_175342.log。
