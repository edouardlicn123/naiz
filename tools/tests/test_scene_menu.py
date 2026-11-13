#!/usr/bin/env python3
"""Scene-menu guards (devdoc 208, extended by devdoc 209).

Pins the build-time scan (sceneconf filtering, escaped titles, unlock ids),
the thumbnail policy (CG thumb / ANI frame 0 / letter icon), the Python<->C
grid constant pair, command registration, the locked-scene visibility filter,
gallery playback return, and the i18n keys/widths.
"""
import re
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from naiz_build.scene_menu import (  # noqa: E402
    CELL_H, CELL_W, GRID_COLS, GRID_ROWS, THUMB_H, THUMB_W, build_scene_menu,
)
from naiz_lib.anim_container import (  # noqa: E402
    ANI_TRACK_PIXEL, ANI_TYPE_FULLSCREEN, AnimContainerDef, build_ani,
)
from naiz_lib.mag_codec import decode_mag_full  # noqa: E402

ENGINE_C = ROOT / "core" / "engine" / "nb_scene_menu.c"
NB_C = ROOT / "core" / "engine" / "nb.c"
NB_H = ROOT / "core" / "engine" / "nb.h"
NB_COMMANDS_C = ROOT / "core" / "engine" / "nb_commands.c"
NB_COMMANDS_H = ROOT / "core" / "engine" / "nb_commands.h"
DEMO = ROOT / "projects" / "demo-a2"

SCHEMA = ("CREATE TABLE img_map (id INTEGER PRIMARY KEY, filename TEXT NOT NULL,"
          " type TEXT DEFAULT 'BG', name TEXT DEFAULT \"\", title TEXT DEFAULT '')")


def _make_project(tmp_path: Path):
    proj = tmp_path / "proj"
    (proj / "scene").mkdir(parents=True)
    (proj / "images").mkdir()
    db = sqlite3.connect(str(proj / "ASSETS.DB"))
    db.execute(SCHEMA)
    db.commit()
    db.close()
    return proj


