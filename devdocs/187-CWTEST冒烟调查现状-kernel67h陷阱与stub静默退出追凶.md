# devdoc 187：CWTEST 冒烟调查现状——kernel INT 67h 陷阱定案与 stub 静默退出追凶

**日期**：2026-10-29
**状态**：调查进行中（step2 未通过，根因链已破案 60%，剩余"静默退出"谜团定位中）
**上游文档**：[devdoc 178](file:///home/edo/naiz/devdocs/178-Naiz部署链开源化规划-CauseWay-FreeDOS98-CTMOUSE.md)（主规划，step2=CauseWay 冒烟测试）、[devdoc 185](file:///home/edo/naiz/devdocs/185-Naiz部署双管线-开源资源包与开源基座-可选择不取代.md)（step4-7 依据）
**本文作用**：固化 step2 全部实验证据、根因结论、工具资产与工作法，供后续 session 无损接续。

---

## 一、任务定义与验收标准

**step2**：CauseWay 冒烟测试——在 NP2kai 模拟器（pc_model='VX'，FreeDOS(98) kernel build 2043-DBCS 基座盘）上，让一个 `wcl386 -l=causeway` 构建的 32-bit PM 测试程序（CWTEST）正常启动、执行、输出、退出。

**验收**：CWTEST 在屏幕上打印预期输出（t2.c 版本为 `CWTEST OK`）并干净返回 COMMAND.COM 提示符。通过后进入 step2d（BGM/ISR 剖面冒烟）。

**为什么必须过这关**：Naiz 引擎本体与 CWTEST 走完全相同的构建/加载链（wcl386 + CauseWay stub + PM 切换），CWTEST 不通则引擎必不通。

---

## 二、根因链（已定案）

### 2.1 最初 panic 的直接死因：kernel INT 67h 陷阱

- FreeDOS(98) kernel build 2043-DBCS（WATCOMC，OEM 0xfd，sava 移植）把**未挂接的 INT 67h 指向自身 PANIC 陷阱（0060:2702）**，打印 `PANIC - Unhandled INT 67h. Stack:` + 13 字栈转储后**终止程序**。
- **实证**：hello2.asm 实模式探针读 IVT 得 `V67=0060:2702`，随后裸发 `int 67h` 即触发 PANIC（截图 cwB2R_hello2.png）。
- 消息文本在 KERNEL.SYS 中以**逐字符立即数构串**存在（0x813 处找到 `PANI\xFFC - Unha\xF6ndle` 模式），且 **KERNEL.SYS 本体加壳/加密**——这就是早期明文扫描找不到 "PANIC" 字串的原因。
- 同一机制解释了 EMM386 实验中 `INT ??h` 的占位符（INT 号动态填入）。

### 2.2 INT 67h 的触发源：CauseWay stub ChkVCPI 无条件探测

- stub 启动流程（/tmp/cwbuild/cw32.asm，stsp causeway v3.60 源码汇编产物）：
  - [cw32.asm:809](file:///tmp/cwbuild/cw32.asm#L809) `CheckProcessor`——**纯 flags 探测**（pushf/popf 位 12-15 判 8086/286），**不依赖 int6**，386 直接通过；
  - [cw32.asm:831](file:///tmp/cwbuild/cw32.asm#L831) `GetProtectedType`：ChkDPMI（int 2Fh/1687h）→ ChkVCPI（int 67h/0DE00h）→ ChkRAW（smsw 查 CR0.PE）；
  - `ChkVCPI`（[cw32.asm:4489-4526](file:///tmp/cwbuild/cw32.asm#L4489-L4526)：仅当 IVT 67h 向量==0000:0000 时自装 DummyIRET，随后**无条件** `int 67h` 发 0DE00h 探测——kernel 陷阱因此被击中。
- 已排除：DPMI 误判（ChkDPMI 判定正确，hello3 探针证明 kernel 对 int 2Fh/1687h 静默忽略 AX 不变）、重建 stub 自身 bug（原版 v4.05 stub 同样死法）、CPU 型号（VX 模式）。

### 2.3 环境模拟方案：UNTRAP67 钩 67h

- **UNTRAP67.COM**（21 字节手写 TSR）：`int 67h` → `mov ax,0FF84h / iret`。AL=84h≠0 使 ChkVCPI 的 `cmp al,0 / jne @@NotThere` 稳定走"VCPI 缺席"路径——等价于真实无 EMS 的 PC-98 环境。
- 失败的备选（记录在案，勿重试）：EMM386 2.26（加载成功但死于 `INT ??h` 变体）、JEMM386（boot 黑屏挂死）。

---

## 三、当前谜团：绕过 67h 陷阱后，行为随 int6 处理者变化

### 3.1 实验矩阵

| # | TSR（UNTRAP67.COM 槽位内容） | int6 handler | int67h handler | CWTEST.EXE 槽位内容 | 结果 |
|---|---|---|---|---|---|
| 1 | 无 | kernel | kernel 陷阱 | 原版 cwtest.exe（v4.05 cwc'd） | `PANIC - Unhandled INT 67h` 终止 |
| 2 | 21B COM 版（只钩 67h） | kernel | FF84h 返回 | 重建版 cwtest_rebuilt.exe（116592B） | 两代 stub 均死于 kernel `Invalid Opcode at 012E`（#UD，INT 6） |
| 3 | udspy67.exe 170B（钩 6h+67h，DS=PSP bug 修复后） | 我们的 print+HLT | FF84h | cwtest_rebuilt.exe | `U6` 打出，CWTEST **静默退出**（详见 3.2） |
| 4 | udspy2.exe 265B（钩 21h/6h/67h） | 我们的 print+HLT | FF84h | cwtest2.exe（66904B，含文件探针） | `U2` 打出后**机器挂死**（我方 TSR 疑似 bug，见 §六） |

**关键观察**：实验 2 与 3 的唯一环境差异 = int6 向量指向谁 + TSR 内存布局。行为从"#UD 崩溃"变成"静默退出"。

### 3.2 实验 3 的完整证据（cwB2R_mark.png / cwB2R_probe.png）

AUTOEXEC（B2R 盘实测内容）：

```
@ECHO OFF
DEL ED.TXT
DEL RN.TXT
UNTRAP67.COM
ECHO MARK-A
CWTEST.EXE
ECHO MARK-B
```

屏幕结果：两条 DEL 文件未找到提示（预期）→ `U6`（TSR 安装标记）→ `MARK-A` → `MARK-B` → `A:\>` 提示符。**无 CWTEST 任何输出，无错误，无 PANIC，无 Invalid Opcode。**

进一步判定（cwtest2.exe = t2f.c 文件探针版：`fopen("CWOK.TXT","wb")` 写文件 + `printf("CWTEST OK\n")`）：**盘上无 CWOK.TXT** → PM 程序**根本没被执行**（fopen 都没发生），而非"跑了但输出丢失"。

### 3.3 已锁定的排除结论

1. **不是 InitError 静默退出**：InitError 全部路径都会打印（实模式 AH=9 打印 `CauseWay error ??` + 消息后 exit，[cw32.asm:3624-3646](file:///tmp/cwbuild/cw32.asm#L3624-L3646)；DPMI 路径经 int 31h/0300h 模拟打印）。
2. **是干净的 int 21h/4Ch 退出**：MARK-B 打出 = 进程经 DOS 正常终止。stub 的所有终止路径（正常+错误）汇于 cwClose 的 `mov ah,4Ch / int 21h`（[cw32.asm:444-451](file:///tmp/cwbuild/cw32.asm#L444-L451)），且 `TerminationHandler dd offset InitError`（[cw32.asm:627](file:///tmp/cwbuild/cw32.asm#L627)）——IErrorNumber=0 时 InitError 是**静默**退出（`cmp IErrorNumber,0 / jz @@NoError_InitError`）。**因此"静默 4Ch 退出"完全可能是走了 InitError(IErrorNumber=0) 或 cwClose 正常路径**。
3. **stub 保护模式类型选择**：DPMI=no（kernel 静默忽略 1687h，AX 不变≠0）→ VCPI=no（FF84h）→ RAW=yes（smsw 查 CR0.PE=0 恒真）→ `SetProtectedType` 取 **ProtectedType=0（RAW 自切换）**，[cw32.asm:4440-4443](file:///tmp/cwbuild/cw32.asm#L4440-L4443)。
4. **旧 #UD 崩溃点特征**：`Invalid Opcode at 012E`——故障 CS=012E，线性地址 0x1B2C（0x012E*16+0x84C），不是正常加载段；推测某调用经垃圾向量跳进 kernel 数据区执行。13 字寄存器转储格式与 stub 的 ExcepNN386（[cw32.asm:1372-1609](file:///tmp/cwbuild/cw32.asm#L1372-L1609)）不符 → 打印者确为 kernel int6 handler，#UD 发生在**实模式**。

### 3.4 两个竞争假说

- **假说 A（int6 依赖）**：stub/加载流程某处依赖 int6 行为（例如 CPU 探测的 #UD 陷阱法）。但 CheckProcessor 已确认是 flags 法不碰 int6，RAW 路径也未发现 int6 依赖——**此假说目前证据薄弱**。
- **假说 B（内存布局敏感）**：TSR 从 21B COM 变为 170B EXE 后，CWTEST 加载段、stub 内部数据落点全部平移，某处读到的垃圾值/边界条件改变，导致走上不同分支。假说 B 与"两次死法完全不同"更自洽。
- **判别手段**（进行中）：抓 `AH=4Ch` 时的 CS:IP + 退出码，映射回 stub 内部偏移即可知道走的是哪条退出路径（InitError(0)？cwClose？还是别的）。

---

## 四、工具资产清单

### 4.1 探针/TSR（/tmp/cwtest/）

| 文件 | 说明 | 状态 |
|---|---|---|
| hello.asm / hello.exe | 最小实模式 int29 打印探针 | ✅ 用过 |
| hello2.asm | 读 IVT 67h 向量打印 + 裸发 int67h | ✅ 实证 V67=0060:2702 + PANIC |
| hello3.asm | DPMI 探针（2Fh/1687h，先存返回值再打印） | ✅ 实证 kernel 静默忽略，无崩溃 |
| untrap67.com | 21B 手写 TSR：int67h→FF84h | ✅ 验证有效（实验 2 环境） |
| udspy67.asm/.exe | int6 间谍（打印故障 CS:IP+8 字节操作码后 HLT）+ int67h 钩 | ✅ 修复 DS=PSP bug 后工作正常 |
| udspy2.asm/.exe | 在 udspy67 基础上加 int21h AH=4Ch 记录器（打印 `X <IP>:<CS> <rc>` 后链回） | ⚠️ 链回代码疑似 bug 致挂死（§六） |
| t2.c / t2f.c | CWTEST 源：`printf("CWTEST OK\n")`；t2f 加 CWOK.TXT 文件写入 | ✅ |
| kernel_sys.bin | 从盘提取的 KERNEL.SYS（49938B，簇 2-14） | 逆向用 |

**udspy67 关键教训（EXE TSR 必写）**：EXE 入口 DS=PSP≠CS，钩中断前必须 `push cs / pop ds`，否则 `mov ax,25XXh` 写入的向量是 PSP:offset（垃圾）。这是实验中段"无声挂死"的根因，已修复并加 `U6` 安装标记。

### 4.2 注入与诊断脚本（/tmp/cw_diag/）

| 文件 | 说明 |
|---|---|
| inject_udspy.py | 注入 UNTRAP67.COM←udspy、CWTEST.EXE←cwtest_rebuilt（overwrite_entry 模式） |
| set_autoexec.py | 重写 AUTOEXEC.BAT 内容（用法：`python3 set_autoexec.py '@ECHO OFF\n...'`） |
| dump_b2r_files.py | 列根目录 + 读 AUTOEXEC/FDCONFIG 内容 |
| boot_cap.sh | 杀模拟器→启动 NP2kai→xdotool 找 640x459 窗→import 截图（用法：`timeout 20 bash boot_cap.sh 16 out.png`） |
| extract_cwtest.py 等 | 从 HDI 提取 CWTEST/kernel 的历史脚本 |

**FAT 注入标准模式**（fat.py 是 re-export 层，真 API 在 fat_fs.py/fat_table.py）：

```python
import sys; sys.path.insert(0, '/home/edo/naiz')
from tools.naiz_img.hdi import HDIImage
from tools.naiz_img.fat import NAIZFatFS, make_alloc_fn
img = HDIImage('/tmp/fdhyb_B2R.hdi'); fs = NAIZFatFS(img)
fat = fs.read_fat_list(); alloc = make_alloc_fn(fat, NAIZFatFS.alloc_next_free(fat, 2))
root = fs.read_root()
off = fs.find_entry_offset(root, b'CWTEST  ', b'EXE')      # 8.3 名必须空格补齐
fs.overwrite_entry(root, off, data, fat, alloc)
fs.write_root(root); fs.write_fat(fat); img.save('/tmp/fdhyb_B2R.hdi')
```

**B2R 盘布局**（曾因偏移读错误报 FAT 双副本不一致，特此固化）：FAT16 BPB 在 **0x12000**（0x11000 是 IPL1 区）；bps=512 spc=8 reserved=2 nfats=2 rootents=3072 spf=250 tot32=511904；fat1=0x12400 fat2=0x31800 root=0x50c00 data=0x68c00；簇 4096B；**FAT1==FAT2 恒等**。

### 4.3 截图证据（/tmp/cw_diag/）

cwB2R_hello2.png（V67+PANIC）、cwB2R_emm.png（EMM386 INT ??h）、cwB2R_untrap.png（Invalid Opcode 012E）、cwB2R_orig.png（原版同死）、cwB2R_dpmi.png（hello3 ALIVE）、cwB2R_udspy.png（DS bug 挂死）、cwB2R_udspy2.png（U6+静默退出）、cwB2R_mark.png（MARK-A/B 版）、cwB2R_probe.png（cwtest2 版）、cwB2R_xit.png（U2 挂死）。

---

## 五、构建工作法（踩坑固化）

1. **Watcom 环境**：`source /home/edo/naiz/core/detect_watcom.sh` 只设 WATCOM+PATH，**不设 INCLUDE**——wcl386 编 C 必须手动 `export INCLUDE=$WATCOM/h`，否则报 E1014/W131 假错。
2. **小 EXE**：`wasm -bt=dos -fo=x.obj x.asm && wlink format dos file x.obj name x.exe`（W1014 stack segment 警告无害）。
3. **CWTEST 构建**：`cd /tmp/cwtest && wcl386 -bt=dos -l=causeway -zq -os -s t2f.c -fe=cwtest2.exe`。stub 经 PATH 解析到 **~/watcom-extras/cwstub.exe（47152B）**；注意 /tmp/cwbuild/cwstub.exe（47120B）是 cwsrc 包自带另一份，/tmp/cwbuild/cw32.exe（97195B）是**扩展器本体**（cw32.asm 编译产物）不是 stub。core/Makefile 有 cwstub 存在性门禁（W1093 防线）。
4. **NP2kai 工作法**：`pkill -9 -x wxnp21kai` 清场（defunct PID 511953 永存无害）；boot_cap.sh 可能因 X/xdotool 瞬时故障卡住——外层必包 `timeout`，卡死先查截图文件存在性再重试；np2_hB2.toml: pc_model='VX'、SCSIHDD0='/tmp/fdhyb_B2R.hdi'。
5. **EXE 挂 .COM 名可用**：FreeDOS kernel EXEC 按 MZ magic 判格式，与扩展名无关（实验 3 证实 udspy67.exe 挂 UNTRAP67.COM 名正常按 EXE 装载）。

---

## 六、进行中：udspy2 挂死（下一步第一件事）

**现象**：实验 4，`U2` 打出后连 MARK-A 都没出现 → 挂死点在 TSR 安装后的**第一次 int 21h 调用**（DEL 命令）。

**嫌疑**：int21h 链回代码：

```asm
chain21:
        push    word ptr cs:old21s
        push    word ptr cs:old21o
        retf
```

理论推演该序列正确（retf 弹掉两个 push 后，原 FLAGS/CS/IP 帧完好）。待办：`objdump -D -b binary -m i8086` 反汇编 udspy2.exe 验证 wasm 对 `push word ptr cs:label` 的实际编码（疑点：wasm 可能没生成 CS override 或操作数尺寸错）。稳妥替代写法（不依赖语法糖）：

```asm
chain21:
        push    ds
        mov     ax, cs
        mov     ds, ax
        les     bp, [old21vec]          ; old21vec dd ?（off+seg）
        pop     ds
        push    es
        push    bp
        retf
```

（DS 在钩内被临时改动但已恢复，老 handler 与 IRET 均不受影响。）

---

## 七、下一步计划（顺序）

1. **修 udspy2 链回 bug** → 注入重测 → 抓 `X <IP>:<CS> <rc>` 退出点。
2. **映射 CS:IP**：由退出 CS 算 stub 加载段（CWTEST PSP+stub），把 IP 对应回 cw32.exe 内偏移，反汇编确认走的是哪条退出路径（InitError(0)？cwClose？还是 3452 行 `IProtectedMode==0 → @@RealMode_InitError` 这类特殊分支）。
3. **判定假说 A/B**，定位 #UD 垃圾向量来源（嫌疑：stub 在 RAW 路径某处 far-call 了未保存/被 kernel 重写的向量）。
4. **定修复方案**（候选：扩展 UNTRAP 钩住更多垃圾向量 / 调整 stub raw 路径 / 给 kernel 补真实默认 handler）。
5. CWTEST 打出 `CWTEST OK` + CWOK.TXT 落盘 → step2 通过 → step2d（BGM+ISR 剖面冒烟）→ step4-8 按 devdoc 178/185 推进。
6. **step8 收尾时必须写入 devdoc**：kernel INT 67h 陷阱机制、ChkVCPI 无条件探测、UNTRAP67 方案、FAT 误报教训、udspy 定位过程、EXE TSR 的 DS=PSP 坑、detect_watcom.sh 不含 INCLUDE 的坑。

---

## 八、教训备忘

1. **"文件不存在=脚本没跑成"不成立**：boot_cap.sh 挂死时截图可能已生成——先查文件。
2. **EXE vs COM 的 DS 语义差异**是 TSR 开发第一大坑，安装标记（`U6`/`U2`）值得成为所有诊断 TSR 的标配。
3. **扫描加密/加壳二进制**：key-invariant XOR-difference 签名扫描（`(a[i]^a[i+1])==w[i]^w[i+1]` 向量化）同时覆盖 XOR/NOT 编码；逐字符构串用带间隙正则（`P.{0,6}?A.{0,6}?N...`）。
4. **一次只改一个变量**：实验 2→3 同时变了 int6 handler 和内存布局，导致假说分叉——后续判别实验应控制变量。
5. **盘面诊断先看目录再猜**：dump_b2r_files.py 式的"列目录+读内容"应先于任何行为推断。
