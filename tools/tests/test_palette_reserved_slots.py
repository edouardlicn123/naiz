#!/usr/bin/env python3
"""Guard the engine-chrome palette slot range against artwork.

core/engine/image.c: image_set_palette() skips IMG_CHROME_PAL_FIRST..LAST
(248..255) for every image type, because that range is owned by the UI
subsystems (dialog fill, button fill/highlight/shadow, menu white/yellow,
cursor black, no-transparency sentinel) — see the owners listed in image.c.
tools/naiz_build/pack_images.py writes 248..255 as black placeholders.

That skip is only sound while no artwork pixel ever references those
indices: such a pixel would render with whatever chrome color its owner
last set instead of its own.  This test decodes every built project image
and asserts the maximum referenced index stays below the reserved range,
so the engine-side skip can never silently break an asset.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from naiz_lib import mag_codec  # noqa: E402

# First reserved (engine-chrome) index — must match IMG_CHROME_PAL_FIRST in
# core/engine/image.c.  Copied as a literal on purpose: the test guards the
# data side, and engine-side symmetry is checked by
# test_reserved_range_matches_engine.
CHROME_FIRST = 248
CHROME_LAST = 255

IMAGE_SRC = ROOT / "core" / "engine" / "image.c"

MAG_SUFFIXES = {".mag"}


def _project_images():
    projects = sorted(p for p in (ROOT / "projects").iterdir() if p.is_dir())
    if not projects:
        pytest.skip("no projects directory")
    out = []
    for proj in projects:
        img_dir = proj / "images"
        if not img_dir.is_dir():
            continue
        for mag in sorted(img_dir.iterdir()):
            if mag.suffix.lower() in MAG_SUFFIXES:
                out.append(mag)
    if not out:
        pytest.skip("no built project images found (run makegame.sh build first)")
    return out


@pytest.mark.parametrize("mag_path", _project_images(),
                         ids=lambda p: f"{p.parts[-3]}/{p.name}")
def test_artwork_never_references_reserved_slots(mag_path):
    decoded = mag_codec.decode_mag_full(mag_path.read_bytes())
    if decoded is None:
        pytest.skip(f"{mag_path.name} is not a decodable MAG")
    pixels, _w, _h, _pal, _bpp, _is_sprite = decoded
    if not pixels:
        pytest.fail(f"{mag_path.name} decoded to zero pixels")
    worst = max(pixels)
    assert worst < CHROME_FIRST, (
        f"{mag_path.name} references palette index {worst}, which is inside "
        f"the engine-chrome range {CHROME_FIRST}..{CHROME_LAST} that "
        f"image_set_palette() never applies")


def _engine_define(name):
    m = re.search(rf"^#define\s+{name}\s+(\d+)\b", IMAGE_SRC.read_text(),
                  re.MULTILINE)
    if not m:
        pytest.fail(f"{name} not found in image.c")
    return int(m.group(1))


def test_reserved_range_matches_engine():
    """The literal range above must match the engine's skip range, and the
    engine must skip the whole span for every image type (not just sprites).
    """
    if not IMAGE_SRC.is_file():
        pytest.skip(f"{IMAGE_SRC} not present")
    src = IMAGE_SRC.read_text()
    assert _engine_define("IMG_CHROME_PAL_FIRST") == CHROME_FIRST
    assert _engine_define("IMG_CHROME_PAL_LAST") == CHROME_LAST
    # The skip must be unconditional on image type: it may not sit behind
    # the is_sprite branch, or backgrounds would still repaint the chrome.
    guard = ("if (i >= IMG_CHROME_PAL_FIRST && i <= IMG_CHROME_PAL_LAST) "
             "continue;")
    if guard not in src:
        pytest.fail("image_set_palette() lost its unconditional chrome skip")
    if "is_sprite && (i >= IMG_CHROME_PAL_FIRST" in src:
        pytest.fail("chrome skip became sprite-only; backgrounds would "
                    "reclaim the engine palette slots")
