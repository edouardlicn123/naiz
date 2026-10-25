# YM2608(OPNA) Timer A/B 硬件规格与中断通路

> **来源**：
> - Yamaha《YM2608 OPNA Application Manual》英译（`YM2608J Translated.PDF`）§2-2-1 寄存器构成、§2-8 Timer（nemesis.hacking-cult.org 原镜像已 404，本轮取自 csclub.uwaterloo.ca 镜像；另有 ManualMachine 网页版可查）
> - 滴了庵日録《YM2203のレジスタ設定(FM音源編)》（2013-11-11，YM2203 同源 OPN 核的 $27h 位定义日文原典）
> - QEMU pc98-opna（`awemorris/qemu-pc98` 的 `hw/audio/pc98-opna.c`）——PC-98 OPNA 端口映射/LRESET 与「FM timer → IRQ3」事实
> - ymfm（`aaronsgiles/ymfm`，BSD-3-Clause，MAME 所用 FM 核）——寄存器名/位域交叉印证
>
> **许可与转写说明**：硬件寄存器行为是硬件事实，不受版权保护。QEMU 为 GPL-2.0，本文件**只引用「FM timer 触发 PC-98 IRQ3」「端口 0x188/18A/18C/18E」这类事实，不复制任何源码文本**（AGENTS §十：GPL v2 不得复制）。YM2608 手册为 Yamaha 官方文档英译，按寄存器表/公式转写并注明出处。
>
> **配套**：OPNA 逐算子/逐通道/SSG/RHYTHM/ADPCM/OPNA mask 寄存器见 `F03_opna_fm_and_bgm_routes.md`（其未收 Timer 段，本文件补缺）；$110 状态寄存器（IRQ RESET/MASK ZERO/BRDY/EOS/TIMER-B/TIMER-A）见 F03 §3.6。Timer 与 PMD 节拍模型的配合见 `F05_pmd_driver_architecture.md`。**Timer 周期的真实口径（手册 1152 vs 实现 2304，2× 差）见 `F07_opn_timer_clock_reference.md`**——本文件 §1/§3.2 保留手册原值，比较实测时须先乘 2。
>
> **⚠ 阅读顺序**：只要结论看 §1。§3 是公式，§5 是 `$29` IRQ ENABLE（**含一处与 devdoc 131 的差异，见 §5.3 未确认项**）。§8 是未确认项——动手前必读。

---

## 1. 结论先行

| 事实 | 值 | 出处 |
|---|---|---|
| **Timer A 分辨率**（φM=8MHz） | 9µs（`tA = 72·(1024−NA)/φM`，NA:0–1023，范围 9µs–9216µs）⚠ **手册值 = 实现的一半**，实机 18µs / 144 clk | YM2608 手册 §2-8-1；口径订正见 `F07` §2 |
| **Timer B 分辨率**（φM=8MHz） | 144µs（`tB = 1152·(256−NB)/φM`，NB:0–255，范围 144µs–36.86ms）⚠ **同上**，实机 **288µs / 2304 clk** | YM2608 手册 §2-8-2；口径订正见 `F07` §2 |
| Timer A 寄存器 | `$24`（高 8 位）+ `$25`（低 2 位） | 手册寄存器表 |
| Timer B 寄存器 | `$26`（8 位） | 手册寄存器表 |
| Timer 控制寄存器 | `$27`（LOAD/ENABLE/RESET/MODE 位域） | 手册 §2-8-3 |
| IRQ 使能寄存器 | `$29`（D7=SCH，D4–D0=IRQ ENABLE） | 手册 §2-2-1 |
| PC-98 OPNA 端口 | 0x188/0x18A（地址/数据，普通组）、0x18C/0x18E（扩展组） | QEMU `pc98-opna.c` 事实 |
| **FM timer 在 PC-98 的 IRQ** | **IRQ3**（QEMU 默认，prop 默认值 3） | QEMU `pc98-opna.c` 事实 |
| 预分频器 | `$2D/$2E/$2F`（仅写地址即生效；默认 FM 1/6、SSG 1/4；φM max 8MHz） | 手册 §2-2-1 |

