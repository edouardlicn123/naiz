# 79 - 动画脚本分离：`.na` 后缀与 `scripts/` 目录及 anima.sh 工作流重组

> **状态**：已实施（2026-08-24）
> **前置**：devdoc 78（naizbook 脚本与 ANI 容器 v1）、AGENTS.md §动画制作工具链（2026-08-24 项目化架构）
> **一句话**：动画脚本与剧本脚本在后缀（`.na` vs `.nb`）、目录（`scripts/` vs `scenes|nb`）、工具链三维度彻底分离，引擎零改动；anima.sh 新增只读登记对账（check）并将交互菜单重组为"项目操作菜单 + 脚本生成子菜单"。

---

## 一、背景与动机

动画制作工具链（devdoc 78）的脚本原用 `.nb` 后缀，与 NB 剧本脚本同后缀，仅靠目录位置隔离（`animation/projects/<项目>/` vs `projects/<game>/scenes/`）。存在两类隐患：

1. **误用路径不可防**：剧情 `.nb` 可被传给动画组装工具链，反之动画脚本若被手工拷入游戏数据目录也会被 NB 解释器当剧本逐行解释；
2. **术语混淆**："naizbook 脚本"与"NB 剧本脚本"在文档与对话中难以区分。

曾评估并**否决**的方案：

| 方案 | 否决原因 |
|------|---------|
| 动画脚本增加 `scene(<名>)` 命令声明场景 | 与剧本侧既有 `scene`（跳转命令，`nb_scene.c`）撞名 |
| 动画脚本复用 `sceneconf(<标题>,anim)` + 引擎 `cmd_sceneconf` 见 `anim` 即 `vm_set_error()` 硬停 | 累赘：需动引擎 C 代码、所有脚本加声明行、全部测试夹具补行；且引擎防护只在"文件已被错误部署进游戏数据"这一不应发生的场景下才有意义 |

**最终裁定**（用户确认）：取消一切场景声明设计，改为**扩展名分离**——`.na`（naiz animation）专属动画脚本，`.nb` 保留给剧本脚本；脚本目录 `naizbook/` 更名 `scripts/`。分离由约定+工具链强制，引擎零改动。

## 二、决策记录

| 决策点 | 结论 | 说明 |
|--------|------|------|
| 场景声明机制 | **取消** | 不引入任何新命令/头部声明 |
| 分离强制层级 | 工具链层 | 解析器入口严格校验后缀；引擎不改 |
| 脚本后缀 | `.na` | 输出命名仍取 stem（`<STEM大写>.ANI`） |
| 脚本目录 | `<项目>/scripts/` | 原 `naizbook/` 废止 |
| 术语口径 | **动画脚本 (.na)** vs **剧本脚本 (.nb)** | 活跃代码/文档不再以"naizbook"指称脚本（devdoc 77/78 历史存档保留旧称） |
| 登记检查范围 | 双向对账 | 未登记文件 / 库内失效行 / mtime+size 变化；有差异退出码非零 |
| 菜单结构 | 操作菜单 + 脚本子菜单 | register/check 上移到项目级操作 |

## 三、分离保证分析（引擎为何可以零改动）

1. **物理隔离**：动画脚本只存在于 `animation/projects/<项目>/scripts/`；游戏数据管线（`makegame.sh build`）只复制 `projects/<game>/scenes/*.nb`，两条管线无交集。
2. **寻址不可能命中**：剧本侧 `cmd_scene` 按 `nbook{id}.nb` 寻址、`nb_load()` 按显式文件名打开；`.na` 文件不会被任何引擎代码路径引用。
3. **工具链正向校验**：`parse_anim_script()` 入口拒绝非 `.na` 路径——剧情脚本无法被动画工具链误构建（消灭静默失败）。
4. **产物无脚本语义**：动画工具链产物为编译态 `.ANI` 容器（MAG 块 + tick 表），不含可解释脚本。

## 四、语法与校验规则变更

