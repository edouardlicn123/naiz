# 189 - CWTEST追凶第三轮：FAT获取挂死锁定 + 自建调试内核

> 交接文档。上一份：188-CWTEST追凶第二轮。上游：178（主规划）、185。
> 本文档供下一对话**直接续做**，含全部可复用命令与当前卡点。

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
