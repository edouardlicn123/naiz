"""Menu-button key extraction guard for i18n_gen.

mainmenu / specialmenu commands render their entry keys through tr() in the
engine, so i18n_gen must collect every entry as a translation key.  A dropped
command (or a menu button not backed by a scene declaration) would silently
fall back to English on regeneration.
"""
from pathlib import Path

from naiz_conv.i18n_gen import extract_texts

ROOT = Path(__file__).resolve().parent.parent.parent
SCENE = ROOT / "projects" / "demo-a2" / "scene"


def _menu_keys(*files):
    _dialogue, _questions, menu = extract_texts([str(f) for f in files])
    return menu


def test_mainmenu_engine_buttons_collected_after_coords_skipped():
    keys = _menu_keys(SCENE / "mainmenu.nb")
    assert {"continue", "load", "start", "special", "settings", "exit"} <= keys
    # x/y/w/h coordinates must never leak into translation keys.
    assert not {"400", "200", "2", "0"} & keys


def test_specialmenu_entries_collected():
    menu = _menu_keys(SCENE / "special.nb")
    assert {"gallery", "scenes", "music"} <= menu


def test_specialmenu_entries_not_leaked_as_dialogue():
    dialogue, _questions, _menu = extract_texts([str(SCENE / "special.nb")])
    assert not {"gallery", "scenes", "music"} & dialogue