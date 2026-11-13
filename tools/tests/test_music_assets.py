"""Music-room asset export guard (devdoc 206).

The music room (nb_music.c) enumerates every registered BGM from
BGM_COUNT / bgm_title_map[] in the generated nb_asset_table.h, mirroring how
the CG gallery enumerates CG_COUNT.  These guards pin the export contract:

  * BGM_COUNT == bgm_map rows == bgm_title_map rows (the arrays are
    index-parallel; a drift silently shifts a track's title onto its
    neighbour);
  * a BGM row with an empty / absent title exports an empty title so the
    engine can fall back to the script key, and a project whose img_map
    predates the title column still exports;
  * the shipped demo-a2 BGM rows carry a non-empty human-readable title;
  * nb_music.c keeps the empty-title fallback.
"""

import io
import json
import sqlite3
from pathlib import Path

from naiz_build import export_asset_table

ROOT = Path(__file__).resolve().parent.parent.parent
NB_MUSIC = ROOT / "core" / "engine" / "nb_music.c"
DEMO_DB = ROOT / "projects" / "demo-a2" / "ASSETS.DB"


def _make_project(tmp_path, bgm_rows, with_title=True):
    """Build a minimal project dir (ASSETS.DB + characters/expressions.json).

    bgm_rows: list of (name, title) tuples registered as type='BGM'.
    """
    (tmp_path / "characters.json").write_text(
        json.dumps({"characters": [{"key": "fei", "id": 9, "name": "Fei"}]}),
        encoding="utf-8")
    (tmp_path / "expressions.json").write_text(
        json.dumps({"expressions": []}), encoding="utf-8")

    db = sqlite3.connect(str(tmp_path / "ASSETS.DB"))
    if with_title:
        db.execute("CREATE TABLE img_map (id INTEGER PRIMARY KEY, filename TEXT, "
                   "type TEXT, name TEXT, title TEXT DEFAULT '')")
        for i, (name, title) in enumerate(bgm_rows):
            db.execute("INSERT INTO img_map (id, filename, type, name, title) "
                       "VALUES (?,?,?,?,?)", (i + 1, f"bgm/{name}.mid", "BGM", name, title))
    else:
        db.execute("CREATE TABLE img_map (id INTEGER PRIMARY KEY, filename TEXT, "
                   "type TEXT, name TEXT)")
        for i, (name, _title) in enumerate(bgm_rows):
            db.execute("INSERT INTO img_map (id, filename, type, name) VALUES (?,?,?,?)",
                       (i + 1, f"bgm/{name}.mid", "BGM", name))
    db.commit()
    db.close()

    out = tmp_path / "nb_asset_table.h"
    counts = export_asset_table.generate(str(tmp_path), str(out))
    return out.read_text(encoding="utf-8"), counts


def test_titles_exported_and_arrays_parallel(tmp_path):
    header, counts = _make_project(
        tmp_path, [("melody_town", "Melody Town Theme"), ("icy_garden", "Icy Garden")])
    assert "#define BGM_COUNT 2" in header
    assert '{"melody_town", "Melody Town Theme"},' in header
    assert '{"icy_garden", "Icy Garden"},' in header
    # counts tuple: (img, char, expr, spr, cg, bgm, snd, vc, fmp)
    assert counts[5] == 2


def test_empty_title_exported_empty_for_engine_fallback(tmp_path):
    """An empty title is emitted as "" (not replaced here) so the engine's
    music_title() falls back to the script key."""
    header, _ = _make_project(tmp_path, [("untitled_track", "")])
    assert '{"untitled_track", ""},' in header


def test_project_without_title_column_still_exports(tmp_path):
    """A project whose img_map predates the title column must not break the
    export (title falls back to the script key at render time)."""
    header, counts = _make_project(tmp_path, [("old_track", "")], with_title=False)
    assert "#define BGM_COUNT 1" in header
    assert '{"old_track", ""},' in header
    assert counts[5] == 1


def test_shipped_bgm_rows_have_titles():
    """The demo-a2 music room must show real names, not raw script keys."""
    db = sqlite3.connect(str(DEMO_DB))
    rows = list(db.execute("SELECT name, title FROM img_map WHERE type='BGM'"))
    db.close()
    assert rows, "demo-a2 registers no BGM assets"
    blank = [name for name, title in rows if not (title or "").strip()]
    assert not blank, f"BGM rows without a display title: {blank}"


def test_engine_keeps_empty_title_fallback():
    src = io.open(NB_MUSIC, encoding="utf-8").read()
    assert "bgm_title_map[abs].title" in src
    assert "bgm_title_map[abs].name" in src, (
        "nb_music.c must fall back to the script key when the title is empty")
