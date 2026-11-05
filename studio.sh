#!/bin/bash
# Naiz 剧本工坊 — 网页版 NB 剧本 IDE 启动入口
# 用法:
#   ./studio.sh               # 默认端口 7130（ナ=7・イ=1・ズ=3，ナイズ数字谐音）
#   ./studio.sh --port 9000   # 指定端口
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "$ROOT/core/engine/main.c" ]; then
    echo "错误: 请在 naiz 项目根目录下运行 ./studio.sh（找不到 core/engine/main.c）"
    exit 1
fi

source "$ROOT/tools/env_setup/ensure_venv.sh"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "警告: 未找到虚拟环境 Python，回退到系统 python3"
    VENV_PYTHON=python3
fi

exec "$VENV_PYTHON" "$ROOT/studio/server.py" "$@"
