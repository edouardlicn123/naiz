"""Runtime language table — single source of truth for the language list
(codes + display names) shared by the engine and the toolchain.

The engine owns the table in C (core/engine/settings_menu.c: LANG_CODES /
LANG_NAMES / N_LANGS).  This module mirrors it for the Python tools so
code-gen (i18n_gen, gen_cjk_font) and runtime stay in sync;
tools/tests/test_langdefs_sync.py cross-checks both against the C table
and fails the build if they drift.
"""
from __future__ import annotations

LANG_CODES = ["eng", "jpn", "chi", "cht", "kor", "fre", "ger", "ita", "spa", "por"]
LANG_NAMES = [
    "English", "Japanese", "Chinese (SC)", "Chinese (TC)", "Korean",
    "French", "German", "Italian", "Spanish", "Portuguese",
]
N_LANGS = len(LANG_CODES)

# Code lookups / families (derived — do not hand-add entries here).
LANG_CODE_SET = frozenset(LANG_CODES)
CJK_FAMILY = frozenset({"jpn", "chi", "cht", "kor"})
LATIN_FAMILY = frozenset({"fre", "ger", "ita", "spa", "por"})


def _raise_unless_consistent() -> None:
    if len(LANG_NAMES) != N_LANGS:
        raise RuntimeError(
            f"langdefs: LANG_NAMES length {len(LANG_NAMES)} != LANG_CODES length {N_LANGS}")
    overlap = CJK_FAMILY | LATIN_FAMILY
    if not overlap.isdisjoint(CJK_FAMILY & LATIN_FAMILY):
        raise RuntimeError("langdefs: CJK_FAMILY and LATIN_FAMILY overlap")
    if not overlap.issubset(LANG_CODE_SET):
        raise RuntimeError("langdefs: family contains a code not in LANG_CODES")


_raise_unless_consistent()