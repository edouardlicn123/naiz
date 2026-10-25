# 131 — 剩余颤动与立绘加载拖慢：unlove 反编译对照、网络调研与方案分析

> 状态：`分析/建议（未实施）`
> 版本：`0.3.028（现状基线）`
> 相关：devdoc 129（帧泵：修冻结/打断）、devdoc 130（vclock 平滑变步进：修颤动）、
> devdoc 82（时钟/帧率实测）、devdoc 107（虚拟时钟下沉 HAL）、
> `docs/B19-时钟计算经验参考.md`、`docs/refdocs/F03_opna_fm_and_bgm_routes.md`、
> `docs/refdocs/B02_io_ports.md`、`tools/tests/test_frame_pump.py`、`tools/tests/test_vclock.py`
>
> 本文档**只做分析与建议，不改任何代码**。任何实施另立 devdoc（编号 +1），
> 并按 §十「规格与实现的收敛责任」逐条核对声称与行号后收口。

---

## 0. 摘要（TL;DR）

- 两个残留症状（BGM 颤动、立绘加载拖慢）有**同一个结构性根因**：把「音乐泵」挂在
  **主循环的协作式轮询**上，于是**任何长耗时操作**（MAG 解码）都会**饿死音乐泵并冻结虚拟时钟**。
- **原版游戏 `EQAP32.EXE` 没有这个问题**：它把音乐交给 **PMD 常驻驱动 + YM2608 Timer-B
  硬件定时器中断**，与主循环解耦。**这是本轮最关键的对照发现**。
- **unlove 的重实现也没有解决它**（`M86_Play()` 同步忙等）——这反证「不颤」靠的不是
  播放器本身，而是**中断驱动架构**。
- 网络调研给出四条可落地路径：**分片让步**、**中断驱动音泵（复刻 PMD）**、
  **预载隐藏解码**、**固定 tick 音序**；并给出 DOS/4GW 挂中断的**具体 API 与硬约束**。
- 本项目 B19 已排除「PIT 读回」「VSYNC 计帧」两条时钟源（NP2kai 下不可用），
  故**不能再走**这两条；时钟源方向的唯一未探索项是 **OPNA Timer A/B**（与 PMD 同源）。

---

## 1. 现状基线

### 1.1 已落地机制（c58 / c59 之后）

| 已落地 | 位置 | 作用 |
|---|---|---|
| 统一帧泵 | `core/engine/frame.c` `engine_frame_pump()` | 顺序固定：`vblank_wait → hal_wallclock_smooth_advance → anim_tick → audio_tick → nb_dialog_reveal_tick`，每个 pass 一次 |
| 帧泵接入 | `main.c` ×3、`nb_interact.c:85`、`nb_menu.c:281`、`nb_setting.c:379`、`nb_saveload.c:277`、`nb_save_dialog.c:136`、`nb_cggallery.c:329,360`、`nb_special.c:85` | 菜单/询问/存读档/CG 画廊/特殊界面/设置等自含循环不再冻结音频 |
| 平滑虚拟时钟 | `core/lib/vclock.{c,h}` | `VCLOCK_SLEW_UNITS=8`（0.5ms/pass 上限）平滑逼近实测速率；废止旧 floor/ceiling 钳制 |
| 时钟 writer/reader 切分 | `core/plat/hal_pc98.c:113-121` | `hal_wallclock_smooth_advance()` 唯一写入方（帧泵）；`hal_wallclock_smooth_ms()` 只读 |
| MAG 解码进度钩子 | `core/lib/mag.c`（4 个调用点）、`core/engine/audio.c` | `audio_init()` 注册 `audio_tick` 为 `mag_set_progress_hook`；`MAG_PROGRESS_STRIDE=4096` |
| 立绘缓存 | `core/engine/image_cache.c:22` | `IMAGE_CACHE_SLOTS=8`，LRU |

**测试基线**：`pytest 760 passed / 1 skipped`；`make -C core` 0 err / 0 warn。

### 1.2 症状定义

| 症状 | 现象 | 触发条件 |
|---|---|---|
| **颤动（flutter）** | 节拍不稳：音符起奏间隔忽长忽短，不是「停表」 | 主要在解码/长操作窗口内与之后 |
| **立绘加载拖慢（slowdown）** | `char`/`cg` 首次显示明显卡顿（帧率骤降） | 缓存未命中、整段 MAG 解码时 |

> 注：症状 1 与症状 2 在用户主观感受上常同时出现（同一帧窗口内），但成因可分别归因（见 §2.4/§2.5）。

---

## 2. 现状机制剖析（为什么还会颤、还会拖）

### 2.1 执行模型：协作式帧泵（cooperative）

引擎是**单线程协作式**：所有「后台」工作（动画、音频、打字机）都在主循环里**轮询**推进。

