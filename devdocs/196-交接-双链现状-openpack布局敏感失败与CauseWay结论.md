# 196 — 交接：双链现状、openpack 布局敏感失败、CauseWay 结论

> 用途：换机前的**自包含交接文档**。读完本文即可在不翻旧对话的情况下继续干活。
> 日期：2026-11-02 · 仓库：`/home/edo/naiz` · 分支 `main` · HEAD `44fcfb9`（写作时；当前 `42fc1f3`，见 §八）
> 上游：195（本轮 mag_decode 修正）、191（CW 根因收敛）、194（作废结论）

---

## 一、三十秒摘要

| 链 | 打包器 | Extender | 当前状态 |
|----|--------|----------|----------|
| **cmpack**（商业） | `tools_commercial` + 商业基座 | DOS/4GW 1.97（绑定 stub） | ✅ **可用**：`SET DOS16M=1` 补回后 3/3 启动，`image_load(13): ok 640x400` |
| **openpack**（开源） | `tools_open` + FreeDOS(98) 基座 | DOS/32A（绑定 stub） | ✅ **可用**：P7 二次定案（泵移出 `cli` 区），**5 布局矩阵 16 次开机 0 失败**，完整流程 `beach1` 与 cmpack 一致 |
| CauseWay | 实验性 | cwstub 3.52/3.60/官方 | **冻结**：不可用，非交付链；见 §五 与 I03 §零 |

当前最高优先：**清 coast 残留 → 可选：host 参考解码做像素验收**（修复已在双链多布局下稳定）。

---

## 二、环境与工具链（新机器先做这一节）

```bash
cd /home/edo/naiz

# Watcom（编译 32-bit DOS 程序必需）
export WATCOM=$HOME/open-watcom-v2/rel
export INCLUDE=$WATCOM/h
export PATH=$WATCOM/binl64:$WATCOM/binw:$PATH   # binw 里有 dos32a.exe / dos4gw stub

# Python 侧（makegame/build 用 venv）
VENV_PYTHON=/home/edo/naiz/tools/env_setup/venv/bin/python3
```

要点：
- `wcl386` 找不到 `wcc386` ⇒ PATH 没加 `$WATCOM/binl64`。
- `bash core/build.sh` 内部 `source detect_watcom.sh` + `export INCLUDE`，但仍建议显式设好上面三个变量。
- `NAIZ_DEBUG ?= ON`（core/Makefile 第 55 行）——串口日志依赖它；改成 OFF 就没有 `image_load(...)` 这类行。

## 三、构建 / 部署 / 验收（可直接复制）

### 3.1 openpack（DOS/32A）

```bash
cd /home/edo/naiz
rm -rf core/build                      # ★ 必须：build/ 不跟踪 EXTENDER/DEFS 变化
bash core/build.sh open                # 产出 core/engine32a.exe、core/engine_a32a.exe
cp core/engine32a.exe games/demo-a2/engine.exe
cp core/engine_a32a.exe games/demo-a2/engine_a.exe      # ★ 少这个会报"engine_a 落后"
./makegame.sh makegame demo-a2 --pack openpack          # build(pack_images) + 注入
python3 -m tools.diag.np2kai_serial --hdi disks/demo-a2.hdi --listen-only --timeout 11 -o /tmp/op.log
grep -E "image_load\(13\)|bg image 13" /tmp/op.log
```

期望：`image_load(13): ok 640x400` + `bootmenu: bg image 13 loaded (640x400, colors=256, bpp=8)`。
当前实际：`code=11 at=255992`（P7）。

### 3.2 cmpack（DOS/4GW）

```bash
rm -rf core/build
bash core/build.sh                     # 默认 EXTENDER=dos4g → core/engine.exe、engine_a.exe
cp core/engine.exe games/demo-a2/engine.exe
cp core/engine_a.exe games/demo-a2/engine_a.exe
./makegame.sh makegame demo-a2 --pack cmpack
python3 -m tools.diag.np2kai_serial --hdi disks/demo-a2.hdi --listen-only --timeout 11 -o /tmp/cm.log
```

