"""devdoc 205 §15.1: %myname% must survive translation.

The dialog layer expands %myname% after tr() lookup, so a translation that
drops the placeholder would silently lose the player's chosen name.
"""

import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DIALOG = ROOT / "core" / "engine" / "nb_dialog.c"
DISPLAY = ROOT / "core" / "engine" / "scene_display.c"


def _read(path):
    return path.read_text(encoding="utf-8")


def test_translations_preserve_myname_placeholder():
    for proj in sorted((ROOT / "projects").iterdir()):
        i18n = proj / "i18n"
        if not i18n.is_dir():
            continue
        for f in sorted(i18n.glob("game_*.txt")):
            with io.open(f, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    key, sep, value = line.partition("=")
                    if not sep or "%myname%" not in key:
                        continue
                    assert "%myname%" in value, (
                        f"{f.name}:{lineno}: translation dropped %myname%"
                    )


def test_engine_expands_myname_before_dialog_show():
    dialog = _read(DIALOG)
    assert "nb_text_expand_vars" in dialog, (
        "nb_dialog.c must provide nb_text_expand_vars()"
    )
    assert "myname" in dialog, "the expansion table must include myname"
    display = _read(DISPLAY)
    assert "nb_text_expand_vars(text)" in display, (
        "dialog_show must receive the expanded text"
    )
