# 165 — 方案 A 中断驱动音泵实机落地：ISR 安全审计与定点硬件时基

> **状态**：实施完成（2026-10-21）——实机验证中断链与定点时基正确、引擎不卡死；剩用户听感收口
> **承接**：`devdocs/164`（方案 A 立项 + 阶段 0 探针 + 阶段 1 ISR 骨架）
> **版本**：0.3.052 → 0.3.053（预期）
> **前提**：c80 遗留的两个疑点（`DL=0x10`、IRQ12 归属）已在 `164 §4.4` 闭合；本文件是**阶段 1 的实机启用调试收口**。

> ## ⚠ ERRATA（`0.3.053` 追加，devdoc 168）
>
> **§四「定点硬件时基」的周期取值与随后的「相位精确」验证结论在 NP2kai 上是错的**，正文以下按存档规则原样保留（其中 §四 B1 段的 `129 units` 推导与 §六 实机验证表的「相位精确」两行已被本块推翻）。
>
> - **被推翻的结论**：①「Timer-B 周期（`F04 §2`，φM=8MHz）：`tB = 1152*(256-NB)/φM`；`NB=200` ⇒ 8.064ms ⇒ 每 tick 步进 **129 units**，累计误差 <0.02%」；②「`[ISR] ticks` 2454→3439 单调递增，`v` 每 ~141 tick 步 ≈1136ms（=141×8.064ms，**相位精确**）」。
> - **错在哪**：① 的 129 units 是**真机 86 板 OPNA**（φM=8 MHz）的值，不是本项目实机 oracle（NP2kai）的值——NP2kai `sound/opntimer.c:59-68` `set_fmtimerbevent()` 按 `288*(256-NB)*(1248/625)` 周期计、`pccore.baseclock = 2.0 MHz`（`pccore.c:307-315`），`multiple` 与 `realclock` 约掉后 NB=200 的实际周期是 **16.102 ms**，恰为真机的 **2 倍**；② 则是**自证**：用「假设周期 8.064 ms × 141 tick」去验证「按该假设推进的实现」，必然「精确」——同一行日志里的 `w=`（真实墙钟）才是独立对照量，却从未被用来比。
> - **正确结论**：在 NP2kai 上每 tick 应推进 **258 units**（16.125 ms）；实测 `logs/serial_demo-a2.log` 首末采样 Δticks=6795 / Δw=110000 ms ⇒ **16.188 ms/tick**，与模型 16.102 ms 差 -0.54%（墙钟 1 秒粒度，窗口误差 ±0.9%）⇒ 原实现的虚拟时钟速率为真实时间的 **49.8%**，ISR 构建下 BGM 半速、SE/voice 欠喂断续、打字机与动画半速。
> - **修复与后果**：Timer-B 周期常量须按宿主分档（NP2kai 258 / 真机 129），并把 PCM 投料的时间源与虚拟时钟解耦；方案、判据（`[ISR]` 行 `v/w ≈ 1.0`）与实施顺序见 **`devdocs/168-TimerB实际周期定论与虚拟时钟速率修正.md`**；本轮（0.3.053 批次）**只订正文档，未改代码**，代码缺陷见 `devdocs/168` §五。

