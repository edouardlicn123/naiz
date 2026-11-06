"""devdoc 119: spec/code convergence guards.

devdoc 118 was marked finished while its body still contained claims that
were never implemented, an overstated guard, a non-existent symbol and 20
stale line references.  Nothing caught it: no test reads `devdocs/`, so a
green pytest said nothing about the document being right (devdoc 119 §3.2).

These tests turn "the document matches the code" into something checkable:

1. every `file:line` reference in a finished devdoc must resolve to a
   non-blank line carrying the symbol the text names;
2. a plan that claims an existing test file was refactored must actually
   match that refactor (frozen to the corrected fact, so nobody "fixes" the
   code back to the stale 118 §9 claim);
3. a correction must not be silently removed — AGENTS.md §10 step 1 requires
   the superseded document to keep an ERRATA block pointing at its successor.

Whitelist map: symbol fragment expected at each referenced line.
"""

import io
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
DEV_DOCS = ROOT / "devdocs"

# file stem -> absolute source path(s) to search when resolving a reference
SOURCE_INDEX = {
    "nb_setting.c": ROOT / "core/engine/nb_setting.c",
    "nb_saveload.c": ROOT / "core/engine/nb_saveload.c",
    "nb_audio.c": ROOT / "core/engine/nb_audio.c",
    "nb.c": ROOT / "core/engine/nb.c",
    "nb_asset_table.h": ROOT / "core/engine/nb_asset_table.h",
    "prefs.c": ROOT / "core/engine/prefs.c",
    "prefs.h": ROOT / "core/engine/prefs.h",
    "bootmenu.c": ROOT / "core/engine/bootmenu.c",
    "nb_menu.c": ROOT / "core/engine/nb_menu.c",
    "audio.c": ROOT / "core/engine/audio.c",
    "audio.h": ROOT / "core/engine/audio.h",
    "hal_audio.c": ROOT / "core/plat/hal_audio.c",
    "save.c": ROOT / "core/engine/save.c",
    "save.h": ROOT / "core/engine/save.h",
    "save_sys.c": ROOT / "core/engine/save_sys.c",
    "main.c": ROOT / "core/engine/main.c",
    "nb_mainmenu.c": ROOT / "core/engine/nb_mainmenu.c",
    "build_game.py": ROOT / "tools/naiz_build/build_game.py",
    "render_text.c": ROOT / "core/engine/render_text.c",
    "tr.c": ROOT / "core/lib/tr.c",
}

# References whose correctness is asserted with the symbol they must contain.
# devdoc 119 §2 holds the full truth table for the 118 set.
LINE_REF_WHITELIST = {
    ("nb_setting.c", 160): "SETTING_ROWS",
    ("nb_setting.c", 179): "setting_row_y",
    ("nb_setting.c", 228): "setting_draw_row",
    ("nb_setting.c", 108): "setting_progress_text",
    ("nb_setting.c", 488): "prefs_save",
    ("nb_setting.c", 119): "sys_save_is_cg_unlocked",
    ("nb_setting.c", 122): "snprintf",
    ("nb_setting.c", 140): "Text Speed",
    ("nb_setting.c", 152): "Read Progress",
    # devdoc 177 (Phase 4 BGM preload) added bgm_load_events(),
    # audio_preload_bgm() and the BgmPreload cache, shifting every later
    # audio.c citation by +6 (327/502/511/398 -> 344/508/517/404) except
    # audio_init/frame_decode_pump, which moved by +6 and +2 respectively.
    # devdoc 186 (same-key guard) added the key field + guard block + commit
    # line, shifting 344->345, 404->415, 508->520, 517->529 (+1/+11/+12/+12);
    # audio_init/frame_decode_pump sit past those and moved by +14/+12.
    # devdoc 199E: audio_pump_once() 落在 frame_decode_pump 声明与 audio_init
    # 之间（+10），audio_init 617->627。
    ("audio.c", 345): "g_bgm_on",
    ("audio.c", 520): "g_snd_on",
    ("audio.c", 529): "g_vc_on",
    ("audio.c", 415): "audio_bgm_stop",
    ("audio.c", 627): "audio_init",
    ("audio.c", 615): "frame_decode_pump",
    ("hal_audio.c", 88): "PCM_CTRL_A46A_IRQ",
    ("hal_audio.c", 94): "PCM_IRQ_INTERVAL_MAX",
    ("hal_audio.c", 134): "hal_pcm_set_volume",
    ("hal_audio.c", 168): "PCM_VOL_PATH_PCM",
    ("nb_asset_table.h", 69): "CG_COUNT",
    ("save.h", 16): "CG_TOTAL",
    ("save_sys.c", 12): "SYSTEM.SAV",
    ("main.c", 143): "prefs_save",
    ("nb_mainmenu.c", 115): "prefs_save",
    # devdoc 119 §3.4: the i18n width guard's geometry anchors.  These were
    # cited before they were registered, and the off-by-one that followed
    # (241 written as 240) passed silently -- see
    # test_every_devdoc_ref_is_registered.
    ("nb_setting.c", 168): "SET_LABEL_W",
    ("nb_setting.c", 171): "SET_VAL_W",
    ("nb_setting.c", 242): "draw_text",
    ("nb_saveload.c", 45): "clipped",
    ("build_game.py", 542): "nb_asset_table.h",
    ("render_text.c", 245): "text_width",
    # devdoc 119 §3.4 renamed this key; the row literal moved with it
    ("nb_setting.c", 150): "Sound & Voice Vol",
    # devdoc 120 §9 -- the replacement truth table for the one retired above.
    ("prefs.c", 33): "Instant",
    ("prefs.c", 57): "prefs_get_lang",
    ("prefs.c", 93): "pref_set_bgm_volume",
    ("prefs.c", 108): "pref_set_pcm_volume",
    ("prefs.c", 181): "prefs_load",
    ("prefs.c", 187): "TEXT_SPEED_DEFAULT",
    ("prefs.c", 195): "USER.CFG",
    ("prefs.c", 242): "prefs_save",
    ("prefs.c", 244): "USER.CFG",
    ("prefs.c", 269): "prefs_set_lang",
    ("prefs.h", 75): "prefs_get_version",
    ("bootmenu.c", 109): "find_lang_index",
    ("bootmenu.c", 206): "bootmenu_run",
    ("bootmenu.c", 316): "prefs_set_lang",
    ("main.c", 151): "LANG] boot",
    ("main.c", 155): "cjk_load_for_lang",
    ("nb.c", 167): "prefs_load",
    ("nb.c", 172): "nb_set_lang",
    ("nb.c", 349): "nb_set_lang",
    ("nb_mainmenu.c", 117): "prefs_get_lang",
    ("nb_menu.c", 273): "prefs_get_version",
    ("tr.c", 28): "tr_table",
    ("tr.c", 168): "break",
    ("build_game.py", 396): "stale_settings.unlink",
    ("build_game.py", 557): "export_config_py",
    ("build_game.py", 564): "compile_engine",
}

