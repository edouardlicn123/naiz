# 176 — ISR 路径 FM 静音根因：DOS/4GW 中断栈段与栈局部变量指针写入

> **状态**：**已完结**（0.3.062；根因已定位、修复已落地、ISR/COOP 双路径以客观音频抓取验证）
> **创建于**：2026-10-27
> **承接**：`devdocs/175`（ISR 路径回退与根因待解；本文订正其 §四 的推断）、`devdocs/168`（Timer-B 步长定论）、`devdocs/165`（ISR 安全约束）
> **影响**：`core/plat/hal_irq.c`、`core/engine/audio.c`、`core/engine/frame.c`、`core/engine/transition.c`

---

## 一、症状

用户在 `nbook001` 场景中报告「场景运行正常但听不到声音」：对白推进正常、SE/语音可闻，**BGM 静音**。该症状只出现在 Timer-B ISR 接管音泵的模式（bootmenu BGM Mode = ISR）；切回 COOP 后同一场景同一首 `melody_town` 有声音。

`devdocs/175` 曾把「bootmenu 无 BGM」当作证据污染源，因此本轮的第一条纪律是：**先确认 `BGM start 'melody_town'` 已出现在串口，再取音频证据**。

## 二、判定过程（全部为客观取证）

### 2.1 抓取模拟器真实输出

`./makegame.sh test demo-a2 --serial` + `SDL_AUDIODRIVER=disk`（`SDL_AUDIO_DISK_OUTPUT_FILE` 指向 raw 文件），xdotool 驱动 bootmenu → mainmenu → `nbook001`，等 `BGM start` 后开始计窗。同场景同曲，仅切换 BGM Mode：

| 模式 | samples | RMS | peak |
|---|---|---|---|
| ISR | 593920 | **0.0** | **0** |
| COOP | 548864 | 5131.9 | 14188 |

ISR 是**精确数字静音**（全零），不是「音量偏小」或「音色不对」。

### 2.2 逐秒 RMS：PCM 正常，FM 归零

在 ISR 模式下逐秒抓取并每 2 s 推进对白（触发 `sound(){chime}` / `voice(){hi}`）：PCM 爆发秒 `peak=16384`、RMS 4800–8600，其余秒 `RMS=0.0 peak=0`。
→ SE/语音（PCM 通路）在 ISR 下**可用**，被判定失效的是 **FM（BGM）通路**。

### 2.3 ISR 内计数：泵在跑、键控在发

在 `fm_sink_write()` 与 `fmseq_pump()` 加 ISR 安全计数器（ISR 只写全局，主线程 dump）：

```
DIAG pumps=188 keyons=6 writes=183 n=183
```

泵被调用、键控事件产生、寄存器写请求也发生。**「有写入」不等于「写对了地址」**。

### 2.4 写入序列对照：值全对，地址全 0

同一次启动的前 96 次 FM 写，按 `地址:数据` 成对 dump：

```
COOP: 30:01 40:3B 50:4C 60:05 70:03 80:A8 34:01 44:7F ... B0:04 B4:C1 A4:2A A0:B6
ISR : 00:01 00:3B 00:4C 00:05 00:03 00:A8 00:01 00:7F ... 00:00 00:00 00:00 00:00
```

数据字节逐项相同，**地址字节全部为 `0x00`**。所有音色/音高/键控都写进 OPNA 寄存器 0，必然静音；同时这些是「写错线性地址」的散写，属于潜在内存破坏。

### 2.5 指针写出参探针

构造一个只做「经指针写一字节」的函数，分别指向栈局部变量与全局变量；再用 `fmopn_ch_addr(0, 0xA0, &bank, &addr)` 分别以全局/栈变量接收出参：

| 目标 | ISR 内结果 | COOP 内结果 |
|---|---|---|
| 指针指向栈局部 | 值未变（写入丢失） | 正常 |
| 指针指向全局 | 值改变（写入落地） | 正常 |
| 出参用全局 | `addr=A0`（正确） | `addr=A0` |
| 出参用栈局部 | `addr=10`（垃圾） | `addr=A0` |

结论：**ISR 内「经指针写栈局部变量」整体失效**，而写全局正常。

### 2.6 段寄存器读数（最小判定证据）

```
ISR : ss=00B0 ds=0160 esp=4F58 loc=4F58
main: ss=0160 ds=0160
```

## 三、根因

DOS/4GW 在投递硬件中断时**切换到自己的栈段**：ISR 内 `SS=00B0`，而平坦数据选择子仍是 `DS=0160`。栈上局部变量的地址是 **SS 段内偏移**，不是 DS 可达的线性地址；因此：

```
fmopn_reg_addr(ch, reg, &bank, &addr);   /* bank/addr 是调用者的栈局部变量 */
```

