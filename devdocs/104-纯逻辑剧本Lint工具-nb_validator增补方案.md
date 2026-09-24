# 104-纯逻辑剧本Lint工具：nb_validator 增补方案（细化至可执行）

> 版本：0.2.124（落地）
> 日期：2026-09-20（细化 / 落地）
> 状态：**已落地（0.2.124）** —— V1–V4 全部实施完成：`split_semi`（nb_line.py）、`load_reference` 增 var_tbl、`check_var_segment`/`validate_question`、`load_accepted`/`filter_accepted`、`start.sh` fullaudit 扩 7 步（validator 置 [3/7]）、`tools/tests/test_nb_lint.py`（20 例）入库；pytest 415 passed、fullaudit 7/7 全绿、0.2.123→0.2.124。
> 前文：原 104 已归档的基础方案（背景/Ren'Py lint 参照）保留于本文件 §1–§2.1/§4。

## 1. 背景

Ren'Py 提供 `lint` 命令：不开游戏、不渲染，仅把全部脚本静态过一遍，检查未知命令、标签引用、参数错误、翻译缺失等（对应物语：`renpy/statements.py register()` 的 parse/lint/execute 三回调，lint 在 init 前跑）。naiz 已有 `tools/naiz_build/nb_validator.py` 承担类似职责并在 `build_game.py` 构建期调用，但覆盖面有缺口。目标：**剧本写错在打包时就红**，不靠进模拟器黑屏或串口回读。

本方案与 devdoc 103/105 独立可并行：Lint 工具只读 `.nb` 文本 + 参考数据，不动引擎。

## 2. 现状审计（证据）

### 2.1 既有能力（nb_validator.py，357 行；build_game.py:484-498 已接入）

- 入口：`python nb_validator.py <project_dir>`，退出码 = 错误数；
- 参考数据：`ASSETS.DB`（img_map IMG/ANI/CG）+ `characters.json` + `expressions.json` + `scene/*.nb` 文件集合；
- 统一解析：`tools/naiz_lib/nb_line.py::parse_nb_line`；
- 校验项：未知命令 / 参数个数（`SIGNATURES`）/ 参数空白 / stub（`STUBS`）/ 资产键 / 表达式 / scene 分段 / playanima once-loop+正秒。
- 构建期：`build_game.py:485-498` `subprocess` 调 validator，returncode≠0 → build 终止。

**已确认的解析脱钩（缺口根因）**：python `parse_nb_line` 对 `question(...)` 按 `,` 拆分 args；引擎对 question/scene 走 **`;` 顶级分段**（`nb_parser.c:130-156 nb_parse_line_semi`，段内逗号保留由 `nb_next_field` 消费）。两者对同一行的 arg 划分不同 → 现有 `SIGNATURES['question']=(2,None)` 的个数检查形同虚设（见 §2.2）。

### 2.2 引擎真值（细化依据——Lint 判定必须对齐的语义）

