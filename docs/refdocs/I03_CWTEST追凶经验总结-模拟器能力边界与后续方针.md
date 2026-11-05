# I03 - CWTEST 追凶经验总结（devdoc 187→191 及后续）：模拟器能力边界与后续方针

> 类型：参考/经验档案（refdoc），不是开发进度文档。
> 覆盖：devdoc 187（2026-10-29）至 191（2026-11-01），以及其后的 3.73 分析、P1 修复两轮、pmprobe/pmprobe2 反射实验。
> 上游：devdoc 178（部署链开源化主规划）、185（双管线）；逐轮交接细节见 187–191。
> 关键前提：**目标不是把 CauseWay 做到完美，而是尽快得到一个能继续开发 Naiz 引擎的环境。
> 判据：任一 extender/装载方式让 32-bit LE 应用进入 PM、正常读写文件并返回 DOS（`CWTEST OK` + 非零 `CWOK.TXT`，`cfg_min.sys` 与 `cfg_dev.sys` 双配置通过）。**

> **状态：已冻结（2026-11-02 定案）。** CauseWay 不作为交付链，不再修复。
> 本文保留全部追凶证据与工作法；冻结结论、回退顺序与复活门槛见 §零。

---

## 零、冻结通告与最终结论（2026-11-02）

**CauseWay 已冻结：它不是待修缺陷，而是已判死的备选方案。** 本项目的交付链固定为：

| 链 | 打包器 | Extender | 状态 |
|---|---|---|---|
| cmpack（商业） | `tools_commercial` + 商业基座 | DOS/4GW 1.97 | ✅ 可用 |
| openpack（开源） | `tools_open` + FreeDOS(98) | DOS/32A | ✅ 可用（P7 已修复，待布局矩阵验收） |
| CauseWay | — | cwstub 3.52/3.60/官方 | **冻结，非交付链** |

### 0.1 判死依据（四条，全部有实测）

1. **模拟器上全败，且死法不止一种**：3.60 三重故障复位；3.52 实模式 `#UD`（栈转储随内存配置变化）；HIMEMX+EMM386 配置挂死；官方 `cwstub` 静默 `4Ch` 退出。四种死法说明这不是一个可定点修复的 bug。
2. **环境不是瓶颈**：自写 `pmprobe.asm` 在不依赖 CW 的前提下证明 PE + 4KB 分页 + 恒等映射 + 映射页读写全部可用（devdoc 191 E6）。瓶颈在 CW 自身。
3. **P1 修复已被实测否定**：钳制 `GetINT15Page` top（`0xEF0000`）+ 强制 1MB 基址，两轮实测均无改善（§3.4）。不要再在 `raw_vcpi.asm` 上加补丁。
4. **即使 P1 成功，反射层仍是死路**：CW 的 `RawSimulate` 走裸 16 位门，在本环境直接复位；而 DPMI 反射是可用且已被 DOS/32A 验证的。让 CW 活下来必须把反射层换成 DPMI——这不是补丁，是替换核心子系统。叠加"上游全库无 PC-98 分支"与约 6400 行 wasm 移植成本，投入产出不成立。

### 0.2 "是否必须"的准确表述

- **模拟器上：不必须。** 两条交付链都能启动、进游戏并完成 `image_load(13)`。
- **实机上：没有证据表明必须 CW。** 但 FreeDOS(98) + HIMEMX + DOS/32A 的实机组合尚未验证（见 §七"模拟器 ≠ 实机"）。准确说法是"无功能依赖 CW"，不是"DOS/32A 保证覆盖所有实机"。
- **若实机翻车，回退顺序**：DOS/4GW（历史实机方案）→ 自写最小 extender（DPMI 反射）→ CW（最差）。

### 0.3 复活门槛（同时满足才启动）

1. 有明确需求（例如实机上 DOS/4GW 与 DOS/32A 均不可用，或有用户强制要求）；
2. 有长期维护人；
3. 接受"不修 CW 源码"的前提；
4. 路线：G0 环境变量矩阵（`MAXMEM`/`NOVM`/`NOPASS`，零代码）→ 若无效直接判死；G2 自写最小 extender（**反射层直接用 DPMI**，不碰裸 16 位门）→ 只实现引擎用到的子集。

### 0.4 归档与冻结范围

