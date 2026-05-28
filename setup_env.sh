#!/bin/bash
# 开发环境安装菜单
# 封装 tools/env_setup/install_env.py

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/tools/env_setup/venv"
ENV_PY="$SCRIPT_DIR/tools/env_setup/install_env.py"

# 激活 venv
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
fi

show_env_menu() {
    while true; do
        clear
        echo "===== 开发环境 ====="
        echo "1.  环境检测 (check)"
        echo "2.  Python 依赖安装 (pip-install)"
        echo "3.  系统依赖 + 交叉编译器 (deps + gcc-ia16)"
        echo "4.  NP2kai 模拟器 wxWidgets 版 [主模拟器]"
        echo "5.  备用模拟器 (NP2kai libretro + RetroArch)"
        echo "6.  编译 i286 核心 [DEPRECATED]"
        echo "7.  镜像源设置"
        echo "0.  退出"
        echo "===================="
        read -p "请选择 [0-7]: " choice

        case "$choice" in
            1)
                python3 "$ENV_PY" check
                read -p "按 Enter 键继续..."
                ;;
            2)
                python3 "$ENV_PY" pip-install
                read -p "按 Enter 键继续..."
                ;;
            3)
                python3 "$ENV_PY" deps
                python3 "$ENV_PY" gcc-ia16
                read -p "按 Enter 键继续..."
                ;;
            4)
                python3 "$ENV_PY" np2kai
                read -p "按 Enter 键继续..."
                ;;
            5)
                python3 "$ENV_PY" np2kai-libretro
                python3 "$ENV_PY" retroarch
                read -p "按 Enter 键继续..."
                ;;
            6)
                python3 "$ENV_PY" build-i286
                read -p "按 Enter 键继续..."
                ;;
            7)
                echo "───── Git 仓库来源 ─────"
                echo "  1) GitHub（海外直连）"
                echo "  2) 国内镜像（Gitee/GitCode，中国大陆加速）"
                read -p "请选择 [1/2]: " m
                case "$m" in
                    1) python3 "$ENV_PY" --mirror github check ;;
                    2) python3 "$ENV_PY" --mirror china check ;;
                esac
                read -p "按 Enter 键继续..."
                ;;
            0)
                break
                ;;
            *)
                read -p "无效选项，按 Enter 键继续..."
                ;;
        esac
    done
}

if [ $# -eq 0 ]; then
    show_env_menu
else
    exec python3 "$ENV_PY" "$@"
fi
