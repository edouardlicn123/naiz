"""Engine render/layer constants: C header / Python mirror consistency.

core/engine/render.h + scene_layers.h and tools/naiz_lib/__init__.py are a
documented C/Python mirror pair.  This test keeps them honest (see devdocs/0.1版开发文档总结.html#doc-38
stage 11.1 for the MAG mirror; this covers the engine constants).

Constants mirrored in naiz_lib/__init__.py:
  - render.h:       PAL_WHITE, PAL_TRANSPARENT, PAL_DIALOG_FILL,
                    LAYER_SCREEN_W, LAYER_SCREEN_H
  - scene_layers.h: LAYER_* / BTN_* / DIALOG_* layout + color indices
"""

import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RENDER_H = os.path.join(REPO_ROOT, "core", "engine", "render.h")
SCENE_LAYERS_H = os.path.join(REPO_ROOT, "core", "engine", "scene_layers.h")

from naiz_lib import (  # noqa: E402
    PAL_WHITE, PAL_TRANSPARENT, PAL_DIALOG_FILL,
    LAYER_SCREEN_W, LAYER_SCREEN_H,
    BTN_W, BTN_H, BTN_R, BTN_GAP, BTN_COL_GAP,
    BTN_FILL_IDX, BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX,
    DIALOG_X, DIALOG_Y, DIALOG_W, DIALOG_H,
    DIALOG_INDENT, DIALOG_RIGHT_INDENT, DIALOG_TEXT_Y,
    DIALOG_HEADER_Y, DIALOG_BORDER, DIALOG_BOTTOM,
    LAYER_SPRITE_W, LAYER_SPRITE_H, LAYER_MAX_SPRITES,
)

# name -> expected Python attribute
_MIRROR = {
    "PAL_WHITE": PAL_WHITE,
    "PAL_TRANSPARENT": PAL_TRANSPARENT,
    "PAL_DIALOG_FILL": PAL_DIALOG_FILL,
    "LAYER_SCREEN_W": LAYER_SCREEN_W,
    "LAYER_SCREEN_H": LAYER_SCREEN_H,
    "BTN_W": BTN_W,
    "BTN_H": BTN_H,
    "BTN_R": BTN_R,
    "BTN_GAP": BTN_GAP,
    "BTN_COL_GAP": BTN_COL_GAP,
    "BTN_FILL_IDX": BTN_FILL_IDX,
    "BTN_HIGHLIGHT_IDX": BTN_HIGHLIGHT_IDX,
    "BTN_SHADOW_IDX": BTN_SHADOW_IDX,
    "LAYER_DIALOG_X": DIALOG_X,
    "LAYER_DIALOG_Y": DIALOG_Y,
    "LAYER_DIALOG_W": DIALOG_W,
    "LAYER_DIALOG_H": DIALOG_H,
    "LAYER_DIALOG_BORDER": DIALOG_BORDER,
    "LAYER_DIALOG_INDENT": DIALOG_INDENT,
    "LAYER_DIALOG_RIGHT_INDENT": DIALOG_RIGHT_INDENT,
    "LAYER_DIALOG_TEXT_Y": DIALOG_TEXT_Y,
    "LAYER_DIALOG_HEADER_Y": DIALOG_HEADER_Y,
    "LAYER_SPRITE_W": LAYER_SPRITE_W,
    "LAYER_SPRITE_H": LAYER_SPRITE_H,
    "LAYER_MAX_SPRITES": LAYER_MAX_SPRITES,
}


def _parse_defines(path, prefix):
    """Parse #define NAME <int> lines with the given name prefix."""
    defines = {}
    if not os.path.exists(path):
        return defines
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"#define\s+(" + prefix + r"\w+)\s+(\d+)", line)
            if m:
                defines[m.group(1)] = int(m.group(2))
    return defines


def test_c_headers_define_all_mirrored_constants():
    render = _parse_defines(RENDER_H, r"(?:PAL_|LAYER_)")
    scene = _parse_defines(SCENE_LAYERS_H, r"(?:LAYER_|BTN_)")
    c_defs = dict(render)
    c_defs.update(scene)

    for name, py_value in _MIRROR.items():
        assert name in c_defs, (
            f"C header missing {name} (Python mirror has {py_value})"
        )


def test_mirror_values_match_c():
    render = _parse_defines(RENDER_H, r"(?:PAL_|LAYER_)")
    scene = _parse_defines(SCENE_LAYERS_H, r"(?:LAYER_|BTN_)")
    c_defs = dict(render)
    c_defs.update(scene)

    for name, py_value in _MIRROR.items():
        assert c_defs[name] == py_value, (
            f"Mirror mismatch for {name}: C={c_defs[name]} Python={py_value}"
        )


def test_protected_index_set():
    from naiz_lib import PROTECTED_IDX_ALL
    # Reserved engine indices must include the dialog/button fill indices.
    assert PAL_WHITE in PROTECTED_IDX_ALL
    assert PAL_TRANSPARENT in PROTECTED_IDX_ALL
    assert BTN_FILL_IDX in PROTECTED_IDX_ALL
    assert BTN_HIGHLIGHT_IDX in PROTECTED_IDX_ALL
    assert BTN_SHADOW_IDX in PROTECTED_IDX_ALL


def test_dialog_bottom_derived():
    assert DIALOG_BOTTOM == DIALOG_Y + DIALOG_H - DIALOG_BORDER
