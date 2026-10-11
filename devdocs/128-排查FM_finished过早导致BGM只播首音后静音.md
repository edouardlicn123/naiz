# 128 — 排查：fmseq_finished 过早导致 BGM 只播首音后静音

> 状态：`规划中（先不动代码）`
> 版本：`0.3.026`
> 相关：devdoc 126–127、123（MIDI→FM）、F03（OPNA 寄存器参考）

## 1. 背景

用户反馈：修复 `fm_op_addr`（`base + 4*r`）和还原 hal_audio.c 临时诊断态后，**主观上仍“听不到 bgm 音乐声”**，而不是“偏静”。

已验证事实：
- `BGM start 'melody_town' (310 events) (FM)` 正常触发（串口日志）
- 波形证实有 FM 信号输出，首音瞬态从 pre-fix ~ -54 dBFS 提升至 ~ -24 dBFS（地址修复生效）
- 双声道有能量（活动段落 rms ~ 600–1100，约 -29 dBFS），但绝大部分录音时段几乎静音
- hal_audio.c 临时诊断态已还原（FM_TRACE_ENABLED=0，VOL1 路径正确）
- FM 相关测试 `test_fm_seq.py + test_fmopn.py + test_audio*.py` 共 **66 passed**

核心矛盾：**波形上有极短首音脉冲，随即转为近乎静音。**

## 2. 假设：fmseq_finished 过早 → fmseq_stop() 立刻 keyoff 全部声部

观察 `core/engine/audio.c::audio_tick()` FM 分支：

```c
if (g_bgm.fm) {
    unsigned long now = hal_wallclock_smooth_ms();
    unsigned long cur = now - g_bgm.wall0;
    fmseq_pump(g_fm_seq, &g_fm_sink, cur);
    if (fmseq_finished(g_fm_seq)) {
        int ring = fmseq_fm_voices(g_fm_seq);
        if (ring > 0)
            hal_logf("FM loop: %d voice%s still ringing on rewind\r\n", ring, ring == 1 ? "" : "s");
        g_bgm.wall0 = now;
        fmseq_stop(g_fm_seq, &g_fm_sink);  /* keyoff 全部 + 静音 SSG */
        /* 不重新 fmseq_events() 重载事件 */
    }
    return;
}
```

要点：
- `fmseq_finished()` 返回真时，直接 `fmseq_stop()`（对所有 FM 声部 keyoff，清空 SSG），不重新装载 MIDI 事件。
- 若 MIDI 事件总时长极短（310 个事件的序列实际只播几百毫秒甚至更短），或者 `hal_wallclock_smooth_ms()` 在首个 tick 就把 `cur` 推进到超过总时长，`fmseq_pump` 会一次性泵完全部事件，使 `fmseq_finished()` 在 BGM start 后极短时间内触发。
- 触发后立即 keyoff 全部声部 → 只剩下首个 note-on 的瞬态，随后全体静音。这与波形“首音脉冲很短，随后近乎静音”的特征完全吻合。

## 3. 排查计划（先不动代码，仅观察验证）

按优先级顺序执行，验证完再决定是否修改代码。

### A. 检查历史串口日志中是否出现 “FM loop” （零改动，最快）
在现有 `logs/serial_demo-a2.log` 中搜索：

```bash
grep -n "FM loop" logs/serial_demo-a2.log
```

重点观察 `BGM start 'melody_town' (310 events) (FM)` 之后是否立刻出现 `FM loop`。如果 BGM start 后 < 1 秒就出现，几乎可断定 finished 过早。

### B. 临时加日志：打印 finished 触发时机（微改动，仅加日志，验证后撤回）
在 `core/engine/audio.c::audio_tick()` 的 FM 分支，`fmseq_finished()` 为真时增加日志：

```c
if (fmseq_finished(g_fm_seq)) {
    int ring = fmseq_fm_voices(g_fm_seq);
    hal_logf("FM finished: ring=%d idx=%ld/%ld cur=%lu wall0=%lu now=%lu\r\n",
             ring, (long)g_bgm.idx, (long)g_bgm.count, cur, g_bgm.wall0, now);
    ...
}
```

验证步骤：
1. 修改后 `make -C core && ./makegame.sh build demo-a2 && ./makegame.sh make demo-a2`
2. 用驱动脚本走到 BGM start，抓取串口日志（`--serial`）
3. 检查 `FM finished` 首次出现的时延、`idx/count`、`cur` 值
4. **验证完立即撤回该日志改动**

### C. 临时开启 FM_TRACE_ENABLED 捕捉寄存器时序（临时，验证后立即还原）
临时将 `core/plat/hal_audio.c` 的 `FM_TRACE_ENABLED` 改回 `1`：

```c
#define FM_TRACE_ENABLED 1  /* 仅本次排查用，排查完还原为 0 */
```

验证步骤：
1. 重编译+make，走到 BGM start，抓取串口日志（会产生大量 `FM XXXX.XX=XX` 行）
2. 重点观察：`0x28` keyon（如 `F0/F1/F2/F4/...`）何时出现，以及 `fmseq_stop()` 导致的 keyoff（`0x28` 写入 channel select 且 key mask 变为 0）是否紧随其后、间隔极短
3. **验证完立即还原 FM_TRACE_ENABLED 为 0**

### D. 分析 MIDI 事件总时长（只读，纯分析）
从 `games/demo-a2/AUDIO.DAT` 提取 `MELODY_T` 对应的 MIDI（已知偏移约 21879），解析 MTrk：
- division = 96（ticks per quarter note）
- 累加 delta-time 换算成毫秒（粗略估算）
- 计算近似总时长

若总时长 < 2000ms，310 个事件很可能在短时间内全部泵出，导致 finished 过早。

## 4. 预期判断标准

| 场景 | 判断 | 后续处理 |
|---|---|---|
| **A/B 显示 BGM start 后 < 500ms 首次 `FM finished`，且 `idx >= count`** | **finished 过早是主因** | 考虑修改 `audio_tick()` FM 循环：在 finished 时若预期循环，不要调用 `fmseq_stop()`，而是 `g_bgm.idx = 0; g_bgm.wall0 = now;` 重绕（保留事件表）。但需结合 `fmseq` 实现细节谨慎处理。 |
| **A/B 显示 finished 很久才触发（> 5–10 秒）** | finished 过早**不是**主因 | 转向检查 hal_fm_init/A460、A466 路径、fmseq_pump 时序、或 FMP 音色参数本身等其他方向。 |
| **C 显示 keyon 后立刻出现 keyoff** | 直接印证“极短后就被 stop” | 同上，基本锁定 finished 过早。 |

## 5. 建议做法

**先做 A（零改动）→ B（加日志，验证后撤回）→ C（开 trace，验证后立即还原）→ D（只读分析）。**

这是最小、最安全的排查路径。只有在 A–C 都指向“finished 过早”时，才考虑动 `audio_tick()` 的逻辑。

## 6. 备注

- 当前代码在 finished 时使用 `fmseq_stop()` 是“安全停播”逻辑，但对于**循环型 BGM**，正确做法是重绕而不是停播。
- `fmseq` 内部是否需要额外清理（如正处于 release 的 voice）要在改动前先了解 `fmseq_stop()` 和 `fmseq_finished()` 的语义。
- **严守“先不动代码”原则**：本 devdoc 仅规划排查步骤。实际改动需在拿到确凿数据后再决定。
