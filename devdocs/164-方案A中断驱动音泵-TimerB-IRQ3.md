# 164 — 方案 A：中断驱动音泵（OPNA Timer-B → IRQ12/IRQ3 双线自适应）

> **状态**：`实施中`（阶段 0 实机取证经 §4.1→§4.2→**§4.3 修探针重跑**→**§4.4 IRQ 线定论**：`flags=1` 证实 **32-bit DPMI host**；`pic=08/10` 证实 master 基向量 08h + slave 基向量 10h——**NP2kai 的 OPNA Timer IRQ 实为 IRQ12（slave, INT 14h）**，原 IRQ3 假设经 §4.4 源码链推翻、改「双线自适应」；阶段 0 **取证通过**，DPMI `0205`/`_dos_setvect` 挂 32-bit ISR 技术可行；阶段 1 骨架已落地并按 §4.4 改为双线，编译验证，**待实机启用**（`NAIZ_BGM_IRQ=1`）；阶段 2 实机验证仅完成探针部分）
> **版本**：`0.3.051`（探针修正 + 重跑清洁读数回填 + §4.4 IRQ 线定论与双线自适应）
> **相关**：`devdocs/163`（BGM 不可打断性三阶段总纲，C2 定义）／`devdocs/134`（方案 C 立项蓝本）／`devdocs/133`（vclock 首窗直采 + 测量平滑）／`devdocs/131`（帧泵 + 解码泵 + 方案 A–E）／`devdocs/129`（帧泵所有权）／`B19 §2`（时钟源谱系）
> **refdocs**：`F04_opna_timer_a_b_specs.md`（Timer-B 规格、`$27`/`$29`、QEMU IRQ3 事实）、`G08_dos4gw_interrupt_and_pit.md`（DPMI 中断 API + 锁页）、`G09_timing_vsync_audio_engineering.md`（vsync IRQ + 级联 ACK 清单）、`F03_opna_fm_and_bgm_routes.md`（`$110` status）、`C01_display_system.md`（vsync IRQ 事实）

> ## ⚠ ERRATA（0.3.053 追加）
>
> **本文 §5.3 的 handler 体前提「时钟读 + `audio_tick()` 在 ISR 内安全」被实机证伪。**
>
> - **§5.3 声称**：handler 内依次调 `hal_wallclock_smooth_advance()`、`fmseq_pump`、`hal_pcm_tick`、清标志、双 EOI，「严格有界，无 malloc/fopen」。
> - **实际**：`hal_wallclock_smooth_advance()` 经 `hal_wallclock_ms()` 走 **`int386`（DOS 反射）**，在硬件 ISR 内不可重入 → **实机立即静默卡死**；`audio_tick()` 另有 `hal_logf`（B3）、`free`（B4）、note-on 路径的 `pow`/`double`（B2）三类 ISR 不安全构造。
> - **正确结论**：ISR **不得**做 DOS/FP/串口日志/堆调用；时基改用**定点硬件步进**（Timer-B 周期常量），音频泵拆为 ISR 安全核心。完整取证、四类不安全构造清单与改造方案见 **`devdocs/165`**。
> - 另：本文未记录的 `$27` 清标志写入内容问题（须写 `RESET_B|ENABLE_B|LOAD_B=0x2A`，否则 NP2kai 静默停表）亦见 `devdocs/165 §二`。


## 一 症状与定性（承 163）

**症状**：任何操作（对白翻页／立绘／SE／voice／菜单）执行时 BGM 明显暂停，操作结束**原地续播**。

**定性（163 §二）**：M1 主嫌 = **慢 pass 时间债**。`audio_tick()`（`audio.c:572`）是 `fmseq_pump`/PCM 的唯一泵，只在 `engine_frame_pump()`/`frame_decode_pump()` 被调；而 `vclock_advance()`（`vclock.c:70`）每次只发 `step`（与本次真实 `delta` 无关），**相位差从不补偿**（`vclock.h` 明文「only the rate matters」）。一次慢 pass（整页重绘／模拟器放大）墙钟走 200–300 ms、虚拟钟只走 ≈36 ms = **音乐时间债**；债此后仅被 5/4 窗口比率钳制的瞬态速率追赶、无相位偿还 ⇒ 操作期停住、操作后原地续播。