期望同 3.1。当前 3/3 通过（AUTOEXEC 52 字节，含 `SET DOS16M=1`）。

### 3.3 `make` 与 `makegame` 的区别（踩过）

| 命令 | 做什么 | 何时用 |
|---|---|---|
| `makegame.sh build demo-a2` | 只跑 `build_game.py`（pack_images/音频/字体），会因缺源文件硬失败 | 改资源后 |
| `makegame.sh make demo-a2 --pack X` | 只做 HDI 注入（不重新打包资源） | 只换 EXE / 快速验证 |
| `makegame.sh makegame demo-a2 --pack X` | 两者合并 | 正式出盘 |
| `makegame.sh test demo-a2 --serial` | 起 emulator 交互测试 | 人工截图/操作 |

### 3.4 截图（看屏幕上的错误，串口拿不到时用）

```bash
pkill -9 -x wxnp21kai; sleep 1
python3 -m tools.naiz_screendig --launch --launch-timeout 40 -w 12 -o /tmp/shot.png
# 然后用图像读取工具看 /tmp/shot.png
```

`pkill` 必须用 `-x`（`-f` 会连带杀掉自己的 shell）。

## 四、openpack 的 P7：布局敏感的解码失败（2026-11-02 二次定案：泵必须在 cli 外运行）

### 4.0 定案更新（2026-11-02 下午，取代 4.0 原版与 4.1–4.5 的"未解决"叙述）

**破坏源**：不是 `hal_wallclock_smooth_advance()` 这个具体函数，而是**整个进度泵在 `IF=0`
的 `cli` 区内运行**。`mag_decode()` 每推进 4096 字节调用一次 `frame_decode_pump()`；DOS/32A
的 `cli` 只虚拟化 IF，被推迟的硬件 IRQ 反射会在泵的深调用链结束后落到解码栈帧上，改写循环
局部量（`short` 迭代：`out_pos` 只前进 0/2 字节，随后 `flag A` 提前耗尽）。因此"移除
`smooth_advance` 即修复"的旧结论只在 `[AP] trace` 开（每次泵入口都有 `INT 21h`）时成立，
trace 关掉后仍稳定复现。