# devdoc 118/119/120/136/138/139 已在 "0.4.001 start" 提交中归档删除，
# 原先守卫它们的 STALE/SUPERSEDED/RETIRED 引用集、注册闭包测试与 errata
# 检查随之退役。LINE_REF_WHITELIST / KNOWN_GOOD_REFS 仍是活守卫：引用
# 当前源码锚点，漂移时必须同步更新。

# References verified correct and left untouched (devdoc 119 §2, last line).
KNOWN_GOOD_REFS = {
    ("nb_saveload.c", 73), ("nb_saveload.c", 76), ("nb_saveload.c", 379),
    ("nb_saveload.c", 386), ("nb_audio.c", 29), ("nb_audio.c", 40),
    ("nb_audio.c", 51), ("nb_audio.c", 43), ("nb.c", 316),
    ("audio.h", 13), ("audio.h", 20), ("save_sys.c", 66),
    ("prefs.h", 50), ("prefs.h", 60),
}

TEST_TEXT_SPEED = ROOT / "tools/tests/test_text_speed_settings.py"
TEST_USER_CFG = ROOT / "tools/tests/test_user_cfg_settings.py"
TEST_AUDIO_INV = ROOT / "tools/tests/test_audio_settings_invariants.py"

REF_RE = re.compile(r"([a-z_]+\.(?:c|h|py))[:：](\d+)")


def _lines(path):
    return io.open(path, encoding="utf-8").read().split("\n")


# --- 1. every checked line reference must resolve ------------------------

def test_devdoc_line_refs_resolve():
    """Each whitelisted reference must land on a non-blank line carrying the
    named symbol.  A blank target is the loudest possible signal that the
    spec and the code have drifted apart (devdoc 119 §2)."""
    assert LINE_REF_WHITELIST, "whitelist must not be emptied"
    for (stem, lineno), symbol in sorted(LINE_REF_WHITELIST.items()):
        src = SOURCE_INDEX[stem]
        lines = _lines(src)
        assert 1 <= lineno <= len(lines), (
            f"{stem}:{lineno} is past end of file ({len(lines)} lines)"
        )
        text = lines[lineno - 1].strip()
        assert text, f"{stem}:{lineno} is blank — spec ref is stale"
        assert symbol in text, (
            f"{stem}:{lineno} does not mention {symbol!r}, found: {text!r}"
        )


