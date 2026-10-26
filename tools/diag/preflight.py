#!/usr/bin/env python3
"""preflight.py — Batch verification script (B94 §4, AGENTS.md §十五 rule 2).

Usage for future agents:
    python -m tools.diag.preflight --plan plan.txt

Where plan.txt contains one check per line (compact format), e.g.:
    REF:hal_irq.c:71:258
    REF:audio.c:737:[AP]
    FILE:core/plat/hal.h:exists
    NOERR:core/*.err
    PYTEST:test_bgm_timer_units

This replaces serial grep/read loops with a single round-trip,
cutting R (round-trips) by ~30-50% per verification phase.
Reference: docs/B94 §4, AGENTS.md §十五 rule 2.
"""
from __future__ import annotations
import argparse, sys, re, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REF_RE = re.compile(r"([a-z_]+\.(?:c|h|py))[:：](\d+)")


def check_ref(stem: str, lineno: int, expected_symbol: str | None = None):
    """Resolve a file:line reference (used by future agents per B94)."""
    index = {
        "audio.c": ROOT / "core/engine/audio.c",
        "audio.h": ROOT / "core/engine/audio.h",
        "hal_irq.c": ROOT / "core/plat/hal_irq.c",
        "hal.h": ROOT / "core/plat/hal.h",
        "vclock.c": ROOT / "core/lib/vclock.c",
        "hal_audio.c": ROOT / "core/plat/hal_audio.c",
        "frame.c": ROOT / "core/engine/frame.c",
        "test_bgm_timer_units.py": ROOT / "tools/tests/test_bgm_timer_units.py",
    }
    p = index.get(stem, ROOT / stem)
    if not p.exists():
        return False, f"MISSING {stem}"  # Changed: was f"MISSING {stem}:{lineno}"
    lines = p.read_text(encoding="utf-8").splitlines()
    if lineno < 1 or lineno > len(lines):
        return False, f"OOB {stem}:{lineno} (max {len(lines)})"  # Changed
    text = lines[lineno - 1].strip()
    if not text:
        return False, f"BLANK {stem}:{lineno}"  # Changed
    if expected_symbol and expected_symbol not in text:
        return False, f"MISMATCH {stem}:{lineno} expected {expected_symbol!r}, got: {text!r}"
    return True, f"OK {stem}:{lineno} -> {text[:60]}"


def run(plan_path: str) -> int:
    results = []
    ok = 0
    fail = 0
    with open(plan_path) as f:  # Added: was open(plan_path, encoding="utf-8") to match original
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Format: TYPE:arg:arg... (compact, one line per check)
            parts = line.split(":")
            cmd = parts[0]
            if cmd == "REF" and len(parts) >= 2:
                # REF:file:line[:expected_symbol]
                stem = parts[1]
                lineno = int(parts[2])
                symbol = parts[3] if len(parts) > 3 else None
                good, msg = check_ref(stem, lineno, symbol)
            elif cmd == "FILE" and len(parts) >= 2:
                # FILE:path:exists|missing|nonempty
                p = ROOT / parts[1]
                state = parts[2] if len(parts) > 2 else "exists"
                if state == "exists":
                    good = p.exists(); msg = f"{('OK' if good else 'FAIL')} {p}"  # Changed for consistency
                elif state == "nonempty":
                    good = p.exists() and p.stat().st_size > 0; msg = f"{('OK' if good else 'FAIL')} {p} (nonempty)"
                else:
                    good = not p.exists(); msg = f"{('OK' if good else 'FAIL')} {p} (missing={good})"
            elif cmd == "PYTEST" and len(parts) >= 2:
                # PYTEST:file -> run pytest -q -k file, check 0 failed
                tgt = parts[1]
                try:
                    out = subprocess.run(
                        [sys.executable, "-m", "pytest", f"tools/tests/{tgt}.py", "-q", "-p", "no:cacheprovider"],
                        capture_output=True, text=True, timeout=120
                    )
                    good = out.returncode in (0, 1, 5) and "failed" not in out.stdout  # 1=tests failed
                    # Actually check explicitly: use stdout parsing
                    stdout_text = out.stdout + out.stderr  # Added: combined output for check
                    failed_count = stdout_text.count("FAILED")  # Added: count failures explicitly
                    # More robust: parse the last line for "X failed"
                    last_lines = stdout_text.strip().split("\n")
                    failed_str = None  # Added: initialize
                    for ln in reversed(last_lines):
                        if "failed" in ln and "passed" in ln:  # Added: check both keywords
                            # Format like "3 failed, 847 passed, 2 skipped"
                            failed_str = ln
                            break
                    if failed_str is not None:
                        # Extract number before "failed"
                        import re  # Added: import for parsing
                        m = re.search(r"(\d+) failed", failed_str)
                        fail_num = int(m.group(1)) if m else 0
                    else:
                        fail_num = stdout_text.count("FAILED")  # Fallback
                    good = fail_num == 0  # Strict: any test failure means preflight fails for that target
                    msg = f"PYTEST {tgt}: {fail_num} failed (exit={out.returncode})"
                except Exception as e:
                    good = False; msg = f"PYTEST {tgt}: EXCEPTION {e}"
            elif cmd == "MAKE" and len(parts) == 1:
                # MAKE -> check make -C core and .err empty
                out = subprocess.run(["make", "-C", "core"], capture_output=True, text=True, timeout=120)
                err_files = list((ROOT / "core").glob("*.err"))  # Changed: full path for accuracy
                err_nonempty = [e.name for e in err_files if e.stat().st_size > 0]  # Added: filter non-empty
                make_ok = out.returncode == 0
                no_err = len(err_nonempty) == 0  # Added: check non-empty errors
                good = make_ok and no_err  # Changed: combine conditions
                msg = f"MAKE exit={out.returncode} errs={len(err_nonempty)} ({','.join(err_nonempty) if err_nonempty else 'clean'})"
            else:
                good = False; msg = f"UNKNOWN cmd {cmd}"
            status = "PASS" if good else "FAIL"
            results.append((status, msg))
            if good:
                ok += 1
            else:
                fail += 1
            print(f"[{status}] {msg}")
    # Summary
    total = ok + fail
    print(f"\n# preflight summary: {ok}/{total} PASS, {fail}/{total} FAIL (plan: {plan_path})")
    # Save compact log for future agents (B94 audit trail)
    log_path = ROOT / "logs" / f"preflight_{time.strftime('%Y%m%d_%H%M%S')}.log"
    log_path.parent.mkdir(exist_ok=True)
    with open(log_path, "w") as f:
        f.write(f"plan={plan_path}\nok={ok}\nfail={fail}\n")
        for s, m in results:
            f.write(f"{s}:{m}\n")
    print(f"# saved: {log_path}")
    return 1 if fail > 0 else 0


def main():
    ap = argparse.ArgumentParser(description="Batch preflight (B94 §4, AGENTS.md §15).")
    ap.add_argument("--plan", required=True, help="Plan file (one check per line)")
    args = ap.parse_args()
    sys.exit(run(args.plan))


if __name__ == "__main__":
    main()