> ## ⚠ ERRATA 追加（2026-10-24，纯文档，devdoc 168 / refdoc F07）
>
> **上一块 ERRATA 自身也有两处错**：「NP2kai 的 16.102 ms 恰为真机的 2 倍」与「常量按宿主分档（NP2kai 258 / 真机 129）」。以本追加为准：
>
> - 真机 Timer-B 每步是 **2304 个主时钟**——手册 `tB = 1152·(256−NB)/φM` 里的 1152 配的是 **φM/2** 时钟（YM2612 手册同核写 `288×(256−NB) µs`，恰为 2 倍）。86 板 φM=**7.9872 MHz**（MAME `pc9801_86.cpp:85`）⇒ NB=200 为 **16.154 ms = 258.5 units**。
> - NP2kai 化简后恒为 `288×(256−NB) µs` = **16.128 ms（258 units）**：两档 baseclock（`1996800`/`2457600`）配 `1248/625`、`1536/625` 后，因子除以 baseclock 都恰好是 1e-6 ⇒ **与 CPU 模式、倍频无关**；与真机只差 **−0.16%**（标称 8 MHz vs 实测晶振），是**忠实建模**。
> - ⇒ 正确修复是**单一常量 258**（不分档）；本文 §四 的 `129 units` 推导只有真值一半，是上述全部半速现象的唯一来源。
> - 证据链（YM2612 手册 `288µs` / GenDev「定时器按 φM/2 计数」定论 / ymfm·Nuked-OPN2·NP2kai 三实现 / PMD `10800000` 节拍常数）：**`docs/refdocs/F07_opn_timer_clock_reference.md`**；订正后的完整记录与验证判据：`devdocs/168` 文首「结论订正」表。

---

## 一 症状与起点

`devdocs/164` 阶段 1 的 ISR 骨架落地后，用 `NAIZ_BGM_IRQ=1` 构建实机运行，**引擎静默卡死**（串口日志停在 `BGM IRQ: unmask` 后，无 `Timer-B installed`、无 `bootmenu`）。裸 ISR（只清标志 + EOI，无 `audio_tick()`）则**不卡死但 ISR 从不被调用**。

用户拍板「深挖 NP2kai 为何不触发」后，本文件记录两条定论的取得过程：① **Timer-B 中断链路的唯一根因（`$27` 标志清除写入内容）**；② **ISR 上下文不可调用 `audio_tick()` 的架构级原因（四类不安全构造）**。

---

## 二 定论一：Timer-B 溢出 IRQ 永不送达 —— `$27` 标志清除写入必须保留 bit1 + bit3

### 2.1 病灶表现

裸 ISR 版实机读数：`isr_count` 从 1 → **永不增长**（1s 轮询内只触发一次，此后无任何 IRQ）。而 gdb 反证（`164` 会话）：

- `HIT opna_settimer cData=0xa` ⇒ 我们的 `$27=0x0A` 写入**到达**模拟器；
- `HIT fmport_b` ×12 ⇒ Timer-B 事件**确实在跑并溢出**；
- `HIT pic_setirq irq=0xc`（IRQ12）×2 ⇒ **Timer-B 确实抬升过 IRQ12**；
- `NEVENT_RESET FMTIMERB(6)` **持续数百次**，全部来自 `nevent_set`（即 `fmport_b` 的 `set_fmtimerbevent` 正常重排）——**Timer-B 事件本身一直在跑**。

关键矛盾：事件在跑、`pic_setirq` 也调过，但 ISR 只进一次。

### 2.2 根因（NP2kai 源码）

`bgm_irq_handler` 清标志的写入是：
```
outb(FM_REG_ADDR, FM_TIMER_CTRL);   // $27
outb(FM_REG_DATA, 0x20);            // RESET_B（旧：仅 bit5）
```
两个 NP2kai 门控同时被这个值打破：

1. **`sound/opntimer.c::opna_settimer`**：`$27` 写入时**bit1 清零**（`cData & 0x02 == 0`）会走 `else nevent_reset(NEVENT_FMTIMERB)` —— 把 **Timer-B 事件整个停掉**。
2. **`sound/opntimer.c::fmport_b`**：溢出抬 IRQ 的门控是 `if ((reg[0x27] & 0x08) && !(status & 0x02))`。`$27` 写 `0x20` 令 **bit3（ENABLE B）清零** ⇒ 此后即使事件重排溢出，**也不再置 status bit1、不再 `pic_setirq`**。

即：清标志的写入**必须同时保留 bit1（LOAD B）与 bit3（ENABLE B）**。

### 2.3 修复

handler 的确认写入改为 **`RESET_B | ENABLE_B | LOAD_B = 0x20 | 0x08 | 0x02 = 0x2A`**：
```c
outb(FM_REG_DATA,
     (unsigned char)(FM_CTRL_RESET_B | FM_CTRL_ENABLE_B | FM_CTRL_LOAD_B));
```
这与真实驱动确认定时器的方式一致（`$27` 单次写入里清标志 + 保活计数）。

