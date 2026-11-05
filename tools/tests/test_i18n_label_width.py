"""Setting-row label/value width guard (devdoc 119 §3.4).

The 15 new i18n keys were shipped to 9 languages, but several did not *fit*
the drawing area and `draw_text` silently clips at x1 -- no error, no compiler
warning, just missing text on the board.  Measured the way the engine measures
(`render_text.c` branches on the byte high bit, so a Latin-1 letter like the
German "ae" umlaut costs CJK_GLYPH_W, not FONT_GLYPH_W):

* row labels, limit `SET_LABEL_W` = 170px: "Sound & Voice Volume" needed 248px
  in French, 208px in German, 184px in Portuguese and Spanish;
* value labels, limit `SET_VAL_W` = 80px: 5 further overflows in French,
  Portuguese and Spanish.

The pre-existing i18n guard only asserted "translated and non-empty" --
existence, not usability (devdoc 119 §3.4, same shape as §3.2).

This guard closes the usability half.  Glyph widths are read from
`core/lib/font.h` / `core/lib/cjk.h` and the row geometry is read from
`core/engine/nb_setting.c`, so the test tracks the engine instead of
freezing a second copy of the numbers.
"""

import io
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
NB_SETTING = ROOT / "core/engine/nb_setting.c"
NB_CGGALLERY = ROOT / "core/engine/nb_cggallery.c"
PREFS_C = ROOT / "core/engine/prefs.c"
FONT_H = ROOT / "core/lib/font.h"
CJK_H = ROOT / "core/lib/cjk.h"
I18N_DIR = ROOT / "projects/demo-a2/i18n"


def _define(path: Path, name: str) -> int:
    """Read `#define <name> <int>` from a header/source file."""
    m = re.search(r"#define\s+%s\s+(\d+)" % re.escape(name), path.read_text("utf-8"))
    if not m:
        raise RuntimeError("cannot find #define %s in %s" % (name, path))
    return int(m.group(1))


def _strings_in(path: Path, pattern: str) -> list:
    """All string literals of a C declaration/initialiser matching `pattern`."""
    m = re.search(pattern + r"[^=]*=\s*\{(.*?)\}", path.read_text("utf-8"), re.S)
    if not m:
        raise RuntimeError("cannot find %r in %s" % (pattern, path))
    return re.findall(r'"([^"]*)"', m.group(1))


# --- geometry and glyph metrics, straight from the engine ------------------
SET_LABEL_W = _define(NB_SETTING, "SET_LABEL_W")   # label clip width, x1 bound
SET_VAL_W = _define(NB_SETTING, "SET_VAL_W")       # value column clip width
FONT_GLYPH_W = _define(FONT_H, "FONT_GLYPH_W")     # ASCII advance
CJK_GLYPH_W = _define(CJK_H, "CJK_GLYPH_W")        # high-bit lead byte advance

# `text_width()` (render_text.c) branches on the *byte* high bit, so every
# non-ASCII codepoint costs CJK_GLYPH_W -- including Latin-1 letters such as
# the German "ae" umlaut.  Measure the same way, not by codepoint class.
def text_width(s: str) -> int:
    return sum(CJK_GLYPH_W if ord(c) > 0x7F else FONT_GLYPH_W for c in s)


# --- CG gallery cell geometry ----------------------------------------------
# The locked-cell label is drawn at x + <inset>, and the cell border sits at
# x + GAL_CELL_W, so that inset is the room the text has before it spills over
# the border.  Read both from the call site so a geometry change resizes the
# bound instead of silently voiding the check.
_GALLERY_CELL = NB_CGGALLERY.read_text("utf-8")
GAL_CELL_W = _define(NB_CGGALLERY, "GAL_CELL_W")
_m = re.search(
    r'draw_text\(tr\("\[LOCKED\]"\),\s*0,\s*x \+ (\d+),.*?x \+ GAL_CELL_W - (\d+)',
    _GALLERY_CELL, re.S)
if not _m:
    raise RuntimeError("cannot find the [LOCKED] draw_text call in nb_cggallery.c")
GAL_LABEL_INSET = int(_m.group(1))
GAL_RIGHT_INSET = int(_m.group(2))
# Hard bound: the text starts at x + GAL_LABEL_INSET and the cell border is at
# x + GAL_CELL_W, so anything wider than this spills past the border (or gets
# clipped outright if draw_text's max_width is ever passed correctly).
GAL_LOCKED_W = GAL_CELL_W - GAL_LABEL_INSET
# The designer also wanted a GAL_RIGHT_INSET margin, which would give a tighter
# bound, but draw_text compares cx against `x + max_width` where x is the
# TEXT's own origin while the call site passes an ABSOLUTE cell coordinate --
# so the limit actually enforced is GAL_CELL_W - GAL_LABEL_INSET + cell_x,
# looser and different per column.  Guard on the stable hard bound instead of
# on an artefact of that mismatch, and keep GAL_RIGHT_INSET recorded so the
# intended margin is not lost.


