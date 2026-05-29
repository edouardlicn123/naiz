# NP2kai HDI 写不回与诊断工具链建设

## 现状

### 已完成的功能

1. **Text VRAM 实时日志输出** — `log.c:buf_write()` 自动调用 `log_write_screen_len()` 写入 segment 0xA000，无需调用方修改
2. **串口调试（INT 14h）** — `log_enable_serial()` + `--serial` 启动参数，PTY 管道捕获引擎输出到 `logs/serial_*.log`
3. **诊断工具链 `tools/diag/`** — 5 个正式诊断工具：
   - `gen_com` — 生成 COM 测试文件（rwcheck / vramwrite / serialwrite 预设）
   - `hdi_patch_autoexec` — 直接 patich HDI 里的 AUTOEXEC.BAT
   - `hdi_find_file` — 按文件名模式搜索 HDI、查看 FAT 链、hex dump
   - `hdi_integrity` — SHA256 检查点，判断模拟器是否写回磁盘
   - `np2kai_screenshot` — NP2kai 窗口截图，自动筛选主显示窗口

### 已知问题

**[P0] NP2kai SCSI HDI 写不回去**

对 HDI 做 `sha256sum before/after` 对比，模拟器运行 20 秒后文件一个字节都没变：

```
BEFORE: b8514d189df2...
AFTER:  b8514d189df2...
```

exit code = 124（timeout 正常退出），模拟器没有崩溃。但 DOS 的 INT 13h 写请求没有被写回到 `.hdi` 文件。

影响：所有依赖文件输出的验证手段（`gen_com rwcheck` → 运行 emu → `hdi_find_file` 读结果）在这个环节断路。

**[P1] ENGINE.LOG 一直是 0 字节**

目录项存在（cluster=0, size=0），但无实际数据。有两个可能：
- 引擎确实执行了 `log_open` 但没来得及 `log_flush` 就卡住了
- `log_flush` 发了 INT 21h AH=40h 但 NP2kai 没写回 HDI

**[P3] 串口首次测试无输出**

`np2kai_serial` 首次运行 20 秒后未收到任何串口数据。可能原因：
- DOS 未完成启动（CONFIG.SYS 中的 DEVICE=NECAI.SYS 等挂起）
- serialwrite COM 未被执行（AUTOEXEC.BAT 中的 CD \DEMO-A1 失败）
- NP2kai 的 COM1 模拟未正确连接到 PTY

需要配合截图验证确认 DOS 是否启动到提示符。

**[P2] 截图验证（已解决）**

之前 `import` 截图失败，真实原因已查明并修复：

1. **窗口标题不匹配** — `xdotool search --name NP2kai` 找不到窗口。实际标题是 `wx NP21kai (IA-32)`（含有 `NP21` 而非 `NP2`）。需用 `--name NP21kai`
2. **子窗口干扰** — PID 下有三个 X11 窗口：10×10（托盘图标）、200×200（工具栏）、640×459（主显示）。`import` 前两个窗口时 X11 返回 `EAGAIN`（`资源暂时不可用`），因为 MIT-SHM 无法读取此类辅助窗口的像素
3. **Deepin compositor 未阻挡** — `import -window root` 全屏截图正常，「compositor 拦截」不是根因

修复方案：`tools/diag/np2kai_screenshot.py` 自动扫描标题含 `NP21kai` 的窗口，按尺寸过滤（排除 ≤300px 的子窗口），选取面积最大的主显示窗口进行截图。

## 排查方向

### A. 截图验证（推荐优先）

现在可通过 `np2kai_screenshot` 工具直接捕获 NP2kai 屏幕。配合 `vramwrite` COM 文件可快速验证 DOS 启动链是否正常：

```bash
python -m tools.diag.gen_com --preset vramwrite -o /tmp/vram.com
cp /tmp/vram.com games/demo-A1/
python -m tools.naiz_img.inject --game demo-A1 --yes
python -m tools.diag.hdi_patch_autoexec disks/demo-A1.hdi "VRAM.COM"
python -m tools.diag.np2kai_screenshot --launch --wait 8 -o /tmp/vram_test.png
```

如果画面上出现 `ABCD`，DOS 启动链正常。如果是黑屏或只有 C:\> 提示符，则需进一步排查。

### B. 串口实时捕获（工具化）

`tools/diag/np2kai_serial.py` 封装了完整流程：生成 serialwrite COM → inject 到 HDI → patich AUTOEXEC.BAT → 创建 PTY → 启动 emu → 捕获串口输出 → 还原 AUTOEXEC.BAT。