**修复（当前代码）**：钩子保留，但调用点改为
`_enable(); g_mag_progress_hook(); _disable();`——热循环仍被 `cli` 保护，泵在 `IF=1` 下执行。
落点：[mag.c](file:///home/edo/naiz/core/lib/mag.c#L425-L439)（`mag_decode`）与
[mag.c](file:///home/edo/naiz/core/lib/mag.c#L847-L855)（`mag_decode_into`）。

**本轮单因子（`AUDIO_PUMP_TRACE=0`，makegame demo-a2 布局）**：

| 变量 | 结果 |
|---|---|
| 基线：钩子在 `cli` 内（`smooth_advance` 已移除） | 1 次开机 4 张图失败（13/5/26/5，全 `code=11`，`short cnt=1`） |
| 钩子全关（`-DNAIZ_DECODE_HOOK_OFF`，实验开关，验证后已移除） | 2 次开机，6 张背景图全过 |
| 钩子保留、调用点 `_enable()/_disable()` | 2 次开机 + 最终构建 1 次，6 张图全过（13/4/6/5/26/25） |
| cmpack 长跑回归（新代码） | 2 轮完整流程，0 失败，`beach1` 正常 |

**验收状态**：open 与 cm 的完整流程均已跑通，`nbook003` 的 `beach1` 背景与 cm 截图逐像素
一致（`test/final-open-nbook003.png` vs `test/screens-cm-beach/.../screenshot_133337_711.png`）。
旧的 12 组实验台账（§4.0 原表）是 `[AP] trace` 开启条件下得到的，保留作历史，不再作为定案依据。

### 4.0a 历史台账（`[AP] trace` 开，2026-11-02 上午，已被上节取代）

| 变量 | 结果 |
|---|---|
| 钩子全关 | 0/4 失败 |
| 原状 | 3/40 ≈ 7.5% |
| 钩子只改调"零 DOS 调用"的 `coast` 变体 | 24/24 全败（假说被证伪） |
| 删除 `smooth_advance` 调用，其余不动 | **18/18 全过** |
| `smooth_advance` 内部改为零 `INT 21h` / 空函数 / 纯 `ret` | 20/20、4/4、4/4 全败 |
| 去掉 `cli` | 2/4 败；再去 `smooth_advance` 后 38/40 败 |
| 最终（`cli` + 无 `smooth_advance` + `[AP] trace` 开） | **40/40 全过** |

完整台账与纪律见 [refdoc I04](file:///home/edo/naiz/docs/refdocs/I04_DPMI反射与cli临界区经验-DOS32A下mag_decode失败定案.md)。

**仍缺的验收**：40/40 只覆盖单一布局。按 §4.4 的"通用判据"（扰动 ≥6 次）尚未通过；
cmpack 回归、像素正确性也未做。

### 4.1 现象

```
image_load(13): mag_decode failed (size=11017 code=11 at=255992)
  bpp=8 bw=640 h=400 total=256000 fabits=64000 clen=80 iters=64001 fb=2120 col=80 fapos=8000 famask=128 flen=8000
  brrej pos=8000 len=8000 cnt=1 baseoff=817 dsize=11017 faoff=817
  short cnt=3 it=4696 pos 18780->18782 ab=11 fb=280 col=80
bootmenu: bg image 13 MISSING, black fallback
```

字段速查：

| 字段 | 含义 |
|---|---|
| `code=11` | flag A 位流用尽（外层计数到 64000 次仍没填满 output） |
| `iters` | 实际迭代次数（正常应 64000；这里 64001 说明有"白跑"的迭代） |
| `short cnt/it/pos a->b/ab/fb/col` | 第一次"一次迭代没推进 4 字节"的现场（ab=action 字节，fb=flag B 位置，col=color 位置） |
| `fapos/flen` | flag A 已读字节 / 总字节（跑满则 8000/8000） |
| `brrej` | 位读取被拒绝的记录（当前 cnt=1 是正常的末尾拒绝） |

图像 13=`yellow_grid`，640×400、8bpp、11017B；`byte_width=640`、`output_total=256000`、
`action_size=160`、flagA=8000B(64000bit)、flagB=2120B、color=80B。位流与输出**严格 1:1**
（64000 bit × 4B），所以任何一次"少推进 2 字节"都会在末尾变成 `code=11`。

### 4.2 已落地的修复（195 的 F6/F7）

| 编号 | 内容 | 落点 |
|---|---|---|
| F6 | `mag_decode()` / `mag_decode_into()` 主循环前后 `_disable()`/`_enable()` | [mag.c](file:///home/edo/naiz/core/lib/mag.c) |
| F7 | `build/mag.o`、`build/a_mag.o` 单独用 `-od`（`-os` 会误编译本循环） | [Makefile](file:///home/edo/naiz/core/Makefile) |

历史证据（08:00 之前）：E1 `-od`+QMOUSE 4/4 失败；E3 去 QMOUSE 2/2 成功；E4 `-os`+cli 3/3
`code=13`；E5 `-od`+cli 4/4+2/2 成功。

### 4.3 为什么说"修好"是假的

| 事实 | 说明 |
|---|---|
| 同一 `engine32a.exe`（225732B，07:53 构建）在旧 `IMAGE.DAT`（含 ANI，940860B）上 6/6 通过 | 修复后的二进制本身没问题 |
| 删除 `img_map` id 17/18（ANI）后 `IMAGE.DAT` 变小 | 堆/加载布局改变 |
| 新布局下 2/2 失败（`at=255992`） | 失败随布局漂移 |
| 再去掉 QMOUSE（AUTOEXEC 只留 `engine.exe`）仍 2/2 失败（`at=255994`，short 移到 `it=4575 pos 18296`） | **本次不是 TSR**，`cli` 也不是万灵药 |

⇒ 存在第二个"写者"或第二个同签名缺陷，位置依赖地址。`cli` 只压住了其中一个。

> **2026-11-02 解释**：这个"第二个写者"就是自家钩子链（`smooth_advance` → `INT 21h`）。
> `cli` 挡住的是外部 IRQ/TSR 反射，挡不住引擎自己发起的 DOS 调用，所以"去 QMOUSE 仍失败"
> 并不矛盾。见 §4.0。

### 4.4 原定位计划（保留复盘；实际定案走的是"子调用分解"）

> 复盘结论：A→D 的粒度太粗。A 把钩子当整体开关，而真正的因子是钩子内部的三个子调用
> （`smooth_advance` / `audio_tick` / `anim+nb tick`）。实际只用"移除其中一个子调用"就定案，
> B/C/D 均未执行。下次遇到"钩子一开就坏"，先把钩子拆到子调用再设计对照。

**步骤 A — 关掉进度钩子（单因子，不要同时换优化档）**
`core/engine/audio.c` 里 `mag_set_progress_hook(frame_decode_pump)` 临时改为 `mag_set_progress_hook(0)`，
其余不动，重建 openpack，连跑 4 次。判据：`short cnt` 是否归零。
（这条能区分"钩子内部写坏"与"外部写者"。历史上试过一次但和 `-od` 混在一起，结论不干净。）

**步骤 B — 把解码状态移出栈**
`int fa_bit/out_pos/fb_pos/col_pos/act_idx` 等改放 `static` 结构或一次性 `malloc` 的结构
（194 试过 heap 但混入了 `-os` 变量，需在 `-od` 下重做）。判据：失败点是否改变或消失。

**步骤 C — 缓冲区固定化**
`output`/`action` 现在来自 `calloc`；改为固定大小的静态数组（256000B + 160B 在 DPMI 下可行，
或继续 calloc 但加"地址打印"日志）。目的：排除两缓冲区重叠/相邻越界。

**步骤 D — canary + 边界填充**
在 `output[-8..-1]`、`output[total..total+8)`、`action[-8..-1]`、`action[160..168)` 各放 8 字节
已知值，每 1KB 校验一次并记录第一次被改的偏移。判据：能直接看到"谁写到哪里"。

**步骤 E — host 侧参考解码**
用 Python 按 `mag_format.h` 的规则解同一份 `IMAGE.DAT` 中 image 13，输出 PNG 与引擎结果比对；
确认"数据/规格"无歧义（也是像素正确性的验收手段）。

**通用判据**：每次运行前微调 `IMAGE.DAT` 体积（例如增删一个无关的 THUMB 条目）以扰动布局，
连续 ≥6 次开机都必须 `ok`。只在一个布局下通过不算通过。

### 4.5 已知的可疑点（供排查参考）

- `hal_irq.c` 里已有结论：DOS/32A 链整条 PM IRQ 路径被禁用（否则 Timer-B 反射会落在应用栈上，
  历史上表现为 "2 字节短"，`code=11 at=255998`）——与 P7 的签名高度相似。
- `mag_diag` 的所有写点在失败路径才打印，但**写点本身每次迭代都发生**（tail 环、short 检查），
  这些写是 32 位常量偏移，理论上不会踩坏调用者；如果步骤 D 的 canary 显示 `mag_diag` 被写，
  那就说明存在越界写而不是反射。
- **（2026-11-02 补）写者已在自家钩子链里找到**：不是外部 TSR，而是 `frame_decode_pump()` →
  `hal_wallclock_smooth_advance()` → `INT 21h` 的 DPMI 反射。`hal_irq.c` 的签名（"2 字节短、
  `at≈255998`"）之所以与 P7 高度相似，是因为两者都是"反射帧落在应用栈"，只是触发源不同。

## 五、CauseWay 结论（已冻结，不作为交付链）

### 5.1 四种失败模式

| 存根 | 配置 | 结果 |
|---|---|---|
| 3.60（Devore 2000 原版） | 有 VEM486 | `CauseWay error 11` → 三重故障复位 |
| 3.52 | `cfg_dev` / `cfg_min` | 实模式 `Invalid Opcode at …`（`#UD`），崩溃点随配置变化 |
| 3.52 | HIMEMX + EMM386（VCPI） | EMM386 报 `no suitable UMB memory block found` 后**挂死** |
| 官方 `cwstub.exe`（47152B） | `cfg_dev` + `INT67FIX` | **静默退出**，`CW.LOG` 0 字节 |

### 5.2 根因收敛（共同指向 CW 的扩展内存获取与自身映像映射）

1. **环境不是瓶颈**：自写 `pmprobe.asm`（不依赖 CW）在 `cfg_min` 下成功开启 PE + 分页，
   在恒等映射的 `0x200000` 写读校验通过 ⇒ CPU/分页/线性地址都可用。
2. **XMS 分配落在低址**（`0x129000` 起），且与 `cw32_tr.exe` 映像偏移命中 ⇒ **分配页与自身映像重叠**。
3. **无内存管理器时 `GetINT15Page` 返回 0x2A8F8003（≈682MB，实装 15MB）** ⇒ 越界。
4. **上游 CW 源码没有 PC-98 分支**（全库无 `pc98/9801/nec` 实义命中）⇒ 只能靠补丁。

### 5.3 冻结（2026-11-02 定案，原复活计划作废）

**CW 已冻结，不作为交付链，不再修复。** 原 P0→P1→P2 计划停止：

- P1（钳制 `GetINT15Page` top + 强制 1MB 基址）已经**两轮实测无改善**，不要重试；
- 即使 P1 成功，CW 的 `RawSimulate` 裸 16 位门在本环境复位；要让它可用必须把反射层换成
  DPMI，等于替换核心子系统，投入产出不成立。

"是否必须"：

- **模拟器上：不必须**——cmpack 与 openpack 两条链都能启动进游戏；
- **实机上：无功能依赖 CW**，但 FreeDOS(98)+HIMEMX+DOS/32A 的实机组合尚未验证；
- **回退顺序**：DOS/4GW（历史实机方案）→ 自写最小 extender（DPMI 反射）→ CW（最差）。

完整依据、冻结范围与复活门槛见 [refdoc I03 §零](file:///home/edo/naiz/docs/refdocs/I03_CWTEST追凶经验总结-模拟器能力边界与后续方针.md)。
交付形态固定为：openpack 用 DOS/32A，cmpack 用 DOS/4GW。

## 六、踩坑清单（新机器最容易重复犯错）

1. **`SET DOS16M=1`**（商业链命门）：AUTOEXEC 少了它就"DOS/4GW 横幅后直接回 `A>`、串口 0 行"。
   已写入 `generate_autoexec()`（cmpack 输出、openpack 不输出）。见 [inject_common.py](file:///home/edo/naiz/tools/naiz_img/inject_common.py#L63-L77)。
2. **AUTOEXEC/CONFIG.SYS 每次注入都会重生成**：手工 patch 的版本会被下一次 `makegame` 覆盖。
   临时实验要么改 `generate_autoexec`，要么在 `make` 之后再 patch。
3. **`core/build/` 不跟踪 EXTENDER/`NAIZ_DOS32A` 变化**：切换链前必须 `rm -rf core/build`，
   否则会用另一条链的目标文件链接（能过、行为错）。
4. **`engine_a.exe` 也要同步部署**：只换 `engine.exe` 会报 "engine_a 落后于 core/engine_a32a.exe"。
5. **`-l=dos32a` + `-os` 曾出现 `fatal (4005)`**；`-od` 正常。LE fixup 数据本身经逐页校验是合法的。
   所以"能不能启动"依赖布局，任何体积变化后都要跑开机冒烟。
6. **删除 hdi 后 makegame 会从基座重建**：`tools_commercial/base_msdos5_scsi_48m_clean.hdi`（商业）、
   `tools_open/base_freedos98_scsi_10m_clean.hdi`（开源）。
7. **`ASSETS.DB` 与源文件不同步**：`img_map` 里指向不存在的文件会让 `pack_images` 直接 `sys.exit(1)`。
   已删 id 17/18（ANI），当前 40 行、ANI=0；若从 git 历史恢复 `ani/*.ANI`，要同时把行加回。
8. **`NAIZ_DEBUG` 默认 ON**：串口验收依赖它；关掉后"引擎在跑"也会看起来像"没启动"。
9. **pkill 用 `-x`**；`screendig --launch` 适合无串口输出的场景。
10. **工作区有未提交改动**（`git status` 见 §八）：不要盲用 `git checkout`。

## 七、代码索引

| 文件 | 关键点 |
|---|---|
| [core/lib/mag.c](file:///home/edo/naiz/core/lib/mag.c) | `mag_decode` @~270-500（含 F6 临界区、short 检查）、`mag_decode_into` @~700-820（同样结构） |
| [core/lib/mag.h](file:///home/edo/naiz/core/lib/mag.h) | `MagDiag`：`iters/progress/error/fa_* /short_* /tail_* /err12_*`，`extern mag_diag` |
| [core/engine/image.c](file:///home/edo/naiz/core/engine/image.c) | 失败路径打印（`code=… at=…`、`short cnt=…`、`brrej`）；成功路径 `image_load(%d): ok` |
| [core/engine/bootmenu.c](file:///home/edo/naiz/core/engine/bootmenu.c) | `bg image 13 loaded/MISSING` 打印 |
| [core/Makefile](file:///home/edo/naiz/core/Makefile) | `NAIZ_DEBUG ?= ON`；`build/mag.o`、`build/a_mag.o` 的 `-od` 规则；`open:` 目标 |
| [core/plat/hal_irq.c](file:///home/edo/naiz/core/plat/hal_irq.c) | DOS/32A 拒绝 PM IRQ 的说明（Timer-B 反射 → 栈短 2 字节，`at=255998`） |
| [tools/naiz_img/inject_common.py](file:///home/edo/naiz/tools/naiz_img/inject_common.py) | `generate_autoexec()`（`SET DOS16M=1`）、`_generate_config()`（VEM486/HIMEMX）、`_is_open_pack()` |
| [tools/naiz_build/pack_images.py](file:///home/edo/naiz/tools/naiz_build/pack_images.py) | `IMAGE.DAT` 打包；缺文件硬失败 |

## 八、当前工作区状态（自查命令，不写死快照）

工作区快照最容易过期，交接时请用命令现场核对，不要相信本文里的旧值：

```bash
cd /home/edo/naiz
git log -1 --oneline          # 写作时 44fcfb9；P7 定案时 42fc1f3
git status --short
git diff --stat
```

2026-11-02 P7 定案时的参照值（**以命令输出为准**）：

- HEAD `42fc1f3 20261102update1-migrate`
- 未提交改动 5 个文件：`core/engine/frame.c`（P7 修复）、`core/lib/mag.c`（注释/诊断）、
  `core/plat/hal.h` + `core/plat/hal_pc98.c`（`coast` 实验残留，待清理）、
  `tools/naiz_img/inject_common.py`（`NAIZ_AE_PAD` 布局旋钮）
- 尚无 `devdocs/197`：P7 定案记录在本文 §4.0 与 refdoc I04
- `disks/demo-a2.hdi` 属于哪条链**取决于最后一次 `makegame --pack`**，不要用旧快照判断；
  `cmpack` 可用物证见 §九 `artifacts/demo-a2-cmpack-current.hdi`

产物快照（新机器重新构建即可，不必拷贝）：`core/engine.exe` / `core/engine32a.exe`
均由 `bash core/build.sh`（或 `bash core/build.sh open`）现场生成。

## 九、随附材料（/tmp 下与本项目相关的**全部**内容已移入 `~/inuse`）

目录：`/home/edo/inuse/naiz_handoff_20261102/`（与原 `/tmp` 同一机能直接 `mv`，已按类别归置）

| 子目录 | 规模 | 内容 |
|---|---|---|
| `evidence/` | 181 文件 / 2.6MB | 所有日志、截图、`*.txt`/`*.json`：`op1/2.log`（P7 失败）、`noq1/2.log`（无 QMOUSE 复现）、`cmok1-3.log`+`cmfinal.log`（cmpack 通过）、`d16.log`（`SET DOS16M=1` 生效）、`ext4g.log`（外部 loader 无效）、`cm_screen.png`/`cm_ext.png`、`hi.png`/`hi_novem.png`、`nou.png`、`s2..s6`/`h194`/`o195`/`run194` 等历史轮次日志 |
| `analysis/` | 39 文件 / 19MB | 复原与验证用的小程序与二进制：`magtest.c`、`mag_probe.py`/`mag13_*.py`、`lefix*.py`、`t32.c`、`np2_*` 对照产物、`mag.o`/`mag195.o`/`mag.dis`、`id13.mag`/`img13.bin`/`img5.bin`、`engine32a_irq1.exe` 等 |
| `cw/` | 28 文件 + 12 树 / 95MB | CW 系全部：`cwclean3`（P1 修改目标 `source/all/raw_vcpi.asm`）、`cw_base`（`run_local.sh`/`np2_15m.toml`/`cfg_dev.sys`/`cfg_min.sys`）、`cwupstream*`、`cw373`/`cw373b`/`cwclean2`/`cwclean4`/`cwcmp1`/`cwcmp2`/`cwfix1`/`cwprobe1`（中间构建树）、`restore_*.asm`、`diff_*.txt`、`np2_*.c/h`（np2kai 源码摘录） |
| `artifacts/` | 169 项 / 93MB | **仅保留 1 份最新可用盘** `demo-a2-cmpack-current.hdi`（50MB，cmpack，AUTOEXEC 52B 含 `SET DOS16M=1`；原件在仓库 `disks/demo-a2.hdi`）；另含 `out_*`（CW 构建输出与被测 EXE）、`*.zip`、`shots/`、`session_*`/`naiz_screendig/` 启动会话 |

**HDI 清理（2026-11-02）**：原有 40 份 HDI 快照（5.2GB：`b*.hdi` 基座体积实验、`open_v*/open_final*/diag_*`、
`fdhyb_B2R` 及其 `.bak`/`.preclidos`、`d2..d5`、`cm.hdi`）已全部删除——这些都能用仓库基座
（`tools_*/base_*.hdi`）+ `makegame` 重新生成。现在只留 `demo-a2-cmpack-current.hdi` 一份作为"已知可用盘"的物证。
整个交接目录因此从 5.4GB 降到 **209MB**（其中 `cw/` 95MB、`artifacts/` 93MB、`analysis/` 19MB、`evidence/` 2.6MB），可整包带走。

**未移动**（与项目无关的系统/会话文件）：`.X11-unix`/`.ICE-unix`/`.font-unix`/`.dotnet` 等套接字目录、
`systemd-private-*`、`clr-debug-pipe-*`、`dotnet-*`、`fcitx-socket-*`、`dbus-*`、`ai-agent`、`trae*`、`opencode`、
`pytest-of-edo`、`mintUpdate`；以及 `cwbuild`/`cwclean`/`cw_diag`/`cworig`/`cwsrc`/`cwtest`/`fd98`/`kernel_build`/`nasm_local`
这些**指向 `~/inuse` 的软链接**（随 inuse 本体走，无需单独搬）。

注意：`cw_base/*.sh`、`inject_*.py` 里**硬编码了 `/tmp/cw_base/...`**。搬到新机后要么
`ln -s <新路径>/cw_base /tmp/cw_base`，要么把这些路径替换掉。

---

## 十、待办（按顺序）

1. ~~**P7 布局矩阵验收**~~（已完成）：openpad 0/64/192/320/512 每布局 ≥3 次开机，**16 次全过 0 失败**。cmpack 布局矩阵 pad=0/192/512 各 1 次全过。已清 coast 残留（hal_pc98.c / hal.h）。
2. 像素正确性（可选）：host 参考解码或 `makegame.sh test demo-a2` 人工截图。
3. `NAIZ_AE_PAD` 标注：保留作为验收工具，但在 inject_common.py 注释里标明"仅用于布局矩阵验收，非生产代码路径"。
4. 商业链复核：确认 `SET DOS16M=1` 在 cmpack makegame 全流程里保留。
5. 修 `tools/tests/test_sync_decode_allowlist.py` 的字符串字面量误计（守卫会少报）。
6. **CW 保持冻结**：不设复活计划。若确有需求，先满足 I03 §零的复活门槛，再按 G0→G2 路线（不要重试 P1 补丁，也不要修 CW 源码）。
