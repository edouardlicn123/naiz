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
    ("nb_setting.c", 159): "SETTING_ROWS",
    ("nb_setting.c", 178): "setting_row_y",
    ("nb_setting.c", 227): "setting_draw_row",
    ("nb_setting.c", 107): "setting_progress_text",
    ("nb_setting.c", 486): "prefs_save",
    ("nb_setting.c", 118): "sys_save_is_cg_unlocked",
    ("nb_setting.c", 121): "snprintf",
    ("nb_setting.c", 139): "Text Speed",
    ("nb_setting.c", 151): "Read Progress",
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
    ("main.c", 94): "prefs_save",
    ("nb_mainmenu.c", 115): "prefs_save",
    # devdoc 119 §3.4: the i18n width guard's geometry anchors.  These were
    # cited before they were registered, and the off-by-one that followed
    # (241 written as 240) passed silently -- see
    # test_every_devdoc_ref_is_registered.
    ("nb_setting.c", 167): "SET_LABEL_W",
    ("nb_setting.c", 170): "SET_VAL_W",
    ("nb_setting.c", 241): "draw_text",
    ("nb_saveload.c", 44): "clipped",
    ("build_game.py", 448): "nb_asset_table.h",
    ("render_text.c", 235): "text_width",
    # devdoc 119 §3.4 renamed this key; the row literal moved with it
    ("nb_setting.c", 149): "Sound & Voice Vol",
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
    ("bootmenu.c", 103): "find_lang_index",
    ("bootmenu.c", 200): "bootmenu_run",
    ("bootmenu.c", 286): "prefs_set_lang",
    ("main.c", 101): "LANG] boot",
    ("main.c", 105): "cjk_load_for_lang",
    ("nb.c", 166): "prefs_load",
    ("nb.c", 171): "nb_set_lang",
    ("nb.c", 337): "nb_set_lang",
    ("nb_mainmenu.c", 117): "prefs_get_lang",
    ("nb_menu.c", 273): "prefs_get_version",
    ("tr.c", 28): "tr_table",
    ("tr.c", 168): "break",
    ("build_game.py", 325): "stale_settings.unlink",
    ("build_game.py", 466): "export_config_py",
    ("build_game.py", 470): "compile_engine",
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
    ("nb_setting.c", 331),
    # 3. devdoc 119 §5.1 quotes the WRONG value it made the same mistake twice
    ("nb_setting.c", 240),
}

# References to files RENAMED in 0.3.014.  devdocs 118/119 are finished and may
# not be edited (AGENTS.md §10 step 1), so their `settings.c:N` / `settings.h:N`
# / `settings_menu.c:N` citations still name a path that no longer exists.  They
# are deliberately NOT resolved against current line numbers -- the line numbers
# were valid for a different file.  devdoc 119 §2's truth table is voided by its
# ERRATA; devdoc 120 §9 is the replacement, and LINE_REF_WHITELIST checks that
# instead.  Renaming a *stem* here would silently unregister 118/119's textual
# citations and let test_every_devdoc_ref_is_registered pass unnoticed.
RETIRED_FILE_QUOTES = {
    # devdoc 119 §2's truth table (right column) and §5's mutation targets
    ("settings.c", 44), ("settings.c", 62), ("settings.c", 65),
    ("settings.c", 80), ("settings.c", 96), ("settings.c", 108),
    ("settings.c", 111), ("settings.c", 115), ("settings.c", 144),
    ("settings.c", 151), ("settings.c", 154), ("settings.c", 185),
    ("settings.c", 192), ("settings.c", 193), ("settings.c", 202),
    ("settings.c", 235), ("settings.c", 281), ("settings.c", 283),
    ("settings.c", 308), ("settings.h", 49), ("settings.h", 50),
    ("settings_menu.c", 105), ("settings_menu.c", 162),
    # devdoc 120 §2.2 cites bootmenu.c:105 in its pre-rename coordinate
    # paragraph; find_lang_index now lives at 103 and is checked there.
    ("bootmenu.c", 105),
    # devdoc 118 §6.1 / devdoc 119 §2 last line: build_game.py's settings.txt
    # deploy stage.  Removed in 0.3.014; the prune that replaced it is 120 §9.
    ("build_game.py", 320),
    # devdoc 119 §2 last row: the nb_asset_table.h export line, which 119
    # recorded as correct at 474.  Deleting the settings deploy block above it
    # shifted the file, so 474 no longer names that statement.  The line now
    # carrying it is 448, registered in LINE_REF_WHITELIST for 120 §9.
    ("build_game.py", 474),
    # devdoc 120 §2.2 quotes main.c:97 as the pre-fix coordinate of
    # `cjk_load_for_lang(settings_get_lang())`.  main.c still exists, but the
    # symbol that claim rests on (settings_get_lang) is gone and the line has
    # since moved, so it is a history quote, not a resolvable reference.
    ("main.c", 97),
    # devdoc 118 §六 cites nb_mainmenu.c:114.  Adding #include "bootmenu.h"
    # there (0.3.014, to fix Watcom W131) shifted it to 115, which 120 §9
    # registers.
    ("nb_mainmenu.c", 114),
    # devdoc 120 §2.2 quotes nb_mainmenu.c:116 in the pre-rename coordinate
    # paragraph, alongside settings_get_lang() which no longer exists.
    ("nb_mainmenu.c", 116),
}