- 历史追查：devdoc 187–191、refdoc I02（均已加冻结横幅，内容保留作证据）。
- 规划作废：devdoc 178 阶段 1（CauseWay 换 DOS/4GW）、devdoc 185 的 causeway chain 选项。
- 当前状态汇总：devdoc 196 §五。

---

## 一、结论摘要（先看这一节）

1. **环境的基础能力可用**：np21kai（IA32 核心、`pc_model='VX'`）+ PC-98 FreeDOS(98) 下，PE 切换、4KB 分页、恒等映射、映射页读写均经自写探针实证（devdoc 191 E6）。
2. **CauseWay 的三个版本都不通，且死法不止一种（四种失败模式）**：3.60 = 保护模式三重故障复位；3.52 = 实模式 `#UD`（由 FreeDOS 内核兜住并返回）；3.52 + EMM386 = 挂死；官方绑定 = 静默 `4Ch` 退出。**"返回 DOS"不等于成功。**
3. **3.73.04tk 升级无收益**：`raw_vcpi.asm`、`memory.asm` 与 3.60 逐字节相同（MD5 一致），新增诊断只在实模式阶段；全库无 PC-98 相关代码。整树替换还需约 6400 行 wasm 移植。
4. **内存分配缺陷已定位但非主因**：PC-98 上 `int 15h AH=88h` 报出荒谬 top（≈682MB）、VDisk 签名误匹配；钳制 top + 强制 1MB 基址两轮实测均无改善。
5. **当前唯一卡点已收敛为"PM→RM 反射"**：自写 `pmprobe2` 在进入 PM、分页、映射全部成功后，**仅执行"远跳进 16 位代码段"就复位**，串口只有 `R A B C 1 2 4 5 6`；去掉 `int` 指令（纯往返）同样复位；把 16 位描述符改成平坦（base=0 / limit=4G / D=0）并重建后，最近串口捕获仍为同一模式（同一时间窗，倾向判定同样失败，建议受控复跑确认）。
6. **因此 CauseWay 判死并冻结（2026-11-02 定案）**：不再以"修 CW 源码"为主线；交付链改用已知可用的 DOS/4GW（cmpack）与 DOS/32A（openpack）。冻结依据、回退顺序与复活门槛见 §零。
7. **引擎已经在跑（决定性事实）**：`core/engine.exe` 本身就是 DOS/4GW 构建（内含 `RATIONAL DOS/4G` 字样），`disks/demo-a2.hdi` 配 VEM486 + DOS4GW.EXE；**2026-11-01 在 np21kai 直接启动到 Naiz Settings 菜单**（截图 `/tmp/cw_base/out_A2DOS4G/f_08.png`）。这说明"把引擎放上去运行"的目标在本机**已经达成**，CW 只是开源交付的备选（已冻结，见 §零），不是开发前置条件。

---

## 二、时间线与实验台账

| 轮次 | 核心动作 | 结果/结论 | 归档 |
|---|---|---|---|
| 187 | 定位 kernel `INT 67h` 陷阱；UNTRAP67 中和；udspy 系列 TSR | kernel 把 0x40–0xFE 向量全指向 PANIC；绕过 67h 后变成"静默 4Ch 退出"；udspy2 链回挂死 | 187 §二、§三 |
| 188 | 排除 kernel EXEC 路径串假设；确认 stub 内部；未压缩 `cw32.exe` 可作补丁载体 | env 段与 `GetEXECName` 算法逐字节吻合；`wcl386` 不认外部 stub，`wlink` stub 子句未解决 | 188 §二–§四 |
| 189 | FAT 获取挂死边界、自建调试内核、探针阶梯 | 调试宏未真正编进；自建内核可行；探针在 CW 内不可信 | 189 §二/§三/§七 |
| 190 | 版本基线对照（3.52 / 近原生 3.60 / 去补丁） | 3.52 是实模式 `#UD`（内核打印 `Invalid Opcode`），不是可用基线；近原生 3.60 同样复位；探针标记不可信 | 190 §2.4、§三 |
| 191 | 最小可观测应用 + 自写 PM 探针 | `pmprobe` 串口 `R A B C 1 2 D`：PM+分页+映射可用；三种 CW 死法无法解释为 CPU/分页缺失 | 191 §二、§三 |
| 后续 A | 下载分析 3.73.04tk | `raw_vcpi.asm`/`memory.asm` 与 3.60 MD5 相同；差异 ≈6400 行，属 wasm 移植成本；无 PC-98 分支 | §三.3 |
| 后续 B | P1：钳制 `GetINT15Page(s)` top + 跳过 VDisk 探测 | `cfg_min` 两轮仍约 2 秒复位、`CW.LOG` 0 字节、串口 0 字节 | §三.4 |
| 后续 C | `pmprobe2`：复刻 CW 的 PM→16 位门→RM→PM 往返 | `R A B C 1 2 4 5 6` 后复位；纯往返（无 `int`）同样；平坦 16 位描述符版同样 | §三.5 |
| **后续 D** | **PEGC 双页翻转 + WCL386 BSS 段限制** | **见下方** | devdoc 200 §6.1/§6.2 |

