# 70 — Deepin 系统鼠标光标中央限制问题诊断与修复

> 版本：0.2.013（修复完成）
> 状态：阶段 1（诊断）+ 阶段 2（修复）均已完成；GUI 最终效果待物理鼠标确认

## 1. 问题现象

- **平台**：Deepin 23.1（beige，KWin/dde-kwin 合成器，X11 会话）
- **模拟器**：`/usr/local/bin/wxnp21kai`（NP2kai wx_alpha 分支，wxWidgets 3.2.6 + GTK3 3.24 deepin 打包版）
- **现象**：模拟器中的虚拟鼠标光标被限制在屏幕中央的一小块区域内移动，超出后会被拉回中心。
- **范围**：仅 Deepin 系统出现；Linux Mint 等其他发行版同版二进制无此问题。

## 2. 背景

### 2.1 鼠标三路架构（devdocs 0.1 总结 #58）

引擎 `core/plat/mouse.c` 三路优先级：

1. **NP2 系统端口绝对坐标**（最高优先级，P5 补丁 `05-wx-mouse-abspos.patch`）：读端口 `0x7E0–0x7E3` 获得宿主绝对坐标，无漂移无需滤波。
2. **INT 33h**（中优先级，实体 PC-98 + QMOUSE）：`_asm{int 33h}` 内联汇编，VM/DPMI 下不可靠。
3. **8255 PPI 增量**（回退，完整滤波链：死区±2/帧限幅±50/方向确认 3/recenter）。

NP2kai 检测成功后优先走路径 1。`mouse_recenter_if_idle()` 对 `mouse_np2kai` 直接 return（无引擎侧拉回逻辑）。

### 2.2 P5 补丁宿主侧实现

`tools/np2kaipatch/05-wx-mouse-abspos.patch` 基于 NP2kai `wx_alpha` 分支修改 4 个文件：

- `io/np2sysp.c`：移除 `#if defined(NP2_WIN)` 门控，非 Windows 也走 `mousemng_getabspos()`；新增端口 `0x7E0=X低/0x7E1=X高/0x7E2=Y低/0x7E3=Y高` 只读 handler。
- `wx/mousemng.cpp` / `wx/mousemng.h`：新增 `mousemng_setabspos()/mousemng_getabspos()`（静态 `mouse_abs_x/y`）。
- `wx/np2panel.cpp`：`OnMouseMove` 中新增绝对坐标追踪块（`pos.x*640/sz.GetWidth()` 缩放 + 钳位 + `mousemng_setabspos`）。

**关键：补丁只新增了绝对坐标追踪，`WarpPointer(cx, cy)` 拉回中心是 NP2kai 原有相对模式设计（diff 上下文无 `+`）。**

### 2.3 wx_alpha 分支 OnMouseMove 原始逻辑

```cpp
void Np2Panel::OnMouseMove(wxMouseEvent &evt) {
    if (!m_mouseCaptured) { evt.Skip(); return; }   // 仅捕获态处理
    wxPoint pos = evt.GetPosition();
    int cx = GetClientSize().x / 2;
    int cy = GetClientSize().y / 2;
    int dx = pos.x - m_lastMousePos.x;
    int dy = pos.y - m_lastMousePos.y;
    if (dx || dy) {
        mousemng_onmove(dx, dy);        // → 8255 相对增量
        WarpPointer(cx, cy);            // 宿主指针拉回窗口中心
        m_lastMousePos = wxPoint(cx, cy);
    }
}
```

引擎经 0x7E0–0x7E3 读取的是 `mousemng_setabspos()` 写入的 `mouse_abs_x/y`，其值 = 每次移动事件时的 `pos`（缩放后）。

## 3. 根因分析（阶段 1 推断）

### 3.1 机制

WarpPointer 在 X11 下经 XWarpPointer 实现，**会合成新的 MotionNotify 事件**。在标准合成器上 warp 立即原子生效，合成事件坐标 ≈ 窗口中心，与 `m_lastMousePos` 相同 → `dx=dy=0` → 被 `if (dx||dy)` 过滤，无害。

