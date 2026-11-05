# OPN Timer A/B 计时口径参考：2304 clk vs 手册 1152（2× 之谜）

> **来源**：
> - Yamaha《YM2608 OPNA Application Manual》英译（`YM2608J Translated.PDF`，csclub.uwaterloo.ca 镜像）§2-2-1 预分频表、§2-8-1 Timer A、§2-8-2 Timer B
> - SMS Power《YM2612 Technical Manual》（Maxim 整理的同名 OPN 核寄存器手册）Register 24H/25H/26H 段
> - GenDev / SpritesMind 论坛 2008-06「New Documentation: an authoritative reference on the YM2612」主题（Nemesis 提问 + Eke 的定论推导）
> - ymfm（`aaronsgiles/ymfm`，BSD-3-Clause，MAME 现用 FM 核）`src/ymfm_fm.ipp` 的 `update_timer()`；Nuked-OPN2（`nukeykt/Nuked-OPN2`，LGPL-2.1）`ym3438.c` 的 `OPN2_DoTimerA/B`
> - NP2kai（`AZO234/NP2kai`，MIT）`sound/opntimer.c`、`sound/opngen.h`、`sound/opna.c`、`sound/fmgen/fmgen_fmtimer.cpp`、`pccore.c`/`pccore.h`、`i386c/ia32/ia32.mcr`；MAME `src/devices/bus/pc98_cbus/pc9801_86.cpp`（86 板晶振）、`pc9801_26.cpp`（26K 对照）
> - BlastEm（`libretro/blastem`，GPL-2.0）`ym2612.c` 的 `ym_run_timers()`；Plutiedev《YM2612 register reference》（按 7.67 MHz 修正的 `18.77µs` / `300.34µs`）
> - MUCOM88（`onitama/mucom88`，PC-8801 驱动汇编 `pc8801src/ver1.2/muc88.asm`）的 `t`（直写 Timer-B 寄存器）语义与社区实测；MAME `src/mame/nec/pc8801.cpp`（PC-8801 的 OPNA 时钟）
> - mml-guide PMD 篇 *Advanced info*（TimerB / Whole Note Length / Tempo 三节）
>
> **许可与转写说明**：本文件**只引用事实与公式，不复制任何源码文本**。Nuked-OPN2 为 LGPL-2.1、BlastEm 为 GPL-2.0、QEMU 为 GPL-2.0（AGENTS §十：GPL v2 不得复制）——下文涉及的实现细节全部改写为「计数器在第几次样点自增」这类行为描述，并给出文件行号供查证，不含代码片段。YM2608/YM2612 手册为 Yamaha 官方文档（前者英译），公式按原文转写。
>
> **配套**：寄存器位域/端口/IRQ 通路见 `F04_opna_timer_a_b_specs.md`；Timer 在 PMD 节拍模型里的角色见 `F05_pmd_driver_architecture.md`。**本文件回答一个问题：一次 Timer-B 步进到底是多少个主时钟？** 手册与四份独立实现给出两个相差 2 倍的答案，本文件给出定论、证据链与工程取值。
>
> **⚠ 阅读顺序**：只有结论看 §1；想知道「手册为什么写成 1152」看 §2；想复核证据看 §3–§4；要改引擎常量看 §5；动手前必读 §6 未确认项。

---

## 1. 结论先行

