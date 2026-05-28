#!/bin/bash

VENV_DIR="tools/env_setup/venv"
source tools/sdl_env.sh

show_menu() {
    clear
    echo "===================================="
    echo "     Naiz Launcher"
    echo "===================================="
    echo "1. 查看状态"
    echo "3. 更新所有子项目"
    echo "4. 编译引擎 (make -C core)"
    echo "0. 退出"
    echo "===================================="
    echo -n "请选择 [0-4]: "
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
        3)
            update_submodules
            ;;
        4)
            echo "编译引擎..."
            make -C core all
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
