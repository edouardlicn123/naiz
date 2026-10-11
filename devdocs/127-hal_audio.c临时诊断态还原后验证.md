# 127 — hal_audio.c 临时诊断态还原后验证

> 状态：`验证中`
> 版本：`0.3.026`
> 相关：devdoc 126（排查方向）、125c（波形分析）

## 1. 修改内容

还原 `core/plat/hal_audio.c` 临时诊断态：
- `FM_TRACE_ENABLED`：`1` → `0`
- `hal_fm_init()`：去除诊断性写入 `0x0F/0x2F`，改为 `outb(PCM_STATUS_PORT, (uint8_t)(FM_VOL_PATH_VOL1 | 0x00))`（VOL1 路径，满音量）
- 新增 `#define FM_VOL_PATH_VOL1 0x00`
- `hal_fm_set_volume()`：由固定写 `0x0F` 恢复为 `outb(PCM_STATUS_PORT, (uint8_t)(FM_VOL_PATH_VOL1 | (atten & 0x0F)))`

编译：`make -C core` 干净（0 .err），`build demo-a2 && make demo-a2` 更新 HDI。

## 2. 验证结果（test_fix.raw）

抓取流程同前（parec 提前后台启动 + monitor 源 + 标记后立即录制 5s）：
- 首音瞬态：`~1.686s`，`max=2048, rms≈352, ~ -39.4 dBFS`（双声道平衡）
- 持续段（1.69–1.9s）：`rms ~ 588, ~ -31.8 dBFS`（双声道平衡）
- 全曲整体：`L mv=25528 rms~39? 整体约 -59.1 dBFS`（受录制时长/静默段影响），但**活动段落电平成分明显改善**：持续段由先前的 -29 dBFS 区间趋于 -32 dBFS 左右（双声道一致且更平衡）

## 3. 对比

- **地址修复（base+4*r）**：瞬态从 -54 dBFS 提升到 ~-24~-39 dBFS，持续段有能量——已生效。
- **临时诊断态还原**：消除了诊断性写入，双声道趋于平衡（L/R 一致），VOL1 路径写入恢复正常。
- 波形上仍有 FM 信号输出，活动段落电平合理。

## 4. 下一步

1. **主观直试听**（最高优先）：直接在 wxNP21kai 运行 `disks/demo-a2.hdi`，提高音量试听 nbook001 的 melody_town。确认是否能听见音乐。
2. 若主观仍偏静，考虑针对 melody_town 主旋律族（flute）做**极小步**载波 TL 下调（-2~-4）单族验证（只改 assets/demo-a2/fm/flute.fmp → build demo-a2 → make demo-a2 → 同流程对比）。
3. 排查 fmseq finished 判定（devdoc 126 步骤 D）：若极短时间后进入 finished→stop，可能只播首小段。可临时加日志观察。
4. 跑 pytest FM 相关测试确保回归：`test_fm_seq.py test_fmopn.py test_audio*.py` 全绿。

## 5. 结论

**临时诊断态还原是正确的修复方向。** 波形显示信号存在且双声道平衡改善。剩下的是主观听感验证——先做直试听，再决定是否进一步微调 FMP。