### 2.4 验证

裸 ISR 版实机（`logs/serial_demo-a2.log`）：
- 修复前：`isr_count=1`（并永不增长）；
- 修复后：`isr_count` 从 12 起**持续递增至 3600+**，贯穿整个运行；
- 主循环同时正常（`[MOUSE] g=…` 轮询 1597 次，未被饿死）。

⇒ **Timer-B → IRQ12 → `_dos_setvect`(INT 14h) → handler 链路完全打通。**

---

## 三 定论二：ISR 上下文不可调用 `audio_tick()` —— 四类不安全构造

裸 ISR 通过后，把 handler 还原为 `164 §5.3` 的完整版（`hal_wallclock_smooth_advance()` + `audio_tick()`），实机**立即静默卡死**（停在 `unmask` 后）。逐行审计 ISR 路径上触达的全部调用，定位四类 ISR 不安全构造。

### 3.1 审计范围

handler 体 → `hal_wallclock_smooth_advance()`（`hal_pc98.c:124`）→ `audio_tick()`（`audio.c:601`）→ 清标志 → 双 EOI。

### 3.2 已确认 ISR 安全

| 调用链 | 依据 |
|---|---|
| `hal_pcm_tick()` | `hal_audio.c:166-197` 全为 `inb/outb` + 结构体字段 |
| `hal_fm_write_reg()` | `hal_audio.c:287-302` 纯 `outb`；`hal_logf` 在 `FM_TRACE_ENABLED=0` 门外 |
| `fmseq_pump` / `dispatch` / `fmseq_stop` / `fmseq_finished` / `fmseq_fm_voices` | `fmseq.c` 无 `int386/malloc/free/fopen/hal_logf` |
| `bgm_rewind_phase` / `fmseq_loop_start` | 纯算术（一次除法、无循环） |
| ISR 尾部 `outb($27)` + 双 EOI | 纯端口 I/O |

### 3.3 四类不安全构造

#### B1 `hal_wallclock_ms()` —— DOS 反射调用（**实测死锁**）
- 位置：`hal_pc98.c:87-117`，第 96 行 `int386(0x21, …)`（DOS 取时间 AH=2Ch）。
- 触达路径：`hal_wallclock_smooth_advance()`（`hal_pc98.c:126`）**与** `audio_tick()` 的 `AUDIO_PUMP_TRACE` 块（`audio.c:617`，**默认 `AUDIO_PUMP_TRACE=1`**，`audio.c:106`）。
- 判定：**DPMI 反射的 DOS 调用在硬件 ISR 内不可重入 → 死锁**。这是完整 handler 卡死的根因（非推测：裸 ISR 无此调用、稳定跑）。

#### B2 x87/FPU + `pow()` —— 浮点运算
- 位置：`fmopn.c:36` `pow(2.0, …)`（`fmopn_note_freq`）；`fmopn.c:43-110`、`fmseq.c:71-83/294-303` 的 `double` 运算。
- 触达路径：任一 note-on（`dispatch` → `fm_note_on`/`ssg_note_on` → `fmopn_note_ratio`/`fmopn_bend_ratio`）。
- 判定：Watcom `__interrupt`（devdoc `164 §三`：INTPACK 偏 16-bit 语义）**不保存 x87 栈**。主循环若正做 FP，ISR 的 `pow`/`double` 会**冲掉挂起的 FP 栈**；且 `pow` 是 libm 调用（可能不可重入），~124Hz 也过重。

#### B3 `hal_logf` / 串口输出 —— 不可重入的阻塞式 I/O
- 位置：`hal_pc98.c:321`（`vsnprintf` + 串口轮询）。
- 触达路径（ISR 内）：`audio_tick()` 的 `AUDIO_PUMP_TRACE` 块（`audio.c:623`，默认开）、FM 回绕分支 `FM loop: N voices…`（`audio.c:654`）。
- 判定：主循环若正写串口时 ISR 并发写 → 输出交错/卡死。

