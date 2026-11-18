# 212 — DOS/32A 装载地址敏感复发与 AUTOEXEC 垫行兜底（0.4.034）

> **状态**: 长期未完结（短期兜底 A 已落地并实机验证；机理深挖 C 见 §九，2026-11-17 已完成离线静态部分，实机扫描受阻，见 §十三）
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
| 实机冒烟（串口） | **1827 B**：`aiz engine` / `[MOUSE] NP2kai detected via system port` / `Init OK` / `Vid OK` …；**无 fatal / 4005** |
| `pytest` | **938 passed, 2 skipped** |

## 八、风险与守则（必须遵守）

1. **任何改动都要冒烟**：AUTOEXEC 行数/字节数、引擎源码体积、编译旗标、链接布局 —— 任一项变化
   都可能再次移动装载地址。判据是「串口日志非空」，不是「模拟器窗口没报错」。
2. **复发时先扫地址，不要先怀疑 fixup**：`NAIZ_AE_PAD=0..4` 各注入一次并开机，若某个值能启动
   即地址敏感（本轮的判定方式）；仿真已证明 fixup 内容合法（§五）。
3. **对照实验必须同一条注入路径**：手动 `tools.naiz_img.inject` 与 `makegame.sh make` 的
   AUTOEXEC 分支不同（210 §十一.4 的污染事故），两边结果不可直接比较。
4. **不要用截图窗口判断启动成功**：必须先 kill 残留模拟器进程，再启动并读串口/抓屏，防假阳性。
5. **不要随意删这行 REM**：它没有语义作用，只有地址作用；删掉即回到坏地址。

## 九、方案 C（后续）：把 4005 与装载地址解耦

目标：不依赖「垫多少字节」的巧合，让任意布局都能加载。

计划步骤：

1. **地址探针**：在 `AUTOEXEC.BAT` 里用 `MEM`/`DEBUG` 或自写小 COM 打印 `ENGINE.EXE` 的实际
   装载段（DOS 的 `PSP:0002h` 即段顶），把「变量 → 地址」的映射测出来，而不是只观测成败。
   **（2026-11-17 订正：无需自写 COM，官方旋钮 `SET DOS32A=/VERBOSE` 已足够，见 §十三.2）**
2. **坏区测绘**：`NAIZ_AE_PAD` 从 0 扫到 ~64，记录每个值的装载段（16 字节粒度）与成败，
   判断坏区是单点、区间，还是与 `段:偏移` 的 64KB 边界跨越相关。
3. **源码级归因**：用 v9.12 `loader.asm` 的 `apply_fixups` 逐条对照坏地址样本（重点：
   `gs:[esi]` 的段界限、fixup 页缓冲区的段内偏移、`es:` 目标写入是否跨 64KB）。
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

- [x] 方案 A 落地 + 0.4.034 实机冒烟（串口 1827 B，无 4005）
- [x] `pytest` 全量复跑（938 passed, 2 skipped）
- [ ] 方案 C：地址探针 + 坏区测绘 + `apply_fixups` 地址级归因（§九 1–3）
  - 2026-11-17：探针已定为 `SET DOS32A=/VERBOSE`；静态归因已收敛到「写入异常掩盖 4005」；坏区测绘待模拟器恢复（§十三）
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
归因于 `/DOSBUF`；本轮能复现的失败只有「完全不加垫」这一种地址，任何 ≥9 B 的追加都落在好区。
这支持「窄坏区 + 地址平移」，**不支持**「DOS 传输缓冲区不足」假设。`/DOSBUF` 线索就此关闭，不作
生产方案；若要彻底排除，需要在**等长的坏地址**上再做 A/B，但目前 0–34 B 追加范围内未找到第二个
坏地址，成本不划算。

剩余可选实验（未执行，价值递减）：`SET DOS32A=/VERBOSE` 观察对象/记录装载位置；`ss.exe` 试
Object Loading Scheme #1–#4。

## 十三、方案 C 离线进展（2026-11-17）

