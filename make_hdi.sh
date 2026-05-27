#!/bin/bash
# Naiz — HDI 磁盘制作工具
# Interactive wrapper for tools/naiz_img/inject.py

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$ROOT/tools/env_setup/venv"
PYTHON="$VENV_DIR/bin/python3"

# Default values
GAME=""
YES_FLAG=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -y|--yes)
            YES_FLAG="--yes"
            shift
            ;;
        -g|--game)
            GAME="$2"
            shift 2
            ;;
        --list-files)
            exec $PYTHON -m tools.naiz_img.inject --list-files
            ;;
        --preview)
            exec $PYTHON -m tools.naiz_img.inject --preview ${GAME:+--game "$GAME"}
            ;;
        -h|--help)
            $PYTHON -m tools.naiz_img.inject --help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [-g game] [-y]"
            echo "       $0 --list-files"
            echo "       $0 --preview [-g game]"
            exit 1
            ;;
    esac
done

# Ensure venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo "首次运行，创建 Python 虚拟环境..."
    python3 -m venv "$VENV_DIR"
    "$PYTHON" -m pip install -r "$ROOT/tools/env_setup/requirements.txt"
fi

# Interactive mode if not in yes mode
if [ -z "$YES_FLAG" ]; then
    clear
    echo "Naiz — HDI 磁盘制作工具"
    echo "========================"

    # Game selection
    echo "Step 1: 游戏项目选择"
    GAMES=()
    if [ -d "$ROOT/games" ]; then
        while IFS= read -r -d '' game; do
            GAMES+=("$(basename "$game")")
        done < <(find "$ROOT/games" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)
    fi

    echo "  检测到以下游戏项目:"
    for i in "${!GAMES[@]}"; do
        echo "    $((i+1))) ${GAMES[$i]}"
    done

    while true; do
        read -p "  请选择 [1]: " choice
        choice=${choice:-1}
        if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#GAMES[@]}" ]; then
            GAME="${GAMES[$((choice-1))]}"
            break
        else
            echo "  无效选择，请重新输入"
        fi
    done
    echo ""

    # Confirmation
    echo "========================"
    echo "   游戏:   $GAME"
    echo "   基座:   tools/msdos5.hdi"
    echo "   输出:   disks/$GAME.hdi"
    echo "========================"

    read -p "  确认制作? (Y/n) " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]] && [ -n "$confirm" ]; then
        echo "已取消"
        exit 0
    fi
fi

# Execute
echo "正在制作 HDI 镜像..."
$PYTHON -m tools.naiz_img.inject --game "$GAME" ${YES_FLAG:---yes}
echo ""
echo "完成！输出文件: $ROOT/disks/$GAME.hdi"
