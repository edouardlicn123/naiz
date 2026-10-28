"""char(hideall) batch contract (devdoc 182).

The old layer_sprite_hide_all() called layer_sprite_sync_dialog_base() once
PER active sprite.  Each sync pays an occluder reset (55 KB memcpy + marks
the devdoc-181 clean-box cache dirty), then layer_dialog_recompose() --
a clean-box rebuild (55,200-iteration paint loop) + page text + a 55 KB
throwaway memcpy + a 55 KB VRAM write.  With the dialog open and N sprites
on stage, char(hideall) ran that whole pipeline N times inside ONE frame
(a 150-300 ms pause reported on scene 001).

The fix: restore every background rect and deactivate first, then sync the
dialog base exactly once -- identical final pixels, one pipeline.  The
per-sprite helper is gone; any future hide-by-id must batch the same way.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SPRITE = ROOT / "core" / "engine" / "layer_sprite.c"


def test_hideall_syncs_the_dialog_base_once():
    """layer_sprite_hide_all() must contain exactly one
    layer_sprite_sync_dialog_base() call, guarded so an empty stage skips it
    entirely."""
    src = SPRITE.read_text(encoding="utf-8")
    m = re.search(r"\bvoid layer_sprite_hide_all\(void\)\n\{", src)
    assert m, "layer_sprite_hide_all must exist"
    depth, i = 0, src.index("{", m.start())
    body = None
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                body = src[i:j + 1]
                break
    assert body, "unbalanced braces in layer_sprite_hide_all"
    n = body.count("layer_sprite_sync_dialog_base()")
    assert n == 1, (
        f"hide_all calls sync_dialog_base {n} times -- it must run exactly "
        f"once after the whole sweep (N x sync is the char(hideall) pause)")
    assert "if (hidden)" in body, (
        "an empty stage must not pay the occluder/recompose pipeline")
    assert "layer_sprite_hide(" not in src, (
        "the per-sprite hide helper must stay deleted -- a per-sprite sync "
        "path is the regression this guard exists for")