Deepin 使用 KWin（dde-kwin）合成器，对 XWarpPointer 的处理**非原子**（延迟/分步/重投递合成事件流）。warp 产生的中间合成事件坐标介于原位置与中心之间，携带**非零 dx/dy**，被 `OnMouseMove` 当作真实移动：

- `mousemng_onmove(dx, dy)` 累加假相对位移；
- `mousemng_setabspos(sx, sy)` 被覆盖为靠近中心的坐标；

引擎软件光标（读绝对端口）被反复拖回中央 → 表现为"限制在中央一小块区域，超出被拉回"。

### 3.2 为什么其他发行版正常

Linux Mint 等发行版窗口管理器对 XWarpPointer 的处理为原子生效，合成事件 delta=0 被过滤，绝对坐标正常反映全范围移动。

### 3.3 排除项

- **引擎侧拉回**：NP2 路径 `mouse_recenter_if_idle()` 直接 return，校准逻辑仅在 8255 路径。排除。
- **显示缩放**：`evt.GetPosition()` 与 `GetClientSize()` 同为设备像素，比例一致，不产生"拉回"。排除。
- **补丁未生效**：二进制 `strings` 确认含 `mousemng_getabspos`，补丁 05 已应用。排除。

## 4. 诊断实证（阶段 1，已完成）

### 4.1 最小 wx 复现程序

`/tmp/opencode/warpdiag/warpdiag.cpp`（不入仓库）：完全复刻 NP2kai `OnMouseMove`
（捕获鼠标 → 读 pos → 算 dx/dy → 打印 → `WarpPointer(窗口中心)` → last=中心）。
wxGTK 3.2.6，Deepin X11。

### 4.2 实测事件序列（节选）

用 xdotool 驱动（单次 `mousemove` 为一步）：

```
CAPTURE last=(320,200)
mousemove → (321,200)  （xdotool 单步 1px）
 [.289] move pos=321,200 dx= 1 dy= 0 -> warp(320,200)   ← 真实移动
 [.312] move pos=316,200 dx=-4 dy= 0 -> warp(320,200)   ← warp 合成事件
 [.330] move pos=314,200 dx=-6 dy= 0 -> warp(320,200)   ← warp 合成事件
 [.382] move pos=321,200 dx= 1 dy= 0 -> warp(320,200)   ← warp 合成事件

mousemove → (60,200)（dx=-260 大位移）
 [.741] move pos= 60,200 dx=-260 dy= 0 -> warp(320,200)  ← 真实移动
 [.752] move pos=340,204 dx= 20 dy= 4                   ← warp 发散
 [.768] move pos=357,202 dx= 37 dy= 2                   ← warp 发散
 [.575]* pos=373,197 dx= 53 dy=-3                       ← 过冲峰值
 [.609] move pos=325,198 dx=  5 dy=-2                   ← 逐步收敛
 [.617] move pos=322,200 dx=  2 dy= 0                   ← 收敛至中心附近
```

### 4.3 结论（根因实证）

- KWin（dde-kwin）对 XWarpPointer 的**非原子处理**导致：每次 `WarpPointer(中心)`
  产生一串**携带非零 delta 的合成 motion 事件**（发散→过冲→收敛到中心）。
- 这些事件全部通过 `if (dx||dy)` 过滤，被当作真实移动：
  - `mousemng_onmove(dx,dy)` 累加假相对位移；
  - `mousemng_setabspos()` 绝对坐标被逐步覆盖为中心 → 引擎软件光标被"拖"回中央。
- 表现：光标只能在中央一小块移动，超出后被拉回 —— 与用户描述完全一致。
- 标准合成器（Linux Mint 等）：WarpPointer 原子生效，合成事件落在中心且与 last
  相同 → dx=dy=0 → 被过滤，事件流干净，光标正常全屏移动。

