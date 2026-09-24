#!/bin/bash
# Naiz — 资产市场下载工具（market）
# 从公开 GitHub 市场仓库整包下载资源到本地落点（默认 assets_samples，gitignored）。
# 单位 = 资源包（市场仓库一个顶层目录）；不做文件级选择，显示名遵循 AGENTS §十三 规律。
#
# 用法:
#   market.sh                     交互式数字包菜单（等价 market.sh menu）
#   market.sh list                列出全部包（显示名/文件数/总大小）
#   market.sh cats                仅包显示名 + 计数
#   market.sh get <包>...         命令行整包下载（原始目录名 或 后缀种类名）
#   market.sh get-all             下载全部包
#   通用参数: --repo/--ref/--dest/--config/--dry-run（置于子命令后）
#
# 配置: 根目录 market.toml 的 [market] repo / ref / dest。

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "$ROOT/core/engine/main.c" ]; then
    echo "错误: 无法确认 Naiz 项目根目录（找不到 core/engine/main.c）"
    echo "  market.sh 路径: $0"
    echo "  解析 ROOT: $ROOT"
    echo "请确保在项目根目录下运行: bash market.sh"
    exit 1
fi
source "$ROOT/tools/env_setup/ensure_venv.sh"

if [ ! -d "$VENV_DIR" ]; then
    echo "错误: 未找到 Python 虚拟环境"
    echo "请先运行: bash start.sh pip"
    exit 1
fi

SUBCOMMAND="${1:-}"
if [ -z "$SUBCOMMAND" ]; then
    exec "$VENV_PYTHON" -m tools.naiz_market.market menu
fi
shift 2>/dev/null || true
exec "$VENV_PYTHON" -m tools.naiz_market.market "$SUBCOMMAND" "$@"