#!/bin/bash
# Naiz animation production — Python backend (tools/naiz_cli/anima.py)
# Usage:
#   anima.sh                        Interactive animation production menu
#   anima.sh init <project>         Create animation project skeleton
#   anima.sh register <project>     Register assets into project db/
#   anima.sh check <project>        Read-only reconcile asset registration
#   anima.sh mp4 <project>          Scan anim/*.mp4 and convert to .ANI
#   anima.sh build <project>/<script>  Compile a single animation script
#   anima.sh buildall [--flags]     Compile all scripts in all projects
#   anima.sh list                   List available animation scripts
#
# Note: run start.sh first to set up the environment.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$ROOT/tools${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -f "$HOME/venv/bin/python3" ]; then
    echo "Error: Python virtual environment not found at $HOME/venv" >&2
    echo "Please run first: bash start.sh pip" >&2
    exit 1
fi

exec "$HOME/venv/bin/python3" -m tools.naiz_cli anima "$@"
