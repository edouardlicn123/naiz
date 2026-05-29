# NP2kai 黑屏排查记录与 GDC 端口协议分析

## 问题现象

引擎在 NP2kai 上运行后画面全黑，DOS 启动阶段的 C:\> 提示符消失，看不见任何文本画面。

## 排查过程

### 第一阶段：端口 0x68 (GDC mode1) 协议分析

NP2kai `io/gdc.c:gdc_o68()` 对 port 0x68 采用**位操作协议**：

```
值范围 0x00-0x0F:
  bit 1-3 = 索引 (0-7)，bit 0 = 0:清除 / 1:置位
  例: 0x0F → 索引=7, 置位 → 设置 bit 7 (显示ON)
  例: 0x0E → 索引=7, 清除 → 清除 bit 7 (显示OFF)
值范围 ≥0xF0: 被忽略（无 else 分支）
```

真实 PC-98 硬件：**行为一致**，0x00-0x7F 为位操作，0x80-0xFF 为直接写入。

### 发现 1（已修复）：GDC_MODE1_DISPLAY_ON 值颠倒

MHVN 原始值 `GDC_MODE1_DISPLAY_ON = 0x0E` 在 NP2kai 上清除 bit 7（显示 OFF）。

修正：`0x0E` ↔ `0x0F` 互换。

结果：**仍黑屏。**

### 发现 2（已修复）：GDC_MODE2 值无法 OR 后一次写入

`main.c:32` 中 `gdc_set_mode2(GDC_MODE2_16COLOURS | GDC_MODE2_EGC)` 对端口 0x6A 写入 `0x05`。

NP2kai `io/gdc.c:gdc_o6a()`：值 <0x08 用位操作，≥0x08 直接写入。`0x05` 属于位操作路径，只设置了 EGC bit 2，未设置 16-color bit 0。

修正：拆分为两个独立调用。

结果：**仍黑屏。**

### 发现 3（当前根因）：GDC_MODE1_COLOUR 在 NP2kai 上实际设置单色

核心问题：所有 port 0x68 宏的值在 NP2kai 位操作协议下意义**颠倒**。

| 宏 | MHVN 原始值 | 真机效果 | NP2kai 效果 |
|---|---|---|---|
| `COLOUR` | `0x02` | 彩色 | **单色** |
| `MONOCHROME` | `0x03` | 单色 | **彩色** |
| `LINEDOUBLE_ON` | `0x08` | 开启 | **关闭** |
| `LINEDOUBLE_OFF` | `0x09` | 关闭 | **开启** |
| `DISPLAY_ON` | `0x0E`(已改0x0F) | 开启 | 开启 ✅ |
| `DISPLAY_OFF` | `0x0F`(已改0x0E) | 关闭 | 关闭 ✅ |

**为什么单色导致黑屏：** NP2kai `pccore.c:1529-1592` 中：

```c
if (!(gdc.mode1 & 2)) {  // 单色模式
    makegrph();           // 只渲染单色平面，不渲染文字层
} else {                  // 彩色模式
    maketextgrph();       // 合成文字+图形 → 显示 DOS 提示符
}
```

`maketextgrph()` 是输出文字层的**唯一路径**。单色模式下它永远不会被调用，所以 `np2_tram[]`（文字 VRAM 缓冲）从不被渲染到表面。

### 发现 4：EGC 在 NP2kai 上未激活

`egc_enable()` 序列：设置 MODIFY → 设置 EGC → 清除 MODIFY。

NP2kai `gdc_o6a()` 中，EGC 路由激活需要当前写入时 `mode2 & 0x08`（MODIFY）为真。清除 MODIFY 后，`egc_clear_screen()` 的 `hal_memset16_far(0xFFFF, GDC_PLANES, 16000)` 仅写入平面 0（`0xA800`），其余 3 个平面保留原始内容。

## 修正方案

### 1. `pc98_gdc.h` 交换 4 个宏值

| 宏 | 修正值 |
|---|---|
| `GDC_MODE1_COLOUR` | `0x03` |
| `GDC_MODE1_MONOCHROME` | `0x02` |
| `GDC_MODE1_LINEDOUBLE_ON` | `0x09` |
| `GDC_MODE1_LINEDOUBLE_OFF` | `0x08` |

`DISPLAY_ON`(0x0F)/`DISPLAY_OFF`(0x0E) 保持不变。

### 2. `pc98_egc.c` 修复 `egc_enable()`

删除最后的 `gdc_set_mode2(GDC_MODE2_NOMODIFY)`，保留 MODIFY 位使 EGC 能拦截 VRAM 访问。

## 双平台兼容说明

| 端口 | 值范围 | 实体机 | NP2kai |
|---|---|---|---|
| 0x68 | 0x00-0x0F | 位操作 ✅ | 位操作 ✅ |
| 0x68 | 0x80-0xFF | 直接写入 ✅ | 被忽略 ❌ |
| 0x6A | 0x00-0x07 | 位操作 ✅ | 位操作 ✅ |
| 0x6A | ≥0x08 | 直接写入 ✅ | 直接写入 ✅ |

本修正使用的 `0x00-0x0F` 范围在两个平台上行为一致，不需要条件编译。
