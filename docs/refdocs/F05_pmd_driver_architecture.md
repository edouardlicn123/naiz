# PMD 常驻驱动架构与 Timer-B 节拍模型

> **来源**：
> - mml-guide PMD 篇 *Advanced info*（https://mml-guide.readthedocs.io/pmd/advanced/）——`#Timer`/`#Zenlen` 语义与 TimerB 公式、`y<reg>,<val>` 寄存器直写
> - PMD MML 手册英译 *P.M.D. version 4.8 MML Command Manual*（https://pigu-a.github.io/pmddocs/pmdmml.htm，原著 M.Kajihara 1997-04-04，英译 Blaze and Pigu）§2.10 Tempo Setting、§11 Tempo 命令
> - ValleyBell `pmd_SeqFormat.txt`（https://raw.githubusercontent.com/ValleyBell/MidiConverters/master/pmd_SeqFormat.txt，据 PMDWin 0.36 源码整理）——`.M` 二进制序列格式
> - ReC98 博客 2021-05-12（https://rec98.nmlgc.net/blog/2021-05-12）——PMD 常驻驱动 API（`AH=09h`/`AH=22h`）、GAME.BAT 加载顺序、缓冲区大小实证
> - QEMU pc98-opna（awemorris fork）——Timer-B → PC-98 IRQ3 事实（见 `F04` §6）
>
> **许可与转写说明**：不复制任何代码。QEMU/DOSBox-X/ReactOS 为 GPL/LGPL，仅取事实（AGENTS §十）。`.M` 格式字段布局是二进制文件格式事实（不受版权保护），按 ValleyBell 文本转写。PMD 手册为第三方英译文档，按「寄存器/命令语义」转写并注明出处。
>
> **配套**：`F06_pmd_mml_manual_en.md` 是 PMD MML 手册完整英译落盘；Timer A/B 硬件规格见 `F04`，**其周期口径的 2× 订正见 `F07`**（下文 §3 的常数即该文 §4 的独立证据）。本文件回答一个问题：**为什么原版游戏的音乐不颤**——它是 devdoc 131「方案 C（中断驱动音泵）」的蓝本。

---

## 1. PMD 是什么

**PMD（Professional Music Driver）** 是 M.Kajihara（KAJA）开发的 PC 音乐驱动，PC-98/88/VA/X68000/PC 均有版本。工作机制：

1. 作曲者用 **MML**（Music Macro Language）写谱 → `MC.EXE` 编译为 `.M`/`.M2` 二进制序列；
2. **驱动常驻内存**（`PMD.COM`/`PMD86.COM`/`PMDB2.COM`），由 `GAME.BAT` 在游戏启动**前**加载；
3. 游戏程序通过**中断 API**（`AH` 功能号）与常驻驱动通信：播放/停止/查询；
4. 驱动的节拍来自 **YM2608 Timer-B 硬件中断**，与游戏主循环解耦。

ReC98 对 TH04/TH05 的实证：`EQAP32.EXE` 类游戏启动时探测 PMD 是否常驻（字符串 `Startup PMD ...` / `WARNING: Cannot detect PMD` / `FATAL: Cannot detect PMD`），用 `AH=09h` 查询驱动类型（OPN/26K 兼容 vs 其它即 OPNA/86 兼容），用 `AH=22h` 查询缓冲区实际大小。TH02 的 `GAME.BAT` 分配：FM 曲 8KB / 音效 2KB / MMD 12KB——**缓冲区大小是驱动命令行可配的**，游戏侧硬编码读入大小曾经因此溢出（ZUN bug，ReC98 记录）。

## 2. 时序模型：Timer-B 驱动，与主循环解耦

```
主循环（画布/脚本/解码）           ── 任意阻塞都不影响 ──▶
YM2608 Timer-B 溢出 ──▶ PC-98 IRQ3 ──▶ PMD ISR ──▶ 序列前进一拍
```

- `#Timer <n>` / `t`/`T` 命令**直接写 Timer-B 值寄存器 `$26`**（pmdmml §2.10：「If #Timer is used, it will directly set the value of TimerB」）；
- MML 的 `#Tempo` 则是「每分钟重复多少次 48 时钟周期」的语义，驱动内部换算成 TimerB 值（默认 `#Zenlen`=96 时 `t`/`T` 值 ≈ 目标 BPM 的一半）；
- mml-guide 给出精确反推公式：

```text
TimerB = 256 − [10800000 / (bpm × 13 × Zenlen)]
```

  Zenlen 必须能整除（否则 MC.EXE 编译报错），取不同 Zenlen 可改善近似精度。`#Timer` 范围：mml-guide 记 1–255；pmdmml §2.10 记 0–250——**两源数值范围略有差异，属文档层面出入，未确认**。

  **这个常数是 Timer 周期口径的独立证据**（`F07` §4）：PMD 序列以 48 tick = 二分音符推进，`#Tempo T` 与 BPM 的关系为 `bpm = 2T`，由此要求 `tB = 1.25/T`；把它与硬件式联立，只有 **2304 clk/步**（φM=7.9872 MHz）能自洽，若按手册的 1152 反解会要求 φM ≈ 4 MHz——即「PMD 全线快一倍」，与事实矛盾。