```
main loop:
    engine_frame_pump()      ← 每 pass 一次：vblank + vclock.advance + anim + audio + reveal
    nb_process()             ← NB 脚本解释；其间可能整段 mag_decode()（纯 CPU 阻塞）
```

`engine_frame_pump()` 是**唯一的节拍入口**；它让「音乐时间」与「画面时间」共用同一个推进点。

### 2.2 时钟链

```
DOS INT 21h AH=2Ch ──► hal_wallclock_ms() ──► vclock_advance() ──► vclock_ms()
      (秒级成簇)         (hal_pc98.c:81)       (帧泵唯一写入)     (只读消费)
                                                                      │
                        ┌─────────────────────────────────────────────┼──────────────┐
                        ▼                                             ▼              ▼
                   anim_tick()                              audio_tick()（BGM 事件表）  nb_dialog_reveal_tick()
```

- `hal_wallclock_ms()` 用 `int386(0x21,…)` 取 DOS 系统时间：`CH`=时 `CL`=分 `DH`=秒 `DL`=百分秒。
- **NP2kai 下 `DL` 恒为 0，秒级成簇交付**（冻 3–6s，然后 +1000..+6000ms）——devdoc 82/107、
  B19 §2.3 已实测。
- `vclock` 用 slewing 把「冻结→猛跳」抹成「每 pass ≤0.5ms 的均匀小步」，解决的是**步长抖动**，
  不是**时间流动本身**。

### 2.3 解码路径

`image_load()` → `mag_decode()` / `mag_decode_into()`：**整段循环、纯 CPU、无 yield**。
`mag.c` 是平台无关 lib，进度钩子签名 `void(*)(void)`，引擎侧注册的是 `audio_tick`。
解码期间：

- 主循环**卡在这个函数里**，帧泵**不运行**；
- 钩子每次调 `audio_tick()`，但 `audio_tick()` 只**读** `vclock_ms()`、**不推进**时钟、**不让出 CPU**。

### 2.4 为什么还颤（时序根因）

`hal_wallclock_smooth_advance()` 是虚拟时钟**唯一写入方**，且**只在帧泵里调用一次**。
解码进行时：

1. 虚拟时钟**冻结**在上一帧的值；
2. `audio_tick()` 每次读到**同一个** `vclock_ms()`；
3. 音符事件按绝对时间表 `cur = vclock_ms() - wall0` 触发，`cur` 不前进 ⇒ **解码期间事件一个也不发**；
4. 解码结束、帧泵恢复，读到一大段真实时差，`vclock` 以 slewing 慢慢「回填」这段差值。

结果：**时间不是连续流动，而是「静止 → 缓慢回填」**。slewing 保证了相邻步差有界（不爆），
但**没有**保证「解码期间时间照常流动」。耳朵对**节奏连续性**敏感 ⇒ 残留颤动。

### 2.5 为什么还拖（CPU 根因）

解码循环纯 CPU 占满、**不主动让出**；`hal_vblank_wait()`（唯一的让出点）不在解码路径上；
进度钩子只调 `audio_tick()`（不等待）。⇒ 解码整段时间画面停更 ⇒ 目视卡顿。
**提高 `MAG_PROGRESS_STRIDE` 只减少钩子调用次数，不减解码耗时本身。**

### 2.6 一个被忽视的约束：NP2kai 下没有可靠的微秒级软件时钟

B19 §2 已实测淘汰两条候选（**本轮不要重复**）：

| 候选 | 结果 |
|---|---|
| PIT 8253 读回（端口 0x71/0x75/0x77） | **不可用**：NP2kai 读回 = `nevent_getremain(NEVENT_ITIMER)/pccore.multiple`，由模拟 CPU 时钟驱动、非单调 |
| VSYNC 帧计数（GDC 0xA0 bit5） | **不可用**：NP2kai pass 率仅 ~20.5Hz，帧计数每秒只推 ~342ms（慢 3 倍） |
| DOS `INT 21h AH=2Ch` | 宏观可用、**微观秒级成簇** |

⇒ **结论**：在 NP2kai 下，靠「软件读硬件计数器」拿不到亚秒稳定时钟。
唯一未探索、且理论上能提供**精确周期**的时基是 **YM2608 的 Timer A/B**（芯片定时器，见 §4.1）
——它同时也是原版 PMD 的节拍源。这直接抬高了「方案 C（中断驱动）」的价值。

---

## 3. unlove 项目对照（PC-98 galgame 反编译）

**unlove**（`~/unlove`）= 对 PC-98 galgame **Love Escalator** 的完整反编译 + 诊断/重实现工具，
是我们最贴近的同题材参照物。

### 3.1 项目性质与结构

