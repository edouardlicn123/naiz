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
    "settings.c": ROOT / "core/engine/settings.c",
    "settings.h": ROOT / "core/engine/settings.h",
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
}

# References whose correctness is asserted with the symbol they must contain.
# devdoc 119 §2 holds the full truth table for the 118 set.
LINE_REF_WHITELIST = {
    ("nb_setting.c", 159): "SETTING_ROWS",
    ("nb_setting.c", 178): "setting_row_y",
    ("nb_setting.c", 227): "setting_draw_row",
    ("nb_setting.c", 107): "setting_progress_text",
    ("nb_setting.c", 486): "settings_save",
    ("nb_setting.c", 118): "sys_save_is_cg_unlocked",
    ("nb_setting.c", 121): "snprintf",
    ("nb_setting.c", 139): "Text Speed",
    ("nb_setting.c", 151): "Read Progress",
    ("settings.c", 185): "settings_load",
    ("settings.c", 202): "settings.txt",
    ("settings.c", 235): "USER.CFG",
    ("settings.c", 283): "USER.CFG",
    ("settings.c", 281): "settings_save",
    ("settings.c", 96): "pref_set_bgm_volume",
    ("settings.c", 111): "pref_set_pcm_volume",
    ("settings.c", 193): "TEXT_SPEED_DEFAULT",
    ("audio.c", 105): "g_bgm_on",
    ("audio.c", 233): "g_snd_on",
    ("audio.c", 242): "g_vc_on",
    ("audio.c", 147): "audio_bgm_stop",
    ("hal_audio.c", 88): "PCM_CTRL_A46A_IRQ",
    ("hal_audio.c", 94): "PCM_IRQ_INTERVAL_MAX",
    ("hal_audio.c", 121): "hal_pcm_set_volume",
    ("hal_audio.c", 155): "PCM_VOL_PATH_PCM",
    ("nb_asset_table.h", 70): "CG_COUNT",
    ("save.h", 16): "CG_TOTAL",
    ("save_sys.c", 12): "SYSTEM.SAV",
    ("main.c", 94): "settings_save",
    ("nb_mainmenu.c", 114): "settings_save",
    # devdoc 119 §3.4: the i18n width guard's geometry anchors.  These were
    # cited before they were registered, and the off-by-one that followed
    # (241 written as 240) passed silently -- see
    # test_every_devdoc_ref_is_registered.
    ("nb_setting.c", 167): "SET_LABEL_W",
    ("nb_setting.c", 170): "SET_VAL_W",
    ("nb_setting.c", 241): "draw_text",
    ("settings.c", 44): "Instant",
    ("nb_saveload.c", 44): "clipped",
    ("build_game.py", 474): "nb_asset_table.h",
    ("render_text.c", 235): "text_width",
    # devdoc 119 §3.4 renamed this key; the row literal moved with it
    ("nb_setting.c", 149): "Sound & Voice Vol",
}

# References a finished devdoc quotes on purpose, and which therefore must NOT
# resolve to the symbol the document claims.  Two groups, both deliberate:
#
# 1. Left column of devdoc 119 §2's truth table -- the *wrong* line numbers
#    devdoc 118 claims, reproduced solely so the right column can correct
#    them.  devdoc 118 §1/§3/§6/§8 may not be edited (AGENTS.md §10 step 1),
#    so the wrong value has to be quoted rather than fixed.  Several of these
#    now land on blank lines or a bare '}' -- that is the point: it is the
#    evidence that 118 drifted.
# 2. devdoc 119 §5's mutation self-test table, which names the broken value
#    each mutation introduces.
#
# If a value moves out of this set because someone corrected the document,
# that is a good change -- but it must be a conscious one.
STALE_QUOTED_REFS = {
    # 1. devdoc 118's stale claims, quoted in 119 §2's left column
    ("audio.c", 112), ("build_game.py", 467), ("hal_audio.c", 83),
    ("hal_audio.c", 120), ("hal_audio.c", 131), ("nb_asset_table.h", 47),
    ("nb_setting.c", 49), ("nb_setting.c", 60), ("nb_setting.c", 71),
    ("nb_setting.c", 80), ("nb_setting.c", 99), ("nb_setting.c", 116),
    ("nb_setting.c", 331), ("settings.c", 65), ("settings.c", 108),
    ("settings.c", 115), ("settings.c", 144), ("settings.c", 151),
    ("settings.c", 154), ("settings.h", 49),
    # 2. mutation self-test table in 119 §5
    ("settings.c", 80),
    # 3. devdoc 119 §5.1 quotes the WRONG value it made the same mistake twice
    ("nb_setting.c", 240),
}