| 事实 | 值 | 依据 |
|---|---|---|
| **Timer A 每一步的主时钟数** | **144 clocks**（`tA = 144·(1024−NA)/φM`） | ymfm `period × OPERATORS(24) × prescale(6)`；Nuked `cycles==1` 每样点一次；BlastEm 每 144 clk 窗口 +1；Plutiedev 修正值 `18.77µs @7.67 MHz` |
| **Timer B 每一步的主时钟数** | **2304 clocks**（`tB = 2304·(256−NB)/φM`） | 同上，`16 × 24 × 6`；Nuked `subcnt==16`；BlastEm `sub_timer_b += 0x10` 满 16 次；Plutiedev `300.34µs @7.67 MHz` |
| **手册写法（YM2608 §2-8）** | `tA = 72·(1024−NA)/φM`、`tB = 1152·(256−NB)/φM`，标称 9µs / 144µs @φM=8MHz | 手册原文。**数值只有实现的 1/2** |
| **手册写法（YM2612 §24H/26H）** | `tA = 18·(1024−NA) µs`、`tB = 288·(256−NB) µs`（按「8 MHz」撰写） | 换算即 `144`/`2304` 个主时钟 ⇒ **与实现一致**；实际 VCLK=7.67 MHz 时 Plutiedev 修正为 18.77/300.34µs |
| **等价读法** | 手册的 1152 是「**φM/2 时钟**」的个数：`1152/(φM/2) = 2304/φM` | GenDev 定论「OPN divides input clock by 2 for the timers」 |
| **86 板 OPNA 主时钟 φM** | **7.9872 MHz**（MAME `pc9801_86.cpp:85`，`7.987_MHz_XTAL`，注 `// actually YM2608B`） | MAME 硬件描述 |
| **NB=200 的真机周期** | **16.154 ms**（`2304×56/7987200`）⇒ **258.5 units**（1/16 ms） | 上式代入 |
| **NP2kai 的模型周期** | **16.128 ms** ⇒ **258.0 units**（恒为 `288×(256−NB) µs`，与 CPU 模式/倍频无关，见 §3.3） | 源码化简 |
| **两者偏差** | **−0.16%**（NP2kai 相对真机） | — |
| **引擎应取常量** | **258 units**（`core/plat/hal_irq.c` 的 `BGM_TIMER_B_UNITS`） | §5 |
| **旧常量 129 的性质** | 错把手册 1152 当「φM 的个数」，等于把周期取成真值的 **1/2** | §5.1 |
| **真机硬件侧佐证** | 按文档值算 ≈50 Hz、实机侧得到 **~100 Hz**（TmEE 自述，MD 硬件）⇒ 实机周期是 YM2608 手册值的 2 倍 | §2.2 原文 |
| **真机软件侧佐证** | MUCOM88 `t198`（直写 `$26`=198）在 PC-8801（OPNA 同为 7.9872 MHz）实测 ≈ **1/60 s/步**、`C60` 全音符 ≈1 s（♩≈239）⇒ `288.5 µs × 58` | §4.4 |

**一句话**：真机 Timer-B 每步 **2304 个 7.9872 MHz 主时钟**（≈16.15 ms，NB=200），NP2kai 的 16.128 ms 是**忠实建模**；`devdocs/168` 初稿把「16 vs 8 ms」判成模拟器 2× bug、并据此把真机档定为 129 units，**结论方向相反**——错的是 129 这个常量本身。

---

## 2. 手册的 2× 之谜

### 2.1 两份 Yamaha 手册互相矛盾

同一 OPN 核，两份官方手册对同一寄存器给出相差 2 倍的周期：

| 手册 | Timer A（@8MHz） | Timer B（@8MHz） |
|---|---|---|
| YM2608(OPNA) §2-8-1/2-8-2 | `tA = 72·(1024−NA)/φM` ⇒ 最小 9µs | `tB = 1152·(256−NB)/φM` ⇒ 最小 144µs |
| YM2612（SMS Power 转写 24H/25H/26H） | `18 × (1024−NA) µs` ⇒ 最小 18µs | `288 × (256−NB) µs` ⇒ 最小 288µs |

YM2612 的值恰好是 YM2608 的 **2 倍**。两颗芯片的 FM 采样率推导式相同（`φM/24/6`，@8MHz 皆为 55.55 kHz），所以「内核本身不同」解释不了这个差。

**换算成「主时钟个数」才看得清**：YM2612 的 `288µs @8MHz` = **2304** 个时钟，YM2608 的 `144µs` = **1152** 个。因此两份官方手册里**只有 YM2608 的 1152 是实现的 1/2**；YM2612 的简化式恰好等于实现值。Plutiedev 的寄存器参考页把这个数按实际时钟修正为 `300.34µs`（7.67 MHz），并明确写下「Sega 文档是按 8 MHz 写的，而 YM2612 实际接 7.67/7.61 MHz」——修正后仍是 2304 个时钟（§2.2）。

### 2.2 GenDev 的定论：定时器按 φM/2 计数

2008 年 SpritesMind 那轮关于 YM2612 权威文档的讨论，把这件事讨论到了底。原文（转写，仅引述观点，不含代码）：