163 的 Phase 1（取证打点）/Phase 2（解码泵时钟去门控 B2）**只覆盖 MAG 解码**这一条 CPU 密集路径，且明文「M1 属结构性，Phase 3 方能根治」。故 163 后其他指令的暂停残留 = **预期**，本轮（Phase 3）即根治。

## 二 用户拍板

1. **跳过探针**，直接实施中断驱动音泵（方案 A）；
2. **中断源 = OPNA Timer-B → PC-98 IRQ3**（`F04 §6` QEMU 事实；不选 GDC vsync IRQ2）。**⚠ 已订正（§4.4）**：本仓实机 oracle NP2kai 实际用 **IRQ12（slave）**，故实现改为 **IRQ12 优先 / IRQ3 回退的「双线自适应」**；本项原「IRQ3」拍板保留为历史记录。
3. **窗口化交付**：阶段 0（只读自检）→ 阶段 1（ISR 骨架）→ 阶段 2（实机验证）；
4. 已做 git 准备。

## 三 工具链现实（本环境实测，硬约束）

**关键发现（比 devdoc 134 的预想更严峻）**：

| 事实 | 值 | 出处 |
|---|---|---|
| `dpmi.h` / `_go32_dpmi_*` | **不存在**（DJGPP 专属，Watcom 侧等价物「未调研」） | 实测 `/usr/h`；`G08:81` |
| 可用头文件 API | `dos.h` 的 `_dos_getvect/_dos_setvect`；`i86.h` 的 `int386/int386x` | 实测 `/usr/h` |
| Watcom `__interrupt` | `union INTPACK` 调用约定，**偏 16-bit DOS 语义**（`i86.h:161`） | 实测 |

**结论**：DPMI INT 31h 的 `0204`（取 PM 向量）/`0205`（设 PM 向量）/`0600`（锁页）与 **Watcom 原生 `_dos_setvect()`**（`dos.h`，§4.2 调研确认对 `8–2Eh` auto-passup 范围**足够**）是两条可行路径，但其在 Watcom + DOS/4GW 下的实际行为**首次落地时未经证实**。这正是必须**先做阶段 0 只读自检**的原因——否则阶段 1 的挂接代码在不知道 API 是否可用的前提下盲写，失败也无法区分「代码错」与「平台不支持」（§九.6：假通过比失败更危险）。（**注**：初稿曾写「DPMI 0205 是唯一可行路径」，经 §4.2 调研订正为「`_dos_setvect()` 便捷路 + DPMI 高效路双选」。）

## 四 阶段 0：DPMI 能力自检（只读，零风险）

**新增** `core/plat/hal_pc98.c::hal_dpmi_probe_run()`（`#if NAIZ_IRQ_PROBE` 编译门控，与 `hal_irq_probe_run()` 并列），`main.c` 在 `hal_irq_probe_run()` 后调用。

**动作（全部只读，绝不 setvect / 绝不改写向量或 IMR）**：
1. `int386(0x31, AX=0400)` → DPMI 版本 + 32-bit 标志 → `[DPMP] ver=%d.%d bits32=%d`；
2. `int386(0x31, AX=0204, BL=vec)` → 取 IRQ 对应实模式向量的 PM 向量。IRQ3 → INT 0Bh（向量基 0x08 + 3，`G01:87`「IRQ0=INT 08h」）；**IRQ12 → INT 14h（向量基 0x10 + 4，`B01:104-113`；§4.4 定论为本 oracle 的实线）**；同时探 0x0A（vsync，供交叉判定）；
3. `int386(0x31, AX=0600, ...)` → 探锁页 API 是否响应。

**串口产出**（设计期原始格式）：`[DPMP] ver=… bits32=… vec0B=… vec0A=… lock_ok=… lock_off=…`（**已改**，现行格式见 §4.3：`flags=`/`cpu=`/`pic=`/`cfB`/`cfA`）

**判定**（**注**：此三行是探针设计期的**原始预设**，已被 §4.2 调研订正——`0400` 的 32-bit 标志读的是 **BX bit0** 而非 CL，且 DPMI 0.9 并不排除 ISR 挂接；实机结论见 §4.1/§4.2）：
- `0204` 对 IRQ 向量返回成功且 `bits32=1` ⇒ 阶段 1 的 `0205` 挂接**理论可行**（本 oracle 实为 IRQ12，§4.4）；
- `0204` 失败 / `bits32=0` ⇒ 方案 A 在本工具链下**不可行**，应转到**方案 B（vclock 有界相位追赶，`devdocs/163 §4 B3`）**。

