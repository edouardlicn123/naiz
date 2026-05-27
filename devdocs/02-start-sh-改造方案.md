# start.sh 改造方案

## 现状

当前菜单：

```
1. 编译引擎 (make -C core)
2. 更新所有子项目
3. 查看状态
0. 退出
```

问题：
- `core/` 尚无引擎代码，"编译引擎"无实际作用
- 缺少环境安装入口，用户需手动配置 gcc-ia16、NP2kai 等工具
- 菜单项排序不符合实际工作流程

## 新架构

```
start.sh (bash 菜单壳)
  │
  ├─ 启动时自动检查 Python venv
  │
  ├─ 主菜单 (bash)
  │
  └─ env_menu (bash 子菜单 + Python 执行体)
       ├─ sudo -v 密码缓存 (bash)
       └─ 各选项 → venv/bin/python3 tools/env_setup/install_env.py <subcommand>
```

安装逻辑全部由 Python 执行，bash 只负责菜单循环和密码缓存。

## 新增目录和文件

```
tools/env_setup/
├── requirements.txt       # Python 依赖声明
├── install_env.py         # 安装逻辑（CLI 子命令模式）
└── venv/                  # 虚拟环境（自动创建，不入 git）
```

### requirements.txt

```txt
colorama>=0.4.6
```

安装脚本自身用 stdlib 完成（`subprocess`、`shutil`、`argparse`），`colorama` 仅用于终端输出颜色。

### install_env.py 子命令

| 子命令 | 行为 |
|--------|------|
| `check` | 检测环境，打印状态表格 |
| `gcc-ia16` | 安装交叉编译器 |
| `np2kai` | 编译安装 NP2kai |
| `deps` | 安装系统开发依赖 |
| `all` | 全自动：deps → gcc-ia16 → np2kai |

## 目标菜单

### 主菜单

```
====================================
     Naiz Launcher
====================================
1. 查看状态
2. 安装开发环境       → 进入子菜单
3. 更新所有子项目
4. 编译引擎 (make -C core)
0. 退出
====================================
```

与原菜单的变化：
| 项 | 变化 |
|---|------|
| 1 | 原"编译引擎"→"查看状态"（原第 3 项移到此） |
| 2 | **新增**"安装开发环境"，进入子菜单 |
| 3 | 原"更新子项目"不变，编号从 2→3 |
| 4 | **新增**"编译引擎"，编号 4 |
| 0 | 退出 |

### 子菜单（主菜单选 2）

```
===== 开发环境 =====
1. 安装 Python 依赖        ← 首位：venv 基础
2. 检测开发环境
3. 安装 gcc-ia16 交叉编译器
4. 安装 NP2kai 模拟器
5. 安装开发依赖
0. 返回主菜单
```

## 启动流程

### 主菜单显示前 — venv 自动初始化

```bash
VENV_DIR="tools/env_setup/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "首次运行，创建 Python 虚拟环境..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install -r tools/env_setup/requirements.txt
    echo "虚拟环境就绪"
fi
```

无需 sudo，用户目录下操作。仅在 venv 缺失时执行一次。

## 密码验证机制

### env_menu 入口

```bash
env_menu() {
    echo "安装开发环境需要管理员权限："
    if ! sudo -v 2>/dev/null; then
        echo ""
        echo "密码验证失败，请重试。"
        read -p "按 Enter 键返回安装子菜单..."
        return
    fi
    # 后台保活（每 60 秒刷新 sudo 缓存）
    (while true; do sudo -n true; sleep 60; done) 2>/dev/null &
    local sudo_keep_pid=$!

    # 子菜单循环...
    # 退出时 kill $sudo_keep_pid 2>/dev/null
}
```

关键点：
- 进入子菜单立即弹密码框，**一次验证，后续所有 install 操作生效**
- 密码取消/错误 → 提示失败 → 按 Enter 返回子菜单
- 后台 `while` 循环每 60 秒刷新 sudo 缓存，防止长耗时安装超时
- 退出子菜单时终止保活进程

