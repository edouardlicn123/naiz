# DOS/4GW 下挂中断与 PIT 改频（保护模式中断编程参考）

> **来源**：
> - DJGPP v2 FAQ 18.9 *How to hook hardware interrupts*（https://www.delorie.com/djgpp/v2faq/faq18_9.html）——`_go32_dpmi_*` / `__dpmi_*` 全套 API、锁内存约束、PM/RM 双 handler 挂接顺序
> - Open Watcom C/C++ Programmer's Guide §5.8 *How do you install a bi-modal interrupt handler using DOS/4GW?*（https://open-watcom.github.io/open-watcom-1.9/pguide.html）——bi-modal handler 概念与动机（另见 §10.1 32 位门/16-32 位链；§5.7 Simulate Real-Mode Interrupt DPMI 0x0300）
> - expiredpopsicle《DOS Timer Stuff》（2017-04-13，https://expiredpopsicle.com/articles/2017-04-13-DOS_Timer_Stuff/2017-04-13-DOS_Timer_Stuff.html）——PIT 改频 + INT 8 链接模板、系统时钟狂奔陷阱
> - Wikibooks《NEC PC Programmers Reference — Sound BIOS》（**本轮未获取**：直连与 archive.org 均不可达；devdoc 131 §4.10 的引述「向量写 `0xCEE00`、以 OPN reg A 作节拍器、tick ≥5ms」暂无法独立核实，列入未确认项）
>
> **许可与转写说明**：Open Watcom 文档示例 `BIMODAL.C` 为 Open Watcom 发布物，本文件**只描述做法不复制代码**；expiredpopsicle 的 C 示例同理只述要点（`setvect`/除数/累计 18.2Hz/`timer_clearInterrupt`）。DPMI API 签名是接口事实。本项目引擎为 DOS/4GW 32 位保护模式（`docs/B91` §3），本文 API 均可用，但**具体选型须另行立项**（devdoc 131 方案 C）。
>
> **配套**：PC-98 PIT 端口（0x71/75/77）与计时器硬件见 `docs/refdocs/B02_io_ports.md`；DOS 时钟源候选谱（PIT 读回/VSYNC/RTC/CTC）见 `G09_timing_vsync_audio_engineering.md`；本项目已实测淘汰的时钟源见 `docs/B19-时钟计算经验参考.md` §2。

---

## 1. 为什么需要（devdoc 131 方案 C 的前置知识）

要把 BGM 音泵从「主循环协作轮询」改为「中断驱动」（复刻 PMD，见 `F05`），必须先回答：

1. DOS/4GW 保护模式下怎么挂硬件中断？（DPMI API）
2. handler 要遵守什么纪律？（锁内存、EOI、可重入）
3. 如果不用 OPNA Timer-B 而用 PC-98 PIT 改频造中断，坑在哪？（系统时钟、EOI）

## 2. DPMI API 清单（DJGPP FAQ 18.9 转写）

### 2.1 两套封面的取舍

| API 族 | 性质 | 适用 |
|---|---|---|
| `_go32_dpmi_*` | **智能封装**：自动保存/恢复寄存器、设置 DS/SS/ES 为 GCC 假设；`_go32_dpmi_allocate_iret_wrapper` 生成汇编 IRET 包裹 | handler 写成 **C 函数** 的原型/调试阶段 |
| `__dpmi_*` | DPMI 规范裸封装（如 `__dpmi_get/set_protected_mode_interrupt_vector`、`__dpmi_lock_linear_region`） | handler 写成**汇编**的生产级实现 |

FAQ 原指出：`_go32_*` 系列「不锁 handler 用到的全部代码和数据，内存紧张机器上会崩，不适合 production-quality」；生产级做法是**汇编 handler + `__dpmi_*`**。

### 2.2 保护模式 handler 挂接步骤（`_go32_dpmi_*` 路线）

1. `_go32_dpmi_get_protected_mode_interrupt_vector` 取出旧向量（退出时恢复用）；
2. `_go32_dpmi_allocate_iret_wrapper`：把 handler 地址放进 `_go32_dpmi_seginfo.pm_offset`、`_my_cs()` 放 `pm_selector`，调用后 `pm_offset` 被替换为 wrapper 入口；
3. `_go32_dpmi_set_protected_mode_interrupt_vector` 装上；
4. 若要链到旧 handler：`_go32_dpmi_chain_protected_mode_interrupt_vector`（内部自动分配 wrapper，一次完成「装 + 链」）。

libc 参考补充的纪律（delorie libc_431）：handler 内**禁止 `longjmp` 出去、禁止系统调用（如 `printf`）、禁止 `enable()`/`asm("sti")`**；用完 `_go32_dpmi_free_iret_wrapper` 释放。

### 2.3 实模式 handler（高频中断时才需要）

FAQ：DPMI 宿主总是先把硬件中断送保护模式，未被处理才反射实模式。**中断频率 > ~10kHz 且程序频繁调 DOS/BIOS 时**，反射开销才不可忍，此时补一个实模式 handler（汇编、常规内存内）。挂接顺序：**先 PM 后 RM**（挂 PM 会改写 RM 向量）。常规内存缓冲（`__dpmi_allocate_dos_memory`）多数 DPMI 宿主默认已锁。

### 2.4 锁内存（硬约束）

