"""S6: GM program -> FM family data (devdocs/124).

Guards the DATA contract between the tool cluster table (tools/naiz_audio/
gm_families.py) and the demo project's registered FM patches:

  - every GM program 0..127 maps to exactly one family (no silent gaps);
  - the project's FMP asset order (ASSETS.DB type='FMP' ORDER BY id, which
    becomes fmp_map order == AUDIO.DAT order == the engine's g_fm_patches
    table) is exactly gm_families.FAMILIES order, so fmp_gm_map indices
    line up with the engine patch table;
  - every family's .fmp source exists, compiles, and stays within the
    engine's FM_FAMILY_MAX.

The C-side family-selection logic (including the unmapped fallback) is
already proven by test_fm_seq.py::test_gm_family_selection.
"""

import glob
import os
import re
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tools'))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, 'tools', 'naiz_audio'))

from naiz_audio import fm_patch, gm_families  # noqa: E402
from naiz_lib import to_dos_name  # noqa: E402

PROJECT = os.path.join(REPO_ROOT, 'projects', 'demo-a2')
ASSETS_DB = os.path.join(PROJECT, 'ASSETS.DB')
FM_SRC_DIR = os.path.join(REPO_ROOT, 'assets', 'demo-a2', 'fm')


def _fmp_rows(db):
    return list(db.execute(
        "SELECT id, name, filename FROM img_map "
        "WHERE type='FMP' ORDER BY id"))


@pytest.fixture(scope='module')
def db():
    conn = sqlite3.connect(ASSETS_DB)
    yield conn
    conn.close()


def test_fmp_registered_exactly_the_family_set(db):
    names = [n for _id, n, _f in _fmp_rows(db)]
    expected = [n for n, _p in gm_families.FAMILIES]
    assert names == expected, (
        "FMP asset order must be exactly gm_families.FAMILIES order so "
        "family indices match the engine patch table")


def test_family_sources_compile_and_validate(db):
    import ctypes

    sys.path.insert(0, os.path.join(REPO_ROOT, 'tools', 'tests'))
    from test_fmopn import _build_fmopn

    lib, _ = _build_fmopn()
    lib.fmopn_patch_validate.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    lib.fmopn_patch_validate.restype = ctypes.c_int

    for _id, name, filename in _fmp_rows(db):
        src = os.path.join(FM_SRC_DIR, name + '.fmp')
        assert os.path.isfile(src), f"{name}.fmp source file must exist"
        blob = fm_patch.compile_source(src)
        assert len(blob) == 32
        arr = (ctypes.c_uint8 * 32).from_buffer_copy(blob)
        assert lib.fmopn_patch_validate(arr) == 0, f"{name}.fmp fails C validator"


def test_gm_map_covers_all_programs(db):
    order = [n for _id, n, _f in _fmp_rows(db)]
    gm = gm_families.build_gm_map(order)
    assert len(gm) == 128
    assert all(0 <= v < len(order) for v in gm)
    assert sorted(set(gm)) == list(range(len(order))), (
        "every family must be reachable by at least one GM program")


def test_family_count_within_engine_limit(db):
    names = [n for _id, n, _f in _fmp_rows(db)]
    assert len(names) <= 16, "FM_FAMILY_MAX in core/engine/audio.c is 16"

    with open(os.path.join(REPO_ROOT, 'core', 'engine', 'audio.c')) as f:
        src = f.read()
    m = re.search(r'#define\s+FM_FAMILY_MAX\s+(\d+)', src)
    assert m, "FM_FAMILY_MAX must exist in core/engine/audio.c"
    assert len(names) <= int(m.group(1))


def test_family_names_are_dos83_unique(db):
    names = [n for _id, n, _f in _fmp_rows(db)]
    shorts = [to_dos_name(n) for n in names]
    assert len(shorts) == len(set(shorts)), "FMP names must be DOS 8.3 unique"
    for n in names:
        assert len(n) <= 8, f"family name {n!r} exceeds 8 chars (DOS 8.3)"


def test_db_filename_matches_fm_dir(db):
    for _id, name, filename in _fmp_rows(db):
        assert filename == f"fm/{name}.fmp", (
            f"{name}: ASSETS.DB filename must be fm/{name}.fmp under assets/demo-a2/")


def test_build_gm_map_rejects_order_mismatch():
    wrong_order = [n for n, _p in gm_families.FAMILIES]
    wrong_order[0], wrong_order[-1] = wrong_order[-1], wrong_order[0]
    with pytest.raises(ValueError, match="FMP asset order"):
        gm_families.build_gm_map(wrong_order)
    with pytest.raises(ValueError, match="FMP asset order"):
        gm_families.build_gm_map([n for n, _p in gm_families.FAMILIES[:-1]])


def test_build_gm_map_detects_gap_and_duplicate(monkeypatch):
    original = list(gm_families.FAMILIES)
    order = [n for n, _p in original]
    good = dict(original)

    # gap: piano covers only 0..7 -> programs 8..127 unmapped
    patch = [(n, [] if n == 'piano' else good[n]) for n, _p in original]
    monkeypatch.setattr(gm_families, 'FAMILIES', patch)
    with pytest.raises(ValueError, match="have no family"):
        gm_families.build_gm_map(order)

    # duplicate: piano listed twice -> 0..7 mapped twice
    patch = [('piano', good['piano'])] + original
    monkeypatch.setattr(gm_families, 'FAMILIES', patch)
    with pytest.raises(ValueError, match="mapped twice"):
        gm_families.build_gm_map([n for n, _p in patch])