- **Nemesis（提问者，2008-06）**：Sega 的简化式与 YM2608 手册对不上，「Sega 要么是按 4 MHz 算的，要么定时器的分频不同。很可能 YM2612 的定时器速率只有一半（Timer A 144 个时钟脉冲，Timer B `144×16 = 2304` 个），而他们是按 8 MHz 算的。」
- **Eke（2008-06-10）**：「YM2612 很可能把输入时钟除以 2：`72/(VCLK/2/10^6) = 18.77µs`、`1152/(VCLK/2/10^6) = 300.37µs`。」（VCLK = 7.67 MHz）
- **TmEE（同日，实机）**：「YM2612 很可能把输入时钟除以 2——我算定时器周期时得出了**双倍**的结果，**~100 Hz 而不是 ~50 Hz**。」

即「**手册的系数配 φM/2 的时钟**」与「**实现的计数配 φM**」是同一个物理事实的两种写法：

```
tA = 72 / (φM/2) = 144/φM   （µs，φM 以 MHz 计）
tB = 1152 / (φM/2) = 2304/φM
```

手册里的 1152 本身没有数错——它数的是 **φM/2 时钟**；错的是公式把它标成「φM 的个数」。`144µs` 这个标称分辨率同理：实机是 **288µs**（NB=255、φM=8MHz）。

Plutiedev 的寄存器参考页把同一结论做成了可直接引用的数值表（按 7.67 MHz 修正）：Timer A `($400−TMRA) × 18.77µs`、Timer B `($100−TMRB) × 300.34µs`。反向验算：`18.77µs × 7.67 MHz = 144.0`、`300.34µs × 7.67 MHz = 2303.6` —— **正好 144 / 2304 个主时钟**。TmEE 那条是这组证据里唯一的**实机侧**读数（他自述按文档值算/编程后得到的是 ~100 Hz，而不是文档预期的 ~50 Hz），虽非波形级测量，但方向明确。

### 2.3 为什么这条错误读法特别容易传播

- 手册公式**自洽**（代入 NB=255 得 144µs，与自己写的「resolution 144µs」一致），所以只看手册无法发现异常；
- PC-98 侧「真机 Timer-B 周期」极少被单独记录，PMD 之类驱动把它藏在节拍公式里（§4）；
- **PC-98 与 PC-8801 的 OPNA 主时钟同为 7.9872 MHz**：86 板见 MAME `pc9801_86.cpp:85`；PC-8801 见 `pc8801.cpp:133`（`MASTER_CLOCK = 31.9488 MHz / 8`）与 `:1586`（OPNA 接 `MASTER_CLOCK * 2`）⇒ `2304 clk = 288.5µs` 这条换算在两台机器上通用，不要以为「288µs」只在标称 8 MHz 下成立；
- 一旦有人用「手册值」当**判据**去比「模拟器实测」，就会把忠实实现判成 2× bug，并顺手把常量改错一半——这正是 `devdocs/168` 初稿踩的坑，也是 AGENTS §十「速率/时序断言必须有独立于被测实现的对照量」那条规则的来源：用假设周期自比，误差必然显示为 0。

---

## 3. 四份独立实现逐行对照

四份互相独立的代码（MAME 系 ymfm、die-level 逆向 Nuked-OPN2、Genesis 模拟器 BlastEm、PC-98 模拟器 NP2kai）在「Timer B = 2304 主时钟/步」上完全一致。BlastEm 与 Nuked 面向 YM2612（同源 OPN 核），ymfm 是 YM2608/2612 共用引擎，NP2kai 面向 YM2608——**这四份里没有一份按 1152 计数**（NP2kai 内另有一个 fmgen 旁路用 1152，但它不驱动 IRQ，见 §6.4）。

### 3.1 ymfm（BSD-3，MAME 现用）

`src/ymfm_fm.ipp:1480` 起，`update_timer()` 先算「寄存器给出的步数」，再乘上时钟换算因子：

| 行 | 内容 | 值（OPN/OPNA，NB=200） |
|---|---|---|
| 1480 | `period = 16 * (256 − timer_b_value)`（Timer A 则是 `1024 − NA`） | `16 × 56 = 896`（Timer B 的样点数） |
| 1486 | `set_timer(tnum, period × OPERATORS × m_clock_prescale)` | `896 × 24 × 6 = 129,024` 主时钟 |

