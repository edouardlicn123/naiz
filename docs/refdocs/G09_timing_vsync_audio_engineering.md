# DOS 时钟源候选谱、PC-98 vsync 中断与流式音频工程证据

> **来源**：
> - XtoF（Kris Heidenstrom）*Timing on the PC family under DOS*（https://www.xtof.info/Timing-on-PC-familly-under-DOS.html，Release 3, Feb 1996）——DOS 定时技术全谱
> - Scali's OpenBlog《Putting the things together》（2017-02-24，https://scalibq.wordpress.com/2017/02/24/putting-the-things-together/）——latched-timer 中断驱动 VGM 播放器；《The myth of the vertical retrace interrupt》（2022-12-06）——EGA/VGA vsync IRQ 兼容性调查
> - ReactOS `sdk/include/reactos/drivers/pc98/video.h`——`GDC1_IO_o_VSYNC 0x64 /* CRT interrupt reset */`；DOSBox-X `src/hardware/vga_pc98_gdc.cpp`——写 0x64 置位 vsync 中断（IRQ 2）
> - DOSBox-X issue #342《Blackbird: FM music interrupt problems》（2017-12 开，2019-02 关）——PC-98 级联 IRQ ACK 全记录
> - DCEmulation《Streaming Music Playback CPU Usage》（TapamN，https://dcemulation.org/phpBB/viewtopic.php?t=105823）——分片解码与帧余量测量法
> - Defold 论坛《Sound stutter while loading a collection factory (SOLVED)》/《Sound stops while loading collection proxy (SOLVED)》——预载隐藏解码
> - MIDAS Sound System Programmer's Guide §5.1.2/5.1.3 *MS-DOS timer screen synchronization*（https://files.mpoli.fi/.../midas061.zip/doc/html/prgguide/node21.html，作者 Petteri Kangaslampi, 1997）——屏幕同步定时器
> - Wikipedia《Vertical blank interrupt》——**本轮未获取**（直连与 archive.org 均不可达，仅列 URL）
>
> **许可与转写说明**：QEMU/DOSBox-X/ReactOS 为 GPL/LGPL/BSD 系，本文件**只引用硬件行为事实与端口语义，不复制源码文本**（AGENTS §十）。论坛/博客内容按事实转写并注明作者。XtoF 原文为 Freeware 技术文档，按其技术总结转写。
>
> **配套**：B19 已实测淘汰的时钟源见 `docs/B19-时钟计算经验参考.md` §2（PIT 读回、VSYNC 计帧）；OPNA Timer A/B 见 `F04`；中断挂接 API 见 `G08`；级联 IRQ 陷阱见本文 §3（方案 C 前置检查清单）。

---

## 1. DOS 定时技术全谱（XtoF 转写）与本项目 B19 结论对照

XtoF 将 PC/DOS 定时手段整理为技术-分辨率-适用性谱系：

| 技术 | 分辨率 | XtoF 定位 | 本项目状态 |
|---|---|---|---|
| DOS/BIOS 系统时钟（INT 21h AH=2Ch / tick count） | 55ms/秒级 | 粗粒度、跨函数可用 | **在用但已知塌陷**：NP2kai 下 `DL` 恒 0、秒级成簇（B19 §2.3 / devdoc 107） |
| BIOS tick count 变量 | 54.9ms | 只适合帧级 | — |
| INT 1Ch / INT 8 挂接 | 54.9ms（或改频后） | 简便、绑定 PIT ch0 | 当前帧泵即此模型的协作版 |
| PIT 8253/8254 读回（Refresh Detect, CTC ch1） | 15.0857µs | 短延迟/输入计时 | ❌ **B19 已淘汰**（NP2kai 非单调） |
| Vertical Retrace（**轮询**状态位） | 1/60–1/72 s | 屏幕同步 | ❌ **B19 已淘汰**（NP2kai pass 率仅 ~20.5Hz，帧计数每秒只推 ~342ms） |
| Vertical Retrace **中断模拟**（§10.16，定时器 + safe margin + 三重缓冲） | 帧级 | 无 VBI 硬件的机器上模拟 | 真机可、NP2kai 未测 |
| RTC | 秒级/报警 | 绝对时间戳 | 粗 |
| 加快 CTC ch0 tick | 任意 | 与 §3 PIT 改频同族 | 改频生中断 ≠ 改频读回；NP2kai 投递未测 |

**结论**：B19 淘汰的是「**读** PIT/VSYNC 拿高精时间」；XtoF 谱系中尚未被本项目探索的是「让硬件定时器**产生中断**驱动事件」——即 OPNA Timer A/B（`F04`）或 PC-98 GDC vsync IRQ（§2）。这正是 devdoc 131 把方案 C 价值抬高的原因。

## 2. PC-98 的 vsync 中断（写 0x64 置 IRQ2）

- ReactOS `video.h`（doxygen 第 236 行）：`#define GDC1_IO_o_VSYNC 0x64 /* CRT interrupt reset */`——GDC1 的 vsync 中断复位/触发端口；
- DOSBox-X `vga_pc98_gdc.cpp`（GDC mode 命令 case `0x04`）：「`0x64: set trigger to signal vsync interrupt (IRQ 2)`」——写 0x64 即置 `GDC_vsync_interrupt`，产生 **IRQ2**。