def _write_scene(proj: Path, name: str, *lines: str):
    (proj / "scene" / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build(proj: Path, tmp_path: Path) -> str:
    header = tmp_path / "nb_scene_menu.h"
    build_scene_menu(proj, proj / "scene", header_path=header)
    return header.read_text(encoding="utf-8")


def test_scan_filters_normal_onlist(tmp_path):
    proj = _make_project(tmp_path)
    _write_scene(proj, "nbook001.nb", "sceneconf(){Alpha, normal, onlist}")
    _write_scene(proj, "nbook002.nb", "sceneconf(){Beta, normal, outlist}")
    _write_scene(proj, "nbook003.nb", "sceneconf(){Gamma, menu, onlist}")
    _write_scene(proj, "nbook004.nb", "sceneconf(){Delta,,onlist}")
    _write_scene(proj, "nbook005.nb", "sceneconf(){Epsilon, normal}")

    header = _build(proj, tmp_path)
    assert '"nbook001.nb"' in header and '"nbook004.nb"' in header
    for absent in ('"nbook002.nb"', '"nbook003.nb"', '"nbook005.nb"'):
        assert absent not in header
    # No CG/ANIM in any scene -> letter icon fallback; unlock id from the name.
    assert re.search(r'\{\s*"nbook001\.nb",\s*"Alpha",\s*0,\s*1\s*\}', header)
    assert re.search(r'\{\s*"nbook004\.nb",\s*"Delta",\s*0,\s*4\s*\}', header)


def test_title_escape_uses_next_field(tmp_path):
    proj = _make_project(tmp_path)
    _write_scene(proj, "nbook001.nb", r"sceneconf(){Ira\, Jr., normal, onlist}")

    header = _build(proj, tmp_path)
    assert '"Ira, Jr."' in header
    src = (ROOT / "tools" / "naiz_build" / "scene_menu.py").read_text(encoding="utf-8")
    assert "next_field(" in src


def test_unlock_id_requires_nbook_name(tmp_path):
    proj = _make_project(tmp_path)
    _write_scene(proj, "intro.nb", "sceneconf(){Intro, normal, onlist}")
    with pytest.raises(RuntimeError, match="nbookNNN"):
        _build(proj, tmp_path)


def test_unlock_id_range_matches_save_h(tmp_path):
    from naiz_build.scene_menu import SCENE_TOTAL

    save_h = (ROOT / "core" / "engine" / "save.h").read_text(encoding="utf-8")
    m = re.search(r"^#define\s+SCENE_TOTAL\s+(\d+)", save_h, re.MULTILINE)
    assert m and int(m.group(1)) == SCENE_TOTAL

    proj = _make_project(tmp_path)
    _write_scene(proj, f"nbook{SCENE_TOTAL + 1}.nb",
                 "sceneconf(){Far, normal, onlist}")
    with pytest.raises(RuntimeError, match="outside"):
        _build(proj, tmp_path)


def test_cg_thumb_id_from_assets_db(tmp_path):
    header = tmp_path / "nb_scene_menu.h"
    build_scene_menu(DEMO, DEMO / "scene", header_path=header)
    text = header.read_text(encoding="utf-8")
    assert re.search(
        r'\{\s*"nbook005\.nb",\s*"Come with cat",\s*29,\s*5\s*\}', text)
    # devdoc 209: unlock_id always mirrors the nbookNNN suffix; scenes without a
    # CG/ANI thumb fall back to 0 (letter icon).  Derived so demo flag edits
    # (e.g. nbook002 -> outlist) need no test change.
    rows = re.findall(
        r'\{\s*"([^"]+\.nb)",\s*"[^"]*",\s*(\d+),\s*(\d+)\s*\}', text)
    assert rows
    for name, thumb, unlock in rows:
        assert int(unlock) == int(re.search(r"(\d+)", name).group(1)), name


def test_anim_first_frame_thumb(tmp_path):
    from PIL import Image
    from naiz_conv.mag_convert import convert_image

    proj = _make_project(tmp_path)
    blob = convert_image(Image.new("RGB", (8, 8), (200, 30, 30)), no_resize=True)
    container = build_ani(AnimContainerDef(
        type=ANI_TYPE_FULLSCREEN, track=ANI_TRACK_PIXEL,
        width=8, height=8, blobs=[blob], ticks=[4]))
    (proj / "ani").mkdir()
    (proj / "ani" / "CLIP.ANI").write_bytes(container)

    db = sqlite3.connect(str(proj / "ASSETS.DB"))
    db.execute("INSERT INTO img_map (filename, type, name) VALUES (?,?,?)",
               ("ani/CLIP.ANI", "ANI", "clip"))
    db.commit()
    db.close()

    _write_scene(proj, "nbook001.nb", "sceneconf(){Clip, normal, onlist}",
                 "playanima(normal){clip}")
    header = _build(proj, tmp_path)

    m = re.search(r'\{\s*"nbook001\.nb",\s*"Clip",\s*(\d+),\s*1\s*\}', header)
    assert m and int(m.group(1)) != 0, header
    thumb = proj / "images" / "clip_t.MAG"
    assert thumb.is_file()
    decoded = decode_mag_full(thumb.read_bytes())
    assert decoded is not None
    assert (decoded[1], decoded[2]) == (THUMB_W, THUMB_H)
    db = sqlite3.connect(str(proj / "ASSETS.DB"))
    row = db.execute("SELECT type FROM img_map WHERE filename=?",
                     ("images/clip_t.MAG",)).fetchone()
    db.close()
    assert row == ("THUMB",)


def _define(path: Path, name: str) -> str:
    m = re.search(rf"^#define\s+{name}\s+(.+)$", path.read_text(), re.MULTILINE)
    assert m, f"{name} not found in {path.name}"
    return m.group(1).split("/*")[0].strip()


def test_grid_constants_in_sync():
    py = {"SCM_THUMB_W": THUMB_W, "SCM_THUMB_H": THUMB_H,
          "SCM_COLS": GRID_COLS, "SCM_ROWS": GRID_ROWS,
          "SCM_CELL_W": CELL_W, "SCM_CELL_H": CELL_H}
    for name, value in py.items():
        assert int(_define(ENGINE_C, name)) == value, name

    origin_y = int(_define(ENGINE_C, "SCM_ORIGIN_Y"))
    step_y = int(_define(ENGINE_C, "SCM_STEP_Y"))
    rows = int(_define(ENGINE_C, "SCM_ROWS"))
    cell_h = int(_define(ENGINE_C, "SCM_CELL_H"))
    arrows_y = int(_define(ENGINE_C, "SCM_ARROWS_Y"))
    grid_bottom = int(_define(ENGINE_C, "SCM_GRID_BOTTOM"))
    assert grid_bottom == origin_y + (rows - 1) * step_y + cell_h
    assert grid_bottom < arrows_y


def test_command_registered():
    c_src = NB_COMMANDS_C.read_text(encoding="utf-8")
    assert '"scenesmenu"' in c_src
    line = next(l for l in c_src.splitlines() if '"scenesmenu"' in l)
    assert "CMD_BLOCKING" in line
    assert "cmd_scenesmenu" in NB_COMMANDS_H.read_text(encoding="utf-8")


def test_no_runtime_accessor():
    for path in (NB_C, NB_H):
        src = path.read_text(encoding="utf-8")
        assert "nb_is_scene_listed" not in src, path.name
        assert "scene_listed" not in src, path.name


def test_locked_scenes_are_hidden():
    src = ENGINE_C.read_text(encoding="utf-8")
    assert "sys_save_is_scene_unlocked" in src
    assert "scm_build_visible" in src
    # The grid pages over the unlocked subset, mapped back to the full table.
    assert "scene_menu_entries[scm_visible[" in src
    assert "scm_visible_count" in src


def test_gallery_playback_returns_to_scenes():
    scene_c = (ROOT / "core" / "engine" / "nb_scene.c").read_text(encoding="utf-8")
    assert "nb_get_playback_mode()" in scene_c
    assert '"scenes.nb"' in scene_c
    assert "SCENE_SWITCH_GALLERY" in ENGINE_C.read_text(encoding="utf-8")
    assert "SCENE_SWITCH_GALLERY" in NB_H.read_text(encoding="utf-8")


def test_unlock_on_entry_inside_nb_load():
    src = NB_C.read_text(encoding="utf-8")
    load_body = src.split("static void nb_load(", 1)[1].split("\n}", 1)[0]
    assert "sys_save_unlock_scene" in load_body
    save_sys = (ROOT / "core" / "engine" / "save_sys.c").read_text(encoding="utf-8")
    assert "sys_save_is_scene_unlocked" in save_sys
    assert "sys_save_is_scene_unlocked" in (ROOT / "core" / "engine" / "save.h").read_text(
        encoding="utf-8")


def _text_width(s: str) -> int:
    # render_text.c branches on the byte high bit: non-ASCII costs 16px.
    return sum(16 if ord(c) > 0x7F else 8 for c in s)


def test_i18n_keys_present():
    from naiz_conv.i18n_gen import SYSTEM_UI_KEYS

    keys = ("SCENE GALLERY", "No scenes available.",
            "Play the story to unlock scenes.")
    for key in keys:
        assert key in SYSTEM_UI_KEYS

    sys_dir = DEMO / "i18n"
    files = sorted(sys_dir.glob("sys_*.txt"))
    assert len(files) == 9
    for path in files:
        table = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                table[k.strip()] = v.strip()
        for key in keys:
            assert table.get(key), (path.name, key)
        # Title drawn at scale 3 (640 wide); messages at scale 1 in a 240px box.
        assert _text_width(table["SCENE GALLERY"]) * 3 <= 640, path.name
        assert _text_width(table["No scenes available."]) <= 240, path.name
        assert _text_width(table["Play the story to unlock scenes."]) <= 240, path.name
