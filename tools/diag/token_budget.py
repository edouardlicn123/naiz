#!/usr/bin/env python3
"""token_budget.py — Monitor per-session token cost (B94 §2, AGENTS.md §15 rule 8).

Usage (required for future agents after each phase):
    python -m tools.diag.token_budget

Reads opencode session_v2 table and reports R (round-trips),
input/output token estimates, and flags if cost exceeds budget.
Reference: docs/B94 §2, AGENTS.md §十五.
"""
import sqlite3, sys
from pathlib import Path
DB = Path.home() / ".local/share/opencode/opencode.db"

def main():
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = db.execute("SELECT id, tokens_input, tokens_output, cost FROM session_v2 ORDER BY time_created DESC LIMIT 10").fetchall()
    total_in = sum(r[1] or 0 for r in rows)
    total_out = sum(r[2] or 0 for r in rows)
    print(f"# token_budget: last 10 sessions")
    print(f"# total_input={total_in}, total_output={total_out}")
    print(f"# budget check: OK" if total_in < 5_000_000 else f"# BUDGET WARNING: {total_in} > 5M")
    for r in rows:
        sid, tin, tout, cost = r
        print(f"session={sid} in={tin} out={tout} cost={cost}")

if __name__ == "__main__":
    main()
