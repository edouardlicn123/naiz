# 189 - CWTEST追凶第三轮：FAT获取挂死锁定 + 自建调试内核

> 交接文档。上一份：188-CWTEST追凶第二轮。上游：178（主规划）、185。
> 本文档供下一对话**直接续做**，含全部可复用命令与当前卡点。

> **冻结通告（2026-11-02）**：CauseWay 追查线已判死并冻结，"直接续做"不再适用。
> 最终结论见 [refdoc I03 §零](file:///home/edo/naiz/docs/refdocs/I03_CWTEST追凶经验总结-模拟器能力边界与后续方针.md)。

---

## 一、总目标（不变）

按 devdoc 178（阶段1-2）与 185（O1-O5）完成 **Naiz 部署链开源化**：CauseWay 引擎用开源工具链（OpenWatcom wasm+wlink）构建，跑在开源 FreeDOS(98) 内核基座上，NP2kai 模拟器执行。

当前阶段 **step2c：CWTEST 冒烟测试追凶**。通过标准 = **屏显 CWTEST OK + CWOK.TXT 落盘**。

继承指令：问题优先参考 pristine 原件（/tmp/cworig/ 与 /media/edo/data/studysource/fdkernel/fdkernel-test-20220120-cherrypick/）；持续执行不问权限。

---

## 二、本 session 已完成（重要成果）

### 2.1 挂死边界与挂点（判读矩阵，已锁定）

| 实验 | 结果 | 结论 |
|---|---|---|
| 3Fh 读 pos 0/2/0x80/0x100/0x1FE | 全成功（R460002/i960002/j460002） | 簇1（relcluster 0）读全通 |
| 3Fh 读 ≥0x200（0x200/0x400/0x8000/0x18880） | 全挂死 | 簇边界 = 0x200（1.44M FAT12 簇=1扇区） |
| 新句柄首读 @0x200 | 挂 | 全局性，非句柄状态 |
| 3Ch create CWPROBE.$$$ | 挂（p 未打印） | 首次 FAT 扇区获取挂死实锤 |
| **AH=69h 取卷序列号** | **成功（y47000F，CF=0）** | **LBA_Transfer 直读（RWzero→getbpb，无缓存无FAT，DiskTransferBuffer 低内存）在反射上下文可用** |

**挂点精确锁定**：读 @0x200 是唯一触发 map_cluster（fatfs.c L1022）while 迭代体的操作 →
`next_cluster(2) → link_fat → getFATblock(abs 1) → getblock(1) 内部` 挂死。
link_fat 的 clussec 语义已确认 = 绝对扇区（dpb_fatstrt 已加，fattab.c L208-221）。

**关键排除**（静态审查全部有界）：searchblock/getblk/flush1/dskxfer/LBA_Transfer/map_cluster/link_fat 无死循环；内核切自有 disk stack（RawStackDif 假说死）；切栈后自 STI（IF=0 假说死）；media_check 不在读路径且 open 已证明可用；int25 retf 与反射协议不兼容（不可用作鉴别器）。

**残余未知**：R 探针（abs 33）的 hit/miss 未知（EXEC 加载走多扇区直读路径不经块缓存，但缓存历史复杂）→ getblk→dskxfer(HMA 弹跳) 链路在反射上下文是否可用未定证。

### 2.2 内核自建（工程管线已打通）

- **调试内核已成功引导**：banner `FreeDOS(98) kernel - GIT (build 2043 DBCS OEM:0xfd) [compiled Oct 30 2026]`，A/B/C 驱动识别正常。boot 完全支持**未压缩 CONFIG 内核**（eb 14 'CONFIG' 头，85934B），无需 upx。
- 源码树副本：/tmp/kernel_build/（pristine 原件在 /media/edo/data/studysource/，勿污染）
- 工具链：WATCOM=/usr（嵌入式安装），PATH 加 /tmp/nasm_local/usr/bin（nasm 2.15.05 从 .deb 解包）与 /usr/binl64（OpenWatcom 2.0 beta）
- 全量编译脚本：/tmp/kernel_build/nec98/kernel/build_manual.sh（52 个 obj）
- 踩坑记录（复建必读）：
  1. makefile.wc 的 DOS 扩展 `$[@ $^@` 在 wmake -ms 与原生模式均报 E09 → 用手工脚本绕过
  2. wcc 2.0 不认 `-1-` → 去掉
  3. `proto.h` 在 ../../kernel/ → CFLAGS 加 `-I../../kernel`
  4. memdisk 是 .asm 不是 .c；**nec98/kernel/ 有大量本地 fork（dsk.c prf.c entry.asm console.asm io.asm intr.asm 等），必须本地优先**
  5. **printf 有三条条件编译路径**（prf.c L125）：① `_INIT`（init 段）② `DEBUG_NEED_PRINTF && !_INIT && !FORSYS`（resident 段 FAR 修正版）③ `FORSYS`。`-DDEBUG_NEED_PRINTF` 只打开 resident 段 FAR printf。**init 段 printf 是自动生效的**（编译时自带 `_INIT`），所以 banner/Press F8 等能打出来；但 resident 段（CONFIG 处理阶段）**没有 printf 调用**（因为 DISPLAY_GETBLOCK 也没加）
  6. libm.lib 是 wtouch 空占位，wlink 报 E2146 → lnk 中去掉
  7. wlink lnk 文件：每行一个 `file xxx.obj` 指令（同行逗号分隔 + 重复 file 关键字会 E3033）
  8. 转换：`/tmp/kernel_build/nec98/utils/exeflat.exe kernel.exe kernel_dsys.sys 0x60 -S0x10 -S0x78 -S0x79`
  9. 调试宏：blockio.obj/fatfs.obj 用 `-DDISPLAY_GETBLOCK` 编（searchblock HIT/MISS + map_cluster 打印）；fattab.c clusterMessage（"I/O: 0x"/"Run chkdsk"）**无条件已编进两个 sys**
  10. sys 目录构建被 upx 缺失卡住 → 直接跳过 sys，只编 kernel 目录
  11. kernel.sys（85934B）vs kernel_dsys.sys（87070B）：同 banner 同编译时间戳，首字节差异在 MZ header 偏移 0x17 — kernel.sys header 指向 init 段，kernel_dsys.sys header 指向另一入口（应该是 exeflat 不同 `-S` 参数产物，exeflat 命令写在踩坑 8）

### 2.3 换内核流程（已验证）

```
python3 /tmp/cw_diag/swap_kernel.py /tmp/kernel_build/nec98/kernel/kernel_dsys.sys /tmp/fdhyb_B2R.hdi
```
- 备份：/tmp/fdhyb_B2R.hdi.bak_orig（换内核前原盘 = 原压缩内核 + CWTEST.EXE y 探针版）
- 回退：`cp /tmp/fdhyb_B2R.hdi.bak_orig /tmp/fdhyb_B2R.hdi`

### 2.4 调试宏实际未编进的实证（2026-10-30 补充，重要发现）

build_manual.sh 里 `COMMON` 宏实际值：

```bash
COMMON="-I. -I../../hdr -I../../kernel -zq-os-s-e5-j-zl-zp1-wx-we-zgf-zff -d1 -bt=DOS -DNEC98 -DJAPAN -DDBCS -DNO_REVISION -DALLOW_MBRDISK"
```

**缺少** `-DDISPLAY_GETBLOCK` 和 `-DDEBUG_NEED_PRINTF`。各宏保护范围精确定位：

| 源文件 | 行 | 保护条件 | 效果 |
|---|---|---|---|
| blockio.c | L48 `/* #define DISPLAY_GETBLOCK */` | 注释掉 | L91 searchblock HIT/MISS、L105 blk 打印、L147 dskxfer 日志 — **全块跳过** |
| fatfs.c | L709/L782/L979/L1048/L1302/L1398 | 全 `#ifdef DISPLAY_GETBLOCK` | find_fat_free / DIR / map_cluster / done / rwblock / DATA — **全块跳过** |
| fattab.c | clusterMessage | **无条件** | "I/O: 0x"/"Run chkdsk" — **已编进** |
| prf.c L125 | `#if DEBUG_NEED_PRINTF \|\| FORSYS \|\| _INIT \|\| TEST` | banner 里 `_INIT` 生效 | init 段 printf 编进了（banner/Press F8/驱动行能打出来） |
| prf.c L127 | `#if DEBUG_NEED_PRINTF && !defined(_INIT)` | **不满足** | resident 段 FAR 版 printf（SS≠DS 修正）**未编进** |

strings 验证：`kernel_dsys.sys` 能扫到 banner（`[compiled Oct 30 2026]`），扫不到 `getblock` / `searchblock` / `map_cluster` — DISPLAY_GETBLOCK 确实未进二进制。blockio.err / fatfs.err 里的 `W308: The function 'printf' without prototyped parameters called` 是被 ifdef 跳过的代码块里的调用点残留警告。

**这意味着黑屏问题首先不是"挂死在 CONFIG 读取"**——是我们期待的调试打印（getblock HIT/MISS、map_cluster current/offset/diff）**根本没编进二进制**，所以什么都看不到。banner/Press F8 能打出来是 init 段 printf（带 `_INIT` 宏）在工作。

### 2.5 CW 侧探针现状

- api.asm T 探针序列：R(读@0) i(读@2) j(读@0x1FE) **y(AH=69h)** p(3Ch create) q(40h write) r(3Eh close) s(3D00h reopen) t(seek 0x200) u(读@0x200 新文件) v(close) w(41h delete) x(handle7 seek0x200+读@0x200 哨兵)
- 本轮串口证据（ser_capture.log 偏移 90473-91825）：
  `T060007 R460002 i960002 j460002 y47000F [create 挂死]`
- CW 构建管线照旧：`wasm -zq -dPERMBIG1 -dPERMNOVM=1 -dENGLISH=1 -fo=cw32_chk.obj cw32.asm && wlink system dos file cw32_chk.obj name cw32_chk.exe option map=cw32_chk.map` → /tmp/cw_diag/resplice.py → inject_cwtest5.py

---

## 三、当前进行中（2026-10-30 现场检查后重写）

> **⚠️ 本节 §3.2/§3.3 的核心结论（"自建内核在 CONFIG/FAT 路径挂死 → 黑屏"）已在同日第二轮现场实验中被推翻，见 §七。原文保留仅作推理链留痕。**

### 3.1 环境状态快照（纯只读检查，不动磁盘）

| 项 | 状态 |
|---|---|
| 模拟器运行中？ | **否**（ps 无 wxnp21kai） |
| `/tmp/fdhyb_B2R.hdi` | 262MB，2026-10-30 15:01 — 调试内核版（含黑屏内核） |
| `/tmp/fdhyb_B2R.hdi.bak_orig` | 同时间戳 — 原内核 + CWTEST 探针版（安全回退点） |
| `/tmp/kernel_build/nec98/kernel/` | 51 个 obj 编全，`kernel.sys`（85934B）+ `kernel_dsys.sys`（87070B） |
| 构建日志 | 两条无关 warning（conkey60.asm/conseg60.asm 段重声明），零错误 |
| 工具链 | nasm 2.15.05、wlink/wcc 2.0 beta 均就位 |

### 3.2 黑屏根因修正（§2.5 + §3.1 现场检查后终版）

上一 session 以为 "内核挂在 CONFIG.SYS 读取的第一个 getblock"，**但这个推断建立在 "调试宏已编进" 的前提上**——而我们实际只编进了 init 段 printf（banner 能打），resident 段调试打印（getblock HIT/MISS、map_cluster 等）**全部被 ifdef 跳过**。

#### 两盘配置完全相同的决定性证据（纯只读，2026-10-30）

| 对比项 | B2R（调试内核盘） | bak_orig（原压缩内核盘） |
|---|---|---|
| KERNEL.SYS size | **87070**（自建 kernel_dsys.sys） | **49938**（原压缩 lpproj kernel） |
| FDCONFIG.SYS | HIMEMX.EXE only，**无 EMM386** | **完全相同**（HIMEMX only） |
| AUTOEXEC.BAT | STG-1 → CWTEST.EXE → STG-3 | **完全相同** |
| CWTEST.EXE | 120696B，cluster 0526 | **同簇同文件** |
| 其他驱动 | 几乎相同 | 几乎相同 |

**推论**：驱动配置（B2N）在两盘上**逐字节相同**。bak_orig 盘在原压缩内核 + B2N 配置下能跑起来（CWTEST 探针能打到 y47000F，只是 create 时 FAT 挂死）。B2R 盘换了自建内核 + 完全相同的配置 → 黑屏。

**→ 黑屏不是驱动配置问题**，是自建内核本身的问题。

#### 现在可以排除的候选

| 候选 | 状态 | 理由 |
|---|---|---|
| 驱动配置问题 | ❌ 排除 | 两盘 FDCONFIG/AUTOEXEC 完全相同 |
| printf/FAR 指针坏了 | ❌ 排除 | resident 段无 printf 调用（全被 DISPLAY_GETBLOCK 跳过）；clusterMessage 用 put_string 不依赖 FAR printf |
| wcc 2.0 beta printf 代码生成 | ❌ 排除 | 没有 resident 段 printf 调用 |
| 磁盘硬件/dskxfer/HMA 挂死 | ⚠️ 待定 | 与 CWTEST 反射上下文的 FAT 挂死**可能同根因**；但 CONFIG 读取走的是 open → findfirst → getblock，和 CWTEST 的 open 同一条磁盘路径 |
| **wcc 2.0 beta 代码生成 bug（磁盘路径核心代码）** | 🔴 头号嫌疑 | 原压缩内核（可能用不同编译器版本）在同硬件同配置同盘上能正常读 CONFIG，自建内核不能 |
| **磁盘路径真的挂死了（与 CWTEST FAT 挂死同根因）** | 🔴 同等嫌疑 | CONFIG 读取一定会走到 getblock（open → findfirst → getblock → dskxfer），而 CWTEST 在同盘上 FAT 路径也挂 |

**两个嫌疑其实指向同一个问题**：**磁盘 I/O 路径（getblock/dskxfer/HMA）在自建内核里有 bug** —— 要么 wcc 2.0 beta 代码生成问题，要么内核某处段/栈/内存布局问题。

#### clusterMessage 的触发条件确认（纯只读）

- fattab.c L54 `clusterMessage(const char *msg, CLUSTER clussec)` — **无条件**，用 put_string/put_console 直接写屏，不依赖 printf/FAR
- 唯一触发点：getFATblock() 里 getblock() 返回 NULL（L85 `clusterMessage("I/O: 0x", clussec)`）
- **已编进二进制**：两个 sys 文件 strings 都能扫到 `Run chkdsk: Bad FAT ` 和 `I/O: 0x`

**推论**：黑屏期间 clusterMessage 没打出来 → getblock() **没返回过 NULL** —— 要么 getblock 内部**直接挂死**（在能返回 NULL 之前），要么磁盘路径更上层就挂了（比如 CONFIG.SYS 文件名的 findfirst 就挂了）。

#### DebugPrintf 在 config.c 里也空了

build_manual.sh 没有 `-DDEBUG`，所以 config.c L906/L910/L925 的 `DebugPrintf(("Reading FDCONFIG.SYS...\n"))` 全是空宏。如果加 `-DDEBUG`，这些也能打出来，可以区分"刚进 CONFIG 就挂"还是"读完 CONFIG 驱动初始化时挂"。

### 3.3 下一步行动计划（改 build 脚本，算动手）

**纯只读阶段结束**。已经确认：两盘配置相同、自建内核在 CONFIG 路径挂死、所有调试打印都被宏跳过。下一步必须加宏重编。

**动手计划（改 build_manual.sh 一行 COMMON）**：

1. COMMON 加三个宏：
   - `-DDISPLAY_GETBLOCK` → blockio/fatfs 调试（getblock HIT/MISS、map_cluster、dskxfer）
   - `-DDEBUG_NEED_PRINTF` → resident 段 FAR printf（SS≠DS 修正）
   - `-DDEBUG` → config.c DebugPrintf（"Reading FDCONFIG.SYS..." / "Skipping CONFIG..."）
2. 重编内核（build_manual.sh）→ swap_kernel → 启动模拟器 → F5 跳过 CONFIG + F8 单步各测一次
3. **关键观察**：看屏幕最后几行 — getblock HIT/MISS？还是直接黑屏无任何输出？

**如果重编后还是黑屏无输出** → wcc 2.0 beta 代码生成嫌疑实锤，考虑换编译器版本（降 1.x 或用不同优化开关 `-os+-ol+`）。

### 3.4 回退路径

bak_orig 盘（原压缩内核 + CWTEST 探针 + 相同配置）是**安全的同配置对照**：
- 原内核在这盘上能跑到 CWTEST 探针 y47000F（只是 FAT 挂死）
- 用来确认不是磁盘镜像本身问题
- `cp /tmp/fdhyb_B2R.hdi.bak_orig /tmp/fdhyb_B2R.hdi` 一键回退

### 测试工作流（惯例，照抄）

```
stat -c %s /tmp/cw_diag/ser_capture.log        # 记偏移
pkill -9 -x wxnp21kai; sleep 2
# Shell run_in_background=true（勿加 &）：
wxnp21kai -c /tmp/cw_diag/np2_hB2.toml
sleep 58~75
# 截屏：WID 过滤 640x459 几何
xdotool search --name 'NP21kai' | while read W; do G=$(xdotool getwindowgeometry $W | grep -oE '[0-9]+x[0-9]+'); [ "$G" = "640x459" ] && echo $W; done
xdotool windowactivate $WID; import -window $WID /tmp/cw_diag/xx.png
# 模拟器内按键（F5/F8）：xdotool key --window $WID F5
```
- 串口：pty_hold.py（常驻，openpty → /dev/pts/0 → append ser_capture.log）；配置 com1_bps=9600 com1para=227
- 串口日志解码：探针 dump 格式 = 字母 + flags低字节2hex + AX 4hex（如 R460002）；噪声串 `SABCDEFJMNKLPVWXYZabcdefghij...IRTU6yz 123945 OQ12390$` 靠位置与格式区分

---

## 四、剩余任务

1. **【立即】** 排查调试内核黑屏（见 §三）→ 用 getblock 打印定位 getblock(1) 挂点 → 修复
2. 修复后重测至 **CWTEST OK + CWOK.TXT → step2c 通过**（可用 /tmp/fdhyb_B2R.hdi.bak_orig 恢复原内核 + CW 探针版做对照）
3. step2c 通过后：回填 I02 §五（/home/edo/naiz/docs/refdocs/I02_cwtest追凶行动计划-udspy2与kernel诊断构建.md）+ devdoc 187/188 修订，累计记录：'9' 标记 AL 污染、探针 AX 污染句柄、簇边界二分法、create 交叉验证法、AH=69h 鉴别器、内核四栈机制、int25 retf 不兼容、dskxfer/HMA 弹跳、**内核自建全套踩坑（§2.2）**、模拟器偶发死亡事件
4. step2d：BGM 播放 + devdoc 176 ISR 剖面复测
5. step4-8：开源基座 HDI / makegame.sh / 端到端 / naiz-openpack / devdoc 收尾
6. 技术债：清理调试插桩（int21h.asm v5 探针 O/C/P/M/R/V/W/Q/X/N、api.asm T 探针 R/i/y/j/p/q/r/s/t/u/v/w/x、raw_vcpi 0-5/9）、X 探针句柄泄漏（6/8/A 未关，无害）、probe*.asm/obj/exe/map、*.bak_*、*_chk.*、.ref；loadle.asm.bak_instr 已污染不可用

---

## 五、交接文件清单（2026-10-30 现场检查后更新）

| 文件 | 用途 |
|---|---|
| /home/edo/naiz/devdocs/188-CWTEST追凶第二轮-*.md | 上轮主记录 |
| /home/edo/naiz/devdocs/189-*.md | 本文件（当前最新，含 §2.4 宏未编进实证、§3.2 两盘配置对照、黑屏根因修正） |
| /tmp/cwbuild/ | CW 源（api.asm T 探针 L6526-6700；int21h.asm v5 探针；cw32.asm） |
| /tmp/cw_diag/ | 测试工具全家桶（resplice/inject/pty_hold/np2_hB2.toml/swap_kernel.py/set_autoexec.py） |
| /tmp/cw_diag/rebuild_cw.sh | **危险勿跑**（pristine 重建会抹掉全部修改） |
| /tmp/cw_diag/pty_hold.py | 串口日志收集器（openpty → ser_capture.log） |
| /tmp/cw_diag/swap_kernel.py | 一键换内核：`swap_kernel.py <kernel.sys> <disk.hdi>` |
| /tmp/kernel_build/ | 内核源码副本 + build_manual.sh + kernel.lnk + kernel.exe + kernel.sys + kernel_dsys.sys |
| /tmp/kernel_build/nec98/kernel/build_manual.sh | **下一步要改的文件** — COMMON 宏加三个 -D（§3.3 计划） |
| /tmp/kernel_build/nec98/kernel/kernel_dsys.sys | 当前替换进 HDI 的内核（87070B，**不带调试宏**） |
| /tmp/kernel_build/nec98/utils/exeflat.exe | kernel.exe → kernel_dsys.sys 转换工具 |
| /media/edo/data/studysource/fdkernel/fdkernel-test-20220120-cherrypick/ | pristine 内核源码（勿污染） |
| /tmp/nasm_local/usr/bin/nasm | nasm 2.15.05 |
| /tmp/fdhyb_B2R.hdi | 当前测试盘（调试内核版，挂黑屏状态，FDCONFIG=HIMEMX only） |
| /tmp/fdhyb_B2R.hdi.bak_orig | 原内核备份盘（原压缩 kernel + CWTEST 探针 + 相同 FDCONFIG，能跑到 y47000F） |
| /tmp/cw_diag/dbgk_boot1-4.png | 调试内核 boot 各阶段截屏（banner → Press F8 → 黑屏） |
| /tmp/cw_diag/ser_capture.log | 最新串口日志（91825 bytes，止于 y47000F 后） |
| /home/edo/naiz/docs/refdocs/I02_*.md | step2c 通过后 §五回填区待填 |

## 六、关键环境

- WATCOM=/usr；PATH 前插 /tmp/nasm_local/usr/bin:/usr/binl64
- 模拟器：`wxnp21kai -c /tmp/cw_diag/np2_hB2.toml`（SCSIHDD0=/tmp/fdhyb_B2R.hdi，pc_model='VX'）
- 串口：com1_bps=9600 com1para=227，pty_hold.py 保持 /dev/pts/0 对接
- 时区 Asia/Shanghai；2026-10-30
- 本轮工作目录：/home/edo/Documents/Trae-CN/temp_20261030_03

---

## 七、2026-10-30 第二轮现场（推翻 §3.2/§3.3，重要）

### 7.1 决定性结论：自建内核没有"CONFIG 挂死/黑屏"

§3.2 的"自建内核 + 相同配置 → 黑屏"**已被实验推翻**。真实情况是两层叠加的假象：

| 实验 | 内核 | 配置 | 结果 |
|---|---|---|---|
| 最小配置（无 DOS=HIGH、无 DEVICE） | dbg2（`-DDEBUG`） | cfg_min | 正常到 `A:\>`，`ECHO READY` 可见 |
| 同配置 | **原压缩内核 KWC8616.SYS** | cfg_min | 正常到 `A:\>`，行为一致 |
| **min + `DEVICE=A:\HIMEMX.EXE`（DOS=LOW）** | **gb（去 `-DDEBUG`）** | cfg_dev | **正常到 `A:\>`**，`STG-1`/`STG-2` 都打印（提示符里 `¥` = PC-98 的 0x5C 反斜杠） |
| 同配置 + CWTEST | dbg2 | cfg_dev | 屏幕乱码 + 静止 → 曾误判为"内核挂死" |

**结论 1**：自建内核在 DOS=LOW + HIMEMX 下**完全正常**（CONFIG 读取、DEVICE 加载、COMMAND.COM、AUTOEXEC 全部通过）。

**结论 2**：早先的"黑屏/乱码"不是内核坏，是 **`-DDEBUG` 版**的 resident printf 把 `%p` 一类值打印成 ≥0x81 字节，PC-98 int29 按 DBCS 首字节处理导致整屏错位。**去掉 `-DDEBUG`（只留 `-DDEBUG_NEED_PRINTF`）后控制台完全可读** —— 这是本轮最重要的方法论修正。

**结论 3**：§3.3 的"下一步必须加三个宏重编"已执行完毕，`DISPLAY_GETBLOCK`/`DEBUG_NEED_PRINTF` 都能编进去（`printf` 原型坑见 §7.5）。

### 7.2 判定矩阵（本轮全部有截屏/文件证据）

| 配置 / 操作 | 结果 | 解读 |
|---|---|---|
| `COPY A:\HIMEMX.EXE A:\BIG2.BIN`（5859B，多簇分配+FAT 写） | **成功**，BIG2.BIN 5859 字节落盘 | **实模式 FAT 读/分配/写全链路健康**，挂死与内核 FAT 代码无关 |
| `TYPE`/`DIR` 等实模式操作 | 正常 | 同上 |
| CWTEST，cfg_min（无任何 XMS） | CW.LOG=439B：`CauseWay error 09`、`Exception: 0D`、`CR0=...011 CR3=0` | **PM 切换失败（GP）**，根本没进保护模式 |
| CWTEST，`DEVICE=A:\EMM386.EXE` | **同样的 CauseWay Error 09** | EMM386 的 XMS 不被 CauseWay 用 |
| CWTEST，`DEVICE=A:\HIMEMX.EXE` | PM 切换**成功**（CW 串口探针 `T060007 R460002 i960002 j460002 y47000F` 打出） | HIMEMX 是必需的 XMS 提供者 |
| 同配置继续跑 | **整机 HLT 停机**：`ps` 显示模拟器 CPU 仅 **1%**（对照 A:\> 空闲时 67%），屏幕 md5 只在两个光标态间交替（光标闪烁由模拟器硬件驱动，不代表 CPU 活着） | **不是死循环，是执行了 HLT** |

### 7.3 探针 `y47000F` 的 flags 修正（推翻 §2.1 的一条结论）

`y` 探针 dump 格式 = 字母 + flags低字节2hex + AX 4hex。`y47000F` 中 **flags=0x47 → bit0(CF)=1，AX=0x000F（错误码 15 = invalid drive）**。
即 **AH=69h 实际是失败，不是 §2.1 写的"成功 CF=0"**。因此 §2.1 里"AH=69h 可作为 LBA_Transfer 反射上下文可用的鉴别器"这一推论**降级为未证实**，不能再当证据用。

### 7.4 新的打点武器：纯标记阶梯（关键工具）

满屏的 `DISPLAY_GETBLOCK` 噪声会把屏幕尾部涂满，无法判读。改用**只打短标记、关掉 getblock 噪声**（编译宏只要 `-DDEBUG_NEED_PRINTF`）：

```
!C   int21 AH=3Ch 入口            c   int21 AH=3Ch 返回
!T   truename OK                  !O  dos_open 调用前    o  dos_open 返回
!M   map_cluster 入口             !Y  rwblock 入口
!P1  getblock 返回之后            !P3  数据搬运完成    !P9  rwblock 返回
!K<n>e  第 n 次读扇区 dskxfer 前后 !W<n>e  第 n 次写扇区
!U   dir_write_update 的 getblock
!Z0 / !Z4  int21 AH=00 / AH=4Ch（终止进程）
```

实测屏幕尾部（`kernel_dsys_mk.sys` + cfg_dev + `CWTEST.EXE > CW.LOG`）：

```
FreeCom ver 0.85a_DBCS - WATCOMC - XMS_Swap (PC98) [Jan 17 2022 22:36:59]
!T!Oo!Y!M!K22e!P1!P3!T!Oo!Y!M!P1P1!P3!K23e!K24e!K25e!K26e!K27e!K28e!U!W29e!W30e!W3
1e!T!O!K32e!K32eo!Y!M!K33e!P1!P3STG-1
!t!T!O!o!Y!M!K34e!K35e!K36e!K37e!U!W38eoc!T!O!o!Y!M!K39e!P1!P3!Y!M!P1
!P3!Y!M!P1!P3!Y!M!P1!P3 ... （!P3!Y!M!P1 长串重复，即逐块读大文件）
... !P3!P9 SABCDE !T!O!K49eo !Y!M!P1!P3!P9 FJMNKLPVWXYZabcdefghij  ← 光标停在此处
```

**解读**：
1. `!C ... c` 出现（line 4 的 `!U!W38eoc`）→ **create 在 DOS=LOW+HIMEMX 下是能返回的**，之前"CWTEST create 必挂"的判读需要重测（当时的 create 是 shell 为 `> CW.LOG` 做的，且环境不同）。
2. 大量 `!P3!Y!M!P1` 循环 = 逐块读取一个 ~236 簇的大文件（CWTEST.EXE 120696B），**内核侧 FAT/块缓存全部正常返回**。
3. 停机前最后的东西是 `SABCDEFJMNKLPVWXYZabcdefghij` 这串**非 ASCII 噪声**（与串口日志里的噪声串 `SABCDEFJMNKLPVWXYZabcdefghijklmnopqrstuIRTU6yz` 同一前缀），且**串口比屏幕多走了 `klmnopqrstu`** —— 说明串口那侧还在往前走、屏幕侧停在 `j`。噪声串是 CW 侧 debug 输出的已知伪影（devdoc §测试工作流已记录），**不是内核打印**。

### 7.5 本轮踩坑（复建必读）

| 坑 | 现象 | 修法 |
|---|---|---|
| `-DDISPLAY_GETBLOCK` 下 resident `printf` 无原型 | `W131/W308` + `-wx` 直接报错，`|| exit 1` 提前退出 → 静默用陈旧 obj | 在 `blockio.c/fatfs.c/fatdir.c/dosfns.c/inthndlr.c` 加 `int VA_CDECL printf(CONST char *fmt, ...);`，守卫 `#if defined(DISPLAY_GETBLOCK) \|\| defined(DEBUG_NEED_PRINTF)` |
| `-DDEBUG` 让 console 整屏乱码 | 误判"内核挂死"整整一轮 | 调试内核**不要带 `-DDEBUG`**，只要 `-DDEBUG_NEED_PRINTF` |
| 用 0:46C tick 判中断是否活着 | NEC98 的 `GetBiosKey_nec98` 走 `WaitVSync`，不看 46C | 0:46C 在 PC-98 上不可作判据 |
| 用屏幕静止判"挂死" | 提示符等待键盘时屏幕本来就静止 | 必须看 `ps` 的 CPU%（67% ≈ 忙/等键，1% ≈ HLT 停机） |
| 用光标闪烁判"系统还活着" | np2kai 的光标闪烁是模拟器驱动，CPU HLT 时照样闪 | 同上，别用光标 |
| `xdotool key` 对模拟器无效 | `--window` 与 `windowactivate` 两种都试过，无回显 | 放弃键盘路线；一律走 "改 AUTOEXEC + 重定向 + 截屏" |

### 7.6 新增可复用工具（在 /tmp/cw_diag/）

| 文件 | 用途 |
|---|---|
| `build_k.sh` | `build_k.sh "<DBGEXTRAS>" <out.sys>`：重编 52 obj + wlink + exeflat，一步出 sys |
| `show_file.py` | `show_file.py <hdi> <8.3名> [扩展名]`：从 FAT 镜像直接按 8.3 名 dump 文件内容（读 `CW.LOG` 等必备） |
| `cfg_min.sys` / `cfg_dev.sys` / `cfg_doshigh.sys` / `cfg_emm.sys` / `cfg_jemm.sys` | 5 种可切换 FDCONFIG 模板 |

**最佳诊断回路（已固化）**：
```bash
python3 /tmp/cw_diag/swap_kernel.py <新 sys> /tmp/fdhyb_B2R.hdi
python3 /tmp/cw_diag/set_autoexec.py '@ECHO OFF
DEL A:\CW.LOG
CWTEST.EXE > CW.LOG
ECHO STG-3-RET'
/tmp/cw_diag/run_test.sh /tmp/cw_diag/cfg_dev.sys /tmp/cw_diag/t_xxx 25
python3 /tmp/cw_diag/show_file.py /tmp/fdhyb_B2R.hdi CW LOG      # 绕开屏幕滚动
convert /tmp/cw_diag/t_xxx/f_24.png -resize 200% ...            # 读最后 24 行标记阶梯
ps -o pcpu -p $(pgrep -x wxnp21kai)                             # 1% = HLT 停机
```

### 7.7 本轮之后剩余的真问题（重新排序）

1. **停机点定位**：`!P9`/`!M`/`!P1` 全都能返回，说明内核侧 FAT 路径没问题；停机紧跟在一串 CW 噪声输出之后 → **优先怀疑 CW32/DPMI 侧**（PM 里执行 HLT 或 DPMI 退出路径异常），而不是 DOS 的 FAT 路径。
2. **验证"PM 反射下 create"到底行不行**：本轮已出现 `!C ... c`（create 成功返回），需要单独做一次"第一步就 create"的探针来确认 §2.1 的"create 必挂"是否仍成立。
3. **`DOS=HIGH` 崩溃**（自建内核 `MoveKernelToHMA` 返回后崩）仍是独立问题，与 step2c 无关，可后置。
4. 收尾清理项不变（见 §四.6）。


### 7.8 决定性 A/B：挂死与自建内核无关（本轮收官结论）

**实验 A：去掉 `_Exec` 探针后重建 CWTEST**
- `api.asm` 的 `_Exec` 探针块（原 L6507-6754：open→读0→读2→seek0x1FE→69h→create→write 0x400→close→reopen→delete→句柄7 读）用 `IFNDEF NOPROBE` / `ENDIF` 包住，只括住成对的 `push ax`/`pushf`…`popf`/`pop ax`，因此不定义 NOPROBE 时行为与之前**逐字节等价**。
- 重建：`wasm -zq -dPERMBIG1 -dPERMNOVM=1 -dENGLISH=1 -dNOPROBE -fo=cw32_chk2.obj cw32.asm && wlink system dos file cw32_chk2.obj name cw32_chk2.exe` → **100224B**（带探针版 cw32_chk.exe = 100944B，正好少 720B）→ `resplice.py`（header 0x1b0→0x1d0，stub2=0x187a0）→ `cwtestB.exe` 119976B → `inject_cwtest5.py`。
- 结果：cfg_dev 启动后**仍挂**，`CW.LOG` size=0，`CWOK.TXT` 不存在。

**实验 B（决定性）：换回原版压缩内核 KWC8616.SYS（49938B）**
- 从镜像内读出 KWC8616.SYS → 以 `KERNEL.SYS` 写回根目录（`make_fdtest.put`），配合同一份 `cfg_dev.sys`、同一份探针-free CWTEST。
- 结果：**与自建内核表现完全一致** —— 屏幕 `FreeCom ver 0.85a_DBCS …` / `STG-1` / `SABCDEFJMNKLPVWXYZabcdefghij`，`CW.LOG` size=0，`CWOK.TXT` 不存在。
- ⇒ **step2c 的挂死与"自建调试内核"无关**。内核侧 `!T/!O/!K/!e/!Y/!M/!P1/!P3/!P9` 阶梯（§7.4）已证明 FAT 全链路健康，这部分结论不受影响。

**谜团解开：之前的"CW 噪声字母"其实是 CW 启动标记**
- `FJMNKLPVWXZabcdefghi` 这类字母来自 [cw32.asm](file:///tmp/cwbuild/cw32.asm#L887-L897) 的 `dbgchar`（`int 29h` + 8251 双写），标记字母 `S A B C D E F … Z a b c … u` 是 extender 启动各阶段。
- 屏幕只显示到 `j`（`k` 之后处于零 IDT 窗口，标记改走串口 `dbgser`，只上串口不上屏）；串口是唯一能看全的通道。

**串口 frontier（两套内核一致）**
- 串口尾部：`… vwx7 IRTU6yz (×6) Q12390 v%M-c*45 IRTU6yz(×6) 1239`，之后**永久静默**（3 秒内日志长度不变）。
- 标记 `v` = post-`fPhysicalGetPage`（[cw32.asm:2088](file:///tmp/cwbuild/cw32.asm#L2088)）、`w` = post-1st `fCR3Flush`（[2104](file:///tmp/cwbuild/cw32.asm#L2104)）、`x` = post-2nd `fCR3Flush`（[2115](file:///tmp/cwbuild/cw32.asm#L2115)）。
- **`'8'`（"init done → cwOpen"，[cw32.asm:3821](file:///tmp/cwbuild/cw32.asm#L3821)）从未出现** ⇒ 死点被夹在 **cw32.asm L2115 … L3821 之间**。
- 串口里 `SABCDEF…u` 整块重复 5-6 次、每次都带不同的 `v%M-x*` 十六进制尾巴；原版内核同样重复 ⇒ 是 extender 自身（`pmacc` 16 字节缓冲 + `pmdump` 重放，[cw32.asm:899-936](file:///tmp/cwbuild/cw32.asm#L899-L936)）的假象，不是内核反复重启它。

**停机性质（修正 §7.5 的判据）**
- INT0 停机点插 `mov al,'H'; int 29h`、iosys INT6 停机点插 `'I'` 的永久刷屏标记（`kernel_dsys_h1.sys`）**都没有出现 H/I 墙** ⇒ 不是 `entry.asm thats_it: hlt` 或 `kernel.asm .sys_halt` 路径。
- `np2_hB2.toml` 里 `EmuSpeed = 100`（模拟器按 PC-98 实速节流），因此 **`ps` 的 CPU% 不能当 HLT 判据**（本轮同一静止画面先读到 1%、后读到瞬时 33%）。

**下一步（重新聚焦）**
> 注：以下 1–4 是上一轮的计划；本轮已把死点压到 0205→0305 这一步，**现行计划以 §7.9 为准**，此处保留仅为记录。
1. 在 `cw32.asm` **L2115 … L3821** 之间逐段插密集标记（`dbgser` 单字母，每 ~10 条指令一个），一跑就能把死点压到几十字节内。
2. 该区间主要是 RM→PM 交接后的重组/搬移/`cwOpen` 前的收尾；结合之前的 `Exception 0D`（`CR0=…011` / `CR3=0x33C5000`）判断大概率是 **GDT/选择子或页表描述符在 PC-98 VX 上不成立**。
3. 从头重建 cw32 的命令（本轮已验证）：`wasm -zq -dPERMBIG1 -dPERMNOVM=1 -dENGLISH=1 [-dNOPROBE] -fo=x.obj cw32.asm` + `wlink system dos file x.obj name x.exe` + `resplice.py <x.exe>` + `inject_cwtest5.py`。
4. 盘上现状：`KERNEL.SYS = KWC8616.SYS`（原版压缩，49938B）、`FDCONFIG.SYS = cfg_dev.sys`、`CWTEST.EXE` = 探针-free 119976B；需要继续内核实验时用 `swap_kernel.py` 换回 `kernel_dsys_*.sys`。

### 7.9 2026-10-31 第三轮：崩溃点已压到「0205 安装后进入新向量」这一步（交接版）

> 本节是新一轮对话的完整交接：**问题在哪、已证到什么程度、还剩什么没证、复建与复现命令**。
> 所有路径均为当前实际使用位置（`/tmp` 下，重启即失，重建方法见 7.9.6）。

#### 7.9.1 精确定位结果（有串口原始证据）

带 0205 安装（正常构建）：
```
... >0E17 S Q D r  >0E19 S Q D r  >0E20 S Q D r  >0E21 S Q D r
    >0E22 >0E23 >0E28 >0E29 >0E30 A3a >0E31 h S >002B:000A h K T E 1!...2  ← 复位环
```
对照实验（把 `cw32.asm` 的 0205 改成 `db 90h` 跳过安装）：
```
... >0E31 hS Q 5D r >0E24 ...        ← 0305 本身完全正常
    随后 retf dpmiCodeSel:PatchExc 处崩：h K T E     ← 同因，换了个入口而已
```
结论：
1. `>0E30` 之前全部正常；`>0E24`（0305 返回点）从不出现。
2. **崩溃发生在 `int 31h AX=0305h` 内部把控制交给新装向量那一刻**，不是 0305 的实现（跳过 0205 时 0305 能正常返回）。
3. `>0E31` 后的 `h S` 是 `IntHandler`→`IntStack`，`>002B:000A` 是 `IntStack` 从 `InterruptTable` 取到的目标：**偏移 0x000A 正确**（`cwAPIpatch` 在 `_apiCode` 中的偏移），**选择器 0x002B 是问题所在**。
4. 崩溃时 CPL 实测 = 3（探针 `A3a` 输出 `3`），排除「PL0 调 DPL3 目标」这类浅层解释。

#### 7.9.2 根因分析：0x2B 是 GDT 选择器，落到 DPL0 代码段

对照 [strucs.inc](file:///tmp/cwprobe1/strucs.inc#L97-L138) 的选择器常量表：

| 选择器 | index | 指向 | DPL |
|---|---|---|---|
| `0x2B`（实测目标） | GDT 5 | `KernalCS0` = Kernal PL0 代码段 | **0** |
| `0x2F`（应有值） | LDT 5 | 000Ch 刚写好的 API 代码段 | 3 |

- 选择器 = `index*8 | TI(bit2) | RPL(bit0-1)`。LDT 第 5 项必须是 `0x28 | 4 | 3 = 0x2F`；实测 `0x2B = 0x28 | 3`，**TI 位（bit2）丢了** → CPU 改去 GDT 查第 5 项。
- GDT 第 5 项是 `KernalCS0`（`DescPresent+DescPL0+...ERCode`，[cw32.asm](file:///tmp/cwprobe1/cw32.asm#L1585-L1594)），DPL0。
- 当前 CPL=3，`iretd` 装 CS=0x2B → **#GP(0)**（权限不足）→ `ExcepNN386`（`E`）→ 复位环 `h K T E`。这与现象 100% 吻合，且是确定性故障，不是竞态。
- 该假设同时解释了对照实验：跳过 0205 后 0305 能返回（无新向量），但随后的 `retf dpmiCodeSel:PatchExc` 用同一个 0x2B 选择器 → 同样 #GP。

#### 7.9.3 尚未解释的唯一矛盾（下一轮第一件事）

按源码，选择器不应该是 0x2B：

- [ldt.asm](file:///tmp/cwprobe1/ldt.asm#L75-L78) `RawGetDescriptors` 结尾是 `or ax,3+4`；反汇编确认实际指令为 `66 83 C8 07`（`or eax,7`），**返回值低 3 位必然为 `111`**，所以 `0x2B` 在数学上不可能由它产生。
- [cw32.asm](file:///tmp/cwprobe1/cw32.asm#L3775-L3780) 调用 `int 31h AX=0000h` 分配选择器，紧接 `mov dpmiCodeSel,ax`；[cw32.asm](file:///tmp/cwprobe1/cw32.asm#L3865-L3875) 用 `mov cx,dpmiCodeSel` + `mov ax,205h` 安装。
- 也就是说：**要么 `dpmiCodeSel` 在中途被别的代码覆盖，要么实际运行的 `RawGetDescriptors` 不是当前二进制反汇编的那一份**（例如运行时拷贝/旧 raw 副本）。

三个定点探针（最小验证，按顺序做）：
1. **P1**：`cw32.asm` L3779（`int 31h` 之后、`mov dpmiCodeSel,ax` 之前）用 `push ax; call xtrace` 打印分配返回值。期望 `>002F`。
2. **P2**：L3871（`mov cx,dpmiCodeSel` 之后、`int 31h` 之前）打印 CX。若 P1=0x2F 而 P2=0x2B → 中间被覆盖，顺着 `dpmiCodeSel` 的写入点查（`cw32.asm` 5834 定义，写入点仅 3780）。
3. **P3**（可选）：000Ch 之后读 LDT index 5 描述符的 access 字节（`0xFA` = PL3 代码，`0xF2` = RW 数据），确认 000C 真写进去了。

判定分支：
- P1=0x2B → 怀疑运行时 raw 代码副本（查 `RAWCopyCheck` 和两份 raw 代码映像），需要在 `00C3` 代码副本里核对 `or eax,7` 是否存在。
- P1=0x2F 且 P2=0x2F → 则 0x2B 是 `RawSetVector` 写表时被裁剪/写错（核对 `RawSetVector` 的 `66 89 4B 04` 与 6 字节表项排布）。
- 修好后必须回归：`>0E31 hS Q D r >0E24`（无异常）。

#### 7.9.4 本轮已排除的候选（不要重复验证）

| 候选 | 结论 | 证据 |
|---|---|---|
| VMM 交换文件/`PERMNOVM` | 已排除 | 该路径被跳过 |
| 内存池 page alias / `fPhysicalGetPages` | 已排除 | `>0D01…>0D06` 全过 |
| API 代码拷贝、数据选择器创建 | 已排除 | `>0E20` 已过 |
| 000Ch 描述符写入路径本身 | 已排除 | `>0E17` 在 000C 之后；`RawBPutDescriptor` 的 `and si,0fff8h` 正确落到 LDT index5 |
| LDT limit 不够（index5 越界） | 已排除 | GDT 里 `KernalLDT` limit = `8192*8`（[cw32.asm](file:///tmp/cwprobe1/cw32.asm#L3130-L3147)），覆盖 index5 |
| 0204/0205/0501/0600/0000/0305 各分支实现 | 已排除 | 对照实验 + 逐分支探针 |
| 探针副作用导致复位 | 已排除 | 干净构建同样复位 |

#### 7.9.5 本轮踩坑（复建/复现必读）

1. **`/tmp/cwprobe1` 的 LDT 清零计数被调试代码破坏**：`mov ecx,ebp`（[cw32.asm](file:///tmp/cwprobe1/cw32.asm#L2958-L2963)）时 EBP 已被前面的 DBG 循环改成 **1024**，而正确值应是 `(8192*8)+8192 = 73728`。`/tmp/cwclean3`、`/tmp/cwclean4` 都是正确的 73728。⇒ **在 cwprobe1 上得到的“分配/描述符”类结论，必须在 cwclean4 上复核一次**。
2. **`fmark` / `fhex2` 是 `retf` 空桩**：所有 `db 66h call cs:f[fmark]` 形式的标记（`P`、`+`、`o`、`D`、`k` 等）**全部失效、无输出**；只有直调 `dbgser`/`dbgser2` 或 inline 端口探针有效。
3. **PM 下不能写 `cs:`**：CS 是只读代码段，写必 fault。PM 后期探针只能“纯端口发送 + pushfd/cli/…/popfd 保护”。
4. **`/tmp/cw_diag` 是硬链接**：`ls -l /tmp/cw_diag -> /home/edo/inuse/cw_diag`（traceback 里显示的是 inuse 路径）。构建树必须 `cp -a` 并比对 inode，否则改的不是同一份。
5. **探针必须 `cli`**：在 `IntStack` 构帧期间耗时过长且 IF 未关会导致中断再入，历史上出现过 4MB 的 `'3'` 日志洪流。

#### 7.9.6 交接：环境、命令、文件

**串口链路（必须保持存活）**
- `pty_hold.py` 常驻进程持有 pty 主端（从端 `/dev/pts/3`，见 `com1path.txt`），把收到的字节追加写到 `/tmp/cw_diag/ser_capture.log`。
- 每轮开跑前先清空：`: > /tmp/cw_diag/ser_capture.log`；跑完直接 `tail -c 2000` 看尾部。

**构建 / 运行**
```bash
# 构建（树参数化；cwclean3 用于最终验证，cwprobe1 用于探针）
EXTRA_DEFS=-dNOXMS bash /tmp/cw_diag/build_clean.sh /tmp/cwprobe1

# 运行（脚本内部会 patch FDCONFIG.SYS 到 /tmp/fdhyb_B2R.hdi 并每 2s 截图）
bash /tmp/cw_diag/run_test.sh /tmp/cw_diag/cfg_min.sys /tmp/out_xxx 10
```
- `build_clean.sh` = `wasm … cw32.asm` → `wlink` → `resplice.py` → `inject_cwtest5.py`（写 HDI 的 CWTEST 目录项，大小随探针增长，当前 124576B 量级）。
- 判据（step2c）：屏显 `CWTEST OK` + HDI 根目录存在 `CWOK.TXT`。

**树与脚本**
| 路径 | 用途 |
|---|---|
| `/tmp/cwprobe1` | 全探针诊断树（当前状态：全部探针在位、0205 已恢复为 `mov ax,205h/int 31h`） |
| `/tmp/cwclean4` | 半探针基线（`dbgser` 可用，其余 stub） |
| `/tmp/cwclean3` | 全静默干净树，**最终验证专用**（clear 计数 73728 已修） |
| `/tmp/cw_diag/probe_cpl.py` | `_cwInit` 侧 CPL 探针（'A'+CPL+'a'） |
| `/tmp/cw_diag/probe_api.py` | `api.asm` 内 'B'/'C'/'N' 探针 |
| `/tmp/cw_diag/probe_int.py`、`probe_int2.py` | `interrup.asm` 内 'S'/'T'/'U'/'h'/'K'/'E' 探针 |
| `/tmp/cw_diag/probe_target2.py` | `IntStack` 目标 `>sel:off` 打印（**唯一有效版本**；`probe_target.py` 已废弃，其 32 位 hex 打印有 nibble bug） |
| `/tmp/fdhyb_B2R.hdi` | 262MB 测试镜像（当前 `FDCONFIG.SYS` 由最后一次 run_test 决定） |

**当前探针字符含义**
`h`=`IntHandler`、`S`=`IntStack`、`K`=`KernalStack`、`T`=`IntDispatch`、`E`=`ExcepNN386`、`Q`=`RawDPMIPatch` 入口、`5`=`@@DPMI_0305`、`D`=`@@Done_RawDPMIPatch`、`r`=`iretd` 前、`B`/`C`/`N`=`cwAPIpatch` 内、`>`+4hex=`xtrace` 行标。

#### 7.9.7 下一步（严格顺序）

1. 按 7.9.3 做 P1/P2 两个探针，锁定 `0x2B` 的产生位置（预计 1 次构建 + 1 次运行即可区分三分支）。
2. 按根因修复（补 TI 位 / 查覆盖 / 查运行时副本），先在 cwprobe1 复现 `>0E31 hS Q D r >0E24`（无 `h K T E`）。
3. 用 `/tmp/cwclean3` 两配置各跑一轮验证两条判据（`cfg_min.sys` 的 NOXMS 版 + 默认含 HIMEMX 版）。
4. 回填本节（把“假设”改为“结论 + 修复 diff”）。
5. 收尾 A 开关（NOXMS/NOCONV）文档化；**保持 `/tmp/cwbuild` 工作副本原状不动**。

#### 7.9.8 盘上/工作区现状

- HDI：`/tmp/fdhyb_B2R.hdi`（262MB），根目录无 `CWOK.TXT`/`CW.LOG`（本轮尚未成功）。
- 最后一次实跑用的是 `cfg_min.sys`（NOXMS），构建树 `/tmp/cwprobe1`，串口尾部即 7.9.1 的复位环。
- 尚未对 `/tmp/cwclean3` 做任何改动；它仍是可直接用于最终验证的干净树。

---

### 7.10 2026-10-31 第四轮：上游源码核对 + `or ax,4` 空结果（0x2B 不在处理器 AX 里）

#### 7.10.1 上游源码获得方式（Codeberg 可用，GitHub 不可用）

- 权威镜像：`https://codeberg.org/tkchia/causeway`（分支 `master`，源码在 `source/all/`）。
- **`WebFetch` 会被 Codeberg 以 UA 拦截**（返回 `Access denied, old Chrome version.`）；GitHub raw 直取亦返回空。
- 可用方式是走 Codeberg REST API + `curl`（需 `dangerouslyDisableSandbox` 放行网络）：

```bash
curl -sS "https://codeberg.org/api/v1/repos/tkchia/causeway" | jq -r .default_branch   # master
curl -sS "https://codeberg.org/api/v1/repos/tkchia/causeway/contents/source/all?ref=master"
curl -sS "https://codeberg.org/tkchia/causeway/raw/branch/master/source/all/<file>" -o /tmp/cwupstream/<file>
```

已落盘到 `/tmp/cwupstream/`：`ldt.asm`、`raw_vcpi.asm`、`interrup.asm`、`cw32.asm`、`cw.inc`、`strucs.inc`、`general.inc`。

#### 7.10.2 上游核对结论：本地三文件**无逻辑偏离**

用「去注释 + 去标签 + 去 `@@` 本地标号 + 小写归一」的语义 diff（脚本 `/tmp/norm_diff.py`）：

| 文件 | 差异性质 | 结论 |
|---|---|---|
| `ldt.asm` | 仅 `@@N:` → `@@N_RawGetDescriptors:` 改名 | **一致**；上游同样 `or ax,3+4`、单选择器走 `index*8│7` |
| `raw_vcpi.asm` | 主要是 DBG 探针；`@@DPMI_0000` 逐行同上游 | **一致**（`push ebx/push eax/call RawGetDescriptors/pop ebx/mov bx,ax/mov eax,ebx/pop ebx/clc`） |
| `interrup.asm` | 只有标签改名、DBG 探针（`h/s/k/t/u/e/>`）、以及 `test cs:dpmiemusystemflags,1` → `test cs:d[...],1` 的**尺寸限定符补正**（语义等价）、`ifdef contrib` 段删除 | **一致**，返回帧处理未被本地改坏 |

⇒ 7.9.3 的三分支中，**A（运行时代码与源码不同）在源码层被排除**；本地构建与原版 CauseWay 语义等价。

#### 7.10.3 探针实测（三条硬结论）

1. **P1 = `002B`、P2 = `002B`**（`P1` 在 `int 31h AX=0000h` 之后打印 AX，`P2` 在 0205h 之前打印 CX）。⇒ DPMI `0000h` 交付给客户端的 AX 就是 `0x2B`，且 `dpmiCodeSel` 从落地起就是 `0x2B`，排除 B（变量被中途覆盖）。
2. 在 `RawGetDescriptors` 入口打 `R`、出口（`@@2: pop eax` 之后）打 `X`：串口只出现 `Q R D r`，**`X` 一次都没有**。⇒ 该调用**没有走到 `@@2` 成功路径**（函数在 `@@8: stc` 分支提前返回），而 `@@DPMI_0000` 结尾的 `clc` 把失败掩盖成「成功」。
3. 在 `raw_vcpi.asm` 的 `@@DPMI_0000` 中 `call RawGetDescriptors` 之后插入 `or ax,4`（已确认汇编进 exe：`66 83 c8 04`，紧接 `call` 之后、`pop ebx` 之前）：**P1 仍为 `002B`，P2 仍为 `002B`**。⇒ 客户端看到的 AX **不来自处理器的 AX 寄存器**，`or` 在处理器里改了也传不出去。

补充：给 `@@DPMI_0000` 加「A + 4 位十六进制」打印时，串口在 `Q R` 之后立即出现 `h K T E`（异常/复位），说明此刻在 `_cwDPMIEMU` 段尾部追加代码会踩到边界（`ldt.asm` 是 `raw_vcpi.asm` 末尾 include 的最后一个文件，代码就贴在段尾）。**后续探针不要加在 `ldt.asm`/段尾，只加在 `@@DPMI_0000` 附近的单字符标记。**

#### 7.10.4 重新表述的问题（下一轮第一件事）

新问题变成两问：

1. `int 31h AX=0000h` 真的进了 `@@DPMI_0000` 吗？（若 AH 非 0，会跳到 `@@DPMI_0100` 等分支，`or ax,4` 自然不执行）
2. 处理器返回后，客户端 AX 是从哪个槽位写回的？（`IntDispatch` 的 `@@resume_intdispatch` 路径按 16 位/32 位客户机分叉，需确认实际走的是哪条）

对应的最小探针（**只加单字符，不加循环/不加 `_cwDPMIEMU` 尾部代码**）：

- `P3`：在 `RawDPMIPatch` 入口（本地 2790 附近，`Q` 打印处）按 AH 分支打 `0`/`1`–`9`，确认 `AH==0`；
- `P4`：在 `@@resume_intdispatch` 入口打 `#`，并在其后紧接打 `+`/`-` 表示此刻 AL 的 bit2 是否为 1；
- `P5`（若需要）：在 `@@DPMI_0000` 的 `clc` 之前打 `c`、在 `@@8` 路径打 `s`，确认到底走了哪条。

#### 7.10.5 本轮盘上变更（可回滚）

- `/tmp/cwprobe1/cw32.asm`：新增 `pval`（L944-977，经 `dbgser` 输出 `P<tag>:hhhh`，保存 ax/bx/cx/si 与 FLAGS）、`P1`（L3816-3817）、`P2`（L3911-3913）。
- `/tmp/cwprobe1/ldt.asm`：入口/出口探针**已回滚**，现与上游等价。
- `/tmp/cwprobe1/raw_vcpi.asm`：`@@DPMI_0000` 的 `or ax,4` 仍**留在树上**（空结果，待后续移除或改为真正修复）。
- `/tmp/cwupstream/`：上游源码快照（新增）。

