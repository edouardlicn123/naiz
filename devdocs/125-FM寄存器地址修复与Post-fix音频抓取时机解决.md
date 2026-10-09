# 125 — FM 寄存器地址修复与 Post-fix 音频抓取（时机解决）

> 状态：`进行中`（0.3.026 补充）
> 版本：`0.3.026`
> 相关：devdoc 123（MIDI→FM）、122（BGM 本地静音）、F03（OPNA FM 寄存器参考）
> 作者：AI 协作记录

## 1. 背景

c57 将引擎对 AUDIO.DAT 的查表归一为 `str_toc8()`，解决了打包侧 8.3 短名（`MELODY_T`）与脚本键（`melody_town`）查表失配。串口日志显示 `BGM start 'melody_town' (310 events) (FM)` 已能正常触发，但实机录音仍表现极低：pre-fix melody `max_abs≈59`（约 -54 dBFS）。

两轮排查定位到：

- **根因 1（代码 bug）**：`core/lib/fmseq.c::fm_op_addr` 使用错误的地址公式 `base + 3*(r&1) + 8*(r>>1)`，导致算子寄存器写入到 `{0,3,8,11}`，偏离 OPN/OPNA 的正确布局 `{0,4,8,12}`（operator 由寄存器地址 bit2–3 选定、channel 由 bit0–1 选定）。
- **根因 2（内容）**：15 个 FMP 音色族全部 `SL=14`（≈-45 dB 持续底），即使寄存器写到正确算子也会使长音符停留在较低的 Sustain 电平。
- **卡点（验证）**：要量化 post-fix 效果，必须稳定抓取 NP2kai 主机回放的波形。此前多轮用“检测到 `BGM start` 标记后再启动 `parec`”均导致 `fix*.raw` 为空或首音丢失，主要是 `parec` fork+PulseAudio/ALSA 初始化的启动延迟（30–80 ms）与时序竞争。

## 2. 修复（根因 1）

### 2.1 fmseq.c
将 `fm_op_addr` 改为符合 ymfm/OPN 权威布局的 `base + 4*r`：

```c
/* Register address of op slot r (register slot) for class base (0x30..0x80).
 * Per ymfm/OPN the operator is selected by register address bits 2-3 and
 * the channel by bits 0-1, so a channel's four operators sit at base+{0,4,8,12}. */
static void fm_op_addr(int ch, int r, uint8_t base, int *bank, uint8_t *addr)
{
    uint8_t reg = (uint8_t)(base + 4 * r);
    fmopn_op_addr(ch, reg, bank, addr);
}
```

（说明：`fmopn_op_tl` 等 accessor 以“芯片寄存器槽 r” 接受参数，并通过 `fmopn_file_slot` 将其反查到 FMP 文件槽 `{0,2,1,3}`。因此改动地址公式即可同时让写入落到正确的寄存器地址。）

### 2.2 测试同步
`tools/tests/test_fm_seq.py` 的断言同步到正确地址：

- 注释：`base + 4*r`（operator=bits2–3, channel=bits0–1）
- 预期 TL 写入：`(0,0x40,40)`、`(0,0x44,42)`、`(0,0x48,44)`、`(0,0x4C,46)`（原先为 `0x43/0x4B`）

运行验证：
```bash
tools/env_setup/venv/bin/python -m pytest tools/tests/test_fm_seq.py tools/tests/test_fmopn.py -q
# 26 passed
```

### 2.3 重编译与 HDI
```bash
make -C core  # clean, 0 .err
./makegame.sh build demo-a2 && ./makegame.sh make demo-a2
```

## 3. 串口/自动化（时机解决思路）

要稳定抓取 post-fix 波形，核心原则是**把 parec 的就绪时延推到 `BGM start` 标记之前**。

### 3.1 推荐做法（突破点）
- **提前后台启动**：在检测循环开始前就 `parec ... >$CAP &`，记录 PID。等到 `grep -q "BGM start"` 时**立即**开始计时录制 4–5s（不做额外 `sleep`）。
- **使用 sink monitor 源**：改用 `alsa_output.pci-*.analog-stereo.monitor` 而不是 `default`，减少回放路径延迟。
- **降低缓冲延迟（可选）**：`--latency-msec=30~60`，或 `--buffer-time`（视 PulseAudio/PipeWire 行为而定）。
- **优雅结束**：用 `SIGINT`（`kill -INT $PID`）比 `SIGKILL` 更有利于写完整尾部。

### 3.2 驱动门控
保持现有效果：
- 等 `bootmenu: enter` → `xdotool key Return`
- 等 `mainmenu:` → `xdotool key Return`
- 等 `BGM start 'melody_town' (310 events) (FM)` → **立刻**启动/开始计时录制
- 录制 4–5s 后 `kill -INT parec`、`fuser -k disks/demo-a2.hdi`

> 注：GUI 自动化避免 `xdotool key --window`（wxWidgets 丢弃），改用 `windowfocus/windowactivate` 配合裸 `key Return`。

## 4. 后续工作（循序渐进）

1. **按 3.1 思路实现驱动脚本**（提前后台启动 + monitor 源 + 标记后立即录制），稳定产出非空 `.raw`（预期 >10KB）。
2. **波形分析量化 post-fix**：计算 `max_abs, RMS, dBFS = 20*log10(rms/32768)`，对比 pre-fix `max_abs≈59, ≈-54 dBFS`。目标：明显高于 pre-fix（如峰值数百～数千、RMS > 数百更合理）。
3. **若仍偏低（持续维持 ~-45～-50 dBFS）**：按根因 2 调整 FMP。建议先从 **SL 14→7** 开始试验（选取 1～2 个主音色族），重建 AUDIO.DAT（`build_game` 的 audio 步骤即可），复测。
4. **验证通过后还原临时诊断**（`core/plat/hal_audio.c` 中 FM_TRACE_ENABLED、测试性写入、强制音量等临时改动，如仍存在）。
5. **必要时再跑全量测试**：`tools/env_setup/venv/bin/python -m pytest tools/tests/ -q` 确认无回归。

## 5. 预期结论

- **地址修复（根因 1）** 是“正确性”修复：寄存器写到正确算子，TL/DT/MUL/KS/AR/D1R/D2R/SL/RR 能真正生效。
- **SL=14（根因 2）** 是“电平”设定：若 melody 仍偏静，属于调音而非 bug。
- **抓取时机** 是本轮验证的最大实操阻力。解决时机后即可得出第一个客观量化结论。

