#!/bin/bash
set -euo pipefail
# Naiz engine build — auto-sets Open Watcom environment
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/detect_watcom.sh"
export INCLUDE="$WATCOM/h"
make -C "$SCRIPT_DIR" "$@"