def test_known_good_refs_still_resolve():
    """The references left untouched by the correction must stay valid; a
    future edit that moves them must update this list, not go unnoticed."""
    for stem, lineno in sorted(KNOWN_GOOD_REFS):
        lines = _lines(SOURCE_INDEX[stem])
        assert 1 <= lineno <= len(lines), f"{stem}:{lineno} past EOF"
        assert lines[lineno - 1].strip(), (
            f"{stem}:{lineno} went blank — devdoc 118's untouched refs are stale"
        )


# --- 2. the corrected "what was actually changed" fact stays corrected ----

def test_devdoc_claims_match_test_files():
    """devdoc 118 §9 claimed test_text_speed_settings.py was retargeted at
    USER.CFG and that _parse_speed/_save_line were split into project and
    preference halves.  Neither happened: only the module docstring changed.

    Freeze the corrected fact so nobody re-reads the stale §9 claim and
    refactors the file to match it."""
    body = "\n".join(_lines(TEST_TEXT_SPEED))
    # still one parser and one serialiser, not a split pair
    assert len(re.findall(r"^def _parse\w*", body, re.M)) == 1, (
        "test_text_speed_settings.py grew a second parser; devdoc 118 §9's "
        "unimplemented 'split into two halves' claim must not be applied"
    )
    assert len(re.findall(r"^def _save\w*", body, re.M)) == 1
    # the roundtrip is line-format only and must not name a file
    roundtrip = re.search(r"^def test_roundtrip_save_load.*?(?=\n\ndef |\Z)",
                          body, re.M | re.S).group(0)
    assert "settings.txt" not in roundtrip and "USER.CFG" not in roundtrip, (
        "the roundtrip test is a line-format check, not a file check"
    )
    # the two files the plan said it would create do exist
    for f in (TEST_USER_CFG, TEST_AUDIO_INV):
        assert f.is_file(), f"{f.name} is missing but devdoc 118 §9 claims it"


def test_build_guard_is_source_level_not_deployed():
    """devdoc 118 §9 described the build guard as 'running build_game.py's
    settings deploy stage'.  It is a source-text assertion; no test in this
    suite executes the deploy path.  Pin that so the wording cannot drift
    back into claiming deployment coverage."""
    src = "\n".join(_lines(TEST_USER_CFG))
    guard = re.search(r"^def test_build_never_writes_user_cfg.*?(?=\n\ndef |\Z)",
                      src, re.M | re.S).group(0)
    for banned in ("subprocess", "os.system", "Popen", "run("):
        assert banned not in guard, (
            "the build guard became an executing test; devdoc 118 §9 and "
            "devdoc 119 §4 must both be updated to match"
        )
    assert "read_text" in guard, "the guard is expected to be source-level"


# --- 4. a hand-maintained doc must not balloon (the B90 corruption) --------
#
# `docs/B90-参考-函数索引.md` was silently corrupted into a 3.4 GB blob -- a
# single line repeated ~15.5M times by an out-of-control text loop -- and it
# survived four commits because nothing checked that a hand-maintained
# reference doc stayed doc-sized.  These two guards make that failure loud.

MAX_DOC_BYTES = 1_000_000   # ~6x the largest legitimate doc in the tree
MAX_LINE_REPEATS = 5_000    # a runaway duplication signature


def _reference_docs():
    for base in (ROOT / "docs", DEV_DOCS):
        for path in sorted(base.rglob("*.md")):
            yield path


def test_reference_docs_are_doc_sized():
    """No hand-maintained doc under `docs/` or `devdocs/` may balloon past a
    sane size: a multi-MB file is the signature of the runaway loop that
    destroyed B90, not of content anyone wrote."""
    offenders = []
    for doc in _reference_docs():
        size = doc.stat().st_size
        if size > MAX_DOC_BYTES:
            offenders.append(f"{doc.relative_to(ROOT)} = {size} bytes")
    assert not offenders, (
        f"reference docs exceed {MAX_DOC_BYTES} bytes (runaway loop?): "
        + ", ".join(offenders)
    )


def test_reference_docs_have_no_runaway_repetition():
    """The other half of the B90 signature: one line repeated thousands of
    times.  Checked only for files that passed the size guard, so the read is
    bounded."""
    for doc in _reference_docs():
        if doc.stat().st_size > MAX_DOC_BYTES:
            continue  # the size guard owns this failure
        worst, worst_n = "", 0
        counts = {}
        for line in _lines(doc):
            s = line.strip()
            if not s:
                continue
            counts[s] = counts.get(s, 0) + 1
            if counts[s] > worst_n:
                worst_n, worst = counts[s], s
        assert worst_n <= MAX_LINE_REPEATS, (
            f"{doc.relative_to(ROOT)} repeats one line {worst_n} times "
            f"(> {MAX_LINE_REPEATS}): {worst[:80]!r}"
        )