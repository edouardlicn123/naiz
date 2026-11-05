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
    m = re.search(r"\bvoid layer_sprite_hide_all_ex\(int recompose\)\n\{", src)
    assert m, "layer_sprite_hide_all_ex must exist"
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
        f"hide_all_ex calls sync_dialog_base {n} times -- it must run exactly "
        f"once after the whole sweep (N x sync is the char(hideall) pause)")
    assert "if (hidden && recompose)" in body, (
        "the sync must be skippable (recompose=0) and skipped on an empty stage")
    assert "layer_sprite_hide(" not in src, (
        "the per-sprite hide helper must stay deleted -- a per-sprite sync "
        "path is the regression this guard exists for")
    wrapper = re.search(r"\bvoid layer_sprite_hide_all\(void\)\n\{([^}]*)\}", src)
    assert wrapper and "layer_sprite_hide_all_ex(1)" in wrapper.group(1), (
        "the plain hide_all wrapper must keep the recompose (scene reset path)")


def test_cmd_char_hideall_skips_the_recompose_it_overwrites():
    """devdoc 183: cmd_char(hideall) runs layer_sprite_hide_all_ex(0) before
    layer_dialog_hide() -- the dialog rect restore overwrites the recomposed
    pixels on the same frame, so paying the occluder+recompose pipeline would
    be pure waste."""
    nbcmd = (ROOT / "core" / "engine" / "nb_commands.c").read_text(encoding="utf-8")
    i = nbcmd.index('"hideall"')
    block = nbcmd[i:nbcmd.index("return;", i)]
    assert "layer_sprite_hide_all_ex(0)" in block, (
        "char(hideall) must suppress the recompose (it is overwritten by the "
        "dialog rect restore on the same frame)")
    assert "layer_dialog_hide()" in block, (
        "char(hideall) must still close the dialog")
