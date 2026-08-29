# Naiz 常见问题排查指南

## 一、鼠标输入

### 1.1 鼠标光标漂移到屏幕边沿

**现象**：主菜单/存档选单/选项界面中，鼠标光标自动漂移到 640×400 屏幕边沿，即使宿主鼠标物理静止。

**根因**：
1. **8255 计数器在菜单循环内持续积累**：三个菜单循环（`menu_show`、`cmd_question`、`save_load_menu`）独立于主循环运行，没有帧尾 `mouse_drain()`。NP2kai 的 `mouseif_sync()` 每帧注入 1-2px 位移（宿主鼠标传感器噪声 + 绝对→相对转换精度损失），在无排空的循环内持续积累到边沿。
2. **I/O delta 泄漏**：`nb_process()` 中的 `bg` 等命令触发文件 I/O，`mouseif_sync()` 在 I/O 期间持续注入增量到 8255 计数器。

**解决方案**（多层防御）：

第一层——帧尾 drain（`main.c:143`）：
```c
mouse_draw_cursor();
mouse_drain();  // 清除 nb_process() 期间 I/O 注入的位移
```

第二层——超时复位（本次修复）：
```c
// mouse_update() 内跟踪空闲帧数
if (dx == 0 && dy == 0) {
    if (mouse_idle_frames < 10000) mouse_idle_frames++;
} else {
    mouse_idle_frames = 0;
}

// 在三个菜单循环中调用
void mouse_recenter_if_idle(void) {
    if (mouse_idle_frames > 120)  // ~2秒无操作
        mouse_set_pos(320, 200);  // 复位到中心
}
```

用户碰鼠标（`dx!=0`）立即清零计数器，永不干扰正常移动。

**涉及文件**：`core/plat/mouse.c`、`core/plat/mouse.h`、`core/engine/nb.c`、`core/engine/nb_menu.c`
**调试命令**：`makegame.sh test demo-a2 --serial` 观察 `[MOUSE] x= y= dx= dy=`
**参考文档**：`devdocs/0.1版开发文档总结.html#doc-49`

### 1.2 鼠标完全不动 / 卡死

**现象**：鼠标光标不响应任何宿主鼠标移动。

**根因**：`mouse_drain()` 在 `mouse_update()` 之后背靠背调用时产生 VBLANK 竞争——`mouse_update` 的 HC↓ 到 `mouse_drain` 的 HC↑ 之间若 `mouseif_sync()` 注入位移，drain 的 HC↑ 会锁存并丢弃这些位移，导致下一帧读到 0。

**解决方案**：不要在 `mouse_update()` 后立即 `mouse_drain()`。帧尾 drain 在 `nb_process()` 之后（I/O 操作后），有足够时间间隔避免竞争。菜单循环内使用超时复位代替 drain。

**涉及文件**：`core/plat/mouse.c`

### 1.3 NP2kai 鼠标被捕获在窗口内

**现象**：鼠标光标无法移出 NP2kai 窗口。

**解决方案**：按左 Ctrl 释放鼠标捕获。

### 1.4 NP2kai 鼠标绝对坐标不工作（np2=0）

**现象**：串口日志中 `np2=0`，引擎走 8255 回退路径而非 NP2 系统端口绝对坐标。

**根因**：NP2 系统端口检测失败。引擎通过端口 0x7ED/0x7EF 写 `"NP2"` 命令并期望读回 `"NP2"` 字符串响应。

**排查步骤**：
1. 确认已应用 P5 补丁（`05-wx-mouse-abspos.patch`）
2. 确认 NP2kai 已重编译且安装的二进制是最新版：
   ```bash
   start.sh np2kai   # 重编译 + 安装
   ```
3. 查看 `/tmp/NP2kai/io/np2sysp.c` 中 `np2sysp_bind()` 是否注册了端口 0x7E0-0x7E3

**涉及文件**：`core/plat/mouse.c`（检测函数 `mouse_np2_detect()`）