# References verified correct and left untouched (devdoc 119 §2, last line).
KNOWN_GOOD_REFS = {
    ("nb_saveload.c", 73), ("nb_saveload.c", 76), ("nb_saveload.c", 379),
    ("nb_saveload.c", 386), ("nb_audio.c", 29), ("nb_audio.c", 40),
    ("nb_audio.c", 51), ("nb_audio.c", 43), ("nb.c", 300),
    ("audio.h", 13), ("audio.h", 20), ("save_sys.c", 66),
    ("prefs.h", 50), ("prefs.h", 60),
}

DOC_118 = DEV_DOCS / "118-玩家偏好分家与音频开关音量设置场景.md"
DOC_119 = DEV_DOCS / "119-用户偏好分家实装订正与设计门控与规格双源守恒.md"
DOC_120 = DEV_DOCS / "120-settings.txt废止与config.toml单一配置源与启动菜单语言根修.md"
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
    registered = (set(LINE_REF_WHITELIST) | set(KNOWN_GOOD_REFS)
                  | STALE_QUOTED_REFS | RETIRED_FILE_QUOTES)
    for doc in (DOC_118, DOC_119, DOC_120):
        unknown = sorted(
            "%s:%d" % ref for ref in set(_devdoc_line_refs(doc)) - registered
        )
        assert not unknown, (
            "%s cites %d reference(s) that no test classifies: %s\n"
            "Add each to LINE_REF_WHITELIST (with the symbol it must contain), "
            "KNOWN_GOOD_REFS, STALE_QUOTED_REFS, or RETIRED_FILE_QUOTES."
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


def test_retired_truth_table_stays_declared_void():
    """devdoc 119 §2's line truth table was built on settings.c.  The 0.3.014
    rename voided every row of it.  AGENTS.md §10: a known-wrong conclusion
    left in place is unfinished work -- so 119 must keep an ERRATA naming the
    void, and devdoc 120 must supply the replacement table."""
    head = "\n".join(_lines(DOC_119)[:24])
    assert "ERRATA" in head, (
        "devdoc 119 lost its ERRATA block; its §2 truth table is void after "
        "the settings.c -> prefs.c rename and must not read as current"
    )
    assert "120" in head, "the ERRATA block must point at devdoc 120"
    text_120 = "\n".join(_lines(DOC_120))
    assert "## 九、行号真值表" in text_120, (
        "devdoc 120 must carry the replacement truth table"
    )
    assert "现行坐标" in text_120, (
        "devdoc 120 must label its line numbers as the current coordinate set, "
        "distinct from the pre-rename coordinates used in its own §2/§3"
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


@pytest.mark.parametrize("doc", [DOC_118, DOC_119, DOC_120])
def test_cited_docs_exist(doc):
    """Every sibling devdoc/refdoc a document points at must be on disk."""
    text = "\n".join(_lines(doc))
    # Greedy up to the closing backtick: a devdoc title may itself contain a
    # dot (devdoc 120's name cites settings.txt / config.toml).  A lazy
    # `[^`]+?` stops at the first `.md` and resolves a truncated path, which
    # reports a missing file that exists -- the guard then looks broken rather
    # than wrong, and gets "fixed" by renaming documents.
    for m in re.finditer(r"`((?:devdocs|docs|tools|logs)/[^`]+\.(?:md|py))`",
                         text):
        target = ROOT / m.group(1)
        assert target.exists(), f"{doc.name} cites missing {target}"