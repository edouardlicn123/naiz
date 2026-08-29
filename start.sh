#!/bin/bash
# Naiz — 环境配置脚本
# 用法:
#   start.sh                 交互式配置菜单
#   start.sh check           环境检测
#   start.sh pip             安装 Python 依赖
#   start.sh deps            安装系统工具链
#   start.sh np2kai          编译安装 NP2kai
#   start.sh retroarch       备用模拟器 (RetroArch)
#   start.sh watcom          安装 Open Watcom
#   start.sh djgpp           安装 DJGPP
#   start.sh mirror          Git 仓库来源设置 (GitHub/国内镜像)
#   start.sh commercial      商用资源下载 (tools_commercial/)
#   start.sh audit           符号封装/拆分审计日志 (logs/)
#   start.sh fullaudit       全项目规则审计: 规则(增量)+pytest+py_compile+bash-n+symbol_audit+make

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

source "$ROOT/tools/sdl_env.sh"
source "$ROOT/tools/env_setup/ensure_venv.sh"
ensure_venv

run_env_cmd() {
    "$VENV_PYTHON" -m tools.env_setup.install_env "$@"
}

# 符号封装/拆分审计：运行 tools.diag.symbol_audit，结果写时间戳日志并同步输出到终端。
run_audit() {
    echo "===== 符号封装/拆分审计 ====="
    mkdir -p "$ROOT/logs"
    local stamp out
    stamp="$(date +%Y%m%d_%H%M%S)"
    out="$ROOT/logs/symbol_audit_${stamp}.log"
    {
        echo "=== symbol_audit ${stamp} ==="
        echo "命令: ${VENV_PYTHON} -m tools.diag.symbol_audit"
        echo ""
    } > "$out"
    if ! "$VENV_PYTHON" -m tools.diag.symbol_audit >> "$out" 2>&1; then
        rm -f "$out"
        echo "[✗] 审计失败，日志已删除"
        return 1
    fi
    cat "$out"
    echo ""
    echo "[✓] 审计完成: $out（$(wc -l < "$out") 行）"
}

