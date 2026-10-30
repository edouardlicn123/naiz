# devdoc 188 — CWTEST 追凶第二轮：kernel EXEC 排除与 stub 内部聚焦

日期：2026-10-29
上游：[devdoc 187](file:///home/edo/naiz/devdocs/187-CWTEST冒烟调查现状-kernel67h陷阱与stub静默退出追凶.md)、[I02 行动计划](file:///home/edo/naiz/docs/refdocs/I02_cwtest追凶行动计划-udspy2与kernel诊断构建.md)
状态：**step2 进行中；旧根因假说被实验排除，嫌疑收敛到 stub 内部初始化流程**

---

## 一、结论速览

1. **旧假说（kernel EXEC 不追加程序路径串 → stub 读垃圾文件名 → 盘级 int24h）被实验排除。**
   kernel 2043 DBCS 的 EXEC 路径串写入**完全正确**（格式、位置、内容全部符合标准约定与 CauseWay 期望）。
2. **GetEXECName 的解析算法与 kernel env 布局逐字节吻合**，用 COM 程序 1:1 复刻该算法 + 3D40h open，在 FreeCom EXEC 同场景下**一次成功**。
3. 因此 CWTEST 的 Critical Error 必然出在 **stub 内部更深处**：AH=4Ah resize → CheckProcessor → CheckDOSVersion → GetEXECName → GetSystemFlags → GetProtectedType 这条链的前半段，或 PM 自切换路径。头号嫌疑：**AH=4Ah resize**（[cw32.asm:789-795](file:///tmp/cwbuild/cw32.asm#L789-L795)）。
4. 补丁载体已解决一半：**官方 stub 是压缩形态无法直接补丁；wasm 构建的未压缩 cw32.exe 可作替代 stub**，但 wcl386 不认它（见 §四），wlink 直接指定 stub 的语法待解决。

## 二、实验证据（本轮新增）

### E1：ENVSPY2 落盘 env 段（决定性证据）
ENVSPY2.COM 由 FreeCom EXEC，把自己 PSP:2Ch 指向的 env 段 1024B 写入 A:\ENV.DAT，镜像读回解码：

```
0x0000: PATH=. / PROMPT=$P$G / TZ=JST-9 / COMSPEC=A:\COMMAND.COM
0x0032: 00 00                     <- env 正常 double-zero 结束
0x0034: 01 00                     <- extra-strings word count = 1
0x0036: "A:\UNTRAP67.COM"        <- kernel 追加的完整路径串 ✓
0x0046: 00                        <- 路径串结束符 ✓
0x0047-0x00A7: 垃圾残留（分配块未清零，非 kernel 写入）
0x00A8: 00 00                     <- 第二个 double-zero（内存残留巧合）
```
- env seg=073D，PSP=084C（E2 实测）。env 块在 PSP 下方独立分配。
- 源码对照：[task.c:133-212 ChildEnv](file:///media/edo/data/studysource/fdkernel/fdkernel-test-20220120-cherrypick/kernel/task.c#L133-L212)——`word count=1` + `truename()` 后 `fstrcpy` 路径串，与盘上数据完全一致。

### E2：PL.COM 复刻 GetEXECName + open
1:1 复刻 [cw32.asm:4200-4250 GetEXECName](file:///tmp/cwbuild/cw32.asm#L4200-L4250) 的 byte-scan 连续双零 + `add si,3` 跳 word count 算法，再执行 GetSystemFlags 的 3D40h open：

```
P084C  E074B  A:\UNTRAP67.COM  O  D
```
即：解析出正确路径串，open 成功。**kernel EXEC 场景下 stub 前两个关键步骤的前置条件全部正常。**

### E3：cwc 转换尝试（失败但信息量大）
VM 内执行 `CWC.EXE /M2 /L85 CWTEST.EXE`（cw32.exe wasm 产物 97195B 原地转换）：
- **CWC 运行时自身调用 INT 67h → kernel 原生 PANIC "Unhandled INT 67h"**（此轮无 UNTRAP67 驻留，直接暴露 kernel 67h 陷阱）
- 转换未完成（读回 CWTEST.EXE 逐字节未变）。**CW 的官方工具链自己也过不了这台 kernel 的 67h 陷阱**——再次印证 step2 的必要性。

## 三、CauseWay 架构定案（源码 + 二进制验证）

- **CWTEST.EXE = [stub MZ image 47184B][3P app 数据]**。stub 的 MZ header（e_cp/e_cblp）声明自身镜像长度，stub 用它定位身后的 3P 数据；3P 头（'P3' 签名）在 app 数据尾部，stub 从**文件尾**反向找。
- 官方 `~/watcom-extras/cwstub.exe`（47152B，Watcom 附带）= **cwc 压缩后的 stub**：搜不到 'CauseWay error' 等明文串 → **无法二进制补丁**。
- `/tmp/cwbuild/cw32.exe`（97195B，wasm+wlink 构建自 cw32.asm）= **未压缩完整 extender MZ**：MZ image=全文件、'CauseWay error' @1210。**它可以直接当 stub 用**（MZ 自洽），且可自由改源码重建——**这是我们的补丁载体**。
- `cw32.exe`（makefile 流程 ml → link → cwc /m2 /l85）与 `cwstub.exe` 同源：cwstub 是 cw32 的压缩/转换发行形态。EXESPLIT 可把 extended app 拆成 extender image + app image 两半（COPY /B 可替换 extender）。
- GetSystemFlags 的 cmdtail 解析（cw32.asm:4339-4407 @@SetRUN）只用于"文件尾无 'P3' 数据"时把第一个命令行参数当程序名——与本次死因无关（喂参数无效已实证）。

## 四、工具链现状与卡点

| 项 | 状态 |
|---|---|
| wasm 构建cw32.obj/cw32.exe | ✅ `wasm -bt=dos -fo=x.obj x.asm`（必须 `-bt=dos` 否则出 ELF `.o`） |
| wlink COM 小程序 | ✅ `wlink format dos com file x.obj name x.exe` |
| wcl386 链 CWTEST | ✅ `export WATCOM=/usr INCLUDE=/usr/h PATH=/usr/binl:$PATH; wcl386 -bt=dos -l=causeway -zq -os -s t2f.c -fe=x.exe` |
| **wcl386 认新 stub** | ❌ 替换 ~/watcom-extras/cwstub.exe 后 wcl386 产出仍是官方压缩 stub（cwtest3 与 cwtest2 前 0xb95f 字节全同；wcl386 重构 MZ header +32B，stub 查找逻辑不走 PATH 上我们放的文件） |
| **wlink 直接指定 stub** | ❌ `format causeway` 语法不存在（E3033）；wlink 二进制内有 `STUB/NOSTUB/getStubNamePtr_/_DOSDefStub` 符号——**正确子句待查**（候选：`op stub=文件`、`system causeway`、或 dos 格式 + `op stub=`） |
| stsp/causeway github | ❌ clone 三次均超时（网络不稳），放弃；本地 cwsrc 包（原版 v4.05 发布源码）够用 |
| VM 内 cwc 转换 | ❌ 被 kernel 67h PANIC 打断（E3）；若装 UNTRAP67（FF84h 应答版）理论上可过，作为备选 |

注意：~/watcom-extras/cwstub.exe 已恢复官方版（备份：/tmp/cwtest/cwstub_official.exe.bak）。

## 五、下一步路线（按优先级）

1. **解决 wlink stub 指定语法**（`strings /usr/binl/wlink` 有 STUB 符号；试 `op stub=` / `option stub=` / 查 OW 手册），用未压缩 cw32.exe 直接链出 cwtest4.exe。
2. **未压缩 stub 版 CWTEST 上 VM 冒烟**：压缩 stub 死得无声，未压缩 stub 预期能打出 `CauseWay error: NN` 或走到 PM 切换——**死点直接浮出**。
3. 按 NN 映射 cw32.asm：1=4Ah resize 失败、2=非386、3=无 PM 路径、4=DOS 版本、5=PM 切换、6=VCPI、7=DPMI——**锁定后改 cw32.asm 源码打补丁重建**（wasm 链路已通），这正是 step2 的"重建 stub"主线。
4. 若 NN 指向 4Ah：对照 [inthndlr.c AH=4Ah DosMemChange](file:///media/edo/data/studysource/fdkernel/fdkernel-test-20220120-cherrypick/kernel/inthndlr.c) 与 stub `_cwEnd` 计算（cw32.asm:790-793），判断是 kernel bug 还是 stub 尺寸声明问题。
5. 线B（fdkernel 本机 Watcom 诊断构建）保持待命；若补丁面超出 stub 范围则升级为主线。
6. 通过标准不变：**CWTEST OK + CWOK.TXT 落盘** → step2d（BGM+ISR 剖面）→ step4-8。

## 六、step2 通过后的既定动作（不变）

回填 I02 §五 + devdoc 187 修订（int21h 钩子禁忌、EXE TSR DX+10h、int29h 破坏 CX/SI、kernel EXEC 排除链）→ step2d → step4 开源基座 HDI → step5-8。
