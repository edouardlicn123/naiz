#!/usr/bin/env python3
"""Build-time CG thumbnail generator for the gallery grid.

The gallery grid (core/engine/nb_cggallery.c) blits one small image per
unlocked cell.  The engine has no scaling primitive, so each thumbnail is
pre-rendered here at exactly one cell size and packed as an ordinary MAG.

Pipeline position: runs after convert_png_to_mag() and before
export_asset_table.py + pack_images(), so the generated assets are both
exported to the C header and packed into IMAGE.DAT.

Pixel size is the contract with the engine: THUMB_W/THUMB_H must equal
GAL_CELL_W/GAL_CELL_H in nb_cggallery.c (tools/tests/test_cg_thumb_size.py
guards the pair).
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from naiz_lib import PROTECTED_IDX_ALL, to_dos_name
from naiz_conv.mag_convert import convert_image, resize_to_screen

# One cell in the gallery grid — must mirror GAL_CELL_W / GAL_CELL_H.
THUMB_W = 144
THUMB_H = 84

# Thumbnail asset name = CG name + suffix.  Kept short and shared with
# export_asset_table.py, which joins cg_map[] to cg_thumb_map[] by name.
THUMB_SUFFIX = '_t'
THUMB_TYPE = 'THUMB'
THUMB_DIR = 'images'
STATE_FILE = '.cg_thumb_state.json'

# DOS 8.3: runtime-injected files are packed into IMAGE.DAT rather than
# shipped as loose files, but the project's naming rule is enforced anyway so
# a long CG name fails loudly at build time instead of silently.
MAX_DOS_BASENAME = 8


def _read_images_map(asset_dir: Path):
    """Map MAG basename -> source PNG path for one images.map file."""
    map_file = asset_dir / "images.map"
    if not map_file.exists():
        return {}
    out = {}
    for line in map_file.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        png_rel, mag_rel = parts[0], parts[1]
        out[Path(mag_rel).name] = asset_dir / png_rel
    return out


def _cg_rows(db_path: Path):
    """Registered CG assets ordered by id — the order cg_map[] is generated in."""
    db = sqlite3.connect(str(db_path))
    try:
        return list(db.execute(
            "SELECT id, filename, name FROM img_map WHERE type='CG' ORDER BY id"))
    finally:
        db.close()


def _upsert_thumb_row(db_path: Path, filename: str, name: str):
    """Register the thumbnail as type='THUMB' (id order mirrors cg_map)."""
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
    finally:
        db.close()


def _check_name(name: str, taken: set):
    """Enforce 8.3 and uniqueness for the derived thumbnail name."""
    if len(name) > MAX_DOS_BASENAME:
        raise RuntimeError(
            f"CG thumbnail name {name!r} is {len(name)} chars, over the "
            f"{MAX_DOS_BASENAME}-char 8.3 limit; rename the CG asset or change "
            f"THUMB_SUFFIX")
    short_base, short_ext = to_dos_name(name + ".MAG")
    short = (short_base.decode("ascii").strip() + "." +
             short_ext.decode("ascii").strip())
    if short.upper() in taken:
        raise RuntimeError(
            f"CG thumbnail name {name!r} collides with {short!r} after DOS "
            f"8.3 shortening; rename the CG asset")
    taken.add(short.upper())


def build_cg_thumbs(proj_dir: Path, asset_dirs):
    """Generate one gallery thumbnail per registered CG asset.

    proj_dir:   the project tree holding ASSETS.DB and images/
    asset_dirs: directories holding images.map (project + assets/common);
                searched in order for each CG's source PNG
    """
    db_path = proj_dir / "ASSETS.DB"
    if not db_path.is_file():
        raise RuntimeError(f"ASSETS.DB not found: {db_path}")

    cg_rows = _cg_rows(db_path)
    if not cg_rows:
        print("  [CG缩略图] 无 CG 资源，跳过")
        return

    # Later dirs win: build_game.py passes the shared assets/common first and
    # the project tree last, so a project-local entry overrides a common one.
    sources = {}
    for asset_dir in asset_dirs:
        sources.update(_read_images_map(asset_dir))

    state_path = proj_dir / STATE_FILE
    try:
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
    except (OSError, ValueError):
        state = {}

    taken = set()
    for _cg_id, filename, name in cg_rows:
        thumb_name = name + THUMB_SUFFIX
        _check_name(thumb_name, taken)

    out_dir = proj_dir / THUMB_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    from PIL import Image

    built = 0
    skipped = 0
    for _cg_id, filename, name in cg_rows:
        thumb_name = name + THUMB_SUFFIX
        png_src = sources.get(Path(filename).name)
        if png_src is None or not png_src.exists():
            raise RuntimeError(
                f"CG {name!r} ({filename}) has no source PNG in any images.map; "
                f"add it so the gallery thumbnail can be generated")
        out_rel = f"{THUMB_DIR}/{thumb_name}.MAG"
        out_path = proj_dir / out_rel
        sig = {
            "png_mtime": png_src.stat().st_mtime,
            "size": [THUMB_W, THUMB_H],
        }
        prev = state.get(out_rel)
        if out_path.exists() and prev == sig:
            print(f"  [CG缩略图] 已是最新: {out_rel}")
            skipped += 1
            continue

        with Image.open(png_src) as img:
            # cover: scale-to-fill + center-crop, so the cell shows artwork
            # edge to edge with no letterbox bars (same policy as --cover).
            resized = resize_to_screen(img.convert("RGB"),
                                       width=THUMB_W, height=THUMB_H, cover=True)
            mag_data = convert_image(resized, no_resize=True,
                                     reserved=PROTECTED_IDX_ALL)
        out_path.write_bytes(mag_data)
        _upsert_thumb_row(db_path, out_rel, thumb_name)
        state[out_rel] = sig
        print(f"  [CG缩略图] {name} -> {out_rel} ({THUMB_W}x{THUMB_H})")
        built += 1

    try:
        state_path.write_text(json.dumps(state, indent=1))
    except OSError as e:
        print(f"  WARN: could not write thumbnail state {state_path}: {e}")

    print(f"  [CG缩略图] 完成: {built} 生成, {skipped} 跳过")