### 1.5 NP2kai 绝对坐标越界（值 >639 或 >399）

**现象**：串口日志中 `g=658/59` 或 `g=536/65531`（Y= -5 的 16 位无符号表示），坐标超出 640×400 范围。

**根因**：wxNP2kai 面板像素坐标未缩放到 640×400。面板可能以 2x 缩放（1280×800）显示。

**解决方案**：P5 补丁已包含缩放逻辑（`np2panel.cpp` `OnMouseMove` 中 `pos.x * 640 / sz.GetWidth()`）。确认 NP2kai 已重编译且 P5 补丁≥该实现版本。

**检查**：
```bash
grep -n '640\|400' /tmp/NP2kai/wx/np2panel.cpp | grep -i 'scal\|size\|get'
```

### 1.6 NP2kai 鼠标光标被限制在窗口中央小区域（Deepin）

**现象**：Deepin 上虚拟鼠标光标被限制在窗口中心一小块区域，移出即被拉回。Linux Mint 等无此问题。

**根因**：NP2kai `OnMouseMove` 原版每次移动后调用 `WarpPointer()` 把宿主指针拉回窗口中心（相对输入模式设计）。Deepin 的 dde-kwin 合成器对 `XWarpPointer` 非原子处理，把 warp 重投递为一系列**非零 delta 的合成 motion 事件**，被当成真实移动，光标反复被拖回中心。

**解决方案**：P5 补丁 `05-wx-mouse-abspos.patch` 已改为**去掉 warp**（`m_lastMousePos = pos`，宿主指针 1:1 跟随，窗口边缘 = 模拟屏边缘；仅 `CaptureMouse()` 捕获瞬间保留一次性 warp）。需基于 `wx_alpha` 分支重编译：

```bash
NAIZ_NP2KAI_REBUILD=1 start.sh np2kai
```

**验证**：串口日志 `np2=1` 且 `nx/ny` 随鼠标覆盖全范围 0–639 × 0–399。

**涉及**：`tools/np2kaipatch/05-wx-mouse-abspos.patch`、`devdocs/70-deepin鼠标中央限制问题诊断与修复.md`

### 1.7 鼠标路径优先级说明

引擎鼠标驱动三路优先级：
1. **NP2 系统端口（P5）** `np2=1` — NP2kai 专用绝对坐标，最稳定
2. **INT33h（QMOUSE）** `i33=1` — 实体 PC-98 上预期可用
3. **8255 PPI 回退** `np2=0 i33=0` — 通用增量模式，可能有漂移

串口日志格式：
```
[MOUSE] g=320/200 d=320/200 b=0 dr=0/0 np2=1 i33=0/0 idle=5
```

---

## 二、键盘输入

### 2.1 空格键不推进对话 / 不确认菜单

**现象**：空格键无法推进对话或确认菜单选择；回车正常。

**根因**：NP2kai wx 前端的键盘扫描码映射错误。`WXK_SPACE` 被映射为 `0x35`（XFER）而非标准 `0x34`（SPC）。引擎 `kbd_is_down(KC_SPACE=0x34)` 永远不匹配主机空格发送的 `0x35`。

**解决方案**（双修方案 C）：
1. **引擎侧**：让 `KC_XFER(0x35)` 也作为推进/确认键（`main.c`、`nb.c` 共 6 处改动）
2. **模拟器侧**：应用 P4 补丁，修正 `wx/kbtrans.cpp` 中 2 处 `0x35` → `0x34`

**检查补丁**：
```bash
grep -n 'WXK_SPACE.*0x34' /tmp/NP2kai/wx/kbtrans.cpp
```

**涉及文件**：`core/engine/main.c`、`core/engine/nb.c`、`/tmp/NP2kai/wx/kbtrans.cpp`
**参考文档**：`devdocs/0.1版开发文档总结.html#doc-29`、`docs/A04-键盘映射故障排查.md`

### 2.2 键盘某个键不响应

**现象**：特定按键无响应，其他键正常。