- 目录：`engine/`（自研引擎 `unlove.exe`，Watcom 16-bit 实模式 `-ml -0`）、
  `engine_re/notes/`（逐日反编译笔记 day1..day9）、`extracted/`、`LOVE/`（原始数据）、
  `refprojects/loveEscalatorTL/`（Node.js `pack.js` 重打包 LOVE.EAR）、`devdocs/`。
- 自研引擎当前**只是诊断工具**（菜单：显示 ECG、列目录、播 M86），非完整游戏。

### 3.2 原引擎 `EQAP32.EXE` 的架构（关键证据）

来自 `~/unlove/engine_re/notes/`（day1/day2/day7/day9）：

- **DOS/4GW 32 位保护模式**（`LE` 可执行，Watcom C/C++ 编译）；
- **WVIDEO** 自研视频驱动（直接操作 GDC `0xA0/0xA2` + VRAM）；
- **PMD / PMDB2 常驻驱动**：字符串证据 `Startup PMD ...` / `WARNING: Cannot detect PMD`
  / `FATAL: Cannot detect PMD`（多处）——说明**游戏启动时会探测常驻驱动是否存在**；
- 支持 **YM2203 / YM2608**；
- 资源容器 `LOVE.EAR`（961 条目）：`EQA` 脚本 63、`ECG` 图片 702、`M86`/`M26` 音乐各 47、`PCL` 89。

**外部独立佐证**：DefleMask 论坛 PC-98 乐器导出帖明确把 **Love Escalator 归入使用 PMD 的游戏**。

### 3.3 PMD 的时序模型 = 硬件定时器中断，与主循环解耦

- PMD 是**常驻驱动**（`PMD.COM`/`PMD86.COM`/`PMDB2.COM`），由 `GAME.BAT` 先于游戏加载；
  游戏通过**中断 API**（`AH` 功能号，ReC98 记录有 `AH=09h`、`AH=22h`）与它通信。
- PMD 用 **YM2608 Timer-B 驱动节拍**：MML 的 `#Tempo` / `#Timer` **直接写 Timer-B 值**。
- ⇒ **音乐节奏由芯片定时器中断推进，与主循环是否卡住无关**。原版即便在解码一张 `ECG`、
  或在 EQA 脚本里耗时，音符照常按定时器滴答输出——**从架构上消除「解码导致音乐停/颤」**。

### 3.4 unlove 重实现的时序模型（反面参照）

`~/unlove/engine/m86.c` 的 `M86_Play()` 是**同步阻塞忙等**（原文）：

```c
for (i = M86_HEADER; i + 1 < size; i += 2) {
    uint8_t reg = data[i], val = data[i + 1];
    if (reg == last_reg && val == 0x00) { delay_count++; continue; }   /* 重复 (reg,0) = 延时标记 */
    if (delay_count > 0) {
        volatile uint32_t j;
        for (j = 0; j < delay_count * 500UL; j++);                    /* 忙等延时 */
        delay_count = 0;
    }
    OPN_WriteReg(reg, val);
    last_reg = reg;
}
```

即把 `M86` 当作「OPN 寄存器写序列 + 忙等延时」来播——**同样挂在主循环、同样没有定时器中断**。
⇒ **unlove 复现的正是我们当前的模型，而不是原版的模型**：一旦主循环被解码占住，音乐一样停。
这反证「不颤」靠的是 **PMD 常驻驱动 + 定时器中断**，不是 M86 数据或播放器写法。

### 3.5 对照结论

| 维度 | 原版 `EQAP32`（Love Escalator） | unlove 重实现 | 本项目 naiz |
|---|---|---|---|
| 音乐时序来源 | **OPNA Timer-B 硬件中断（PMD 常驻驱动）** | 主循环忙等延时 | 主循环协作轮询（帧泵） |
| 解码是否影响音乐 | **否**（定时器独立推进） | 是（同主循环） | 是（帧泵被阻塞、时钟冻结） |
| 解码是否影响画面 | 是 | 是 | 是（拖慢） |
| 音乐数据格式 | PMD 编译格式（`.M/.M2` 系，`M86/M26`） | 同左（寄存器流解读） | MIDI（`AUDIO.DAT`） |
| 运行时资源命名 | `EQA/ECG/M86/M26/PCL` | 同左 | `SCENE.DAT/IMAGE.DAT/AUDIO.DAT` |

**一句话**：两个残留症状在原版架构下**结构性不存在**；我们（及 unlove 重实现）用协作轮询，
代价就是任何长耗时操作都牺牲节拍与流畅度。

---

## 4. 网络调研（逐条，附出处）

### 4.1 YM2608 Timer A/B 精确规格（方案 C 的寄存器基础）

**Yamaha YM2608 手册节 2-8**（多源一致：ManualMachine、cpcwiki 译本、retroweb）：

