#!/usr/bin/env python3
"""read_slice.py — 小片段读取（B94 §3.3，devdoc 202）。

用法：
    python -m tools.diag.read_slice <path> [line_or_offset] [limit]
    python -m tools.diag.read_slice <path> --symbol <函数名>
    python -m tools.diag.read_slice <path> --section "## 三"

--symbol 按函数定义边界切片，--section 按文档小节切片，
两者都不需要手算 offset/limit，也不受 50 行整读守卫限制。
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

MAX_LINES_DEFAULT = 50   # 整读守卫：超过即拒绝
MAX_SLICE = 150          # symbol/section 单次输出上限


def emit(lines, start, end, p, tag):
    start = max(1, start)
    end = min(len(lines), end)
    for i in range(start - 1, end):
        print(f"{i+1}: {lines[i]}")
    print(f"# -- {tag} {start}:{end} of {len(lines)} (file: {p.name})",
          file=sys.stderr)


def find_symbol(lines, name):
    """返回 (start, end)，1-based；找不到返回 None。"""
    rx = re.compile(r"^\s*[A-Za-z_].*\b" + re.escape(name) + r"\s*\(")
    for i, line in enumerate(lines):
        if not rx.match(line):
            continue
        indent = len(line) - len(line.lstrip())
        end = min(len(lines), i + MAX_SLICE)
        for j in range(i + 1, end):
            stripped = lines[j].lstrip()
            if stripped.startswith("}") and (len(lines[j]) - len(stripped)) <= indent:
                return i + 1, j + 1
        return i + 1, end
    return None


def find_section(lines, prefix):
    """返回 (start, end)，1-based；找不到返回 None。"""
    level = len(prefix) - len(prefix.lstrip("#"))
    ordered = [ln for ln in ["#" * n for n in range(1, 7)]
               if ln == "#" * level]
    head = ordered[0] + " " if ordered else prefix
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            end = min(len(lines), i + MAX_SLICE)
            for j in range(i + 1, end):
                m = re.match(r"^(#+) ", lines[j])
                if m and len(m.group(1)) <= level:
                    return i + 1, j
            return i + 1, end
    # 前缀匹配失败时退化为裸标题（去掉前导 '#'）
    for i, line in enumerate(lines):
        if line.lstrip().startswith(head):
            return find_section(lines, line[:len(head)])
    return None


def main():
    ap = argparse.ArgumentParser(description="Small, targeted file slices (B94).")
    ap.add_argument("path", help="File path")
    ap.add_argument("--offset", type=int, default=1, help="1-based start line")
    ap.add_argument("--limit", type=int, default=30, help="Lines to print")
    ap.add_argument("--symbol", metavar="NAME",
                    help="slice by C function name (definition to closing brace)")
    ap.add_argument("--section", metavar="PREFIX",
                    help='slice by markdown heading, e.g. "## 三"')
    ap.add_argument("--full", action="store_true", help="Override guard (discouraged)")
    args = ap.parse_args()

    p = Path(args.path)
    if not p.exists():
        print(f"[read_slice] not found: {p}", file=sys.stderr)
        return 2

    lines = p.read_text(encoding="utf-8").splitlines()

    if args.symbol:
        span = find_symbol(lines, args.symbol)
        if span is None:
            print(f"[read_slice] symbol not found: {args.symbol}", file=sys.stderr)
            return 1
        emit(lines, span[0], span[1], p, "symbol")
        return 0

    if args.section:
        span = find_section(lines, args.section)
        if span is None:
            print(f"[read_slice] section not found: {args.section}", file=sys.stderr)
            return 1
        emit(lines, span[0], span[1], p, "section")
        return 0

    if len(lines) > MAX_LINES_DEFAULT and not args.full:
        sys.stderr.write(
            f"[read_slice BLOCKED] {p.name}: {len(lines)} lines (> {MAX_LINES_DEFAULT}).\n"
            f"Use --symbol NAME, --section PREFIX, or --offset=X --limit=15\n"
            f"Reference: AGENTS.md §十五 rule 3, docs/B94 §3.3\n"
        )
        return 2

    emit(lines, args.offset, args.offset + args.limit - 1, p, "slice")
    return 0


if __name__ == "__main__":
    sys.exit(main())