| 项 | 引擎行为 | 证据 |
|---|---|---|
| 多段命令分段 | question/scene 按 `;` 顶级分段；段内 `,` 保留 | nb_parser.c:130-156 |
| `var(id,op,value)` | op ∈ {`=`,`+`,`-`}；未知 op 只 WARN 返回（不 set）；value 走 `atoi`；未知 id WARN 返回 | nb_commands.c:305-338（op 判断 :323-337） |
| 变量 clamp | `nb_var_set/add` 64 位 clamp 进 `[min,max]` | nb_vars.c（V1 参照） |
| `delay(seconds)` | 支持小数；**负/0 收敛 frames=1**（不崩溃）——负值几乎总是笔误 | nb_commands.c:340-361 |
| `question(prompt;opt,...)` | argc<2 返回；段数上限 **10 截断**（:54-57）；每段 `label,var,op,delta` 缺字段**静默丢段**（:65-77）；op=`=`→set、`-`→减、其它含`+`→add（apply_option :23-36）；显示上限 4（:82-86） | nb_question.c:38-89 |
| 参考表 | `variables.json`：`{id,name,desc,initial,min,max}`（demo-a2 三个 bond_* 0..100/initial 0）；**animatest 无此文件** | projects/*/variables.json |

### 2.3 缺口与覆盖

| # | 缺口 | 本方案 |
|---|---|---|
| 1 | `var` 越界未查（只查个数） | V1（§3.1） |
| 2 | `question` 分段未深查（且解析脱钩） | V2（§3.2） |
| 3 | `delay` 未查正数 | V3（§3.3） |
| 4 | `mainmenu` 项数上限（低优先） | **维持现状不做**（引擎截断语义防御足够） |
| 5 | 无回归测试 | §5.8 |
| 6 | 无白名单通道 | V4（§3.4） |

## 3. 方案（V1–V4 细化规格）

### 3.0 公共件：`split_semi(raw)`

新增 python helper（放 `nb_validator.py` 顶部 static，或 `naiz_lib/nb_line.py` 导出）：
- 输入 `raw`（paren 内原始串，不含 `()`）；返回 `[seg1, seg2, ...]`（按 `;` 拆，空白段剔除）。
- 语义对齐 `nb_parse_line_semi`（nb_parser.c:146-156）：顶级 `;` 分段、段内逗号保留。
- 现 `scene` 分支（nb_validator.py:270-271）改走该 helper —— 单一事实源。

### 3.1 V1 `var` bounds 校验

**参考加载**：`load_reference` 增读 `project_dir/variables.json` → `var_tbl = {id: (min, max, initial)}`。**文件缺失则 var 相关全部跳过**（animatest 现况，防误报）。

**判定**（逐文件一行行序；每文件以各 var 的 `initial` 独立初始化 known-range；文件间不做数据流）：
- 对 `var(id, op, value)` 行：`id ∉ var_tbl` → 红；`op ∉ {=,+,-}` → 红；value 非**数值字面量**（须 `^[-+]?[0-9]+$`）→ 红 + **停止该 var 传播**；
- `=`：`val ∉ [min,max]` → 红；否则该 var range ← `[val,val]`；
- `+` / `-`：由当前 range `[lo,hi]` 传播 → `lo+delta, hi+delta`（`-` 为减）；更新后 `lo<min || hi>max` → 红；
- `question(…; label,var,op,delta; …)`（V2 分段结果）每个 option 段同 op/delta 语义计算**各分支结果并集** `[min(lo_i), max(hi_i)]` 传播，出界红；
- 传播途中断（未知 id / 非法 delta）后该 var 不再传播（保守：不误报），但后续 `=` 重新建立 range。

**错误消息**（沿用现有前缀风格）：
```
  {file}:{lineno}: var[{id}] op={op} not in =/+/- 
  {file}:{lineno}: var[{id}] value {v} out of bounds [{min},{max}]
```
**明确不做**：跨文件数据流（scene 切换不追踪）；`scene(a;b,var,op,val)` 条件跳转的 var 传播（避免误报）；运行时精确模拟。

### 3.2 V2 `question` 分段深查

- 现 `SIGNATURES['question']=(2,None)` **改为下拉到 `args` 下限语义无意义**——question 判定完全走分段（`args[0]` 逗号拆分不再可信）。结论：`SIGNATURES['question']` 删除，改专用 `validate_question(raw)` 分支（仿现有 scene 分支结构）：
  1. 以 `split_semi(raw)` 分段 → `segs`；空 `raw` → 红；
  2. `segs[0]` 为 prompt：空 → 红；
  3. 段数 `len(segs)-1`（选项数）∈ `[1,10]`；`>10` → 红（引擎截断是防御，剧本超限即误写）；
  4. 每个 option 段按 `,` 拆 → 期望恰好 4 字段 `label,var,op,delta`：段内逗号数 ≠3 → 红；缺 label → 红；`var ∉ var_tbl`（表存在时）→ 红；`op ∉ {=,+,-}` → 红；delta 非数值字面量 → 红（空/非数字：引擎 atoi→0 静默，剧本即误写）。

错误消息：
```
  {file}:{lineno}: question: segment {i} needs 'label,var,op,delta' (got {n} fields)
  {file}:{lineno}: question: var[{id}] not in variables.json
  {file}:{lineno}: question: op={op} not in =/+/-
```
- 引擎现有卷一行用例即为正例基准：`question(Go?;Yes,bond_ira,+,1;No,bond_neon,+,1)`（demo-a2 scene，按 §3.1 传播初始→`[1,1]` 在界内应 **0 红**）。

### 3.3 V3 `delay` 正数校验

`SIGNATURES['delay']=(1,1)` 分支加数值校验（**复刻** playanima seconds 分支 nb_validator.py:260-267）：
```
if len(args) >= 1:
    try:
        if not float(args[0]) > 0: raise ValueError
    except ValueError:
        errors.append(f"  {nb}:{lineno}: delay seconds {args[0]!r} must be a positive number")
```
- 语义注记（写入文档）：引擎对负/0 收敛 frames=1 不崩溃；本校验为**纪律性红线**（同一实数值误写模式），与 playanima 一致。

### 3.4 V4 白名单 `nb_lint_accepted.txt`

- 位置：`<project_dir>/nb_lint_accepted.txt`（与 scene/ 同级）。
- 行格式：`file:lineno|pattern`（`#` 注释/空行忽略）——`file` 为 `.nb` 基名（`nbook001`，不含扩展名），`lineno` 1-based，`pattern` 可选、为该行**子串断言**（pattern 不匹配该行 → 不豁免，防止行文本漂移后误豁免；pattern 空跳过断言）。
- 豁免语义：命中项**照常打印**原错误行但**不计入 total_errors**；末尾追加 `  (accepted: nbook001.nb:12)`。
- 与 verify_notes 同理念、独立文件格式（Lint 是数据校验而非源码行级）。

### 3.5 接入 `start.sh`（用户已定：并入 fullaudit）

`run_fullaudit` 由 6 步扩为 **7 步**，新步骤「NB 剧本静态校验」**插在 `[2/6] pytest` 之后即位 `[3/7]`**（pytest 之后、py_compile 之前），全链编号 1/7…7/7（make 为 `[7/7]`）：

```bash
echo "--- [3/7] NB 剧本静态校验 (nb_validator) ---" | tee -a "$out"
local vr=0 d
for d in "$ROOT"/projects/*/; do
    [ -f "$d/ASSETS.DB" ] || continue
    if ! "$VENV_PYTHON" "$ROOT/tools/naiz_build/nb_validator.py" "$d" >> "$out" 2>&1; then
        echo "[✗] NB 校验失败: $d" | tee -a "$out"; vr=1
    else
        echo "[✓] NB 校验通过: $d" | tee -a "$out"
    fi