### 4.1 实机取证结果（2026-10-21，0.3.050）

**构建与运行**：`export EXTRA_DEFS=-DNAIZ_IRQ_PROBE=1` → `make -C core clean` → `./makegame.sh build demo-a2 && ./makegame.sh make demo-a2` → `test-hdi --serial`（NP2kai `wxnp21kai` IA32 核，宿主 DOS/4GW）。探针在 `main.c:98` `hal_video_init()` 后执行。

**串口原始输出**（`logs/serial_demo-a2.log`）：
```
Init OK
Vid OK
[IRQP] vsync irq2 hits=3878 samples=3878 imr=7d (2s)
[DPMP] ver=0.90 bits32=0 vec0B=80002c vec0A=800028 lock_ok=0 lock_off=1000
VRAM OK
```

**逐项解读**：

| 指标 | 值 | 含义 |
|---|---|---|
| `ver=0.90` | DPMI 0.9 | **规范文书化的 0.9 标记**：`0400` 下 AH=0、AL=90（十进制）= 0x5A（`delorie 310400` 明文「Under DPMI version 0.9 hosts, AH is returned as 0, and AL is returned as decimal 90」）⇒ 宿主是 **DPMI 0.9**（1993 年 DOS/4GW v4.45 的典型版本），`0204`/`0205`/`0600` **均为 0.9 已定义 API**（见下「调研订正」） |
| ~~**`bits32=0`** ⚠~~ → **探针读位 bug** | **无效读数** | `0400` 的 32-bit host 标志在 **BX bit0**（`delorie 310400`：Bit0 `0=16-bit host / 1=32-bit (80386) host`）；**CL 是 CPU 类型**（`02=286 / 03=386 / 04=486 / 05+=保留`），**与 32-bit host 无关**。探针 `hal_pc98.c:256` 读的是 `r.x.ecx & 0x01` = **CL 的最低位** = 「CPU 类型为偶数」= NP2kai IA32 核报 80486（`CL=04`）⇒ **恒 0**。**该位不构成任何结论** |
| `vec0B=80002c` | IRQ3 / INT 0Bh 向量 | 指向保护模式高址——**符合 DOS/4GW 期待**：`8–2Eh` 是 DOS/4GW 的 **auto-passup 范围**，extender 会在此区段预置 PM passup stub（`dos4gwqa 4a`）——**非「异常占用」，是机制本身** |
| `vec0A=800028` | IRQ2 / INT 0Ah 向量 | 紧邻 0Bh（差 4），同属 DOS/4GW passup stub 区（同上） |
| ~~**`lock_ok=0`** ⚠~~ → **基本无意义** | **本环境无 VM，锁页非必要** | ① 探针用线性地址 `0` + `esi/edi=0` 探（`hal_pc98.c:279-282`），对任意地址本就不保证成功；② **决定性事实**：部署树 `AUTOEXEC.BAT` **未设 `DOS4GVM`**，`CONFIG.SYS` 用 **VEM486** 而非 DOS/4GW VMM ⇒ 按 `dos4gqa`/DOS4GW 文档「If this variable is not set, then only real memory will be used」⇒ **无分页、无换出，`0600` 锁页在无 VM 下空转**。锁页只在 Windows/OS-2/CWSDPMI/`DOS4GVM` VMM 等**有分页宿主**下才成为硬约束（`dos4gqa 4c/7c`） |
| `[IRQP] hits=3878 samples=3878` | 100% | **GDC vsync 确实以 IRQ2 投递**（`163` C1 判定成立），IRQ2 是可靠中断源 |

**取证结论（调研订正后——由「负向」改为「待实机重验」，见 §4.2）**：

