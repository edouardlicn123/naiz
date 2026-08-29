#!/bin/bash
# detect_watcom.sh — Locate Open Watcom v2 installation
#
# Usage (sourced):  source detect_watcom.sh  → sets $WATCOM, adds binl*/binl to $PATH
# Usage (subshell): WATCOM=$(./detect_watcom.sh) → prints path only
#
# Search order:
#   1. $WATCOM environment variable (already set)
#   2. ~/open-watcom-v2/rel  (default dev location)
#   3. /opt/watcom           (system install)
#   4. /usr                  (binl64/wcl386 on PATH)
# Order matches core/Makefile's `WATCOM ?=` fallback.

_dw_found=""
_dw_paths=()
while IFS= read -r -d '' _p; do _dw_paths+=("$_p"); done < <(printf '%s\0' "${WATCOM:-}" "$HOME/open-watcom-v2/rel" "/opt/watcom" "/usr")

for _p in "${_dw_paths[@]}"; do
    if [ -d "$_p/binl64" ] || [ -d "$_p/binl" ]; then
        _dw_found="$_p"
        break
    fi
done

if [ -z "$_dw_found" ]; then
    echo "ERROR: Open Watcom not found. Set \$WATCOM or install to ~/open-watcom-v2/rel" >&2
    exit 1
fi

# Subshell mode: print path only
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    echo "$_dw_found"
    exit 0
fi

# Source mode: set WATCOM and update PATH
export WATCOM="$_dw_found"
if [ -d "$WATCOM/binl64" ]; then
    export PATH="$WATCOM/binl64:$PATH"
elif [ -d "$WATCOM/binl" ]; then
    export PATH="$WATCOM/binl:$PATH"
fi
