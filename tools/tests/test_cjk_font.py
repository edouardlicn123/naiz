"""Tests for the corpus-driven CJK font generator (gen_cjk_font.py).

Covers the multibyte corpus collectors, range merging, the CJKF atlas
subseter, glyph-source priority, and the output-format contract the engine
(cjk.c) depends on: ascending ranges, first-range offset == header size,
zero-filled fallback glyphs with WARN, and a valid 0-range empty file.
"""

import struct

import pytest

from naiz_font.gen_cjk_font import (
    MAX_RANGES,
    RUNTIME_LANGS,
    CJK_FAMILY,
    LATIN_FAMILY,
    _iter_multibyte_cps,
    _validate_collect_lang,
    collect_cps,
    collect_i18n_cps,
    collect_nb_cps,
    generate_cjk_file,
    lang_base_ranges,
    merge_glyph_sources,
    merge_ranges,
    subset_from_atlas,
)

REPO_ROOT = __file__.split("tools/tests")[0]
ATLAS = REPO_ROOT + "tools/naiz_font/CJK.DAT"


# ---------------------------------------------------------------- collectors


def test_iter_multibyte_cps_excludes_ascii_and_surrogates():
    text = "A\u4E00b\uFFFD\ud800\U0001F600"
    got = list(_iter_multibyte_cps(text))
    assert 0x4E00 in got
    assert 0xFFFD in got
    assert 0x1F600 in got
    assert 0x41 not in got  # 'A'
    assert 0xD800 not in got  # lone surrogate
    assert 0x61 not in got  # 'b'


def test_collect_i18n_cps_value_only(tmp_path):
    f = tmp_path / "game_ja.txt"
    f.write_text(
        "# comment\ntitle=こんにちは\nempty=\n# ORPHANED: 旧キー=\n"
        "mixed=abc日本語\n"
    )
    cps = collect_i18n_cps(str(f))
    assert 0x3053 in cps  # こ
    assert 0x65E5 in cps  # 日 (from mixed=abc日本語)
    assert 0x8A9E in cps  # 語
    assert 0x65E7 not in cps  # 旧 is on the key side of ORPHANED line
    assert all(cp >= 0x80 for cp in cps)


def test_collect_nb_cps_skips_comments(tmp_path):
    f = tmp_path / "scene.nb"
    f.write_text("# コメント行\nsay(hello){こんにちは}\nsceneconf(){本編,type}\n")
    cps = collect_nb_cps(str(f))
    assert 0x3053 in cps  # こ from say payload
    assert 0x672C in cps  # 本 from sceneconf title
    assert 0x30B3 not in cps  # コ is in the # comment line only


def test_collect_cps_family_base(tmp_path):
    proj = tmp_path / "p"
    (proj / "scene").mkdir(parents=True)
    (proj / "i18n").mkdir()
    (proj / "scene" / "a.nb").write_text("say(x){日本語}\n")
    (proj / "i18n" / "game_jpn.txt").write_text("k=あ\n")

    for lang in sorted(CJK_FAMILY):
        cps = collect_cps(str(proj), lang, with_base=True)
        assert 0x3000 in cps and 0x303F in cps  # full CJK base block per family
        if lang == "jpn":
            assert 0x3042 in cps  # あ from i18n value

    for lang in sorted(LATIN_FAMILY):
        cps = collect_cps(str(proj), lang, with_base=True)
        assert 0x00A0 in cps and 0x00FF in cps  # full Latin-1 base block

    eng = collect_cps(str(proj), "eng", with_base=True)
    assert 0x00A0 not in eng and 0x3000 not in eng  # eng has no base block


def test_collect_cps_without_base(tmp_path):
    proj = tmp_path / "p"
    (proj / "scene").mkdir(parents=True)
    (proj / "scene" / "a.nb").write_text("say(x){漢字}\n")
    cps = collect_cps(str(proj), "jpn", with_base=False)
    assert 0x6F22 in cps  # 漢
    assert 0x5B57 in cps  # 字
    assert 0x3000 not in cps  # no base unless requested


# ------------------------------------------------------------------- ranges


def test_merge_ranges_ascending_ordered():
    cps = {0x3050, 0x3052, 0x304F, 0x3051}
    ranges = merge_ranges(cps)
    for a, b in zip(ranges, ranges[1:]):
        assert a[1] < b[0]  # strictly ordered, non-overlapping


def test_merge_ranges_merges_contiguous():
    ranges = merge_ranges({0x3000, 0x3001, 0x3002, 0x303F})
    assert (0x3000, 0x3002) in ranges
    assert (0x303F, 0x303F) in ranges


def test_merge_ranges_empty():
    assert merge_ranges(set()) == []