1. **原「`bits32=0` + `lock_ok=0` 双红灯」已证伪**：`bits32` 是**探针读位 bug**（读了 CL 而非 BX），`lock_ok=0` 在**无 VM 宿主下无意义**——**两者都不支持「DPMI 层不可靠」这一结论**。
2. **IRQ3 → INT 0Bh 映射成立**且落于 PC-98 master PIC 标准向量区（`G01:87`）；**IRQ12 → INT 14h（slave base 0x10）同由 `pic=08/10` 证实（§4.4）**；`vec0B` 已指向保护模式高址 = DOS/4GW 标准 passup stub，**恰好证明该向量在 PM 下可挂**。
3. **Watcom 原生路径存在且优先**：`dos4gwqa 4a` 明文——中断号在 **auto-passup 范围 `8–2Eh`** 时，**仅用 `INT 21h/25h` 或 `_dos_setvect()`（Watcom `dos.h` 直接可用，见 §三）** 即可让 DOS/4GW 同时把 PM/RM 中断路由到你的 PM handler；DPMI `0205` 是「高效路」（避免模式切换）而非必需。故 §三「DPMI 0205 是唯一可行路径」的结论**过窄**，应改为「`_dos_setvect()` 便捷路 + `0205`/`0208` 高效路双选」。
4. **`0600` 锁页在实机（有 VMM 的 PC-98 宿主）才需处理**——本 NP2kai 环境（无 `DOS4GVM`）不需要；实机若不设 `DOS4GVM` 亦然。若未来宿主带 VMM，再按 `dos4gqa 4c` 锁 handler 代码/数据。

**遗留待办（订正后）**：
- ~~修正探针 `bits32` 读位并重跑~~ → **已完成，见 §4.3**（`flags=1` 证实 32-bit host）；
- `[IRQP]` 已证 IRQ2 可靠；IRQ3 是否被 Timer-B 抬升**仍须实机验证**（探针只查向量、未让 Timer-B 起振）；
- 装 ISR（`NAIZ_BGM_IRQ=1`）后是否静默卡死**仍须实机验证**——但风险已由「DPMI 不可靠」大幅下调为「挂在 IRQ3 上的既有 stub 链是否可安全覆盖/链尾」。

### 4.2 网络调研订正（2026-10-21，0.3.050）

承 §4.1 遗留项，就三项疑点查证外部规范，**三项全部指向「原负向结论过强，探针有 bug」**：

| 疑点 | 调研结论 | 出处 |
|---|---|---|
| `bits32=0` 是否有效 | **无效**：32-bit host 位在 **BX bit0**；**CL = CPU 类型**（04=486）。探针读 `ecx & 1` 取的是 CPU 类型最低位，486⇒0 | `delorie.com/djgpp/doc/dpmi/api/310400.html` |
| `ver=0.90` 含义 | **DPMI 0.9 文书标记**（AH=0/AL=90）；`0204`/`0205`/`0600` 均为 **0.9 已定义**（DOS/4GW QA「DPMI functions supported」表列 0204/0205/0600），故 0.9 **不排除** ISR 挂接 | `delorie 310400` + Open Watcom `dos4gwqa.gml` |
| `lock_ok=0` 是否致命 | **不致命**：部署树 `AUTOEXEC.BAT` 未设 `DOS4GVM`、用 **VEM486** ⇒ **无分页宿主**，锁页空转；且探针探的是线性地址 0 | 部署树 `AUTOEXEC.BAT`/`CONFIG.SYS`（HDI 实测）+ `dos4gwqa 4c/7c` |
| （新增）IRQ3 怎么挂 | **`_dos_setvect(0x0B, h)` 即可**：0Bh ∈ auto-passup `8–2Eh`，DOS/4GW 自动双向路由；`0205` 为高效替代 | `dos4gwqa 4a`（原文引于 G08 §2.5 上游） |
| （新增）`vec0B=80002c` 表示什么 | **DOS/4GW passup stub**（8–2Eh 区段 PM 化），机制正常，**非异常占用** | `dos4gwqa 4a` |

**订正后的路线**：方案 A **未被证否**，改判为「**待实机重验**」——阶段 0 探针先修读位重跑（取 BX bit0 / CL / DH / DL 干净读数），再决定走 `_dos_setvect()` 便捷路还是 DPMI `0205` 高效路。方案 B（vclock 有界相位追赶）保留为**回退**，但不再是「因 DPMI 不可靠而优先」。

### 4.3 探针修正 + 重跑（2026-10-21，0.3.051，**清洁读数**）

**探针修正**（`core/plat/hal_pc98.c::hal_dpmi_probe_run()`）：
- `bits32 = r.x.ecx & 0x01` → **`flags = r.x.ebx & 0x05`**（BX bit0 = 32-bit host、bit2 = 虚拟内存；此前误读 CL）；
- 增打 `cpu`（CL = 处理器类型）、`pic`（DH/DL = master/slave PIC 基向量）、`cfB`/`cfA`（两次 `0204` 的进位，0=成功）。