- `OPERATORS = CHANNELS × 4 = 24`（`ymfm_opn.h:116-118`），`DEFAULT_PRESCALE = 6`（`ymfm_opn.h:122`，即 `$2D` 默认 1/6）；
- `24 × 6 = 144` 正好是**每样点的主时钟数**（采样率 = φM/144），于是 Timer B 每步 = `16 样点 × 144 = 2304` 主时钟，Timer A 每步 = `1 × 24 × 6 = 144`；
- NB=200：`129024 / 7987200 = 16.154 ms`（与 §1 真机值一致）；
- 同一份代码对 OPM（YM2151）算出 `32 × 2 = 64`/步，与 OPM 手册的 `64·(1024−NA)` **完全吻合**——说明 ymfm 的通用式没错，是 OPN 手册的系数与实现差 2 倍。

### 3.2 Nuked-OPN2（die 级逆向，最接近硅片行为）

`ym3438.c`：

- `OPN2_Clock()` 每次推进一个算子槽，`chip->cycles` 在 0–23 间回绕（`:1336`，`(cycles + 1) % 24`）⇒ **24 次调用 = 1 个输出样点**；
- 一个样点 = `24 槽 × 6（预分频）= 144` 主时钟（这也是 OPN 系列「采样率 = φM/144」的来源）；
- `OPN2_DoTimerB()`：`chip->cycles == 1` 时 `timer_b_subcnt++`（`:1137-1140`）——即**每样点一次**；
- `timer_b_subcnt == 0x10`（16）时才把 Timer B 计数器 +1（`:1141-1144`）；
- ⇒ 每步 = `16 样点 × 144 clk = 2304` 主时钟。Timer A 则是 `cycles == 1` 直接 +1（`:1097`）⇒ **144** 主时钟/步。

Nuked 的模型不含任何「手册系数」，它是按裸片时序反推的，因此这一条对「2304」的支持力度最大。

### 3.3 NP2kai（本项目的验证 oracle）

`sound/opntimer.c` 的 `set_fmtimerbevent()`：

| 行 | 内容 |
|---|---|
| 59 | `l = 288 × (256 − reg[0x26])`（NB=200 ⇒ `16128`） |
| 60-67 | 8 MHz 模式（`CPUMODE_8MHZ`）乘 `1248/625`，否则乘 `1536/625` |
| 68 | `l *= pccore.multiple` |

事件以**CPU 时钟**计（`pccore.c:326-328`：`realclock = baseclock × multiple`），而 `multiple` 在分子分母中各出现一次 ⇒ 约掉。再把两个 baseclock 代入：

| CPU 模式 | baseclock（`pccore.h:11-12`） | 换算因子 | 因子 ÷ baseclock | NB=200 周期 |
|---|---|---|---|---|
| 8 MHz 模式（`pccore.c:314-315`） | `1996800` | `1248/625` | `1.9968 / 1996800 = 1/1000000` | **16.128 ms** |
| 5 MHz 模式（`pccore.c:307-309`） | `2457600` | `1536/625` | `2.4576 / 2457600 = 1/1000000` | **16.128 ms** |

两个因子除以各自 baseclock **都恰好是 1e-6** ⇒ NP2kai 的周期化简为闭式：

```
tB(NP2kai) = 288 × (256 − NB)  µs      （与 CPU 模式、倍频 multiple 均无关）
```

- NB=200 ⇒ `288 × 56 = 16128 µs` = **16.128 ms**；
- 与真机 `2304 × 56 / 7987200 = 16.154 ms` 只差 **0.16%**（正是 `8.0000 MHz` 与 `7.9872 MHz` 的差）；
- 换句话说：NP2kai 用的是「8 MHz 标称值 + 2304 计数」，真机是「7.9872 MHz + 2304 计数」。**模拟器没有 2× 错误。**

> 附带订正 `devdocs/168` §3.2 的两处估算：baseclock 是 **1996800**（不是 2.0 MHz 整），且 **5 MHz 模式同样是 16.128 ms**（不是 15.85 ms / 254 units）。「宿主周期不是常量、需要分档」的前提不成立。

### 3.4 BlastEm（Genesis 模拟器，GPL-2.0）

`ym2612.c` 用「一个算子槽一次迭代」的调度：`current_op` 在 0–23 间回绕（`ym2612.h:17`，`NUM_OPERATORS = 4×6`），每槽推进 `clock_inc` 个主时钟（`ym2612.c:195`，`clock_inc = clock_div × 6`；Genesis 上 `clock_div = MCLKS_PER_YM`，即每个 YM 时钟对应 7 个 68K 时钟）。`current_op` 归零时（= **144 个 YM 时钟**，代码注释写 `144 cycle period`，`:636`）调一次 `ym_run_timers()`。