**结论：必须去掉 OnMouseMove 中的 WarpPointer。** 引擎路径 1 只用绝对坐标端口，
warp 冗余且是 deepin 上光标拉回的唯一来源。

## 5. 修复执行（阶段 2，2026-08-11）

### 5.1 修复目标

1. 补丁 05：OnMouseMove 去掉 `WarpPointer`（保留 `CaptureMouse()` 一次性 warp 初始化）。
2. 构建链路：让 `start.sh np2kai` 能基于 `wx_alpha` 分支重编译并自动应用补丁。
3. 重编译并安装 `wxnp21kai`，验证修复。

### 5.2 动作链时间线

1. **clone 源码**：`git clone --depth 1 --branch wx_alpha https://github.com/AZO234/NP2kai.git /tmp/NP2kai`（当前 HEAD `e2dc904`）。
2. **确认原补丁基线失配**：旧补丁 05 在新源码上 `git apply` 失败（np2sysp.c 上下文、np2panel.cpp 行序均已随上游变化）。
3. **重写补丁 05**：Python 脚本对 4 个文件做精确修改（每步校验锚点唯一性），再 `git diff` 生成新补丁；`git apply --check` + `apply` 在干净 HEAD 上双通过。
4. **修复构建链路**（3 个 Python 工具，见 5.3 问题表 #5/#6）。
5. **编译**（首次配置遇 USE_SDL 问题 → 改 `-DUSE_SDL=3`；编译遇 `#endif` 缺失 → 修复）→ 0 errors。
6. **运行时验证**：引擎串口日志 + xdotool 驱动（遇 xdotool 注入失效，见问题表 #7）。
7. **收尾**：移除临时调试代码、重编最终版、恢复用户 toml 配置、更新文档、`bump_version`。
8. **安装**：`sudo cp /tmp/NP2kai/build_wx/wxnp21kai /usr/local/bin/wxnp21kai`（旧版备份为 `wxnp21kai.warp.bak`），sha256 与编译产物一致。

### 5.3 遇到的问题与解决

| # | 问题 | 现象 | 根因 | 解决 |
|---|------|------|------|------|
| 1 | 旧补丁 05 无法应用 | `git apply` 报 np2sysp.c:695、np2panel.cpp:197 上下文失配 | 上游 wx_alpha 已更新（np2panel warp/m_lastMousePos 行序颠倒、np2sysp 行号偏移） | 按新基线重写补丁并重新生成 |
| 2 | CMake 配置失败 | `SDL3::SDL3 target not found`（CMakeLists.txt:923） | `-DUSE_SDL=0` 使 find_package(SDL3) 不执行，但 `NP2kai_WX_base` 无条件链接 SDL3::SDL3 | `cmd_np2kai` 改用 `-DUSE_SDL=3`（依赖系统 `libsdl3-dev`/`libsdl3-ttf-dev`，deepin 已有） |
| 3 | 编译失败 | `np2sysp.c:947: unterminated #if` | 首次生成补丁时误删 NP2APPDEV 块的 `#endif` | 补回 `#endif` 并重新生成补丁；`#if`/`#endif` 计数 43/43 平衡 |
| 4 | diff 全文件重写 | `np2sysp.c` diff 显示 +1988/−988 行 | 上游文件 CRLF 行尾被 Python `io.open` 转成 LF（universal newlines） | 改用 bytes 模式处理（`\r\n→\n→\r\n`），diff 收敛为 65 insertions |
| 5 | 构建链路损坏（缺 wx 前端） | `cmd_np2kai` clone master 分支无 `wx/` | 官方 master 无 wx 前端；gitcode 镜像 `edouardlicn123/NP2kai` 已 403 | clone 固定 `--branch wx_alpha`；镜像行加失效注释（无可靠替代 URL） |
| 6 | 构建链路损坏（缺 git apply） | 文档声称自动 `git apply`，代码缺失 | B09 文档与实现不符；旧版二进制其实是早期手动打补丁编出来的 | 新增 `_apply_common_patches()`（按文件名序 apply、反向检查跳过已应用）并在 cmake 前调用 |
| 7 | xdotool 无法注入 wx 事件 | 临时 stderr 调试显示 CaptureMouse/OnMouseMove/setabspos 调用计数全 0（getabspos 348 次全返回 0 0） | deepin + xdotool 合成事件（click/mousemove/windowfocus/windowactivate）无法到达 wx 面板 | 属环境限制，非代码 bug；GUI 最终效果改由物理鼠标确认 |
| 8 | np2kai_serial import 失败 | `ModuleNotFoundError: naiz_lib` | `sys.path.insert(...'..','..')` 指向项目根，但 `naiz_lib` 在 `tools/` 下 | 本次用 `PYTHONPATH=tools` 绕过；属现存工具 bug，记入遗留项（未修） |
| 9 | 操作失误：`git stash drop` 误还原源码 | /tmp/NP2kai 源码回到干净 HEAD，补丁丢失（二进制未受影响） | 验证补丁时 `git apply --check` 不落盘，随后 `stash drop` 把带修改的 stash 删掉 | 重新 `git apply` 恢复；教训：`--check` 后勿 drop |
| 10 | 操作失误：`pkill -f` 自杀 | bash 命令超时被杀 | `pkill -f wxnp21kai` 匹配到命令行自身含该字符串 | 改用 `pkill -x wxnp21kai`（精确进程名） |