### 后续 D：PEGC 硬件端口 + WCL386 BSS 段（devdoc 200 附录）

两轮独立发现，均与 NP2kai 模拟器/编译器有关：

**D1 PEGC 双页翻转在 NP2kai 上不可用**（devdoc 200 §6.2）：
- satotomi SL9821 PEGC 技术笔记确实记录 `0x6A=0x68`（2 画面模式）+ `0xA4`（表示面設定）+ `E0004`（bank 选择）。
- video_init 已经用 `outb(0x6A, 0x21)` 开启 PEGC 256 色扩展模式，说明 NP2kai 对这个端口命令的解析是按 PEGC 的。
- 但 **发 `outb(0x6A, 0x68)` 后**，NP2kai 的 PEGC 状态机进入不可预测分支：bank 窗口或 palette 访问路径被破坏，bootmenu logo 白色变黑、剧情场景背景全黑只剩对话框。
- **即使不发 0x68**，只改 `hal_vram_bank_select(bank + 8)` 访问 page 1 bank（bank 8-15），在 NP2kai 上也导致 bootmenu 背景变黑。
- 软件 VSYNC 方案（`vblank_wait()` 一行）可完全替代，且 bootmenu/nb_anim 已经在用。

**D2 WCL386 DOS/4GW 默认 BSS 段上限 64KB**（devdoc 200 §6.1）：
- image.c 加了 3×256=768B static 数组 + 4B valid flag，刚顶破 64KB 上限。
- 段溢出导致 `g_last_pal_valid` 被意外覆盖为 1（BSS 默认全 0，但溢出后其他静态变量可能污染这个位置），且数组内容是垃圾值。
- 恰好 bootmenu image 13 的 palette 部分槽的垃圾值与"全 0"（硬件 palette 默认值）巧合匹配，skip 触发。
- 症状首次启动就出现（不是剧情场景才坏），说明不是外部 `hal_set_palette` 绕过缓存的时序问题。
- 未来规避：改 BSS 段大小（`-bss=128K`）或显式段布局（`.exp` 文件）。

---

## 三、已确立事实（按证据强度排序）

### 3.1 环境层：可用

- **PE + 分页 + 恒等映射可用**（自写探针，串口证据）：`0–16MB` 恒等映射后，在 `0x200000` 写入并读回成功。
- **实模式基础服务可用**：FreeDOS(98) 正常引导、FAT 读写、AUTOEXEC 执行、串口 8251 输出（`out 32h` 控制 / `out 30h` 数据）。
- **CPU 能力齐全**：`CPUID`、MMX/SSE/TSC/CMOV 报告正常；CR0 初始为实模式。
- **XMS 14175K 空闲、常规 556K 空闲**（15MB 配置）。

### 3.2 装载器层：全线失败

| 形态 | 失败模式 | 证据 |
|---|---|---|
| CW 3.60（干净树/近原生/去补丁） | 保护模式三重故障 → POST 复位 | `cfg_dev`/`cfg_min`，无 `STG-3-RET` |
| CW 3.52 原版存根 | 实模式 `#UD` → kernel 打印 `Invalid Opcode at …` → 返回 `A:\>` | 191 E1/E3；190 §3.2 |
| 官方 `cwstub.exe` 绑定 | 静默 `int 21h/4Ch` 退出，`CWOK.TXT` 未生成 | 191 E2 |
| HIMEMX + EMM386（VCPI） | `no suitable UMB memory block found` → 挂死 | 191 E4 |
| 3.73.04tk | 未构建成功（JWasm `@@` 作用域 + 本地 1353 行改造） | 3.73 树分析 |

