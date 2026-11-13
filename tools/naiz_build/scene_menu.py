#!/usr/bin/env python3
"""Build-time scene-menu table generator.

The scene menu (core/engine/nb_scene_menu.c) shows one cell per scripted
scene that opts in via `sceneconf(){title, normal, onlist}`.  The engine has
no directory listing, so the eligible set is scanned here and frozen into
core/engine/nb_scene_menu.h.

Each entry also carries `unlock_id` — the numeric suffix of nbookNNN.nb.
The engine unlocks a scene when it loads it (devdoc 209) and the menu hides
entries whose unlock bit is clear, so the gallery only lists played scenes.
An onlist scene whose filename is not nbookNNN.nb cannot be tracked and is a
hard build error.

Thumbnail policy (first match wins, per the feature requirement):
  1. first `cg(){key}` in the scene -> the CG gallery thumbnail
     (`<cg>_t` produced by cg_thumb.py);
  2. else first `playanima(...){key}` -> frame 0 of the ANI container,
     re-rendered here at the scene-menu cell size and registered as THUMB;
  3. else thumb_id 0 -> the engine draws the title's first letter.

Pipeline position: after cg_thumb.build_cg_thumbs() and before
export_asset_table.py + pack_images(), so a freshly generated ANI thumbnail
is exported and packed like any other THUMB asset.

THUMB_W/THUMB_H/GRID_* are the contract with nb_scene_menu.c and are guarded
by tools/tests/test_scene_menu.py.
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from naiz_lib import PROTECTED_IDX_ALL, to_dos_name
from naiz_lib.anim_container import parse_ani
from naiz_lib.mag_codec import decode_mag_full
from naiz_lib.nb_line import parse_nb_line, next_field
from naiz_conv.mag_convert import convert_image, resize_to_screen

ROOT = Path(__file__).resolve().parent.parent.parent

# Grid geometry — mirrored by SCM_* in core/engine/nb_scene_menu.c.
THUMB_W = 160
THUMB_H = 100
GRID_COLS = 3
GRID_ROWS = 2
CELL_W = 180
CELL_H = 130

THUMB_SUFFIX = '_t'
THUMB_TYPE = 'THUMB'
THUMB_DIR = 'images'
HEADER_REL = 'core/engine/nb_scene_menu.h'
STATE_FILE = '.scene_menu_state.json'

MAX_DOS_BASENAME = 8

# Keep in sync with SCENE_TOTAL in core/engine/save.h (guarded by
# tools/tests/test_scene_menu.py).
SCENE_TOTAL = 100


def _split_sceneconf(raw: str):
    """Split one sceneconf segment into (title, type, list_flag).

    Uses nb_next_field semantics so an escaped comma in the title stays part
    of the title (rule §14.9).  A field without a trailing comma is the last
    field; the one-field form is a bare title.
    """
    title, rest = next_field(raw)
    if title is None:
        title, rest = raw.strip(), ''
    type_, rest2 = next_field(rest)
    if type_ is None:
        type_, rest2 = rest.strip(), ''
    return title, type_, rest2.strip()


def _scene_lines(path: Path):
    return path.read_text(encoding='utf-8', errors='replace').splitlines()


def _first_sceneconf(lines):
    for line in lines:
        parsed = parse_nb_line(line)
        if parsed and parsed.cmd == 'sceneconf' and parsed.text is not None:
            return _split_sceneconf(parsed.text)
    return None


def _first_brace_key(lines, cmd: str):
    """First `<cmd>(...){key}` key in the scene, or None."""
    for line in lines:
        parsed = parse_nb_line(line)
        if parsed and parsed.cmd == cmd:
            key = (parsed.text or '').strip()
            if not key and parsed.args:
                key = parsed.args[0]
            if key:
                return key
    return None


def _db_rows(db_path: Path, sql: str, params=()):
    db = sqlite3.connect(str(db_path))
    try:
        return list(db.execute(sql, params))
    finally:
        db.close()


def _upsert_thumb_row(db_path: Path, filename: str, name: str):
    db = sqlite3.connect(str(db_path))
    try:
        row = db.execute(
            "SELECT id, type, name FROM img_map WHERE filename=?", (filename,)
        ).fetchone()
        if row is None:
            db.execute("INSERT INTO img_map (filename, type, name) VALUES (?,?,?)",
                       (filename, THUMB_TYPE, name))
        elif row[1] != THUMB_TYPE or row[2] != name:
            db.execute("UPDATE img_map SET type=?, name=? WHERE filename=?",
                       (THUMB_TYPE, name, filename))
        db.commit()
        return db.execute("SELECT id FROM img_map WHERE filename=?",
                          (filename,)).fetchone()[0]
    finally:
        db.close()


def _taken_thumb_names(db_path: Path) -> set:
    """Short names already used by THUMB assets, so a new one cannot collide."""
    taken = set()
    for (filename,) in _db_rows(db_path,
                                "SELECT filename FROM img_map WHERE type='THUMB'"):
        short_base, short_ext = to_dos_name(Path(filename).name)
        short = (short_base.decode("ascii").strip() + "." +
                 short_ext.decode("ascii").strip())
        taken.add(short.upper())
    return taken


def _check_name(name: str, taken: set):
    """Enforce 8.3 and clash-free short names for a derived thumbnail."""
    if len(name) > MAX_DOS_BASENAME:
        raise RuntimeError(
            f"thumbnail name {name!r} is {len(name)} chars, over the "
            f"{MAX_DOS_BASENAME}-char 8.3 limit; shorten the source asset name")
    short_base, short_ext = to_dos_name(name + ".MAG")
    short = (short_base.decode("ascii").strip() + "." +
             short_ext.decode("ascii").strip())
    if short.upper() in taken:
        raise RuntimeError(
            f"thumbnail name {name!r} collides with {short!r} after DOS 8.3 "
            f"shortening; rename the source asset")
    taken.add(short.upper())


def _cg_thumb_id(db_path: Path, cg_key: str) -> int:
    row = _db_rows(db_path,
                   "SELECT filename FROM img_map WHERE type='CG' AND name=?",
                   (cg_key,))
    if not row:
        print(f"  WARN: scene menu: CG {cg_key!r} is not a registered CG asset")
        return 0
    cg_base = Path(row[0][0]).stem
    thumb_name = cg_base + THUMB_SUFFIX
    thumb_file = f"{THUMB_DIR}/{thumb_name}.MAG"
    row = _db_rows(db_path,
                   "SELECT id FROM img_map WHERE type='THUMB' AND filename=?",
                   (thumb_file,))
    if not row:
        print(f"  WARN: scene menu: CG {cg_key!r} has no thumbnail {thumb_file}; "
              f"falling back")
        return 0
    return int(row[0][0])


def _ani_thumb_id(db_path: Path, proj_dir: Path, ani_key: str, taken: set,
                  state: dict) -> int:
    row = _db_rows(db_path,
                   "SELECT filename FROM img_map WHERE type='ANI' AND name=?",
                   (ani_key,))
    if not row:
        print(f"  WARN: scene menu: anim {ani_key!r} is not a registered ANI asset")
        return 0
    src_rel = row[0][0]
    ani_path = proj_dir / src_rel
    if not ani_path.is_file():
        print(f"  WARN: scene menu: ANI file missing: {ani_path}")
        return 0

    thumb_name = ani_key + THUMB_SUFFIX
    out_rel = f"{THUMB_DIR}/{thumb_name}.MAG"
    out_path = proj_dir / out_rel
    already = _db_rows(db_path,
                       "SELECT id FROM img_map WHERE type='THUMB' AND filename=?",
                       (out_rel,))
    if not already:
        _check_name(thumb_name, taken)

    sig = {"src_mtime": ani_path.stat().st_mtime, "size": [THUMB_W, THUMB_H]}
    if out_path.exists() and state.get(out_rel) == sig:
        print(f"  [场景缩略图] 已是最新: {out_rel}")
        return _upsert_thumb_row(db_path, out_rel, thumb_name)

    try:
        container = parse_ani(ani_path.read_bytes())
    except (ValueError, OSError) as exc:
        print(f"  WARN: scene menu: cannot parse {src_rel}: {exc}; falling back")
        return 0
    if not container.blobs:
        print(f"  WARN: scene menu: {src_rel} has no blobs; falling back")
        return 0

    decoded = decode_mag_full(container.blobs[0])
    if decoded is None:
        print(f"  WARN: scene menu: {src_rel} frame 0 is not a valid MAG; falling back")
        return 0
    pixels, width, height, palette, _bpp, _is_sprite = decoded

    pal = []
    for rgb in palette[:256]:
        pal.extend(rgb)
    pal.extend([0] * (256 * 3 - len(pal)))
    img = Image.frombytes('P', (width, height), bytes(pixels))
    img.putpalette(pal)
    img = img.convert('RGB')

    resized = resize_to_screen(img, width=THUMB_W, height=THUMB_H, cover=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(convert_image(resized, no_resize=True,
                                       reserved=PROTECTED_IDX_ALL))
    thumb_id = _upsert_thumb_row(db_path, out_rel, thumb_name)
    state[out_rel] = sig
    print(f"  [场景缩略图] {ani_key} -> {out_rel} ({THUMB_W}x{THUMB_H})")
    return thumb_id


def _scene_dos_name(path: Path) -> str:
    """Validate the 8.3 form, then return the original name for the engine.

    The table stores exactly what scripts write (e.g. "nbook005.nb"); the
    check only rejects names that would be silently truncated on pack.
    """
    short_base, short_ext = to_dos_name(path.name)
    base = short_base.decode('ascii').strip()
    ext = short_ext.decode('ascii').strip()
    if base.upper() != path.stem.upper() or \
            ext.upper() != path.suffix.lstrip('.').upper():
        raise RuntimeError(
            f"scene file {path.name!r} is not 8.3-safe (shortens to "
            f"{base}.{ext}); rename the scene file")
    return path.name


def _scene_unlock_id(path: Path) -> int:
    """Story-scene id (1..SCENE_TOTAL) from the nbookNNN.nb filename.

    The gallery hides scenes until they have been played, and the unlock bit
    is indexed by this id, so an onlist scene without a valid id would be
    permanently invisible.  Fail loudly instead of guessing.
    """
    match = re.fullmatch(r'nbook(\d+)', path.stem, re.IGNORECASE)
    if not match:
        raise RuntimeError(
            f"scene file {path.name!r} is onlist but not named nbookNNN.nb; "
            f"the scene menu needs its numeric unlock id")
    scene_id = int(match.group(1))
    if not 1 <= scene_id <= SCENE_TOTAL:
        raise RuntimeError(
            f"scene file {path.name!r} has unlock id {scene_id}, outside "
            f"1..{SCENE_TOTAL} (SCENE_TOTAL in core/engine/save.h)")
    return scene_id


def _render_header(entries) -> str:
    count = len(entries)
    rows = ''.join(
        f'    {{ "{scene}", "{title}", {thumb_id}, {unlock_id} }},\n'
        for scene, title, thumb_id, unlock_id in entries)
    return (
        "/* Generated by tools/naiz_build/scene_menu.py — do not edit.\n"
        " * Source: projects/<game>/scene/*.nb sceneconf(){title, normal, onlist}.\n"
        " * thumb_id 0 means the engine draws the title's first letter.\n"
        " * unlock_id is the nbookNNN.nb numeric suffix (1..SCENE_TOTAL). */\n"
        "#ifndef NB_SCENE_MENU_H\n"
        "#define NB_SCENE_MENU_H\n\n"
        f"#define SCENE_MENU_COUNT {count}\n\n"
        "typedef struct {\n"
        "    const char *scene;\n"
        "    const char *title;\n"
        "    unsigned short thumb_id;\n"
        "    unsigned char unlock_id;\n"
        "} SceneMenuEntry;\n\n"
        "static const SceneMenuEntry\n"
        "    scene_menu_entries[SCENE_MENU_COUNT > 0 ? SCENE_MENU_COUNT : 1] = {\n"
        f"{rows}"
        "};\n\n"
        "#endif /* NB_SCENE_MENU_H */\n"
    )


def build_scene_menu(proj_dir: Path, scene_dir: Path, asset_dirs=(),
                     header_path=None) -> int:
    """Scan scene scripts, build missing ANI thumbnails, write the C table.

    header_path overrides the generated header location (tests point it at a
    temp dir so they never clobber the real core/engine/nb_scene_menu.h).
    """
    proj_dir = Path(proj_dir)
    scene_dir = Path(scene_dir)
    db_path = proj_dir / 'ASSETS.DB'
    if not db_path.is_file():
        raise RuntimeError(f"ASSETS.DB not found: {db_path}")

    state_path = proj_dir / STATE_FILE
    try:
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
    except (OSError, ValueError):
        state = {}

    taken = _taken_thumb_names(db_path)
    entries = []
    for scene_path in sorted(scene_dir.glob('*.nb'), key=lambda p: p.name):
        lines = _scene_lines(scene_path)
        conf = _first_sceneconf(lines)
        if conf is None:
            continue
        title, type_, list_flag = conf
        if type_ not in ('', 'normal'):
            continue
        if list_flag != 'onlist':
            continue

        thumb_id = 0
        cg_key = _first_brace_key(lines, 'cg')
        ani_key = _first_brace_key(lines, 'playanima')
        if cg_key:
            thumb_id = _cg_thumb_id(db_path, cg_key)
        if thumb_id == 0 and ani_key:
            thumb_id = _ani_thumb_id(db_path, proj_dir, ani_key, taken, state)

        entries.append((_scene_dos_name(scene_path), title, thumb_id,
                        _scene_unlock_id(scene_path)))

    try:
        state_path.write_text(json.dumps(state, indent=1))
    except OSError as exc:
        print(f"  WARN: could not write scene menu state {state_path}: {exc}")

    header_path = Path(header_path) if header_path is not None else ROOT / HEADER_REL
    rendered = _render_header(entries)
    if header_path.exists() and header_path.read_text(encoding='utf-8') == rendered:
        print(f"  [场景菜单] 已是最新: {HEADER_REL} ({len(entries)} 项)")
    else:
        header_path.write_text(rendered, encoding='utf-8')
        print(f"  [场景菜单] 生成 {HEADER_REL} ({len(entries)} 项)")
    return len(entries)
