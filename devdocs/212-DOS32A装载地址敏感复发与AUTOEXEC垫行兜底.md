# 212 — DOS/32A 装载地址敏感复发与 AUTOEXEC 垫行兜底（0.4.034）

> **状态**: 已完结（短期兜底 A 已落地并实机验证；机理深挖 C 见 §九，未完成）
> **版本**: 0.4.034（`projects/demo-a2/config.toml`）
> **关联**: `CHANGELOG.md` c112、devdocs/210 §十一、`tools/naiz_img/inject_common.py` `generate_autoexec()`
> **结论类型**: 现象级兜底（非根因修复）——根因仍是 DOS/32A v9.12 加载器对 `ENGINE.EXE` 装载地址的敏感性

## 一、一句话结论

0.4.033 的 `SET DOS16M=1` 只在 245232 B 那版 `-os` 镜像上把装载地址推到了好区；
镜像变成 245500 B 后地址又落回坏区，**fatal 4005 复发**。本轮在生产 `AUTOEXEC.BAT` 里固定增加
一行无害的 `REM naiz ae pad`，把 openpack 链的装载地址再次平移出坏区，实机启动恢复正常。

## 二、症状与现场（2026-11-16）

用户实机截图（NP2kai）：

```
CuteMouse v2.1 beta4 [FreeDOS]
Error: device not found
DOS/32A warning (9004): mouse initialization failed
DOS/32A fatal (4005): unrecognized fixup data in application exec "A:\*ENGINE.EXE"
A:\>
```

现场事实：

| 项 | 值 |
|---|---|
| `games/demo-a2/engine.exe` | 245500 B，11-16 11:46，`-os` 全链 |
| HDI 内 `ENGINE.EXE` | 245500 B（与部署件一致） |
| HDI 内 `AUTOEXEC.BAT` | 已含 `SET DOS16M=1`（0.4.033 修复已生效） |
| `makegame.sh test --serial` | **串口 0 字节** → 引擎代码一行未执行 |

**判据**：加载期失败的唯一稳定信号是「串口日志为空」。截图里的
`DOS/32A warning (9004): mouse initialization failed` 与 `CuteMouse ... device not found`
都是既有噪声（PC-98 上 CuteMouse 找不到 PS/2 设备；引擎自己用 8255 端口初始化鼠标），
**不是** 4005 的原因。

## 三、复现与判定矩阵

同一枚 245500 B 引擎，只改注入路径的 AUTOEXEC 垫行数：

| `NAIZ_AE_PAD` | AUTOEXEC 实际行 | 串口字节 | 结果 |
|---|---|---|---|
| 0（默认） | 无垫行 | 0 | **fatal 4005** |
| 1 | `REM .` | 1657 | 启动，`aiz engine` |
| 2 | `REM ..` | 1657 | 启动 |
| 3 | `REM ...` | 1659 | 启动 |
| 4 | `REM ....` | 1657 | 启动 |

结论：**同一镜像内容的 4005 与否只由装载地址决定**，与 fixup 记录内容无关（与 devdoc 210 §十一.5
的结论一致）。

**测量前提**：本矩阵在 0.4.034 落地**之前**的代码上测得（PAD=0 = AUTOEXEC 里没有任何垫行）。
当前代码 openpack 链无条件写 `REM naiz ae pad`，所以 `NAIZ_AE_PAD=0` 实际已带 17 B 垫行；
要复现原始 4005 必须**先手工删掉生产垫行**，否则 §八.2 的 `0..4` 扫描只是在 17 B 基线上叠加。

## 四、为什么 0.4.033 的修复不够

0.4.033 的判断是「openpack 链缺 `SET DOS16M=1` → 地址恰落在坏区」，据此把该行改为两条链无条件写入。
那条结论在 **245232 B 镜像**上成立；但：

- `SET DOS16M=1` 本身不被 DOS/32A 读取（v9.12 源码零引用），它只是把 AUTOEXEC/环境块
  撑大若干字节 → 平移装载地址；
- 装载地址 = 可用内存顶端 − 镜像大小，**镜像大小本身就是地址公式里的主变量**；
- 11-16 的构建（vclock 等改动）把镜像从 245232 变成 245500（+268 B），地址再度落入坏区。

所以「写死某一行」并不能保证长期有效，**必须每次构建后用开机冒烟验证**——这正是本轮复发的直接教训。

## 五、机理现状（已知 / 未知）

**已知**

- 4005 的全部触发点在 DOS/32A v9.12 `apply_fixups` 内（devdoc 210 §11.1）；`_err_code` 在循环顶部
  预置 4005，任何 `file_errorm` 都按 4005 报出。
