# refdoc 001：FreeDOS(98) 基座生态——源码/镜像拆解与对当前行动的帮助评估

**日期**：2026-10-29
**来源**：lpproj（bauxite.sakura.ne.jp）+ tori 原版 FreeDOS(98)，均为公开 GitHub 仓库/Release
**范围**：仅基座生态（文档+源码+镜像）。galgame 引擎与 archive.org 商业镜像按指示排除。
**关联**：[devdoc 178](file:///home/edo/naiz/devdocs/178-Naiz部署链开源化规划-CauseWay-FreeDOS98-CTMOUSE.md) step2、[devdoc 187](file:///home/edo/naiz/devdocs/187-CWTEST冒烟调查现状-kernel67h陷阱与stub静默退出追凶.md)

---

## 一、资产清单

### 1.1 源码与镜像 → /media/edo/data/studysource/

| 路径 | 内容 | 大小 |
|---|---|---|
| `fdkernel/fdkernel_source_test-20220120.zip` + 已解包 `fdkernel-test-20220120-cherrypick/` | **kernel 完整源码**（C+asm，Watcom 构建） | 806KB |
| `fdkernel/fdkernel_dbcs-20220120-bin.zip` + 已解包 `bin/` | 预编译 kernel（ibmpc/ + nec98/，含 KWC8616/8632/18632 等 8 个变体） | 716KB |
| `fdkernel/bin/nec98/KWC8616.sys` | **与我们盘上 KERNEL.SYS 逐字节相同**（cmp 验证） | 49938B |
| `images/FD98_HD_250M.hdi`（已解包） | 官方 250MB 基座镜像；**尺寸 262168576B 与我们 /tmp/fdhyb_B2R.hdi 完全一致** | 250MB |
| `images/fd98_hd_250m_20220123.zip` / `fd98_2hd144_20220123.zip` | 上述镜像的原始压缩包（后者含 2HD/1.44M 软盘启动镜像） | 4MB/743KB |
| `freecom_dbcs2/`（src+bin） | FreeCom 0.85a DBCS 源码+预编译（我们盘上的 COMMAND.COM） | 1.3MB |
| `emm386_nec/`（src+bin） | EMM386(98) v2.26 源码+预编译 | 330KB |
| `himemx_nec/`（src+bin） | HimemX 3.34 NEC98 移植源码+预编译（FDCONFIG 在用的 XMS 驱动） | 44KB |

### 1.2 文档原文 → /home/edo/naiz/docs/refdocs/raw/

| 文件 | 内容 |
|---|---|
| `nec98int.txt` | FreeDOS(98) 对 PC-98 特有中断的支持矩阵（INT DCh 内部 DOS 功能为主） |
| `fdkernel_nec98_history.txt` | fdkernel NEC98 分支更新史 |
| `sys_fd98.txt`（Shift-JIS） | SYS.COM 用法 + **kernel 内建 CONFIG 参数说明**（替代 CONFIG.SYS 的机制） |
| `emm386_NEC98.txt`（Shift-JIS） | EMM386(98) README：明确警告 UMB 相关**不完整** |
| `bauxite_freedos.htm` | lpproj 配布页全量快照 |
| `tori_freedos.htm` | （下载失败待补）tori 原版页面 |

上游链接：fdkernel [仓库](https://github.com/lpproj/fdkernel/tree/nec98test) / [release test-20220120-cherrypick](https://github.com/lpproj/fdkernel/releases)；[FreeCOM dbcs2](https://github.com/lpproj/freecom_dbcs2/)；[emm386.nec](https://github.com/lpproj/emm386.nec)；[himemx.nec](https://github.com/lpproj/himemx.nec/)；[bauxite 配布页](http://bauxite.sakura.ne.jp/software/dos/freedos.htm)；[tori 原版](http://www.retropc.net/tori/freedos/)。

---

## 二、核心拆解发现（源码级，直接改写 devdoc 187 的结论）

### 2.1 版本同源性（铁证）

`cmp bin/nec98/KWC8616.sys /tmp/cwtest/kernel_sys.bin` → **IDENTICAL**。我们 B2R 盘 = 官方 fd98_hd_250m_20220123 衍生（尺寸亦同）。今后任何 kernel 行为都可直接查源码，不再黑盒猜。

### 2.2 INT 陷阱机制全貌（devdoc 187 §二的源码级定案）

**安装点**：[nec98/kernel/main.c:311-316](file:///media/edo/data/studysource/fdkernel/fdkernel-test-20220120-cherrypick/nec98/kernel/main.c#L311-L316)

```c
for (i = 0x23; i <= 0x3f; i++)  setvec(i, empty_handler);        // 静默 iret
for (i = 0x40; i <= 0xfe; i++)  setvec(i, unhandled_int_handler_iosys);  // PANIC 陷阱，0x67 在内
setvec(0x05, int5_handler);                                      // COPY 键
setvec(0x06, int6_handler);                                      // STOP 键 / #UD
```

- **0x40–0xFE 全部向量默认指向 PANIC 陷阱**——不是专门针对 67h 的设计，而是"未实现一律 PANIC"策略。
- 处理器实现：[nec98/kernel/kernel.asm:456-486](file:///media/edo/data/studysource/fdkernel/fdkernel-test-20220120-cherrypick/nec98/kernel/kernel.asm#L456-L486)，打印 `PANIC - Unhandled INT ??h. Stack:` 后跳 `con_put_and_dump`。
- **`con_put_and_dump`（kernel.asm:419-442）转储顺序修正**：`[bp+0]`=IP、`[bp+1]`=CS、随后 flags+栈 13 词；结束执行 **`mov ax,04c7fh / int 21h` = 以 errorlevel 127 终止当前进程**（不是 halt，失败才 `.sys_halt`）。→ 一切 PANIC/Invalid Opcode 后"回到提示符"的行为由此解释。
- **`_int6_handler`（kernel.asm:362-446）双语义**：若返回地址前是 `int 06h` 指令（`[bx-2]==0x06CD`）→ STOP 键语义（收 HDD 磁头/Ctrl-C）后 iret；否则按真 #UD 打印 `Invalid Opcode at ` + 13 词转储 + **4C7F 终止**。
- **devdoc 187 的"垃圾 IVT 向量跳转"假说需要修正**："Invalid Opcode at 012E" 的 012E 是**第一转储词 = 故障 IP**，084C 是**第二词 = 故障 CS**（此前误读为 seg:off 且算错线性地址）。线性地址 = 0x84C*16 + 0x12E = **0x85EE**，很可能是 CWTEST 加载段内偏移 0x12E——**#UD 大概率发生在 stub 代码段内部**，而非跳进 kernel 数据区。
- （注：stub_blob 0x12E 对应文件区为 0，故故障段未必是入口段；精确归属待 udspy2 抓现行后闭环。）

### 2.3 由此打开的两条新修复路线（都比 TSR 绕过更根治）

1. **诊断构建 kernel**：改 main.c 让 0x40–0xFE 陷阱对特定向量（67h）改为静默 iret 或日志，用仓库自带 Watcom 构建系统重编 KWC8616.SYS 换入盘内。风险低（可回滚），信息量大。
2. **正式产品路线**：开源基座的 FDCONFIG 里若仍需避开 kernel 陷阱，UNTRAP67 类 TSR 仍是首选（零 kernel 修改）；但"未实现向量=PANIC"的 kernel 行为必须写入 devdoc，任何走 VCPI/EMS 探测的 extender 在此基座上都会踩雷。

### 2.4 文档要点摘译

- `emm386_NEC98.txt`：EMM386(98) 自述"MS-DOS 上 UMB 关系不完整"，且需要 1.6MB+ RAM——我们实验中 EMM386+CWTEST 死于 `INT ??h`（PANIC 占位符）与此相符：EMM386 自身会探测/挂接未实现向量区。
- `sys_fd98.txt`：kernel 配置经 SYS.COM 写入 KERNEL.SYS 尾部参数区（非 CONFIG.SYS），修改基座行为时应注意该机制。
- `nec98int.txt`：INT DCh（内部 DOS 功能）有完整支持矩阵；未实现功能调用会挂系统——别在诊断 TSR 里乱用 DC 系列。

---

## 三、对当前行动（step2）的帮助评估

| 资产 | 帮助 | 具体动作 |
|---|---|---|
| fdkernel 源码 | **决定性** | ①已完成：INT 陷阱机制定案+转储顺序修正；②下一步：诊断构建 kernel（改 67h 行为）验证 stub 假说；③step4 基座改版时可注入自定义默认 handler |
| 官方 HDI | 高 | diff 我们 B2R 盘 vs 官方镜像，确认所有改动可复现（step4 开源基座的合规前提） |
| KWC8616.SYS 等多变体 | 中 | FAT32/386 变体或许行为不同（kernel.asm 有 IBMPC/NEC98 条件编译差异），作为对照实验备选 |
| FreeCOM 源码 | 中 | 解释 AUTOEXEC 批处理/错误级行为；排查 MARK-A/B 类问题时可查 |
| EMM386 源码 | 中 | 若最终必须支持 EMS 路线，读它怎么挂向量、为什么和 stub 冲突 |
| HimemX 源码 | 低 | 当前仅作 XMS 驱动，无已知冲突 |
| nec98int/history 文档 | 低-中 | 背景知识 |

## 四、遗留事项

- tori_freedos.htm 抓取失败（retropc.net 可能限速），补抓非必需。
- HDI 全盘 diff（官方 vs B2R）未做，step4 前完成。
- kernel 诊断构建的可行性（本机 Open Watcom v2 能否编 fdkernel）未验证，属 step2 修复路线评估的一部分。