```bash
# 一键执行
python -m tools.diag.np2kai_serial --game demo-A1 --timeout 20
```

如果收到 `Hello from DOS!`，证明 DOS 启动链 + COM 文件执行正常。
如果收不到，说明 DOS 没执行到那一步。

### C. CONFIG.SYS 极简化

当前 CONFIG.SYS（参考 `tools/ref_config/CONFIG.SYS`）含多个 DEVICE 调用。部分 DEVICE（如 `NECAI.SYS`）可能在 NP2kai SCSI 环境下卡住。

验证方法：将 CONFIG.SYS 缩减为仅 `SHELL=COMMAND.COM /P`，排除 DEVICE 加载问题。

```bash
# 修改 tools/ref_config/CONFIG.SYS
echo "SHELL=COMMAND.COM /P" > tools/ref_config/CONFIG.SYS

# 重建 HDI 并注入
python -m tools.naiz_img.inject --game demo-A1 --yes

# 测试
makegame.sh test demo-A1
# 或配合 serialwrite 测试
```

### D. 引擎早期启动诊断

在 `log_open()` 之前直接通过 INT 21h AH=40h 写一个固定文件 `BOOTMARK.LOG`，确认引擎代码是否到达 `main()`。

方法：在 `main.c` 入口处（`log_open` 之前）加一段内联 asm：

```c
__asm volatile (
    "mov $0x3C00, %%ax\n\t"    // create file
    "xor %%cx, %%cx\n\t"
    "mov $path, %%dx\n\t"
    "int $0x21\n\t"
    "mov %%ax, %%bx\n\t"       // handle
    "mov $0x4000, %%ax\n\t"    // write
    "mov $5, %%cx\n\t"
    "mov $data, %%dx\n\t"
    "int $0x21\n\t"
    "mov $0x4C00, %%ax\n\t"    // exit
    "int $0x21\n\t"
    "path: .asciz \"BOOTMARK.LOG\"\n\t"
    "data: .ascii \"BOOT\\n\""
    ::: "%ax", "%bx", "%cx", "%dx");
```

配合 `hdi_find_file` 读取结果。

### E. NP2kai 源码分析

查 NP2kai 的 SCSI HDI 写回逻辑，判断是否因为配置或代码缺陷导致写不回：

| 文件 | 搜索关键词 | 说明 |
|------|-----------|------|
| `io/hdd/sxsi.c` 或 `sxsihdd.c` | `hdd\w*_write` / `sector` / `write` | SCSI/IDE 通用硬盘写逻辑 |
| `io/hdd/hdd.h` | `HDD\w*WRITE` / `LOCK` / `READONLY` | 写保护标志定义 |
| `io/iocore.c` | `sxsi\w*_write\b` | 中断分发到硬盘写路径 |
| `config.c` 或 `np2.c` | `hddlock` / `nowrite` / `readonly` | 配置选项 |

如果硬件层面写了但没 flush 到文件，可以在模拟器退出时（`WM_CLOSE` / `SIGTERM` handler）加入显式 flush。

### F. IDE 接口替代 SCSI

当前基座镜像使用 SCSI（分区表 sys_id = `0x91`）。换用 IDE 接口可以确认写不回是 SCSI 特有的问题。

需要对基座镜像做改造：
1. 用 `HDD1FILE` 代替 `SCSIHDD0`
2. 分区表 sys_id 改为 IDE 对应值
3. 确保 DOS 的 IDE 驱动加载正确

优先级较低，因为需要重新制作基座镜像。

## 工具链使用流程总图

```
gen_com ──→ .com ──→ cp games/<name>/
                        │
                        ▼
                 inject.py (rebuild HDI)
                        │
                        ▼
          ┌─── hdi_patch_autoexec (改 autoexec)
          │
          ▼
    makegame.sh test          makegame.sh test --serial
          │                           │
          ▼                           ▼
    hdi_integrity verify      logs/serial_*.log
    hdi_find_file *.LOG            (实时捕获)
          │
          ▼
    结果: HDI 是否写回？
    文件内容是否正确？
```

虚线路径（HDI 写回）目前不通。实线路径（串口、截图）可用。

截图路径（新增）：

```
gen_com vramwrite ──→ .com ──→ inject.py ──→ hdi_patch_autoexec
                                                     │
                                                     ▼
                                         np2kai_screenshot --launch
                                                     │
                                                     ▼
                                             检查.png 画面
```
