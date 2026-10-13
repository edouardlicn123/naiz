# 134 — 方案 C：OPNA Timer-B 中断驱动音泵（单独立项，未实施）

> 状态：`计划中`
> 版本：`0.3.031`（立项版本，未实现）
> 相关：devdoc 131 §4/§6/§9.1（方案 C 定义与依赖）、133（本轮 Phase 1–4，症状 1+2 的时基修复）、129（帧泵）、130（vclock）、B19 §2（时钟源决策）
> refdocs：`F04_opna_timer_a_b_specs.md`、`F05_pmd_driver_architecture.md`、`G08_dos4gw_interrupt_and_pit.md`、`G09_timing_vsync_audio_engineering.md`

## 1. 立项理由

devdoc 133 的虚拟时钟仍由**主循环协作轮询**推进：其节拍正确性取决于 pass 率稳定。任何长 CPU 操作（立绘解码、blit、菜单重排）都会降低窗口内 pass 数，使**该窗口内的音乐时间不足**——「稳态颤」可被 133 的测量平滑治好，但**加载期 tempo 塌陷**是结构性的，只有把音泵从主循环解耦才能根治。这正是原版 PC-98 音乐「不颤」的架构来源（`F05`：PMD 常驻驱动 + Timer-B 中断，与游戏主循环解耦）。

方案 C 即复刻该模型：初始化 YM2608 Timer-B → 挂中断处理 → 中断内推进 BGM 事件表。**本环境（NP2kai）无法验证中断投递与级联 ACK，写错会静默卡死**，故不并入 133，单独立项。

## 2. 硬件与 API 事实（来自 refdocs）

- **Timer-B**：`tB = 1152 · (256 − NB) / φM`，精度基准 144µs/步（`F04` §2）。两级门控：`$27`（Timer 控制）/`$29`（SCH + IRQ ENABLE，D1=EN_TB）。IRQ 经 PC-98 板载路由到 **IRQ3**（QEMU `pc98-opna` 事实，`F04` §6；`hal_audio.c` 现有端口 `0x0188`/`0x018A`）。
- **DOS/4GW 挂中断**：`_go32_dpmi_*` / `__dpmi_*` + iret wrapper + **锁内存**（handler 必须常驻、不可被换页），bi-modal handler（`G08`）。
- **级联 IRQ ACK**：PC-98 双 8259 级联，EOI 次序与 in-service 位需按手册；鼠标 IRQ13 优先级高于 FM IRQ12；写 0x64 → vsync IRQ2（`G09` §3 有 DOSBox-X #342 的完整清单，作为方案 C 前置检查）。
- **未确认项（动手前硬阻塞）**：NP2kai 是否/以何频率投递 OPNA Timer IRQ（`F04:141`）、DOS/4GW 下默认 IRQ 号与向量映射（`G08:80`）、`$29` 默认位行为（`F04:173`，devdoc 131 与手册不一致）。

## 3. 分两步实施（风险递增）

### 步骤 1 — 中断投递探针（低成本、默认关、只读）

目的：一次实机即可判定「C 可行不可行、该用哪个中断源」，零运行时风险。

- 最小 handler：只**计数** + 清芯片标志（`$110` IRQ RESET / `$27` RESET 位，`F04` §5）+ **级联 EOI** + 串口打印计数。
- 先用 C handler + `_go32_dpmi_allocate_iret_wrapper` + CWSDPR0（`G08:57`）；确认可行后再考虑汇编 handler。
- **优先测 GDC vsync IRQ(0x64)**（`G09:41`）：PC-98 原生 IRQ2、不碰 OPNA 端口、不触及 FM 静音陷阱（`hal_audio.c:143` 的 `A460` bit1 = 强制 FM 静音）。若 NP2kai 按帧投递它，则是比 Timer-B 更省的稳定 60Hz 中断时基。
- 通过条件：探针计数 ≈ 预期频率（vsync ≈ 显示帧率；Timer-B ≈ `1/tB`）且抖动可接受。

### 步骤 2 — 音泵接管（探针通过后才做）

- 初始化 Timer-B（`F04` §5），handler 内推进 BGM 事件表（替代 `audio_tick()` 的轮询推进）。
- **重估契约**：`vclock` 所有权（devdoc 129 规定单写者 = 帧泵）、`audio_tick()` 的单消费方假设、`frame_decode_pump()` 与 ISR 的并发裁决。
- PCM 泵与 BGM 泵的关系：ISR 是否只推 BGM、PCM FIFO 仍由主循环喂（避免 ISR 内做重活）。

### 3.3 与 133 的关系

- 133 是 C 的**前置**：若 133 后 `[VC]` 显示稳态已稳、加载塌陷可接受，C 优先级下降；若加载瞬时仍慢，则 C 是唯一根治。
- C 落地后 133 的测量平滑/首窗直采仍有用（作为 ISR 缺席时的降级路径）。

## 4. 不在本轮范围

- 症状 3「立绘拖」与 C 无关（devdoc 131 矩阵：C 治颤、不治拖），由 133 的预取与去 hitch 处理。
- 方案 E（多时基投票等）仍不建议。

## 5. 验收（步骤 1）

- 中断计数在串口稳定输出且与预期频率量级一致；
- 系统不卡死（中断未挂错向量、EOI 正确、键盘鼠标仍响应）；
- 一次实机日志即可判定步骤 2 是否值得投入。

## 6. 前置调研清单（动手前逐条核）

1. NP2kai OPNA Timer IRQ 投递频率与抖动（`F04:141`）；
2. DOS/4GW 下 IRQ 向量/默认 IRQ 号（`G08:80`）；
3. `$29` 默认位行为与清标志/重装载次序（`F04:173`）；
4. G09 §3 级联 ACK 清单逐条对照（EOI/in-service、双 8259、鼠标优先级）。
