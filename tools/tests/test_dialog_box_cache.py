"""Dialog clean-box cache contract (devdoc 181).

The residual "text switch" stutter: a page turn and every typewriter reveal
frame re-ran the dialog composite prologue -- dialog_seed_base() memcpy plus
dialog_paint_box()'s 55,200-iteration per-pixel fill loop (~10-30 ms on the
emulated CPU) -- even though the box is pixel-identical between pages.  Only
the occluder underneath (sprites moved / background changed) and the dialog
style change the box pixels; the palette is resolved at VRAM write time and
never invalidates.

The cache: dialog_box_base (480xLAYER_DIALOG_H heap buffer) holds the
occluder-seeded, box-painted, text-free composite.  Every render publishes it
with one memcpy; it is rebuilt only when dialog_box_base_dirty is set by
dialog_occluder_reset_base() or dlg_set_style().
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LAYER_DIALOG = ROOT / "core" / "engine" / "layer_dialog.c"


def _src():
    return LAYER_DIALOG.read_text(encoding="utf-8")


def _func_body(src, name):
    m = re.search(r"\b" + name + r"\([^)]*\)\n\{", src)
    assert m, f"function {name} not found"
    depth, i = 0, src.index("{", m.start())
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    return src[i:]


def test_box_cache_exists_and_renders_use_one_memcpy():
    """The clean-box base must exist, and layer_dialog_show /
    layer_dialog_render_page / layer_dialog_recompose must publish it via
    dialog_box_base_sync() instead of seeding + painting per render."""
    src = _src()
    assert "static unsigned char *dialog_box_base" in src, (
        "the clean-box cache buffer must exist")
    for fn in ("layer_dialog_show", "layer_dialog_render_page",
               "layer_dialog_recompose"):
        body = _func_body(src, fn)
        assert "dialog_box_base_sync()" in body, (
            f"{fn} must go through the clean-box cache")
        assert "dialog_paint_box(dialog_layer" not in body, (
            f"{fn} must not re-run the box paint loop into the composite per "
            f"render (the OOM-degraded dialog_paint_box(NULL, 0) VRAM path "
            f"may stay)")
    sync = _func_body(src, "dialog_box_base_sync")
    assert "dialog_paint_box(" in sync, (
        "the paint loop must run only inside the cache rebuild")
    assert "memcpy(dialog_layer, dialog_box_base" in sync, (
        "a clean render must publish the cached base with one memcpy")


def test_cache_invalidated_by_occluder_and_style_changes():
    """The cached box pixels change only when the underneath changes
    (dialog_occluder_reset_base) or the fill pattern changes (dlg_set_style).
    Both must mark the cache dirty; palette updates must not (indices are
    resolved at VRAM write time)."""
    src = _src()
    reset = _func_body(src, "dialog_occluder_reset_base")
    style = _func_body(src, "dlg_set_style")
    assert "dialog_box_base_dirty = 1" in reset, (
        "an occluder re-base must invalidate the clean-box cache")
    assert "dialog_box_base_dirty = 1" in style, (
        "a dialog style change must invalidate the clean-box cache")
    pal = _func_body(src, "dlg_update_palette")
    assert "dialog_box_base_dirty" not in pal, (
        "palette updates must not invalidate the index-based cache")
    reset_fn = _func_body(src, "layer_dialog_reset")
    assert "free(dialog_box_base)" in reset_fn, (
        "a full reset must free the cache buffer")
