#!/bin/bash
# Naiz game workflow tool — Python backend (tools/naiz_cli/makegame.py)
# Usage:
#   makegame.sh makegame <game>  Build project data and make HDI (build + make combined)
#   makegame.sh make <game>      Make HDI
#   makegame.sh test <game>      Launch NP2kai test [--serial] [--porttest] [--auto]
#   makegame.sh audio            Emulator audio latency (BGM vibrato/buzz, global)
#   makegame.sh build <proj>     Build project data
#   makegame.sh i18n-gen <game>  Generate translation templates
#   makegame.sh pack             View/switch pack mode
#   makegame.sh                  Interactive game workflow
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

exec "$HOME/venv/bin/python3" -m tools.naiz_cli makegame "$@"
