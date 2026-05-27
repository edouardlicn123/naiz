#!/bin/bash

VENV_DIR="tools/env_setup/venv"
source tools/sdl_env.sh

show_menu() {
    clear
    echo "===================================="
    echo "     Naiz Launcher"
    echo "===================================="
    echo "1. 查看状态"
    echo "2. 安装开发环境"
    echo "3. 更新所有子项目"
    echo "4. 编译引擎 (make -C core)"
    echo "5. 编译 demo-A1 数据 (make -C projects/demo-A1)"
    echo "0. 退出"
    echo "===================================="
    echo -n "请选择 [0-5]: "
}

MODULES=(
    "ref_projects/MHVNVisualNovelEngine"
    "ref_projects/djlsr"
    "ref_projects/xsys35c"
    "ref_projects/gdc_test"
    "ref_projects/ps2busmouse98"
    "ref_projects/pmdmini"
    "ref_projects/ReC98"
    "ref_projects/master_lib"
    "ref_projects/xsystem35-sdl2"
    "ref_projects/np21w"
    "ref_projects/98imgtools"
    "ref_projects/98fmplayer"
)

update_submodules() {
    echo "正在更新所有子项目..."
    for mod in "${MODULES[@]}"; do
        echo "  → 更新 $mod ..."
        git submodule update --remote --merge "$mod" 2>/dev/null || echo "  [跳过] $mod (可能无远程追踪分支)"
    done
    echo "更新完成！"
    echo ""
    read -p "按 Enter 键继续..."
}

env_menu() {
    local PYTHON="$VENV_DIR/bin/python3"
    local SCRIPT="tools/env_setup/install_env.py"

    while true; do
        clear
        echo "===== 开发环境 ====="
        echo "1. Python 依赖安装"
        echo "2. 系统依赖与交叉编译器 (deps + gcc-ia16)"
        echo "3. NP2kai 模拟器 (SDL2) [主模拟器]"
        echo "4. 备用模拟器 (RetroArch + libretro 核心) [备用]"
        echo "5. 编译 i286 核心 [DEPRECATED]"
        echo "6. 环境检测"
        echo "7. 镜像源设置"
        echo "0. 返回主菜单"
        echo "===================="
        echo -n "请选择 [0-7]: "
        read sub_choice
        case $sub_choice in
            1)
                $PYTHON "$SCRIPT" pip-install
                echo ""
                read -p "按 Enter 键继续..."
                ;;
            2)
                echo "安装开发环境需要管理员权限："
                sudo -v 2>/dev/null || { echo "密码验证失败"; read -p "按 Enter 键继续..."; continue; }
                (while true; do sudo -n true; sleep 60; done) 2>/dev/null &
                local sudo_keep_pid=$!
                $PYTHON "$SCRIPT" system-tools
                kill $sudo_keep_pid 2>/dev/null
                echo ""
                read -p "按 Enter 键继续..."
                ;;
            3)
                echo "安装开发环境需要管理员权限："
                sudo -v 2>/dev/null || { echo "密码验证失败"; read -p "按 Enter 键继续..."; continue; }
                (while true; do sudo -n true; sleep 60; done) 2>/dev/null &
                local sudo_keep_pid=$!
                $PYTHON "$SCRIPT" np2kai
                kill $sudo_keep_pid 2>/dev/null
                echo ""
                read -p "按 Enter 键继续..."
                ;;
            4)
                echo "安装开发环境需要管理员权限："
                sudo -v 2>/dev/null || { echo "密码验证失败"; read -p "按 Enter 键继续..."; continue; }
                (while true; do sudo -n true; sleep 60; done) 2>/dev/null &
                local sudo_keep_pid=$!
                $PYTHON "$SCRIPT" backup-emu
                kill $sudo_keep_pid 2>/dev/null
                echo ""
                read -p "按 Enter 键继续..."
                ;;
            5)
                echo "安装开发环境需要管理员权限："
                sudo -v 2>/dev/null || { echo "密码验证失败"; read -p "按 Enter 键继续..."; continue; }
                (while true; do sudo -n true; sleep 60; done) 2>/dev/null &
                local sudo_keep_pid=$!
                $PYTHON "$SCRIPT" build-i286
                kill $sudo_keep_pid 2>/dev/null
                echo ""
                read -p "按 Enter 键继续..."
                ;;
            6)
                $PYTHON "$SCRIPT" check
                echo ""
                read -p "按 Enter 键继续..."
                ;;
            7)
                echo ""
                echo "───── Git 仓库来源 ─────"
                echo "  1) GitHub（海外直连）"
                echo "  2) 国内镜像（Gitee/GitCode，中国大陆加速）"
                echo -n "  请选择 [1/2]: "
                read mirror_choice
                case $mirror_choice in
                    1)
                        $PYTHON "$SCRIPT" --mirror github check
                        ;;
                    2)
                        $PYTHON "$SCRIPT" --mirror china check
                        ;;
                    *)
                        echo "  无效选项"
                        ;;
                esac
                echo ""
                read -p "按 Enter 键继续..."
                ;;
            0)
                return
                ;;
            *)
                echo "无效选项，请重新选择。"
                sleep 1
                ;;
        esac
    done
}

# 主循环前：自动检查 Python venv
ensure_venv() {
    if [ -d "$VENV_DIR" ] && [ ! -f "$VENV_DIR/bin/pip" ]; then
        echo "  检测到不完整的虚拟环境（缺少 pip），重建..."
        rm -rf "$VENV_DIR"
    fi
    if [ ! -d "$VENV_DIR" ]; then
        echo "创建 Python 虚拟环境..."
        if ! python3 -c "import ensurepip" 2>/dev/null; then
            echo "  安装 python3-venv..."
            sudo apt-get install -y python3-venv 2>&1 || {
                echo "  安装失败，请手动执行：sudo apt-get install -y python3-venv"
                exit 1
            }
        fi
        python3 -m venv "$VENV_DIR" || {
            echo "  创建虚拟环境失败，尝试安装 python3-venv..."
            sudo apt-get install -y python3-venv 2>&1
            python3 -m venv "$VENV_DIR" || {
                echo "  仍失败，请手动执行：sudo apt-get install -y python3-venv"
                exit 1
            }
        }
        "$VENV_DIR/bin/pip" install -r tools/env_setup/requirements.txt
        echo "虚拟环境就绪"
    fi
}
ensure_venv

while true; do
    show_menu
    read choice
    case $choice in
        1)
            echo "=== Git 状态 ==="
            git status
            echo ""
            echo "=== Submodule 状态 ==="
            git submodule status
            echo ""
            read -p "按 Enter 键继续..."
            ;;
        2)
            env_menu
            ;;
        3)
            update_submodules
            ;;
        4)
            echo "编译引擎..."
            make -C core all
            echo ""
            read -p "按 Enter 键继续..."
            ;;
        5)
            echo "编译 demo-A1 数据..."
            make -C projects/demo-A1
            echo ""
            read -p "按 Enter 键继续..."
            ;;
        0)
            echo "再见！"
            exit 0
            ;;
        *)
            echo "无效选项，请重新选择。"
            sleep 1
            ;;
    esac
done