- **Timer B**：`tB = 1152·(256−NB)/φM`；φM=8MHz ⇒ 基准周期 **144µs**，可设周期 `144·(256−NB)µs`
  —— ⚠ **口径订正（2026-10-24，纯文档）**：手册的 1152 配的是 **φM/2** 时钟，实机每步是 **2304 主时钟 ⇒ 288µs**（NB=200、φM=7.9872 MHz ⇒ 16.154 ms）。见 `docs/refdocs/F07_opn_timer_clock_reference.md`；本文其余分析不受影响。
  （NB:0–255）。寄存器 **`$26`** 装 NB（8-bit）。
- **Timer A**：`tA = 72·(1024−NA)/φM` ⇒ 基准 **9µs**，范围 9µs–9216µs。寄存器
  **`$24`（高 8 位）+ `$25`（低 2 位）**。
- **Timer 控制 `$27`**：`D0/D1`=LOAD（启动/停止 A/B）、`D2/D3`=ENABLE（是否在溢出时置标志并拉低
  `!IRQ`）、`D4/D5`=RESET（清标志，读后自清）。
- **⚠ 最后一块拼图 `$29` `IRQ ENABLE`**：`D0`=EN_TA、`D1`=EN_TB——**不写 `$29` 拿不到 IRQ**。
  devdoc 131 早期稿只写到 `$26/$27`，本轮补齐。
- 状态/IRQ 标志在 **`$110`**（本项目 F03 §3.6 已收录）。

**模拟器一致性**：QEMU `pc98-opna.c`（`awemorris/qemu-pc98`）确认 PC-98 OPNA 定时器
按 `cnt/clock` 计时并**触发 FM 中断（默认 IRQ 3）**，且同时模拟 MAME YM2608 与 emu2149 SSG；
NP2kai 亦模拟 OPNA 定时器。⇒ **中断时序在模拟器里可信**（仍需实机探针验证，见 §9）。

### 4.2 PMD 的 Timer 语义（佐证「标准做法」）

- PMD 英文文档 §2.10：`#Timer` / `t` 命令**直接设 TimerB**。
- `mml-guide` PMD 进阶：`TimerB = 256 − 10800000/(bpm · 13 · Zenlen)`；`#Timer` 范围 1–255。
- ValleyBell `pmd_SeqFormat.txt`：`FC tt` = 设 Tempo 为**原始 OPN Timer-B 值**；`EB kk` = OPNA Rhythm Key On。
- ⇒ PC-98 把节拍交给 OPNA Timer-B 是**当年标准做法**，不是奇技淫巧。

### 4.3 PC-98 垂直回扫中断（另一条硬件中断源，此前未收录）

- ReactOS `drivers/pc98/video.h`：`GDC1_IO_o_VSYNC 0x64 /* CRT interrupt reset */`。
- DOSBox-X `vga_pc98_gdc.cpp`：写端口 **`0x64` = 置位触发 vsync 中断（IRQ 2）**。
- ⇒ PC-98 有**帧同步中断**，可作 60Hz 帧时钟或「每帧泵一次」，**不必碰 PIT**。
  （真机垂直回扫 60Hz；NP2kai 下是否能稳定产生该中断需实测。）

### 4.4 DOS/4GW 下挂中断的具体 API（决定方案 C 可行性）

- DJGPP `faq18_9` / `hal`（Peter Marinov）：`_go32_dpmi_chain_protected_mode_interrupt_vector()`、
  `_go32_dpmi_allocate_iret_wrapper()`、`_go32_dpmi_get|set_protected_mode_interrupt_vector()`。
- **硬约束**：handler 触及的**所有内存必须 lock**（`__dpmi_lock_linear_region`，
  或 `_crt0_startup_flags |= _CRT0_FLAG_LOCK_MEMORY`）。C 写 handler **无法可靠 lock 自身代码/栈**
  ⇒ 官方推荐**汇编 handler**，或关闭分页（CWSDPR0 / PMODE/DJ）。
- `INT 1Ch/23h/24h` 会被反射到保护模式；纯软件 `INT 1Ch` 是**最省事的挂点**——
  但 `INT 1Ch` 的速率绑定 PIT 0（18.2Hz 或改频后）。
- DOS/4GW 手册 §5.8「bi-modal interrupt handler」：PM 与 RM handler 的挂接顺序与互斥。
- ⇒ **方案 C 在 DOS/4GW 下可行但需谨慎**：优先挂 **OPNA IRQ**（硬件定时器，与墙钟无关）
  或 **GDC vsync IRQ 0x64**，并把 handler 写成汇编 + 锁内存。

### 4.5 经典 PIT 改频 + INT 8 链接模板

