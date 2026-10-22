# 168 — Timer-B 实际周期定论与虚拟时钟速率修正

> **状态**：实施中（根因已定论、有实机数据支撑；**代码修复待实施**）  
> **日期**：2026-10-22  
> **承接**：`devdocs/165`（定点硬件时基，**其周期取值已被本文件订正**）、`devdocs/167`（伪阻塞撤回与真根因定位）  
> **版本**：0.3.053 批次（本轮**只订正文档，未改代码，也未 bump 版本号**——版本号随下一次代码改动一并 bump）  
> **结论一句话**：NP2kai 的 OPNA Timer-B 周期是**真机公式值的 2 倍**（16.10 ms vs 8.064 ms），而 `hal_irq.c` 按真机值 129 units/8.0625 ms 推进 ⇒ ISR 构建下虚拟时钟以真实时间 **49.8%** 的速率前进，BGM/动画/打字机全线半速、SE/voice 欠喂断续。

---

## 一、症状

`NAIZ_BGM_IRQ=1` 构建在 NP2kai 上**不卡死、中断链完整**（`[ISR] ticks` 单调递增），但用户侧听感不对：音乐拖沓、发声断续，主观接近「顿挫」。同期协作式构建（默认）则表现为「立绘/场景切换时 BGM 停住」——那是 `devdocs/163` 的 M1 时间债，与本文是两件事。

## 二、判定过程

### 2.1 先推翻一个假阻塞

`devdocs/167` 初稿把「当前阻塞」写成「FM 后端 `malloc(fmseq_size())` 失败 ⇒ `g_fm_ok=0` ⇒ `hal_bgm_irq_init()` 被跳过 ⇒ ISR 未安装」。该结论有**两条独立反证**：

1. **日志时效性**：初稿引用的 `logs/serial_demo-a2_trace.log` mtime 为 **2026-09-29 11:51**，内容是 `AUD WARN: no MPU-401 (BGM disabled, PCM unchanged)`——早于 FM 后端存在的时期，全文件不含 `BGM IRQ` / `[ISR]` / `OPNA OK`。它证明不了 10 月构建的任何行为。
2. **逻辑互斥**：`hal_bgm_irq_init()` 只在 `g_fm_ok` 为真时被调用，而 `g_fm_ok = 0` 正是 FM 分配失败的直接后果 ⇒ 同一启动**不可能**同时打印 `BGM IRQ install failed` 与 `AUD WARN: no memory for FM backend`。

真实的 ISR 构建抓取是 `logs/serial_demo-a2.log`（2026-10-22 17:43），其内容为：`AUD OPNA OK` → `FM: 15 patch families ready` → `BGM IRQ: probing INT 14h (IRQ12 (slave))` → `0204 -> 800050:0080` → `_dos_setvect(INT 14h) handler=46a5fd` → `programming Timer-B` → `unmask IRQ12 (slave) (imr 51 -> 41)` → `Timer-B installed (NB=200, ~124Hz, IRQ12 (slave))`，随后 `[ISR] ticks` 204→6999 单调递增。**中断链完全打通，FM 分配成功**。

### 2.2 真正的线索藏在 `w=` 里

`devdocs/167` §三.3 给 `[ISR]` 行加了 `w=`（真实墙钟），本意就是「对比 `v` 与 `w` 判断 ISR 是否跟上真实时间」——但没人做这个对比，反而用「141 tick × 8.064 ms = 1136 ms」与**假设周期**自比，得出「相位精确」。**速率断言不可自证**：用假设周期验证按假设周期推进的实现，必然「精确」。

把首末两点拿来做这次对比，结论立刻显形。

## 三、根因一：Timer-B 实际周期 = 理论值的 2 倍

### 3.1 实测

`logs/serial_demo-a2.log` 的 `[ISR]` 首末采样：

```
[ISR] ticks=204  v=1636  w=0
[ISR] ticks=6999 v=56421 w=110000
```

| 量 | 值 | 推导 |
|---|---|---|
| Δticks | 6795 | 6999 − 204 |
| Δv（虚拟钟） | 54785 ms | 56421 − 1636 |
| Δw（墙钟） | 110000 ms | 110000 − 0 |
| 虚拟步进 | **8.0625 ms/tick** | 54785 / 6795（= 129 units ÷ 16，与 `core/plat/hal_irq.c:66` 的常量一致） |
| 真实步进 | **16.188 ms/tick** | 110000 / 6795 |
| **虚拟钟速率** | **49.8%** | 54785 / 110000 |

