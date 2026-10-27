# devdoc 178：Naiz 部署链开源化规划

**日期**：2026-10-27
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
| 体积 | 内嵌到 EXE 后 ≈ 几 KB stub（DOS4GW.EXE ≈ 200KB 外部文件） |
| 切换方法 | 改一行 linker 参数：`WLINK system CauseWay` 替代 `WLINK system DOS4GW` |

> ⚠️ 注意：CauseWay 是 **extender stub**，不是 DPMI host。它仍然需要底层内存管理器（VEM486 或 tori emm386）提供 VCPI/raw INT 15h。换 CauseWay **不碰 VEM486**。

**具体改动位置**：
- Open Watcom 构建脚本（待搜索确认具体 Makefile 路径）：找 `WLINK system DOS4GW` 或 `dos4gw.obj` stub 引用
- [build_game.py:354](file:///home/edo/naiz/tools/naiz_build/build_game.py#L354)：换完 CauseWay 后，从追踪列表里删掉 `DOS4GW.EXE`（CauseWay 内嵌 EXE，不需要外部文件）

### 3.3 MS-DOS 5.0 → FreeDOS(98) ✅ 有现成磁盘镜像

**FreeDOS(98)**：tori（retropc.net）基于 FreeDOS 开发的 PC-98 特化分支。

| 项目 | URL | 角色 | 状态 |
|---|---|---|---|
| **lpproj/fdkernel** (nec98test 分支) | `https://github.com/lpproj/fdkernel` | ⭐ 最活跃的合并版：FreeDOS 开发内核 + tori PC-98 成果合体 | 活跃，有预编译二进制发布 |
| **tori 原始 FreeDOS(98)** | `http://retropc.net/tori/freedos/` | 原始 PC-98 特化：kernel 2028/2035a + fdxms + emm386（PC-98 专属） | 停更但有完整二进制 |
| **NP2kai wiki 镜像** | `http://simk98.github.io/np21w/freedos98.html` | 指向 fd98_2hd.img（现成 2HD 软盘镜像） | 有现成磁盘可直接用 |

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
| **目标** | 替换 DOS4GW.EXE（闭源 ~200KB stub）→ CauseWay（公有领域，内嵌 EXE） |
| **前置** | 无——和 VEM486/FreeDOS 完全独立 |
| **改动清单** | ① 搜索 Open Watcom 构建脚本里 `WLINK system DOS4GW` 或 `dos4gw.obj` stub 引用<br>② 改为 `WLINK system CauseWay`（或链接 `causeway.obj` stub）<br>③ 从 build_game.py 追踪列表删除 `DOS4GW.EXE`<br>④ 重新编译 engine.exe |
| **验证步骤** | ① NP2kai 启动 engine.exe，看能否进 bootmenu<br>② 进 demo-a2 场景，听 BGM 是否正常<br>③ 触发一次 transition，看画面过渡是否正常<br>④ 跑实机（如果你有） |
| **耗时** | 编译切 stub + 验证 ≈ 1-2 小时 |
| **风险** | 极低——CauseWay User's Guide 有明确兼容声明 |
| **回滚** | 改回 `WLINK system DOS4GW`，恢复 build_game.py 列表 |

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
DEVICE=A:\HIMEMX.EXE        ; FreeDOS XMS
DEVICE=A:\EMM386.EXE +VCPI  ; lpproj 合包里的 PC-98 特化 EMM386
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

### 阶段 3：完整部署链切换（阶段 2 成功后）

| 层 | 当前闭源 | 替换为 | 状态 |
|---|---|---|---|
| DOS 内核 | MS-DOS 5.0 (NEC) | **FreeDOS(98)**（lpproj/fdkernel nec98test 或 fd98_2hd.img） | 阶段 2 验证 |
| XMS + UMB | VEM486.EXE | **FDXMS.SYS** 或 **HIMEMX.EXE** | 阶段 2 验证 |
| EMS + VCPI | VEM486.EXE | **tori EMM386.EXE** 或 **lpproj EMM386.EXE** | 阶段 2 验证 |
| DOS extender | DOS4GW.EXE | **CauseWay**（内嵌 EXE） | ✅ 阶段 1 完成 |
| 鼠标驱动 | QMOUSE.COM | **CTMOUSE.COM** | ✅ 工具链已改 |

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
