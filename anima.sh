#!/bin/bash
# Naiz — 动画制作工具
# 动画脚本(.na) → .ANI 容器组装（制作侧，见 devdocs/79）
# 用法:
#   anima.sh                        交互式动画制作菜单
#   anima.sh init <项目>            创建动画项目骨架 animation/projects/<项目>/
#   anima.sh register <项目>        登记素材到项目 db/<项目>.db
#   anima.sh check <项目>           只读对账素材登记（有差异退出码 1）
#   anima.sh mp4 <项目>             扫描 anim/*.mp4 转换为 .ANI
#   anima.sh build <项目>/<脚本>    编译单个动画脚本
#   anima.sh buildall [--flags]     编译全部项目的全部脚本
#   anima.sh list                   列出可用动画脚本（<项目>/<脚本>）
#
# 项目架构: animation/projects/<项目名>/{config.toml,scripts/,db/}
# 脚本目录: animation/projects/<项目名>/scripts/<名>.na（平铺单层；
#           .na 后缀专属动画脚本，与剧本脚本 .nb 分离）
# 素材目录: assets/<项目名>/anim/（png/pal，与游戏构建管线同址）
# 输出目录: animation/output/<NAME>.ANI
#
# 注意: 首次使用前请先运行 start.sh 配置环境

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "$ROOT/core/engine/main.c" ]; then
    echo "错误: 无法确认 Naiz 项目根目录（找不到 core/engine/main.c）"
    echo "  anima.sh 路径: $0"
    echo "  解析 ROOT: $ROOT"
    echo "请确保在项目根目录下运行: bash anima.sh"
    exit 1
fi
source "$ROOT/tools/env_setup/ensure_venv.sh"

if [ ! -d "$VENV_DIR" ]; then
    echo "错误: 未找到 Python 虚拟环境"
    echo "请先运行: bash start.sh pip"
    exit 1
fi

mkdir -p "$ROOT/animation/projects" "$ROOT/animation/output"

# 列出候选动画项目（含 config.toml 的目录，逐行输出）
_list_projects() {
    "$VENV_PYTHON" -m tools.naiz_build.anim_project list
}

# 二级菜单: 项目操作（检查登记 / register / 生成动画）
_proj_menu() {
    local P="$1"
    while true; do
        echo ""
        echo "===== 项目: $P ====="
        echo "操作选择:"
        echo "  1) 检查素材登记 (check，只读对账)"
        echo "  2) register 同步登记库"
        echo "  3) 生成动画（选择 .na 脚本）"
        echo "  4) MP4 → ANI 转换（扫描 anim/*.mp4）"
        echo "  0) 返回上级"
        read -r -p "请选择 [0-4]: " ochoice
        case "$ochoice" in
            0)
                return
                ;;
            1)
                if ! "$0" check "$P"; then
                    echo "对账存在差异或检查失败: $P"
                fi
                read -r -p "按 Enter 返回..."
                ;;
            2)
                if ! "$0" register "$P"; then
                    echo "登记失败: $P"
                fi
                read -r -p "按 Enter 返回..."
                ;;
            3)
                _script_menu "$P"
                ;;
            4)
                if ! "$0" mp4 "$P"; then
                    echo "MP4 转换失败: $P"
                fi
                read -r -p "按 Enter 返回..."
                ;;
            '')
                ;;
            *)
                echo "无效选项: $ochoice"
                ;;
        esac
    done
}

# 三级菜单: 扫描项目 scripts/*.na 并选择要生成的脚本
_script_menu() {
    local P="$1"
    while true; do
        local SCRIPTS=()
        shopt -s nullglob
        for f in "$ROOT/animation/projects/$P/scripts/"*.na; do
            SCRIPTS+=("$(basename "$f" .na)")
        done
        shopt -u nullglob

        echo ""
        echo "===== 生成动画: $P ====="
        if [ ${#SCRIPTS[@]} -eq 0 ]; then
            echo "(该项目暂无动画脚本 — 在 animation/projects/$P/scripts/ 下创建 .na)"
        else
            echo "选择动画脚本:"
            for i in "${!SCRIPTS[@]}"; do
                echo "  $((i+1))) ${SCRIPTS[$i]}"
            done
        fi
        echo "  0) 返回上级"
        read -r -p "请选择 [0/序号]: " schoice
        case "$schoice" in
            0)
                return
                ;;
            '')
                ;;
            *[!0-9]*)
                echo "无效选择: $schoice"
                ;;
            *)
                if ! [[ "$schoice" =~ ^[0-9]+$ ]] \
                   || [ "$schoice" -lt 1 ] \
                   || [ "$((schoice-1))" -ge "${#SCRIPTS[@]}" ]; then
                    echo "无效选择: $schoice"
                else
                    _action_menu "$P" "${SCRIPTS[$((schoice-1))]}"
                fi
                ;;
        esac
    done
}

