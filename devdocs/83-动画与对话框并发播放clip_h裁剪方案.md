# 83 — 动画与对话框并发播放：clip_h 裁剪方案

> 日期：2026-08-26
> 前置：devdoc 82（VSYNC 心跳修复后，动画时长准确；现需支持动画+对话框并行）
> 版本起点：0.2.061

---

## 一、问题陈述

当前 `waitanima` 阻塞脚本执行，动画播完才继续。用户需要**动画播放期间同时推进剧情**（显示对话文字、执行脚本命令）。

根因：`anim_draw_frame()` 调 `vram_blit(a->img, 0, 0)` 写满 640×400，覆盖对话框区域（y≥280）的文字像素。

## 二、现有架构分析

### 2.1 动画帧写入路径

```
anim_tick() → anim_draw_frame()
  ├─ Track 0 (pixel): palette loop → vram_blit(全屏) → cursor_refresh → rebuild_dialog_snapshot
  └─ Track 1 (palette): 一次性 vram_blit(全屏) → palette remap
```

### 2.2 对话框区域

```
LAYER_DIALOG_X=80, LAYER_DIALOG_Y=280, LAYER_DIALOG_W=480, LAYER_DIALOG_H=115
```

- `scene_draw_dialog()`: 填充 PAL_DIALOG_FILL(248) + 白色边框
- `dialog_snapshot`: 捕获对话框像素（frame only，不含文字）
- `bg_dialog_snapshot`: 对话框下方背景（无对话框覆盖）

### 2.3 已有保护

| 机制 | 作用 |
|------|------|
| `prot_pal[256]` | 阻止动画调色板覆盖 index 0/7/15/248/249/252/253/254 |
| `anim_rebuild_dialog_if_open()` | 从图像 RAM 更新 `bg_dialog_snapshot`（避免 55KB VRAM 回读） |
| `cursor_refresh()` | 动画帧后重绘光标（无 vblank_wait） |
| `vram_blit_sprite()` 的 `clip_h` | 已支持裁剪 blit 高度 |

## 三、方案：对话框打开时裁剪动画到 y<280

### 3.1 核心思路

利用 `vram_blit_sprite()` 的 `clip_h` 参数，对话框打开时只写入 y=0..279，对话框区域（y≥280）不被覆盖。

### 3.2 改动清单

#### A. `nb_anim.c:anim_draw_frame()` — Track 0 路径

```c
// 现在（L240-241）
vram_blit(a->img, 0, 0);

// 改为
if (dlg_on && a->type == 0)
    vram_blit_sprite(a->img, 0, 0, PAL_NO_TRANSPARENCY, 0, LAYER_DIALOG_Y);
else
    vram_blit(a->img, 0, 0);
```

- `dlg_on`: `layer_dialog_drawn()` 缓存值（OPT-14）
- `a->type == 0`: 全屏动画才需裁剪；cine(type=1) 天然 640×280，不触碰 y≥280
- `anim_rebuild_dialog_if_open()` **保留调用**：保持 `bg_dialog_snapshot` 与动画帧同步

#### B. `nb_anim.c:anim_draw_frame()` — Track 1 路径

```c
// 现在（L248-249）
vram_blit(a->img, 0, 0);

// 改为
if (dlg_on)
    vram_blit_sprite(a->img, 0, 0, PAL_NO_TRANSPARENCY, 0, LAYER_DIALOG_Y);
else
    vram_blit(a->img, 0, 0);
```

Track 1 只做一次性 blit + palette remap，裁剪后动画底部 120 行不可见，但 palette remap 仍作用于全屏（包括对话框区域），由 `prot_pal` 保护对话框颜色。

#### C. 无需改动

| 模块 | 原因 |
|------|------|
| `cursor_refresh()` | 已在 blit 后调用，不受裁剪影响 |
| `prot_pal[]` | 已覆盖所有对话框 UI 颜色 |
| `layer_dialog.c` | 对话框帧/文字由 NB 引擎管理，动画不干预 |
| `vram_blit_sprite()` | clip_h 机制已就绪 |

### 3.3 行为矩阵

| 动画类型 | 对话框状态 | blit 范围 | 对话框区域 |
|----------|-----------|-----------|-----------|
| type 0 (fullscreen) | 关闭 | 全屏 640×400 | 动画像素 |
| type 0 (fullscreen) | 打开 | y=0..279 | 对话框帧+文字（不被覆盖） |
| type 1 (cine) | 关闭 | 全屏 640×280 | 不触碰 y≥280 |
| type 1 (cine) | 打开 | 全屏 640×280 | 不触碰 y≥280 |

### 3.4 脚本使用方式

```
; 动画+对话框并行
bg(room1)
playanima(once){splash}     ; 启动动画，立即返回
; 无需 waitanima — 脚本继续执行
op_text(cafeteria)          ; 显示角色名
op_text(你好，欢迎光临)     ; 显示对话文字
; 动画在背景播放，对话框在 y≥280 显示
; 用户点击后继续
```

## 四、限制与已知问题

### 4.1 视觉限制

- **动画底部不可见**：type 0 动画的 y=280..399 被裁剪，对话框覆盖区域显示旧背景
- **两侧窄边**：x=0..79 和 x=560..639 在 y≥280 显示旧背景（对话框边框外）
- **可接受性**：对大多数 VN 场景可接受——对话框覆盖大部分 y≥280 区域

### 4.2 技术债务

- `bg_dialog_snapshot` 在裁剪模式下仍从图像 RAM 更新，保持同步
- `dialog_snapshot` 不含文字（仅 frame），裁剪模式下无需更新
- 未来如需"全屏动画+对话框叠加"，需暴露 NB 对话状态到 layer 系统

## 五、验证计划

### 5.1 编译验证

```bash
make -C core 2>&1 | grep -iE 'error|warning'
```

### 5.2 功能验证（NP2kai）

1. **无对话框动画**：`playanima(once){fullscreen_anim}` → 全屏播放正常
2. **动画+对话框**：`playanima(once){fullscreen_anim}` + `op_text(hello)` → 动画 y<280，对话框 y≥280 不被覆盖
3. **cine 动画**：`playanima(once){cine_anim}` → 640×280，不触碰对话框
4. **对话框隐藏恢复**：动画播放中 `layer_dialog_hide()` → 从 `bg_dialog_snapshot` 恢复动画像素
5. **光标**：动画播放中鼠标移动 → 无黑块、无闪烁

### 5.3 回归验证

```bash
make -C core && python -m pytest tools/tests/
```

## 六、版本变更

- 版本号：0.2.061 → 0.2.062
- 变更文件：`core/engine/nb_anim.c`（2 处 vram_blit → vram_blit_sprite）
- 无头文件变更（clip_h 是 vram_blit_sprite 已有参数）
