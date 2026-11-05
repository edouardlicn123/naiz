#!/usr/bin/env python3
"""batch_edit.py — Combine multiple edits into one file pass (B94 §3.4).

Usage (required):
    echo "old_text|new_text|core/plat/hal_irq.c" | python -m tools.diag.batch_edit

Reads stdin lines of format: OLD|NEW|FILE, applies sequentially.
This turns N separate edit tool calls into 1 round-trip.
"""
import argparse, sys
from pathlib import Path

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        old, new, file_path = line.split("|")
        p = Path(file_path)
        content = p.read_text(encoding="utf-8")
        content = content.replace(old, new, 1)
        p.write_text(content, encoding="utf-8")
        print(f"EDIT_OK {file_path}: replaced {len(old)} chars")

if __name__ == "__main__":
    main()
