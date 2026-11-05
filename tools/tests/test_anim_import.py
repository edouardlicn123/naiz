"""anim_import integration tests — pixel & palette assembly paths.

Exercises assemble_pixel / assemble_palette / build_ani end-to-end with
synthetic tiny assets and per-project animation DBs, including the
palette-track difference-chain semantics (devdoc 78 §3.4/§6.1).
"""

import sqlite3

from PIL import Image

import pytest

from naiz_build.anim_import import assemble_palette, assemble_pixel
from naiz_build.anim_script import parse_anim_script
from naiz_lib.anim_container import ANI_PALETTE_BYTES, build_ani, parse_ani


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    name     TEXT NOT NULL,
    filename TEXT NOT NULL,
    kind     TEXT NOT NULL,
    mtime    REAL NOT NULL,
    size     INTEGER NOT NULL,
    PRIMARY KEY (name, kind)
)
"""


def _make_db(tmp_path, project, rows):
    """Create animation/projects/<project>/db/<project>.db;
    rows are (name, kind, filename)."""
    db_dir = tmp_path / "animation" / "projects" / project / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_dir / f"{project}.db")
    conn.execute(_DB_SCHEMA)
    conn.executemany(
        "INSERT INTO assets(name, filename, kind, mtime, size) "
        "VALUES (?, ?, ?, 0, 0)",
        [(n, f, k) for n, k, f in rows])
    conn.commit()
    conn.close()
    return db_dir


def _make_png(path, w=16, h=16):
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 16) % 256, (y * 16) % 256, ((x + y) * 8) % 256)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def _make_script(tmp_path, project, text, name="t"):
    script_dir = tmp_path / "animation" / "projects" / project / "scripts"
    script_dir.mkdir(parents=True, exist_ok=True)
    script = script_dir / f"{name}.na"
    script.write_text(text, encoding="utf-8")
    return script


def _entry(table, idx):
    return tuple(table[idx * 3:idx * 3 + 3])


# ---------------------------------------------------------------------------
# Pixel track
# ---------------------------------------------------------------------------

def test_assemble_pixel_own_palettes(tmp_path):
    root = tmp_path / "assets"
    _make_png(root / "aniframe" / "anim" / "a.png", w=640, h=400)
    _make_png(root / "aniframe" / "anim" / "b.png", w=640, h=400)
    db_root = _make_db(tmp_path, "aniframe",
                       [("a", "png", "a.png"), ("b", "png", "b.png")])
    script = _make_script(
        tmp_path, "aniframe",
        "animaconf(fullscreen,pixel,aniframe)\n"
        "frame(0.5){a}\n"
        "frame(0.25){b}\n")

    defn = parse_anim_script(script, root, db_root)
    container, total_raw = assemble_pixel(defn, project_dir=None)

    assert (container.type, container.track) == (0, 0)
    assert container.nframes == 2 and container.nblob == 2
    assert container.ticks == [30, 15]
    assert container.palettes is None and container.palsz == 0
    assert total_raw == 640 * 400 * 4 * 2

    r = parse_ani(build_ani(container))
    assert r.blobs == container.blobs
    assert r.fps_nominal == 0  # variable durations


def test_assemble_pixel_multi_name_sequence(tmp_path):
    root = tmp_path / "assets"
    _make_png(root / "p" / "anim" / "f1.png", w=640, h=400)
    _make_png(root / "p" / "anim" / "f2.png", w=640, h=400)
    db_root = _make_db(tmp_path, "p",
                       [("f1", "png", "f1.png"), ("f2", "png", "f2.png")])
    script = _make_script(
        tmp_path, "p", "animaconf(fullscreen,pixel,p)\nframe(0.5){f1,f2,f1,f2}\n")

    defn = parse_anim_script(script, root, db_root)
    container, _raw = assemble_pixel(defn, project_dir=None)

    assert container.nframes == 4 and container.ticks == [30] * 4
    # repeated names embed the same pixels twice (explicit sequence wins)
    assert container.blobs[0] == container.blobs[2]
    assert container.blobs[1] == container.blobs[3]


def test_assemble_pixel_dimension_mismatch_rejected(tmp_path, capsys):
    root = tmp_path / "assets"
    _make_png(root / "aniframe" / "anim" / "a.png", w=16, h=16)
    _make_png(root / "aniframe" / "anim" / "b.png", w=8, h=8)
    db_root = _make_db(tmp_path, "aniframe",
                       [("a", "png", "a.png"), ("b", "png", "b.png")])
    script = _make_script(
        tmp_path, "aniframe",
        "animaconf(fullscreen,pixel,aniframe)\n"
        "frame(0.5){a}\n"
        "frame(0.5){b}\n")

    defn = parse_anim_script(script, root, db_root)
    with pytest.raises(SystemExit) as ei:
        assemble_pixel(defn, project_dir=None)
    assert ei.value.code == 1
    assert "帧尺寸不一致" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Palette track: difference chain
# ---------------------------------------------------------------------------

def test_assemble_palette_chain_inheritance(tmp_path):
    root = tmp_path / "assets"
    anim_dir = root / "aniframe" / "anim"
    _make_png(anim_dir / "base.png", w=640, h=400)
    (anim_dir / "p1.pal").write_text(
        "# idx10 red, idx11 green\n10 255 0 0\n11 0 255 0\n", encoding="utf-8")
    (anim_dir / "p2.pal").write_text(
        "# idx20 blue only\n20 0 0 255\n", encoding="utf-8")
    db_root = _make_db(tmp_path, "aniframe", [
        ("base", "png", "base.png"),
        ("p1", "pal", "p1.pal"), ("p2", "pal", "p2.pal")])
    script = _make_script(
        tmp_path, "aniframe",
        "animaconf(fullscreen,palette,aniframe)\n"
        "base(){base}\n"
        "pal(0.1){p1}\n"
        "pal(0.1){p2}\n")

    defn = parse_anim_script(script, root, db_root)
    container, _raw = assemble_palette(defn, project_dir=None)

    assert (container.type, container.track) == (0, 1)
    assert container.nblob == 1 and container.nframes == 2
    assert container.ticks == [6, 6]
    t1, t2 = container.palettes
    assert len(t1) == len(t2) == ANI_PALETTE_BYTES

    # frame1 = base ⊕ pal001
    assert _entry(t1, 10) == (255, 0, 0)
    assert _entry(t1, 11) == (0, 255, 0)
    # frame2 inherits pal001 overrides and adds pal002
    assert _entry(t2, 10) == (255, 0, 0)
    assert _entry(t2, 11) == (0, 255, 0)
    assert _entry(t2, 20) == (0, 0, 255)
    # tables differ exactly at the newly overridden entry
    diff = {i for i in range(256) if _entry(t1, i) != _entry(t2, i)}
    assert diff == {20}

    r = parse_ani(build_ani(container))
    assert r.palettes == container.palettes
    assert r.palsz == 2 * ANI_PALETTE_BYTES