脚本语法本体**完全不变**（`animaconf`/`frame`/`base`/`pal` 裸括号形式、裸名字查库、V1–V8 校验）。唯一新增：

- **F1（文件级前置检查）**：脚本路径必须以 `.na` 结尾，否则解析器报错退出：
  `anim_script: <path>: 动画脚本须为 .na 后缀（与剧本脚本 .nb 分离）`

该检查位于 `parse_anim_script()` 入口（单一权威点），`anim_import.py` 经其自然获得约束。

## 五、登记对账（check）

### 5.1 diff_project() —— 只读对账

从 `sync_project()` 中抽出公共对账逻辑：

```python
diff_project(project, repo_root=None)
    -> (added, updated, removed, unchanged)
    # added:   assets/<项目>/anim/ 有而库中无（未登记）
    # removed: 库中有而文件消失（失效行）
    # updated: mtime+size 任一变化（待更新）
    # unchanged: 其余
```

不写库、不建目录；库不存在时报错（须先 register）。`sync_project()` 改为 `load_project + scan + diff + 写事务`复用同一扫描结果。

### 5.2 CLI

```
python -m tools.naiz_build.anim_register <项目>            # 同步（原行为）
python -m tools.naiz_build.anim_register --check <项目>    # 只读对账
```

报告符号：`+ 未登记 / - 失效行 / ~ 待更新 / = 未变`；`added∪updated∪removed 非空 → exit 1`。

### 5.3 anima.sh 入口

```
anima.sh check <项目>     # 等价 --check，供菜单与脚本化调用
```

## 六、anima.sh 结构

### 6.1 子命令

| 命令 | 行为 |
|------|------|
| `init <项目>` | 创建 `animation/projects/<项目>/{config.toml,scripts/,db/}`（不变） |
| `register <项目>` | 同步素材登记库（不变） |
| `check <项目>` | **新增**：只读双向对账，有差异 exit 1 |
| `build <项目>/<脚本>` | 寻址 `<项目>/scripts/<脚本>.na`（后缀不再可省略地隐含于 glob） |
| `buildall [--flags]` | 全项目全脚本（glob 改 `.na`） |
| `list` | 列 `<项目>/<脚本>`（glob 改 `.na`） |

### 6.2 交互菜单（无参数）

```
===== Naiz 动画制作 =====          ← 一级：项目列表（不变）
选择动画项目: 1)..n / i)init / 0)退出

===== 项目: P =====                ← 二级：固定操作菜单（重构）
  1) 检查素材登记 (check，只读)
  2) register 同步登记库
  3) 生成动画（进入三级子菜单）
  0) 返回上级

选择要生成的动画脚本:              ← 三级：扫描 scripts/*.na
  1) foo  2) bar  0) 返回
  → 选号后: 1) build  2) build --sync  0) 返回
```

与 makegame.sh 工作流保持同一偏差模式：动作以 `if ! "$0" …` 包裹，失败回菜单不退出。

## 七、迁移清单

| 项 | 内容 |
|----|------|
| 存量项目 | `animation/projects/animatest/naizbook/animatest.nb` → `scripts/animatest.na`（git mv）；脚本头速查注释重写为新约定 |
| 测试夹具 | `test_anim_script.py:_write_script`、`test_anim_import.py:_make_script` 写入路径改 `scripts/<名>.na`；`test_anim_project.py` 目录断言改 `scripts/` |
| 新增用例 | 非 `.na` 后缀被拒 / `diff_project` 只读不写 / check 退出码两态 |

## 八、验证标准

```bash
tools/env_setup/venv/bin/python -m pytest tools/tests/    # 全绿（含新用例）
bash -n anima.sh                                          # 语法通过
./start.sh fullaudit                                      # 无 C 改动，make 节 SKIP，其余全过
python -m tools.naiz_build.bump_version demo-a2           # .py 变更触发版本自增
./anima.sh build animatest/animatest                      # 存量项目迁移后端到端可构建
```
