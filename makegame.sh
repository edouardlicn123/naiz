#!/bin/bash
# Naiz — 游戏工作流工具
# 制作/测试/编译一体化脚本
# 用法:
#   makegame.sh make <game>    制作 HDI
#   makegame.sh test <game>    启动 NP2kai 测试
#   makegame.sh build <proj>   编译项目数据
#   makegame.sh                交互式游戏工作流

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$ROOT/tools/env_setup/venv"
PYTHON="$VENV_DIR/bin/python3"

# Ensure venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo "创建 Python 虚拟环境..."
    python3 -m venv "$VENV_DIR"
    "$PYTHON" -m pip install -r "$ROOT/tools/env_setup/requirements.txt"
fi

SUBCOMMAND="${1:-}"
shift 2>/dev/null || true

case "$SUBCOMMAND" in
    make)
        GAME="${1:-}"
        if [ -z "$GAME" ]; then
            echo "用法: makegame.sh make <game>"
            exit 1
        fi
        cd "$ROOT" && exec "$PYTHON" -m tools.naiz_img.inject --game "$GAME" --yes
        ;;

    test)
        GAME="${1:-}"
        if [ -z "$GAME" ]; then
            echo "用法: makegame.sh test <game>"
            exit 1
        fi
        exec "$PYTHON" "$ROOT/tools/env_setup/install_env.py" test-hdi --hdi "$ROOT/disks/$GAME.hdi"
        ;;

    build)
        PROJ="${1:-}"
        if [ -z "$PROJ" ]; then
            echo "用法: makegame.sh build <project>"
            exit 1
        fi
        if [ ! -d "$ROOT/projects/$PROJ" ]; then
            echo "错误: 项目不存在: $ROOT/projects/$PROJ"
            exit 1
        fi
        exec make -C "$ROOT/projects/$PROJ"
        ;;

    "")
        # 交互模式
        while true; do
            GAMES=()
            while IFS= read -r -d '' game; do
                GAMES+=("$(basename "$game")")
            done < <(find "$ROOT/games" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)

            if [ ${#GAMES[@]} -eq 0 ]; then
                echo "错误: games/ 下没有游戏"
                exit 1
            fi

            echo "===== 游戏工作流 ====="
            echo "检测到以下游戏:"
            for i in "${!GAMES[@]}"; do
                echo "  $((i+1))) ${GAMES[$i]}"
            done
            echo "  0) 退出"
            read -p "请选择游戏 [1]: " choice
            choice=${choice:-1}
            [ "$choice" = "0" ] && exit 0
            GAME="${GAMES[$((choice-1))]}"

            while true; do
                echo ""
                echo "=== $GAME ==="
                echo "操作选择:"
                echo "  1) build  — 编译项目数据"
                echo "  2) make   — 制作 HDI 镜像"
                echo "  3) test   — 启动 NP2kai 测试"
                echo "  4) all    — build → make → test"
                echo "  0) 返回"
                read -p "请选择 [0-4]: " action

                case $action in
                    1) "$0" build "$GAME" ;;
                    2) "$0" make "$GAME" ;;
                    3) "$0" test "$GAME" ;;
                    4) "$0" build "$GAME" && "$0" make "$GAME" && "$0" test "$GAME" ;;
                    0) break ;;
                    *) echo "无效选项" ;;
                esac
                read -p "按 Enter 返回..."
            done
        done
        ;;

    *)
        echo "用法: $0 {make|test|build} [args]"
        echo "  make <game>    制作 HDI 镜像"
        echo "  test <game>    启动 NP2kai 测试"
        echo "  build <proj>   编译项目数据"
        echo ""
        echo "无参数: 交互式游戏工作流"
        exit 1
        ;;
esac