- 逐检查仿真（`tmp_le/sim_loader.py`）显示：`-os` / `-od` / `animatest` 三份镜像**都不含**任何
  检查级触发条件（无源列表位、无对象号越界、无非法类型）→ 排除「某条记录内容非法」。
  （注：`tmp_le/sim_loader.py` 与 `tmp_le/dos32a-git/` 已随 c5187e6「出库 AI 工具垃圾」清理，
  本节是当时的实测结论，当前仓库内不可复跑；复核需重新取 v9.12 源码并重建仿真脚本。）
- 同内容、只改装载地址即可在 4005 / 正常启动之间切换（§三矩阵，PAD 0 vs 1–4）。

**未知（C 项）**

- 装载地址具体如何影响 `apply_fixups`：210 §十一.5 的线索是 `gs:[esi]` 段界限/缓冲区布局；
  尚未做地址级采样（需要能读出实际装载段值的探针），也未定位坏区边界（是单点、区间，还是
  与 16 字节段对齐相关）。

## 六、方案 A（已落地）：生产 AUTOEXEC 固定垫行

位置：`tools/naiz_img/inject_common.py` `generate_autoexec()`，在 `SET DOS16M=1` 之后、
`NAIZ_AE_PAD` 诊断段之前：

```python
if _is_open_pack():
    content += b'REM naiz ae pad\r\n'
```

- 只作用于 openpack（DOS/32A）链：`_is_open_pack()` = `NAIZ_PACK=openpack` 或
  `NAIZ_EXTENDER=dos32a`；dos4g 链的 AUTOEXEC 完全不变。
- `NAIZ_AE_PAD` 诊断旋钮保留在垫行之后，仍可叠加偏移，用于将来复发时扫地址。
- 该行长度（17 字节含 CRLF）是地址公式的一部分：**改它等同于改装载地址**。

**为什么不选 `-od`**：`-od` 在观察到的所有样本里都能启动，但会关闭优化，blit 热循环约慢 4 倍
（0.4.033 恢复 `-os` 的原因）。用一行 REM 换取 `-os` 性能是当前更优解。

**为什么不做「AUTOEXEC 定长填充」**：定长只能抵消 AUTOEXEC 侧的长度变化；镜像大小变化仍会
移动装载地址（§四），无法消除敏感性，只是把问题藏得更深。

## 七、验证（0.4.034）

| 项 | 结果 |
|---|---|
| `make -C core` 诊断 | `core/*.err` 全空 |
| 注入后 AUTOEXEC | `@ECHO OFF` / `CTMOUSE.COM` / `SET DOS16M=1` / `REM naiz ae pad` / `engine.exe` |
| 注入后 `ENGINE.EXE` | 245500 B（`-os`，与修复前同尺寸） |
| 实机冒烟（串口，旧机） | **1827 B**：`aiz engine` / `[MOUSE] NP2kai detected via system port` / `Init OK` / `Vid OK` …；**无 fatal / 4005** |
| 本机复测（2026-11-16，245500 B openpack） | 串口 **1220 B**：`aiz engine` / `[MOUSE] NP2kai detected via system port` / `Init OK` / `Vid OK`；**无 fatal / 4005**（§七.1） |
| `pytest` | **938 passed, 2 skipped**（当前工作区；0.4.034 HEAD `8b341f3` 为 933，差额 = 新增的 5 条垫行守护测试，见 §八.5） |

**§七.1 本机串口取证过程**：`tools/diag/np2kai_smoke_fifo.py` 原用 **FIFO** 替代 PTY，但本机
wxnp21kai 对 `com1_m_o` 的普通文件/FIFO 只做一次 `openat(O_RDWR|O_NOCTTY|O_NONBLOCK)` 随即
`close()`（`strace` 实测），此后不转发任何字节，故串口恒为 0 B——这是**抓取方式**问题，不是
启动失败（用户目测引擎正常）。工具改为 **PTY slave** 后，同一 `disks/demo-a2.hdi` 输出
**1220 B**，含 `aiz engine` / `Init OK` / `Vid OK`，无 4005。旧机 1827 B 与 1220 B 不等长属正常：
本机为 legacy 模式（见首批输出后 10 s 即停），旧机是固定时长抓尾。

## 八、风险与守则（必须遵守）

1. **任何改动都要冒烟**：AUTOEXEC 行数/字节数、引擎源码体积、编译旗标、链接布局 —— 任一项变化
   都可能再次移动装载地址。判据是「串口日志非空」，不是「模拟器窗口没报错」。
2. **复发时先扫地址，不要先怀疑 fixup**：`NAIZ_AE_PAD=0..4` 各注入一次并开机，若某个值能启动
   即地址敏感（本轮的判定方式）；仿真已证明 fixup 内容合法（§五）。注意 0 已是生产垫行 17 B，
   扫描是「17 B + N 行」的偏移；要复现原始 4005 须先删生产垫行（§三 测量前提）。
