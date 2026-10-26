#!/usr/bin/env python3
"""read_slice.py — Enforce offset/limit file reads (B94 §3.3).

Usage (must be used by future agents per AGENTS.md §十五):
    python -m tools.diag.read_slice <path> [line_or_offset] [limit]

Rejects reading a file > 50 lines at once; prints only the requested slice.
This prevents dumping a 270-line hal_irq.c (or 790-line audio.c) into the
context just to check 1-3 lines -- the dominant token waste per B94 §2.
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

MAX_LINES_DEFAULT = 50  # hard guard: no full-file read without explicit --full


def read_slice(path_str: str, start: int = 1, limit: int = 30) -> None:
    p = Path(path_str)
    if not p.exists():
        raise FileNotFoundError(p)
    lines = p.read_text(encoding="utf-8").splitlines()
    if len(lines) > MAX_LINES_DEFAULT and limit is None:
        # This is the guard: if no explicit slice requested and file is large,
        # we print a warning and only show the first line with direction.
        print(f"[BLOCKED] {p}: {len(lines)} lines (> {MAX_LINES_DEFAULT}). "
              f"Use offset/limit (e.g. offset=47 limit=15) instead of full read.",
              file=sys.stderr)
        # Print a minimal header so agent still has orientation
        for i in range(min(3, len(lines))):
            print(f"{i+1}: {lines[i]}")
        print(f"... ({len(lines)-3} more lines; use --offset/--limit)")
        sys.exit(1)
    start = max(1, start)
    end = min(len(lines), start + limit - 1)
    for i in range(start - 1, end):
        print(f"{i+1}: {lines[i]}")
    print(f"# -- slice {start}:{end} of {len(lines)} (file: {p.name})", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="Enforce small file slices (B94).")
    ap.add_argument("path", help="File path")
    ap.add_argument("--offset", type=int, default=1, help="1-based start line")
    ap.add_argument("--limit", type=int, default=30, help="Lines to print")
    ap.add_argument("--full", action="store_true", help="Override guard (discouraged)")
    args = ap.parse_args()
    p = Path(args.path)
    lines = p.read_text(encoding="utf-8").splitlines()
    if len(lines) > MAX_LINES_DEFAULT and not args.full:
        # Block full-file read with clear message for future agents
        sys.stderr.write(
            f"[read_slice BLOCKED] {p.name}: {len(lines)} lines (> {MAX_LINES_DEFAULT}).\n"
            f"Future agents: use grep -n first, then 'python -m tools.diag.read_slice {args.path} --offset=X --limit=15'\n"
            f"Reference: AGENTS.md §十五 rule 3, docs/B94 §3.3\n"
        )
        sys.exit(2)
    read_slice(args.path, args.offset, args.limit)


if __name__ == "__main__":
    main()