## 3. MML 直写寄存器：`y<reg>,<val>`

mml-guide Advanced：

- 几乎全部命令可接受十六进制（`$` 前缀）；
- `y$30,0` 形式**直接写 OPNA 寄存器**——用于驱动不原生支持的技巧；但同时警告：PMD 的其它命令可能覆盖这些直写（需对寄存器图有完整认识，`$30` = 本通道 Operator 1 的 MULTI）。

**对本项目的意义**：这是「PC-98 音乐圈把 OPNA 寄存器知识当作显学」的直接证据；本仓 `F03`/`F04` 的寄存器表正是这类知识的沉淀。`#Timer` 一次直写就是 F04 §3.2 的 `$26`。

## 4. `.M` 序列二进制格式（ValleyBell 整理）

要点（PMD 4.8，据 PMDWin 0.36）：

```text
1 byte       file version（.M/.M2 通常 00，FM Towns 必须 FF）
11×2 bytes   track pointers：0-5 FM1-6 / 6-8 PSG1-3 / 9 OPNA ADPCM B / 10 OPNA Rhythm
2 bytes      Rhythm Subroutine Table
2 bytes      FM instrument pointer（兼作附加文件指针）
x bytes      sequence data
...          rhythm subroutine data、FM instruments（每件 1 byte ID + 19h bytes，
             寄存器序 30 34 38 3C 40 44 … 88 8C B0）、PSG envelopes
Values stored Little Endian; pointers relative to file offset 0001h
```

音符事件形如 `00-7F ll`（高 4 位八度、低 4 位音高，ll = 长度），`note xC/xF` 为特殊记号。**用途**：若将来要在本项目内做 PMD 解析/转 MIDI 的诊断工具，这是字段级依据；当前**不是**本项目格式（本项目 BGM 输入已定 MIDI，见 F03 §1.2）。

## 5. 与其它架构的对照（devdoc 131 §3 的浓缩）

| 维度 | PMD（原版 EQAP32 所用） | unlove 重实现 `M86_Play()` | naiz 现状 |
|---|---|---|---|
| 节拍来源 | **YM2608 Timer-B 硬件中断（IRQ3）** | 主循环忙等延时 | 主循环协作轮询（帧泵，c58/c59） |
| 长解码的影响 | **无**（ISR 独立推进） | 有（同主循环） | 时钟冻结 + 事件停发 |
| 音乐数据 | PMD 编译格式 `.M/.M2` | 寄存器流解读（M86/M26） | MIDI（`AUDIO.DAT`） |

unlove 的 `M86_Play()` 把 M86 当作「OPN 寄存器写序列 + 忙等延时」同步播放——**它复现的恰是我们当前的模型**，反证「不颤」靠中断驱动而非播放器写法。

## 6. 对本项目的行动含义

1. **方案 C（devdoc 131）就是复刻本模型**：初始化 Timer-B（F04 §5 的 `$29`/`$27` 两级门控）→ 挂 IRQ handler → handler 推进 BGM 事件表；
2. **节拍精度**：TimerB 步进 288µs（手册写 144µs，实为 φM/2 口径，见 `F07` §2），远优于当前 vclock 的 0.5ms slew 上限；
3. **音频事件表与画面解耦**后，解码/菜单/存读档都不再牺牲节拍（devdoc 131 §2.4 的「静止→回填」颤动结构性消失）；
4. **风险清单**见 `G09` §3 的级联 IRQ ACK 全记录（PC-98 FM=IRQ12/QEMU 默认 IRQ3、鼠标 IRQ13 更高优先级、EOI/in-service 位）与 `G08` 的 DOS/4GW 挂中断 API。

## 7. 未确认项

1. `#Timer` 数值范围两源不一致（1–255 vs 0–250）；
2. PMD 在不同板（26K vs 86）上的 Timer-B 预设值/预分频交互未实测（F04 §8.3 同款高危）；
3. ReC98 实证基于 TH02–TH05（PMD86 4.8o），Love Escalator 具体用的 PMD 变体/常驻参数未逐字节确认（DefleMask 论坛帖将其归入 PMD 游戏，devdoc 131 §3.2 已列为间接佐证）。

## 附：来源清单

| 来源 | URL | 用途 |
|---|---|---|
| mml-guide PMD Advanced | https://mml-guide.readthedocs.io/pmd/advanced/ | TimerB 公式、`#Timer`/`#Zenlen`、`y` 直写 |
| PMD MML 手册英译（§2.10 等） | https://pigu-a.github.io/pmddocs/pmdmml.htm | `#Tempo`/`#Timer` 语义 |
| ValleyBell pmd_SeqFormat.txt | https://raw.githubusercontent.com/ValleyBell/MidiConverters/master/pmd_SeqFormat.txt | `.M` 二进制格式 |
| ReC98 博客 2021-05-12 | https://rec98.nmlgc.net/blog/2021-05-12 | 常驻驱动 API/加载顺序/缓冲区实证 |
| QEMU pc98-opna.c（事实） | https://github.com/awemorris/qemu-pc98 | Timer→IRQ3 |
| devdoc 131 §3/§4.2 | — | 对照与立项由来 |