#### B4 `free()` —— 堆操作
- 位置：`audio.c:634-637`：`if (g_pcm_buf && !hal_pcm_active()) { free(g_pcm_buf); … }`。
- 触达路径：每次 `audio_tick()`（PCM 播完）。
- 判定：堆管理器不可重入；主循环若正 `malloc/free` 时 ISR 并发 `free` → 堆损坏。

### 3.4 未覆盖项（记录）

- MIDI 后端路径（`hal_midi_out`）：本环境无 MPU-401，ISR 实际走 FM 分支；MIDI 分支的 ISR 化暂不覆盖。
- `fmseq.c` sink 恒为 `fm_sink_write` → `hal_fm_write_reg`（`audio.c:157/565`）。

---

## 四 设计裁决：定点硬件时基（方案 B）

### 4.1 为何不是「主循环缓存墙钟」

`164 §5.3` 的前提「handler 只做时钟读 + outb」已证伪——**时钟读本身跨进实模式（B1）**。两种补救方向：

- **主循环发布墙钟 + ISR 读缓存**：ISR 读到的是停顿前的陈旧值，**恰好丢掉中断驱动要解决的问题**（停顿期 BGM 该继续走）——是「更精致的错误」。
- **定点硬件时基（采纳）**：ISR **不做任何 DOS/FP/日志/堆调用**，每次 Timer-B 溢出按**常量步**推进虚拟时钟，再泵音频。这正是 `F05` 记载的原版 PMD 模型——**定时器本身就是时基**，与主循环解耦，天然免疫停顿。

### 4.2 定点步长

Timer-B 周期（`F04 §2`，phiM=8MHz）：`tB = 1152*(256-NB)/phiM`；`NB=200` ⇒ `1152*56/8e6 = 8.064ms`。虚拟时钟单位 `VCLOCK_UNITS_PER_MS=16` ⇒ **每 tick 步进 `8.064 * 16 = 129.02 → 129 units`**（取整 129 ≈ 8.0625ms，累计误差 <0.02%，可忽略）。

### 4.3 改造集（已实施）

1. **B1**：`vclock.{c,h}` 新增 `vclock_advance_fixed(VClock *, unsigned long delta_units)`——纯算术、不做平台测量、不复用 `vclock_advance()` 的窗口/平滑逻辑（那套是为不可靠 DOS 秒设计的，硬件时基不需要），也不动 `step/target/passes/accum/calibrated`。参数为 **1/16 ms 单位**（`129` = 8.064ms，保住亚毫秒相位）。ISR 经 `hal_wallclock_fixed_advance()`（`hal_pc98.c`）调它。
2. **B2**：`fmopn.c` 的 `pow()`/`double` 全部去 FP——
   - `fmopn_note_ratio()` 改 **128 项 `(block<<10|fnum)` 静态表** `fmopn_note_table`（离线按旧公式生成，A4→5/520、C4→4/618 与 `test_fmopn` anchor 逐字节一致）；删 `fmopn_note_freq`/`fmopn_freq_ratio`/`#include <math.h>`。
   - 新增 **`fmopn_ratio_freq_x256()`**（Hz×256 整数）与内部 `fmopn_freq_ratio_fixed()`；`fmopn_bend_ratio()` 走「解 freq→整数因子 502/4096→重编码」全整数。
   - `fmseq.c::period_of_freq()` 改收 Hz×256 整数（内联 `7987200/4/16` 整数字面量——**不得用 `FMSEQ_CLOCK`/`FMSEQ_SSG_DIV` 宏，它们是 `double` 字面量，会把 x87 拉回 ISR 路径**）；两个 SSG 调用点改用 `fmopn_ratio_freq_x256`；删无用的双精度宏。
   - 公开的 `double fmopn_ratio_freq()`（无任何调用方）**删除**（C13）。