done
[ "$vr" -ne 0 ] && overall=1
```

- `start.sh` 头注释（:3-15）、`run_fullaudit` 流水线注释（:51-52）、用法字符串（:317）同步 7 步表述；
- **同步文档**（§10 / devdocs 禁改项例外）：`AGENTS.md` §十三"6 步流水线"→7 步（含 NB 剧本静态校验）；`docs/B91 §2` 审计命令节补一句。

## 4. 复用与边界

- 复用：`parse_nb_line`、`load_reference` 框架、`SIGNATURES`、scene 现有 `;` 分段（抽 `split_semi` 共用）、playanima 正数分支模式（V3 复刻）。
- 不改成全量引擎仿真：不模拟 question 绘制/输入、不执行 `nb_var_set`；只做静态范围估计。
- 不引入新依赖：仅标准库。

## 5. 落地清单

| # | 动作 | 涉及 |
|---|---|---|
| 5.1 | 抽 `split_semi(raw)` helper（对齐 `nb_parse_line_semi`） | nb_validator.py（或 nb_line.py） |
| 5.2 | `load_reference` 增读 `variables.json` → `var_tbl`（缺失跳过） | nb_validator.py |
| 5.3 | V1 `var` 校验 + known-range 传播（含 question 段并集） | nb_validator.py |
| 5.4 | V2 `validate_question(raw)`（删 SIGNATURES 的 question 项，改专用分支；scene 分支迁 `split_semi`） | nb_validator.py |
| 5.5 | V3 `delay` 正数 | nb_validator.py |
| 5.6 | V4 `nb_lint_accepted.txt` 读取/匹配/豁免计数 | nb_validator.py |
| 5.7 | `start.sh` fullaudit 7 步 + AGENTS §十三 + B91 §2 同步 | start.sh、AGENTS.md、docs/B91 |
| 5.8 | `tools/tests/test_nb_lint.py`（见 §6） | 新增 |
| 5.9 | 两项目跑 validator 清零误报（实测 0 error）；`bump_version`；CHANGELOG 顶部条目；B90 登记 | 工具链 |

## 6. 验证

### 6.1 test_nb_lint.py 用例（正/反）

| 类别 | 行 | 期望 |
|---|---|---|
| V1 正 | `var(bond_ira,=,50)`；`var(bond_ira,+,30)`（range 50→80 ≤100） | 通过 |
| V1 反 | `var(bond_ira,=,101)`；`var(bond_ira,-,1)`（initial 0→-1 <0）；`var(no_such,=,1)`；`var(bond_ira,?,1)` | 各红 |
| V1 反 | `var(bond_ira,+,abc)`（非法 delta）| 红 + 断传播 |
| V2 正 | `question(Go?;Yes,bond_ira,+,1;No,bond_neon,+,1)` | 通过（= demo-a2 现存实样） |
| V2 反 | `question(Prompt;A,bond_ira,+)`（缺 delta）；`question(Prompt;A,bond_ira,x,1)`；`question(Prompt;A,unknown,+,1)`；注：段数 >10；prompt 空 | 各红 |
| V3 正 | `delay(0.5)` | 通过 |
| V3 反 | `delay(0)`；`delay(-1)`；`delay(abc)` | 各红 |
| V4 | accepted 含 `nbook001.nb:12|xxx` 且该行含 `xxx` → 打印不计 exit；pattern 不匹配 → 仍计 | 通过 |

### 6.2 回归

- `demo-a2` 全剧本 validator 0 errors（含现存 question 实样）；`animatest`（无 variables.json）var 跳过不误报；
- `python -m py_compile` 全绿；`./start.sh fullaudit` **7/7** 全绿；pytest 全绿；
- 两项目 `makegame.sh build` validator 0 errors 通过；
- B90/B91/AGENTS/CHANGELOG 同步，`bump_version` 统一版本（与 devdocs/105 打字机同批协调编号）。