### 3.3 上游版本的硬事实

- 3.73.04tk（Codeberg `tkchia/causeway`，2026-01-22）与 3.60：`raw_vcpi.asm`（148021B）、`memory.asm`（71741B）**MD5 完全一致**；diff 集中于 `api.asm`、本地 wasm 移植差异、`loadle`、`int21h`、`memory`、`exceptn`，合计约 6400 行。
- 3.73 新增诊断（`IErrorM10 "Unable to locate self"`）位于 `GetSystemFlags` **之前**的实模式阶段，无法解释我们的 PM 三重故障。
- 全库 grep 无 `pc98/9801/nec` 实义命中；唯一 issue（#1，已关闭）是 FreeDOS 1.3 上 `int 21h AH=4B00` 复制环境串 off-by-one。

### 3.4 分配器缺陷（真实存在，但非主因）

- `GIComputeBytes2` 的 top 直接采用 `int 15h AH=88h` 结果，PC-98 上得到 `0x2A8F8003`（≈682MB）；
- VDisk 签名探测命中不存在的 IBM MCA 结构，给出 ≈682MB 基址；
- 无内存管理器时 XMS 分配落在 `0x129000` 起的低址，与 CW 自身映像重叠（scratch 页与 `cw32_tr.exe` 偏移 90899/91469 命中）；
- **但**：钳制 top（`0xEF0000`）+ 强制基址 1MB 后两轮无改善 ⇒ 不能解释三重故障。

### 3.5 PM→RM 反射：本机不可用（当前最强结论）

`pmprobe2` 的构造完全复刻 CW `RawSimulate` 思路：

1. 实模式分配 32KB、4K 对齐，取页目录/页表区；
2. 填 4 个 PDE + 4 个页表，覆盖 0–16MB 恒等映射；
3. 建 256 门 IDT，把 `21h`/`15h` 覆盖为 16 位中断门，基址 = IVT 里的真实 `seg<<4`；
4. 直接 `mov cr0` 进 PE+PG（CS=0x08 平坦 32 位，SS=0x10 平坦 32 位）；
5. 在 32 位侧写一个 16 位跳板（`int n` 或纯 `66 EA` 返回），然后 `push sel(0x28) / push eip / retf` 进入 16 位代码段。

串口结果：

- 第 1 版（描述符 base=`allocseg<<4`、limit 64KB）：`R A B C 1 2 4 5 6` → 复位；
- 去掉 `int` 的纯往返版：同样 `R A B C 1 2 4 5 6` → 复位；
- 平坦 16 位描述符版（base=0、limit=4G、G=1、D=0、ES=0x10 线性写跳板、栈 `tramp_lin+0x7E00`）：源码已改并重建（`PMPROBE2.COM`，20:01），最近串口捕获仍为 `R A B C 1 2 4 5 6`（两轮，20:01 时间窗）⇒ **倾向判定同样失败**；为严谨计，应再跑一次受控实验（确认镜像内 COM 与新建版本一致、AUTOEXEC 指向正确）后才固化为事实。

含义：死点不在 `int` 指令，而在"`retf` 装载 16 位代码段并开始执行"这一动作（或紧随其后的第一条 `66 EA`）。在此机器/核心上，CW 赖以生存的"临时改 IDT 门 + 远跳实模式风格代码"机制走不通。

> 注意证据边界：这仍可能是探针自身的边角 bug（栈帧/描述符/GDT limit），也可能是 np21kai IA32 核心对该组合的实现缺陷。**在拿到正向对照（DOS/4GW）之前，不应把它上升为"真机也不行"的结论。**

---

## 四、失败模式判读矩阵（替代逐点二分）

| 现象 | 判定 | 首要排查 |
|---|---|---|
| POST 画面（`CPU MODE High / MEMORY 640KB +14336KB OK`）反复出现 | 三重故障复位 | PM 初始化（分页/IDT/门/物理页），或反射机制 |
| `STG-3-RET` + `A:\>` + `Invalid Opcode at …` | 实模式 `#UD` 被内核兜住 | 不是"成功"；查 stub 实模式路径 |
| 停在 `STG-1`、串口停写 | 挂死在初始化循环/调用 | IVT/内存管理器/中断 |
| 串口只到固定标记就复位 | 该标记后的第一条特权指令出问题 | 用纯标记阶梯二分（一次一变量） |
| 探针标记不按预期递减/重复 | **探针自身不可信** | 停用该探针，换外部可观测手段 |
| `CW.LOG` 0 字节 + 无 `CWOK.TXT` | 应用根本没执行 | 先查是否进入 PM，再查 API 层 |