### 5.4 实际代码改动清单

**`tools/np2kaipatch/05-wx-mouse-abspos.patch`**（重写）：
- `io/np2sysp.c`：移除 `#if defined(NP2_WIN)` 门控；新增 `0x7E0–0x7E3` 只读 handler + `np2sysp_bind()` 注册；保留 NP2APPDEV `#endif`。
- `wx/mousemng.cpp` / `.h`：新增 `mouse_abs_x/y` 状态 + `mousemng_setabspos()/mousemng_getabspos()`。
- `wx/np2panel.cpp`：`OnMouseMove` 去 warp（`m_lastMousePos = pos` + 缩放钳位 + `setabspos`）；`CaptureMouse()` 保留一次性 warp。

**`tools/env_setup/env_utils.py`**：`_git_clone_with_retry` 新增 `branch` 参数；`_get_np2kai_source` clone 传 `branch="wx_alpha"`；mirror 行加 403 注释。

**`tools/env_setup/env_np2kai.py`**：新增 `_apply_common_patches()`；`cmd_np2kai()` 编译前调用它；CMake `-DUSE_SDL=0→3`；支持 `NAIZ_NP2KAI_REBUILD=1` 强制重编译。

**`tools/diag/np2kai_serial.py`**：新增 `NP2KAI_BIN` 环境变量覆盖 EMULATOR。

### 5.5 文档与版本

- B13 §8.3/8.4、B09 §2.2、FAQ §1.6、B91 §5.3、B90 已补"去 warp + wx_alpha + rebuild"说明
- `bump_version demo-a2`：0.2.012 → 0.2.013

## 6. 结果与验证

### 6.1 编译结果

- `cmake -S . -B build_wx -DBUILD_I286=OFF -DBUILD_WX=ON -DUSE_SDL=3 -DCMAKE_BUILD_TYPE=Release` 配置成功
- `cmake --build build_wx --target wxnp21kai -j` → **0 errors**；二进制含 `mousemng_getabspos/setabspos` 符号，`WarpPointer` 仅残留于 `CaptureMouse()`
- 新补丁在干净 wx_alpha HEAD（e2dc904）上 `git apply --check` + `apply` 双通过

### 6.2 运行时验证（引擎串口）

- 引擎日志确认 `np2=1`（NP2kai 系统端口路径激活），`[MOUSE] NP2 raw port: nx= ny=` 每帧输出
- `getabspos()` 被引擎高频调用（872 次/16 秒）→ **引擎侧绝对坐标读取链路完全活跃**
- 加临时 stderr 调试确认 xdotool 注入不到 wx 面板（见 5.3 #7）；**绝对坐标链路的最终端到端效果需物理鼠标确认**（已安装新二进制，待用户实测）

