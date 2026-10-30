# devdoc 178：Naiz 部署链开源化规划

**日期**：2026-10-27（2026-10-28 核对更新：Watcom 构建点定位、参考项目链接实测、风险表补充）
**状态**：规划阶段，未开始代码实施
**与 devdoc 177 关系**：devdoc 177 是**引擎内部**时间敏感事务调度重构（Phase 0-6，audio_tick split drain、transition 拆分、preload_queue 等），本规划是**部署工具链层面**的闭源依赖替换。两线完全独立，互不阻塞。
**影响范围**：仅涉及编译链接器 stub（DOS4GW → CauseWay）和部署磁盘镜像内容（FreeDOS98 + CTMOUSE），**零引擎 C 代码改动**。

---

## 一、现状：Naiz 部署链闭源依赖清单

来源：[build_game.py:354](file:///home/edo/naiz/tools/naiz_build/build_game.py#L354) 和 [inject_common.py:39](file:///home/edo/naiz/tools/naiz_img/inject_common.py#L39)。

| # | 闭源文件 | 类型 | 许可/来源 | 作用 | 引擎硬依赖 |
|---|---|---|---|---|---|
| 1 | **DOS4GW.EXE** | DOS extender stub | Tenberry Software，闭源商业软件 | DOS/4GW 保护模式启动 stub，Open Watcom linker 默认嵌入（或外部文件） | ✅ 必须——Naiz 是 32-bit protected mode（`-mcmodel=small` far pointer + DOS/4GW） |
| 2 | **VEM486.EXE** | XMS/EMS/VCPI 内存管理器 | 荻野晃史，Vector Software 免费发布但闭源 | PC-98 专属——识别 PC-98 UMB 布局、提供 VCPI 给 DOS extender 分配扩展内存 | ✅ 必须——CauseWay/DOS/4GW 都通过 VCPI DE01h 申请 32-bit linear memory |
| 3 | **QMOUSE.COM** | 鼠标驱动 | 闭源 | PC-98 鼠标驱动，提供 INT 33h API | ❌ **非必须**——引擎 mouse.c 有三条 fallback 路径（NP2kai 端口 → INT 33h → 8255 PPI 硬件直读），INT 33h 只是为了 Windows 95/98 的 PC-9821 上绝对坐标更方便 |
| 4 | **MS-DOS 5.0 (NEC)** | DOS 内核 | NEC/微软 OEM 闭源 | DOS 内核 | ⚠️ 不是引擎硬依赖，但磁盘镜像基础 |

---

## 二、参考引擎 ADV98 的真相

关键澄清（之前理解有误）：

- ADV98 是 **16-bit real mode 程序**（`ia16-elf-gcc -mcmodel=small -march=v30`）
- 直接调 PC-98 BIOS 中断，**完全不需要 DOS extender**
- 它"用 FreeDOS"指的是基座磁盘，不是程序依赖 VEM486 或 DOS/4GW
- Naiz 是 32-bit protected mode，**必须有 DOS extender + VCPI provider**，这是本规划的正确语境

---

## 三、三个可确定替换的组件

### 3.1 QMOUSE.COM → CTMOUSE.COM ✅ 已完成

**CTMOUSE（CuteMouse）**：FreeDOS 官方鼠标驱动，GPL 开源，纯汇编编写。

**工具链改动**（已落地）：
- [build_game.py:354](file:///home/edo/naiz/tools/naiz_build/build_game.py#L354)：追踪列表 `QMOUSE.COM` → `CTMOUSE.COM`
- [inject_common.py:39](file:///home/edo/naiz/tools/naiz_img/inject_common.py#L39)：AUTOEXEC.BAT 加载行 `QMOUSE -a- -z` → `CTMOUSE.COM`

**PC-98 兼容性评估**：CTMOUSE 是 IBM PC/AT 设计，找 COM 串口 + PS/2 端口，在 PC-98 实机上大概率找不到鼠标硬件。但**完全不影响 Naiz 运行**——mouse.c 有三条自动 fallback 路径：

| 优先级 | 路径 | 依赖 | CTMOUSE 在时 | CTMOUSE 不在时 |
|---|---|---|---|---|
| 1 | NP2kai 系统端口 0x7E0-0x7E3 | 无 | 优先使用，绕开 CTMOUSE | 同左 |
| 2 | INT 33h `mouse_int33_asm(0x0003)` | 提供 INT 33h 的驱动 | CTMOUSE 找不到硬件→返回无效坐标→有效性检查失败→自动关闭 | 不检测 |
| 3 | 8255 PPI 硬件直读（0x7FD9/0x7FDF/0x7FDD） | 无 | **自动 fallback 接管** | 同上 |

**Net 效果**：INT 33h 路径相当于"试一下能不能用，不行就自动关掉"。零风险。

### 3.2 DOS4GW.EXE → CauseWay ✅ 确定可替换

**CauseWay**：Tenberry DOS/4GW 的直接竞争对手，2000 年**完整源码释放到公有领域（Public Domain）**。

| 项 | 详情 |
|---|---|
| 许可 | Public Domain |
| 位置 | Open Watcom 自带，`wlink` 直接支持 |
| 兼容性 | CauseWay User's Guide 明确写："Most applications built for DOS/4GW will run with CauseWay without any changes" |
| 体积 | 内嵌到 EXE 后 ≈ 几 KB stub（DOS4GW.EXE 实测 265,396 字节外部文件，见 B07-参考项目列表） |
| 切换方法 | 改一行 linker 参数：`WLINK system CauseWay` 替代 `WLINK system DOS4GW` |

> ⚠️ 注意：CauseWay 是 **extender stub**，不是 DPMI host。它仍然需要底层内存管理器（VEM486 或 tori emm386）提供 VCPI/raw INT 15h。换 CauseWay **不碰 VEM486**。

**具体改动位置**（已确认，2026-10-28）：
- [core/Makefile:31](file:///home/edo/naiz/core/Makefile#L31)：`BASE = -bt=dos -l=dos4g ...` → 把 `-l=dos4g` 改为 `-l=causeway`。**一行改动覆盖全部目标**——engine.exe / engine_a.exe / diag.exe 共用 BASE。构建链是 [build.sh](file:///home/edo/naiz/core/build.sh) → make → wcl386，wcl386 把 `-l=` 传给 wlink 作 `SYSTEM CAUSEWAY`，不走 `WLINK system DOS4GW` 命令行
- [build_game.py:354](file:///home/edo/naiz/tools/naiz_build/build_game.py#L354)：换完 CauseWay 后，从追踪列表里删掉 `DOS4GW.EXE`（CauseWay 内嵌 EXE，不需要外部文件）
- [inject_common.py:38](file:///home/edo/naiz/tools/naiz_img/inject_common.py#L38)：AUTOEXEC 里 `SET DOS16M=1` 是 DOS/4GW（DOS/16M 系）专用环境变量，CauseWay 下变 no-op——无害但建议顺手删除，避免误导

### 3.3 MS-DOS 5.0 → FreeDOS(98) ✅ 有现成磁盘镜像

**FreeDOS(98)**：tori（retropc.net）基于 FreeDOS 开发的 PC-98 特化分支。

| 项目 | URL | 角色 | 状态 |
|---|---|---|---|
| **lpproj/fdkernel** (nec98test 分支) | `https://github.com/lpproj/fdkernel` | ⭐ 最活跃的合并版：FreeDOS 开发内核 + tori PC-98 成果合体 | 活跃，有预编译二进制发布 |
| **tori 原始 FreeDOS(98)** | `http://retropc.net/tori/freedos/` | 原始 PC-98 特化：kernel 2028/2035a + fdxms + emm386（PC-98 专属） | 停更但有完整二进制 |
| **NP21/W 使用指南** | `https://simk98.github.io/np21w/freedos98.html` | 指向 lpproj bauxite 下载页，有现成 fd98_2hd144 / fd98_hd_250m 镜像 | 直链见第八节 |

---

## 四、VEM486 替代：唯一的不确定项

### 4.1 VEM486 到底干什么

VEM486（作者荻野晃史）是 PC-98 专属的 **XMS + EMS + VCPI 三合一内存管理器**。核心功能：

1. **XMS**：扩展内存分配（INT 2Fh AX=4300h）
2. **UMB**：upper memory block 映射（PC-98 有三个不连续 UMB 区域：`A500-A7FF`、`D100-DFFF`、`E800-F7FF`，完全不同于 IBM PC 的 `C800-EFFF`）
3. **VCPI**：DOS extender（DOS/4GW、CauseWay）通过 VCPI DE01h 申请 32-bit linear memory——**这是 Naiz 作为 32-bit protected mode 程序的生命线**

### 4.2 候选替代

| 优先级 | 候选 | 来源 | PC-98 特化 | VCPI 支持 | 可信度 |
|---|---|---|---|---|---|
| **1（首选）** | **tori emm386** | `http://retropc.net/tori/freedos/`（2005/2/23 版） | ✅ 是 | ⚠️ 未明确标注但 tori 为 PC-98 设计 | 高 |
| **2** | lpproj/fdkernel 合包里的 emm386 | GitHub `lpproj/fdkernel`（nec98test） | ✅ 是 | ⚠️ 需确认 | 高 |
| **3** | JEMM386 | GitHub `Baron-von-Riedesel/Jemm` | ❌ IBM PC 设计 | ✅ 文档明确支持 VCPI | 低（UMB 布局硬编码） |
| **4（降级）** | **维持 VEM486** | Vector Software 免费发布 | ✅ 是 | ✅ 已验证 | 确定（闭源但免费稳定） |

**候选 1 为什么最有希望**：VEM486 之所以能在 PC-98 上工作，就是因为它理解 PC-98 的 UMB 布局。tori 写的 emm386 也是 PC-98 开发者写给 PC-98 用的，**大概率同样理解 PC-98 内存布局**。

### 4.3 为什么 JEMM386 大概率不行

JEMM386 是 IBM PC/AT 设计，硬编码 IBM PC UMB 区域 `C800h-EFFFh`。PC-98 的三个不连续 UMB 区域完全不重叠。虽然 JEMM386 有 `EXCLUDE=` 选项，但 PC-98 UMB 是**三个不连续小块**，JEMM386 可能根本不会扫描这些地址。

### 4.4 VCPI 链路原理

```
┌──────────────────────┐      VCPI DE01h       ┌──────────────────────┐
│ DOS extender         │ ──────────────────────→ │ 内存管理器           │
│ (DOS4GW / CauseWay)  │ ←────────────────────── │ (VEM486 / tori emm)  │
└──────────────────────┘      返回 32-bit       └──────────────────────┘
                               linear memory
                                        │
                                        ↓
                               ┌──────────────────────┐
                               │ 物理扩展内存          │
                               └──────────────────────┘
```

VCPI 是标准协议（EDM2 有完整规范）。任何声称支持 VCPI 的内存管理器理论上都对任何 DOS extender 提供相同服务。但 PC-98 上 page table 设置、物理内存映射可能有微妙差异——**必须实机验证**。

---

## 五、实施规划

### 阶段 1：CauseWay 换 DOS4GW（确定可成，无风险）

| 项 | 内容 |
|---|---|
| **目标** | 替换 DOS4GW.EXE（闭源 265KB stub）→ CauseWay（公有领域，内嵌 EXE） |
| **前置** | 无——和 VEM486/FreeDOS 完全独立 |
| **改动清单** | ① [core/Makefile:31](file:///home/edo/naiz/core/Makefile#L31) `BASE` 里 `-l=dos4g` 改 `-l=causeway`（一行，三个 EXE 目标共用）<br>② [build_game.py:354](file:///home/edo/naiz/tools/naiz_build/build_game.py#L354) 追踪列表删除 `DOS4GW.EXE`<br>③ （可选）[inject_common.py:38](file:///home/edo/naiz/tools/naiz_img/inject_common.py#L38) 删 `SET DOS16M=1`<br>④ `make -C core clean` 后重新编译 |
| **验证步骤** | ① NP2kai 启动 engine.exe，看能否进 bootmenu<br>② 进 demo-a2 场景，听 BGM 是否正常——**必须按 devdoc 176 的 ISR 剖面方法复测**（176 的 FM 静音根因绑定 DOS4GW 中断栈段行为，CauseWay 行为不同，见风险表）<br>③ 触发一次 transition，看画面过渡是否正常<br>④ 跑实机（如果你有） |
| **耗时** | 编译切 stub + 验证 ≈ 1-2 小时 |
| **风险** | 极低——CauseWay User's Guide 有明确兼容声明 |
| **回滚** | [core/Makefile:31](file:///home/edo/naiz/core/Makefile#L31) 改回 `-l=dos4g`，恢复 build_game.py 列表 |

#### 阶段 1 实施注记（2026-10-28）

编译侧四项改动全部落地：① [core/Makefile](file:///home/edo/naiz/core/Makefile) 切 `-l=causeway` 并加 cwstub 缺失防线（wlink 缺 stub 时只报 W1093 警告仍产出 5KB 坏 EXE，故 Makefile 里 `$(error)` 前置硬失败）；② [build_game.py](file:///home/edo/naiz/tools/naiz_build/build_game.py) 追踪列表删 `DOS4GW.EXE`；③ [inject_common.py](file:///home/edo/naiz/tools/naiz_img/inject_common.py) AUTOEXEC 删 `SET DOS16M=1`（36 字节新版，已验证覆盖写入）；④ 重编译通过，ENGINE.EXE 239380 字节、内嵌 47KB CauseWay stub（LE@0xb830）。

**关键发现（阶段 1 验证在商业基座上受阻）**：MS-DOS 5.0A(NEC) + VEM486 1.29 + CauseWay stub 在 NP2kai 上**无法启动**，DOS/4GW 同环境正常。实测矩阵（CWTEST 最小程序注入 demo-a2.hdi 逐一验证）：

| stub 版本 | VEM486 在场 | 无内存管理器 |
|---|---|---|
| stsp v3.60（Devore 2000 原版） | CauseWay error 11 | 非法中断 #6 |
| CW5 v5.0（CauseWay-JR，watcom v4.05 源流） | 非法中断 #6 | — |
| Open Watcom v2 官方 binw/cwstub.exe | CauseWay error 11 | — |

error 11 语义（源码确认）：stub 实模式段 `cwExec`/Load3P 失败——CW 内核只认原生 3P 格式或 MZ+LE 附加数据，wlink `system causeway` 产出的 MZ+LE 在该环境的自举路径不通；CW5 过了格式检查但 32 位初始化触发 #6。另 FreeDOS 邮件列表同款案例（[Bart Oldeman 2004](https://go.mail-archive.com/freedos-devel@lists.sourceforge.net/msg00501.html)）：cwstub 在 EMM386 UMB 下报 "dos mem corrupt" → error 11，UMBPCI 下正常——stub 对 UMB/VCPI 提供者的内存布局敏感。

**结论**：阶段 1 的验证与阶段 2 合并推进——CauseWay 管线按计划绑定 FreeDOS(98) 开源基座验证（stsp 维护的 CauseWay 本就是 PC-98 fdnpkg 生态组件，其目标环境是 FreeDOS kernel 而非 NEC MS-DOS 5.0A）。Makefile 切换保留（构建侧已就绪），商业基座暂保持 DOS4GW 回滚能力：`games/*` 重跑 `makegame.sh` 即恢复 DOS4GW 版引擎（Makefile 改回一行即可）。构建机 stub 部署：cwstub.exe 放 `~/watcom-extras/`（detect_watcom.sh 自动加 PATH），来源三选一已验证均可完成链接（现用 watcom 官方版）。

### 阶段 2：VEM486 替代验证（NP2kai 上低成本试错）

| 项 | 内容 |
|---|---|
| **目标** | 确认 tori emm386 或 lpproj/fdkernel emm386 在 PC-98 上能否提供有效 VCPI |
| **前置** | 无——可以和阶段 1 并行 |
| **准备材料** | ① tori retropc.net/freedos/ 下载 emm386 + fdxms<br>② lpproj/fdkernel 克隆 nec98test 分支拿 kernel + emm386<br>③ NP2kai 安装 |
| **三张 CONFIG.SYS 测试配置** | 见下方 5.2.1 |
| **验证步骤** | 见下方 5.2.2 |
| **耗时** | 做三张软盘镜像 + NP2kai 跑 ≈ 半天 |
| **降级方案** | 全部不行就维持 VEM486 不变 |

#### 5.2.1 三张 CONFIG.SYS 测试配置

```dos
;;; 配置 A：tori FreeDOS(98) kernel + fdxms + emm386（首选测试）
FILES=30
BUFFERS=6,0
DOS=HIGH,UMB
DEVICE=A:\FDXMS.SYS         ; tori 版 XMS
DEVICE=A:\EMM386.EXE +VCPI  ; tori 版 EMS/VCPI（2005/2/23）
SHELL=A:\COMMAND.COM A:\ /P

;;; 配置 B：lpproj/fdkernel kernel + emm386
FILES=30
BUFFERS=6,0
DOS=HIGH,UMB
DEVICE=A:\HIMEMX.EXE        ; ★ 必须用 lpproj 的 PC-98 移植版 himemx.nec v3.34（第八节直链）；IBM 通用版不认 PC-98
DEVICE=A:\EMM386.EXE +VCPI  ; ★ 确切来源是独立 repo lpproj/emm386.nec EMM386(98) v2.26（第八节直链），不是 fdkernel 合包内置
SHELL=A:\COMMAND.COM A:\ /P

;;; 配置 C：FreeDOS 通用 HIMEMX + JEMM386（大概率不行但试一下）
FILES=30
BUFFERS=6,0
DOS=HIGH,UMB
DEVICE=A:\HIMEMX.EXE
DEVICE=A:\JEMM386.EXE +VCPI EXCLUDE=C800-DFFF
; IBM PC 用 C800-DFFF，PC-98 UMB 在 A500-A7FF/D100-DFFF/E800-F7FF
; JEMM386 可能根本不扫描这些地址
SHELL=A:\COMMAND.COM A:\ /P
```

#### 5.2.2 验证步骤（每张配置重复一遍）

| 步骤 | 操作 | 预期通过标志 |
|---|---|---|
| 1 | NP2kai 启动，用 `MEM` 命令看内存 | 显示 XMS + EMS 总量 ≈ 8MB（假设 NP2kai 配了 8MB） |
| 2 | 加载 CauseWay 版 engine.exe | 不 crash，能进 bootmenu |
| 3 | 进 demo-a2 场景 | BGM 播放（FM 合成不依赖 VCPI 但需要 engine 启动） |
| 4 | 触发 image_load | image_load 不 crash（这是 VCPI 内存分配最密集的操作） |
| 5 | 触发 transition | 画面过渡正常 |

**通过标准**：步骤 3 和 4 都过 → 这个内存管理器可以替代 VEM486。

#### 阶段 2 实施注记（2026-10-29，NP2kai + fdhyb_B2 实测矩阵）

三张配置在 lpproj kernel build 2043 DBCS（`FreeDOS(98) kernel - GIT build 2043`）+ FreeCom 0.85a_DBCS XMS_Swap 上实测，测试程序 CWTEST.EXE（wlink `-l=causeway` 内嵌 47KB cwstub 的最小 LE，66,540B）：

| 配置 | EMS/VCPI 提供者 | 结果 |
|---|---|---|
| B2N（HIMEMX 3.34，无 emm386） | 无 | **CW stub 自举成功（raw 路径切 PM），运行时启动后 `PANIC – Unhandled INT 67h`** |
| B2（HIMEMX + emm386.nec 2.26 默认） | EMS+VCPI | stub PM 初始化挂死：DOS 层 `Critical Error: Abort, Retry, Ignore, Fail?` |
| B2E（同上，无 DOS=HIGH） | EMS+VCPI | 同 CE |
| B2 + `FRAME=D000` | — | emm386 报 `selected page frame d000 not available`，自动回落 c000，同 CE |
| B2 + `/VERBOSE` | — | 确认自动选中 `PAGEFRAME c000:0000`（NP2kai C 段无设备映射，SystemMemory 全 'U'） |
| B2 + `NOEMS` | 仅 VCPI | 同 CE |
| B2 + JEMM386 | — | **系统挂死在 BIOS 内存检查**（IBM PC 设计，PC-98 不可用，与 5.2.1 预判一致） |

**关键定位实验**：
- emm386 在场时 CE 菜单按 `I`(Ignore) → `CauseWay error 11 : DOS reported an absent or corrupt file found.`（No:00000000，对应 [api.asm:7883](file:///tmp/cwsrc/causeway/source/all/api.asm#L7883) `@@file_error2`，reloc 号 0）→ **CE 发生在 CW 内核 PM 期读 LE reloc 的 DOS 调用，即 VCPI 路径（[cw32.asm:1640-1727](file:///tmp/cwsrc/causeway/source/all/cw32.asm#L1640-L1727) @@VCPI，DE01h/DE0Ch）挂死**；cw.asm 正式 stub 本身无 INT 67h/VCPI 代码，探测在 CW 内核 ChkVCPI（cw32.asm:4488）
- 对照组：ED.EXE(1.5KB)/MEM.EXE(19KB) 非 causeway 程序在同一 emm386 环境 EXEC 全部正常 → kernel/EXEC/磁盘 I/O 无辜；EMM386 的 `/VERBOSE`、FRAME 自动选择均正常工作，**故障与 frame 位置无关**
- B2N 直跑（无 launcher）同样 `PANIC – Unhandled INT 67h`（栈值 25BA 1EB6 7202 0060 2702 088C 0005 1687 251F 0505 ...）→ panic 与 launcher 无关，是 CW 运行时自身的 EMS 依赖（core 引擎代码不用 EMS，已 grep 确认）
- `PANIC – Unhandled INT 67h` 文本在 stsp causeway 源码中不存在 → 现用 stub 是 Open Watcom 官方 `binw/cwstub.exe` 预编译二进制，与源码版本行为有差

**结论（与阶段 1 矩阵互证）**：CW 对"EMS/VCPI 提供者在场"的 VCPI 自举路径是跨管理器（VEM486 1.29、emm386.nec 2.26）的系统性兼容性深坑；无 host 时 raw 路径反而能完整自举到运行时，只差运行时的 EMS 依赖。**当前最优路线：无 emm386（raw 路径）+ 消除 CW 运行时的 INT 67h 依赖**——两条子路线：① 从 stsp causeway 源码重编 stub/运行时并打补丁（源码在 `/tmp/cwsrc/causeway`，wasm 可编，需确认 raw 路径运行时不再无条件探测 EMS）；② 查 binw/cwstub.exe 的隐藏开关。注意 5.2.2 步骤 3 已明确 FM 合成 BGM 不依赖 VCPI/EMS，raw 路径一旦跑通即可满足 BGM+ISR 冒烟目标。

**launcher（RUNENV）副产品**（/tmp/cw_diag/runenv2.asm，编译产物 RUNENV.EXE 已入盘）：复用自身 PSP env 块改写 MS-DOS 5+ 尾部路径 → 4Ah 缩块 → 4B00h EXEC 的方案已全链验证（ED.EXE/MEM.EXE 作为目标成功执行），实测要点：4Ah 的 ES 必须指向 PSP；int 21h 返回会破坏 DS/ES 需立即恢复；shrink 应缩至自身映像大小（bx=0x180）为子进程让出 ~600KB；EXEC 后 4Dh 取退出码的组合日志例程尚有写出残渣的小 bug（不影响功能）。此 launcher 可作为后续 engine 启动器（自动设置 env 尾部路径）的雏形。

### 阶段 3：完整部署链切换（阶段 2 成功后）

| 层 | 当前闭源 | 替换为 | 状态 |
|---|---|---|---|
| DOS 内核 | MS-DOS 5.0 (NEC) | **FreeDOS(98)**（lpproj/fdkernel nec98test 或 fd98_2hd.img） | 阶段 2 验证 |
| XMS + UMB | VEM486.EXE | **FDXMS.SYS** 或 **HIMEMX.EXE** | 阶段 2 验证 |
| EMS + VCPI | VEM486.EXE | **tori EMM386.EXE** 或 **lpproj EMM386.EXE** | 阶段 2 验证 |
| DOS extender | DOS4GW.EXE | **CauseWay**（内嵌 EXE） | ✅ 阶段 1 完成 |
| 鼠标驱动 | QMOUSE.COM | **CTMOUSE.COM** | ✅ 工具链已改 |
| CONFIG.SYS 注入模板 | `DEVICE=A:\VEM486.EXE /U`（[inject_common.py:30](file:///home/edo/naiz/tools/naiz_img/inject_common.py#L30)） | 按 5.2.1 选定配置整体改写 | 阶段 3 实施 |

**阶段 3 完成后**：Naiz 部署链**零闭源依赖**。

### 阶段间依赖图

```
阶段 1（CauseWay）──→ 无依赖 ──→ 可立即开始
阶段 2（VEM486 替代）──→ 无依赖 ──→ 可与阶段 1 并行
阶段 3（完整切换）──→ 阶段 1 ✅ + 阶段 2 ✅
```

**关键**：阶段 1 和阶段 2 互相独立，可以并行推进。阶段 3 等阶段 2 确认后再做。

---

## 六、与 devdoc 177 的协调

devdoc 177（Naiz Queue）和本规划完全独立：

| 维度 | devdoc 177 | devdoc 178（本规划） |
|---|---|---|
| 层级 | 引擎 C 代码重构 | 部署工具链 + 编译 stub |
| 改动文件 | audio.c、transition.c、image_cache.c 等 | Open Watcom Makefile、build_game.py、inject_common.py |
| 验证方法 | pytest + NP2kai + 实机 hal_logf 探针 | NP2kai CONFIG.SYS + engine.exe 启动测试 |
| 依赖 | devdoc 176 ISR 基础 | 无 |

**执行顺序建议**：

- Phase 0（audio_tick split drain）和阶段 1（CauseWay）是**两条并行线**，可以同一个 session 里跑
- Phase 2（image_cache 扩容）和阶段 2（VEM486 替代验证）也是**两条并行线**
- Phase 3+ 和阶段 3+ 同理

---

## 七、风险汇总

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| CauseWay 切换后某些 OPNA I/O 兼容性问题 | 低 | 阶段 1 回滚 | CauseWay 有明确 DOS/4GW 兼容声明 |
| **CauseWay 中断栈行为与 DOS/4GW 不同**——devdoc 176 的 FM 静音根因绑定 DOS4GW 中断栈段与栈局部指针写入，该前提在 CauseWay 下不成立 | 中 | ISR 路径回归：BGM 再次静音或行为漂移 | 阶段 1 验证步骤②必须含 devdoc 176 的 ISR 剖面复测；异常即回滚 |
| tori emm386 在 PC-98 上没有 VCPI | 中 | 阶段 2 全部失败 | 降级维持 VEM486（闭源但免费稳定） |
| JEMM386 UMB 区域不兼容 | 高（预期） | 阶段 2 配置 C 失败 | 预期内，不影响配置 A/B 测试 |
| FreeDOS(98) kernel 和 tori emm386 组合有冲突 | 低 | 阶段 2 部分配置失败 | 降级维持 VEM486 |
| 阶段 2 全部失败，只能维持 VEM486 | 中 | 完整开源链少一环 | VEM486 在 PC-98 demo 圈广泛流通，闭源但不是专有壁垒 |

**最坏情况**：阶段 2 全部失败，最终部署链是：

```
FreeDOS(98) + VEM486 + CauseWay + CTMOUSE
              ↓ 唯一闭源
           但免费且广泛流通
```

比现状（MS-DOS 5.0 + VEM486 + DOS4GW + QMOUSE）好得多——至少 DOS 内核和 extender stub 开源了。

---

## 八、参考项目下载地址（2026-10-28 实测可达）

### 8.1 DOS 内核与启动镜像

| 项目 | 地址 | 说明 |
|---|---|---|
| lpproj/fdkernel 仓库（nec98test 分支） | https://github.com/lpproj/fdkernel/tree/nec98test | 源码 + 开发主线 |
| lpproj/fdkernel Releases | https://github.com/lpproj/fdkernel/releases | 最新 test-20220120-cherrypick（pre-release） |
| 编译好的内核 bin 包 | https://github.com/lpproj/fdkernel/releases/download/test-20220120-cherrypick/fdkernel_dbcs-20220120-bin.zip | IBMPC + NEC98，FAT16/FAT32 内核同包 |
| 2HD/1.44M 软盘启动镜像 | https://github.com/lpproj/fdkernel/releases/download/test-20220120-cherrypick/fd98_2hd144_20220123.zip | 阶段 2 测试软盘基础 |
| 模拟器用 HDI（250MB） | https://github.com/lpproj/fdkernel/releases/download/test-20220120-cherrypick/fd98_hd_250m_20220123.zip | NP21/W 可直接挂载 |
| lpproj 下载导航页 | https://bauxite.sakura.ne.jp/software/dos/freedos.htm | 上述全部直链 + bauxite 镜像 |
| tori 原始 FreeDOS(98) | http://retropc.net/tori/freedos/ | kernel 2028/2035a、fdxms（2004/9/10）、emm386（2005/2/23），页面内直接下载 |

### 8.2 内存管理器与驱动（阶段 2 材料）

| 组件 | 地址 | 说明 |
|---|---|---|
| HimemX NEC98 移植版 v3.34 | https://github.com/lpproj/himemx.nec/releases/download/v3.34-nec98-20160913/himemx334_nec98_20160913.zip | 配置 B 的 XMS 必须用这个（PC-98 移植版），IBM 通用版不认 PC-98；源码 https://github.com/lpproj/himemx.nec |
| EMM386(98) v2.26 試作 | https://github.com/lpproj/emm386.nec/releases/download/EMM386_v2.26_nec98_20161111wip/emm386_nec98_20161111wip.zip | "lpproj EMM386" 的确切来源是独立 repo lpproj/emm386.nec（2016-11-11 wip）；说明文档 https://github.com/lpproj/emm386.nec/blob/master/doc/emm386/NEC98.txt |
| MEM 1.11p1（PC98/IBM 兼用） | https://github.com/lpproj/mem.nec/releases/download/mem1.11p1-20181113/mem11p1-20181113.zip | 验证步骤 1 用 MEM 命令建议装这个，PC-98 内存布局显示正确 |
| JEMM386 / JEMMEx | https://github.com/Baron-von-Riedesel/Jemm （Releases: https://github.com/Baron-von-Riedesel/Jemm/releases） | 配置 C 对照用，IBM PC 设计；README 明确支持 VCPI；官方推荐 JemmEx（内置 XMS） |

### 8.3 DOS extender 与鼠标驱动

| 组件 | 地址 | 说明 |
|---|---|---|
| CauseWay（构建用） | Open Watcom v2 自带 | `wcl386 -l=causeway` / `wlink SYSTEM CAUSEWAY`，无需下载 |
| CauseWay 源码（Public Domain 参考） | https://github.com/stsp/causeway | v3.60，源自 Open Watcom 源码树；另见 https://github.com/Baron-von-Riedesel/CauseWay （JEMM 作者维护）和 https://github.com/amindlost/cw （v3.52）。Public Domain 确认：Michael Devore 2000-01-09 释放，含二进制与汇编源码 |
| CTMOUSE 源码（GPL v2） | https://github.com/FDOS/mouse | CuteMouse 2.1，纯汇编；官方发布渠道为 FreeDOS 官方仓库（ibiblio，验证当日 503）。本项目二进制已在 tools_commercial/dos_system/ |

### 8.4 验证环境

| 组件 | 地址 | 说明 |
|---|---|---|
| NP21/W 下载页 | https://simk98.github.io/np21w/download.html | 模拟器本体（"なんかくれ"页） |
| FreeDOS(98) in NP21/W 使用指南 | https://simk98.github.io/np21w/freedos98.html | 实操教程，指向 bauxite 下载页 |