**重跑方式**（`NAIZ_IRQ_PROBE=1` 全流程，**关键教训**：`makegame.sh build` 会重跑 `compile_engine()` 且**不携带** `EXTRA_DEFS` ⇒ 必须 `export EXTRA_DEFS=-DNAIZ_IRQ_PROBE=1` 覆盖**整条** `build`+`make` 管线，否则 `a_main.o` 无旗标而 `a_hal_pc98.o` 有之 → **混用陈旧对象、探针被静默编译掉**）。

**串口原始输出**（`logs/serial_demo-a2.log`）：
```
[IRQP] vsync irq2 hits=3872 samples=3872 imr=7d (2s)
[DPMP] ver=0.90 flags=1 cpu=6 pic=08/10 cfB=0 cfA=0 vec0B=80002c vec0A=800028 lock_ok=0 lock_off=1000
```

**逐项解读（清洁读数）**：

| 指标 | 值 | 含义 |
|---|---|---|
| `ver=0.90` | DPMI 0.9 | 文书标记（AH=0/AL=90），非「0.9」字面 |
| **`flags=1`** | ✅ | `BX & 0x05 = 1` ⇒ **bit0=1 = 32-bit (80386) DPMI host**；bit2=0 = 无虚拟内存。**原 `bits32=0` 确系读位 bug，此位实为正** |
| `cpu=6` | CL=6 | 处理器类型（文档 0.9 定义 02–05；6 属 `05H-FFH` 保留区，NP2kai 报较新型号，无碍） |
| **`pic=08/10`** | ✅ | **DH=0x08 = master PIC 基向量 = INT 08h**，与 `G01:87`「IRQ0=INT 08h」一致 ⇒ **IRQ3 → INT 0Bh 得证**；**DL=0x10 = slave PIC 基向量 = INT 10h**，与 `B01:104-113` IRQ 分配表（slave IRQ8→INT 10h）一致 ⇒ **IRQ12 → INT 14h 得证**（细节见 §4.4） |
| **`cfB=0` / `cfA=0`** | ✅ | 两次 `0204` 进位为 0 = **均成功**（读回 `vec0B`/`vec0A` 非 0 佐证） |
| `vec0B=80002c` / `vec0A=800028` | 正常 | DOS/4GW passup stub（`8–2Eh` auto-passup 区段 PM 化） |
| `lock_ok=0` | 无意义 | 无 `DOS4GVM` 宿主 ⇒ 锁页空转（§4.2）；探的是线性地址 0 |
| `[IRQP] 100%` | ✅ | IRQ2（GDC vsync）投递可靠（`163` C1） |

**重跑结论（决定性）**：
1. ✅ **32-bit DPMI host 证实**（`flags=1`）——原「DPMI 层不可靠」结论**彻底证伪**。
2. ✅ **IRQ3 → INT 0Bh 映射得证**（`pic=08` + `cfB=0` + `vec0B` 有效）。
3. ✅ **阶段 0 取证通过**：Watcom + DOS/4GW 下用 DPMI `0205`（高效路）或 `_dos_setvect(0x0B,…)`（便捷路，`8–2Eh` auto-passup）挂 32-bit ISR **技术上可行**。
4. **`lock_ok=0` 不构成阻塞**（无 VM 宿主）；**`cpu=6` 无碍**。

**新遗留**：
- IRQ3/IRQ12 是否被 Timer-B **实际抬升**仍须实机（探针只查向量）；
- `NAIZ_BGM_IRQ=1` 装 ISR 后是否静默卡死仍须实机（风险已降至「既有 stub 链可否安全覆盖/链尾」）。

### 4.4 IRQ 线归属定论 + 双线自适应（2026-10-21，**推翻原 IRQ3 假设**）

承 §4.3：`pic=08/10` 同时证实了 **master 基向量 08h** 与 **slave 基向量 10h**——后者正是原判「`DL=0x10` 异常（标准 0x70）」的**订正**：DDPMI `310400` 规格（delorie）定义 `DH=virtual master PIC base`、`DL=virtual slave PIC base`；**PC-98 的 slave 基向量本就是 `0x10`**（IBM PC 才是 `0x70`），依 `docs/refdocs/B01_memory_map.md:104-113`：master IRQ0→INT 08h、slave IRQ8→**INT 10h**。`DH=08/DL=10` 与 PC-98 架构**完全自洽，非异常**。

