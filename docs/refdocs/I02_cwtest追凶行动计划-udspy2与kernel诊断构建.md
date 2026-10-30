# refdoc I02：CWTEST 追凶行动计划——udspy2 抓 4Ch 退出点 + fdkernel 诊断构建

**日期**：2026-10-29
**性质**：行动计划 + 执行记录（执行后回填 §五）
**依赖**：[I01](file:///home/edo/naiz/docs/refdocs/I01_freedos98_base_sources.md)（kernel 源码落盘）、[devdoc 187](file:///home/edo/naiz/devdocs/187-CWTEST冒烟调查现状-kernel67h陷阱与stub静默退出追凶.md)（调查现状）

---

## 一、已知事实（压缩自 devdoc 187）

1. kernel 把 IVT 0x40–0xFE 全指到 PANIC 陷阱（[main.c:313-316](file:///media/edo/data/studysource/fdkernel/fdkernel-test-20220120-cherrypick/nec98/kernel/main.c#L313-L316)）；PANIC 与 #UD 转储均以 `int 21h/4C7Fh` 终止进程（errorlevel 127）。
2. 转储顺序 = 先 IP 后 CS。旧崩溃 #UD：CS=084C，IP=012E（线性 0x85EE，疑似 stub 代码段内）。
3. UNTRAP67（int67h→FF84h）绕过陷阱后，行为随 int6 handler/内存布局变化：kernel int6 → #UD at 012E；我们的 udspy6 → CWTEST 静默退出（PM 程序未跑，无 CWOK.TXT）。
4. stub 路径判定：DPMI=no / VCPI=no / RAW=yes → ProtectedType=0。InitError(IErrorNumber=0) 是静默 4Ch 退出（[cw32.asm:627,3624-3646](file:///tmp/cwbuild/cw32.asm#L627)）；所有终止汇于 cwClose 4Ch（cw32.asm:444-451）。
5. udspy2（int21h 4Ch 记录器）首次实测挂死于第一次 int21h（DEL）——链回代码疑似 wasm 编码问题。

## 二、判别逻辑（抓到 `X <IP4>:<CS4> <rc>` 后怎么读）

| 现象 | 判定 |
|---|---|
| rc=0x7F | kernel con_put_and_dump 终止（PANIC/#UD 发生但在我们的 TSR 环境下）→ IP/CS 指向故障点 |
| rc=0 且 IP 落在 stub 的 InitError 区 | 静默 InitError(0) 退出 → 查 IErrorNumber 置 0 的上游分支 |
| rc=0 且 IP=程序正常退出点 | stub 认为程序"正常结束"——查 PM 切换失败被当正常退出的路径 |
| 4Ch 从未被调用但 MARK-B 已打 | 退出走了非 4Ch 路径（int20h 或 KeepExec）——扩钩子 |
| 抓到 X 但后续挂死 | 打印本身破坏了状态（int29h 在 int21h 内嵌套）→ 打印改缓冲后置 |

## 三、线 A：udspy2 修复与 4Ch 捕获

1. **反汇编 udspy2.exe** 验证 `push word ptr cs:old21s / push / retf` 实际编码。
2. **修复**：链回改为绝对远跳 `db 0EAh / dw old21o / dw old21s`（8086 兼容，零语法糖；flags 帧不动，老 handler 的 iret 语义不变）。
3. 保留打印在链回前（int29h 直写控制台，不动 DOS 栈）。
4. 构建：`source detect_watcom.sh && wasm -bt=dos … && wlink format dos …`。
5. 注入 B2R：UNTRAP67.COM←udspy2、CWTEST.EXE←cwtest2.exe（AUTOEXEC 不变：DEL/DEL/UNTRAP67/MARK-A/CWTEST/MARK-B）。
6. `timeout 90 boot_cap.sh 16 cwB2R_x2.png` → 读 X 行 → 按上表判定 → 映射回 cw32.exe 偏移。

## 四、线 B：fdkernel 诊断构建（kernel 级根治验证）

1. 审 build 系统（config.b / makefile / build 脚本；确认 wcc/wasm/wmake + nasm 需求）。
2. 本机 Watcom 直接构建原版 KWC8616.SYS，与官方 bin 比对（能复现=构建链健康）。
3. 诊断补丁（最小）：[main.c](file:///media/edo/data/studysource/fdkernel/fdkernel-test-20220120-cherrypick/nec98/kernel/main.c) 的 0x40–0xFE 循环后追加 `setvec(0x67, ems_absent_handler)`，handler=`mov ax,0FF84h / iret`（kernel 内建 UNTRAP67 语义，AL=84h≠0 令 ChkVCPI 稳定走 raw 路径）。
4. 构建失败回退：二进制 patch 官方 KWC8616.sys（定位 `B8 7F 4C CD 21` 锚点附近 handler 入口改 `B8 84 FF CF`）。
5. 注入诊断 kernel 到 B2R → **AUTOEXEC 去掉 UNTRAP67 行**（隔离变量：kernel+无 TSR）→ CWTEST 实测。
   - 通过 → 67h 陷阱理论完全闭环，且得到无 TSR 的干净基线；TSR 方案保留为零侵入产品路线。
   - 仍失败 → 崩溃点与 67h 无关，转查 stub RAW 自切换路径（假说 B 内存布局线）。

## 五、执行记录（回填区）

- [ ] 线A：反汇编 → 修复 → 注入 → 截图 → 判定
- [ ] 线B：构建系统审查 → 构建验证 → 补丁 → 注入 → 截图 → 判定
- [ ] 结论回写 devdoc 187/178
