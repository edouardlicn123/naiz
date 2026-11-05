"""palette_utils: skin-tone detection, nearest-colour search, validation."""

import pytest

from naiz_lib import palette_utils
from naiz_lib.palette_utils import (
    MAGENTA_KEY,
    KEY_DIST_SQ,
    is_near_magenta,
    is_skin_tone,
    find_skin_entries,
    warm_skin_tone,
    nearest_color_index,
    colour_distance,
    validate_skin_palette,
)


# ---------------------------------------------------------------------------
# is_near_magenta
# ---------------------------------------------------------------------------

def test_exact_magenta_is_near():
    assert is_near_magenta(*MAGENTA_KEY)


def test_far_color_is_not_near():
    assert not is_near_magenta(0, 0, 0)


def test_custom_threshold():
    assert is_near_magenta(255, 0, 254, threshold_sq=4)
    assert not is_near_magenta(255, 0, 254, threshold_sq=1)


# ---------------------------------------------------------------------------
# is_skin_tone
# ---------------------------------------------------------------------------

def test_skin_tone_detection():
    # A prototypical warm skin tone (r>200, 160<g<245, 120<b<220, g<r)
    assert is_skin_tone(220, 180, 160)


def test_skin_tone_boundaries_excluded():
    # Strict comparisons: r==200 is NOT a skin tone
    assert not is_skin_tone(200, 180, 160)
    # g must be strictly < r
    assert not is_skin_tone(220, 220, 160)


def test_greater_than_r_excluded():
    assert not is_skin_tone(160, 180, 160)


# ---------------------------------------------------------------------------
# find_skin_entries / warm_skin_tone
# ---------------------------------------------------------------------------

def test_find_skin_entries():
    palette = [
        (220, 180, 160),   # 0: skin
        (0, 0, 0),         # 1: black
        (255, 0, 255),     # 2: magenta key
        (210, 170, 150),   # 3: skin
    ]
    assert find_skin_entries(palette) == [0, 3]


def test_warm_skin_tone_warms_skin_only():
    warm = warm_skin_tone(220, 180, 160)
    assert warm == (min(255, 220 + palette_utils.SKIN_WARM_R_OFFSET),
                    180 + palette_utils.SKIN_WARM_G_DELTA,
                    160)
    assert warm[0] > 220
    assert warm[1] < 180


def test_warm_skin_tone_non_skin_unchanged():
    assert warm_skin_tone(0, 0, 0) == (0, 0, 0)


def test_warm_skin_tone_clamps_255():
    assert warm_skin_tone(253, 170, 150)[0] == 255


# ---------------------------------------------------------------------------
# nearest_color_index
# ---------------------------------------------------------------------------

def test_nearest_color_index_exact():
    pal = [(0, 0, 0), (255, 0, 0), (0, 255, 0)]
    assert nearest_color_index(pal, 255, 2, 2) == 1


def test_nearest_color_index_skip_protected():
    pal = [(0, 0, 0), (255, 0, 0), (0, 255, 0)]
    assert nearest_color_index(pal, 255, 0, 0, skip={1}) == 0


def test_nearest_color_index_empty_returns_0():
    assert nearest_color_index([(0, 0, 0)], 10, 10, 10) == 0


# ---------------------------------------------------------------------------
# colour_distance
# ---------------------------------------------------------------------------

def test_colour_distance_zero():
    assert colour_distance((1, 2, 3), (1, 2, 3)) == 0.0


def test_colour_distance_diagonal():
    d = colour_distance((0, 0, 0), (3, 4, 0))
    assert d == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# validate_skin_palette
# ---------------------------------------------------------------------------

def _shared_containing_skin():
    pal = [(0, 0, 0)] * 256
    pal[5] = (220, 180, 160)
    return pal


def test_validate_skin_palette_no_warnings_when_match():
    shared = _shared_containing_skin()
    src = [(0, 0, 0)] * 256
    src[0] = (220, 180, 160)
    warnings = validate_skin_palette(shared, [src])
    assert warnings == []


def test_validate_skin_palette_warns_on_mismatch():
    shared = [(0, 0, 0)] * 256
    src = [(0, 0, 0)] * 256
    src[0] = (220, 180, 160)
    # Shared has no skin entry near the source -> ΔE warning
    warnings = validate_skin_palette(shared, [src])
    assert warnings, "expected a ΔE warning when shared palette has no skin match"
