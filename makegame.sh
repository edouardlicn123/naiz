#!/bin/bash
# Naiz — 游戏工作流工具
# 制作/测试/编译一体化脚本
# 用法:
#   makegame.sh makegame <game>  编译项目数据并制作 HDI (build + make 合并)
#   makegame.sh make <game>    制作 HDI
#   makegame.sh test <game>    启动 NP2kai 测试 [--serial] [--porttest] [--auto]
#   makegame.sh audio          模拟器音频延迟设置 (BGM 颤音/电流声, 全局)
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

# ---- 打包方式选择（devdoc 185 / 193）--------------------------------------
#   cmpack   = tools_commercial + DOS/4GW（商业资源包）
#   openpack = tools_open + DOS/32A（开源资源包，extender 绑定进 EXE）
# 优先级: --pack <值> > 环境变量 NAIZ_PACK > 项目根 .naiz_pack > 自动探测。
# 解析结果导出为 NAIZ_PACK / NAIZ_EXTENDER，供 build_game.py 与 inject 读取。
PACK_MODE=""
_NORM_ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --pack)
            if [ $# -lt 2 ]; then
                echo "错误: --pack 需要一个值 (cmpack|openpack)" >&2
                exit 1
            fi
            PACK_MODE="$2"
            shift 2
            ;;
        --pack=*)
            PACK_MODE="${1#--pack=}"
            shift
            ;;
        *)
            _NORM_ARGS+=("$1")
            shift
            ;;
    esac
done
set -- "${_NORM_ARGS[@]}"

PACK_FILE="$ROOT/.naiz_pack"
if [ -z "$PACK_MODE" ] && [ -f "$PACK_FILE" ]; then
    PACK_MODE="$(tr -d '[:space:]' < "$PACK_FILE")"
fi
if [ -z "$PACK_MODE" ]; then
    if [ -d "$ROOT/tools_commercial" ]; then
        PACK_MODE=cmpack
    elif [ -d "$ROOT/tools_open" ]; then
        PACK_MODE=openpack
    else
        PACK_MODE=cmpack
    fi
fi
case "$PACK_MODE" in
    cmp|cmpack|commercial)  PACK_MODE=cmpack ;;
    open|openpack|oss)      PACK_MODE=openpack ;;
    *)
        echo "错误: 无效打包方式 '$PACK_MODE'（可选: cmpack | openpack）" >&2
        exit 1
        ;;
esac
export NAIZ_PACK="$PACK_MODE"
if [ "$PACK_MODE" = openpack ]; then
    export NAIZ_EXTENDER=dos32a
else
    export NAIZ_EXTENDER=dos4g
fi

pack_describe() {
    if [ "$PACK_MODE" = openpack ]; then
        echo "openpack (tools_open + DOS/32A 开源链)"
    else
        echo "cmpack (tools_commercial + DOS/4GW 商业链)"
    fi
}


# Emulator audio buffer latency menu (BGM "vibrato/buzz", devdoc 154).
# The NP2kai SDL output path inserts silence whenever its audio queue starves;
# the resulting AM frequency follows the buffer block size (Latencys).  This is
# a host-side emulator setting, so it is applied here (launcher), not by the
# game.  The Latencys values below MUST match AUDIO_LATENCY_LEVELS in
# tools/naiz_lib/np2kai_capture.py (guarded by test_makegame_audio.py).
audio_apply() {
    "$VENV_PYTHON" -m tools.env_setup.install_env audio-latency --latency "$1"
}

