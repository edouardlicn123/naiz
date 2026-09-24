# 82 — VSYNC 心跳失准排查与 GDC 状态位掩码根修（playanima 秒数缩水）

> 日期：2026-08-25
> 前置：devdoc 81（解析器括号剥离缺陷修复后，动画链路已通，但时长参数失准）
> 版本起点：0.1.007

---

## 一、问题陈述

用户在模拟器中手动游玩 animatest 的 nbook001 场景（`playanima(loop,5){testcine}`），观察到 cine 动画**明显不足 5 秒**即停止。loop+sec 语义下应循环播放至 300 tick（标称 60Hz × 5s）耗尽为止；TESTCINE 为 2 帧 × 30 tick（自然一轮 1s），循环上限 300 tick。

## 二、排查经过

### 2.1 已排除的嫌疑

- `anim_stop_internal` 无提前终止路径（逐字段清零 + vm_request_process，nb_anim.c:70）；
- HOLD 期鼠标点击/空格/回车均有 `!anim_waiting()` 吞输入守卫（main.c:140/164）；
- waitanima→HOLD→自然结束/duration 到期链路此前 DBG.LOG 已验证（81 号文档 §2.6）；
- TESTCINE 容器本体：type=1(cine)、track=0(pixel)、nframes=2、tick 表 [30,30]、palsz=0/nblob=2，头 28B 合法（offset 8 处的 u16 值 2 为保留字段小端低字节，offset9=0 满足 L2 校验）。

### 2.2 矛盾的证据链

| 证据 | 含义 |
|------|------|
| 用户观察：手动玩明显偏短 | 主循环 pass 率 > 60Hz（tick 烧得快） |
| 插桩跑 DBG.LOG：`STOP natural end at tick n=65` | g_dbg_ticks 是每主循环 pass 自增的全局计数，~10s 墙钟仅累加 65 ⇒ pass 率 ~7Hz（tick 烧得慢） |
| logo 各阶段墙钟看起来大致正常（~3.2s） | 若全速空转，logo 应一闪而过；若 7Hz 应龟速 |

三组证据互相矛盾 → 提出 FAST/SLOW 两模型（vblank_wait 立即返回 vs 吃满 timeout），静态分析无法裁决，必须实测。

### 2.3 决定性发现：状态位用错（refdocs 对照）

`docs/refdocs/C01_display_system.md §状态寄存器（读 60h/A0h）`：

| Bit | 标志 |
|-----|------|
| 7 | LPEN 光笔 |
| 6 | HBLANK 水平消隐 |
| **5** | **VSYNC 垂直同步** |
| 4 | DMA 执行中 |
| 3 | DRAWING 绘图中 |
| **2** | **FIFO EMPTY** |
| 1 | FIFO FULL |
| 0 | DATA READY |

而 `core/plat/pc98.h:150` 定义：

```c
#define GDC_SYNC_REFRESH     0x04  /* bit 2：刷新同步标志 */   ← 注释错误，实为 FIFO EMPTY
```

`hal_vblank_wait`（hal_pc98.c:77）轮询的是 **FIFO EMPTY 位而非 VSYNC 位**：

```c
while (!(inb(GDC_GFX_PARAM) & GDC_SYNC_REFRESH) && --timeout > 0);
```

GDC 空闲时 FIFO 恒空 → bit2 恒为 1 → 条件立即满足 → **该函数从不等待，主循环没有任何 60Hz 节拍**。这就是秒数缩水的根因：

- tick 全速燃烧：`(loop,5)` 的 300 tick 在 CPU 速度下远快于 5s 烧完 → **偏短 ✓（与用户观察一致）**；
- 各阶段墙钟被 MAG 解码耗时（数百 ms～秒级）掩盖，故 logo/menu "看起来还行"；
- 插桩跑 n=65 的反常读数推测与 NP2kai 对 bit2 的模拟细节有关（绘制期间 FIFO 非空时该轮询反而退化为"等 GDC 空闲"，混合行为平均出低 pass 率）；不影响本次结论——bit 用错本身即为充分根因。

### 2.4 影响面

凡以 vblank_wait 为节拍的机制全部失准：

- `anim_tick` 帧推进与 duration 预算（本 bug）；
- `vm_delay_tick()` 脚本级延迟；
- kbd/mouse 输入循环节奏、光标闪烁等一切"每 pass"计数逻辑。

## 三、修复方案

### 3.1 一行根修（主）

`pc98.h`: `GDC_SYNC_REFRESH` 0x04 → 0x20（bit5 VSYNC），并更正注释。恢复设计意图："等待进入垂直消隐期再操作 VRAM"。单段轮询最坏相位误差 ≤1 帧，对心跳用途足够；timeout 上限保留防 NP2kai 位恒 0 时死循环。

### 3.2 实测验证（必做）

改位后不盲信，用**双时钟对比法**量化心跳：