| 行 | 行为 | 效果 |
|---|---|---|
| 366-369 | 每次 `ym_run_timers()` 调 `timer_a++` | Timer A = **144 YM clk/步** |
| 406 | `sub_timer_b += 0x10`（4 位子计数器） | 每 16 次调用 = **2304 YM clk** 才轮到 Timer B |
| 392-395 | `!sub_timer_b` 时才 `timer_b++` | Timer B = **2304 YM clk/步** |

与 ymfm/Nuked 的差别只是调度粒度：BlastEm 在「每 144 时钟」的窗口里用 4 位子计数器凑出 16 分频，Nuked 用 16 个样点计数，ymfm 直接把 `16` 乘进周期。**三者是同一个 2304**，而且 BlastEm 是其中唯一把「144」直接写进代码注释的。

### 3.5 四实现汇总

| 实现 | Timer A 步长 | Timer B 步长 | 与 YM2608 手册 72/1152 的关系 |
|---|---|---|---|
| ymfm | 24×6 = 144 | 16×24×6 = 2304 | 2× |
| Nuked-OPN2 | 每样点 +1 = 144 | 16 样点 = 2304 | 2× |
| BlastEm | 每 144 clk 窗口 +1 = 144 | 16 个窗口 = 2304 | 2× |
| NP2kai | `18×(1024−NA)` → 化简为 `144` | `288×(256−NB) µs` → 2304 | 2× |
| **YM2608 手册** | 72 | 1152 | 基准 |
| YM2612 手册（Sega，按 8 MHz） | 144 | 2304 | 1×（与实现一致） |

四份实现彼此无共同祖先（ymfm 为 MAME 系重写、Nuked 为裸片逆向、BlastEm 为 Genesis 模拟器、NP2kai 为 fmgen 旁路的独立事件模型），一致给出 2×；且跨芯片一致（YM2612 侧 BlastEm/Nuked、YM2608 侧 ymfm/NP2kai）。

---

## 4. 真机软件侧反证（PMD / MUCOM88）

前三节都是模拟器/逆向证据，本节是**真机软件侧**的证据：两台 NEC 机器上用了三十年的两个驱动（PC-98 的 PMD、PC-8801 的 MUCOM88）都在代码里写死了只与「2304 clocks」自洽的常数。

### 4.1 公式

mml-guide PMD *Advanced*：

```
TimerB = 256 − ⌊10800000 / (bpm × 13 × Zenlen)⌋
```

（`bpm` = 目标每分钟四分音符数，`Zenlen` = 全音符长度，默认 96；PMD 的 `#Tempo T` 值约为 BPM 的一半，即 `bpm = 2T`。）

### 4.2 语义 → 步长的精确关系

PMD 的序列时钟以 **48 tick = 一个二分音符** 推进（等价 24 tick/四分音符）。设 `T` 为 PMD 的 `#Tempo` 值（每分钟二分音符数），则：

```
一个二分音符 = 60/T 秒 = 48 × tB   ⇒   tB = 1.25 / T   （秒）
```

### 4.3 反解隐含的计数常量

把 `bpm = 2T`、`Zenlen = 96` 代入 PMD 公式：

```
256 − NB = 10800000 / (2T × 13 × 96) = 4326.92 / T
```

而硬件关系是 `tB = C × (256 − NB) / φM`，配合 `tB = 1.25/T`：

```
1.25·φM / C = 4326.92      ⇒   C = 1.25·φM / 4326.92
```

| 若 φM = | 得 C = | 结论 |
|---|---|---|
| **7.9872 MHz（86 板实测晶振）** | **2307** | ✅ 与 2304 相差 0.14%（取整/时序余量） |
| 8.0000 MHz（标称） | 2311 | ✅ 相差 0.3% |
| 若强行用 C = 1152 | 需 φM ≈ **3.99 MHz** | ❌ 86 板没有这个时钟；等于宣称 PMD 全线快一倍 |

而且验证一个具体点：`#Tempo 90`（mml-guide 明示「输出 BPM 为 180」）⇒ `256−NB = 10800000/224640 = 48.07` ⇒ NB=208 ⇒ 真机 `tB = 2304×48/7987200 = 13.85 ms`；180 BPM 的四分音符 = 333.3 ms；`333.3/13.85 = 24.07` ⇒ **恰好 24 tick/四分音符**，与 §4.2 的 48 tick/二分音符自洽。

