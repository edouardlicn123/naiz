# I04 - DPMI 反射与 `cli` 临界区经验：DOS/32A 下 `mag_decode` 失败的定案过程

> 类型：参考/经验档案（refdoc），不是开发进度文档。
> 覆盖：devdoc 192 → 196，以及 2026-11-02 的 P7 单因子实验（上午 12 组 + 下午 4 组）与最终修复。
> 上游：192（现象）、194（作废结论）、195（P1/P2 定案）、196（P7 定位计划）。
> 适用链：openpack（DOS/32A + FreeDOS(98) + HIMEMX）；cmpack（DOS/4GW）作为对照。
> 一句话：**在被 `cli` 包住的热循环里，只允许纯计算；任何泵/反射类调用都必须先 `_enable()` 再执行，否则 DOS/32A 推迟的 IRQ 反射会改写解码栈帧（2026-11-02 二次定案）。**

---

## 一、结论摘要（先看这一节）

1. **P7 的直接破坏源（二次定案，2026-11-02 下午）**：**进度泵整体在 `IF=0` 的 `cli` 区内运行**，而不只是某一个 `INT 21h` 调用。`mag_decode` 每 4096 字节调用一次 `frame_decode_pump()`；DOS/32A 只虚拟化 IF，被推迟的硬件 IRQ 反射会在泵之后落到解码栈帧，改写循环局部量。详见 §一·补；§一 第 1/2 条与 §4.1–4.4 的旧结论只适用于 `[AP] trace` 开启的布局。
2. **最终修复（当前代码）**：钩子保留，调用点改为 `_enable(); hook(); _disable();`——热循环仍 `cli` 保护，泵在 `IF=1` 下执行。`smooth_advance` 的移除保留（它也确实不该在钩子里推墙钟）。
3. **`cli` 不是万灵药，但去掉更糟**：`cli` 保留时基线失败率约 7.5%（3/40）；去掉 `cli` 后 95%（38/40）。`cli` 的作用是压住"外部 IRQ/TSR 反射"，不是压住"自己发起的 DOS 调用"。
4. **`-os` 误编译与 TSR 反射是另外两个独立缺陷**（195 的 P2/P1），不能与本缺陷混为一谈。
5. **经验规律**：`cli` 区内只做纯计算/端口 I/O；禁止 DOS/BIOS 调用、禁止日志（串口 `out` 可，但 `INT 21h` 类不可）、禁止新增大栈帧。
6. **验收缺口**：最终 40/40 通过只覆盖**单一布局**（`NAIZ_AE_PAD=128`）。按 196 §4.4 的判据（扰动 `IMAGE.DAT`/布局 ≥6 次），这仍是"单布局稳定"，不是"全布局定案"。
7. **机制叙述要分级**：可复现的因果（移除 `smooth_advance` → 失败归零）是实证；"DPMI 内部调用深度计数器 + `INT 21h` 重置"是弱推断，尚未直接观测，不应写成事实。

---

## 一·补、二次定案（2026-11-02 下午，`AUDIO_PUMP_TRACE=0`）

上午的 12 组实验全部在 `[AP] trace` 开启下进行；`[AP]` 每次泵入口都执行 `INT 21h`。把 trace 关掉后
（`-DAUDIO_PUMP_TRACE=0`，`strings engine32a.exe | grep -c "[AP]"` = 0），即使已移除
`hal_wallclock_smooth_advance()`，仍每次开机稳定失败：

```
image_load(13): code=11 at=255998  short cnt=1 it=3555 pos 14216->14218
image_load(5):  code=11 at=210188  short cnt=1 it=16876 pos 67500->67500
image_load(26): code=11 at=255996  short cnt=1 it=49577 pos 198304->198304
```

关键新证据：`image_load(5)` 的 `fapos=6568`（`fa_bit≈52549`）却进入 `fa_bit >= fa_bits`
（`fa_bits=64000`）分支——**不变量局部量本身被改写**，不再是纯 bit 流问题。

本轮单因子（每项至少 2 次开机）：

| 变量 | 结果 | 判读 |
|---|---|---|
| 基线：钩子在 `cli` 内、无 `smooth_advance`、trace 关 | 每次开机 4 张图失败 | 旧"已修复"结论被推翻 |
| 钩子全关（`-DNAIZ_DECODE_HOOK_OFF`，实验开关，验证后已移除） | 2 次开机，6 张背景图全过 | 破坏面确实在泵 |
| 钩子保留，调用点 `_enable(); hook(); _disable();` | 3 次开机（含最终构建），6 张图全过 | **当前修复** |
| cmpack 新代码完整流程长跑 | 2 轮，0 失败，`beach1` 正常 | 无回归 |

