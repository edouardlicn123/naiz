"""Language-table sync guard between the engine and the Python toolchain.

The runtime language list has a single source of truth per side: the C table
in core/engine/settings_menu.c (LANG_CODES + LANG_NAMES + N_LANGS) and
tools/naiz_lib/langdefs.py (mirrored by i18n_gen's VALID_LANGS and
gen_cjk_font's RUNTIME_LANGS).  A new supported language must be added to
BOTH sides, or generation, font building and the runtime selector drift apart
(e.g. i18n target accepted but no font built for it).  This test parses the
C table and fails whenever the Python side stops matching it.
"""
import re

import pytest

import naiz_lib.langdefs as ld
from naiz_font.gen_cjk_font import RUNTIME_LANGS

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent.parent
SETTINGS_MENU_C = ROOT / "core" / "engine" / "settings_menu.c"


def _c_array(c_src, name):
    m = re.search(rf'static const char \*{name}\[\]\s*=\s*\{{([^}}]*)\}}', c_src, re.S)
    assert m, f"settings_menu.c: string array {name} not found"
    return re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))


def test_python_and_c_code_lists_match():
    c_src = SETTINGS_MENU_C.read_text(encoding="utf-8")
    assert ld.LANG_CODES == _c_array(c_src, "LANG_CODES")
    assert ld.LANG_NAMES == _c_array(c_src, "LANG_NAMES")
    assert ld.N_LANGS == len(ld.LANG_CODES) == len(ld.LANG_NAMES)


def test_c_code_count_constant_matches():
    c_src = SETTINGS_MENU_C.read_text(encoding="utf-8")
    m = re.search(r"#define N_LANGS\s+(\d+)", c_src)
    assert m, "settings_menu.c: N_LANGS macro not found"
    assert int(m.group(1)) == len(ld.LANG_CODES)


def test_toolchain_imports_stay_derived():
    assert list(RUNTIME_LANGS) == ld.LANG_CODES
    assert set(RUNTIME_LANGS) == ld.LANG_CODE_SET


def test_no_duplicate_codes_or_names():
    assert len(ld.LANG_CODES) == len(set(ld.LANG_CODES))
    assert len(ld.LANG_NAMES) == len(set(ld.LANG_NAMES))
    assert ld.LANG_CODE_SET.isdisjoint(set())
    families = ld.CJK_FAMILY | ld.LATIN_FAMILY
    assert families.issubset(ld.LANG_CODE_SET)
    assert ld.CJK_FAMILY.isdisjoint(ld.LATIN_FAMILY)