**真正待决的是 OPNA Timer-B 落哪条线**。两处来源矛盾：`F04:28`（QEMU pc98-opna 默认）= **IRQ3（master）**；`G09:49`（DOSBox-X #342 / Blackbird）= **IRQ12（slave）**。以本仓实机 oracle（NP2kai）源码链定论：

| 步骤 | 证据 | 值 |
|---|---|---|
| 默认 `snd86opt` | `pccore.c:654`（`NP2CFG def` 字面量，与 `pccore.h:155` 字段序逐一核对） | **`0x7f`** |
| 派生 IRQ | `board86.c:150` `nIrq = (s&0x10)|((s&0x4)<<5)|((s&0x8)<<3)` | `0x10|0x80|0x40 = `**`0xD0`** |
| 索引表 | `opntimer.c:158` `opna->s.irq = s_irqtable[nIrq>>6]`（`nIrq&0x10` 为真时） | `s_irqtable[3]` |
| 表值 | `opntimer.c:13` `s_irqtable[4] = {0x03,0x0d,0x0a,0x0c}` | **`0x0c` = IRQ12** |
| 交叉印证 | `snd86opt&0x01=1` ⇒ I/O base=**0x188** | 与串口 `AUDIO OPNA OK`（引擎于 0x188 探测成功）吻合，反证 `snd86opt=0x7f` |

⇒ **NP2kai 的 86 板 OPNA Timer IRQ = IRQ12（slave）**，IRQ12 = slave IRQ4 ⇒ **向量 INT 14h**、须解除 **slave IMR bit4（`0x10`）**、EOI 需正确级联。

**应对（用户拍板「双线自适应」，IRQ12 优先 / IRQ3 回退）**：`hal_irq.c` 的 `hal_bgm_irq_init()` 改为按 `g_irq_lines[]` 顺序试挂——先 IRQ12（`INT 0x14`/`PIC1_IMR` bit4），若 `0204` 无 PM 向量或 `0205` 失败则回退 IRQ3（`INT 0x0B`/`PIC0_IMR` bit3）；handler 的双发 EOI（slave 先 master 后）对两线**均正确**，故无需按线分支。

## 五 阶段 1：ISR 音泵骨架（`NAIZ_BGM_IRQ` 编译开关，默认关）

**新增文件** `core/plat/hal_irq.c`（`outb/inb/int386` 的新唯一出处，符合 §5.1 HAL 边界）。

### 5.1 初始化 Timer-B（`hal_bgm_irq_init()`）
- `$26` = NB。`tB = 1152·(256−NB)/φM`（φM=8MHz）。取 **NB=200 → 实机 ≈61.9 Hz**（远高于 ≈28Hz 主循环）。（⚠ 2026-10-24 订正：手册系数 1152 配 φM/2 时钟，实机每步 2304 主时钟；初期按 1152@φM 误算成 ≈124 Hz，见 `docs/refdocs/F07_opn_timer_clock_reference.md`。）
- `$27` = LOAD B（D1）+ ENABLE B（D3）（`F04 §4`）。
- `$29` 置 **EN_TB（D1）**（`F04 §5`；默认可能为 1，显式置位无害）。
- **绝不碰 `$2D-$2F` 预分频**（`F04 §8.3` 高危，改则 FM/SSG 全部音高与 Timer 基准同比变化，全程保持默认）。
- 前序必须 `outb(PCM_ID_PORT, 0x01)`（A460 bit0 选 OPNA；bit1=0 不强制 FM 静音）。

### 5.2 挂接 handler
- INT 31h `AX=0205` 设 IRQ 向量的 PM handler 为 32-bit 代码；**（双线：先试 IRQ12/INT 14h，失败回退 IRQ3/INT 0Bh，§4.4）**；
- `AX=0600` 锁 handler 代码段 + 静态数据页（handler 必须常驻、不可换页）；
- 解除该线的屏蔽位（IRQ12 → **slave** IMR bit4（`0x10`）；IRQ3 → **master** IMR bit3（`0x08`）——按实际挂上的线择一，§4.4）。