**排查流程**（`docs/A04`）：
1. 引擎定义 → `core/plat/keyboard.h` 确认 KC_ 宏
2. 引擎使用点 → 搜索 `kbd_is_down(KC_xxx)`
3. wx kbtrans → `wx/kbtrans.cpp` 中 `wxkcnv[]` / `ascii_to_pc98_106[]` 表
4. SDL 对照 → `sdl/kbtrans.c`
5. 标准定义 → `keystat.tbl`

---

## 三、显示与渲染

### 3.1 模拟器黑屏 / 无 BIOS

**现象**：NP2kai 启动后屏幕完全黑屏，无 BIOS 启动画面。

**根因**：BIOS ROM（bios.rom/font.rom）缺失或路径错误。

**解决方案**：将 BIOS ROM 文件复制到 wxnp21kai 配置目录（`~/.config/wxnp21kai/`）。

### 3.2 VRAM 花屏

**现象**：画面显示混乱、花屏。

**根因**：PEGC bank 切换错误 / 调色板未设置 / `0xE0004` bank 寄存器值错误。

**解决方案**：检查 `fill_rect` 等渲染原语中的 bank 切换逻辑，确认调色板已正确上传，验证 `outpw(0xE0004, bank)` 写入是否正确。确认 P1/P2 补丁已应用。

### 3.3 文字不显示 / 方块

**现象**：文字显示为方块或完全不显示。

**根因**：`FONT.DAT` / `CJK.DAT` 未部署或路径不对。

**解决方案**：确认 `FONT.DAT` 和 `CJK.DAT` 已通过 `makegame.sh build` 正确部署到 `games/<game>/` 目录。

### 3.4 引擎闪退

**现象**：引擎启动后立即崩溃退出。

**根因**：DOS/4GW 堆栈溢出 / NULL 指针解引用。

**解决方案**：检查代码中的指针使用，确保堆栈分配足够。用串口输出定位崩溃点。

---

## 四、调色板与颜色

### 4.1 白色偏黄 / 调色板残留（青/紫/品红）

**现象**：应为白色的像素显示为奶黄色；预留索引显示随机颜色。

**根因**：`gdc.anareg[48..48+1024]`（256c 调色板寄存器）未初始化。NP2kai 保留上电残留值。

**解决方案**：`image_set_palette()` 上传全部 256 色后覆盖预留索引。

### 4.2 调色板自检失败（WARN 输出）

**现象**：串口输出 `WARN: pal[1] readback != Blue(00,00,FF): 00,AA,FF`。

**根因**：P3 补丁未应用，`GDCANALOG_256` 未置位，`pal_make9821` 不运行。

**解决方案**：应用 P3 补丁（`bios/bios18.c` 中 `gdc_analogext(TRUE)` + `mem[MEMB_PRXDUPD] |= 0x80`）。

**检查**：
```bash
grep -n 'gdc_analogext(TRUE)' /tmp/NP2kai/bios/bios18.c
```

### 4.3 背景图中出现白点

**现象**：背景图中索引 7/15 的像素显示纯白。

**根因**：引擎预留索引 7（文字色）和 15（精灵透明色）为白色，但背景图数据使用了这些索引。

**解决方案**：`pack_images.py` 重映射背景图中所有预留索引像素（`PROTECTED_IDX` 保护集）。

### 4.4 BGLOAD 后对话框颜色异常

**现象**：BGLOAD 后对话框从蓝色变成浅咖啡色。

**根因**：`image_set_palette` 覆盖了索引 248（对话框底色），未恢复。

**解决方案**：在 BGLOAD handler 中追加 `dlg_update_palette()`。

---

## 五、对话框与 UI

### 5.1 对话框伪透明丢失（第二句起实心）

**现象**：第一句对话对话框伪透明正常，第二句新台词起对话框变实心。

**根因**：`fill_rect(248)` 全覆盖清除对话框区域，覆盖了伪透明间隙保留的背景像素。

