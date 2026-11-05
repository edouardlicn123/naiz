#!/usr/bin/env python3
"""batch_read.py — Batch parallel file slices (B94 §3.1, AGENTS.md §15).

Usage (required for future agents):
    python -m tools.diag.batch_read file1:5:20 file2:80:10 file3:1:15

Reads multiple file slices in ONE invocation (one round-trip),
replacing 3 serial read calls with 1.
"""
import argparse, sys
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", metavar="file:offset:limit")
    args = ap.parse_args()
    for spec in args.files:
        parts = spec.split(":")
        p = Path(parts[0])
        off = int(parts[1]) if len(parts) > 1 else 1
        lim = int(parts[2]) if len(parts) > 2 else 15
        lines = p.read_text(encoding="utf-8").splitlines()
        print(f"=== {p.name}:{off}:{off+lim-1} ===")
        for i in range(off-1, min(off+lim-1, len(lines))):
            print(f"{i+1}: {lines[i]}")

if __name__ == "__main__":
    main()