3. **对照实验必须同一条注入路径**：手动 `tools.naiz_img.inject` 与 `makegame.sh make` 的
   AUTOEXEC 分支不同（210 §十一.4 的污染事故），两边结果不可直接比较。
4. **不要用截图窗口判断启动成功**：必须先 kill 残留模拟器进程，再启动并读串口/抓屏，防假阳性。
5. **不要随意删这行 REM**：它没有语义作用，只有地址作用；删掉即回到坏地址。现由
   `tools/tests/test_autoexec_pad.py`（5 条）守护：删除、改写或移位这行都会让 pytest 变红。

## 九、方案 C（后续）：把 4005 与装载地址解耦

目标：不依赖「垫多少字节」的巧合，让任意布局都能加载。

计划步骤：

1. **地址探针**：在 `AUTOEXEC.BAT` 里用 `MEM`/`DEBUG` 或自写小 COM 打印 `ENGINE.EXE` 的实际
   装载段（DOS 的 `PSP:0002h` 即段顶），把「变量 → 地址」的映射测出来，而不是只观测成败。
2. **坏区测绘**：`NAIZ_AE_PAD` 从 0 扫到 ~64，记录每个值的装载段（16 字节粒度）与成败，
   判断坏区是单点、区间，还是与 `段:偏移` 的 64KB 边界跨越相关。
3. **源码级归因**：用 v9.12 `loader.asm` 的 `apply_fixups` 逐条对照坏地址样本（重点：
   `gs:[esi]` 的段界限、fixup 页缓冲区的段内偏移、`es:` 目标写入是否跨 64KB）。
   （§十二.3 已修正此猜测：`gs:[esi]` 只是 flat 选择子 `_sel_zero`（base 0 / limit 4G），
   不是段界限问题；重心应放在 fixup 页缓冲区与 `es:` 目标写入。）
4. **候选修复**：
   - 若坏区与 64KB 边界相关 → 在引擎侧把某段/某表对齐到固定偏移，或调整 LE 段对齐；
   - 若与 fixup 缓冲区位置相关 → 只能靠链/布局约束（例如固定 `-od` 或固定对齐），并写入构建守则。
5. **验收**：至少构造 3 种不同体积的镜像（±2KB），在 pad=0 下全部能启动，才算解耦成功。

在 C 完成前，A 是唯一生产兜底。

## 十、踩坑清单

1. **「加了 SET DOS16M=1 就修好了」是过拟合**：它只是地址平移的一种实现，镜像一变就失效（§四）。
2. **串口为空 ≠ 串口配置错**：先分辨「加载期失败」与「引擎早期崩溃」，前者一行日志都没有。
3. **模拟器告警会误导**：`9004 mouse initialization failed` 与 CuteMouse `device not found` 是
   PC-98 上的既有噪声，与 4005 无因果关系。
4. **镜像大小是地址公式主变量**：0.4.030（245232）→ 0.4.033（245232）→ 0.4.034（245500），
   中间任何一次功能改动都可能改变成败。
5. **垫行长度是常量，不要「顺手改注释」**：`REM naiz ae pad` 的字节数参与计算。

## 十一、验收缺口

- [x] 方案 A 落地 + 0.4.034 实机冒烟：旧机串口 1827 B（无 4005）；本机复测串口 1220 B（无 4005，§七.1）
- [x] `pytest` 全量复跑（0.4.034 HEAD `8b341f3` = 933 passed, 2 skipped；补 5 条垫行守护测试后当前 = 938 passed, 2 skipped）
- [x] 生产垫行单测守护（`tools/tests/test_autoexec_pad.py`，5 条）
- [ ] 方案 C：地址探针 + 坏区测绘 + `apply_fixups` 地址级归因（§九 1–3）
- [ ] 方案 C 验收：三种体积镜像在 pad=0 下均可启动（§九 5）
- [ ] 用户人工流程冒烟：Scene 菜单（当前仅 005 一项）/ 播放 / `scene(end)` 回鉴赏 / Back 回 special

## 十二、公开资料调研（2026-11-16）

检索范围：DOS/32A 官方站点与源码、Open Watcom 文档/PR、Vogons、GitHub issues。

1. **没有公开报告**把 4005 与装载地址/DPMI 布局关联。官方用户手册把 4005 定性为
   "fixup 记录损坏 / extender 不支持该记录"（DOS/32A User Guide §8，
   `javiergutierrezchamorro.com/wp-content/uploads/2013/07/dos32a/html/user/8.html`）。
2. **关键线索（源码/changelog）**：fixup 记录**先装入常规内存**，不够才用高位内存
   （`updates.txt`："fixups are loaded in DOS memory first"，
   `github.com/javiergutierrezchamorro/DOS32A/blob/main/updates.txt`）。结合
   `apply_fixups` 入口预置 `_err_code=4005h`，**推测**（非文档）：记录表的实际读取与预期
   不符（截断/错位/残留在旧内存），残留内容随环境块长度变化 → 表现为地址敏感。