本轮只做**不依赖模拟器**的部分；实机扫描因环境缺件暂停（§十三.4）。

### 1. 源码基线已就地重建

`tmp_le/dos32a-git/src/`（`loader.asm` / `loadpe.asm` / `kernel.asm` / `dos32a.asm`）与
`tmp_le/dos32a-main/`（完整 v9.12 树）已拉取，`tmp_le/` 在 `.gitignore:48` 内，不污染仓库。
§九.3 的源码级归因从此可离线进行。

### 2. 地址探针：用官方 `/VERBOSE`，不自写 COM

- `SET DOS32A=/VERBOSE` 是加载器注册的关键字：`src/dos32a/text/client/data.asm:52`
  （`dfA_str` = `'VERBOSE'`），`_misc_byte2` 默认值 `7`（同文件 `:104`）已使能环境变量解析，
  无需额外开关。
- 输出通道是 `writes` → INT 21h **AH=09h**（句柄 1），因此 `AUTOEXEC` 写
  `engine.exe > D32ALOG.TXT` 即可把加载布局落盘，再用现有 `naiz_img` 读回——**不依赖串口、
  不依赖截图**。VERBOSE 会打印启动内存状况（含 PSP/Env 段）与每个对象的装载基址，
  正好覆盖 §九.1 要的「变量 → 地址」映射。

### 3. `apply_fixups` 静态归因（`src/dos32a/loader.asm`）

- 4005 在 `apply_fixups` 入口预置，函数内能独立置位的只有 4 类**内容检查**：
  `test cx,0F20h`、objnum 越界（`sub edx,eax; jc`）、`type > 8`、以及 `fix_invalid`
  （type 1/4）。记录内容若全部合法（§五仿真结论），这些分支都不该命中。
- 记录表读取路径：`load_gs_block` → INT 21h 反射（`client/int21h.asm` `@__3Fh`），
  目标 `ES:EDI` 中 ES = 调用方 DS（flat）、EDI = **完整 32 位 EDX**，按 `_lobufsize`
  分块拷贝。**未发现 64KB 截断或段内偏移丢失**。
- `gs` = `_sel_zero`（`client/misc.asm` 建描述符：base 0 / limit 4 GB），故 §十二.3 的
  「段界限」猜测继续排除。
- 由此收敛出唯一未被否证的残余假设：**记录合法，但写入 `gs:[edi]` 时目标页异常，
  异常路径把入口预置的 4005 当作错误码报出**——这正是「地址敏感」的形态，但必须实测
  才能定案，不能再用静态推理替代证据。

### 4. 卡点：本机没有可执行的模拟器

`/usr/local/bin/wxnp21kai` 不存在，`~/NP2kai` 全树也无已构建产物，因此
`np2kai_capture` / `np2kai_smoke_fifo.py` / `makegame.sh test` 均无法执行。
在模拟器恢复前，§九.2（坏区测绘）与 §九.5（三镜像验收）**无法推进**。

### 5. 已实测的当前镜像参数（离线，可复核）

`games/demo-a2/engine.exe`（245500 B，`-os`）LE 头自洽数据：`e_lfanew = 0x6B90`、
页数 46、页大小 4096、末页 2808 B、数据页偏移 58372、fixup 段 30392 B、loader 段 246 B
（58372 + 45×4096 + 2808 = 245500 ✓）。可作为坏区测绘时「地址—成败」对照的固定基线。

### 6. 下一步（按依赖顺序）

1. 恢复模拟器（或提供可执行路径）→ 实现 `tools/diag/ae_addr_sweep.py`：任意**单字节粒度**
   垫行（现有 `NAIZ_AE_PAD` 只有 6 字节粒度）+ `DOS32A=VERBOSE` + 日志回读 + 成败表；
2. 扫 pad=0..N，产出「装载段 → 成败」映射，判定坏区是单点/区间/64KB 边界相关；
3. 按 §九.4 选修复方向；4. 按 §九.5 用三种体积镜像验收。

