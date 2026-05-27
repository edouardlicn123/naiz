#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$ROOT/tools/env_setup/venv"

# Ensure venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo "首次运行，创建 Python 虚拟环境..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install -r "$ROOT/tools/env_setup/requirements.txt"
fi

PYTHON="$VENV_DIR/bin/python3"
SCRIPT="$ROOT/tools/env_setup/install_env.py"

# Usage: test_hdi.sh [<hdi_name>] [ia32|i286]
#   <hdi_name>  : HDI 文件名 (默认交互选择)
#   ia32|i286   : 模拟器版本 (默认 ia32; i286 [DEPRECATED])
ARGS=()
if [ $# -ge 1 ]; then
    case "$1" in
        -h|--help)
            echo "用法: $0 [<hdi_name>] [ia32|i286]"
            echo "  <hdi_name>  : HDI 文件名 (如 demo-A1，默认交互选择)"
            echo "  ia32|i286   : 模拟器版本 (默认 ia32; i286 [DEPRECATED])"
            exit 0
            ;;
        ia32|i286)
            ARGS+=("--emulator" "$1")
            ;;
        *)
            ARGS+=("--hdi" "$1")
            ;;
    esac
fi
if [ $# -ge 2 ]; then
    ARGS+=("--emulator" "$2")
fi

exec "$PYTHON" "$SCRIPT" test-hdi "${ARGS[@]}"
