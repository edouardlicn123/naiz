"""devdoc 205 §15.1: save v4 layout, three-tier read sizes, state restore.

Slot saves gained a string-variable tail in v4.  Old v2/v3 files remain
loadable through explicit shorter read sizes; losing that would make every
pre-205 save unreadable.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SAVE_H = ROOT / "core" / "engine" / "save.h"
SAVE_IO = ROOT / "core" / "engine" / "save_io.c"
SAVE_C = ROOT / "core" / "engine" / "save.c"


def _read(path):
    return path.read_text(encoding="utf-8")


def test_save_version_constants():
    src = _read(SAVE_H)
    assert re.search(r"#define\s+SAVE_VERSION\s+4\b", src), (
        "SAVE_VERSION must be 4 (string-variable tail)"
    )
    assert re.search(r"#define\s+SAVE_VERSION_MIN\s+2\b", src), (
        "SAVE_VERSION_MIN must be 2 (v2/v3 still loadable)"
    )


def test_var_strings_is_the_last_save_data_field():
    src = _read(SAVE_H)
    body = re.search(r"typedef\s+struct\s*\{(.*?)\}\s*SaveData;", src, re.S)
    assert body, "SaveData struct not found in save.h"
    without_comments = re.sub(r"/*.*?\*/", "", body.group(1), flags=re.S)
    decls = [line.strip() for line in without_comments.splitlines() if line.strip()]
    assert decls, "SaveData has no fields"
    assert "var_strings" in decls[-1], (
        "var_strings must be the last SaveData field (v4 read tail)"
    )


def test_save_read_has_three_length_tiers():
    src = _read(SAVE_IO)
    assert "if (ver < 3)" in src, "missing v2 length tier"
    assert "else if (ver < max_version)" in src, "missing v3 length tier"
    assert "read_sz = bufsz" in src, "missing current-length fallback"


def test_save_apply_restores_string_variables():
    src = _read(SAVE_C)
    assert "nb_var_set_str_state(s->var_strings)" in src, (
        "save_apply must restore the v4 string-variable tail"
    )