- handler 触及的**所有**内存（代码/数据/栈）必须锁；C 写 handler **无法可靠锁定自身代码与栈尺寸** ⇒ 官方推荐汇编 handler；
- 锁手段：`__dpmi_lock_linear_region` 逐区域锁；或 `_crt0_startup_flags |= _CRT0_FLAG_LOCK_MEMORY`（只适用于小程序、物理内存充足的机器）；或换**禁用分页的 DPMI 宿主**（CWSDPMI 的 CWSDPR0 / PMODE/DJ）——FAQ 明言后者是调试首批版本的推荐姿势；
- C++ 类成员 handler 另需：隐藏首参、虚表锁、对象本体锁。

### 2.5 与 Watcom/DOS-4GW 的关系

Watcom Programmer's Guide §5.8 的 bi-modal 模型与上表同构：PM handler + RM handler 双挂，中断发生时按当前模式分流，避免 DOS/4GW 在两种模式间反复切换丢数据（示例场景：串口 9600bps 收发，handler 在 RM/PIC 切换窗口丢字节）。§5.7 的 `DPMI 0x0300 Simulate Real-Mode Interrupt` 用于**调用**（非挂接）实模式中断，配合 0x0100 分配实模式内存传递寄存器块。§10.1 补充：21h/35h 在保护模式的中断处理语义、32 位门、16/32 位 handler 链式混挂。

> 本项目若走方案 C：**候选**是汇编 handler + `__dpmi_*` + 锁内存，或先用 C handler + `_go32_dpmi_allocate_iret_wrapper` + CWSDPR0 做 NP2kai 探针（见 `G09` §9 的探针前置条件）。

## 3. PIT 改频造中断（expiredpopsicle 模板要点）

如果（且仅如果）OPNA Timer-B 路线被否，可考虑改写 PC-98 PIT 除数让 INT 8 以更高频触发。模板要点：

1. `_dos_getvect(0x08)` 存旧 handler；`_dos_setvect(0x08, 新handler)`；
2. 除数：`c = 1193181 / 目标频率`（模板取 1000Hz ≈ 每 1ms 一次）；控制字 `0x34`（counter0 / 先低后高双字节 / mode 2 rate generator / 16-bit 二进制），先 `outp(0x43, 0x34)` 再低字节、高字节写 `0x40`；
3. **系统时钟陷阱**：旧 DOS timer handler 每次被调用都推进系统时钟 1/18.2s——直接每次链旧 handler 会让时钟狂奔。**修法**：handler 内计数，累计到 18.2Hz 才调旧 handler（模板按每 10 次调 1 次折算）；
4. **EOI**：未调旧 handler 的那些次必须自己发 EOI（模板用 `timer_clearInterrupt()`），否则 PIC 不再派发同级中断；
5. 退出时恢复除数与旧向量。

**本项目语境下的两条限定**：
- 端口号是 IBM PC 的 `0x40/0x43`；**PC-98 的 PIT 端口是 0x71/0x75/0x77**（`B02` §定时器），控制字/除数语义同族但映射不同——照搬前必须逐端口核对；
- B19 已实测 **PIT 读回值**在 NP2kai 不可用（`nevent_getremain` 驱动、非单调）；但「改频**产生**中断」是另一回事（NP2kai 是否按预期投递未测）。devdoc 131 §4.5 同样的限定仍然有效。

## 4. INT 1Ch 这个「软挂点」

FAQ 与 expiredpopsicle 均提到 `INT 1Ch`（由 timer tick 链出的软中断）：挂它最省事（无需碰 PIC），但频率绑定 PIT ch0（默认 18.2Hz 或改频后的值）⇒ 精度上限 54.9ms，**只适合做帧级粗节拍，不适合 BGM 事件**。对本项目：当前帧泵本质就是「每 pass 一次」的协作版 INT 1Ch——它的局限就是 devdoc 131 §2 记录的局限。

## 5. 未获取/未确认项

1. Wikibooks Sound BIOS（PC-98 OPN 内置音乐 BIOS：向量 `0xCEE00`、reg A 节拍器、tick ≥5ms、应用自建中断）——**本轮网络不可达未能核实**，devdoc 131 §4.10 的引述待独立来源确认；
2. DOS/4GW 下 OPNA IRQ 的向量映射与默认 IRQ 号（QEMU 默认 3，devdoc 131 §4.1 佐证 NP2kai 亦模拟 OPNA 定时器）——**实机/NP2kai 探针未做**；
3. `_go32_dpmi_*` 在本项目实际链接器/wcl386 工具链下是否可直接引用（本项目用 Open Watcom；DJGPP API 属 DJGPP libc，**需 Watcom 侧等价物**——Watcom 用 DPMI 调用或 RMLib，具体等价 API 未调研）。

## 附：来源清单

| 来源 | URL | 用途 |
|---|---|---|
| DJGPP v2 FAQ 18.9 | https://www.delorie.com/djgpp/v2faq/faq18_9.html | DPMI 中断 API/锁内存/双 handler |
| DJGPP libc 参考 `_go32_dpmi_allocate_iret_wrapper` | https://www.delorie.com/djgpp/doc/libc/libc_431.html | wrapper 语义与禁令 |
| Open Watcom C/C++ Programmer's Guide 1.9 | https://open-watcom.github.io/open-watcom-1.9/pguide.html | §5.8 bi-modal、§5.7 DPMI 0x0300、§10.1 |
| expiredpopsicle《DOS Timer Stuff》 | https://expiredpopsicle.com/articles/2017-04-13-DOS_Timer_Stuff/2017-04-13-DOS_Timer_Stuff.html | PIT 改频模板 |
| Wikibooks NEC Sound BIOS | （未获取） | PC-98 OPN BIOS 节拍器 |
| B02 / B19 | 仓库内 | PIT 端口、时钟源实测结论 |