**对本项目的意义**（devdoc 131 方案 C 的硬件基础）：OPNA Timer B 是**芯片内定时器**，精度 288µs/步（手册写 144µs，实为 φM/2 口径——见 `F07`）、与 DOS 墙钟/主循环完全解耦——它正是原版 PMD 的节拍源，也是 NP2kai 下唯一「未探索且理论上有精确周期」的时基（B19 已实测淘汰 PIT 读回与 VSYNC 计帧两条，`docs/B19-时钟计算经验参考.md` §2）。

---

## 2. 寄存器总览（$21–$2F 与本主题相关部分）

手册原文（英译转写）：

> The register of the FM sound source part consists of `$21-$B6` …… `$21-$2F`: Function that works together compared with all pronunciation channels.

| 地址 | 名称 | 说明 |
|---|---|---|
| `$24` | TIMER-A | Timer A 高 8 位（P9–P2） |
| `$25` | TIMER-A | Timer A 低 2 位（P1,P0） |
| `$26` | TIMER-B | Timer B 8 位（P7–P0） |
| `$27` | TIMER-A/B Control and 3CH Mode | 启动/停止（LOAD）、标志使能（ENABLE）、标志复位（RESET）、CH3 模式（MODE） |
| `$28` | SLOT / CH | Key-ON/OFF |
| `$29` | SCH / IRQ ENABLE | 发声通道数切换（SCH）+ IRQ 使能位 |
| `$2D/$2E/$2F` | Prescaler | 内部分频选择（仅写地址即设定） |

Timer 溢出时置 status flag（D1=TB、D0=TA，见 F03 §3.6 的 `$110`），并向 CPU 发 IRQ——手册原文：

> Timer information sets up "1" in timer flags (D1, D0) of status 0 and 1 when the time set to the timer passes, and generates IRQ for CPU.

---

## 3. 周期公式与算例

### 3.1 Timer A（10 位，`$24`+`$25`）

```
tA = 72 × (1024 − NA) / φM        NA: 0–1023, φM = 主时钟
```