---

## 五、工作法与踩坑（可复用清单）

1. **探针不可信原则**：CW 内部加的标记会被 `bp` 破坏/串口干扰（190 §3.3：`0100,0104…` 单调递增且重复两遍）。优先用外部观测：屏幕错误信息、HDI 文件、串口。
2. **一次只改一个变量**：187 实验 2→3 同时改 int6 handler 与内存布局，导致假说分叉。
3. **"返回 DOS" ≠ 成功**：`Invalid Opcode at` 是 FreeDOS 内核 `int 6` 处理器打印的（`KERNEL.SYS` 偏移 0x7d5），随后 `4C7F` 终止。判断成功必须看 `CWTEST OK` + 非零 `CWOK.TXT`。
4. **版本基线先做二进制对照**：`raw_vcpi.asm`/`memory.asm` MD5 相同 ⇒ 上游升级不会改变分配逻辑；先比对再投入移植。
5. **不要混搭源码树**：3.73 按 JWasm 写，`@@` 局部标签作用域不同；本地树已有 1353 行 wasm 改造。整树替换必然失败。
6. **串口是唯一稳定外部通道**：PC-98 8251（`out 32h` 控制、`out 30h` 数据），pty 由 `pty_hold.py` 持有，master 写 `/tmp/cw_diag/ser_capture.log`；读取时 `tr -d '\000'`。
7. **盘面诊断先列目录再推断**：用 FAT 工具读目录/文件内容，再谈行为。
8. **EXE TSR 的 DS=PSP 坑**：入口 DS≠CS，钩中断前必须 `push cs / pop ds`；安装标记（`U6`/`U2`）是标配。
9. **GUI 自动化必须加 `timeout`**：`import -window` 截图可能因 X/xdotool 瞬时故障卡住；先查文件是否存在。
10. **改镜像前先备份**：`AUTOEXEC.BAT`、`CONFIG.SYS`、注入文件都要能在一条命令内复原。
11. **模拟器状态也是变量**：`ExMemory`、CPU 型号、时钟倍率、内存开关、扩展板开关、pty 路径都会改变结果；每次运行记录 toml。
12. **复位与挂死要用不同证据区分**：复位看 POST 画面重现；挂死看串口停写/画面冻结；静默退出看 `MARK-B` 与文件是否存在。

---

## 六、已证伪的假设（不要再重试）

| 假设 | 结论 | 依据 |
|---|---|---|
| kernel EXEC 路径串错误导致 stub 读垃圾文件名 | 已排除 | 188 E1/E2 逐字节吻合 |
| 3.52 是可用基线（能返回 DOS 即成功） | 已推翻 | 190 §3.2，`#UD` 由内核兜住 |
| 补丁/开关造成 3.60 复位 | 已排除 | 190 D4 近原生同样复位 |
| CW 扩展内存分配越界是主因 | 已否定（至少非唯一） | P1 两轮无改善 |
| 3.73 升级可修复 | 已否定 | 分配器 MD5 相同 + 无 PC-98 分支 + 6400 行移植 |
| `-dNOXMS/-dNOCONV` 能绕过 | 已排除 | 190 D3 仍复位 |
| 给 CW 加内部探针做二分 | 已判定不可信 | 190 §3.3 |
| EMM386 2.26 / JEMM386 替代 | 已失败 | 187 §2.3（记录在案） |

---

## 七、模拟器 ≠ 实机：能力边界与差异清单

> 依据：np21/w 官方 FAQ（simk98.github.io/np21w/faq.html）、NP2kai README（github.com/AZO234/NP2kai）、本项目 A01/G07，以及本轮对 `wxnp21kai` 二进制的配置项核对。

### 7.1 模拟器提供的"近似"，不是硬件等价