**对比 PC（AT） heritage 的警示**（Scali 2022 调查，非 PC-98）：MDA/CGA 无显示中断；EGA/VGA 有 vsync IRQ 但因（1）克隆芯片组行为不一、（2）IBM VGA 为 PS/2 电平触发设计、ISA 版 IRQ 线未接、（3）走 IRQ2/9 双控制器级联需双重确认——**事实上无人使用**。PC-98 的 GDC vsync 是原生设计（IRQ2），但「NP2kai 是否按帧投递」未实测（devdoc 131 §9.2 列为探针项）。**若做实机探针，先测它比先测 OPNA Timer 便宜。**

## 3. 级联 IRQ ACK 陷阱全记录（DOSBox-X #342）——方案 C 前置检查清单

该 issue 是 PC-98 FM 音乐中断问题的事实库（joncampbell123 逐条定位）。**结论性事实**：

| 事实 | 出处（issue 评论） |
|---|---|
| PC-98 FM 音乐中断在 **IRQ12**；鼠标在 **IRQ13，优先级高于 FM** | 2018-09-07 评论 |
| PC-98 IRQ 为**电平触发**（同 IBM），slave PIC 的 IRQ0-7 经 master IRQ2/IRQ7 级联上报 | 2018-09-07 评论 |
| Blackbird 的 FM ISR 写了「读 master ISR 的 OCW3(0x0B)」却从 **slave PIC 端口**读数 ⇒ 读到 pending 而非 in-service ⇒ 永不 ACK 级联 ⇒ 音乐停 | 2018-09-07 评论（附反汇编） |
| 多游戏（Quarth、Alpha Dain、某 Konami 作）各有变体：先读 ISR 再 ACK slave、mask→处理→ACK→unmask 序列、non-specific EOI | 2018-09-07 评论 |
| DOSBox-X 最终通过「读命令寄存器回 ISR」「级联不置 in-service」两处 PIC 行为修正解决 | 2019-02-02 关闭评论 |

**给本项目方案 C 的硬约束**：
1. handler 必须正确 EOI——**slave 与 master（级联）都要**，且 ACK 前不得做可能遗漏同级中断的长操作；
2. 与鼠标/键盘 IRQ 的优先级关系必须实机验证（鼠标 IRQ13 > FM）；
3. 不要指望「未 ACK 级联也能凑合」——不同游戏在 DOSBox-X 上的表现证明这依赖 PIC 实现细节；
4. 清定时器标志（`$110` IRQ RESET / `$27` RESET 位，`F04` §5）与 PIC EOI 的**次序**需按芯片手册并在 NP2kai 上实测。

## 4. 定时器中断驱动事件线（Scali VGM 播放器）——BGM 事件表的设计参照

Scali 在 8088 上用 **8253 latched 模式**做无 jitter 的绝对时基，把 VGM（寄存器写+延时序列）当中断驱动的「事件线」播放：

- **latched 装载**：不在 handler 里 reset timer，只写新的 countdown ⇒ 时间轴保持绝对，无累积 skew；
- **提前一拍规划**：counter 归零后新值立即装载，故 handler 实际写的是「下下次」的延时（`data_count=0` 拆长延时）；
- **预处理**：把原始流转成 `(delay_in_PIT_ticks, data_runs)` 紧凑格式，handler 只顺序消费；
- **事件重组**（part 2）：延时太短来不及发完的事件，数据并到前一事件、延时累加——等价于硬件 FIFO 的行为，保持绝对时序；
- **磁盘后台流**：中断是「后台」，前台随便跑，只有缓冲欠载才破音。

**映射到本项目**：`audio_tick()` 的 BGM 事件表就是「事件线」；devdoc 131 方案 B/C 的差别只是「谁来推进时间」。Scali 的 lancher 装载/事件重组/拆长延时三件套可直接借鉴进 FM/MIDI 事件表实现。

## 5. 分片解码的工程证据（DCEmulation）——方案 B 的量化依据

TapamN 对 KOS 音频流的研究（Dreamcast 语境，方法学通用）：

- **测量法**：空闲循环自增全局变量，**vblank 归零**，变量峰值 = 本帧空闲余量；
- **症状**：解码器「攒满一大块才解」⇒ 平均 CPU 仅 16%，但**单帧尖峰 60%**；
- **修法**：改成**每帧手动小片回填**，不许缓冲太空 ⇒ **最坏尖峰 60% → 25%**，平均 12%；
- 32kHz 采样率再降最坏尖峰至 22%；
- 结论：要「不卡」必须**把长解码切成帧预算内的小片**，而不是一次做完。

**映射到本项目**：`mag_decode()` 整段纯 CPU 循环（devdoc 131 §2.3）正是「攒满一大块才解」；§5 的测量法（vblank 归零计数器）就是 devdoc 131 §9.2 推荐的卡顿量化手段，可直接照做（NP2kai 下按 guest 侧计数而非 host 时间）。

