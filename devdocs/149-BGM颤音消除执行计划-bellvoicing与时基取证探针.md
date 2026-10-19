# 149 — BGM 颤/电流声消除执行计划：Phase B（bell voicing）→ A1（时基取证）→ A2（Timer 中断探针）

> **状态**：`已完结`（**Phase B 已完成**，见 `151`；**A1 取证经 `152` 于真实循环执行**；**A2 / C 经用户裁决收束** —— `152` 判定残余「电流声」的可测分量（~13.5 Hz AM）源自 **NP2kai 输出通路**（随 `Latencys` 移动，与引擎音乐输出无关），引擎侧 A/C 改动不能消除，故不再执行）
> **版本**：`0.3.039`（Phase B 落地版本）
> **创建于**：2026-10-18
> **类型**：实施计划（承 `148` 的架构判断 → 落地为可执行步骤）
> **执行记录**：**Phase B（bell voicing）已实施并验证** —— 根因为 `bell.fmp` `alg=4` 最响载波 `op2 mul=8`（基频上移 3 八度），修复后 `icy_garden` 引擎录音 `>5kHz` 0.3977 → 0.0123、质心 4160 → 1085 Hz（GM 参考 0.0041/861 Hz）。**A 轴经 `BGM_TICK_TRACE` 实测为非主因**（派发残差抖动 std 6.5–8.2 ms）。完整记录见 **`151`**，三轴实测表见 **`150 §六`**。
> **前序**：`148`（BGM 时基：机制 vs 实现 + 四道墙 + 三轴收敛）、`146`（现状代码分析与改造建议）、`145`（ADV98/98fmplayer/ReC98 逐读）、`143`/`142`（buzz 诊断）、`134`（方案 C：OPNA Timer-B 中断驱动音泵）、`139`（虚拟时钟速率钳制）、`135`（LFO + 15 族）
> **来源/坐标**（撰写时 `0.3.038`）：`assets/demo-a2/fm/bell.fmp`、`assets/demo-a2/fm/targets.toml`、`core/plat/{hal_audio,hal_pc98}.c`、`core/plat/pc98.h`、`core/engine/{audio,frame}.c`、`core/lib/{fmseq,vclock}.c`、`tools/naiz_audio/*`、`tools/diag/np2kai_audio.py`、`docs/refdocs/{F04,F05,G08,G09}`

---

## 一、背景与已定前提

用户实测（0.3.038 P0 之后）复报：BGM「音乐有所改善，但仍有类似电流声的颤音」，并确认：

| 问题 | 用户回答 | 对计划的影响 |
|---|---|---|
| 症状范围 | **四曲都有**（含 001/002 flute） | 存在**系统性**成分 ⇒ 轴 A（时基）为主嫌（`148 §五`） |
| 测试平台 | **NP2kai 模拟器** | pass 率 ~20.5Hz ⇒ 帧量化 ~49ms（真机 16.7ms，**放大 3 倍**） |
| 优先级 | **先 B 后 A，两件都做** | 见 §二 顺序 |

三轴（`148 §五`）：**A 时基**（系统性/时域）、**B `bell.fmp` voicing**（仅 003/004/频谱）、**C LFO**（默认值差异）。

**已排除**（`141`/`142`）：不是 FM 仿真语义错误、不是 SSG 无人机音、不是未关的持续音、不是低八度（`138` 已实机确认修复）。

**两条关键判据**（本计划据此排序）：
1. `001`（纯 flute）实机录音**频谱干净**（`>5kHz` 0.11%，`142 §六`）却仍被听出颤 ⇒ **频谱 oracle 看不见时域伪影**（`148 §5.1`）。故轴 A 只能用 `[VC]`/IOI **运行期**取证。
2. `hal_vblank_wait()`（`core/plat/hal_pc98.c:159`）是 **VSYNC 电平轮询 + 10 万次超时**；静置对白页（轻工作量）帧量化仍只 16.7ms 却也颤 ⇒ 除帧量化外还有 **vclock 速率摆动**（簇状 1/100s DOS 时钟的残余，`146 §三.1`）。二者同属轴 A，同指向「换时基」根治。

---

## 二、执行顺序总览

```
Phase B  bell.fmp voicing 重做        [低风险 · 可离线自证 · 先做 · 隔离]
   │
   ▼
Phase A1 时基取证（[VC] + IOI + LFO A/B）[只读 · 决定性 · 判定轴 A-1/A-2/轴 C]
   │
   ▼
Phase A2 按 134 §3 步骤 1 中断投递探针  [高险 · build-flag 门控 · 失败回落]
```

**决策（已定）**：
- **B 与 C 不合并**：B 单独先做（只影响 003/004，干净归因）；**轴 C 的一次性 A/B 折进 A1 会话**（改一行 `$22` 重编一次即可判定），不单独开一轮。
- **A2 走 `134` 步骤 1 探针**（只读、默认关、门控、失败回落），它是「P1 是否可行」的**唯一门控**；**替补** = 协作式 Timer-B 轮询（无 DPMI/PIC，见 §五.5）。