- NP2kai 的 IA32 核心是**解释器**，不是周期精确/边界条件精确的 486。异常优先级、三重故障时序、段检查细节都可能与真机不同。
- 结论必须标注证据层级：
  - **L0**：np21kai 当前配置下的行为（本项目全部结论都是 L0）；
  - **L1**：另一模拟器（DOSBox-X PC-98、Anex86）复现；
  - **L2**：真机（本项目暂无）。
- L0 失败**不能**直接断言真机失败；L0 成功也**不能**保证真机成功。对外交付前需保留 L2 验收项。

### 7.2 文档明确提到的模拟器差异（对本项目直接相关）

| 项 | 文档说法 | 对本项目的含义 |
|---|---|---|
| CPU 型号 | np21/w 可选 V30 / i486SX / i486DX / Pentium 等；FAQ 建议对齐本家用 **486SX** | `wxnp21kai.toml` 未暴露 CPU 型号键（需在菜单确认）；CPU 型号会改变指令/异常行为 |
| 16bit I/O 寻址 | "Always use 16bit I/O port addressing (PC-9821)" 可开关（`wxnp21kai` 二进制中存在该字符串） | 影响 I/O 端口译码；排查外设/串口异常时应切到与本家一致（FAQ 建议关闭） |
| 时钟倍率 | `clk_mult`/动态调频；过高会让部分软件异常 | 时序敏感实验（BGM/ISR）必须固定时钟 |
| 扩展内存容量 | `ExMemory` 可调；**内存过大反而会让老软件报"内存不足"**，FAQ 建议试 7.6MB | 当前 15MB 是一个应该被当作变量的选择，不是常量 |
| IDE BIOS 位置 | np21/w 把 IDE BIOS 放在 **D8000h**；FAQ 明确要求内存管理器排除 `D8000h–DFFFFh` | `HIMEMX + EMM386` 的 UMB 失败/挂死可能与此有关，而非 CW 的问题 |
| BIOS/核心匹配 | PC-9821 BIOS 必须配 IA32 核心，否则 IMA 失败、键盘死锁 | 已在 A01 §11.1 固化 |
| 打印机/外设 | Bypass(RAW)/PC-PR201/ESC/P 等模式 | 与当前目标无关 |

### 7.3 需要在模拟器上**显式验证**的能力（而不是假定）

1. 保护模式 `D=0` 代码段的装载与执行（当前探针疑似失败点）；
2. `retf`/远跳在 16/32 位段间的切换；
3. 16 位中断门 + 实模式风格 handler 的调用与返回；
4. V86 模式与 16 位门组合（`strings` 中可见 `interrupt: 16bit gate && VM86` 路径，但是否完整未知）；
5. VCPI（EMM386/VEM486）与 DPMI（DPMI32/CWSDPMI）宿主的中介反射；
6. 分页写保护/缺页异常（当前只验证了"恒等映射可读写"，未验证异常路径）。

### 7.4 为什么"用游戏能跑"不能证明反射可用

DOS/4GW 类游戏在 np21kai 上大量可运行，说明**它们走的那条反射路径**可用；但不同 extender 的反射实现不同（DPMI 宿主中介 vs 裸 16 位门）。必须用**同机制的正向对照**，否则会误判。

---

## 八、后续方针（历史记录；自 2026-11-02 起被 §零 取代）

> **本节不再执行。** 其中的 CW 路线（P0 环境矩阵 / P1 补丁 / P2 自写 extender）已冻结；
> 需要重启时只按 §零.3 的复活门槛与 G0→G2 路线，不要照本节原顺序推进。
> 本节保留用于复盘"当时为什么这样判断"。

### 8.1 三条硬原则

1. **先判环境，再判 CW**：任何 CW 结论都必须有一个"已知可用"的对照组同时跑同一配置。
2. **优先宿主中介，少碰裸机制**：DPMI/VCPI 由内存管理器/宿主负责切换，绕开我们对 16 位门语义的依赖。
3. **止损线**：同一假设连续两轮实验无效即换路线；不以"修好 CW"为目标，只以"环境可用"为目标。

### 8.2 阶段化路线（建议顺序）

**S0 校准模拟器（不改任何代码）**
- CPU 型号对齐 486SX；关闭 "16bit I/O port addressing"；禁用 PCI/WAB/NET 扩展板（FAQ 建议）；
- 固定时钟倍率；把 `ExMemory` 从 15MB 改为 **7.6MB** 再跑一次同一探针；
- 若使用 EMM386/HIMEMX，排除 `D8000h–DFFFFh`；
- 目的：排除"模拟器配置造成的假失败"。

