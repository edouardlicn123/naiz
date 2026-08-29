"""Shell-script anti-regression rules (AGENTS section 17, S1-S9)."""

import re


def _line(text, pos):
    return text.count("\n", 0, pos) + 1


def _strip_sh_comments(text):
    return "\n".join(re.sub(r"#.*$", "", ln) for ln in text.splitlines())


def _aggregate(out, text, lines, how_many=8):
    """Cap HEUR hits per rule so noisy heuristics stay readable."""
    out.extend(lines[:how_many])
    if len(lines) > how_many:
        out.append((_line(text, len(text)), f"... {len(lines)} hits total"))


# ---------------------------------------------------------------------------
# S1 unquoted variable expansions
# ---------------------------------------------------------------------------


def _s1_hits(text):
    out = []
    clean = _strip_sh_comments(text)
    for i, line in enumerate(clean.splitlines(), 1):
        # Bare $VAR or ${VAR} not already inside double quotes and not $?/$@/$-.
        for m in re.finditer(
                r'(?<!\$)(?<![\"\\\\])\$\{?[A-Za-z_][A-Za-z0-9_]*\}?', line):
            token = m.group(0)
            if token in ("$?", "$@", "$-"):
                continue
            col = m.start()
            # only report if not enclosed in double quotes before/after
            prefix = line[:col]
            if prefix.count('"') % 2 == 1:
                continue
            out.append((i, f"unquoted {token}"))
    return out


def check_s1(text, _path):
    return _s1_hits(text)[:8]


# ---------------------------------------------------------------------------
# S2 eval, S3 which, S4 readlink -- deterministic
# ---------------------------------------------------------------------------


def check_s2(text, _path):
    clean = _strip_sh_comments(text)
    return [(_line(clean, m.start()), "eval used; banned")
            for m in re.finditer(r"\beval\s", clean)]


def check_s3(text, _path):
    clean = _strip_sh_comments(text)
    return [(_line(clean, m.start()), "which used; use command -v")
            for m in re.finditer(r"\bwhich\b", clean)]


def check_s4(text, _path):
    clean = _strip_sh_comments(text)
    return [(_line(clean, m.start()), "readlink used; use cd+dirname+pwd")
            for m in re.finditer(r"\breadlink\b", clean)]


# ---------------------------------------------------------------------------
# S5 shift guarded by $#
# ---------------------------------------------------------------------------


def check_s5(text, _path):
    clean = _strip_sh_comments(text)
    out = []
    for m in re.finditer(r"^\s*(?:command\s+)?shift\b", clean, flags=re.M):
        ctx = clean[max(0, m.start() - 400):m.start()]
        if re.search(r"\[[^]]*\$#|\$\#", ctx):
            continue
        out.append((_line(clean, m.start()),
                    "shift without a nearby $# argument-count guard"))
    return out


# ---------------------------------------------------------------------------
# S6 unquoted $list in for loops
# ---------------------------------------------------------------------------


def check_s6(text, _path):
    clean = _strip_sh_comments(text)
    return [
        (_line(clean, m.start()), "for-loop over unquoted variable "
         f"'{m.group(1)}'; word-splitting - use an array or quote")
        for m in re.finditer(r"^\s*for\s+(\w+)\s+in\s+\$\{?\w+\}?", clean, re.M)
    ]


# ---------------------------------------------------------------------------
# S7 empty-string positional args (manual review hint)
# ---------------------------------------------------------------------------

MANUAL_NOTES = {
    "S7": "Optional flags must be appended via arrays (no empty positional "
          "strings). Re-check makegame.sh $SERIAL/$AUTO paths.",
}


# ---------------------------------------------------------------------------
# S8 strict-mode header
# ---------------------------------------------------------------------------


def check_s8(text, _path):
    head = _strip_sh_comments(text)[:1200]
    if not re.search(r"\bset\s+-e|\bset\s+-eu|\bset\s+-euo", head):
        return [(1, "script lacks set -e / set -euo pipefail strict mode")]
    return []


def registry():
    return {
        "S1": (check_s1, "HEUR", "unquoted variables"),
        "S2": (check_s2, "AUTO", "eval banned"),
        "S3": (check_s3, "AUTO", "which -> command -v"),
        "S4": (check_s4, "AUTO", "readlink -> cd+dirname"),
        "S5": (check_s5, "HEUR", "shift without $# guard"),
        "S6": (check_s6, "HEUR", "unquoted for-loop list"),
        "S8": (check_s8, "HEUR", "strict-mode header"),
    }