audio_menu() {
    while true; do
        echo ""
        echo "===== 模拟器音频延迟设置 (BGM 颤音/电流声) ====="
        echo "  写入 ~/.config/wxnp21kai/wxnp21kai.toml [NP21kai] 段（全局，影响所有游戏）"
        echo "  1) Off     — 不改动模拟器（使用其现有设置）"
        echo "  2) Short   — Latencys=47   (2048 块 ≈ 23ms)"
        echo "  3) Normal  — Latencys=93   (4096 块 ≈ 93ms)   ← 会出现 ~13.5Hz 颤音"
        echo "  4) Long    — Latencys=186  (8192 块 ≈ 186ms)  ← 推荐"
        echo "  5) Max     — Latencys=372  (16384 块 ≈ 372ms) ← 最彻底，音效延迟最明显"
        echo "  0) 返回"
        read -r -p "请选择 [0-5]: " lvl
        case "$lvl" in
            1) audio_apply off ;;
            2) audio_apply short ;;
            3) audio_apply normal ;;
            4) audio_apply long ;;
            5) audio_apply max ;;
            0) return ;;
            *) echo "无效选项" ;;
        esac
    done
}

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
    pack)
        # 切换/查看打包方式: 写入 $ROOT/.naiz_pack，后续命令以此为缺省。
        NEW_PACK="${1:-}"
        if [ -n "$NEW_PACK" ]; then
            case "$NEW_PACK" in
                cmp|cmpack|commercial) NEW_PACK=cmpack ;;
                open|openpack|oss)     NEW_PACK=openpack ;;
                *) echo "错误: 无效打包方式 '$NEW_PACK'（cmpack | openpack）"; exit 1 ;;
            esac
            echo "$NEW_PACK" > "$PACK_FILE"
            echo "[✓] 打包方式已切换为 $NEW_PACK（后续 makegame.sh 命令默认使用）"
            exit 0
        fi
        while true; do
            echo ""
            echo "===== 打包方式 ====="
            echo "  当前: $(pack_describe)"
            echo "  1) cmpack    — tools_commercial + DOS/4GW（商业链）"
            echo "  2) openpack  — tools_open + DOS/32A（开源链）"
            echo "  0) 返回"
            read -r -p "请选择 [0-2]: " p
            case "$p" in
                1) echo cmpack > "$PACK_FILE"; PACK_MODE=cmpack; break ;;
                2) echo openpack > "$PACK_FILE"; PACK_MODE=openpack; break ;;
                0) exit 0 ;;
                *) echo "无效选项" ;;
            esac
        done
        echo "[✓] 已保存到 .naiz_pack: $(cat "$PACK_FILE")"
        exit 0
        ;;

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

        # HDI freshness gate (0.3.010): `build` only deploys the DOS tree,
        # `make` is what injects it into disks/<game>.hdi.  Booting a stale
        # HDI silently runs an OLD engine: every log line looks normal, so
        # an A/B or a bug verdict drawn from it is invalid without any error
        # being raised.  Guard here, at the one moment the emulator is about
        # to be trusted, rather than in pytest (which would fire on every
        # source edit).  Guarded by tools/tests/test_hdi_freshness_guard.py.
        HDI_PATH="$ROOT/disks/$GAME.hdi"
        ENGINE_PATH="$ROOT/games/$GAME/engine.exe"
        if [ -f "$HDI_PATH" ] && [ -f "$ENGINE_PATH" ]; then
            if [ "$HDI_PATH" -ot "$ENGINE_PATH" ]; then
                echo "=== ERROR: HDI 过期: $HDI_PATH 比 $ENGINE_PATH 旧 ==="
                echo "    模拟器会运行旧引擎（build 只部署 DOS 树，make 才注入 HDI）。"
                echo "    修复: ./makegame.sh build $GAME && ./makegame.sh make $GAME"
                exit 1
            fi
        fi

        ARGS=()
        [ -n "$SERIAL" ] && ARGS+=("--serial")
        [ -n "$AUTO" ] && ARGS+=("--auto")
        exec "$VENV_PYTHON" -m tools.env_setup.install_env test-hdi --hdi "$HDI_PATH" "${ARGS[@]}"
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

    makegame)
        GAME="${1:-}"
        if [ -z "$GAME" ]; then
            echo "用法: makegame.sh makegame <game>"
            exit 1
        fi
        check_wcl386
        # build first (deploy the DOS tree + regenerate nb_config.h).  No exec
        # here, or the injection step below would never run; `makegame` is a
        # superset of `build` and `make`, which stay available on their own.
        "$VENV_PYTHON" -m tools.naiz_build.build_game "$GAME"
        echo "=== 制作 HDI 镜像: $GAME [$(pack_describe)] ==="
        cd "$ROOT" && exec "$VENV_PYTHON" -m tools.naiz_img.inject --game "$GAME" --yes
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

        echo "=== 制作 HDI 镜像: $GAME [$(pack_describe)] ==="
        # devdoc 184: `build` 部署 DOS 树（含 core/engine*.exe → games/<game>/），
        # `make` 只打包。若 core 引擎比 games/<game>/ 里的新，说明这次改动
        # 没经过 build —— 打包会静默跑旧引擎（本次量化踩过：埋点不在日志里，
        # 白跑一轮）。与 test 的 HDI 过期守卫同一策略：报错指路。
        # 开源链的产物名不同（engine32a.exe / engine_a32a.exe），但 deploy_engine
        # 统一重命名为 engine.exe / engine_a.exe，故按打包方式映射。
        if [ "$PACK_MODE" = openpack ]; then
            CORE_PAIRS=("$ROOT/core/engine32a.exe->engine.exe"
                        "$ROOT/core/engine_a32a.exe->engine_a.exe")
        else
            CORE_PAIRS=("$ROOT/core/engine.exe->engine.exe"
                        "$ROOT/core/engine_a.exe->engine_a.exe")
        fi
        for CORE_PAIR in "${CORE_PAIRS[@]}"; do
            CORE_EXE="${CORE_PAIR%%->*}"
            DEPLOYED_NAME="${CORE_PAIR##*->}"
            GAME_EXE="$ROOT/games/$GAME/$DEPLOYED_NAME"
            if [ -f "$CORE_EXE" ] && { [ ! -f "$GAME_EXE" ] || [ "$GAME_EXE" -ot "$CORE_EXE" ]; }; then
                echo "=== ERROR: games/$GAME/$DEPLOYED_NAME 落后于 core/$(basename "$CORE_EXE") ==="
                echo "    make 只注入 games/<game>/，不部署引擎。"
                echo "    修复: ./makegame.sh build $GAME && ./makegame.sh make $GAME"
                exit 1
            fi
        done
        cd "$ROOT" && exec "$VENV_PYTHON" -m tools.naiz_img.inject --game "$GAME" --yes
        ;;

    audio)
        # Emulator audio latency (global, not per-game): see devdoc 154.
        audio_menu
        exit 0
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
                echo "=== $GAME  [打包方式: $PACK_MODE] ==="
                echo "操作选择:"
                echo "  1) makegame      — 编译项目数据 + 制作 HDI (build + make)"
                echo "  2) build         — 编译项目数据"
                echo "  3) make          — 制作 HDI 镜像"
                echo "  4) test          — 启动 NP2kai 测试"
                echo "  5) test --porttest — 串口硬件测试"
                echo "  6) audio         — 模拟器音频延迟设置 (全局)"
                echo "  7) pack          — 切换打包方式 (cmpack / openpack)"
                echo "  0) 返回"
                read -p "请选择 [0-7]: " action

                case "$action" in
                    1) "$0" makegame "$GAME" ;;
                    2) "$0" build "$GAME" ;;
                    3) "$0" make "$GAME" ;;
                    4) "$0" test "$GAME" ;;
                    5) "$0" test "$GAME" --porttest ;;
                    6) audio_menu ;;
                    7) "$0" pack ;;
                    0) break ;;
                    *) echo "无效选项" ;;
                esac
                read -p "按 Enter 返回..."
            done
        done
        ;;

    *)
        echo "用法: $0 {makegame|make|test|build|i18n-gen|audio|pack} [--pack cmpack|openpack] [args]"
        echo "  makegame <game> 编译游戏数据并制作 HDI (build + make 合并, 一步到位)"
        echo "  build <game>    编译游戏数据 (PNG→MAG, 引擎, 场景, IMAGE.DAT, 运行时)"
        echo "  make <game>     制作 HDI 镜像 (仅注入 games/<game> → disks/<game>.hdi)"
        echo "  test <game>     启动 NP2kai 测试 [--serial] [--porttest] [--auto]"
        echo "    --porttest    串口硬件测试 (serialwrite.com + PTY + 验证)"
        echo "  audio           模拟器音频延迟设置 (BGM 颤音/电流声, 全局)"
        echo "  i18n-gen <game> 生成翻译模板 [--force]"
        echo "  pack [cmpack|openpack]  查看/切换打包方式（写入 .naiz_pack 作为默认）"
        echo ""
        echo "  --pack cmpack   = tools_commercial + DOS/4GW（商业链，默认）"
        echo "  --pack openpack = tools_open + DOS/32A（开源链，无闭源组件）"
        echo ""
        echo "无参数: 交互式游戏工作流"
        echo ""
        echo "首次使用请先运行 start.sh 配置环境"
        exit 1
        ;;
esac