### 5.3 handler 内（严格有界，无 malloc/fopen）
1. `hal_wallclock_smooth_advance()`；
2. `fmseq_pump(预算 FMSEQ_PUMP_MAX_PER_CALL)`；
3. `hal_pcm_tick()`；
4. 清 OPNA Timer-B 标志：写 `$27` RESET B 位（D5，自清）——`F04 §5.3` 次序未确认，备用 `$110` 读；
5. **双发 EOI**：先 `outb(PIC1_CMD, PIC_EOI)`（slave `0x08/0x20`）再 `outb(PIC0_CMD, PIC_EOI)`（master `0x00/0x20`）（`G09 §3` 硬约束 1；PC-98 级联线归属 IRQ2 vs IRQ7 未定，双发无害覆盖）。

### 5.4 契约变更（163 §五 C2.4）
开关开时：
- `engine_frame_pump()` **移除** `hal_wallclock_smooth_advance()`（所有权移交 ISR）；
- `audio_tick()` **去** fmseq/PCM 泵职责（防双泵）；
- `audio_bgm_start/stop` 加短临界区（`cli`/`sti` 包裹状态位修改）防与 ISR 竞态。

### 5.5 回退路径
- `NAIZ_BGM_IRQ=0`（**默认**）= 现协作路径**逐字节不变**；
- 开关开但 `hal_bgm_irq_init()` 装探针失败 ⇒ 串口告警 + 运行时回落协作路径（`hal_bgm_irq_active()` 返回 0，帧泵照旧）。

## 六 阶段 2：实机验证（用户执行）
- `make -C core EXTRA_DEFS=-DNAIZ_IRQ_PROBE=1` → `build`+`make` → `test --serial`，回报 `[DPMP]` 行；**（已完成，见 §4.1；读数经 §4.2 调研订正、§4.3 修探针重跑取得清洁读数：`flags=1` 证实 32-bit host、`pic=08/10` 证实 master/slave 基向量；IRQ 线经 §4.4 定为 IRQ12（slave）+ IRQ3 回退）**
- 阶段 1 完成后 `-DNAIZ_BGM_IRQ=1` 构建 → 实机听感 + 串口观察（是否卡死／EOI 正确／与鼠标 IRQ13 共存）。**（阶段 0 已通过；风险已降至「既有 stub 链可否定全」，可进入实机启用验证；预期串口见 `BGM IRQ: Timer-B installed (… IRQ12 (slave))`）**

## 七 验证与防复发

| 项 | 手段 |
|---|---|
| 编译 | `make -C core` 0 诊断（`core/*.err` 空）；`make -C core EXTRA_DEFS=-DNAIZ_BGM_IRQ=1` 与 `-DNAIZ_IRQ_PROBE=1` 各 0 诊断；默认构建（两开关皆 0）行为与 0.3.049 逐字节等同 |
| 守卫 | `test_frame_pump.py` 7 条（`test_bgm_irq_is_gated_and_defaults_off`／`test_frame_pump_yields_clock_and_audio_to_the_isr`／`test_decode_pump_yields_pump_but_keeps_anim_pacing`／`test_isr_sequence_is_bounded_and_eois_both_pics`／**`test_bgm_irq_is_dual_line_slave_first`**／`test_bgm_state_commit_is_critical_sectioned`／`test_dpmi_probe_is_gated_and_read_only`），删除或改坏即红 |
| 行号 | `test_devdoc_refs.py` audio.c 四条（`g_bgm_on`/`g_snd_on`/`g_vc_on`/`audio_bgm_stop`）+ main.c 三条（`prefs_save`/`LANG] boot`/`cjk_load_for_lang`）随锁块/清理宏位移更新（旧值入 `SUPERSEDED_SHIFTED_LINE_REFS`） |
| 文档 | `docs/B90` 补 `hal_dpmi_probe_run`/`hal_bgm_irq_init/active/shutdown`；`docs/B91 §2.2.1` 新增诊断编译开关表 |
| 实机 | §六 |