### 6.3 回归（含 2026-08-11 二次修复）

- 显示必需补丁 P1–P3、键盘 P4 未被触碰（独立补丁文件）
- `make -C core`：0 errors / 0 warnings；Python 工具全量语法检查通过

> **⚠️ 阶段 2 二次修复（黑白花屏回归）**：首次安装的"新版本"其实**只含 P5**（重写 P5 后在 /tmp/NP2kai 手动 `git apply` 05 并手工 cmake 编译，绕过了 `cmd_np2kai()` 的 `_apply_common_patches()` 全补丁链路），P1–P3（显示必需）、P4（键盘）全部丢失 → 进入引擎游戏时 VGA 图形合成不触发 + `GDCANALOG_256` 不置位调色板全黑，表现为**黑白花屏**。
  修复：对 `/tmp/NP2kai` `git apply` P1–P4（clean 通过），源码验证 `grphdisp |= 5`（memvga.c:40）、gdc_o6a 去门控（gdc.c）、`analogext(TRUE)`（bios18.c:347/390/986）、`WXK_SPACE→0x34`（kbtrans.cpp:43），重编译 0 errors，安装。
  教训：**重编译必须走完整补丁链路**（`NAIZ_NP2KAI_REBUILD=1 start.sh np2kai` 或全量 `git apply` 01–05），禁止只打单补丁手动编译。

### 6.4 安装状态

- `/usr/local/bin/wxnp21kai` 现为 **P1–P5 完整版**
  - 版本 1（修复前，含 P1–P3+P4+P5，显示正常/Deepin 鼠标受限）：备份 `wxnp21kai.warp.bak`
  - 版本 2（仅 P5，黑白花屏）：备份 `wxnp21kai.p5-only.bak`
  - 版本 3（当前，P1–P5 完整）：已安装
- sha256 与 `/tmp/NP2kai/build_wx/wxnp21kai` 完全一致（`ae2bc211…ceeb01`）；P5 符号 `mousemng_getabspos/setabspos` 在

## 7. 环境事实记录

- Deepin 23.1，`XDG_SESSION_TYPE=x11`，`DISPLAY=:0`
- wxnp21kai：wxGTK 3.2.6（`libwxgtk3.2-1 3.2.6+dfsg-2deepin1`）、GTK 3.24.41（deepin 打包）
- 构建源码 `/tmp/NP2kai`（wx_alpha 分支，HEAD `e2dc904`，已应用 P1–P5 补丁，工作区已清理临时调试代码）
- 官方 master `AZO234/NP2kai.git` 无 wx 前端；wx 代码在 `wx_alpha` 分支
- 本地 `/home/edo/NP2kai` 为官方 master checkout（SDL 前端），非 wx 构建源
- 系统具备 `libsdl3-dev`/`libsdl3-ttf-dev`（deepin 打包）、wxWidgets 3.2.6、`xdotool`、`cmake`
- 测试后已恢复 `~/.config/wxnp21kai/wxnp21kai.toml`（np2kai_serial 运行会以单引号风格重写该文件）

## 8. 遗留项

- `tools/diag/np2kai_serial.py:22-23` 的 `sys.path` 指向项目根，但 `naiz_lib` 在 `tools/` 下 → `from naiz_lib import` 必失败（实测 `ModuleNotFoundError`；`PYTHONPATH=tools` 可绕过）。未修。
- `tools/env_setup/env_utils.py` `_run_check()` 存在既有 `shell=True`（P7 规则），本次未触碰。
- gitcode 镜像 `edouardlicn123/NP2kai` 403 失效，已加注释，待提供可靠镜像地址后更新。
- **GUI 端到端验证**：物理鼠标实测"光标全屏移动无拉回"待用户确认。
