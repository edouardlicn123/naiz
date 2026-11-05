#!/usr/bin/env python3
"""Guard the CG thumbnail pixel size against the engine gallery cell size.

tools/naiz_build/cg_thumb.py generates thumbnails at THUMB_W x THUMB_H and
core/engine/nb_cggallery.c blits them into GAL_CELL_W x GAL_CELL_H cells with
no scaling.  A mismatch would blit a mis-sized image, so the duplicated
constant pair is asserted equal here.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from naiz_build.cg_thumb import THUMB_H, THUMB_W  # noqa: E402

GALLERY_SRC = ROOT / "core" / "engine" / "nb_cggallery.c"


def _gallery_define(name):
    if not GALLERY_SRC.is_file():
        pytest.skip(f"{GALLERY_SRC} not present")
    m = re.search(rf"^#define\s+{name}\s+(\d+)\b", GALLERY_SRC.read_text(),
                  re.MULTILINE)
    if not m:
        pytest.fail(f"{name} not found in {GALLERY_SRC.name}")
    return int(m.group(1))


def test_thumb_width_matches_cell_width():
    assert THUMB_W == _gallery_define("GAL_CELL_W")


def test_thumb_height_matches_cell_height():
    assert THUMB_H == _gallery_define("GAL_CELL_H")


def test_grid_clears_page_nav_arrow_band():
    """The grid must end above the page-nav arrow strip, or the footer erase
    in menu_pagenav_draw would cut into the last cell row."""
    arrows_y = _gallery_define("GAL_ARROWS_Y")
    origin_y = _gallery_define("GAL_ORIGIN_Y")
    step_y = _gallery_define("GAL_STEP_Y")
    cell_h = _gallery_define("GAL_CELL_H")
    rows = _gallery_define("GAL_ROWS")
    grid_bottom = origin_y + (rows - 1) * step_y + cell_h
    assert grid_bottom < arrows_y, (
        f"grid bottom {grid_bottom} overlaps arrow band at y={arrows_y}")


def test_footer_below_grid_in_order():
    """Back button must sit below the page-nav arrows, not on top of them."""
    assert _gallery_define("GAL_ARROWS_Y") < _gallery_define("GAL_COUNT_Y")
    assert _gallery_define("GAL_COUNT_Y") < _gallery_define("GAL_BACK_Y")