---

## 三、Phase B — `bell.fmp` voicing 重做【低风险，先做】

### 3.1 目标
消除 003/004 的**频谱类**「电流声」：`>5kHz` 占比由 44–47% 回落到 001 的 0.1% 量级；质心落 `[bell] centroid_hz=[1500,5000]`（`assets/demo-a2/fm/targets.toml`）。

### 3.2 根因（已确认，`143 §四`）
`bell.fmp` 的 `alg=4` A 对为 `op1(mul=2,tl=14) → op2(mul=8,tl=14)`，**载波 `op2` 倍频 8×**（`bell.fmp:6`），再由极响的调制器（`op1`，`bell.fmp:4`）展成 `4f,6f,8f,…` 密频簇 ⇒ 频谱重心远超设计带。属 **voicing 缺陷**（把高倍频放在「载波」而非「调制器」）。

### 3.3 改动
`assets/demo-a2/fm/bell.fmp`（A 对两行）：
- `op=2 mul=8 → 1`（载波回基频）
- `op=1 mul=2 → 8`（把「8」移到调制器 ⇒ 8f 只作边带）
- 视测量收紧 `op=1 tl`（提高以收敛边带）。

> `op=N` = **算法算子 N**（非寄存器槽，`c66`/`136`）；`.fmp` 是文本源，须经 `fm_patch.py::compile_source()` 重编译并 `build` 才生效。

### 3.4 验证
**离线（无需实机）**：
```
tools/env_setup/venv/bin/python -m tools.naiz_audio.fm_render assets/demo-a2/fm/bell.fmp /tmp/bell.wav --note 60
tools/env_setup/venv/bin/python -m tools.naiz_audio.spectrum_report /tmp/bell.wav --oracle --note 60
```
判据：质心入 `[1500,5000]`；达标则把 `targets.toml [bell] calibrated=false → true`（纳入 `test_fm_timbre.py::test_oracle_calibrated_families_meet_bands` 回归）。

**实机（NP2kai）**：
```
./makegame.sh build demo-a2 && ./makegame.sh make demo-a2
tools/env_setup/venv/bin/python -m tools.diag.np2kai_audio --game demo-a2 --after BGM --duration 8 --out logs/aud003.raw
```
量 `>5kHz`（`spectrum_report`），期望从 44–47% 落向 ~0.1% 量级。

### 3.5 验收 / 风险 / 回退
- **验收**：003/004 `>5kHz` 显著回落 + 耳听电流声消失。
- **风险**：低。**回退**：`git checkout -- assets/demo-a2/fm/bell.fmp`（及 `targets.toml`）。

---

## 四、Phase A1 — 时基取证【只读，决定性】

### 4.1 三支判别
1. **`[VC]` trace 直读**：`./makegame.sh test demo-a2 --serial` → 读 `hal_wallclock_smooth_advance()` 每 64 pass 打的 `[VC] v= step= tgt= cal=`（`core/plat/hal_pc98.c:124`，`VCLOCK_TRACE_ENABLED` 默认开）：
   - `tgt` **平滑漂移** ⇒ **A-2**（vclock 速率摆动）；
   - `tgt` 尖峰 + `step/16` ≈ 帧时 ⇒ **A-1**（帧量化）。
2. **001 IOI 抖动**：录 001（纯 flute，谱最干净）：
   ```
   tools/env_setup/venv/bin/python -m tools.diag.np2kai_audio --game demo-a2 --after BGM --duration 8 --out logs/aud001.raw
   ```
   测**音符起始间隔**：≈49ms 成簇 ⇒ A-1；秒级 ±5% 正弦 ⇒ A-2。
3. **轴 C A/B**：临时把 `core/plat/hal_audio.c:255` 的 `$22` 写入关闭（或 `FM_LFO_RATE` `:228` 置 0）重编一次听 001——颤消失 ⇒ **轴 C（LFO）**。

### 4.2 产出 / 回退
- 结论写回 `devdoc 148 §六`（判别法执行结果，坐实哪条轴）。
- 轴 C 若成立：**按需改各 `.fmp` 的 `pms/ams`**（`strings/reeds/ethnic/synfx pms=3`、`synpad pms=2 ams=1`、`flute pms=1`、`organ/sfx ams=1`），**而非全局关 LFO**；具体音色方向需用户确认。
- **回退**：撤销临时构建（`git checkout -- core/plat/hal_audio.c`）。

---

## 五、Phase A2 — 按 `134 §3` 步骤 1 中断投递探针【高险，A1 之后】

### 5.1 目标
一次实机判定「Timer 中断驱动音泵（`134` 方案 C）**可行不可行、该用哪个中断源**」，**零运行时风险**（默认关）。