**解决方案**：将 `fill_rect(248)` 替换为背景还原 + 精灵重绘 + 对话框刷新，封装为 `layer_dialog_rebuild()`。

**涉及文件**：`core/engine/layer_dialog.c`

### 5.2 对话框重建冗余（每句都重建）

**现象**：即使立绘和背景未变更，每句新台词都执行全部三步重建，导致性能浪费。

**根因**：`layer_dialog_rebuild()` 无变更检测。

**解决方案**：引入 `dialog_dirty` 惰性截图方案。`layer_sprite_replace()` 和 `layer_sprite_hide()` 设 `dialog_dirty = 1`；`dialog_show()` 中仅在 `dialog_dirty` 时重建。

**涉及文件**：`core/engine/layer_dialog.c`、`core/engine/layer_sprite.c`
**参考文档**：`devdocs/0.1版开发文档总结.html#doc-32`

### 5.3 立绘在对话框区域消失 / 错误

**现象**：立绘在对话框重叠区域显示异常或消失。

**根因**：`clip_h` 参数限制 / `dialog_snapshot` 缓存过期 / `body` vs `face` 选择错误。

**解决方案**：检查 `vram_blit_sprite()` 的 `clip_h` 参数（y ≥ LAYER_DIALOG_Y=280 时裁剪）；确保 `dialog_dirty` 正确设置；验证 `body`/`face` 选择逻辑。

---

## 六、菜单渲染

### 6.1 菜单闪烁（UP/DOWN 切换时）

**现象**：按 UP/DOWN 切换菜单项时，整个区域闪烁。

**根因**：PEGC 无双缓冲，每帧 VRAM 写入在当前帧扫描期间可见。

**解决方案**（增量重绘）：
1. 菜单入口 `menu_draw()` 全量绘制一次
2. UP/DOWN 时只重绘变化的两项
3. 使用专用 palette 条目 250/251 代替 3/7，避免 palette 全局切换
4. 使用 `mouse_draw_cursor()`（save/restore），禁止 `mouse_draw_cursor_ez()`

**涉及文件**：`core/engine/nb_menu.c`、`core/engine/nb.c`
**参考文档**：`devdocs/0.1版开发文档总结.html#doc-23`

### 6.2 保存/读取菜单闪烁

**现象**：存档读档界面全量重绘导致闪烁和光标残影。

**解决方案**（两阶段模式）：
1. 入口 `save_load_draw(full=1)` 全量绘制一次
2. 循环内 `save_load_draw(full=0)` 增量更新文字颜色
3. 全量重绘后调 `mouse_draw_cursor_force()` 刷新保存的背景

---

## 七、启动与引导

### 7.1 HDI 引导到 DOS 提示符

**现象**：模拟器启动后进入 DOS 命令行而非直接运行引擎。

**根因**：`AUTOEXEC.BAT` 路径不对 / `ENGINE.EXE` 不在根目录。

**解决方案**：确认 `ENGINE.EXE` 在 HDI 根目录，`AUTOEXEC.BAT` 末行包含 `ENGINE.EXE`。

### 7.2 CONFIG.SYS INSTALL= 导致黑屏

**现象**：使用 `INSTALL=` 方式启动引擎时 NP2kai 黑屏。

**解决方案**：使用 `AUTOEXEC.BAT` 末行启动（`AGENTS.md §十一` 硬性规定）。

### 7.3 场景脚本无反应

**现象**：引擎启动后场景无任何反应。

**根因**：`logo.nb` 不存在 / NB 命令拼写错误。

**解决方案**：用 `nb_validator` 检查 `.nb` 文件语法；确认 `logo.nb` 已部署。

---

## 八、NP2kai 模拟器补丁

### 8.1 补丁总览

| 补丁 | 文件 | 作用 | 检查命令 |
|------|------|------|---------|
| P1 | `mem/memvga.c` | VRAM 写入后触发图形合成 | `grep -n 'grphdisp \|= 5'` |
| P2 | `io/gdc.c` | VGA VRAM 映射建立 | `grep -nE '0x6A.*0x2[01]'` |
| P3 | `bios/bios18.c` | 256c 调色板使能 | `grep -n 'analogext(TRUE)'` |
| P4 | `wx/kbtrans.cpp` | 空格键映射修正 | `grep -n 'WXK_SPACE.*0x34'` |

