"""sync_line_refs.py — re-anchor LINE_REF_WHITELIST after source drift.

test_devdoc_refs.py pins devdoc line citations as (stem, lineno) -> symbol.
Any edit that inserts lines above a cited symbol breaks the guard even though
the devdoc still points at the right *statement*; fixing it by hand is a
grep-edit-retest loop.  This tool does the mechanical part:

  for each ("file.c", N): "symbol" entry in LINE_REF_WHITELIST:
      - if source[N] already contains the symbol: keep
      - else find every line containing the symbol, pick the one nearest N,
        and rewrite the entry in place

KNOWN_GOOD_REFS / STALE_QUOTED_REFS / SUPERSEDED_* carry no symbol (or are
deliberately wrong) and are never touched.

Usage:
  python3 -m tools.naiz_docs.sync_line_refs          # fix in place
  python3 -m tools.naiz_docs.sync_line_refs --check  # report drift, exit 1
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TEST_FILE = ROOT / "tools" / "tests" / "test_devdoc_refs.py"

ENTRY_RE = re.compile(
    r'^(?P<indent>\s*)\("(?P<stem>[a-z_]+\.(?:c|h|py))",\s*(?P<lineno>\d+)\)'
    r':\s*"(?P<symbol>[^"]+)"(?P<tail>,?\s*(?:#.*)?)$'
)

# stems that appear in LINE_REF_WHITELIST; mirror of SOURCE_INDEX there.
# Kept as a glob fallback so new stems resolve without editing this tool.
SOURCE_GLOBS = ("core/engine", "core/plat", "core/lib", "tools/naiz_build",
                "tools/tests")


def _find_source(stem):
    for d in SOURCE_GLOBS:
        p = ROOT / d / stem
        if p.is_file():
            return p
    return None


def _nearest_symbol_line(lines, symbol, old_lineno):
    """1-based line numbers of every line containing symbol; nearest to old."""
    hits = [i + 1 for i, text in enumerate(lines) if symbol in text]
    if not hits:
        return None
    return min(hits, key=lambda n: (abs(n - old_lineno), n))


def main(argv):
    check_only = "--check" in argv
    test_lines = TEST_FILE.read_text(encoding="utf-8").split("\n")
    src_cache = {}
    drifted = []
    ambiguous = []

    for idx, raw in enumerate(test_lines):
        m = ENTRY_RE.match(raw)
        if not m:
            continue
        stem, lineno, symbol = m.group("stem"), int(m.group("lineno")), m.group("symbol")
        if stem not in src_cache:
            path = _find_source(stem)
            src_cache[stem] = path and path.read_text(encoding="utf-8").split("\n")
        lines = src_cache[stem]
        if lines is None:
            print(f"  SKIP {stem}: source not found", file=sys.stderr)
            continue
        if lineno <= len(lines) and symbol in lines[lineno - 1]:
            continue  # still accurate
        new_lineno = _nearest_symbol_line(lines, symbol, lineno)
        if new_lineno is None:
            print(f"  FAIL {stem}:{lineno} — symbol {symbol!r} gone from {stem}",
                  file=sys.stderr)
            ambiguous.append((stem, lineno, symbol))
            continue
        drifted.append((stem, lineno, new_lineno, symbol))
        if not check_only:
            test_lines[idx] = (
                f'{m.group("indent")}("{stem}", {new_lineno}): "{symbol}"'
                f'{m.group("tail")}'
            )

    for stem, old, new, symbol in drifted:
        print(f"  {stem}: {old} -> {new}  ({symbol})")

    if ambiguous:
        print(f"\n{len(ambiguous)} entr(ies) need manual fixing", file=sys.stderr)
        return 2
    if not drifted:
        print("LINE_REF_WHITELIST: all entries resolve, nothing to do")
        return 0
    if check_only:
        print(f"\n{len(drifted)} drifted entr(ies); run without --check to fix",
              file=sys.stderr)
        return 1
    TEST_FILE.write_text("\n".join(test_lines), encoding="utf-8")
    print(f"\n{len(drifted)} entr(ies) re-anchored in {TEST_FILE.name}; "
          f"re-run pytest to confirm")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