expiredpopsicle《DOS Timer Stuff》：`_dos_getvect/_dos_setvect(0x08, …)` + 重编程 PIT 除数
（`1193181/1000`），**只在累计到 18.2Hz 时才调原 handler**，其余走 `timer_clearInterrupt()`。
可直接照搬到 PC-98（PIT 端口 `71h/75h/77h`，B02 §定时器）。**注意**：本项目已判定
PIT **读数**在 NP2kai 不可靠（§2.6），但**改频产生中断**是另一回事（中断是否被 NP2kai 按
预期节流仍未测）。此条仅作方案 C 的候选实现参考。

### 4.6 高分辨率时钟候选（含本项目已排除项）

XtoF《Timing on the PC family under DOS》列出：Refresh Detect（CTC ch1 回读，15.0857µs）、
Vertical Retrace（polled，1/60–1/72s）、RTC、加快 CTC ch0。**但**：
- Refresh Detect / PIT 回读 = §2.6 **已实测淘汰**（NP2kai 非单调）；
- VSYNC 帧计数 = §2.6 **已实测淘汰**（~20.5Hz）。

⇒ 本节仅作**知识留档**：真机上这些源可用，NP2kai 下不可用，故**不作为本轮方案**。

### 4.7 流式音频的「尖峰」与「分片」（方案 B 的工程证据）

DCEmulation《Streaming Music Playback CPU Usage》（最强类比）：
- 解码器「攒满一大块才解」⇒ **单帧 CPU 尖峰高达 60%**，平均仅 16%；
- 改成**每帧手动小片回填**后，**最坏尖峰 60% → 25%**；
- **量化方法**：忙循环自增全局变量、**vblank 归零**，测每帧空闲余量——可直接用来标定分片粒度；
- 结论：要「不卡」，必须把长解码**切成帧预算内的小片**，而不是一次做完。

### 4.8 预载隐藏解码（方案 D）

Defold 论坛《Sound stutter while loading…》：同步 `create` 触发上传 ⇒ 卡顿；
先**异步 `load`（预载）**再 `create` ⇒ 卡顿消失。映射到我们：
**缓存未命中是主因**（`IMAGE_CACHE_SLOTS=8`）——可在对白/空闲期**预解码下一场景立绘**，
或对 `cg`/`char` 走「先出低质量占位、后台补齐」。

### 4.9 反面警示（方案 C 的真实风险）

DOSBox-X issue #342《Blackbird: FM music interrupt problems》：
- PC-98 **FM 音乐因 game 的 FM ISR 未正确 ACK（级联 IRQ 处理错）而卡死**；
- **鼠标 IRQ 13 优先级高于 FM**；级联（cascade）IRQ 的 in-service 位处理不当会导致音乐停；
- ⇒ 方案 C 必须：正确 EOI（含级联）、评估与键鼠中断的互斥、验证 NP2kai 的中断注入时序。

### 4.10 其他佐证

- **NEC PC-98 Sound BIOS**（Wikibooks）：OPN 内置音乐 BIOS，**中断需应用自建**（向量写 `0xCEE00`），
  「以 OPN reg A 作节拍器、reg B 调制、挂在 PIC 上、metronome tick ≥5ms」——
  PC-98「用 OPNA 定时器当节拍」的**官方背书**（属 real-mode BIOS，DOS/4GW 下未必可直接用）。
- **QEMU `pc98-opna.c`**：PC-98 FM 定时器触发 **IRQ 3**（默认）；周期 = `cnt/clock`。
- **Microprose MPS/MMUSIC 解码**（`music_v1.txt` 的 `MpsMachine`、ScummVM `music_v1.txt`）：
  **帧制音序器**（每帧 `tempo_ticks` 扣减、6.5ms/帧）——即 `audio_tick` 的现代同构，
  差别只在「谁驱动这一帧」。
- **Amiga `ptplayer`（CIA-B 定时器）**、**Rayman TPLS TSR**（把播放 handler 注入游戏
  `HMIDRV.386`，v2.0 注入 32-bit 保护模式载荷）——「常驻音频驱动」范式的 DOS/其他平台实例。

---

## 5. 根因综合图

```
                         ┌───────────────────────────────┐
                         │  主循环（单线程协作式）         │
                         └───────────────┬───────────────┘
                                         │
              ┌──────────────────────────┴────────────────────────────┐
              ▼                                                       ▼
   engine_frame_pump()                                       nb_process()
   ├ vblank_wait()                                            └─► mag_decode()  ← 纯 CPU 整段阻塞
   ├ hal_wallclock_smooth_advance()  ← 虚拟时钟唯一写入         │   （期间帧泵不运行、时钟冻结、不让出）
   ├ anim_tick()                                                │
   ├ audio_tick()  ── (BGM 事件表, 读 vclock_ms)                 │
   └ nb_dialog_reveal_tick()                                    │
                                                                ▼
                                          mag 进度钩子 = audio_tick()（只读、不让出）
                                          ⇒ 解码期间事件不发、时钟不走

根因 1（颤）：vclock 只在帧泵推进；解码期时钟冻结 → 事件停 → 事后缓慢回填
根因 2（拖）：解码纯 CPU 循环、无 yield；唯一让出点 hal_vblank_wait() 不在路径上
共同结构根因：音乐/时间泵 = 主循环轮询（非中断驱动）
```

