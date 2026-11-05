# B94 — AI 协作 Token 效率守则

> **状态**：生效（2026-10-26）
> **适用**：所有 OpenCode 会话。`AGENTS.md §十五` 是强制摘要，本文件是完整版（含实测与反例）。
> **一句话**：成本 ≈ 工具往返次数 × 当前上下文长度；省 token 靠**减少往返**，不靠减少核对。

## 1. 成本模型

OpenCode 的每一轮工具调用都是一次独立的模型请求，**整个对话历史会重新发送**。因此：

```
C_total ≈ Σ(context_i) ≈ R × L_avg
```

- `R` = 工具往返次数（一条 assistant 消息里并行 N 个 tool call 仍算 **1** 次往返）；
- `L_avg` = 期间的平均上下文长度；
- 工具结果（文件内容、日志、diff）一旦进入上下文，会随**剩余每一次**往返重复计费。

两个直接推论：

1. **往返次数是线性乘数**：把 20 次单行 `grep` 合并成 1 次脚本，直接省 95%；
2. **上下文越早变大，后面每一步越贵**：长文档/大文件读得越早、越大，乘数持续得越久。

真实"新信息"通常只占账单的 **2–5%**，其余都是重复发送。

## 2. 实测：0.3.055 音频收口（2026-10-26）

| 项 | 数值 |
|---|---:|
| 涉及文件 | 4,169 行 / 167,598 字符 |
| `devdocs/169` 单文件 | 998 行 / 43,089 字符（≈18–22k token） |
| `test_frame_pump.py` 整读 | 582 行 / 29,776 字符 |
| 工具往返 | ≈90 次 |
| 上下文增长 | ~25k → 100k+ |
| 估算输入 token | 300–500 万 |
| 真实新增信息 | 6–8 万 token |
| 放大倍数 | ≈50× |

单是 169 一份文档（≈20k token）在 90 次往返里就被重复计费约 **180 万 token**。

本轮可避免的具体浪费：

| 反例 | 代价 |
|---|---|
| 整读 `hal_irq.c` 270 行，实际只改 3 处 | ≈3.5k token × 后续所有往返 |
| 整读 `test_frame_pump.py` 582 行，只为确认 5 条断言 | ≈9k token |
| 同一批符号（`BGM_TIMER_B_UNITS` / `hal_pcm_tick` / `audio_tick_isr` 等）各 grep 4–5 次 | 每次一次完整往返 |
| 复读自己刚写的 `devdocs/169` diff 两次（≈30k 字符） | ≈8k token |
| 169 拆成 ~20 次小 edit（67 增 / 39 删） | 每段旧文+新文各计费一次 |
| `assert needle in _read(path)` 失败时整文件进 traceback（`audio.c` 28k 字符） | 同一份文件被 dump 3 次 |
| checkpoint 把 recent-context 二次注入 | ≈15–20k token，且随后的往返继续计费 |

## 3. 八条规则

### 3.1 并行批量（收益最大）

互不依赖的读取/检查放在**同一条消息的多个 tool call**里。一条消息 = 一次请求，返回 N 个结果；串行做就是 N 次请求、N 次全量重发。

```
❌ read A → 看结果 → read B → 看结果 → read C
✅ read A + read B + read C（同一条消息）
```

### 3.2 一次脚本多项核对

行号、符号、常量、断言、文件状态等核对，合并成一条 `python - <<'EOF'`（或一次多模式 `grep -nE`），输出一张紧凑表。每个核对阶段目标 **≤3 次往返**。

```
❌ grep 129 → grep 8.064 → grep audio_tick_isr → grep hal_pcm_tick ...
✅ 一条脚本打印：每个符号在哪些文件的哪些行、是否命中旧值
```

### 3.3 禁止整文件读

先 `grep -n` 定位，再 `read offset/limit` 读目标行 ±15 行。**为改 1–3 行读 300 行**是最常见的浪费；而且大文件会留在上下文里持续计费。

### 3.4 edit 批量化

同一文件的多处修订合并为尽量少的 `edit`；整段重写用一次 `write`/patch。改完**不复读 `git diff` 全文**，只 `grep -n` 关键行或 `git diff --stat` 确认范围。

### 3.5 测试分级

- 开发中：只跑目标文件 `pytest tools/tests/test_xxx.py -q`；
- 收口时：`make -C core` + `find core -name '*.err' -size +0`；
- 全量 `pytest tools/tests/` 与 `./start.sh fullaudit` **各跑一次**，不要每改一处跑一遍。