**S1 正向对照（决定性，成本最低）——已完成，判定"能跑"**
- 资产：`tools_commercial/dos_system/DOS4GW.EXE`（v4.45，265KB）+ `VEM486.EXE`；
- 实测：`disks/demo-a2.hdi`（CONFIG.SYS = `DEVICE=A:\VEM486.EXE /U` + `DOS=HIGH,UMB`）在 np21kai（`pc_model='VX'`，ExMemory=15）下**启动进入 Naiz Settings 菜单**（截图 `/tmp/cw_base/out_A2DOS4G/f_08.png`，2026-11-01）；
- 判定：
  - **能跑** ⇒ 环境的 PM→RM 反射可用，卡点确属 CW 自身；同时立刻获得"可继续开发引擎"的环境（符合总判据），**CW 降级为开源替代长期项**；
  - 不能跑 ⇒ 环境/镜像配置退化或 np21kai 反射能力缺失，转 S2。

> S1 通过后，主线不再是"让某个 extender 跑通"，而是"让引擎开发循环（编辑→构建→注入→截图回归）顺畅"。详见 §八.5。

**S2 反射机制的替代验证（仅在 S1 失败时）**
- 依次试：DPMI 宿主（DPMI32/CWSDPMI）→ VCPI（EMM386.nec/VEM486，先解决 D8000 冲突与 UMB 配置）→ 自写 extender 的"PM 内直接驱动"方案（成本最高，仅作兜底）；
- 每次只换一个变量，串口 + 屏幕 + 文件三重证据。

**S3 只有在 S1/S2 都失败时，才回到 CW 源码**
- 此时问题已被证明是"环境不提供某能力"，CW 补丁也无解，应转向真机验证或更换模拟器核对（L1）。

### 8.3 交付策略（与 devdoc 178 的双管线对齐）

| 目标 | 载体 | 状态 |
|---|---|---|
| **开发/内侧运行**（当前主线） | DOS/4GW v4.45 + VEM486（商业文件在 `tools_commercial/`，不可再分发） | **已验证**：demo-a2 启动到 Naiz Settings（2026-11-01） |
| **开源交付基线** | CauseWay（开源） | 受阻于反射机制；**不阻塞开发**，降为独立打包任务 |
| 备选开源 extender | DOS/32A（标准 LE，需验证）/ 自写 extender | 仅在发布合规成为真实需求时启动 |
| 备选运行时 | DJGPP/go32 + DPMI32（G07 路径） | 观察，不启用 |

> 一句话：**引擎已经在 DOS/4GW 上跑起来了；CW 从"前置阻塞"降级为"交付阶段的替换项"。**

### 8.4 验收与记录（改为引擎视角）

- 开发期验收：`engine.exe` 能启动到 Naiz Settings/场景，且输入、显示、文件、音频无回归；
- `CWTEST OK` + 非零 `CWOK.TXT` + 双配置：**仅作为将来替换 extender 时的兼容性回归**，不再作为开发前置；
- 每次运行记录：模拟器 toml 快照、镜像名、AUTOEXEC、截图目录；结论标注 L0/L1/L2。

### 8.5 S1 之后的主线：让引擎开发循环顺畅

1. **构建默认回到 DOS/4GW（已完成 2026-11-01）**：`core/Makefile` 新增 `EXTENDER ?= dos4g`（`EXT_LINK = -l=dos4g|-l=causeway`），CauseWay 的 `cwstub.exe` 门禁只在 `EXTENDER=causeway` 时生效。重建产物 `engine.exe` 192772B / `engine_a.exe` 188116B，均含 `RATIONAL DOS/4G`；注入 `demo-a2` 副本后启动到 Naiz 主菜单（截图 `/tmp/cw_base/out_A2NEW/f_10.png`）。
2. **固化"编辑→构建→注入→截图回归"**：沿用 `makegame.sh build/test <game>` 与 `install_env.py test-hdi`；每次改动至少一张菜单/场景截图。
3. **引擎功能冒烟清单**（按实际开发需要排序）：启动到主菜单 → 场景加载（NB/IMAGE.DAT）→ 键盘/鼠标 → 文本与 CJK → 存档读写 → BGM/音效 → 退出回 DOS。
4. **extender 替换独立化**：作为"发布合规/开源化"任务单独立项，验收用 CWTEST + 引擎冒烟双回归；不放在功能开发的关键路径上。
5. **风险登记**：DOS4GW.EXE 不可再分发（开源发布必须替换）；DOS4GW 在真机的兼容性未验证（L2 缺位）；以上风险均不阻塞当前开发。