### 3.2 机理（NP2kai 源码）

`sound/opntimer.c:49-68` `set_fmtimerbevent()`：

```c
l = 288 * (256 - opna->s.reg[0x26]);   /* :59  NB=200 -> 16128 */
if (pccore.cpumode & CPUMODE_8MHZ)    /* :60 */
    l = (l * 1248) / 625;              /* :62  -> 32204 */
else
    l = (l * 1536) / 625;              /* :66  -> 39628 */
l *= pccore.multiple;                  /* :68 */
```

事件以 **CPU 周期**计，而 `pccore.realclock = pccore.baseclock * pccore.multiple`（`pccore.c:326-328`）⇒ `multiple` 约掉，周期只由 baseclock 决定：

| 宿主 | 周期公式 | NB=200 实际周期 | 折算 units（1/16 ms） |
|---|---|---|---|
| 真机 86 板 OPNA（φM=8 MHz） | `tB = 1152*(256-NB)/φM`（`docs/refdocs/F04_opna_timer_a_b_specs.md` §2） | 8.064 ms | **129** |
| NP2kai 8 MHz 模式（baseclock 2.0 MHz，`pccore.c:314-315`） | `288*(256-NB)*(1248/625)/2e6` | **16.102 ms** | **258** |
| NP2kai 5 MHz 模式（baseclock 2.5 MHz，`pccore.c:307-309`） | `288*(256-NB)*(1536/625)/2.5e6` | 15.851 ms | 254 |

⇒ **NP2kai 的模型 = 真机的 2 倍**：它按 CPU 基础时钟 × 288 步计周期，硬件按 OPNA 8 MHz 主时钟 × 1152 步计。NP2kai 自己能同时模拟两种 CPU 模式（`np2cfg.baseclock` 决定 2.0/2.5 MHz），所以「周期」在这台模拟器上**不是常量**，而 `hal_irq.c` 却把它当常量。

### 3.3 一致性校验

- 实测 16.188 ms vs 8 MHz 模式模型 16.102 ms ⇒ 差 **-0.54%**；墙钟 `w` 只有 1 秒粒度（`w % 1000` 恒为 0），全窗口误差界 ±0.9% ⇒ **相符**。
- 实测 vs 5 MHz 模式模型 15.851 ms ⇒ 差 **-2.1%**，超出误差界 ⇒ 本次抓取跑在 **8 MHz 模式**。

## 四、连带影响

### 4.1 半速清单（虚拟时钟是所有时基的公共上游）

| 受影响项 | 位置 | 现象 |
|---|---|---|
| BGM 事件调度 | `core/engine/audio.c:87,385`（`g_bgm.wall0`）、`core/lib/fmseq.c` | 音乐**半速** |
| SE / voice 的 FIFO 投料 | `core/engine/audio.c:674-684` | 每 tick 喂 22050×8.0625/1000 ≈ **178** 字节，而 DAC 每 16.188 ms 需 ≈ **357** 字节 ⇒ 欠喂 ~50% ⇒ FIFO 欠载 ⇒ 断续 |
| 打字机揭示 | `core/engine/nb_dialog.c:258` | 半速 |
| 动画时基 | `core/engine/nb_anim.c:568` | 半速 |

（`chime`/`ding` 的采样率为 22.05 kHz（`assets/demo-a2/se/*.pcm` 头 `rate_code=2`），`hi` 为 11.025 kHz（`rate_code=4`）。）

### 4.2 根因二：PCM 泵的时间源取自虚拟时钟（`devdocs/167` 引入）

`hal_pcm_tick(uint32_t elapsed_ms)`（`core/plat/hal_audio.c:176`）的 `elapsed_ms` 由 `audio_tick_isr()` 用 `hal_wallclock_smooth_ms()` 算出（`core/engine/audio.c:674-684`）⇒ 取的是**虚拟时钟**而非真实时间。

- 协作式路径的虚拟钟是自测量时钟，速率被钳制在 `target×4/5 … target×5/4`（`core/lib/vclock.h:115-116`），实测 `logs/probe_run.out` 尾段 Δv/Δw ≈ 4646/5000 = 93%；
- ⇒ SE/voice 的播放速度与音高随虚拟钟漂移。此前实现是「一直推到 FIFO 满」⇒ 硬件速率精确。