---

## 6. 方案空间

### 6.0 判据

- **治标**：让卡顿变轻，但解码期间时间仍不流动（音频仍不派发）。
- **治本于「拖」**：解码不占满 CPU、画面照常更。
- **治本于「颤」**：解码期间**时钟照常推进、音频事件照常派发**。
- **结构性治本**：音乐泵脱离主循环（中断驱动），任一长操作都不影响节拍。

### 方案 A（最小改动、低风险）：`audio_tick()` 内节流让出 CPU

在 `audio_tick()` 加静态计数器，每 N 次（8/16）调一次 `hal_vblank_wait()`（`hal.h` 已声明）。

- 效果：解码期间偶尔让出，缓解「拖」；时序逻辑不变（仍只读 `vclock_ms()`）。
- 代价：极小；不触碰 `mag.c`、不触碰时钟所有权、不触碰任何现有测试契约。
- 局限：**治标**——不能真正让节拍在解码期间照常流动（「颤」仍在）。

### 方案 A′（时钟源改进）：**本轮判定为死路（在 NP2kai 下）**

- 已被 B19 §2 排除：PIT 回读、VSYNC 帧计数在 NP2kai 不可用；DOS 2Ch 微观成簇。
- 唯一未尽方向：**用 OPNA Timer A/B 探针读回**作高分辨率源——但这需要 OPNA 端口访问，
  **已属于方案 C 的实现范围**，非独立方案。⇒ 合并进 C，不单列。

### 方案 B（中等）：把解码切成「帧分片」，每片回一次帧泵

将 `mag_decode()` 整段改为**分片解码**（每解一定行/字节后回到帧泵子集
`advance + audio`，必要时含 `vblank_wait`）：

- 解码期间**时钟照常推进**（解 §2.4），音频事件照常派发（**治本于颤**），
- 顺带让出 CPU（**治本于拖**），
- 与 §4.7 的工程证据一致：把大块解码切成帧预算内的小片可显著压低最坏尖峰。

**契约障碍（必须正面解决）**：`hal_wallclock_smooth_advance()` 现在**只在
`engine_frame_pump()` 里被调用一次**，测试
`test_frame_pump.py::test_smooth_advance_owns_the_step` / `test_frame_pump_sequence_is_exact`
钉死此点。若分片泵也推进时钟，则违反「每逻辑帧一次」。
**合规改法**：把「推进时钟」抽成一个**每逻辑帧至多执行一次**的幂等步骤
（例如帧泵与解码分片泵共用一个 `frame_advanced` 标志的 `advance_once()`），
并**同步更新测试契约**——属改契约，**必须另立 devdoc** 并按 §十 收口。

- 代价：中；触及 `frame.c/.h`、`mag.c` 分片粒度、`image.c` 调用链、`test_frame_pump.py`。
- 风险：分片粒度过小 → 钩子/切换开销上升；过大 → 让步不足。需按 §4.7 方法实测标定。

### 方案 C（架构级、最贴近原版）：OPNA Timer-B 中断驱动音泵

复刻 PMD 模型：

1. 初始化 **YM2608 Timer-B**：写 `$26`（NB）、`$27`（ENABLE/LOAD）、**`$29`（EN_TB 使能 IRQ）**；
2. 挂 **IRQ handler**（DOS/4GW：汇编 + 锁内存，见 §4.4；或挂 GDC vsync IRQ 0x64，§4.3）；
3. handler 里推进 `fmseq_pump()` / MIDI 事件表，主循环只管画面；
4. 正确 EOI（含级联），规避 §4.9 的鼠标/级联陷阱。

- 效果：**结构性消除**「解码导致音乐停/颤」，与原版一致；同时天然提供**精确周期时基**
  （Timer B 实际 288µs/步精度），可顺带解决 §2.6 的时钟量化。
- 代价：高。中断挂接（保原向量、EOI、可重入、锁内存）、与协作帧泵的**并发竞态**
  （时钟/事件表读写）、NP2kai 中断时序验证；且 `audio_tick()` 的「单一消费方」假设、
  `vclock` 所有权、`test_frame_pump.py` 契约都要重估。**必须独立立项**。

### 方案 D（预载/预热）：把解码藏起来