### 5.2 改动（`core/plat/`，`outb` 仅限本目录）
- 最小 handler：**只计数 + 清芯片标志（`$110` IRQ RESET / `$27` RESET 位）+ 级联 EOI + 串口打印**；C handler + `_go32_dpmi_allocate_iret_wrapper` + CWSDPR0（`G08:57`）+ `_go32_dpmi_lock_code/data`（handler 常驻、不可换页）。
- **build-flag 门控**（默认关）；关闭时行为与现状**逐字节一致**（回落 `engine_frame_pump`）。
- 先测 **GDC vsync IRQ(0x64 → IRQ2)**（PC-98 原生、不碰 OPNA、避 `hal_audio.c:144` 的 A460 FM 静音陷阱），再测 **OPNA Timer-B IRQ3**（`F04`）。

### 5.3 验收（步骤 1）
- 探针计数 ≈ 预期频率（vsync ≈ 显示帧率；Timer-B ≈ `1/tB`）；
- **系统不卡死**（中断未挂错向量、EOI 正确、键盘鼠标仍响应）；
- 一次实机日志即可判定步骤 2（音泵接管）是否值得投入。

### 5.4 前置硬阻塞项（`134 §2`/`§6`）
- NP2kai 是否/以何频率投递 OPNA Timer IRQ（`F04:141`）；
- DOS/4GW 下默认 IRQ 号与向量映射（`G08:80`）；
- `$29` 默认位行为与清标志/重装载次序（`F04:173`）。

### 5.5 替补（探针不通过时）
**协作式 Timer-B 轮询**：在 `hal_vblank_wait()`（`hal_pc98.c:159`）的忙等循环内轮询 Timer-B 溢出标志推进 audio tick——**无中断、无 DPMI、无 PIC**，把 tick 分辨率从「一帧」降到「Timer-B 周期」。局限：只覆盖等待期，且仍依赖 NP2kai 模拟 Timer-B。作为 P1 之前的一次低成本探针。

---

## 六、收尾项（穿插）

| 项 | 动作 |
|---|---|
| `142`/`143` 订正 | 按 §十 四步：`142` 头部加 `⚠ ERRATA` 指向 `143`/`148`；`CHANGELOG`/`AGENTS` 加订正标记（锚点/索引/正文不动）——把「宿主层优先」改为「时基/宿主并列」 |
| 提交 P0 | **仅在用户明说「提交」时执行** |
| `targets.toml` 逐族 `calibrated=true` | bell 修好并有稳定测量后，逐族推进 |

---

## 七、每轮 AGENTS 义务与回归

- 改 `.fmp`/`.c`/`.py`：`bump_version`（全项目同步）+ `nb_config.h` 重生成 + `CHANGELOG.md` 顶部条目（下一锚点 `c70`）+ `docs/B90` 若函数变动。
- 回归：`make -C core` **0 诊断**（`core/*.err` 空）+ `tools/env_setup/venv/bin/python -m pytest tools/tests/` + `./start.sh fullaudit` **7/7**。
- 新守卫：B → `test_fm_timbre` 置 `[bell] calibrated=true`；A2 → 探针 flag-off 行为等价性断言 + `test_devdoc_refs` 行号随动。

---

## 八、未确认项与风险

- **A1 已执行（经 `152`）**：真实主循环（`BGM_IDLE`）实测——`[VC]` idle `step=574`（35.9 ms/28 Hz）vs bench `step=55`（3.4 ms/291 Hz）；`[BGMT]` tempo ratio 0.998、残差 std 21.4 ms/p95 35 ms（**A 轴存在但次级**）。**主发现**：录音包络主导 **~13.5 Hz AM**，GM 参考无；该分量**不随 patch / 循环速率 / FM 核（`USEFMGEN`）改变，仅随模拟器 `Latencys` 移动**（30→8.3 / 93→13.5 / 250→5.7 Hz），且**全频带**（增益调制）⇒ 归属 **NP2kai 输出通路**，非引擎。⇒ **A2 / C 收束不执行**。
- **A2 全部前置项未确认**（§5.4），且本环境（NP2kai）**无法验证中断投递与级联 ACK**，写错 = 静默死机（`AGENTS §八`）——故必须 build-flag 门控 + 失败回落。
- **平台局限**：仅 NP2kai 可测 ⇒ 轴 A 在模拟器侧被放大约 3 倍；真机（60Hz）行为未验证，最终须真机复听。
- **轴 C 方向未定**（`pms/ams` 目标值属音色设计取舍，需用户拍板）。
- `hal_wallclock_ms()` 的 DOS 1/100s 簇状交付是轴 A-2 的根源；更细的软时间源不存在 ⇒ 唯有硬件定时器（P1）根治。

---

**本轮零代码/零音色改动**（仅新增本文档）。
