"""Hygiene guards for AGENTS.md and CHANGELOG.md.

The project rule (AGENTS.md section 13, "change-update protocol") states that
CHANGELOG.md is the single carrier of development history and that AGENTS.md
must hold rules plus current state only.  The rule was repeatedly violated:
the "latest entry" line in the AGENTS.md header grew to 53029 characters
because every round appended its whole summary to that line, while
CHANGELOG.md lost entries (c21 and c77 had index links but no body).

These tests keep both files in shape:

* the AGENTS.md header line stays a short pointer, not a history dump;
* no historical entry body lives in AGENTS.md;
* CHANGELOG.md anchors are contiguous and every index link resolves.
"""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_MD = ROOT / "AGENTS.md"
CHANGELOG_MD = ROOT / "CHANGELOG.md"

LATEST_LINE_PREFIX = "> **最新条目**"
MAX_LATEST_LINE_CHARS = 2000
MAX_HISTORY_REFS = 3
ANCHOR_RE = re.compile(r'^<a id="c(\d+)"\s*/?>', re.M)
INDEX_LINK_RE = re.compile(r"\]\(#c(\d+)\)")
HISTORY_REF_RE = re.compile(r"`c\d+`")
CARRIED_HISTORY_RE = re.compile(r"前序\s*`c\d+`")


def _read(path: Path) -> str:
    with path.open(encoding="utf-8") as fh:
        return fh.read()


def _latest_line_index(lines: list[str]) -> int:
    for idx, line in enumerate(lines):
        if line.startswith(LATEST_LINE_PREFIX):
            return idx
    raise AssertionError("AGENTS.md header line not found: " + LATEST_LINE_PREFIX)


def test_latest_entry_line_stays_a_pointer():
    """The header line is a pointer, not a per-round history dump."""
    lines = _read(AGENTS_MD).split("\n")
    idx = _latest_line_index(lines)
    assert len(lines[idx]) <= MAX_LATEST_LINE_CHARS, (
        "AGENTS.md latest-entry line is %d chars (limit %d): "
        "history belongs in CHANGELOG.md, keep this a pointer"
        % (len(lines[idx]), MAX_LATEST_LINE_CHARS)
    )


def test_no_history_entries_in_agents_md_body():
    """No per-round summary may be carried into the AGENTS.md body."""
    lines = _read(AGENTS_MD).split("\n")
    idx = _latest_line_index(lines)
    body = "\n".join(lines[idx + 1:])
    hit = CARRIED_HISTORY_RE.search(body)
    assert hit is None, (
        "AGENTS.md body carries a historical entry summary (%s); "
        "move it to CHANGELOG.md" % hit.group(0)
    )


def test_agents_md_keeps_few_history_refs():
    """At most a couple of pointers to history entries may stay in AGENTS.md."""
    refs = HISTORY_REF_RE.findall(_read(AGENTS_MD))
    assert len(refs) <= MAX_HISTORY_REFS, (
        "AGENTS.md references %d history entries (%s); limit is %d"
        % (len(refs), ", ".join(sorted(set(refs))), MAX_HISTORY_REFS)
    )


def test_changelog_anchors_are_contiguous():
    """CHANGELOG.md anchors must run 1..N without gaps."""
    anchors = sorted(int(x) for x in ANCHOR_RE.findall(_read(CHANGELOG_MD)))
    assert anchors, "no <a id=\"cN\"> anchors found in CHANGELOG.md"
    expected = list(range(1, anchors[-1] + 1))
    missing = [n for n in expected if n not in anchors]
    assert not missing, (
        "CHANGELOG.md is missing anchors: %s (anchor numbers must be "
        "contiguous; add the entry body before bumping to the next number)"
        % ", ".join("c%d" % n for n in missing)
    )


def test_changelog_index_links_resolve():
    """Every version-index link must point at an existing anchor."""
    text = _read(CHANGELOG_MD)
    anchors = set(ANCHOR_RE.findall(text))
    dangling = sorted({link for link in INDEX_LINK_RE.findall(text) if link not in anchors})
    assert not dangling, (
        "CHANGELOG.md index links point at missing anchors: %s" % ", ".join(dangling)
    )


def test_changelog_entries_have_bodies():
    """Each anchored entry must carry a body, unless it is flagged as lost."""
    text = _read(CHANGELOG_MD)
    anchors = [(m.start(), int(m.group(1))) for m in ANCHOR_RE.finditer(text)]
    empty = []
    for pos, (start, num) in enumerate(anchors):
        end = anchors[pos + 1][0] if pos + 1 < len(anchors) else len(text)
        block = text[start:end]
        if "正文缺失" in block:
            continue
        body = [ln for ln in block.split("\n")[1:] if ln.strip() and not ln.startswith("#")]
        if not body:
            empty.append("c%d" % num)
    assert not empty, (
        "CHANGELOG.md entries without a body: %s (either write the entry or "
        "mark it as 正文缺失)" % ", ".join(empty)
    )