- 对白/空闲期**预解码下一场景立绘**（预取），命中 `IMAGE_CACHE_SLOTS`；
- 或对 `cg`/`char` 走「先占位、后台补齐」的两段式。
- 效果：从**用户路径上消除**解码停顿（**治本于「拖」**，对「颤」无效）。
- 代价：低—中；只碰 `image.c`/`image_cache.c` 与场景调度，不动时钟/帧泵契约。
- 风险：内存/缓存槽压力；预取时机若选错（如对白期间仍有大量解码）会加剧争用。

### 方案 E（固定 tick 音序）：不依赖墙钟微秒

放弃「按真实毫秒派发事件」，改为**每个音乐 tick 固定消费固定数量的音频步**
（如每帧固定推进 K 个 MIDI tick），音乐速度由常量决定、不读墙钟。

- 效果：**结构上不可能颤**（步进恒定）；与 §4.7、Microprose 帧制音序器同源。
- 代价：低—中；主要碰 `audio.c` 的事件派发循环。
- 致命局限：音乐速度**绑定主循环 pass 率**（NP2kai ~20.5Hz，真机 ~60Hz）⇒ 模拟器与真机
  **速度不一致**，且 pass 率有波动时仍不匀。仅适合「对绝对速度不敏感」的场合，**本项目不推荐**。

---

## 7. 方案对比矩阵

| 方案 | 治「颤」 | 治「拖」 | 触及契约 | 代价 | 与原版对齐 | 推荐度 |
|---|---|---|---|---|---|---|
| A 节流让出 | ✗（治标） | △（缓解） | 无 | 极低 | 低 | ★★★（先做） |
| A′ 改时钟源 | — | — | — | — | — | ✗（NP2kai 死路，已排除） |
| B 分片解码 | ✓ | ✓ | 帧泵「每帧一次」 | 中 | 中 | ★★★ |
| C 中断驱动音泵 | ✓✓ | ✗（不直接治拖） | 帧泵+vclock+audio | 高 | **高（=PMD）** | ★★（长期） |
| D 预载隐藏 | ✗ | ✓ | image/cache | 低-中 | 低 | ★★★ |
| E 固定 tick | ✓（限速场景） | ✗ | audio 派发 | 低-中 | 中 | ✗（模拟器/真机速度不一致） |

---

## 8. 对现有测试/文档契约的影响

| 方案 | 触及契约 | 需改测试？ |
|---|---|---|
| A | 无（`audio_tick` 内部不设防） | 否 |
| B | 帧泵「每帧一次 advance / sole writer」 | 是（`test_frame_pump.py`），另立 devdoc |
| C | 帧泵 + `vclock` 所有权 + `audio_tick` 单消费方 | 是，另立 devdoc |
| D | 无（除非改缓存槽数） | 否 |
| E | `audio.c` 事件派发 | 可能，另立 devdoc |

> 任何改动若动了 `hal_wallclock_smooth_advance()` 的调用点，必须同步更新
> `tools/tests/test_frame_pump.py`（`test_smooth_advance_owns_the_step`、
> `test_frame_pump_sequence_is_exact`）与 `test_reveal_final_page.py`
> （`test_smooth_wallclock_bounds_in_hal`），否则即红。

---

## 9. 建议的决策顺序与实机验证方法

### 9.1 顺序

1. **先做方案 A**（最小代价）——按 §八 五禁补齐串口证据；
2. **A + D 组合**（A 缓解卡顿，D 从路径上消除解码停顿）——两者均不碰帧泵契约，
   可一起落地，风险最低、见效最快；
3. **A/D 不足再做 B**（帧分片），**单独 devdoc**，重点标定分片粒度与
   「每帧一次 advance」契约的合规改法（`advance_once()` 幂等化）；
4. **C 作为长期架构目标**另行立项（若未来以原生硬件/高保真为目标，中断驱动是唯一
   能结构性对齐原版的路，且顺带根治时钟量化）；
5. E 不建议。

### 9.2 验证方法（对齐 §八 五禁，禁靠感觉）

- **量化卡顿**（§4.7）：在空闲路径忙循环自增全局计数、`vblank` 归零，串口打印每帧余量；
  对比 A/D 前后最坏帧余量（NP2kai pass 率 ~20.5Hz，需按 guest 侧计数而非 host 时间）。
- **判定颤动**（禁点击计数竞态）：用引擎侧确定性标记做否定/正向断言，比对各解码窗口内
  音频事件的时间戳序列是否连续（`audio_tick` 派发点打串口戳）。
- **时效性**：改引擎后必须 `./makegame.sh build <game> && ./makegame.sh make <game>`，
  防「跑旧引擎 A/B 报 PASS」（§八 五禁之二，两道守卫已落地）。