φM=8MHz 时：**最小 9µs**（NA=1023）、**最大 9216µs**（NA=0）。滴了庵日録对 YM2203 的记述同源（NA = (`@24h[7:0]<<2) + @25h[1:0]`）。⚠ 同 §3.2 的口径问题：实机是 **144 clk/步**（即 18µs–18.4ms），手册系数 72 同样只有一半。

### 3.2 Timer B（8 位，`$26`）

```
tB = 1152 × (256 − NB) / φM        NB: 0–255, φM = 主时钟
```

> **⚠ 口径注记（见 `F07`）**：手册这个式子的系数**只有实现的一半**。OPN 的定时器按 **φM/2** 计数，等价写法是 `tB = 2304 × (256 − NB) / φM`；ymfm（`period × 24 × 6`）、Nuked-OPN2（`subcnt==16` × 144 clk/样点）、NP2kai（`288×(256−NB) µs`）三者一致给出 2304，PMD 的节拍常数（`F05` §2 的 `10800000`）也只在 2304 口径下自洽。
> **下表（及 §3.1 的 9µs/9216µs）是手册原值，成对使用时仍自洽**（周期 = 分辨率 × 步数），但**任何拿它与模拟器/真机实测周期比较的场合，都必须先乘 2**。工程取值见 `F07` §5（86 板 φM=7.9872 MHz、NB=200 ⇒ 16.154 ms = 258 units）。

φM=8MHz 时：**最小 144µs**（NB=255，实机 288µs）——注意 **NB 越小周期越长**。算例（手册口径）：

| NB | 手册周期 | 实机周期（×2，φM=7.9872MHz） | 频率（实机） |
|---|---|---|---|
| 255 | 144µs | 288.5µs | ≈3.47kHz |
| 200 | 144×56 = 8064µs | 16.154ms | ≈61.9Hz |
| 100 | 144×156 = 22.46ms | 45.00ms | ≈22.2Hz |
| 0 | 144×256 = 36.86ms | 73.85ms | ≈13.5Hz |

### 3.3 PMD 的用法（交叉印证）

PMD 用 Timer-B 作全曲节拍器，`#Timer` 直接写 `$26`；mml-guide 给出由 bpm 反推 NB 的公式（范围 1–255）：

```
TimerB = 256 − [10800000 / (bpm × 13 × Zenlen)]
```

（详见 `F05_pmd_driver_architecture.md` §2。）这个常数是**周期口径的独立证据**：把 PMD 的 `48 tick = 二分音符` / `bpm = 2T` 语义与硬件式联立，只有 **2304 clk/步**（φM≈7.9872 MHz）能自洽；若按手册的 1152 反解，会要求 φM ≈ 4 MHz——即「PMD 全线快一倍」，与事实矛盾（完整推导见 `F07` §4）。YM2610 手册（同族 OPN 核，ajworld.net NeoGeoDev）的 `tA`/`tB` 系数同样是 72/1152——**与 YM2608 手册一致，故两者的口径问题也一致**，不能拿来当「手册即真值」的佐证。

---

## 4. `$27` Timer 控制器位域

手册原文（英译转写，位序号自上而下 D7→D0）：

```
D7 D6 : MODE    —— CH3 模式（00 Normality / 01 CSM / 10 Effect sound）
D5    : RESET B —— "1" 复位 Timer B 标志（同时自清 0）
D4    : RESET A —— "1" 复位 Timer A 标志（同时自清 0）
D3    : ENABLE B—— "1" 时 Timer B 溢出置标志并拉低 !IRQ；"0" 则溢出也不变标志
D2    : ENABLE A—— 同上（Timer A）
D1    : LOAD B  —— "1" 启动 / "0" 停止 Timer B
D0    : LOAD A  —— "1" 启动 / "0" 停止 Timer A
```

滴了庵日録（YM2203）给出的对应位定义与此一致：`@27h[0]/[1]` = 启动/停止 A/B；`@27h[2]/[3]` = 溢出置标志（并使能中断）；`@27h[4]/[5]` = 写 1 清标志（读后/写后即自清）。**两源交叉一致，无冲突。**

---

## 5. `$29`：SCH + IRQ ENABLE（本轮补 devdoc 131 的待核实项）

### 5.1 位定义（手册原文转写）

```
D7  : SCH   —— 发声通道数。0 = 3 音（CH1-CH3，OPN 兼容）；1 = 6 音同时。
D6,D5 : 未使用
D4  : EN ZERO
D3  : EN BRDY
D2  : EN EOS
D1  : EN TB    ← Timer B 中断使能
D0  : EN TA    ← Timer A 中断使能
```

手册原文：

> • SCH: …… A set value is "0" in the early after it initial clears. Please make this bit "1" first to use it by six sound pronunciation simultaneously.
> • IRQ ENABLE: The interrupt signal is controlled. When each bit of D4-D0 is "1", the terminal !IRQ is made Low level synchronizing with the generation of corresponding status flag. **The default of D4-D0 is "1".**

### 5.2 devdoc 131 §4.1 的断言核对

| devdoc 131 断言 | 手册核对结果 |
|---|---|
| `$29` D0=EN_TA、D1=EN_TB | ✅ 一致 |
| `$29` 是「最后一块拼图，不写就拿不到 IRQ」 | ⚠ **未获手册支持**：手册称 D4–D0 **默认即为 1**。差异可能来自：特定初始化序列（如某板卡/BIOS 会清零）、或 devdoc 作者把「ENABLE 位（$27 D3/D2）」与「IRQ ENABLE（$29）」混淆。二者是**两级门控**：$27 ENABLE 决定溢出是否置标志，$29 决定标志是否拉低 !IRQ。 |

### 5.3 未确认项（写入 devdoc 131 后续立项的验证清单）

1. **`$29` D4–D0 上电默认值在实机/PC-98 BIOS 初始化后的真实状态**（手册说默认 1，但 PC-98 开机流程可能改写）；
2. **Timer A/B IRQ 在 NP2kai 的投递频率与抖动**（QEMU `pc98-opna.c` 按 `cnt/clock` 模拟，NP2kai 侧未实测，devdoc 131 §9.2 已列为探针前置项）；
3. `$110` IRQ RESET 写 1 清标志后，服务例程内重装载 Timer 的正确次序（手册未给时序图）。

---

## 6. PC-98 侧的端口与 IRQ 通路（事实层）

QEMU `pc98-opna.c`（GPL-2.0，仅列事实不复制代码）：

- OPNA I/O 基址四端口：`0x188`（addr）、`0x18A`（data）、`0x18C`（addr,bank1）、`0x18E`（data,bank1）——按 `(addr - IOBASE) >> 1` 得 0..3，`a & 1` 区分地址/数据写，`(a >> 1) & 1` 选 bank；
- `0x2D–0x2F` 写在 bank0 时置预分频器（与手册 §2-2-1 对应）；
- 文件头注释原文：*"The FM timers raise PC-98 IRQ 3 (INT0)."*；设备属性默认 `isairq = 3`；
- PCM IRQ 与 FM timer IRQ **共用同一 `qemu_irq` 线**（`irq_level || pcm_irq_pending`）——若本项目将来同时用 PCM FIFO 中断， handler 必须分诊（呼应 F02 的 A46A 双用途陷阱）。
- `0xA460` sound ID 端口与本仓 `F02_86pcm_registers.md` 收录一致（bit0 可写锁存、板卡 ID 只读）。

**噪音/磨损注意**：86 板 8MHz φM 由 `$2D`（默认 1/6）分频给 FM/SSG；手册明确「访问所有音源时保持默认」，改预分频会同时改变音高（F03 §陷阱）。

---

## 7. 与现有文档的对照

| 文档 | 覆盖 | 本文件补充 |
|---|---|---|
| `F03_opna_fm_and_bgm_routes.md` | 逐算子/通道/SSG/RHYTHM/ADPCM/mask、$110 status | `$24–$27` Timer、`$29` IRQ ENABLE、预分频 `$2D-$2F` |
| `docs/refdocs/B02_io_ports.md` | PC-98 PIT 8253 端口 0x71/75/77（墙钟侧） | OPNA Timer（芯片内，墙钟之外的另一条时基） |
| `docs/B19-时钟计算经验参考.md` | PIT 读回/VSYNC 计帧实测淘汰 | 未探索的第三条：OPNA Timer A/B |
| `F05_pmd_driver_architecture.md` | PMD 如何用 Timer-B | 本文件是硬件规格侧 |

---

## 8. 未确认项汇总（动手前硬检查）

1. §5.3 三条（`$29` 默认值、NP2kai 投递时序、清标志/重装载次序）；
2. **实机 vs 模拟器的 Timer 周期一致性**：手册公式以 φM=8MHz 为准且**系数只有实现的一半**（见 `F07`）——86 板晶振已取证为 7.9872 MHz（MAME `pc9801_86.cpp:85`），周期推导与 NP2kai 的对照已完成（`F07` §3），但**仍无实机示波器数据**；
3. `$2D-$2F` 预分频若被改写，FM/SSG 全部音高与 Timer 基准同比变化（未测，属高危操作，建议全程保持默认）。

---

## 附：来源清单

| 来源 | URL | 用途 |
|---|---|---|
| YM2608J Translated.PDF（csclub 镜像） | https://csclub.uwaterloo.ca/~pbarfuss/YM2608J_Translated.PDF | 本文件主依据（寄存器表/§2-8/§2-2-1） |
| ManualMachine YM2608 User Manual | https://manualmachine.com/yamaha/ym2608/5410883-user-manual/ | 网页版核对（$29 表） |
| 滴了庵日録 YM2203 寄存器(FM音源編) | https://lipoyang.hatenablog.com/entry/20131112/p1 | $27h 位定义交叉印证 |
| QEMU pc98-opna.c | https://github.com/awemorris/qemu-pc98 | IRQ3/端口映射事实 |
| ymfm | https://github.com/aaronsgiles/ymfm | 寄存器名/位域交叉印证（BSD-3） |
| ajworld.net YM2610 手册 | https://www.ajworld.net/neogeodev/ym2610am2.html | 同族公式佐证（本轮该站 DNS 不可达，内容经搜索快照核对） |
| devdoc 131 §4.1 | `devdocs/131-剩余颤动与立绘加载拖慢分析unlove对照与建议.md` | 本文件的立项由来 |
