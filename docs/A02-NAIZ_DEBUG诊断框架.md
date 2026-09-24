# NAIZ_DEBUG — NP2kai 诊断框架

> **状态**：已集成到 NP2kai 源码（`/tmp/np2kai_src`），通过 CMake option 开关控制。
> **创建**：2026-06-08
> **目的**：长期可复用的 NP2kai 渲染管线诊断工具链，不依赖 wx 窗口截图。

## 一、架构

```
                 ┌──────────────────────────────────────┐
                 │         NP2kai pccore 渲染循环        │
                 │                                      │
drawscreen() ────┤ → fprintf(stderr, key_vars)          │
                 │ → scrnsave BMP dump (np2_vram)       │
                 │ → scrndraw_draw() 调用轨迹           │
                 └──────────────┬───────────────────────┘
                                │
                 ┌──────────────▼───────────────────────┐
                 │     io/gdc.c — GDC 端口处理器         │
                 │                                      │
CMD_START/STOP ──┤ → fprintf(grphdisp/textdisp 前后值) │
                 └──────────────┬───────────────────────┘
                                │
                 ┌──────────────▼───────────────────────┐
                 │  wx/np2panel.cpp — wx 面板           │
                 │                                      │
UpdateScreen() ──┤ → fwrite(pixbuf_raw, w*h*2)         │
                 └──────────────────────────────────────┘
```

## 二、输出文件

| 文件 | 内容 | 格式 |
|------|------|------|
| `/tmp/naiz_trace.log` | 所有 `fprintf(stderr, ...)` 输出 | 纯文本，每行以 `NAIZ_` 前缀 |
| `/tmp/naiz_vram_0.bmp` | NP2kai 内部 framebuffer（第 1 帧） | 8-bit 索引色 BMP，640×400 |
| `/tmp/naiz_vram_N.bmp` | 后续帧（最多 10 帧） | 同上 |
| `/tmp/naiz_pixbuf_0.raw` | wx 面板读取的原始像素数据（第 1 帧） | 16bpp RGB565 raw，640×400×2=512,000 字节 |
| `/tmp/naiz_pixbuf_N.raw` | 后续帧（最多 10 帧） | 同上 |

## 三、使用方法

### 启用（一次性）

```bash
cd /tmp/np2kai_src
rm -rf build_wx
cmake -S . -B build_wx -DBUILD_WX=ON -DNAIZ_DEBUG=ON
make -C build_wx -j$(nproc)
sudo make -C build_wx install
```

### 收集诊断数据

```bash
# 删除旧数据
rm -f /tmp/naiz_*.log /tmp/naiz_*.bmp /tmp/naiz_*.raw

# 运行模拟器
/usr/local/bin/wxnp21kai 2>/tmp/naiz_trace.log &
WX_PID=$!
sleep 25
kill $WX_PID
```

### 禁用

```bash
cmake -S . -B build_wx -DBUILD_WX=ON -DNAIZ_DEBUG=OFF
```

## 四、Trace 行格式

### DRAW trace

```
NAIZ_DRAW #N: frame=F grph=0xGG text=0xTT mode1=0xMM disp=D
```

| 字段 | 含义 |
|------|------|
| N | 帧序号（从 1 递增） |
| F | drawframe（0 或 1，1=渲染帧） |
| GG | gdcs.grphdisp 当前值 |
| TT | gdcs.textdisp 当前值 |
| MM | gdc.mode1 当前值 |
| D | gdcs.disp（VRAM 页面号） |

### GDC trace

```
NAIZ_GDC START id=I before grph=0xGG text=0xTT
NAIZ_GDC START id=I after  grph=0xGG text=0xTT
```

| 字段 | 含义 |
|------|------|
| I | GDC ID（0=master/text, 1=slave/graphics） |

### Surface rendering trace

```
NAIZ_SCRBIT: grph=0xGG text=0xTT disp=D
NAIZ_SCRNDRAW_CALL: sdrawfn=ADDR bit=B disp=D mode1=0xMM
```

### PIXBUF trace

```
NAIZ_PIXBUF #N: WxH bpp=BPP nonzero=N/TOTAL saved PATH
```

| 字段 | 含义 |
|------|------|
| N | 序号（0-9） |
| nonzero | 非零字节数 |
| TOTAL | 总字节数（512000 = 640*400*2） |

### VRAM trace

```
NAIZ_VRAM #N: saved PATH
```

## 五、修改的文件

| 文件 | 修改内容 | NAIZ_DEBUG 下的行为 |
|------|----------|-------------------|
| `CMakeLists.txt` | 添加 `option(NAIZ_DEBUG ...)` + `add_compile_definitions` | 编译开关 |
| `pccore.c` | 添加 `<stdio.h>`, `<vram/scrnsave.h>` | `drawscreen()` 入口 fprintf + 末尾 scrnsave BMP |
| `io/gdc.c` | 添加 `<stdio.h>` | CMD_START/STOP 前后 fprintf |
| `wx/np2panel.cpp` | 添加 `<cstdio>` | `UpdateScreen()` 中 fwrite raw dump |
| `vram/scrndraw.c` | 添加 scrbit / scrndraw_call trace | 位计算和表面渲染调用日志 |
| `vram/sdrawq16.c` | 添加 qvga16p_gi dirty count trace | 未触发（该函数未被调用） |

## 六、典型诊断流程

### 1. 判断 VRAM 写入是否正确

```bash
grep "NAIZ_PIXBUF" /tmp/naiz_trace.log
# nonzero=0 → VRAM 到 pixbuf 断裂
# nonzero>10000 → 有数据传输
```

### 2. 判断 GDC 渲染是否执行

```bash
grep "NAIZ_BITMATCH" /tmp/naiz_trace.log
# 有输出 → makegrph 被调用
# 无输出 → grphdisp 的 MAKE 位未满足条件
```

### 3. 查看 VRAM 实际内容

```bash
# 查看 BMP 直方图
convert /tmp/naiz_vram_0.bmp -format "%c" histogram:info:- | sort -rn | head -10

# 查看中心像素
convert /tmp/naiz_vram_0.bmp -crop 1x1+320+200 -format "%[pixel:s]" info:
```

### 4. 查看 pixbuf 内容

```bash
# 查找非零字节
python3 -c "
data = open('/tmp/naiz_pixbuf_0.raw','rb').read()
nz = [(i, data[i]) for i in range(len(data)) if data[i] != 0]
print(f'Non-zero bytes: {len(nz)}')
"
```

### 5. 追踪 GDC flag 变化时间线

```bash
grep -E "NAIZ_DRAW|NAIZ_GDC" /tmp/naiz_trace.log | less
```

## 七、已知限制

- VRAM BMP 和 PIXBUF 各最多保存 10 帧
- 所有输出写入 `/tmp`，需确保有写入权限
- 诊断输出会显著降低 NP2kai 性能（每帧约 1-2MB 日志）
- `scrnsave` 捕获的是**混合画面**（text+graphics），非纯图形层
- PIXBUF 的 16bpp 格式依赖平台字节序（x86_64 为小端）