# --- what the setting scene actually renders --------------------------------
ROW_LABELS = re.findall(
    r'\{\s*"([^"]+)"\s*,\s*ROW_(?:ENUM|READOUT)', NB_SETTING.read_text("utf-8")
)
VALUE_LABELS = (
    _strings_in(NB_SETTING, r"static const char \*const g_onoff_labels")
    + _strings_in(NB_SETTING, r"static const char \*const g_bgm_vol_labels")
    + _strings_in(NB_SETTING, r"static const char \*const g_pcm_vol_labels")
    + _strings_in(PREFS_C, r"const char \*const PREFS_TEXT_SPEED_LABELS")
)
# `setting_progress_text()` formats "%d / %d" with the unlocked/total counts.
# Bound it at the largest project that can exist today (3 digits each).
PROGRESS_MAX = "%d / %d" % (999, 999)

LANGS = sorted(p.stem.split("_", 1)[1] for p in I18N_DIR.glob("sys_*.txt"))


def _translations(lang: str) -> dict:
    out = {}
    for line in io.open(I18N_DIR / ("sys_%s.txt" % lang), encoding="utf-8"):
        line = line.rstrip("\n")
        if "=" in line:
            key, val = line.split("=", 1)
            out[key] = val
    return out


def test_row_labels_parsed_from_engine() -> None:
    """The regexes must actually see the 7 rows, else every check below is vacuous."""
    assert len(ROW_LABELS) == 7, ROW_LABELS
    assert "Sound & Voice Vol" in ROW_LABELS
    assert len(LANGS) == 9, LANGS


def test_no_oversized_row_labels() -> None:
    """Every setting-row label must fit SET_LABEL_W in every language."""
    bad = [
        "%s/%s %r = %dpx > %dpx" % (lang, key, tr, text_width(tr), SET_LABEL_W)
        for lang in LANGS
        for key in ROW_LABELS
        for tr in [_translations(lang).get(key, "")]
        if not tr or text_width(tr) > SET_LABEL_W
    ]
    assert not bad, "clipped setting labels:\n" + "\n".join(bad)


def test_no_oversized_value_labels() -> None:
    """Enum values are centred in SET_VAL_W and clipped there too."""
    bad = [
        "%s: %r -> %r = %dpx > %dpx" % (lang, v, tr, text_width(tr), SET_VAL_W)
        for lang in LANGS
        for v in VALUE_LABELS
        for tr in [_translations(lang).get(v, "")]
        if not tr or text_width(tr) > SET_VAL_W
    ]
    assert not bad, "clipped setting values:\n" + "\n".join(bad)


def test_read_progress_readout_fits() -> None:
    """The one non-tr()'d value in the column is "%d / %d"."""
    assert text_width(PROGRESS_MAX) <= SET_VAL_W, (
        "read-progress readout %r needs %dpx, column is %dpx"
        % (PROGRESS_MAX, text_width(PROGRESS_MAX), SET_VAL_W)
    )


def test_gallery_geometry_parsed_from_engine() -> None:
    """If the call site moves, the bound must follow or the check is vacuous."""
    assert GAL_CELL_W == 144, GAL_CELL_W
    assert (GAL_LABEL_INSET, GAL_RIGHT_INSET) == (30, 30)
    assert GAL_LOCKED_W == 114, GAL_LOCKED_W
    assert "[LOCKED]" in _translations("cht")


def test_no_oversized_gallery_locked_label() -> None:
    """tr("[LOCKED]") is drawn in a locked gallery cell and clipped at
    GAL_LOCKED_W.  French "[VERROUILL[E]" (104px) is the long one and leaves
    under two characters of slack, so watch it."""
    bad = [
        "%s: %r = %dpx > %dpx" % (lang, tr, text_width(tr), GAL_LOCKED_W)
        for lang in LANGS
        for tr in [_translations(lang).get("[LOCKED]", "")]
        if not tr or text_width(tr) > GAL_LOCKED_W
    ]
    assert not bad, "clipped gallery [LOCKED] label:\n" + "\n".join(bad)


def test_gallery_locked_label_fits_with_headroom() -> None:
    """Keep margin, not just "not over": at exactly the bound a one-character
    edit in any language re-breaks the cell, and nothing else would catch it."""
    tight = [
        "%s: %r = %dpx of %dpx" % (lang, tr, text_width(tr), GAL_LOCKED_W)
        for lang in LANGS
        for tr in [_translations(lang).get("[LOCKED]", "")]
        if text_width(tr) > GAL_LOCKED_W - FONT_GLYPH_W
    ]
    assert not tight, "gallery [LOCKED] label with no headroom:\n" + "\n".join(tight)


def test_high_bit_letters_cost_cjk_width() -> None:
    """Freeze the byte-high-bit rule: German "ae" umlaut must not measure 8px.

    If this ever starts measuring ASCII width, the width checks above would
    silently under-count every accented Latin language.
    """
    assert text_width("a") == FONT_GLYPH_W
    assert text_width("\u00e4") == CJK_GLYPH_W
    assert text_width("\u97f3") == CJK_GLYPH_W


@pytest.mark.parametrize("lang", LANGS)
def test_guard_detects_oversized_translation(lang: str) -> None:
    """Self-test: an over-wide string must be rejected, not waved through.

    Guards that cannot fail are the "print instead of exit 1" antipattern
    (AGENTS.md §8, ban #4).
    """
    assert text_width("x" * (SET_LABEL_W // FONT_GLYPH_W + 1)) > SET_LABEL_W
    assert _translations(lang)["Sound & Voice Vol"]
    # and the gallery bound must reject an over-wide label the same way
    assert text_width("x" * (GAL_LOCKED_W // FONT_GLYPH_W + 1)) > GAL_LOCKED_W