这条**与 ISR 无关**，默认（协作）构建同样中招 ⇒ 属于本轮 `devdocs/167` 引入的回归。

## 五、已拍板的修复方案（本轮只订正文档，实施在下一轮）

### 5.1 Timer-B 周期常量：编译期分档

**决定**：周期在运行时不可探测（宿主差异无法从引擎内识别），故按宿主编译期分档：

```
NP2kai（当前唯一验证环境） → 258 units（16.125 ms）
真机 86 板 OPNA             → 129 units（ 8.0625 ms）
```

- 默认档取 **NP2kai 258**：`NAIZ_BGM_IRQ` 整套方案就是在 NP2kai 上取证与验证的，且 `[ISR]` 行同时打印 `v` 与 `w`，选错会立刻表现为 `v/w ≠ 1`（不会静默）；真机档需显式选择，切换点与注释模板见下。
- 注释必须写清三件事：真机公式出处（`F04 §2`）、NP2kai 源码出处（`sound/opntimer.c:59-68` + `pccore.c:307-315`）、以及两者的 2× 关系——否则下一个读者会再次把它当常量。
- **不选运行时自校准的理由**：`hal_wallclock_ms()` 在 NP2kai 上只有 **1 秒粒度**（`w % 1000` 恒为 0），用它标定 tick 周期需要数十秒窗口才能把误差压到 1% 级，且需要一个带小数累加器的状态机；在实验性开关构建里引入这套机制，复杂度与风险都高于收益。运行时自校准保留为备选（§七）。

### 5.2 PCM 投料与虚拟时钟解耦

- **协作路径**：`elapsed_ms` 改取**真实墙钟** `hal_wallclock_ms()` 的差值 ⇒ SE/voice 速率回到硬件精确；
- **ISR 路径**：`elapsed_ms` 取**硬件 tick 步长**（= §5.1 选定常量换算的毫秒数）⇒ ISR 内不碰 DOS（保持 165 的 B1 约束），且周期改对后即等于真实时间；
- 接口形态：`audio_tick_isr()` 显式接收投料时长（而非自己读时钟），两条路径各自提供 ⇒ 时基来源在调用点即一目了然。

### 5.3 验证判据

1. **速率**：`[ISR]` 行的 `v/w` 应落在 **1.0 ±2%**（现状 49.8%）；
2. **单位自洽**：虚拟步进 = 选定常量 ÷ 16（NP2kai 档 ⇒ 16.125 ms/tick）；
3. **听感**：BGM 恢复正常速率；SE/voice 不再断续、速度与协作构建一致；
4. **构建纪律**：`export EXTRA_DEFS=-DNAIZ_BGM_IRQ=1` 必须贯穿 `makegame.sh build` + `make` **全管线**（`build` 会重跑 `compile_engine()`），结束后用 `strings` 确认部署树与 `core/engine.exe` 一致且不含 ISR 符号（c79/c81 教训；`tools/tests/test_engine_deploy_consistency.py` 已守机制）。

## 六、防复发

- **守卫点（下一轮实施时落地）**：把「`hal_irq.c` 的周期常量 = 所选宿主档的值」与「该常量在源码注释里带宿主推导」做成 pytest 断言，防止常量与档位脱钩；并把 165 的 ERRATA 块、167 的「§五 已重写且不含过期日志」做成守卫，防止订正被静默删除。
- **文档纪律**：`devdocs/167` 的 §五/§六 已按实机日志重写，**不得**再引用 `logs/serial_demo-a2_trace.log`（2026-09-29）作为任何 10 月构建的证据。
- **方法纪律**：任何「速率/时序正确」的断言必须有一个**独立于被测实现**的对照量（本例即 `w=`）；用被测实现的假设值自比不构成验证。

## 七、遗留与备选

1. **真机周期未取证**：分档方案把真机档固定为 `F04 §2` 的 129 units（未经实机验证）。若日后在真实 PC-98 上跑 ISR 构建，需核对 `[ISR]` 的 `v/w`，不符则再分档。
2. **运行时自校准备选**：若最终需要同时支持多个模拟器/真机而不分档，可改为「长窗口测量 + 小数累加器」的自动标定（墙钟粒度决定收敛速度），届时以本文件 §3 的模型为初值。
3. **方案 B（vclock 有界相位追赶）** 继续作为协作路径的回退方案保留；本文件不改变它。
4. **MIDI 后端 ISR 化**仍未覆盖（本环境无 MPU-401），不在本文范围。