**落地要点（阶段 1 实现，与 §五 逐条对照）**：
- `hal_irq.c` 为 `outb/inb/int386` 的新唯一出处（HAL 边界）；handler `__interrupt __far` 严格有界、无 `malloc`/`fopen`、**不含 `$2D-$2F`**；
- §5.4 契约落地方式：`engine_frame_pump()`/`frame_decode_pump()` 在 `hal_bgm_irq_active()` 为真时**跳过** `hal_wallclock_smooth_advance()` 与 `audio_tick()`（防双泵/双步进）——比「无条件从 audio_tick 内摘除泵职责」更内聚：协作路径下 `audio_tick()` 仍是完整泵，语义零分裂；
- `audio_bgm_start/stop` 的状态提交窗以 `bgm_irq_lock()/unlock()`（`_disable/_enable`）包裹，防 ISR 在半换表时入内；`NAIZ_BGM_IRQ=0` 时该对被 `#define` 折叠为空，产品构建逐字节不变；
- `ENGINE_EXIT` 加 `hal_bgm_irq_shutdown()`（`#if NAIZ_BGM_IRQ`），退出前停表 + 重屏蔽**实际挂上的那条** IRQ 线（§4.4 双线）。

## 八 边界与不做的事
- **不碰 GDC vsync IRQ2**（用户已选 Timer-B）；
- **不碰 `$2D-$2F` 预分频**；
- **不改 vclock 本体**（方案 B 保留为回退）；
- **阶段 0 取证通过（§4.3/§4.4）：可启用 `NAIZ_BGM_IRQ=1` 上实机**——`flags=1`（32-bit host）+ `pic=08/10`（master/slave 基向量）+ `cfB/cfA=0`（`0204` 成功）三项均正；`lock_ok=0` 在无 VM 宿主下不构成阻塞。OPNA Timer-B 线归属经 §4.4 定为 **IRQ12（slave, INT 14h）**（本 oracle），实现取 **IRQ12 优先 / IRQ3 回退**。方案 B（vclock 有界相位追赶）保留为**回退**；
- NP2kai 自身 VRAM/GDC 慢速（引擎管不着的宿主开销）若仍为主要成分，引擎侧中断消的是「引擎 pass 稀疏」分量。

## 九 来源清单

| 来源 | 用途 |
|---|---|
| 本仓 `docs/refdocs/F04_opna_timer_a_b_specs.md` | Timer-B 公式、`$27`/`$29` 位域、QEMU IRQ3 事实（**候选线之一**） |
| 本仓 `docs/refdocs/G08_dos4gw_interrupt_and_pit.md` | DPMI 中断 API、锁页、bi-modal handler |
| 本仓 `docs/refdocs/G09_timing_vsync_audio_engineering.md §3` | 级联 IRQ ACK 硬约束；**IRQ12（slave）事实**（`G09:49`） |
| 本仓 `docs/refdocs/B01_memory_map.md:104-113` | IRQ 分配表：master IRQ0→INT 08h、slave IRQ8→INT 10h（**`DL=0x10` 非异常的依据**、IRQ12→INT 14h） |
| NP2kai `sound/opntimer.c`（`s_irqtable`）/ `sound/board86.c`（`nIrq`）/ `pccore.c`（`snd86opt=0x7f` 默认） | **IRQ12 定论的源码链**（§4.4） |
| 本仓 `docs/refdocs/F03_opna_fm_and_bgm_routes.md` | `$110` status（IRQ RESET） |
| 本仓 `docs/refdocs/C01_display_system.md` / `G01:78-87` | PIC 端口、向量基 |
| 本仓 `devdocs/163` / `134` / `133` / `131` | 症状定性、C2 总纲、方案 C 蓝本 |
| `delorie.com/djgpp/doc/dpmi/api/310400.html`（INT 31h `0400`） | DPMI 版本/32-bit 位（**BX bit0**）/CL=CPU 类型/DH-DL=PIC 基向量（§4.2 订正依据） |
| Open Watcom `dos4gwqa.gml`（DOS/4GW FAQ，Tenberry） | auto-passup `8–2Eh` 单 handler 便捷路（`_dos_setvect`）、`0205` 高效路、锁页硬约束（§4.2） |
| 本仓部署树 HDI `AUTOEXEC.BAT`/`CONFIG.SYS` | **未设 `DOS4GVM`** + 用 VEM486 ⇒ 无 VM（§4.2 `lock_ok` 判据） |
| Open Watcom `int386` + DPMI INT 31h 公开 API | C2 向量挂接/锁页（**工具链等价物未证实，故阶段 0 先自检**） |