1. `anim_tick` 内临时文件日志（DBG.LOG→HDI→Python 抽取管线，同 81 号文档 §2.5）：记录 `(g_dbg_ticks, BIOS 日时钟)`；
   - BIOS 日时钟 = 远指针 `0000:006Ch` u32（18.2Hz 真实墙钟，独立于引擎一切时钟）；PC-98 BDA 位于 000400–0005FF（B01_memory_map），若 46Ch 语义存疑则改走 INT 1Ah AH=0（引擎已有 INT 18h BIOS 调用通道先例）。
2. op.nb 动画临时换 `(loop,5){testcine}`（AUTOEXIT 无法点菜单进 nbook001，借道可达路径测量）；
3. 判定标准：START 与 STOP 两行差值 ⇒ 300 tick 的墙钟时长 ∈ [4.5, 5.5]s 且换算心跳 ≈ 60Hz ± 10%。

### 3.3 兜底分支（条件触发）

仅当实测证明 NP2kai 未模拟 A0h bit5（VSYNC 恒 0 导致每次吃满 timeout、心跳骤降）：改用 PC-98 8253 PIT 计数器锁存读出做确定性节拍（端口 71h/75h/77h，B02_io_ports §定时器；outb/inb 仅限 core/plat/，符合 HAL 边界）。不再猜第三种方案。

### 3.4 顺带修复：ESC 无守卫

main.c 输入等待循环 ESC 分支（原 :158）在 HOLD 期直接 `nb_load("mainmenu.nb")`，违背"HOLD 期吞输入"契约（对比鼠标 :142 / F5 :146 / F6 :152 / 空格 :166 均有 `!anim_waiting()`）。补同款守卫。

## 四、收尾清单

1. 还原 op.nb 为 `(once){testfull}`；
2. 拆除全部临时探针（grep 零残留）；
3. 最终回归截图时间线确认播放 ≈ 自然时长且菜单时序正确；
4. `bump_version animatest`；
5. fullaudit 全过；
6. 本文档补记实测数据段落。

## 五、实测数据（0.1.008 已完成）

执行中发现**第二个漏网 bug**，与位掩码问题叠加才是完整根因链：

### 5.1 Bug A：`a->loop` 从未赋值

DBG.LOG 首测显示 `STOP-NAT`——loop 模式动画竟"自然结束"。排查发现 cmd_playanima 解析了局部变量 `mode`、应用了 duration，却**没有任何 `a->loop = mode` 赋值行**：所有动画永远按 once 播一轮就停。此前全部测试均为 once 模式，此路径从未被执行过。用户观察到的"明显短于 5 秒"直接成因：60 tick 自然结束 + 心跳失准双重叠加。

修复：启动初始化块补 `a->loop = mode;`（nb_anim.c）。修复后 DBG.LOG：`STOP-DUR n=303`（300 tick 精确消耗）。

### 5.2 位掩码修复后的心跳实测：20.5Hz

VSYNC 位修正后，`(loop,5)` 墙钟 14.6s ⇒ 真实 pass 率 **~20.5Hz**（每 pass ~49ms = VSYNC 等待 + NP2kai 解释核上的 VRAM/解释开销）。在模拟器上把 pass 率提到 60Hz 不现实，遂改为**时间基步进**：

- 新增 `hal_wallclock_ms()`（hal.h/hal_pc98.c）：DOS INT 21h AH=2Ch，10ms 粒度；
- `anim_tick` 重构：墙钟差值 → 浮点 tick 累积器（60 tick/s 名义率）→ 按 steps 消费；steps clamp 180 防长停滞后狂跳帧；午夜回绕按零增量处理；
- AnimState 增加 `last_ms` / `ms_accum` 字段，anim_stop_internal 同步清零。

### 5.3 双时钟自证：引擎精确，偏差属模拟器

| 时钟 | START | STOP-DUR | Δ |
|------|-------|----------|---|
| guest（INT 21h） | 67408000 ms | 67413000 ms | **5000 ms 整** |
| host（截图时间戳） | — | — | ≈ 5.8–6.4 s |

引擎时长逻辑在 guest 时钟上**精确 5.000s**；host 观感偏长 ~15% 为 NP2kai guest 时钟漂移（模拟器属性，真机不存在）。

### 5.4 最终回归（0.1.008）

原版 `(once){testfull}`：logo → 深蓝动画帧自然播放（~2s 含 frame1 解码）→ 菜单淡入，时序正确。ESC 分支已补 `!anim_waiting()` 守卫。fullaudit 全过。

## 六、防复发要点

- **硬件常量必须对照 refdocs 落地，注释不得替代文档出处**：`GDC_SYNC_REFRESH` 的错误注释（"刷新同步标志"）正是误导源。新增 plat 层位定义时在注释里标注 refdocs 章节（如 C01 §状态寄存器）；
- 时序类改动一律双时钟对比法验证，不接受"看起来正常"（解码耗时掩盖效应已两次造成误判：81 号文档 vram_row_copy 前后的显影观察、本次 logo 假正常）；
- 新增阻塞类命令必须同步登记 nb_process 守卫链 + 输入吞没守卫（ESC 漏网即此类疏失）。