**结论**：PMD 这个在真机上跑了三十年的驱动，其常数只在 2304 口径下成立。这构成「真机 Timer-B = 2304 主时钟/步」的**间接但极强**的证据。

### 4.4 MUCOM88（PC-8801 驱动，直写 Timer-B 寄存器）

MUCOM88 汇编源（`pc8801src/ver1.2/`）有两条与节拍相关的命令：

| 行 | 内容 |
|---|---|
| `msub.asm:1126` | 命令表项 `DB 't' ; TEMPO (DIRECT CLOCK)` |
| `muc88.asm:1707-1726` | `TIMERB`/`TIMEB2`：把参数**原样写入 `$26`**（`LD A,0FAH` → 地址 `$26`，`LD A,E` → 数据口） |
| `muc88.asm:1727+` | `SETTMP`（大写 `T`，按 BPM 计算）：先按 `CLOCK`（`muc88.asm:3019-3020`，默认 **128**）线性化，结果同样走 `TIMEB2` |

即小写 `t` 的数值就是 `$26` 寄存器的值：`t198` ⇒ NB=198 ⇒ `256−198 = 58` 步。社区实测（Estuary::Blog，2025-01-27）：「テンポ t198 だと1クロックがだいたい 1/60」——58 步 ≈ 1/60 s ⇒ 每步 ≈ **287.4µs**。

同一段落还给出可交叉验算的第二读数：`t198` 下 `C60`（全音符 = 60 clock）≈1 秒，且「厳密には♩=240にはならずに239ちょいくらい」（严格说四分音符不是 240 而是 239 出头）。两条读数（`1/60 s` 与 `♩≈239`）相互独立。

PC-8801 的 OPNA 主时钟由 MAME 取证（`src/mame/nec/pc8801.cpp:133`、`:1586`）：`MASTER_CLOCK = 31.9488 MHz / 8`，OPNA 接 `MASTER_CLOCK × 2` ⇒ **7.9872 MHz**（与 86 板相同）。于是 `t198` 的两种口径给出：

| 口径 | 每步 | 一个 clock（58 步） | `C60` 全音符 | ♩ BPM | 与实测 |
|---|---|---|---|---|---|
| **2304 clk** | **288.46µs** | **16.731 ms** | **1.0038 s** | **239.1** | ✅ 「1/60」与「♩≈239」同时成立 |
| 1152 clk | 144.23µs | 8.365 ms | 0.5019 s | 478.2 | ❌ 两项都差一倍 |

**结论**：同一颗 OPNA、同一时钟，只有 2304 口径能同时满足「1/60 s/clock」与「`C60`≈1 s（♩≈239）」两条实测。这是 PC-8801 生态的独立佐证，与 PC-98 的 PMD 常数（§4.1–§4.3）互不依赖。

> **证据强度**：`t` 直写 `$26` 由源码确证；「1/60 s」与「♩≈239」是社区博客的实测描述而非厂商文档，故仍列为**辅助证据**——但这两条读数相互独立（绝对时长 / 乐谱换算）且只有 2304 口径能同时满足，交叉力度不弱。大写 `T` 的线性化常数（`346/100` 量级）在同一口径下量级相容，但其音乐语义（一拍几 tick）本轮未完全确证，不作独立判据。

---

## 5. 工程取值：258 units

### 5.1 129 是怎么来的，错在哪

`core/plat/hal_irq.c:61-66` 的注释与常量：

```
tB = 1152 × (256 − NB) / 8e6 = 8.064 ms   →  8.064 × 16 = 129 units（"0.02% short"）
```

两处问题：

1. **计数取的是手册值 1152，而不是实现的 2304** ⇒ 周期只有真值的一半；
2. **「0.02% short」的对照量是被测实现自己**（129 units ↔ 8.0625 ms ↔ 8.064 ms），所以误差看起来完美——这正是 AGENTS §十 那条「速率断言必须有独立对照量」的教科书案例。实机 `v/w = 49.8%`（`devdocs/168` §3.1 的 Δv=54785 / Δw=110000）才是真相。

### 5.2 取值表

| 取值 | 每 tick | 用于 NP2kai（16.128 ms） | 用于真机（16.154 ms） |
|---|---|---|---|
| **129（现状）** | 8.0625 ms | **−50.02%**（半速） | **−50.09%** |
| **258（建议）** | 16.1250 ms | −0.019% | **−0.18%** |
| 259 | 16.1875 ms | +0.37% | +0.21% |