---

## 九、当前现场状态与收尾事项

- HDI `/tmp/fdhyb_B2R.hdi` 的 `AUTOEXEC.BAT` 当前指向 **`PMPROBE2.COM`**（探针版），原内容备份在 `/tmp/cw_base/autoexec.bak`：
  ```
  @ECHO OFF
  DEL A:\CW.LOG
  ECHO STG-1
  CWTEST.EXE > CW.LOG
  ECHO STG-3-RET
  ```
- 根目录仍留有探针/诊断文件（`PMPROBE.COM`、`PMPROBE2.COM`、`CPUPROBE.COM`、`INT67FIX.COM`、`CPUID.EXE`、`CPUSTAT.EXE`、`PROBE.LOG` 等），不影响启动，但收尾时应删除。
- `/tmp/cwfix1` 是 P1 双补丁树（已构建、已注入并跑过两轮，无改善）；`/tmp/cwclean3` 是干净 3.60 树；`/tmp/cw373` 是 3.73.04tk 分析树（只读）。
- 本轮新增观测：平坦 16 位描述符版探针已重建（20:01），串口日志仍为 `R A B C 1 2 4 5 6` 重复两遍；建议受控复跑后固化为事实。
- **引擎侧已验证**：`disks/demo-a2.hdi`（DOS4GW + VEM486）在 np21kai 启动到 `Naiz Settings`（截图 `/tmp/cw_base/out_A2DOS4G/f_08.png`）；`core/engine.exe` 内含 `RATIONAL DOS/4G` 字样，确认为 DOS/4GW 构建。
- 收尾时可放弃 `/tmp/fdhyb_B2R.hdi` 的探针状态：该盘与引擎运行无关，直接复原 AUTOEXEC 或弃用即可。

---

## 十、证据档案索引

| 类别 | 位置 |
|---|---|
| 逐轮交接 | `devdocs/187`–`191` |
| 自写 PM 探针（第一版） | `/tmp/cw_base/pmprobe.asm` → `PMPROBE.COM` |
| 反射探针（当前版） | `/tmp/cw_base/pmprobe2.asm` → `PMPROBE2.COM` |
| 串口捕获 | `/tmp/cw_diag/ser_capture.log`（`tr -d '\000'` 后 od） |
| 截图 | `/tmp/cw_base/out_M352` `out_OFF` `out_V67` `out_VCPI` `out_MIN352` `out_CPU` `out_PM*` `out_RM1`–`out_RM6` |
| 构建/运行脚本 | `/tmp/cw_diag/build_clean.sh`、`/tmp/cw_base/run_local.sh`、`run_local.sh` 参数 `<cfg> <outdir> [frames]` |
| 内存配置 | `/tmp/cw_diag/cfg_min.sys`（无管理器）、`cfg_dev.sys`（HIMEMX）、`/tmp/cw_base/cfg_vcpi.sys`（HIMEMX+EMM386） |
| 现存可运行资产 | `tools_commercial/dos_system/DOS4GW.EXE`、`VEM486.EXE`；`disks/demo-a2.hdi` |
| 上游分析 | `/tmp/cw373/`（3.73.04tk 解压树） |

---

## 十一、来源

- np21/w 官方 FAQ：https://simk98.github.io/np21w/faq.html
- NP2kai README（AZO234）：https://github.com/AZO234/NP2kai
- np21kai libretro 文档：https://uithub.com/libretro/NP2kai
- 本项目：`docs/A01-NP2kai与镜像工具链.md`、`docs/refdocs/G07_djgpp_pc98_toolchain.md`、`docs/B91-构建环境与参考速查.md`
- VCPI/DPMI 背景：https://handwiki.org/wiki/Extended_Virtual_Control_Program_Interface
- DOS Extender 定义（RBIL）：https://fd.lod.bz/rbil/interrup/dos_extenders/index.html