# References verified correct and left untouched (devdoc 119 §2, last line).
KNOWN_GOOD_REFS = {
    ("nb_saveload.c", 73), ("nb_saveload.c", 76), ("nb_saveload.c", 379),
    ("nb_saveload.c", 386), ("nb_audio.c", 29), ("nb_audio.c", 40),
    ("nb_audio.c", 51), ("nb_audio.c", 43), ("nb.c", 300),
    ("audio.h", 13), ("audio.h", 20), ("save_sys.c", 66),
    ("settings.h", 50), ("build_game.py", 320),
}

DOC_118 = DEV_DOCS / "118-玩家偏好分家与音频开关音量设置场景.md"
DOC_119 = DEV_DOCS / "119-用户偏好分家实装订正与设计门控与规格双源守恒.md"
TEST_TEXT_SPEED = ROOT / "tools/tests/test_text_speed_settings.py"
TEST_USER_CFG = ROOT / "tools/tests/test_user_cfg_settings.py"
TEST_AUDIO_INV = ROOT / "tools/tests/test_audio_settings_invariants.py"

REF_RE = re.compile(r"([a-z_]+\.(?:c|h|py))[:：](\d+)")


def _lines(path):
    return io.open(path, encoding="utf-8").read().split("\n")


def _devdoc_line_refs(doc):
    """(stem, lineno) for every file:line reference in a devdoc."""
    for raw in _lines(doc):
        for m in REF_RE.finditer(raw):
            yield m.group(1), int(m.group(2))


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


def test_every_devdoc_ref_is_registered():
    """No reference may exist outside the three known sets.

    `LINE_REF_WHITELIST` is a closed list, so an *unregistered* reference was
    unchecked: writing `nb_setting.c:240` instead of `:241` in devdoc 119 §3.4
    passed the whole suite.  The whitelist protects the references someone
    remembered to add; this test protects the ones nobody remembered.

    Any new citation must be classified as a real reference (whitelist, with
    the symbol it must contain), as verified-correct (KNOWN_GOOD_REFS), or as
    a deliberate quote of a superseded/incorrect value (STALE_QUOTED_REFS).
    """
    registered = set(LINE_REF_WHITELIST) | set(KNOWN_GOOD_REFS) | STALE_QUOTED_REFS
    for doc in (DOC_118, DOC_119):
        unknown = sorted(
            "%s:%d" % ref for ref in set(_devdoc_line_refs(doc)) - registered
        )
        assert not unknown, (
            "%s cites %d reference(s) that no test classifies: %s\n"
            "Add each to LINE_REF_WHITELIST (with the symbol it must contain), "
            "KNOWN_GOOD_REFS, or STALE_QUOTED_REFS."
            % (doc.name, len(unknown), ", ".join(unknown))
        )


def test_devdoc_118_references_match_truth_table():
    """devdoc 118 §1/§3/§6/§8 carry pre-implementation line numbers on
    purpose: AGENTS.md §10 step 1 forbids editing a finished document.
    What must hold is that devdoc 119 carries the correcting truth table, so
    a reader following 118 is redirected rather than misled."""
    text = "\n".join(_lines(DOC_119))
    for stem, lineno in (("nb_setting.c", 159), ("settings.c", 185),
                         ("audio.c", 147), ("hal_audio.c", 155)):
        assert f"{stem}:{lineno}" in text, (
            f"devdoc 119 must record the corrected location {stem}:{lineno}"
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


# --- 3. a correction must not be silently removed (AGENTS.md §10 step 1) --

def test_devdoc_118_keeps_its_errata_block():
    """118 is superseded but must keep pointing at 119.  Deleting the block
    would restore a silently-wrong finished document."""
    head = "\n".join(_lines(DOC_118)[:20])
    assert "ERRATA" in head, (
        "devdoc 118 lost its ERRATA block — AGENTS.md §10 requires the "
        "superseded document to keep pointing at its successor"
    )
    assert "119" in head, "the ERRATA block must name devdoc 119"


def test_finished_devdoc_has_no_pending_claims():
    """A document marked finished may legitimately defer real-hardware work
    (§10), but must not defer its own bookkeeping."""
    text = "\n".join(_lines(DOC_118))
    assert "状态**：完结" in text
    for stale in ("验证结果待回填", "状态**：计划中", "尚未实施"):
        assert stale not in text, (
            f"devdoc 118 is marked finished but still says {stale!r}"
        )


@pytest.mark.parametrize("doc", [DOC_118, DOC_119])
def test_cited_docs_exist(doc):
    """Every sibling devdoc/refdoc a document points at must be on disk."""
    text = "\n".join(_lines(doc))
    for m in re.finditer(r"`((?:devdocs|docs|tools|logs)/[^`]+?)\.(?:md|py)`", text):
        target = ROOT / m.group(1)
        target = target.with_suffix("." + m.group(0).rsplit(".", 1)[1].strip("`"))
        assert target.exists(), f"{doc.name} cites missing {target}"