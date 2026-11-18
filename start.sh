#!/bin/bash
# Naiz development environment setup — Python backend (tools/naiz_cli/start.py)
# Usage:
#   start.sh                 Interactive setup menu
#   start.sh check           Environment check
#   start.sh pip             Install Python dependencies
#   start.sh deps            Install system toolchain
#   start.sh np2kai          Build and install NP2kai
#   start.sh watcom          Install Open Watcom
#   start.sh mirror          Git repository source (GitHub / domestic mirror)
#   start.sh commercial      Commercial assets download (tools_commercial/)
#   start.sh openpack        Open-source assets download (tools_open/)
#   start.sh audit           Symbol encapsulation/split audit log (logs/)
#   start.sh fullaudit       Full project rule audit
#   start.sh lang            Set UI language (eng|chi|jpn|kor)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$ROOT/tools${PYTHONPATH:+:$PYTHONPATH}"

# Auto-create venv on first run (mirrors old start.sh behavior)
if [ ! -d "$HOME/venv/bin" ] || [ ! -f "$HOME/venv/bin/pip" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$HOME/venv" || { echo "Failed to create venv"; exit 1; }
    "$HOME/venv/bin/pip" install -r "$ROOT/tools/env_setup/requirements.txt" || true
fi

exec "$HOME/venv/bin/python3" -m tools.naiz_cli start "$@"