- 取 **258**：真机偏差 −0.18%（BGM 慢 0.18%，约 3 音分，听不出）、NP2kai 偏差 −0.02%（几乎为零）；
- 取 259 会把误差推到 0.2–0.4%，**没有收益**；要更准需要小数累加器（真值 258.46 / 258.05 都不是整数），代价远高于 0.2% 的节拍误差——BGM 是「tick 调度」不是「积分时基」，0.2% 只影响速度、不累积漂移；
- **不需要编译期分档**（`devdocs/168` §5.1 原方案作废）：两个宿主的真实值相差 0.16%，一个常量覆盖。

### 5.3 `v/w` 判据（保留）

修正常量后，预期 `[ISR]` 行出现：

```
Δticks ≈ 6795, Δv ≈ 6795 × 258 / 16 ≈ 109,569 ms, Δw = 110,000 ms  ⇒  v/w ≈ 99.6%
```

- 判据仍是 **`v/w` ∈ 1.0 ±2%**（现状 49.8%）；
- 注意 `w` 的粒度是 **1 秒**（`hal_wallclock_ms()` 在 NP2kai 上取自 DOS `INT 21h AH=2Ch`），短窗口内误差界约 ±1%，故**不要**用 141 tick 之类的小窗口做判定（`devdocs/168` §2.2 的教训）。

### 5.4 落地清单（本轮只记文档，代码在下一轮）

| 位置 | 现状 | 应为 |
|---|---|---|
| `core/plat/hal_irq.c:66` | `#define BGM_TIMER_B_UNITS 129` | `258` |
| 同文件 `:47-52`、`:61-65` 注释 | 写「144us/step、1152、8.064 ms」 | 改「2304 clk/step @7.9872 MHz ⇒ 16.154 ms；NP2kai 16.128 ms（−0.16%）」，并注明「手册 1152 是 φM/2 口径，见 `docs/refdocs/F07`」 |
| `[ISR]` 启动日志 | `Timer-B installed (NB=200, ~124Hz, …)` | `~61.9Hz`（约 1/16.15 ms） |
| `devdocs/168` | 根因=模拟器 2×、分档 129/258 | 已就地订正（§三 / §5.1） |

---

## 6. 未确认项

1. **无实机示波器/逻辑分析仪数据**：本文件的真机值由「四份实现 + PMD/MUCOM88 常数 + 手册矛盾 + TmEE 的实机侧读数（§2.2）」交叉推出，缺一条直接时序测量（TmEE 是听感/计数级证据，不是波形级）。若日后上真机，判据仍是 `[ISR]` 的 `v/w ≈ 1.0`（±2% 内即认为 258 正确）。
2. **`$2D–$2F` 预分频是否作用于定时器**：ymfm 把 `m_clock_prescale` 乘进 Timer 周期（§3.1），而 YM2608 手册把 `$2D–$2F` 描述为 FM/SSG 分频（§2-2-1），两者未完全对齐。本项目全程保持默认（FM 1/6、SSG 1/4），故不影响 2304 的取值；若将来改预分频，需重新确认。
3. **26K 板（YM2203）的 φM**：MAME `pc9801_26.cpp:53` 为 `15.9744 MHz / 4` 且注释 `divider not verified`。本项目只面向 86 板，未取证；若支持 26K 需重新推导（`tB = 2304×N/φM` 的 φM 不同）。
4. **NP2kai 内的 fmgen 旁路实现的是 1152 口径，但不参与计时**：`OPNA_CLOCK = 3993600`（`sound/opngen.h:13`，即 φM/2），`sound/opna.c:123` 给 fmgen 传 `OPNA_CLOCK*2`（7.9872 MHz）；`fmgen_fmtimer.cpp:137` 的 `timer_step = 1e6·65536/clock` 配 `:52` 的 `timerb = (256−data)·timer_step`、`:80` 的每 µs 减 `<<12`（4096），化简即 `16·(256−NB)·1e6/(φM/72) = 1152·(256−NB)/φM` ⇒ NB=200 为 **8.08 ms**。**但 fmgen 的 `Intr(bool)` 是空虚函数**（`fmgen_opna.h:197/322/490`，NP2kai 未覆写），定时器状态与 IRQ 一律由 `sound/opntimer.c` 的事件模型给出（§3.3，2304 口径）；fmgen 只负责出声。因此看到「同一模拟器内存在两套口径」时，**判定以 IRQ 路径为准**，不要拿 fmgen 的 `fmtimer.cpp` 反推本文件结论。
5. **手册为何写成 2× 小的数值**：可以确认「手册数值 = 实现的一半」这一事实与「按 φM/2 计数」的等价性，但 Yamaha 内部是笔误还是按「定时器时钟」列的公式，无权威说明。

