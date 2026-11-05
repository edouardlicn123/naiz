# 190 - CWTEST 追凶第四轮：版本基线对照（3.60 复位 / 3.52 实模式 #UD）+ 转向"先求可用环境"

> 交接文档。上一份：189-CWTEST追凶第三轮。上游：178（主规划）、185。
> 本文档供下一对话**直接续做**，含全部可复用命令、当前结论与下一步计划。

> **冻结通告（2026-11-02）**：本文的 P0/P1 计划已冻结；P1（钳制 `GetINT15Page` + 强制 1MB 基址）
> 经两轮实测**无改善**，不要重试。CauseWay 不做交付链，最终结论与复活门槛见
> [refdoc I03 §零](file:///home/edo/naiz/docs/refdocs/I03_CWTEST追凶经验总结-模拟器能力边界与后续方针.md)。

---

## 一、总目标与继承指令（更新版）

**最终目标不是"把 CauseWay 做好"，而是尽快得到一个可以继续做 Naiz 游戏引擎的环境。**
因此：能跑通的 extender 版本就用哪个版本；**3.60 若在 np21kai 上不可修，直接改用 3.52 交付**。

本阶段（step2c：CWTEST 冒烟测试）的通过标准仍是：

1. 屏显 `CWTEST OK`；
2. HDI 根目录生成非零 `CWOK.TXT`；
3. `cfg_min.sys`（无 HIMEMX）与 `cfg_dev.sys`（含 HIMEMX）**双配置都通过**。

新增判据（本 session 定）：**只要有一个 extender 存根能让 LE 应用进入并正常读写文件/返回 DOS，环境即视为可用**，不必追究 3.60 的特定初始化路径。

---

## 二、各阶段结果汇总（按时间顺序）

### 2.1 阶段 A：屏显乱码 = 字体 ROM 未加载（已澄清，结论作废）

- 曾判断"屏幕乱码是字体 ROM 未正确加载"。
- 核对 refdoc 后确认：`wxnp21kai -c <toml>` 的 ROM 搜索目录 = 配置文件所在目录；`/tmp/cw_base/font.rom`（md5 `2af6179d…`）与 `~/.config/wxnp21kai/font.rom` 一致，`bios.rom`（md5 `e246140d…`）一致。
- 实拍画面 `CPU MODE High / MEMORY 640KB +14336KB OK`、字形正常 ⇒ **ROM 加载正确，早期"乱码"判读全部作废**。

### 2.2 阶段 B：stub 静默退出与 kernel IVT 陷阱（devdoc 187–189）

- FreeDOS(98) kernel 把 IVT 0x40–0xFE 全指到 PANIC 陷阱，`#UD`/PANIC 均以 `int 21h/4C7Fh` 终止（errorlevel 127）。
- 旧崩溃：CS=084C / IP=012E（线性 0x85EE，stub 代码段内）。
- 试验：UNTRAP67、udspy2（4Ch 记录器）、自建调试内核（`setvec(0x67…)`）——均未取得可用基线；udspy2 挂死在第一个 int21h。
- 结论：退出路径分析与最终故障点无关，转 stub 内部（阶段 C）。

### 2.3 阶段 C：CW 内核诊断构建 + 串口标记（本轮之前的现状）

- 工具链：`wasm` → `wlink` → `resplice.py`（追加 LE 应用）→ `inject_cwtest5.py`（写入 HDI）。
- 常用命令：
  ```bash
  EXTRA_DEFS="-dNOXMS -dNOCONV" bash /tmp/cw_diag/build_clean.sh /tmp/cwprobe1
  bash /tmp/cw_base/run_local.sh /tmp/cw_diag/cfg_dev.sys /tmp/cw_base/out_X 45
  tr -d '\000' < /tmp/cw_diag/ser_capture.log | grep -a -oE '>[0-9A-F]{4}\|'
  ```
- 已确立事实：
  - CPL3 下 CS=0x00A3（GDT idx 0x14，RPL=3）；**CS base 实测 0x0002BAE0**（低内存）；
  - ES limit = 0xFFFFFFFF；H1（临时窗与自身映像重叠）**不成立**；
  - `LinearEntry` 从 1024 起；别名窗 `0xFFC00000 + idx*4 → PT[idx/1024][idx%1024]`；
  - scratch 页物理 0x12B000 前 4 dword 与 `cw32_tr.exe` 偏移 90899/91469 命中 ⇒ XMS 分配把"映像占用区"当空闲页的 H2 方向。
- 探针机制（`xtrace` 打 `>XXXX|` + 看门狗 `ds:[5279]/ds:[0084]`；`pval` 打 `P<tag>:hhhh`，**会破坏 si/dx**）在本轮被判定为**不可信**（见 3.3）。

### 2.4 阶段 D：本轮四次对照实验（决定性）

| # | 二进制 | 配置 | 结果 |
|---|---|---|---|
| D1 | 上游 repo `cw32.asm` 直接替换本地主文件 | — | **组装失败**：`@@p1/@@p0/@@p2…` 标签重复。仓库缺 `raw&vcpi.asm`、`memory.asm`、`decode_c.asm`、`loadle.asm`，且本地文件已改名/改标签，**不能混搭** |
| D2 | **原版 3.52 存根** `source/all/cw352.exe` + 我们的 LE 应用 | `cfg_dev` | **进入保护模式并正常返回 DOS**：屏显 `Invalid Opcode at FFC8 0B36 0207 E20A 201D 2000 2000 …`，随后 `STG-3-RET` + `A:\>` 提示符 |
| D3 | 本地干净树**去掉** `-dNOXMS/-dNOCONV`（走 HIMEMX/XMS） | `cfg_dev` | **复位**（POST：`CPU MODE High / MEMORY 640KB +14336KB OK`） |
| D4 | **近乎原生 v3.60**（`cw32.asm.bak_cwopen`，仅 4 处 PC-98 补丁） | `cfg_dev` | **复位** |

**结论**：复位不是补丁/开关造成的。近乎没有补丁的 v3.60 同样复位；原版 3.52 在同一机器、同一配置下能建 IDT、能进 PM、能被异常处理器接住并优雅返回。
⇒ **np21kai + PC-98 FreeDOS 的 PM/分页/IDT 环境是可用的；卡点是 v3.60 的初始化流程与该环境不兼容。**

### 2.5 阶段 C 的探针链（供对照，但标记值已判定不可信）

- `cfg_dev` + 探针树：
  `0E01 0E02 0F08 0F09 0F0A 0F0C 0F0B 0F00 0F10 0F14 0F15 0F16 0F19 C011 FFFF FFFF C010 BAE0 0002 C012 C016 C017 C018 0F17 0F18 0F11 C01B 0F12 0F13 0F20 0F21 0F22 0F23 0F24 0F25 0F27 0F28` 之后进入 256 门循环，机器停在 `STG-1` 不再前进。
- `cfg_min` + 同一探针树：只循环 `0E01 0E02 0F08 0F09 0F0A 0F0C 0F0B 0F00` 共 8 轮后**复位**。
- 干净树（无探针）：一进 `CWTEST.EXE` 即**复位**，无 `STG-3-RET`。

---

## 三、本轮确立的三条硬结论

### 3.1 判读矩阵（替代"逐点二分"）

| 现象 | 判定 |
|---|---|
| `STG-3-RET` + `A:\>` + `Invalid Opcode at …` | extender 正常完成 PM 初始化，故障在**应用侧或 API 侧** |
| POST 画面（`CPU MODE High / MEMORY …`）反复出现 | 三重故障复位，故障在 **init 期（分页/IDT/门/物理页）** |
| 停在 `STG-1` 不再变化、串口停写 | 挂死在 init 期某个循环/调用 |
| 探针标记 `bp` 不按预期递减（见 3.3） | **探针自身不可信**，不要据此推理 |

### 3.2 3.52 ≠ 可用基线（本条已修正）

**修正记录**：最初判断"3.52 可用"，是因为它报错后能返回 DOS。核对字符串来源后推翻：

- `Invalid Opcode at ` 这段文字**不在 `cw352.exe` 里，也不在应用里**，而是**在 FreeDOS 内核 `KERNEL.SYS` 偏移 0x7d5–0x7de**（`'Invalid' 0x7d5 / 'Opcode' 0x7de`，紧邻 `PANI…C - Unha…ndle…INT`）。
- 因此它是**实模式 `#UD`**被内核 int6/PANIC 处理器打印的，随后以 `int 21h/4C7Fh` 结束进程——即 **3.52 存根同样崩了，只是崩在实模式、由内核兜住，而不是保护模式三重故障复位**。
- 两者失败模式不同（3.60 = PM 三重故障复位；3.52 = RM `#UD` + 内核转储），但**都是"没能跑起来"**。

⇒ 原版 3.52 证明了"内核/PM 基础链路可走到某一步"，**不能证明 3.52 是可交付基线**。

### 3.3 探针不可信（重要）

门循环 `test bp,3 / push bp` 应只打印 4 次（`0100,00FC,0080,0040`），实测打出 **约 1015 个单调 +4 的值**（`0100,0104,…,10DC`，且正好重复 2 遍，`00FC` 从不出现）。
逐字节反汇编确认二进制编码正确（`f7 c5 03 00` / `55` / `4d` / `75 e8`）⇒ `bp` 在运行中被破坏，或串口输出干扰了执行。
**结论：不要再给 cw32 加标记做二分，改用外部可观测手段（屏幕错误信息、HDI 文件、模拟器调试）。**

---

## 四、下一步计划（按顺序执行）

### P0（已发现的新线索，优先核实）
1. **完整上游 v3.60 源码已在本机**：`/home/edo/inuse/cwsrc/causeway/source/all/`（含 `memory.asm`、`decode_c.asm`、`loadle.asm`、`raw_vcpi.asm` 等，`cw32.asm` 版本串为 `3.60`）。之前 D1 失败只因 `/tmp/cwupstream` 缺文件——**真正的 pristine v3.60 基线可以构建**。
2. **正规绑定工具可用**：HDI 根目录已有 `CWC.EXE`（55625B，CauseWay EXE maker）；`resplice.py` 只是它的手写替代。若怀疑拼接方式错误（`cwc /m2 /l85` 还会改写头部字段），可在 FreeDOS 里直接用 `CWC.EXE` 生成 CWTEST。

### P1（决定性判别）：确认故障在"环境"还是"应用/拼接"
1. 用 OpenWatcom 生成**最小 LE 应用**（只写一行字 + 写一个文件，不调用任何 CW API）；
2. 分别用 3.52 存根与本地 v3.60 存根拼接（必要时用 HDI 内的 `CWC.EXE` 正规绑定）；
3. 各跑一次 `cfg_dev`：
   - 最小应用也复位/`#UD` ⇒ 故障在**extender/拼接**，与引擎 API 无关；
   - 最小应用正常 ⇒ 故障在 **cwapi 调用层**，可从 API 收敛。

### P2（按 P1 结果分叉）
- **若故障在 extender**：改用 pristine v3.60（`/home/edo/inuse/cwsrc/causeway/source/all/`）逐项加回本地补丁，或用 `CWC.EXE` 正规绑定；仍不行则评估换 extender（PMODE/W、DOS/32A 均吃标准 LE），把"引擎能跑"作为第一目标。
- **若故障在 API 层**：用最小 API 逐类调用（文件/内存/控制台）定位到具体 cwapi 服务。

### P3：双配置验收
- `cfg_min.sys`（无 HIMEMX）与 `cfg_dev.sys` 各跑一次，要求 `CWTEST OK` + 非零 `CWOK.TXT`。

### P4：收尾
- HDI 内复原 `CLIDOS.COM`、清理探针；结论回写 178/185/本文件。

---

## 五、路径与产物清单

| 用途 | 路径 |
|---|---|
| 干净树（无探针，含 PC-98 补丁，当前注入的是它） | `/tmp/cwclean3`（`cw32.asm`, `cw32_tr.exe`） |
| 探针树 | `/tmp/cwprobe1`（`cw32.asm` 191371B） |
| 近原生 v3.60 备份 | `/tmp/cwprobe1/cw32.asm.bak_cwopen`（5218 行，4 处 PC-98 补丁） |
| 原版 3.52 存根 | `/tmp/cwupstream_src/cw352.exe`（58273B） |
| 上游 v3.60 源码（不完整） | `/tmp/cwupstream/`、`/tmp/cwupstream_src/` |
| 镜像与运行 | `/tmp/fdhyb_B2R.hdi`、`/tmp/cw_base/np2_15m.toml`、`bash /tmp/cw_base/run_local.sh <cfg> <outdir> <frames>` |
| 本轮截图 | `/tmp/cw_base/out_A_min`、`out_A_dev`、`out_B_clean`、`out_C_352`、`out_D_xms`、`out_E_base` |
| 规格与任务 | `spec.md`、`tasks.md`（本工作目录；T1–T6 均未勾选，目标版本需按"3.52 可用"更新） |

**硬约束**：不改 `/home/edo/inuse/cwbuild`，不改 `/tmp/cw_diag/*.sh|*.py`；只改 `/tmp/cwprobe1`、`/tmp/cw_base`、`/tmp/cwclean3`、`/tmp/cwcmp1`、`/tmp/cwcmp2`。