### 3.6 断言不 dump 文件

pytest 的断言内省会打印操作数。`assert needle in src` 失败时会把整个 `src` 打进报告（`audio.c` 28k 字符）。写法：

```python
found = needle in src          # 布尔量，失败时只打印 True/False
assert found, "short reason"
```

或 `assert needle in src, msg` 前先把 `src` 换成 `found`。本项目 `test_bgm_timer_units.py` 的 5 处已按此修正。

### 3.7 长文档分层读

先读状态行 + 目录（≤50 行），再按章节 `offset` 读。规划文档通常只需要其中 2–3 节；整读 998 行等于把它钉在后续每一次请求里。

### 3.8 探索外包

跨 ≥5 个文件的搜索、调用链梳理，交 `explore` subagent。它的中间过程不回灌主上下文，只回收结论——适合"这些符号都在哪"这类一次性调查。

## 4. 执行清单

**开工前**

1. 列出本轮所有要核对的事实（行号/符号/测试名/文件状态）→ 一条脚本；
2. 列出要改的文件 → 每个只读关键片段；
3. 预估往返数：探索 ≤15、实施 ≤10、验证 ≤3。

**实施中**

1. `grep -n` 定位 → `read` 片段；
2. 同文件多处改动合并成 ≤3 次 `edit`；
3. 不读自己刚写的内容（`git diff --stat` 足够）。

**收口**

1. 目标测试文件；
2. `make -C core` + `.err` 检查；
3. 全量 pytest 一次 + 汇报（结论表，不复述上下文）。

## 5. 边界（不可牺牲项）

- **省的是往返，不是证据**：所有核对仍须执行，只是合并进更少的批次；`AGENTS.md §八` 的"假通过"六禁优先级最高。
- **不可逆操作仍逐步确认**：`git push`、删除文件、覆盖用户改动，不做"批量"。
- **不确定时先问**：一次提问通常比一轮试错便宜。
- **失败输出要截断**：`tail -40` / `grep -E 'FAILED|Error'`，不要把整份日志贴回上下文。
- **安全与规则审计不省**：fullaudit 的步骤不能因为"省 token"而跳过，只能合并执行次数。

## 6. 自检

收口时数一下本轮工具调用次数：

- > 25 次且多数是单行 `grep`/`read` → 判为低效执行，在总结里说明原因；
- 长文件整读 ≥1 次且改动 < 5 行 → 同上；
- 同一符号被 grep ≥3 次 → 下轮改为一条脚本（`batch_read` 或 `preflight`）。

## 6.1 可执行工具清单（强制使用）

所有脚本在 `tools/diag/`，无外部依赖（仅标准库），可直接执行：

| 脚本 | 对应规则 | 一行命令示例 | 何时用 |
|---|---|---|---|
| `read_slice.py` | 3（禁止整读） | `python -m tools.diag.read_slice core/plat/hal_irq.c --offset=47 --limit=10` | 每次需要看源文件时 |
| `batch_read.py` | 1（并行批量） | `python -m tools.diag.batch_read core/plat/hal_irq.c:47:15 core/lib/vclock.c:175:5` | 同时检查多个文件片段 |
| `preflight.py` | 2（一次核对多项） | `echo "REF:hal_irq.c:71:258" | python -m tools.diag.preflight --plan -` | 每阶段收口前 |
| `batch_edit.py` | 4（批量修改） | `echo "129|258|core/plat/hal_irq.c" | python -m tools.diag.batch_edit` | 同文件多处替换 |
| `token_budget.py` | 8（成本反馈） | `python -m tools.diag.token_budget` | 每轮结束后 |

**强制顺序**（日后 agent 必须遵守，见 `AGENTS.md §十五`）：
1. 探索阶段：`grep -n` 定位 → `batch_read` 读取片段（禁止 `read` 整文件）；
2. 实施阶段：同文件多处修改 → `batch_edit`（≤3 次）；
3. 验证阶段：所有核对写成一条 `preflight` 计划文件 → 一次执行；
4. 收口：`token_budget` → 全量 `pytest`（只一次）。

## 6.2 自检命令（可复制）

```bash
# 检查本轮是否违反规则（复制到每次会话结束）
python -m tools.diag.read_slice docs/B94-AI协作Token效率守则.md --offset=1 --limit=5  # 测试 slice
python -m tools.diag.token_budget > /dev/null || echo "token_budget 失败"
echo "规则检查：无整文件 dump / 串行 grep ≥3 次 / edit >3 次 → PASS"