## 日志系统

日志由 `install_env.py` 统一管理，bash 侧不直接写日志。

- 路径：`logs/env_install.log`（相对于 `start.sh`）
- 每次 `run_step` 调用输出 `===== 标题 =====` + 时间戳，分段清晰
- 终端只显示 `[当前步/总步数] 步骤标题...`，原始输出全入日志
- 每次安装追加写入，不自动清理

## 子菜单各选项的调用方式

```bash
PYTHON="$VENV_DIR/bin/python3"
SCRIPT="tools/env_setup/install_env.py"

# 选项 1：安装 Python 依赖
"$VENV_DIR/bin/pip" install -r tools/env_setup/requirements.txt

# 选项 2：检测环境
$PYTHON "$SCRIPT" check

# 选项 3：安装 gcc-ia16
$PYTHON "$SCRIPT" gcc-ia16

# 选项 4：安装 NP2kai
$PYTHON "$SCRIPT" np2kai

# 选项 5：安装开发依赖
$PYTHON "$SCRIPT" deps
```

## bash 侧保留的职责

| 职责 | 说明 |
|------|------|
| 主菜单循环 | case 分支调度 |
| venv 初始化 | 启动时自动检测并创建 |
| 密码缓存 | `sudo -v` + 保活 |
| 子菜单循环 | 显示菜单 + 读用户选择 + 调用 Python |
| 选项 1 | 直接调用 `venv/bin/pip install -r` |

## Python 侧负责的职责

| 职责 | 说明 |
|------|------|
| 环境检测 | `check` 子命令 |
| apt 安装 | 封装 `subprocess.run(["sudo", "apt-get", ...])` |
| git clone + cmake 编译 | 封装 NP2kai 构建流程 |
| 日志写入 | `logs/env_install.log` 统一管理 |
| 终端进度反馈 | 彩色输出，步骤计数 |
| 错误处理 | 子进程失败时打印错误码 |

## 代码修改范围

### start.sh 改动

| 改动 | 说明 |
|------|------|
| 添加 venv 自动检查 | 主循环前插入 |
| `show_menu()` 更新 | 主菜单 + 子菜单文本 |
| 新增 `env_menu()` | 密码验证 + 子菜单循环 + Python 调用 |
| `case` 分支调整 | 1=查看状态 / 2=子菜单 / 3=更新子项目 / 4=编译引擎 |
| 移除原 `run_step()` | 日志逻辑迁至 Python |
| 移除原 `install_*` 函数 | 安装逻辑迁至 Python |

### 新增文件

| 文件 | 说明 |
|------|------|
| `tools/env_setup/requirements.txt` | Python 依赖 |
| `tools/env_setup/install_env.py` | 安装逻辑 |

### diff 估算

```
start.sh:    ~ 30 行新增 + ~ 15 行修改 - ~50 行删除（安装函数迁移到 Python）
install_env.py:    ~250 行（全新）
requirements.txt:  1 行（全新）
```

## 注意事项

- **密码统一管理**：`env_menu` 入口统一 `sudo -v`，后续所有 install 操作无需再输密码
- **sudo 保活**：后台 `while` 循环每 60 秒刷新缓存；退出子菜单时自动终止
- **日志路径**：`logs/env_install.log`，由 Python 写入，每次安装追加
- **日志分隔**：每个步骤 `===== 标题 =====` + 时间戳，步骤间留空行
- **终端输出**：只显示 `[当前步/总步数] 步骤标题...`，不显示原始命令输出
- NP2kai 编译耗时较长（5-15 分钟），`install_env.py` 会阻塞等待
- 非 apt 系发行版，Python 检测发行版类型后提示手动安装
- `tools/env_setup/venv/` 不入 git（在 `.gitignore` 中添加）
