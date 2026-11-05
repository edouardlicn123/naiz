# 191 - CWTEST 第五轮：环境能力实证（PE+分页可用）+ 根因收敛

> 交接文档。上一份：190（版本基线对照）。上游：178（主规划）、185。
> 本轮全部实验均在 2026-11-01 现场执行，命令可复现，产物见 §五。

> **冻结通告（2026-11-02）**：CauseWay 已判死并冻结，§四的 P1/P2 不再执行。
> 本文的实验证据（环境可用、CW 自身映射缺陷）保留；最终结论见
> [refdoc I03 §零](file:///home/edo/naiz/docs/refdocs/I03_CWTEST追凶经验总结-模拟器能力边界与后续方针.md)。

---

## 一、目标与判据（继承 190，不变）

**最终目标不是把 CauseWay 做好，而是尽快得到一个可以继续做 Naiz 游戏引擎的环境。**
有任何一种 extender/加载方式能让 32-bit LE 应用进入 PM、正常读写文件并返回 DOS，环境即视为可用。

本阶段验收判据（step2c）：

1. 屏显 `CWTEST OK`；
2. HDI 根目录生成非零 `CWOK.TXT`；
3. `cfg_min.sys`（无 HIMEMX）与 `cfg_dev.sys`（含 HIMEMX）**双配置都通过**。

---

## 二、本轮实验与结果

| # | 实验 | 配置 | 结果 |
|---|---|---|---|
| E1 | **最小可观测应用**（`app_m.c`，用无缓冲 `write(1,..)` 打点 M0–M3）用 **3.52 存根**拼接 | `cfg_dev` | 屏显 `Invalid Opcode at FFC8 0B36 0207 …` → `STG-3-RET` → `A:\>`；`CW.LOG` **0 字节**；应用一个字节都没写出 |
| E2 | **官方绑定**（`wcl386 -bt=dos -l=causeway` 产出的 `cwtest2.exe`，官方 `cwstub.exe` 47152B） | `cfg_dev` + 自写 `INT67FIX.COM`（INT 67h 返回 AH=84h） | **静默退出**：无任何错误信息、`CW.LOG` 0 字节、直接回 `A:\>` |
| E3 | 3.52 存根 | `cfg_min`（无内存管理器） | 同样 RM `#UD`，但**栈转储与 E1 不同**（`0A6A× 0B36 0206 6742 214F 001B …` vs `FFC8 0B36 0207 E20A 201D …`）⇒ 崩溃位置随内存配置变化，**不是同一条固定"非法指令"** |
| E4 | 3.52 存根 | `HIMEMX + EMM386`（VCPI） | EMM386 报 `no suitable UMB memory block found`，随后 **CWTEST 挂死**（不返回、无输出） |
| E5 | CPU/内存事实 | `CPUID.EXE` / `CPUSTAT.EXE` / `MEM.EXE` 输出到 HDI 日志 | `CPUID` 指令可用，报告 MMX/SSE/TSC/CX8/CMOV/FXSAVE；CR0=`60000010`（实模式）；XMS 14175K 空闲、常规 556K 空闲 |
| E6 | **自写 PM 探针** `pmprobe.asm`（完全不依赖 CauseWay） | `cfg_min` | 串口输出 `R A B C 1 2 D`：**PE+分页开启成功**，且在恒等映射的线性 `0x200000` **写读校验通过** |

补充说明（避免误读日志）：

- `Invalid Opcode at …` 是 FreeDOS(98) 内核实模式 `int 6` 处理器打印的（[entry.asm](file:///home/edo/inuse/kernel_build/nec98/kernel/entry.asm#L276)），后跟 13 个栈字。
- 该栈的第 2 个字在两个配置里恒为 `0x0B36`（内核重定位段），**不是故障 CS:IP**，不能据此定位。
- 官方绑定那次（E2）能静默退出，说明它走到了能自行结束的路径，但同样没有进入/完成应用。

---

## 三、本轮确立的结论

1. **环境不是瓶颈**：np21kai（`pc_model='VX'`）+ PC-98 FreeDOS 下，**保护模式、4KB 分页、恒等映射、映射页读写都可用**（E6 自证，不依赖 CW）。
2. **3.52 不是可用基线**：`cfg_dev` 与 `cfg_min` 都 `#UD`（E1/E3），VCPI 配置直接挂死（E4）。190 §3.2 的修正成立。
3. **官方绑定不是解药**：官方 stub 静默退出（E2），与"拼接方式错误"无关。
4. 三种失败模式（3.60 三重故障复位 / 3.52 实模式 `#UD` / VCPI 挂死 / 官方静默退出）共同指向 **CW 的扩展内存获取与自身映像映射**，而不是 CPU 或分页能力：
   - XMS 分配落在 `0x129000` 起的**低址**（[spec.md](file:///home/edo/文档/Trae-CN/temp_20261031_01/spec.md#L33-L37) 实测序列）；
   - 无内存管理器时 `GetINT15Page` 返回 `0x2A8F8003`（≈682MB，远超实装 15MB）；
   - 前述 scratch 页内容与 `cw32_tr.exe` 偏移 90899/91469 命中 ⇒ 分配页与 CW 自身映像重叠。
5. **上游 CW 源码没有 PC-98 分支**（全库 grep 无 `pc98/9801/nec` 实义命中）⇒ PC-98 适配只能来自 BIOS 服务兼容性 + 我们的补丁。

---

## 四、下一步计划（按顺序）

### P0 环境矩阵再收敛（不改代码，一次运行一项）
- 只换环境变量跑 3.52 存根：`CAUSEWAY=MAXMEM=<n>`、`CAUSEWAY=NOVM`、`CAUSEWAY=NOPASS`。
  - 目的：确认"分配器越界"是否为主因（若 `MAXMEM` 能改变失败模式，即坐实）。
  - 命令：改 `AUTOEXEC.BAT` 加 `SET CAUSEWAY=...`，再 `bash /tmp/cw_base/run_local.sh /tmp/cw_diag/cfg_dev.sys <outdir> 30`。

### P1 决定性修复（优先 `cfg_min`，减少变量）
文件：`/tmp/cwclean3/raw_vcpi.asm`（对应上游 `source/all/raw_vcpi.asm`）

1. `GetINT15Page`（本地 5172–5448，top 计算 5300–5316）：`GIComputeBytes2` 之后按**实装 RAM 上限**钳制 `top`（`0x100000 + 14336K = 0xEF0000`，由 BIOS 计数取），并拒绝 `base >= top`（走已有"无可用内存"分支）。
2. `GetXMSPage`（本地 4795–4951）：拒绝落入 `[0x100000, ImageTop]` 的块；`ImageTop` 用 `_cwRaw` 全局（初值 0 = 不启用），被拒 handle 记入 `XMSList` 以免反复申请同一块。
3. 两处都只在"钳制值/ImageTop 非 0"时生效，保留原行为可回退。

验收：`cfg_min` 一轮（无 HIMEMX）→ 期望不再 `#UD`；再 `cfg_dev` 一轮。

### P2 若 P1 仍失败：走"自写最小 extender"路线（E6 已证明可行）
- 自写 loader：读 MZ `0x3C` 处的 LE → 恒等映射放入低内存 → 反射 `INT 21h` → 退出。
- 先让 `app_m`（写 CWOK.TXT + 打印）跑通，再按引擎实际用到的 `cwapi` 子集逐类补齐。
- 该路线与 CW 源码无关，风险可控；引擎侧只需保持 `-bt=dos` 编译产物（标准 LE）。

### P3 双配置验收
- `cfg_min.sys` / `cfg_dev.sys` 各一次，要求 `CWTEST OK` + 非零 `CWOK.TXT`。

### P4 收尾
- 复原 HDI `AUTOEXEC.BAT`/清理本轮注入的探针文件（`CPUPROBE.COM`、`INT67FIX.COM`、`CPUID.EXE`、`CPUSTAT.EXE` 及 `*.LOG`）；
- 结论回写 178 / 185 / 190。

---

## 五、本轮产物与可复现命令

| 用途 | 路径 |
|---|---|
| 最小可观测应用源码 | `/home/edo/inuse/cwtest/app_m.c`（`wcl386 -bt=dos -l=causeway -zq -os -s app_m.c -fe=cwtest_m.exe`） |
| 通用拼接（参数化 stub/app/out） | `/tmp/cw_base/splice_m.py` |
| 写 AUTOEXEC.BAT | `/tmp/cw_base/set_autoexec.py "<多行文本>"` |
| 任意文件写入 HDI 根目录 | `/tmp/cw_base/inject_file.py <src> <NAME.EXT>` |
| INT 67h 中和 TSR | `/tmp/cw_base/int67fix.asm` → `INT67FIX.COM`（48B） |
| 自写 PM+分页探针 | `/tmp/cw_base/pmprobe.asm` → `PMPROBE.COM`（串口打点） |
| VCPI 配置 | `/tmp/cw_base/cfg_vcpi.sys`（`HIMEMX + EMM386`） |
| 本轮截图 | `out_M352` `out_OFF` `out_V67` `out_VCPI` `out_MIN352` `out_CPU` `out_PM` `out_PM2` `out_PM3` |
| 串口读取 | `tr -d '\000' < /tmp/cw_diag/ser_capture.log \| od -c \| tail` |
| CPU/内存日志 | HDI 根目录 `PROBE.LOG` `CPUID.LOG` `CPUST.LOG` `MEM.LOG` |

**硬约束**：不改 `/home/edo/inuse/cwbuild`、不改 `/tmp/cw_diag/*.sh|*.py`；可改 `/tmp/cwprobe1`、`/tmp/cwclean3`、`/tmp/cw_base`、`/tmp/cwcmp1`、`/tmp/cwcmp2`。

**当前 HDI 状态（本轮结束时已复原）**：`CWTEST.EXE` = `/tmp/cwclean3/cw32_tr.exe` 干净 v3.60 存根 + `app_le.bin`（123459B）；`AUTOEXEC.BAT` 已回到 `STG-1 → CWTEST.EXE > CW.LOG → STG-3-RET`；根目录仍留有探针文件（`PMPROBE.COM`、`CPUPROBE.COM`、`INT67FIX.COM`、`CPUID.EXE`、`CPUSTAT.EXE`、`PROBE.LOG`、`CPUID.LOG`、`CPUST.LOG`、`MEM.LOG`），不影响 CWTEST 运行，P4 收尾时删除。
