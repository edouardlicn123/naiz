# 174 — Timer-B 中断线候选扫描与看门狗选举（「Timer-B 不可用」是过期结论）

> **状态**：`已实施，待实机串口日志判定`（`hal_irq.c` 候选线扫描 + 看门狗；`NAIZ_BGM_IRQ` 默认 1；pytest 850 passed / 2 skipped；等 `./makegame.sh test demo-a2 --serial` 的 `BGM IRQ:` 行确认哪条候选线真正 tick）
> **创建于**：2026-10-27
> **承接**：`devdocs/171`、`devdocs/172`、`devdocs/173`

---

## 一、为什么现在要做

devdoc 173 收走追赶爆发后，用户仍听到「轻微的拖延和过快」。根因不在校准，而在**粒度**：`audio_tick()` 只从帧泵调用，NP2kai 下 pass 率约 20 Hz，音符起音被量化到 50 ms 网格，±25 ms 就是可闻的抖动。

要在不改变音乐相位的前提下消灭它，只有把音泵挂到硬件定时器上 —— OPNA Timer-B，NB=200 @ φM=7.9872 MHz → 16.154 ms ≈ 61.9 Hz，正好 ≈3 倍于 20 Hz 帧率。

## 二、「Timer-B 不可用」为什么是过期结论

此前若干轮把该结论当成既定事实，据此关闭了 ISR 路径。复核四条证据后确认结论建立在**已不存在的配置**上：

1. **NP2kai 源码**：`sound/opntimer.c::fmport_b()` 确实调 `pic_setirq(opna->s.irq)`；`cbus/board86.c::board86_reset()` 从板上 option 解出 `nIrq`，`opna_timer()` 再取 `s_irqtable[nIrq >> 6]`。**Timer-B 中断是被实现的**。
2. **本项目自己的日志**：devdocs/168 §3.1 记 `[ISR] ticks=6999 v=56421 w=110000` —— 63.6 Hz 单调递增，中断持续触发；devdoc 167 开头亦记「已实机证明中断持续触发」。
3. **真机与其他模拟器**：PC-9801-86 的 FM 中断是 IRQ12（可配 IRQ10/13/3），NP21w GUI 有「サウンド割り込み番号 / 割り込みの有無」。可被关闭，但**是被支持的标准功能**。
4. **配置已变**：用户换声卡时 `USEFMGEN: true → false`（从 fmgen 切到 np2kai 原生 OPNA，即上面读到的 `opntimer.c` 路径）、`SNDboard: 4 → 6`。得出「不触发」结论时的配置状态已不存在；`$27` D3 被写坏的那个 bug（devdocs/165 §59）此后也已修复。

真正的风险不是「Timer-B 不工作」，而是**挂错了向量**——见下节。

## 三、核心不确定性：IRQ 线由 DIP 决定

`cbus/board86.c::board86_reset()`：

```c
nIrq = (snd86opt & 0x10) | ((snd86opt & 0x4) << 5) | ((snd86opt & 0x8) << 3);
```

`sound/opntimer.c::opna_timer()`：`if (nIrq & 0x10) opna->s.irq = s_irqtable[nIrq >> 6];`，其中 `s_irqtable[4] = {0x03, 0x0D, 0x0A, 0x0C}`。

PC-98 的向量 = PIC base + 线号（master base `08h`，slave base `10h`，slave 挂 master IRQ7），故四种 strapping 对应四个向量：

| `nIrq >> 6` | `s_irqtable` | 线 | 向量 |
|---|---|---|---|
| 0 | `03h` | master IRQ3 | **INT 0Bh** |
| 1 | `0Dh` | slave IRQ5 | **INT 15h** |
| 2 | `0Ah` | slave IRQ2 | **INT 12h** |
| 3 | `0Ch` | slave IRQ4 | **INT 14h**（NP2kai opt=`7Fh` 默认；本项目实测线）|

引擎**读不到 DIP**。旧实现假设「先试 INT 14h，不成再试 INT 0Bh」，且一旦某个向量在 DPMI 里非空就立刻 `g_irq_active = 1` 夺取时钟/音泵所有权 —— 这正是「装上了但 ticks 永不增长」的最可能机制：挂上一条没有 tick 的线，同时把还在工作的协作泵关掉。

## 四、方案：顺序探测 + 看门狗

`hal_bgm_irq_init()` 改为**只编程 Timer-B，不夺取所有权**：

1. 写 `$26`（NB=200）、`$27`（LOAD B | ENABLE B）、`$29`（`80h|02h` = SCH 六声道 + EN_TB）。此时所有候选线仍屏蔽。
2. `g_irq_probing = 1; g_irq_active = 0;` → 协作泵继续跑，**BGM 永不静音**。
3. `bgm_irq_probe_advance()` 挂上第一条候选线（`bgm_irq_attach()`：保存原向量 → `_dos_setvect` → 保存并清除该 PIC 的 IMR 位）。

`hal_bgm_irq_probe_step()` 由 `engine_frame_pump()` 每帧调用：

- 记录 `g_probe_base_ticks = g_isr_ticks`，窗口 `BGM_IRQ_PROBE_FRAMES = 8` 帧。
- 若窗口内 `delta >= BGM_IRQ_PROBE_MIN_TICKS = 6` → **该线真的在 tick**，`g_irq_active = 1`，ISR 接管时钟与音泵。
- 否则 `bgm_irq_probe_advance()` 调 `bgm_irq_detach()`（**恢复 IMR 与原向量**，不永久屏蔽别人的线）并试下一条。
- 全部候选耗尽 → 掉 `no candidate ticks; co-operative pump stays active`，Timer-B 停掉（`$27` RESET B），协作泵保持。**这同时经验性地回答了「Timer-B 到底可不可用」**。