**一键检查**：`start.sh check`

**手动应用**：`start.sh np2kai`（自动编译安装到 `/usr/local/bin/`）

### 8.2 补丁缺失的症状

| 缺失 | 症状 |
|------|------|
| P1 | VRAM 写入后画面全黑 |
| P2 | VRAM 写入无效 |
| P3 | 调色板设置后仍全黑 / 串口 WARN |
| P4 | 空格键发 0x35（XFER）而非 0x34（SPC）|

---

## 九、串口调试

### 9.1 串口看不到 "Pal chk OK"

**现象**：串口输出中无 `Pal chk OK` 字样。

**排查方向**：
- `--serial` 参数未加
- BIOS ROM 路径错误导致串口未初始化
- P3 补丁未应用导致调色板自检失败

### 9.2 串口数据慢（~500ms/byte）

**原因**：引擎使用 uPD8251 轮询模式，每次写入一个字节，硬编码 9600 baud。

**解决方案**：这是引擎设计行为，非错误。如需更高波特率，修改 `hal_serial_init()` 的模式字（`core/plat/hal_pc98.c:462`）。

### 9.3 INT 14h 不可用

**原因**：PC-9821 BIOS ROM 不含 INT 14h 处理函数。

**解决方案**：引擎使用直接端口 I/O（`0x30/0x32` uPD8251）绕过此限制。使用 PTY 直连法（`--serial`）。

---

## 十、工具链与构建

### 10.1 Open Watcom 找不到

**现象**：`make -C core` 报错 `Open Watcom not found`。

**解决方案**：运行 `start.sh watcom` 安装，或使用 `bash core/build.sh`（自动设置 WATCOM 环境变量）。

### 10.2 TOML 布尔值大小写导致配置清空

**现象**：NP2kai 配置被清空，`ExMemory`、`pc_model` 等关键项丢失。

**根因**：Python `False` 序列化为 `False`（首字母大写），TOML 标准要求全小写 `true`/`false`。`tomllib.load()` 遇到大写抛出异常。

**解决方案**：编辑 TOML 时布尔值使用小写。使用 `start.sh` 生成的配置不受影响。

### 10.3 HDI 写回不持久

**现象**：NP2kai 退出后，引擎写入 HDI 的数据未保存。

**解决方案**：确保 NP2kai 优雅退出。使用串口调试获取实时输出。

---

## 关键文件索引

| 类别 | 涉及的核心文件 |
|------|---------------|
| 鼠标 | `core/plat/mouse.c`、`core/engine/cursor.c`、`core/engine/nb.c`、`core/engine/nb_menu.c`、`core/engine/main.c` |
| 键盘 | `core/plat/keyboard.h`、`core/engine/main.c`、`core/engine/nb.c`、`/tmp/NP2kai/wx/kbtrans.cpp` |
| 显示 | `core/plat/gdc.c`、`core/engine/render.c`、`core/engine/image.c`、`core/plat/video.c` |
| 对话框 | `core/engine/layer_dialog.c`、`core/engine/nb.c` |
| 菜单 | `core/engine/nb_menu.c`、`core/engine/nb.c` |
| 调色板 | `tools/naiz_build/pack_images.py`、`core/engine/layer_dialog.c`、`core/engine/image.c` |
| 工具链 | `core/build.sh`、`tools/diag/*.py` |
| 串口 | `core/plat/hal_pc98.c`、`tools/diag/np2kai_serial.py` |
| NP2kai 补丁 | `/tmp/NP2kai/mem/memvga.c`、`/tmp/NP2kai/io/gdc.c`、`/tmp/NP2kai/bios/bios18.c`、`/tmp/NP2kai/wx/kbtrans.cpp` |