# 全项目规则审计（含增量、git 状态文件 audit_state.json）：
# 1) tools.audit.audit(规则) 2) pytest 3) py_compile 4) bash -n 5) symbol_audit 6) make(可选 --no-make)
run_fullaudit() {
    local do_make=1
    [[ "${1:-}" == "--no-make" ]] && do_make=0
    local stamp out overall=0
    stamp="$(date +%Y%m%d_%H%M%S)"
    out="$ROOT/logs/fullaudit_${stamp}.log"
    mkdir -p "$ROOT/logs"
    echo "===== 全项目规则审计 $(date '+%F %T') =====" | tee "$out"

    echo "--- [1/6] 规则审计 (git 增量, audit_state.json) ---" | tee -a "$out"
    local ar=0
    if ! "$VENV_PYTHON" -m tools.audit.audit >> "$out" 2>&1; then
        ar=$?
        echo "[✗] 规则审计发现确定性违规 (exit $ar)" | tee -a "$out"
        overall=1
    else
        echo "[✓] 规则审计通过" | tee -a "$out"
    fi

    echo "--- [2/6] pytest ($ROOT/tools/tests/) ---" | tee -a "$out"
    if ! "$VENV_PYTHON" -m pytest "$ROOT/tools/tests/" -q >> "$out" 2>&1; then
        echo "[✗] pytest 失败" | tee -a "$out"
        overall=1
    else
        echo "[✓] pytest 通过" | tee -a "$out"
    fi

    echo "--- [3/6] py_compile (tools/**/*.py) ---" | tee -a "$out"
    local pc=0 f
    while IFS= read -r -d '' f; do
        if ! "$VENV_PYTHON" -m py_compile "$f"; then
            echo "[✗] py_compile 失败: $f" | tee -a "$out"
            pc=1
        fi
    done < <(find "$ROOT/tools" -name '*.py' -not -path '*/venv/*' \
                 -not -path '*/__pycache__/*' -print0)
    if [ "$pc" -ne 0 ]; then overall=1; else echo "[✓] py_compile 通过" | tee -a "$out"; fi

    echo "--- [4/6] bash -n (shell 语法) ---" | tee -a "$out"
    local sn=0
    for s in "$ROOT/makegame.sh" "$ROOT/start.sh" "$ROOT"/core/*.sh; do
        if ! bash -n "$s" 2>>"$out"; then echo "[✗] bash -n 失败: $s" | tee -a "$out"; sn=1; fi
    done
    if [ "$sn" -ne 0 ]; then overall=1; else echo "[✓] bash -n 通过" | tee -a "$out"; fi

    echo "--- [5/6] symbol_audit (A 节: 未用 static/导出) ---" | tee -a "$out"
    if ! "$VENV_PYTHON" -m tools.diag.symbol_audit -s A >> "$out" 2>&1; then
        echo "[✗] symbol_audit 失败" | tee -a "$out"
        overall=1
    else
        echo "[✓] symbol_audit 通过" | tee -a "$out"
    fi

    if [ "$do_make" -eq 1 ]; then
        echo "--- [6/6] make -C core ---" | tee -a "$out"
        if ! make -C "$ROOT/core" >> "$out" 2>&1; then
            echo "[✗] make 失败" | tee -a "$out"
            overall=1
        else
            if grep -qE 'Warning|Error' "$out"; then
                echo "[!] make 有 Warning/Error 输出（见上）" | tee -a "$out"
            else
                echo "[✓] make 通过 (0 err / 0 warn)" | tee -a "$out"
            fi
        fi
    else
        echo "--- [6/6] make 已跳过 (--no-make) ---" | tee -a "$out"
    fi

    echo "" | tee -a "$out"
    if [ "$overall" -eq 0 ]; then
        echo "[✓] fullaudit 全部通过: $out" | tee -a "$out"
    else
        echo "[✗] fullaudit 存在失败项: $out" | tee -a "$out"
        return 1
    fi
}

# 商用资源包下载源（格式: 描述|URL|sha256）
# 添加新下载点：在数组追加一行，或子菜单选"手动输入 URL"。
COMMERCIAL_DOWNLOADS=(
    "GitHub Releases (naiz_cmpack) v1.1|https://github.com/edouardlicn123/naiz_cmpack/releases/download/1.1/tools_commercial.zip|020af0e498e013886b196f8c8d6811a10618c6b51ba176608138e7b987a388a3"
)

fetch_commercial() {
    local desc="$1" url="$2" sha="$3"
    echo ""
    echo "===== 商用资源下载: $desc ====="
    if [ -d "$ROOT/tools_commercial" ]; then
        echo "  tools_commercial/ 已存在。"
        read -p "  输入 y 覆盖重新下载，其他键跳过: " ans
        if [ "$ans" != "y" ] && [ "$ans" != "Y" ]; then
            echo "[✓] 已跳过下载"
            return 0
        fi
    fi
    local tmpzip
    tmpzip="$(mktemp /tmp/tools_commercial.XXXXXX.zip)"
    trap 'rm -f "$tmpzip"' RETURN
    echo "  下载中: $url"
    if ! curl -fsSL --retry 3 -o "$tmpzip" "$url"; then
        echo "[✗] 下载失败: $url"
        rm -f "$tmpzip"
        return 1
    fi
    echo "  校验 sha256..."
    local got
    got="$(sha256sum "$tmpzip" | awk '{print $1}')"
    if [ -n "$sha" ] && [ "$got" != "$sha" ]; then
        echo "[✗] sha256 校验失败: $got"
        rm -f "$tmpzip"
        return 1
    fi
    echo "  解压到项目根目录..."
    if ! unzip -q -o "$tmpzip" -d "$ROOT"; then
        echo "[✗] 解压失败"
        rm -f "$tmpzip"
        return 1
    fi
    rm -f "$tmpzip"
    if [ -d "$ROOT/tools_commercial" ]; then
        echo "[✓] 商用资源已就绪: tools_commercial/"
    else
        echo "[!] 解压完成但未找到 tools_commercial/ 目录，请检查"
        return 1
    fi
    return 0
}

commercial_menu() {
    while true; do
        clear
        echo "===================================="
        echo "     商用资源下载"
        echo "===================================="
        echo "  0) 返回"
        local i=1
        for entry in "${COMMERCIAL_DOWNLOADS[@]}"; do
            echo "  $i) ${entry%%|*}"
            i=$((i+1))
        done
        echo "  $i) 手动输入 URL"
        echo "===================================="
        echo -n "请选择 [0-$i]: "
        read -r choice
        case "$choice" in
            0) return ;;
            "$i")
                echo -n "  输入 zip 下载 URL: "
                read -r manual_url
                echo -n "  输入预期 sha256 (可留空跳过校验): "
                read -r manual_sha
                if [ -z "$manual_url" ]; then
                    echo "  无效 URL"
                    sleep 1
                    continue
                fi
                fetch_commercial "自定义" "$manual_url" "$manual_sha"
                ;;
            *)
                if ! [[ "$choice" =~ ^[0-9]+$ ]]; then
                    echo "  无效选项"
                    sleep 1
                    continue
                fi
                local idx=$((choice))
                local entry="${COMMERCIAL_DOWNLOADS[$((idx-1))]:-}"
                if [ -z "$entry" ]; then
                    echo "  无效选项"
                    sleep 1
                    continue
                fi
                local desc url sha
                IFS='|' read -r desc url sha <<< "$entry"
                fetch_commercial "$desc" "$url" "$sha"
                ;;
        esac
        echo ""
        read -p "按 Enter 返回..."
    done
}

show_menu() {
    clear
    echo "===================================="
    echo "     Naiz 环境配置"
    echo "===================================="
    echo " 1) 环境检测"
    echo " 2) 环境安装"
    echo " 3) 符号封装/拆分审计"
    echo " 4) 全项目规则审计 (fullaudit)"
    echo " 0) 退出"
    echo "===================================="
    echo -n "请选择 [0-4]: "
}

show_env_menu() {
    clear
    echo "===================================="
    echo "     环境安装"
    echo "===================================="
    echo " 1) Python 依赖安装"
    echo " 2) 系统工具链 (deps + gcc-ia16)"
    echo " 3) NP2kai 模拟器 (wxWidgets/GTK3) 【主模拟器】"
    echo " 4) 备用模拟器 (RetroArch + libretro) 【备用】"
    echo " 5) 安装 Open Watcom 工具链"
    echo " 6) 安装 DJGPP 工具链 【备选】"
    echo " 7) 商用资源下载"
    echo " 8) Git 仓库来源设置 (GitHub/国内镜像)"
    echo " 0) 返回上级"
    echo "===================================="
    echo -n "请选择 [0-8]: "
}

env_menu() {
    while true; do
        show_env_menu
        read -r choice
        case "$choice" in
            1) run_env_cmd pip-install ;;
            2) run_env_cmd system-tools ;;
            3) run_env_cmd np2kai ;;
            4) run_env_cmd backup-emu ;;
            5) run_env_cmd install-watcom ;;
            6) run_env_cmd install-djgpp ;;
            7) commercial_menu ;;
            8) run_env_cmd mirror ;;
            0) return ;;
            *) echo "无效选项，请重新选择。"; sleep 1 ;;
        esac
        echo ""
        read -p "按 Enter 返回..."
    done
}

CMD="${1:-}"
case "$CMD" in
    check)      exec "$VENV_PYTHON" -m tools.env_setup.install_env check ;;
    pip)        exec "$VENV_PYTHON" -m tools.env_setup.install_env pip-install ;;
    deps)       exec "$VENV_PYTHON" -m tools.env_setup.install_env system-tools ;;
    np2kai)     exec "$VENV_PYTHON" -m tools.env_setup.install_env np2kai ;;
    retroarch)  exec "$VENV_PYTHON" -m tools.env_setup.install_env backup-emu ;;
    watcom)     exec "$VENV_PYTHON" -m tools.env_setup.install_env install-watcom ;;
    djgpp)      exec "$VENV_PYTHON" -m tools.env_setup.install_env install-djgpp ;;
    mirror)     exec "$VENV_PYTHON" -m tools.env_setup.install_env mirror ;;  # 直接进入 Git 仓库来源设置
    commercial) commercial_menu ;;
    audit)      run_audit ;;
    fullaudit)  shift; run_fullaudit "$@" ;;  # 支持 fullaudit --no-make
    "")
        while true; do
            show_menu
            read -r choice
            case "$choice" in
                1) run_env_cmd check ;;
                2) env_menu ;;
                3) run_audit ;;
                4) run_fullaudit ;;
                0) echo "再见！"; exit 0 ;;
                *) echo "无效选项，请重新选择。"; sleep 1 ;;
            esac
            echo ""
            read -p "按 Enter 返回..."
        done
        ;;
    *)  echo "用法: start.sh {check|pip|deps|np2kai|retroarch|watcom|djgpp|mirror|commercial|audit|fullaudit|fullaudit --no-make}"
        echo "无参数: 交互式配置菜单"
        exit 1
        ;;
esac