# 四级菜单: 单脚本的构建操作
_action_menu() {
    local P="$1" NAME="$2"
    while true; do
        echo ""
        echo "=== $P/$NAME ==="
        echo "操作选择:"
        echo "  1) build        — 构建 .ANI（按脚本项目名自动推导色板）"
        echo "  2) build --sync — 构建前先同步素材登记库"
        echo "  0) 返回"
        read -r -p "请选择 [0-2]: " action
        case "$action" in
            1)
                if ! "$0" build "$P/$NAME"; then
                    echo "构建失败: $P/$NAME"
                fi
                ;;
            2)
                if ! "$0" build "$P/$NAME" --sync; then
                    echo "构建失败: $P/$NAME"
                fi
                ;;
            0)
                return
                ;;
            *)
                echo "无效选项"
                ;;
        esac
        read -r -p "按 Enter 返回..."
    done
}

SUBCOMMAND="${1:-}"
shift 2>/dev/null || true

case "$SUBCOMMAND" in
    init)
        PROJECT="${1:-}"
        if [ -z "$PROJECT" ]; then
            echo "用法: anima.sh init <项目>"
            echo "  创建 animation/projects/<项目>/{config.toml,scripts/,db/}"
            exit 1
        fi
        exec "$VENV_PYTHON" -m tools.naiz_build.anim_project init "$PROJECT"
        ;;

    register)
        PROJECT="${1:-}"
        if [ -z "$PROJECT" ]; then
            echo "用法: anima.sh register <项目>"
            echo "  扫描 assets/<项目>/anim/ 下 *.png/*.pal，"
            echo "  登记到 animation/projects/<项目>/db/<项目>.db（裸名字索引）"
            exit 1
        fi
        exec "$VENV_PYTHON" -m tools.naiz_build.anim_register "$PROJECT"
        ;;

    check)
        PROJECT="${1:-}"
        if [ -z "$PROJECT" ]; then
            echo "用法: anima.sh check <项目>"
            echo "  只读对账 assets/<项目>/anim/ 与 db/<项目>.db；"
            echo "  存在差异（未登记/失效行/待更新）时退出码 1，不写库"
            exit 1
        fi
        exec "$VENV_PYTHON" -m tools.naiz_build.anim_register --check "$PROJECT"
        ;;

    mp4)
        PROJECT="${1:-}"
        if [ -z "$PROJECT" ]; then
            echo "用法: anima.sh mp4 <项目> [--fps N] [--width W] [--height H]"
            echo "  扫描 assets/<项目>/anim/ 下 *.mp4，转换为 .ANI"
            echo "  默认: 640x400, 10fps, fullscreen"
            exit 1
        fi
        shift 2>/dev/null || true
        exec "$VENV_PYTHON" -m tools.naiz_build.mp4_to_ani "$PROJECT" "$@"
        ;;

    build)
        SPEC="${1:-}"
        if [ -z "$SPEC" ] || [[ "$SPEC" != */* ]]; then
            echo "用法: anima.sh build <项目>/<脚本> [--out PATH] [--sync]"
            echo "  示例: anima.sh build animatest/animatest"
            exit 1
        fi
        PROJECT="${SPEC%%/*}"
        NAME="${SPEC#*/}"
        if [ -z "$PROJECT" ] || [ -z "$NAME" ] || [[ "$NAME" == */* ]]; then
            echo "错误: 寻址格式须为 <项目>/<脚本>（恰好一个 /）: $SPEC"
            exit 1
        fi
        shift 2>/dev/null || true
        SCRIPT="$ROOT/animation/projects/$PROJECT/scripts/$NAME.na"
        if [ ! -f "$SCRIPT" ]; then
            echo "错误: 动画脚本不存在: $SCRIPT"
            echo "可用脚本:"
            "$0" list || true
            exit 1
        fi
        # --project 置于 "$@" 之后: 用户重复传入时以寻址项目名为准
        exec "$VENV_PYTHON" -m tools.naiz_build.anim_import \
            "$SCRIPT" "$@" --project "$PROJECT"
        ;;

    buildall)
        BUILDALL_ARGS=()
        for arg in "$@"; do
            BUILDALL_ARGS+=("$arg")
        done
        PROJECTS=()
        while IFS= read -r p; do
            [ -n "$p" ] && PROJECTS+=("$p")
        done < <(_list_projects)
        if [ ${#PROJECTS[@]} -eq 0 ]; then
            echo "错误: animation/projects/ 下没有动画项目"
            echo "先用 anima.sh init <项目> 创建项目骨架"
            exit 1
        fi
        OK=0
        FAILED=0
        FAILED_NAMES=()
        shopt -s nullglob
        for p in "${PROJECTS[@]}"; do
            for script in "$ROOT/animation/projects/$p/scripts/"*.na; do
                echo ""
                echo "=== 编译动画: $p/$(basename "$script" .na) ==="
                if "$VENV_PYTHON" -m tools.naiz_build.anim_import \
                    "$script" "${BUILDALL_ARGS[@]}"; then
                    OK=$((OK+1))
                else
                    FAILED=$((FAILED+1))
                    FAILED_NAMES+=("$p/$(basename "$script")")
                fi
            done
        done
        shopt -u nullglob
        echo ""
        echo "=== 汇总: $OK 成功 / $FAILED 失败 ==="
        if [ "$FAILED" -gt 0 ]; then
            for name in "${FAILED_NAMES[@]}"; do
                echo "  失败: $name"
            done
            exit 1
        fi
        ;;

    list)
        PROJECTS=()
        while IFS= read -r p; do
            [ -n "$p" ] && PROJECTS+=("$p")
        done < <(_list_projects)
        if [ ${#PROJECTS[@]} -eq 0 ]; then
            echo "(无动画项目 — 用 anima.sh init <项目> 创建)"
            exit 0
        fi
        FOUND=0
        shopt -s nullglob
        for p in "${PROJECTS[@]}"; do
            for script in "$ROOT/animation/projects/$p/scripts/"*.na; do
                echo "$p/$(basename "$script" .na)"
                FOUND=1
            done
        done
        shopt -u nullglob
        if [ "$FOUND" -eq 0 ]; then
            echo "(动画项目存在但均无脚本 — 在各项目 scripts/ 下创建 .na)" >&2
        fi
        ;;

    "")
        # 交互模式 — 两级菜单（镜像 makegame.sh 工作流）
        while true; do
            PROJECTS=()
            while IFS= read -r p; do
                [ -n "$p" ] && PROJECTS+=("$p")
            done < <(_list_projects)

            echo ""
            echo "===== Naiz 动画制作 ====="
            if [ ${#PROJECTS[@]} -eq 0 ]; then
                echo "(尚无动画项目)"
            else
                echo "选择动画项目:"
                for i in "${!PROJECTS[@]}"; do
                    echo "  $((i+1))) ${PROJECTS[$i]}"
                done
            fi
            echo "  i) 新建项目 (init)"
            echo "  0) 退出"
            read -r -p "请选择 [0/i/序号]: " choice
            case "$choice" in
                0)
                    exit 0
                    ;;
                i|I)
                    read -r -p "新项目名: " NEWP
                    if [ -n "$NEWP" ]; then
                        if ! "$0" init "$NEWP"; then
                            echo "初始化失败: $NEWP"
                        fi
                        read -r -p "按 Enter 返回..."
                    fi
                    ;;
                '')
                    ;;
                *)
                    if ! [[ "$choice" =~ ^[0-9]+$ ]] \
                       || [ "$choice" -lt 1 ] \
                       || [ "$((choice-1))" -ge "${#PROJECTS[@]}" ]; then
                        echo "无效选择: $choice"
                    else
                        _proj_menu "${PROJECTS[$((choice-1))]}"
                    fi
                    ;;
            esac
        done
        ;;

    *)
        echo "用法: $0 [{init|register|check|mp4|build|buildall|list} args]"
        echo "  init <项目>           创建动画项目骨架 animation/projects/<项目>/"
        echo "                        （config.toml + scripts/ + db/）"
        echo "  register <项目>       登记 assets/<项目>/anim/ 素材到项目 db/<项目>.db"
        echo "  check <项目>          只读对账素材登记库（有差异退出码 1）"
        echo "  mp4 <项目>            扫描 anim/*.mp4 转换为 .ANI（交互选择文件）"
        echo "       [--fps N]        采样帧率（默认 10）"
        echo "       [--width W]      目标宽度（默认 640）"
        echo "       [--height H]     目标高度（默认 400）"
        echo "  build <项目>/<脚本>   编译 <项目>/scripts/<脚本>.na → animation/output/"
        echo "       [--out PATH]     指定输出路径"
        echo "       [--sync]         构建前先同步该项目素材登记库"
        echo "  buildall [--flags]    编译全部项目的全部脚本（汇总结果）"
        echo "  list                  列出全部 <项目>/<脚本>"
        echo ""
        echo "无参数: 交互式动画制作菜单"
        echo ""
        echo "动画脚本为 .na 后缀，与剧本脚本 .nb 分离（devdocs/79）"
        echo "首次使用请先运行 start.sh 配置环境"
        exit 1
        ;;
esac
