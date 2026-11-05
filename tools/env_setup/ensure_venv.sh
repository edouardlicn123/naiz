#!/bin/bash
# ensure_venv.sh — Locate / create the shared Python venv.
#
# Single source of truth for the venv path. Shared by start.sh and makegame.sh.
# Usage (sourced):  source ensure_venv.sh  → exports $VENV_DIR, ensures $VENV_PYTHON
#   After sourcing, use "$VENV_PYTHON" instead of hardcoding bin/python3.
#
# Requires $ROOT to be set to the naiz project root before sourcing.

if [ -z "${ROOT:-}" ]; then
    echo "ERROR: ensure_venv.sh requires \$ROOT to be set" >&2
    exit 1
fi

VENV_DIR="$ROOT/tools/env_setup/venv"
VENV_PYTHON="$VENV_DIR/bin/python3"

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
        "$VENV_DIR/bin/pip" install -r "$ROOT/tools/env_setup/requirements.txt" 2>&1
        echo "虚拟环境就绪"
    fi
}
