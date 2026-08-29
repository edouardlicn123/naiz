#!/bin/bash
# Naiz — 游戏工作流工具
# 制作/测试/编译一体化脚本
# 用法:
#   makegame.sh make <game>    制作 HDI
#   makegame.sh test <game>    启动 NP2kai 测试 [--serial] [--porttest] [--auto]
#   makegame.sh build <proj>   编译项目数据
#   makegame.sh                交互式游戏工作流
#
# 注意: 首次使用前请先运行 start.sh 配置环境

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "$ROOT/core/engine/main.c" ]; then
    echo "错误: 无法确认 Naiz 项目根目录（找不到 core/engine/main.c）"
    echo "  makegame.sh 路径: $0"
    echo "  解析 ROOT: $ROOT"
    echo "请确保在项目根目录下运行: bash makegame.sh"
    exit 1
fi
source "$ROOT/tools/env_setup/ensure_venv.sh"

if [ ! -d "$VENV_DIR" ]; then
    echo "错误: 未找到 Python 虚拟环境"
    echo "请先运行: bash start.sh pip"
    exit 1
fi

check_wcl386() {
    # 复用 core/detect_watcom.sh 的统一搜索逻辑（$WATCOM 环境变量 → ~/open-watcom-v2/rel → /opt/watcom）
    # 找不到时 detect_watcom.sh 会 exit 1；set -e 下此处不会继续执行。
    # source 会导出 $WATCOM 并更新 PATH。
    source "$ROOT/core/detect_watcom.sh"
    if ! command -v wcl386 &>/dev/null; then
        echo "警告: detect_watcom.sh 找到了 $WATCOM 但 wcl386 不在 PATH 中"
        return 1
    fi
    return 0
}

SUBCOMMAND="${1:-}"
# shift with stderr redirect: '2>/dev/null' is fd redirect, NOT shift argument.
# Actual effect: shift by 1 (removes subcommand only). Verified: bash test.
shift 2>/dev/null || true

case "$SUBCOMMAND" in
    test)
        GAME="${1:-}"
        SERIAL=""
        PORTTEST=""
        AUTO=""
        for arg in "$@"; do
            [ "$arg" = "--serial" ] && SERIAL="--serial"
            [ "$arg" = "--porttest" ] && PORTTEST="1"
            [ "$arg" = "--auto" ] && AUTO="--auto"
        done
        if [ -z "$GAME" ]; then
            echo "用法: makegame.sh test <game> [--serial] [--porttest] [--auto]"
            exit 1
        fi

        if [ -n "$PORTTEST" ]; then
            echo "=== 串口端口测试: $GAME ==="
            "$VENV_PYTHON" -m tools.diag.np2kai_serial --game "$GAME"
            exit $?
        fi

        # --auto: swap in engine_a.exe if available
        if [ -n "$AUTO" ]; then
            GAME_DIR="$ROOT/games/$GAME"
            if [ -f "$GAME_DIR/engine_a.exe" ]; then
                cp "$GAME_DIR/engine_a.exe" "$GAME_DIR/engine.exe"
                echo "[auto] engine_a.exe → engine.exe"
                # Rebuild HDI with auto engine
                cd "$ROOT" && "$VENV_PYTHON" -m tools.naiz_img.inject --game "$GAME" --yes
            else
                echo "[auto] 警告: $GAME_DIR/engine_a.exe 不存在，使用原 engine.exe"
            fi
        fi

        ARGS=()
        [ -n "$SERIAL" ] && ARGS+=("--serial")
        [ -n "$AUTO" ] && ARGS+=("--auto")
        exec "$VENV_PYTHON" -m tools.env_setup.install_env test-hdi --hdi "$ROOT/disks/$GAME.hdi" "${ARGS[@]}"
        ;;

    build)
        GAME="${1:-}"
        if [ -z "$GAME" ]; then
            echo "用法: makegame.sh build <game>"
            exit 1
        fi
        check_wcl386
        exec "$VENV_PYTHON" -m tools.naiz_build.build_game "$GAME"
        ;;

    i18n-gen)
        GAME="${1:-}"
        I18N_ARGS=()
        if [ "${2:-}" = "--force" ]; then
            I18N_ARGS+=("--force")
        fi
        if [ -z "$GAME" ]; then
            echo "用法: makegame.sh i18n-gen <game> [--force]"
            exit 1
        fi
        exec "$VENV_PYTHON" -m tools.naiz_conv.i18n_gen "$ROOT/projects/$GAME" "${I18N_ARGS[@]}"
        ;;

    make)
        GAME="${1:-}"
        if [ -z "$GAME" ]; then
            echo "用法: makegame.sh make <game>"
            exit 1
        fi

        echo "=== 制作 HDI 镜像: $GAME ==="
        cd "$ROOT" && exec "$VENV_PYTHON" -m tools.naiz_img.inject --game "$GAME" --yes
        ;;

    "")
        # 交互模式 — 项目工作流
        while true; do
            GAMES=()
            while IFS= read -r -d '' game; do
                GAMES+=("$(basename "$game")")
            done < <(find "$ROOT/projects" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)

            if [ ${#GAMES[@]} -eq 0 ]; then
                echo "错误: projects/ 下没有项目"
                exit 1
            fi

            echo ""
            echo "===== Naiz 项目工作流 ====="
            echo "检测到以下项目:"
            for i in "${!GAMES[@]}"; do
                echo "  $((i+1))) ${GAMES[$i]}"
            done
            echo "  0) 退出"
            read -r -p "请选择游戏 [1]: " choice
            choice=${choice:-1}
            if [ "$choice" = "0" ]; then
                exit 0
            fi
            if ! [[ "$choice" =~ ^[0-9]+$ ]] \
               || [ "$((choice-1))" -ge "${#GAMES[@]}" ]; then
                echo "无效选择: $choice"
                exit 1
            fi
            GAME="${GAMES[$((choice-1))]}"

            while true; do
                echo ""
                echo "=== $GAME ==="
                echo "操作选择:"
                echo "  1) build         — 编译项目数据"
                echo "  2) make          — 制作 HDI 镜像"
                echo "  3) test          — 启动 NP2kai 测试"
                echo "  4) test --porttest — 串口硬件测试"
                echo "  0) 返回"
                read -p "请选择 [0-4]: " action

                case "$action" in
                    1) "$0" build "$GAME" ;;
                    2) "$0" make "$GAME" ;;
                    3) "$0" test "$GAME" ;;
                    4) "$0" test "$GAME" --porttest ;;
                    0) break ;;
                    *) echo "无效选项" ;;
                esac
                read -p "按 Enter 返回..."
            done
        done
        ;;

    *)
        echo "用法: $0 {make|test|build|i18n-gen} [args]"
        echo "  build <game>    编译游戏数据 (PNG→MAG, 引擎, 场景, IMAGE.DAT, 运行时)"
        echo "  make <game>     制作 HDI 镜像 (仅注入 games/<game>/ → disks/<game>.hdi)"
        echo "  test <game>     启动 NP2kai 测试 [--serial] [--porttest] [--auto]"
        echo "    --porttest    串口硬件测试 (serialwrite.com + PTY + 验证)"
        echo "  i18n-gen <game> 生成翻译模板 [--force]"
        echo ""
        echo "无参数: 交互式游戏工作流"
        echo ""
        echo "首次使用请先运行 start.sh 配置环境"
        exit 1
        ;;
esac