## 6. 预载隐藏解码（Defold）——方案 D 的用户手册级证据

- **成因**：`collectionfactory.create()` 在资源未预热时**同步**创建/上传 ⇒ 声音卡一两帧（帖子 14271）；
- **修法**：先 `collectionfactory.load()`（异步）再 `create()` ⇒ 卡顿消失；
- **边界**：`async_load` 只把「加载一个资源」做成异步，**不拆分单个大资源**，且 GPU 上传等仍在主线程 ⇒ 大图集仍会 hiccup（帖子 3565）；
- **经验法则**：预载要早（init 期）、要全（大资源集中预热）。

**映射到本项目**：`IMAGE_CACHE_SLOTS=8` LRU 未命中即整段同步解码 ⇒ 方案 D（对白/空闲期预解码下一场景立绘）有直接的生态先例；但要预期「预载本身若仍阻塞则无收益」。

## 7. MIDAS 屏幕同步定时器（1997）——中断派发三回调的先例

MIDAS 的 timer 内置屏幕同步（DOS-only）：`tmrGetScrSync()` 测帧率，`tmrSyncScr(sync, &preVR, &immVR, &inVR)` 注册三个回调：

- `preVR()`：垂直回扫**前**一刻（改显示起始地址/计数）——必须极短；
- `immVR()`：回扫**开始后**（改必须落在回扫内的硬件寄存器）——必须极短；
- `inVR()`：回扫中后段（调色板/小面积更新）——可较长但不得超过一帧，否则影响音乐 tempo。

手册还给出用「帧计数器等待」代替轮询 status 位的范式（防音乐中断夹在轮询中间漏帧）与速度补偿伪码。**这是「一个定时器同时驱动音乐与画面同步」的完整先例**——devdoc 131 方案 C 若要把音泵与帧同步合并，这是最接近的参考架构。

## 8. 对本项目（devdoc 131 方案矩阵）的支撑关系

| devdoc 131 方案 | 本文支撑 | 出处 |
|---|---|---|
| A（节流让出） | 帧余量测量法（改 A 前后对比最坏帧） | §5 |
| B（分片解码） | 尖峰 60%→25% 量化证据 + 切片粒度标定法 | §5 |
| C（中断驱动） | OPNA Timer-B（F04）+ PIT/vsync 造中断 + 级联 ACK 清单 + Scali/Scali 事件线设计 | §1/§2/§3/§4 |
| D（预载隐藏） | Defold 异步预载范式与边界 | §6 |
| E（固定 tick） | XtoF 谱系证明事件必须挂在真实硬件时基上，pass 率绑定无先例支持 | §1 |

## 9. 未获取/未确认项

1. Wikipedia VBI：网络不可达（仅列 URL）；
2. **NP2kai 对 GDC vsync IRQ(0x64) 与 OPNA Timer IRQ 的投递频率/抖动未实测**（§2 的探针是 devdoc 131 §9.2 的前置，预期管理：QEMU/DOSBox-X 已模拟，NP2kai 待证）；
3. XtoF §10.16「模拟垂直回扫中断」的 safe margin 取值依赖具体机器帧时（78xx PC 与 486 不同），未移植评估；
4. MIDAS 面向 VGA/PC，回调语义在 PC-98 GDC 上的对应关系（是否有 preVR/immVR/inVR 三时刻可用的状态位）未调研。

## 附：来源清单

| 来源 | URL | 用途 |
|---|---|---|
| XtoF Timing on PC family under DOS | https://www.xtof.info/Timing-on-PC-familly-under-DOS.html | 时钟源全谱 |
| Scali VGM | https://scalibq.wordpress.com/2017/02/24/putting-the-things-together/ | latched timer 事件线 |
| Scali VBI myth | https://scalibq.wordpress.com/2022/12/06/the-myth-of-the-vertical-retrace-interrupt/ | EGA/VGA vsync IRQ 兼容性警示 |
| ReactOS pc98/video.h | https://doxygen.reactos.org/d6/d70/sdk_2include_2reactos_2drivers_2pc98_2video_8h.html | 0x64 CRT interrupt reset |
| DOSBox-X vga_pc98_gdc.cpp | https://github.com/joncampbell123/dosbox-x | 0x64→IRQ2 事实 |
| DOSBox-X #342 | https://github.com/joncampbell123/dosbox-x/issues/342 | 级联 IRQ ACK 全记录 |
| DCEmulation streaming CPU | https://dcemulation.org/phpBB/viewtopic.php?t=105823 | 分片解码量化 |
| Defold factory stutter | https://forum.defold.com/t/sound-stutter-while-loading-a-collection-factory-solved/14271 | 预载隐藏 |
| Defold proxy stops | https://forum.defold.com/t/sound-stops-while-loading-collection-proxy-solved/3565 | 异步边界 |
| MIDAS prgguide §5.1 | https://files.mpoli.fi/pub/unpacked/skene/music/mutils/midas061.zip/doc/html/prgguide/node21.html | 屏幕同步定时器三回调 |
| Wikipedia VBI | （未获取） | — |