`fmopn_reg_addr()`（`core/lib/fmopn.c:288`）通过 `*bank` / `*addr` 写出参时，写入落到了错误的线性地址（约 `0x4F58` 的低内存），调用方的 `addr` 保持未初始化值；`fmseq.c` 的 `fm_op_addr()` / `fm_ch_addr()` 全部以栈局部变量接收出参，于是每次 FM 写的 `addr` 都是 0。修复前的表现因此精确对应：**数据对、地址 0、BGM 静音、低内存散写**。

**为什么躲过了 devdoc 165 的 ISR 安全审查**：该审查覆盖了浮点、日志、堆分配、DOS/BIOS 调用，但没有覆盖「经指针写出参到栈局部变量」这一类——它在平常代码里完全合法，只在「SS 基址 ≠ DS 基址」的执行环境下失效。

## 四、修复：ISR 只拥有时钟

原则：**中断处理函数不执行任何引擎代码**；它只做两件全部基于全局量的事，其余工作回到主线程（`SS == DS`）。

| 位置 | 改动 |
|---|---|
| `core/plat/hal_irq.c:168` `bgm_irq_handler()` | 保留 `hal_wallclock_fixed_advance(BGM_TIMER_B_UNITS)`；新增 `g_irq_units_total += BGM_TIMER_B_UNITS`；删除 `audio_tick_isr()` 调用与 `#include "audio.h"` |
| `core/plat/hal_irq.c:356` `hal_bgm_irq_take_pending_units()` | 返回 `produced - consumed` 差分。`consumed` 是只在主线程写的 `static`，对齐 32 位读写原子，无需关中断，也不会丢 tick |
| `core/engine/audio.c:742` `audio_tick_isr_pending()` | 主线程排水：取待处理单位后调用 `audio_tick_isr(units)`（`:748`） |
| `core/engine/frame.c:37`、`:93` | 正常帧与解码泵在 ISR 持有时调用排水函数 |
| `core/engine/transition.c:63` | 过渡循环在 ISR 持有时只排水，不再推进协作时钟（否则过渡期间双倍速率） |

`[ISR] ticks=… v=… w=…` 心跳保留在 `frame.c:46`，继续作为「Timer-B 真的在跳」的取证点。

## 五、验证

修复后同一驱动、同一场景、同一首曲：

| 模式 | samples | RMS | peak |
|---|---|---|---|
| ISR | 552960 | **5354.9** | 14287 |
| COOP | 462848 | 5283.2 | 14280 |

- 14 s ISR 逐秒剖面（修复后最终构建）：**每一秒都有信号**（RMS 3561–9504，peak 6588–21771；对白推进处为 PCM 叠加），不再出现连续静音秒。
- `[ISR] ticks` 持续递增，`v` 与 `w` 同步（`v/w ≈ 1.03–1.05`，属已知的时钟速率独立项，不在本文范围）。
- `make -C core` 返回 0，`core/*.err` 无内容。

## 六、防复发

1. **规则（架构级）**：中断处理函数内禁止调用引擎层代码，禁止任何「取栈局部变量地址并经指针写」的操作。ISR 只允许 HAL 层、仅使用全局量的原语。需要引擎工作时，用「计数/队列 + 主线程排水」。
2. **守卫** `tools/tests/test_isr_pump_boundary.py`：
   - `bgm_irq_handler()` 函数体内不得出现 `audio_tick_isr(`、`fmseq`、`hal_log`；
   - `core/plat/hal_irq.c` 不得 `#include "audio.h"`（plat 不反向依赖 engine）；
   - `audio_tick_isr_pending()` 必须存在且被 `frame.c` / `transition.c` 调用。
3. **取证纪律**：ISR 静音类问题必须先满足「真实 BGM 已启动」再抓音频（`devdocs/175` §五），且**只读探针优先**——本次第一版探针本身就在 ISR 内写栈局部变量，直接向低内存散写。

## 七、踩坑清单

1. **「有写入」不是「写对地址」**：计数器只能证明调用发生，必须 dump `addr:value` 成对序列才能发现地址字段归零。
2. **只比对数据字节会漏掉地址**：`30:01` vs `00:01` 的数据完全一致，差异只在地址。
3. **flat 模型不等于 SS==DS**：DOS/4GW 的 IRQ 栈段是独立对象；判断 ISR 执行环境的最小证据是 `SS`/`DS`/`ESP` 读数。
4. **ISR 内写探针会破坏内存**：任何「验证写入是否生效」的探针若本身经指针写栈局部变量，就会复现同一 bug 并向低内存散写；应改为只读或写全局。
5. **修复要覆盖所有泵入口**：主循环、解码泵、场景过渡三条路径都会推进音泵；只改其中一条会在特定阶段回落旧行为。