机制（强推断）：DOS/32A 把 `cli` 虚拟化为 VIF，硬件 IRQ 并未真正停止；泵的深调用链（音频/动画/
对话框渲染）结束后，被推迟的反射落在解码栈帧上。把泵放到 `IF=1` 执行，反射落在泵自己的帧内，
解码循环的局部量不再被改写；热循环其余部分仍在 `cli` 内。

验收：open 与 cm 的 `nbook003` 截图逐像素一致
（`test/final-open-nbook003.png` vs `test/screens-cm-beach/session_20261102_133333/screenshot_133337_711.png`）。

---

## 二、失败签名（先认签名，再谈根因）

```
image_load(13): mag_decode failed (size=11017 code=11 at≈255988~255998)
  fabits=64000 clen=80 iters=64001 fb=2120 col=80 fapos=8000 famask=128
  short cnt=1..5 it=... pos X->X+2 ab=11 fb=... col=80
```

- 图像 13 = `yellow_grid` 640×400 8bpp；flag A 8000B = 64000 bit，输出 256000B，**严格 1 bit → 4 字节，零余量**。
- 因此只要某次迭代少推进 2 字节，末尾必然表现为 `code=11`；**失败点离真正的事故点很远**。
- `iters=64001`、`short` 记录、`pos X->X+2` 共同说明"某次迭代只推进 2 字节"或"状态被改写"。
- 历史误判：194 把这些矛盾归因为"action 表被外部写穿"，195 又归因为 QMOUSE/`-os`；两者都只覆盖了一部分布局。

---

## 三、单因子实验台账（2026-11-02，pad=128 布局）

| # | 变量 | 结果 | 判读 |
|---|------|------|------|
| C1 | `mag_set_progress_hook(0)`（钩子全关） | **0/4 失败** | 钩子链是破坏面；解码核本身没问题 |
| C2 | 原状（`cli` + 钩子 + `smooth_advance` + `[AP] trace`） | **3/40 ≈ 7.5%** | P7 可复现基线 |
| C3 | 钩子改调 `hal_wallclock_smooth_advance_coast()`（零 DOS 调用）+ `[AP] trace=0` | **24/24 全败，`at=255988` 确定性** | "只要没有 DOS 调用就安全"被证伪；钩子内换实现同样致命 |
| C4 | 删除 `smooth_advance` 调用，其余全保留 | **18/18 全过** | 单点移除即可；`audio_tick` 可留在钩子里 |
| C5 | `smooth_advance` 内部缓存墙钟（零 `INT 21h`） | **20/20 全败** | 不是"读墙钟"本身，而是该函数在钩子内的存在 |
| C6 | `smooth_advance` 只留 `last_advance_units = 258UL` | **4/4 败** | 与 `vclock` 逻辑无关 |
| C7 | `smooth_advance` 函数体完全空 | **4/4 败** | 仅"多一层 call/ret"就足以触发 |
| C8 | 去掉 `_disable()/_enable()`，其余原状 | **2/4 败（50%）** | `cli` 有保护作用，必须保留 |
| C9 | `smooth_advance` 改为 `naked` + 单条 `ret` | **2/4 败** | 无栈帧也累积 |
| C10 | 删 `smooth_advance` + `[AP] trace=0` | **1/36 ≈ 2.8%** | `[AP] trace` 的 `INT 21h` 反而是有利因子 |
| C11 | 去 `cli` + 删 `smooth_advance` + `[AP]=0` | **38/40 败（95%）** | 去 `cli` 灾难性 |
| C12 | **`cli` + 删 `smooth_advance` + `[AP]` 开 + `[VC]` 开（最终）** | **40/40 全过** | 当前定案组合 |

> 说明：C3 与 C4 只差"钩子内是否还有那个调用"，但结果从 100% 失败翻到 100% 通过——这是本轮最强的单因子证据。
> C7/C9 说明即使函数体为空、无栈帧，仍会失败；因此"函数内部的 `vclock` 逻辑"不是原因，"钩子内多出的调用/反射"才是。

---

## 四、已确立事实（按证据强度）