- **C 的中断**：先用最小探针验证 NP2kai **是否/以何频率**投递 OPNA IRQ 与 GDC vsync IRQ 0x64，
  再谈实现（预期管理：QEMU/DOSBox-X 已模拟，NP2kai 待证）。

---

## 10. 风险与反面清单

- **禁**：把「串口一次观察」当因果（§八 五禁之一）；用点击计数判颤动（竞态）。
- **禁**：只 `build` 不 `make`（实机跑旧引擎、日志一切正常但结论全废）。
- **C 专属**：未正确 ACK 级联 IRQ / EOI ⇒ 音乐卡死（DOSBox-X #342 实证）；
  鼠标 IRQ 优先级高于 FM；DOS/4GW handler 必须锁内存（否则缺页崩溃）。
- **A 专属**：`hal_vblank_wait()` 在 NP2kai 下是 VSYNC 轮询（§2.6），若 pass 率低，
  节流过密会**过减速**——N 需实测，不宜取太小。
- **D 专属**：预取时机/内存压力；预取本身若仍阻塞则无收益。
- **E 专属**：速度绑定 pass 率 ⇒ 模拟器/真机不一致。

---

## 11. 参考

### 本项目
- `devdocs/129-BGM在菜单询问立绘加载期间卡顿与中断根修.md`（帧泵）
- `devdocs/130-BGM颤动根修虚拟时钟改平滑变步进.md`（vclock）
- `devdocs/82`（时钟/帧率实测）、`devdocs/107`（虚拟时钟下沉 HAL）
- `docs/B19-时钟计算经验参考.md`（时钟源决策全谱：PIT/VSYNC/DOS 逐条实测）
- `docs/refdocs/F03_opna_fm_and_bgm_routes.md`（OPNA 寄存器 / Timer A/B / BGM 通路）
- `docs/refdocs/B02_io_ports.md`（PC-98 PIT 8253 端口 0x71/0x75/0x77）
- `tools/tests/test_frame_pump.py`、`tools/tests/test_vclock.py`

### unlove 项目（`~/unlove`）
- `engine_re/notes/day1.md`（PMD/PMDB2、YM2203/2608、EQAP32 = DOS/4GW LE）
- `engine_re/notes/day7_resources.md`（LOVE.EAR / ECG / M86 / M26 / EQA 格式）
- `engine_re/notes/day9_wvideo_analysis.md`（WVIDEO 视频驱动）
- `engine/m86.c`（`M86_Play` 同步忙等重实现）、`engine/main.c`（诊断菜单）
- `devdocs/PROJECT_FINAL_REPORT.md`、`devdocs/VRAM_ISSUE_ANALYSIS.md`

### 网络
- YM2608 手册 §2-8 Timer（ManualMachine / cpcwiki 译本 / retroweb PDF）
- PMD 英文文档 §2.10 Tempo/Timer：`https://pigu-a.github.io/pmddocs/`
- PMD 进阶 `mml-guide.readthedocs.io/pmd/advanced/`（TimerB 公式）
- ValleyBell `pmd_SeqFormat.txt`（`FC`=Tempo 写 Timer-B、`EB`=Rhythm Key On）
- ReC98（PC-98 同人反编译）PMD 常驻驱动 API：`https://rec98.nmlgc.net/blog/2021-05-12`
- QEMU pc98-opna：`https://github.com/awemorris/qemu-pc98/blob/hw/audio/pc98-opna.c`（FM timer→IRQ3、周期 cnt/clock）
- ReactOS `drivers/pc98/video.h` + DOSBox-X `vga_pc98_gdc.cpp`（GDC 0x64 = vsync IRQ）
- DJGPP `faq18_9` + Peter Marinov 中断处理（DOS/4GW 挂中断 API 与锁内存约束）
- DOS/4GW 手册 §5.8 bi-modal interrupt handler
- XtoF《Timing on the PC family under DOS》（Refresh Detect / vertical retrace / CTC）
- expiredpopsicle《DOS Timer Stuff》（PIT 改频 + INT 8 链接模板）
- MIDAS Sound System *Timer screen synchronization*（定时器 + 屏幕同步）
- Scali OpenBlog《Putting the things together》（定时器中断派发 VGM 事件线）
- DCEmulation《Streaming Music Playback CPU Usage》（分片解码把尖峰 60%→25% + 帧余量量化法）
- Defold 论坛《Sound stutter while loading…》（预载隐藏解码）
- DOSBox-X issue #342《Blackbird: FM music interrupt problems》（级联 IRQ ACK 陷阱）
- Wikibooks《NEC PC Programmers Reference — Sound BIOS》（OPN 内置音乐 BIOS 节拍器）
- DefleMask 论坛 PC-98 乐器导出帖（Love Escalator 使用 PMD 的独立佐证）
- Wikipedia《Vertical blank interrupt》（VBI 作时基的通用原理）