def test_merge_ranges_many_singletons_vs_cap():
    # The engine's fixed cjk_ranges[] array is guarded by generate_cjk_file
    # (ValueError above MAX_RANGES); this checks a realistic sparse corpus
    # (hundreds of runs) stays well under the cap.
    ranges = merge_ranges({0x4E00 + i * 97 for i in range(300)})
    assert len(ranges) == 300
    assert len(ranges) < MAX_RANGES


# -------------------------------------------------------- glyph source merge


def test_merge_glyph_sources_priority():
    p1 = {0x3042: b"A" * 32}
    p2 = {0x3042: b"B" * 32, 0x3044: b"B" * 32}
    out = merge_glyph_sources([p1, p2], {0x3042, 0x3044})
    assert out[0x3042] == b"A" * 32  # P1 wins
    assert out[0x3044] == b"B" * 32  # P2 fills the rest


def test_merge_glyph_sources_missing_omitted():
    out = merge_glyph_sources([{0x3042: b"x" * 32}], {0x3042, 0x3051})
    assert 0x3042 in out and 0x3051 not in out


# -------------------------------------------------------------------- atlas


def test_subset_from_atlas_roundtrip():
    if not __import__("os").path.exists(ATLAS):
        pytest.skip("atlas CJK.DAT not present in repo")
    data = __import__("pathlib").Path(ATLAS).read_bytes()
    rc = struct.unpack("<H", data[4:6])[0]
    assert rc >= 4  # legacy 6-block atlas covers >= 4 merged ranges

    all_g = subset_from_atlas(ATLAS)
    assert len(all_g) > 1000
    sample = sorted(all_g)[:100]
    sel = subset_from_atlas(ATLAS, cps=set(sample))
    assert len(sel) == len(set(sample))
    assert all(v == all_g[k] for k, v in sel.items())
    # every glyph is 32 bytes of valid bitmap data
    assert all(len(v) == 32 for v in sel.values())


# --------------------------------------------------------------- generation


def _read_back(path, glyphs=None):
    """Parse a generated CJKF file; with glyphs dict, verify stored data."""
    data = path.read_bytes()
    assert data[:4] == b"CJKF"
    rc = struct.unpack("<H", data[4:6])[0]
    header = 10 + rc * 16
    ranges = []
    for i in range(rc):
        start, end, goff, _ = struct.unpack("<IIII", data[10 + i * 16:10 + i * 16 + 16])
        ranges.append((start, end, goff))
        if i == 0:
            assert goff == header  # engine mandatory first-range check
    if glyphs is not None:
        for start, end, goff in ranges:
            for cp in range(start, end + 1):
                off = goff + (cp - start) * 32
                got = data[off:off + 32]
                if cp in glyphs:
                    assert got == glyphs[cp]
                else:
                    assert got == b"\x00" * 32
    return ranges, header


def test_generate_zero_range_empty_file(tmp_path):
    out = tmp_path / "CJK_ENG.DAT"
    missing = generate_cjk_file({}, [], str(out))
    assert missing == []
    assert out.stat().st_size == 10
    ranges, header = _read_back(out)
    assert ranges == []


def test_generate_ranges_and_missing_warn(tmp_path, capsys):
    out = tmp_path / "CJK_JPN.DAT"
    missing = generate_cjk_file(
        {0x30A2: b"G" * 32},  # ア present, イ absent
        [(0x3000, 0x303F), (0x30A0, 0x30AF)],
        str(out),
    )
    assert 0x30A2 not in missing
    assert 0x30A1 in missing and 0x30AF in missing
    assert missing[0] in (0x3000, 0x30A1)
    capsys.readouterr()  # suppress the WARN diagnostics from test output
    _read_back(out, {0x30A2: b"G" * 32})  # contract + zero-fill verified


def test_generate_max_ranges_guard(tmp_path):
    ranges = [(0x10000 + i * 4097, 0x10000 + i * 4097) for i in range(MAX_RANGES + 1)]
    with pytest.raises(ValueError, match="MAX_CJK_RANGES"):
        generate_cjk_file({}, ranges, str(tmp_path / "x.DAT"))


def test_lang_base_ranges():
    assert lang_base_ranges("jpn") == [(0x3000, 0x303F)]
    assert lang_base_ranges("kor") == [(0x3000, 0x303F)]
    assert lang_base_ranges("fre") == [(0x00A0, 0x00FF)]
    assert lang_base_ranges("eng") == []


def test_validate_collect_lang():
    for lang in RUNTIME_LANGS:
        assert _validate_collect_lang(lang) == lang
    assert _validate_collect_lang("FRE") == "fre"
    with pytest.raises(ValueError):
        _validate_collect_lang("fra")  # non-runtime code
    with pytest.raises(ValueError):
        _validate_collect_lang("oops")