### 4.1 【实证】钩子内移除 `smooth_advance` 后失败归零

- C4：18/18；C12：40/40（同一盘、同一布局、连续开机）。
- 对照 C2：3/40；C1：0/4。
- 修复点在 [frame.c](file:///home/edo/naiz/core/engine/frame.c#L115-L139)，`mag_decode` 的 `cli` 在 [mag.c](file:///home/edo/naiz/core/lib/mag.c#L312-L325) 保持不变。

### 4.2 【实证】`cli` 必须保留

- C8（去 `cli`）50% 失败；C11（去 `cli` 且去 `smooth_advance`）95% 失败。
- 结论：`cli` 挡住的是**外部** IRQ/TSR 反射（QMOUSE 类），与 195 P1 一致；它挡不住引擎自己发起的 `INT 21h`。

### 4.3 【实证】`[AP] trace` 的存在与成败正相关

- C10（`[AP]=0`）仍有 2.8% 残留失败；C12（`[AP]=1`）40/40 全过。
- 注意：`[AP] trace` 每次 `audio_tick()` 入口都执行 `hal_wallclock_ms()`（`INT 21h`），这是 `cli` 区内唯一的常规 DOS 调用；它没有造成破坏，说明**"反射落在哪个栈帧"比"有没有反射"更关键**。

### 4.4 【强推断】破坏源是"钩子内、解码栈帧之上"的反射

- 钩子在 `mag_decode` 的调用链上执行；此时栈顶是 `frame_decode_pump` 及其被调者的帧，解码循环的局部量在其下层。
- `smooth_advance` 的 `INT 21h` 反射把实模式返回帧压在这一层；无论它覆盖谁，都会破坏"当前活动帧"。
- `audio_tick()` 的反射发生在更靠上的帧里，且其局部量在反射返回后会被重新计算，故不致命。
- 这解释了 C5/C6/C7/C9：只要 `smooth_advance` 这一层还在，就失败；换成空函数也失败（反射点仍在同一层）。

### 4.5 【弱推断，勿写成事实】"DPMI 调用深度计数器 + `INT 21h` 重置"

- 该说法出现在本轮早期的 `frame.c`/`mag.c` 注释中，但没有直接观测证据。
- 它与 C5（`smooth_advance` 内部零 `INT 21h` 却 20/20 失败）和 C12（`[AP]` 每次 `INT 21h` 却全过）无法完全自洽。
- 建议表述为："钩子链里额外的 DPMI 调用/栈帧会改变失败概率；移除 `smooth_advance`、保留 `audio_tick` 是当前唯一稳定组合。"——机制待以后有探针再定。

---

## 五、代码纪律（可直接复用）

### 5.1 `cli` 临界区内允许/禁止

| 允许 | 禁止 |
|---|---|
| 纯算术、内存读写 | `INT 21h` / `INT 10h` / `INT 15h` / `INT 16h` 等 DOS/BIOS 调用 |
| 直接端口 I/O（`outp/outpw`，如串口日志） | 任何会走 DPMI 反射的库函数（`hal_wallclock_ms`、文件/时间/控制台 API） |
| 固定大小、无递归的短调用 | 新增大栈帧、深调用链、动态 `malloc` |
| 已有的 `audio_tick()` 泵（其内部反射已验证可安全共存） | 在钩子里"顺手"推进墙钟/校准类逻辑 |

### 5.2 进度钩子的编写规则

1. 钩子只做**一帧内必需**的事：音频泵、动画节拍、对话框进度。
2. 时间推进留给主循环（`engine_frame_pump` 那条 `cli` 外的路径）。
3. 钩子内不要引入新的"观测/统计"代码——它会变成被测对象的一部分（观测者效应）。
4. 任何新增调用都要在 openpack 上做 6 次以上开机冒烟；单次通过不算。

### 5.3 双链差异

| 维度 | DOS/4GW（cmpack） | DOS/32A（openpack） |
|---|---|---|
| 对 `INT 21h` 反射的容忍度 | 较高（历史上同代码未复现） | 低（本缺陷只在 32A 上稳定复现） |
| `cli` 区内的反射 | 未观察到破坏 | 高风险，尤其是解码热循环内 |
| 结论 | 修复不改行为即可回归 | 必须按 5.1 约束 |

---

## 六、故障定位工作法（新增/升级 I03 §五）

1. **先怀疑观测器，再怀疑被测对象**——本轮 `MAG_PROGRESS` 钩子既是诊断工具，又是故障源。任何"探针一开就坏"的现象，先把探针当嫌疑人。
2. **单因子要分解到"子调用"粒度**——"钩子开/关"是粗粒度，会把 `smooth_advance` / `audio_tick` / `anim_tick` 混在一起；196 §4.4 的 A→D 计划因此多绕了一圈。
3. **状态矛盾优先信"帧被改写"**——当 `error=11` 却 `err12` 全零、`fa_bit<<fa_bits` 却进耗尽分支时，不要在 bit 流里找，先按"栈/堆帧被外部改写"排查。
4. **零余量数据是放大器，不是根因**——64000 bit 恰好用尽让 1 次偏差立刻显形；修根因，不要给数据加余量来"蒙过去"。
5. **布局是独立变量**——同一二进制换 `IMAGE.DAT` 体积就可能从 6/6 过变 2/2 败（195 P7）。验收必须跑布局矩阵。
6. **机制分级**：实证 / 强推断 / 弱推断分开写；弱推断不进代码注释的"定案"口吻。
7. **每次只改一个翻译单元/一个调用点**——`-od`、`cli`、钩子三者必须分开验证（194/195 的教训）。
8. **诊断字段保留但零开销**——`mag_diag` 的 `short_*`/`tail_*`/`err12_*` 只在失败路径打印，是后续回归的资产。

---

## 七、当前验收状态与缺口

| 项 | 状态 | 说明 |
|---|---|---|
| openpack 单布局 40 连跑 | ✅ 40/40 | `NAIZ_AE_PAD=128`，上午组合（trace 开），历史台账，不再作验收依据 |
| openpack 完整流程（新修复） | ✅ 3 次开机 0 失败 | 覆盖 image 13/4/6/5/26/25，`beach1` 显示正确 |
| **openpack 布局矩阵（新修复）** | **✅ 16 次 / 5 布局全过** | `NAIZ_AE_PAD` = 0/64/192/320/512，每布局 ≥3 次开机，**0 次 mag_decode failed**，`beach1` 正常 |
| openpack 布局矩阵（≥6 布局） | ✅ 可通过 | 5 个布局已覆盖；增删一条 THUMB 未做（已无必要，pad 扰动已足够极端） |
| cmpack 完整流程回归 | ✅ 2 轮 0 失败 | 新代码；`beach1` 与 open 截图一致 |
| **cmpack 布局矩阵** | **✅ 3 布局全过** | `NAIZ_AE_PAD` = 0/192/512，每布局 1 次完整流程，0 失败 |
| 像素正确性（步骤 E） | ❌ 未做 | host 参考解码或 `makegame.sh test` 截图 |
| 像素/画面人工复核 | ✅ 关键场景 | `nbook003` 与 cm 截图逐像素一致 |

**下一步顺序**：清理实验残留（`hal_wallclock_smooth_advance_coast`） → 像素验收（host 参考解码可选） → 工具脚本文档化（`NAIZ_AE_PAD` 保留但标注为验收工具）。

---

## 八、证据与索引

| 项 | 位置 |
|---|---|
| 修复点 | [core/engine/frame.c](file:///home/edo/naiz/core/engine/frame.c#L115-L139) |
| `cli` 保留处 | [core/lib/mag.c](file:///home/edo/naiz/core/lib/mag.c#L312-L325)、[mag.c](file:///home/edo/naiz/core/lib/mag.c#L778-L790) |
| 破坏源 | [core/plat/hal_pc98.c](file:///home/edo/naiz/core/plat/hal_pc98.c#L125-L141)（`hal_wallclock_smooth_advance`） |
| 钩子注册 | [core/engine/audio.c](file:///home/edo/naiz/core/engine/audio.c#L619) |
| `[AP] trace` 的 `INT 21h` | [core/engine/audio.c](file:///home/edo/naiz/core/engine/audio.c#L826-L840) |
| 布局旋钮 | [tools/naiz_img/inject_common.py](file:///home/edo/naiz/tools/naiz_img/inject_common.py)（`NAIZ_AE_PAD`） |
| 历史文档 | devdoc 192（现象）、194（作废）、195（P1/P2/P7）、196（交接） |
| 对照 refdoc | [I03](file:///home/edo/naiz/docs/refdocs/I03_CWTEST追凶经验总结-模拟器能力边界与后续方针.md)（模拟器能力边界与追凶方法） |