---

## 7. 来源清单

| 来源 | URL | 用途 / 许可 |
|---|---|---|
| YM2608J Translated.PDF | https://csclub.uwaterloo.ca/~pbarfuss/YM2608J_Translated.PDF | §2-8 公式原文（`72`/`1152`、`9µs`/`144µs`）；Yamaha 官方文档英译 |
| SMS Power YM2612 Technical Manual | https://www.smspower.org/maxim/Documents/YM2612 | 24H/25H = `18×(1024−NA) µs`、26H = `288×(256−NB) µs`、`0.288 ms / 73.44 ms` 边界 |
| GenDev / SpritesMind 2008 主题 | http://gendev.spritesmind.net/forum/viewtopic.php?t=386&start=15 | 「OPN 定时器把输入时钟 ÷2」的定论推导（Nemesis 提出 144/2304、Eke 给出 18.77/300.37µs、TmEE 实机 ~100Hz vs ~50Hz） |
| ymfm | https://github.com/aaronsgiles/ymfm （`src/ymfm_fm.ipp:1480,1486`、`src/ymfm_opn.h:116-122`） | `period × OPERATORS × PRESCALE`；BSD-3-Clause，仅引用事实 |
| Nuked-OPN2 | https://github.com/nukeykt/Nuked-OPN2 （`ym3438.c:1097,1137-1145,1336`） | `subcnt==0x10` × 144 clk/样点；LGPL-2.1，仅引用行为描述 |
| BlastEm | https://github.com/libretro/blastem （`ym2612.c:195,366-406,636`、`ym2612.h:17`） | 每 144 clk 窗口跑一次定时器；`sub_timer_b += 0x10` 满 16 次；GPL-2.0，仅引用行为描述 |
| Plutiedev YM2612 register reference | https://plutiedev.com/ym2612-registers | 修正值 `($400−TMRA)×18.77µs` / `($100−TMRB)×300.34µs`；注明 Sega 按 8 MHz 写、实机 7.67/7.61 MHz |
| NP2kai | https://github.com/AZO234/NP2kai （`sound/opntimer.c:59-68`、`pccore.c:307-328`、`pccore.h:11-12`、`i386c/ia32/ia32.mcr:68`） | 事件周期化简；MIT |
| NP2kai fmgen 旁路 | 同仓库 `sound/fmgen/fmgen_fmtimer.cpp:52,80,137`、`sound/opngen.h:13`、`sound/opna.c:123`、`sound/fmgen/fmgen_opna.h:197` | 1152 口径 + `Intr()` 空实现（§6.4） |
| MAME pc9801_86 | https://github.com/mamedev/mame/blob/master/src/devices/bus/pc98_cbus/pc9801_86.cpp （`:85`） | 86 板 OPNA 晶振 7.9872 MHz |
| MAME pc9801_26 | 同仓库 `pc9801_26.cpp:53` | 26K 板对照（`15.9744/4`，divider 未验证） |
| MAME pc8801 | 同仓库 `src/mame/nec/pc8801.cpp:133,1586` | PC-8801 的 OPNA 时钟 = `31.9488 MHz / 8 × 2` = 7.9872 MHz |
| MUCOM88 | https://github.com/onitama/mucom88 （`pc8801src/ver1.2/muc88.asm:1707-1726,1727+,3019-3020`、`msub.asm:1126`） | `t` 直写 `$26`；`T` 线性化后同路径 |
| Estuary::Blog「MUCOM88のソフトウェアLFO」 | https://est.ceres.ne.jp/2025/01/27/mucom88-software-lfo/ | `t198` ≈ 1/60 s 的社区实测描述（辅助证据，§4.4） |
| mml-guide PMD Advanced | https://mml-guide.readthedocs.io/pmd/advanced/ | TimerB 公式、`48 tick` 语义、`#Tempo 90 → 180 BPM` |
| 本仓实机数据 | `devdocs/168` §3.1（`Δticks 6795 / Δv 54785 / Δw 110000`） | ISR 构建实测速率 49.8% |