8 帧 ≈ NP2kai ~20 Hz 下 0.4 s（约 25 个 Timer-B tick），60 Hz 下 0.13 s（约 8 个）——`MIN_TICKS = 6` 足以把无关线上的偶发中断排除掉。

## 五、handler 必须自证身份

候选线可能与其它板卡共享。handler 因此**先读 `$188` 状态口 bit1**（Timer-B 溢出标志）：

- bit1 未置 → 不是我们的 tick：立刻两次 EOI 返回，**不碰时钟、不碰音频**；
- bit1 置 → `g_isr_ticks++`；仅当 `g_irq_active` 时才 `hal_wallclock_fixed_advance(258)` + `audio_tick_isr(258)`（探测期间只计数，否则会与协作泵叠加成双倍速度）。

确认应答 `$27` 必须保留 **D1（LOAD B）+ D3（ENABLE B）** 与 D5（RESET B）一起写（`0x2A`）：清 D1 会让 NP2kai 的 `opna_settimer` 丢弃 Timer-B 事件（定时器停摆），清 D3 后模型在第一个 tick 之后不再置溢出标志 / 拉 IRQ —— 只写 `0x20` 会让 ISR **恰好只触发一次**（devdocs/165 §二）。

## 六、改动清单

- `core/plat/hal_irq.c`
  - 候选线由 2 条扩到 4 条（`BGM_IRQ_LINE_COUNT 4`）：INT 14h → 0Bh → 15h → 12h，附完整 `s_irqtable` 映射来源注释；
  - `bgm_irq_attach()` / `bgm_irq_detach()`：成对的向量与 IMR 保存/恢复；
  - `bgm_irq_probe_advance()`：耗尽式推进候选游标；
  - `hal_bgm_irq_init()`：只编程 Timer-B，置 `g_irq_probing`；
  - `hal_bgm_irq_probe_step()`：看门狗选举；
  - `hal_bgm_irq_shutdown()`：判据改为 `g_irq_line < 0`（不再是 `!g_irq_active`），并走 `bgm_irq_detach()`；
  - handler：`$188` bit1 自证 + 探测期只计数。
- `core/plat/hal.h`：`NAIZ_BGM_IRQ` 默认 **1**；新增 `void hal_bgm_irq_probe_step(void);`；`hal_bgm_irq_active()` 语义改为「**选举完成**才为 1」。
- `core/engine/frame.c`：`engine_frame_pump()` 的 `#if NAIZ_BGM_IRQ` 块开头加 `hal_bgm_irq_probe_step();`。
- `core/engine/audio.c`：init 成功日志改为 `BGM IRQ: scanning FM IRQ line; co-operative pump stays active`（不再是「ISR active」）。
- `tools/tests/test_frame_pump.py`：`test_bgm_irq_is_gated_and_defaults_off` → `..._defaults_on`（默认值契约变更）；新增 `test_bgm_irq_scans_and_falls_back`（init 不得夺取所有权、step 必须按 ticks 选举、静默候选必须 detach、耗尽必须回落协作泵）。

## 七、判据（串口日志）

运行 `./makegame.sh test demo-a2 --serial` 后读 `logs/serial_demo-a2.log`：

- **成功**：出现 `BGM IRQ: <线名> ticks (N in M frames); ISR owns the pump`，且随后 `[ISR] ticks=` 单调递增、`v` 与 `w` 同步增长（≈63 Hz）。此后再无 ±25 ms 起音抖动。
- **失败**：出现 `BGM IRQ: no candidate ticks; co-operative pump stays active` —— 则该环境下 Timer-B 中断确实不可用，协作泵维持现状（devdoc 173 的成果不受影响）。
- 中间态：逐条 `BGM IRQ: <线名> silent (0 ticks in 8 frames); next candidate` 说明挂错线，这本身就是有价值的信息（可据此反推 DIP 设置）。

## 八、验证

- `make -C core`：`engine.exe` + `engine_a.exe` 均重建，`core/*.err` **不存在**（0 诊断）。
- `pytest tools/tests/`：**850 passed, 2 skipped, 1 failed** —— 唯一失败为 `test_naiz_market.py::test_clear_screen_emits_ansi_on_tty`，在 HEAD（未含本轮改动）上同样失败，属终端/pty 环境问题，与本轮无关。
- 版本：`bump_version` 0.3.057 → **0.3.058**（全项目同步），`nb_config.h` 重生成，`demo-a2.hdi` 重建完成。

## 九、ERRATA（针对 devdocs 171 / 172）

- **171/172 的 `BGM IRQ: installed; co-operative pump disabled (ISR active)` 不构成「ISR 正常」的证据** —— 该行只表示 `hal_bgm_irq_init()` 返回了 1（第一个向量非空即返回），并不表示中断在 tick。真正的中断活动证据只有 `[ISR] ticks=` 单调递增。
- **172 未覆盖 `hal_fm_detect()` 缺失 `outb(PCM_ID_PORT, 0x01)`** —— 即 OPNA 选择位从未被置起，空总线读到 `0xFF` 的直接原因。
- **172 未覆盖 `transition_run()` 16 帧紧循环零泵** 与 **`nb_process()` 显示命令累积零泵** 两个 BGM 停顿路径。
- **171/172 未标注 IRQ 选线依赖宿主 DIP** —— 任何「插上就工作」的表述都不成立，必须按本文 §三/§七 走观测。