3. **B3/B4**：`audio.c` 拆出 **`audio_tick_isr()`**（ISR 安全核心：`hal_pcm_tick()` + FM/MPU 泵 + 回绕，**无 `hal_logf`、无 `free`、无 `hal_wallclock_ms()`**）；`audio_tick()` 成为帧路径外壳（`[AP]` trace + 调 `audio_tick_isr()` + 释放 PCM 缓冲）。PCM 重绑（`pcm_play`/`pcm_release`）与帧路径释放均套 **`bgm_irq_lock()/unlock()`** 临界区（ISR 的 `hal_pcm_tick` 并发安全）。ISR handler 改为 `hal_wallclock_fixed_advance(129)` + `audio_tick_isr()`。
4. **心跳可观测**：handler 内 `g_isr_ticks++`（volatile），经 `hal_bgm_irq_ticks()` 由**帧路径**每 ~64 帧采样并打 `[ISR] ticks=… v=…`——**handler 自身绝不打日志**（B3）。没有它，「装上了但从不触发」与「正常工作」在串口上无法区分。

### 4.4 双泵防护（沿用 `164 §5.4`）

`engine_frame_pump()`/`frame_decode_pump()` 已实现 `if (!hal_bgm_irq_active())` 跳过时钟与音泵（`frame.c:21/62`），保留。

---

## 五 验证与防复发

| 项 | 手段 | 状态 |
|---|---|---|
| Timer-B IRQ 送达 | 裸 ISR `isr_count` 持续递增（3600+） | ✅ 实机 |
| Timer-B 持续触发（整链） | `[ISR] ticks` 2454→3439 单调递增，`v` 每 ~141 tick 步 ≈1136ms（=141×8.064ms，相位精确） | ✅ 实机 0.3.053 |
| `$27=0x2A` 写入 | `test_frame_pump.py::test_isr_timer_b_reset_keeps_load_and_enable` 守卫三位组合 | ✅ |
| ISR 安全（无 DOS/FP/日志/堆） | `test_isr_sequence_is_bounded_and_eois_both_pics` 否定断言（禁 `hal_wallclock_smooth_advance`/`hal_wallclock_ms`/`audio_tick();`/`hal_logf`/`free(`/`pow(`/`double `） | ✅ |
| 定点时基正确 | `test_vclock.py::test_fixed_advance_uses_the_hardware_delta_only`（100 tick×129 = 806ms，不动测量态） | ✅ |
| 心跳采样 | `test_isr_heartbeat_is_sampled_from_the_frame_path` | ✅ |
| 引擎不卡死 | 实机串口跑满主循环（3836 次鼠标轮询）+ `bootmenu: enter` | ✅ 实机 |
| BGM 不停顿 | 实机听感（CPU 密集操作期） | 待用户 |

## 六 遗留

- 实机最终听感（BGM 在 CPU 密集操作期是否真的不停顿）**待用户验证**——本仓取证已证中断链与定点时基正确、引擎不卡死，但「听感」只能由用户判。
- MIDI 后端路径（`hal_midi_out`）的 ISR 化未覆盖（本环境无 MPU-401，ISR 实际走 FM 分支）。
- 非 NP2kai 真机的 IRQ 线归属仍未知（双线自适应是缓解手段）。
- 方案 B（`devdocs/163` 的 vclock 有界相位追赶）作为回退仍保留。

## 七 教训

1. **`$27` 清标志 ≠ 只写 RESET_B**：NP2kai 模型把 `$27` 的 bit1（LOAD B）/bit3（ENABLE B）当作「事件存活 / 抬 IRQ」的开关，单写 `0x20` 会静默停表且不报错。
2. **ISR 安全是分层硬约束**：`audio_tick()` 在协作路径下完全正确，在 ISR 下**完全不可用**——同一函数在两个上下文里的合法性不同。任何「把主循环逻辑搬进 ISR」的设想都必须先过本文 §3 的四类筛。
3. **规格要随实现订正**：`164 §5.3` 的前提被证伪，按 `AGENTS §十` 订正路径处理（见 §八）。