3. **修正 §九.3 的猜测**：`gs:[esi]` 只是读记录的 flat 选择子 `_sel_zero`（base 0 / limit 4G），
   不是段界限问题；`src` 越界另有 4006。
4. **可直接实测的官方旋钮**：
   - `SET DOS32A=/VERBOSE`：打印对象装载位置与内存状况；
   - `SET DOS32A=/DOSBUF:NNNN`：DOS 传输缓冲区，默认 8KB、上限 64KB
     （`.../html/user/4.html`）——若 4005 真由记录表搬运不完整引起，这是比垫行更"对症"的开关；
   - `ss.exe`：可改 Object Loading Scheme #1–#4、DOS Transfer Buffer，并可锁定配置
     （`.../html/util/3f.html`）。
5. **版本串确认**：9.12 客户端版权横幅的默认字面量就是 `x.x.x`
   （`.../src/dos32a/text/client/data.asm`），与实机所见一致。
6. **无修复记录**：9.0–9.1.3 的 `updates.txt` 无任何 4005/fixup 修复；唯一相关是老条目
   "LX + Watcom v11 忽略 Internal fixups applied 位"。非官方 fork `dos32a-ng`（2021）只补了
   source-list 支持，与本问题无关。`LOADFIX` 属 DOS 自身 "Packed file corrupt" 手段，文档未提。
7. **PC-98 专门资料：未找到**。

**实验记录（2026-11-16，同一 245500 B `-os` 镜像，仅改注入的 AUTOEXEC）**

| AUTOEXEC 追加内容 | 追加字节 | AUTOEXEC 总长 | 串口字节 | 结果 |
|---|---:|---:|---:|---|
| 无 | 0 | 50 | 0 | **fatal 4005** |
| `REM naiz ae pad`（生产垫行） | 17 | 67 | 1827 | 启动 |
| `SET DOS32A=/DOSBUF:64` | 23 | 73 | 1657 | 启动 |
| `REM` + 17 个 `.`（等长对照） | 23 | 73 | 1673 | 启动 |
| `REM` + 19 个 `.` | 25 | 75 | 1657 | 启动 |

**结论**：等长 A/B（73 B：`SET DOS32A=/DOSBUF:64` vs 23 B `REM`）**两者都能启动**，因此无法把成功
归因于 `/DOSBUF`；本轮能复现的失败只有「完全不加垫」这一种地址，任何 ≥7 B 的追加都落在好区
（实测最小成功点 = §三 的 PAD=1，即 7 B）。
这支持「窄坏区 + 地址平移」，**不支持**「DOS 传输缓冲区不足」假设。`/DOSBUF` 线索就此关闭，不作
生产方案；若要彻底排除，需要在**等长的坏地址**上再做 A/B，但目前 0–25 B 追加范围
（实测点仅 0/7/8/9/10/17/23/25）内未找到第二个坏地址，成本不划算。

剩余可选实验（未执行，价值递减）：`SET DOS32A=/VERBOSE` 观察对象/记录装载位置；`ss.exe` 试
Object Loading Scheme #1–#4。

## 十三、2026-11-16 本机复核记录

同一条 `disks/demo-a2.hdi`（openpack）在本机重测，用于确认 §二/§七 的旧机结论可复现：

| 项目 | 本机实测 | 结论 |
|---|---|---|
| 注入产物 | `ENGINE.EXE` 245500 B；`AUTOEXEC.BAT` 67 B（`@ECHO OFF` / `CTMOUSE.COM` / `SET DOS16M=1` / `REM naiz ae pad` / `engine.exe`） | 与 §二 表一致 |
| 开机冒烟 | `tools/diag/np2kai_smoke_fifo.py disks/demo-a2.hdi` → 串口 **1220 B**：`aiz engine` / `Init OK` / `Vid OK`；无 4005 | 启动链完整 |
| `pytest` | **938 passed, 2 skipped**（含 `test_autoexec_pad.py` 5 条；0.4.034 HEAD `8b341f3` 为 933） | 守护生效 |
| 串口差异 | 本机 1220 B vs 旧机 1827 B | 模式差异：本机 legacy 见首批输出后 10 s 即停，旧机固定时长抓尾；不是故障 |

**工具修复**：冒烟脚本原用 FIFO，本机 wxnp21kai 对 `com1_m_o` 指向的普通文件/FIFO 只做一次
`openat(O_RDWR|O_NOCTTY|O_NONBLOCK)` 随即 `close()`，不转发任何字节（`strace` 实测）；改为
PTY slave 后立即出 1220 B。详见 §七.1。

**结论**：旧机结论在本机复现，问题出在抓取载体而非启动；§三 矩阵仍须按「测量前提」解读；
方案 C 维持「体积变化后冒烟失败再启用」的触发条件。
