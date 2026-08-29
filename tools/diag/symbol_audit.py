#!/usr/bin/env python3
"""One-shot encapsulation / split audit for the core/ engine.

Scans all core/{engine,plat,lib} C sources and headers once and prints a
compact report in the AGENTS.md analysis format:

    file:line -- one-line description

Sections:
  A. static candidates -- public functions with zero external .c callers
                          (make them static; [hdr] flag = also declared in a header)
  B. dead exports      -- functions declared in a header but called from no other
                          .c file (remove the header declaration)
  C. coupling / split view -- per file: line count, public count and number of
                          external caller files (spot candidates for splitting)
  D. public symbol inventory -- every public function with defining file:line
                          (index to consult instead of re-reading sources)
  E. split candidates  -- prefix-cluster analysis: within each file group public
                          functions sharing their first two underscore words;
                          cohesive clusters >= MIN_CLUSTER_SIZE signal extractable
                          submodules (ranked by cluster mass * file lines)

Run:
    python -m tools.diag.symbol_audit            # all sections
    python -m tools.diag.symbol_audit -s A,E     # selected sections only
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[2] / "core"

# vram.c is an opt-in reference implementation excluded from the build
# (filter-out in core/Makefile); skip it to match the real linkage graph.
EXCLUDED_FILES = {CORE_DIR / "plat" / "vram.c"}

# Split-candidate heuristics. A cluster is a group of public functions in one
# file sharing their first two underscore words (e.g. hal_mouse_*, nb_set_*).
MIN_CLUSTER_SIZE = 3      # functions per cohesive cluster to report it
MAX_CLUSTERS_KEPT = 3     # top clusters printed per file
TOP_SPLIT_FILES = 10      # files listed in the ranked split summary

TYPE_WORDS = (
    r"(?:void|int|uint|unsigned|char|signed|const|BOOL|long|short|float|double|"
    r"uint8_t|uint16_t|uint32_t|int8_t|int16_t|int32_t|size_t|word|byte)"
)

# Top-level (column 0) definition: return type tokens, optional '*', name, '('.
# Negative lookahead rejects 'static' both flat and indented.
FUNC_DEF_RE = re.compile(
    r"^(?!\s*static\s)" + TYPE_WORDS + r"(?:\s+" + TYPE_WORDS + r")*\s*\*?\s*"
    r"([A-Za-z_]\w*)\s*\(",
    re.MULTILINE,
)

# Function declaration inside a header: type tokens then '('.
FUNC_DECL_RE = re.compile(
    r"\b" + TYPE_WORDS + r"(?:\s+" + TYPE_WORDS + r")*\s*\*?\s*"
    r"([A-Za-z_]\w*)\s*\("
)

# File-scope global definition: type then name, optional array/braces/init.
GLOBAL_DEF_RE = re.compile(
    r"^(?!\s*static\s)" + TYPE_WORDS + r"(?:\s+" + TYPE_WORDS + r")*\s*\*?\s*"
    r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*(?:=|;|\{)",
    re.MULTILINE,
)


def collect_sources():
    """Return {Path: text} for every built .c file in core/."""
    sources = {}
    for path in sorted(CORE_DIR.glob("*/*.c")):
        if path in EXCLUDED_FILES:
            continue
        try:
            sources[path] = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise RuntimeError(f"cannot read source {path}: {exc}") from exc
    return sources


def collect_headers():
    """Return {Path: text} for every .h file in core/."""
    headers = {}
    for path in sorted(CORE_DIR.glob("*/*.h")):
        try:
            headers[path] = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise RuntimeError(f"cannot read header {path}: {exc}") from exc
    return headers


def scan_defs(sources):
    """Return {name: (Path, lineno)} for every public function definition."""
    defs = {}
    for path, text in sources.items():
        for m in FUNC_DEF_RE.finditer(text):
            name = m.group(1)
            if name not in defs:
                lineno = text.count("\n", 0, m.start()) + 1
                defs[name] = (path, lineno)
    return defs


def scan_globals(sources):
    """Return {name: (Path, lineno)} for every public file-scope global."""
    globals_ = {}
    for path, text in sources.items():
        for m in GLOBAL_DEF_RE.finditer(text):
            name = m.group(1)
            if name not in globals_:
                lineno = text.count("\n", 0, m.start()) + 1
                globals_[name] = (path, lineno)
    return globals_


def scan_header_symbols(headers):
    """Return the set of function names declared in any core/ header."""
    declared = set()
    for text in headers.values():
        for m in FUNC_DECL_RE.finditer(text):
            declared.add(m.group(1))
    return declared


def file_lines(path, cache=None):
    """Return the number of lines in a source file (cached across sections)."""
    if cache is None:
        cache = {}
    if path in cache:
        return cache[path]
    text = path.read_text(encoding="utf-8", errors="replace")
    cache[path] = text.count("\n") + 1
    return cache[path]


def prefix_of(name):
    """First two underscore words of a function name (identity when < 2)."""
    parts = name.split("_")
    return "_".join(parts[:2]) if len(parts) >= 2 else name


def split_clusters(path, names):
    """Return {prefix: sorted name list} for cohesive clusters in a file."""
    groups = defaultdict(list)
    for name in names:
        groups[prefix_of(name)].append(name)
    return {
        prefix: sorted(cluster)
        for prefix, cluster in groups.items()
        if len(cluster) >= MIN_CLUSTER_SIZE
    }


def external_users(name, sources, own_path):
    """Return the .c files (other than own_path) whose text mentions name."""
    return [
        path for path, text in sources.items()
        if path != own_path and re.search(r"\b" + re.escape(name) + r"\b", text)
    ]


def sprint(path, lineno, desc):
    """Emit one report line in the standard file:line -- description format."""
    rel = path.relative_to(CORE_DIR.parent)
    sys.stdout.write(f"{rel}:{lineno} -- {desc}\n")


def section_a(defs, sources, declared):
    """Static candidates: public functions with zero external callers."""
    print("=== A. STATIC CANDIDATES (no external .c caller) ===")
    for name, (path, lineno) in sorted(defs.items()):
        if external_users(name, sources, path):
            continue
        flag = " [hdr]" if name in declared else ""
        sprint(path, lineno, f"{name}() public but used only here{flag}")
    print()


def section_b(defs, sources, declared):
    """Dead exports: header-declared functions with no external callers."""
    print("=== B. DEAD EXPORTS (declared in header, called from no other .c) ===")
    for name, (path, lineno) in sorted(defs.items()):
        if name in declared and not external_users(name, sources, path):
            sprint(path, lineno, f"{name}() header decl has no external callers")
    print()


def section_c(defs, sources, line_cache):
    """Coupling / split view: public count and external caller files per owner."""
    print("=== C. COUPLING / SPLIT VIEW ===")
    owner_agg = defaultdict(list)
    for name, (path, _lineno) in defs.items():
        users = external_users(name, sources, path)
        if users:
            owner_agg[path].append((name, users))

    rows = []
    for path, items in owner_agg.items():
        sizes = sorted(len(users) for _name, users in items)
        rows.append((
            path,
            len(items),
            sum(sizes),
            max(sizes) if sizes else 0,
            file_lines(path, line_cache),
            items,
        ))
    rows.sort(key=lambda r: (-r[2], str(r[0])))

    header = f"{'file':<44} {'lines':>5} {'pub':>4} {'ext-users':>9} {'max-users':>9}"
    print(header)
    print("-" * len(header))
    for path, npub, total, mx, lines, _items in rows:
        rel = str(path.relative_to(CORE_DIR.parent))
        print(f"{rel:<44} {lines:>5} {npub:>4} {total:>9} {mx:>9}")
    print()


def section_d(defs, globals_, declared):
    """Public symbol inventory grouped by defining file."""
    print("=== D. PUBLIC SYMBOL INVENTORY ===")
    by_file = defaultdict(list)
    for name, (path, lineno) in defs.items():
        by_file[path].append((lineno, name, "fn" + (" [hdr]" if name in declared else "")))
    for name, (path, lineno) in globals_.items():
        by_file[path].append((lineno, name, "gv"))
    for path in sorted(by_file):
        rel = str(path.relative_to(CORE_DIR.parent))
        print(f"# {rel}")
        for lineno, name, kind in sorted(by_file[path]):
            print(f"  {name} : {lineno} ({kind})")
    print()


def section_e(defs, sources, line_cache):
    """Split candidates: prefix clusters per file, ranked by cluster mass.

    Mass = (cluster size ** 2) * owner file lines, so dense cohesive clusters
    inside larger files rank first -- the most promising extraction targets.
    """
    print(f"=== E. SPLIT CANDIDATES (prefix clusters >= {MIN_CLUSTER_SIZE} funcs) ===")

    owner_funcs = defaultdict(list)
    for name, (path, _lineno) in defs.items():
        owner_funcs[path].append(name)

    ranked = []
    for path, names in owner_funcs.items():
        clusters = split_clusters(path, names)
        if not clusters:
            continue
        lines = file_lines(path, line_cache)
        mass = sum(len(cluster) ** 2 for cluster in clusters.values()) * lines
        ranked.append((path, lines, clusters, mass))
    ranked.sort(key=lambda r: (-r[3], str(r[0])))

    if not ranked:
        print("  (none)")
        print()
        return

    print(f"\n  Top {TOP_SPLIT_FILES} files by cluster mass (larger => better split target):")
    for path, lines, clusters, mass in ranked[:TOP_SPLIT_FILES]:
        rel = str(path.relative_to(CORE_DIR.parent))
        print(f"  {rel}  ({lines} lines, mass={mass})")
        for prefix, cluster in sorted(
                clusters.items(), key=lambda kv: -len(kv[1]))[:MAX_CLUSTERS_KEPT]:
            shown = ", ".join(f"{n}()" for n in cluster)
            print(f"    {prefix:<22} x{len(cluster):>2}: {shown}")
        print()
    print()


def main():
    parser = argparse.ArgumentParser(description="core/ encapsulation & split audit")
    parser.add_argument(
        "-s", "--sections", default="A,B,C,D,E",
        help="comma-separated sections to print (default A,B,C,D,E)",
    )
    args = parser.parse_args()

    sources = collect_sources()
    headers = collect_headers()
    defs = scan_defs(sources)
    globals_ = scan_globals(sources)
    declared = scan_header_symbols(headers)

    line_cache = {}

    print(f"scanned {len(sources)} sources, {len(headers)} headers, "
          f"{len(defs)} public funcs, {len(globals_)} file-scope globals\n")

    wanted = {chunk.strip().upper() for chunk in args.sections.split(",") if chunk.strip()}
    if "A" in wanted:
        section_a(defs, sources, declared)
    if "B" in wanted:
        section_b(defs, sources, declared)
    if "C" in wanted:
        section_c(defs, sources, line_cache)
    if "D" in wanted:
        section_d(defs, globals_, declared)
    if "E" in wanted:
        section_e(defs, sources, line_cache)


if __name__ == "__main__":
    main()