"""Software cursor layer contract guard (devdoc 108 / plan for 0.2.135).

Bug root cause (devdoc 108): the cursor is a VRAM save/restore overlay
(cursor_draw stores a 24x24 background snapshot, cursor_erase restores it).
dialog_layer_blit() wrote the 480x115 dialog composite straight to VRAM
without invalidating a cursor parked over the text: the blit clobbered the
cursor shape, the steady-position early-return (cursor_render) stopped
redrawing it, and the next mouse move restored the STALE pre-update
snapshot over the freshly revealed characters — "the mouse erases the
subtitle text".

The fix elevates the save/restore overlay to a real SOFTWARE CURSOR LAYER:
a layer contract where every VRAM writer must first report its write
rectangle via hal_mouse_touch_cursor(x,y,w,h) — or the stronger
un-bounded hal_mouse_invalidate_cursor() — BEFORE writing.  touch() erases
+ invalidates the cursor only when its 24x24 region overlaps the reported
rect (four-way intersection); non-overlapping writes are no-ops, so the
dialog/reveal hot path only pays while the pointer sits inside the written
region.  This freezes the bug: no VRAM writer may reach the cursor region
silently, and any re-introduced un-touched dialog write path fails here.

These tests parse the C sources (mirrors test_reveal_final_page.py /
test_cmd_meta.py); a regression that drops a touch/invalidate from a dialog
or menu-layer VRAM write, weakens the overlap test, or removes the HAL
forwarding fails here.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LAYER_DIALOG_C = ROOT / "core" / "engine" / "layer_dialog.c"
MENU_LAYER_C = ROOT / "core" / "engine" / "menu_layer.c"
CURSOR_C = ROOT / "core" / "engine" / "cursor.c"
HAL_MOUSE_C = ROOT / "core" / "plat" / "hal_mouse.c"

DIALOG_TOUCH = "hal_mouse_touch_cursor_opaque(LAYER_DIALOG_X, LAYER_DIALOG_Y,\n"
DIALOG_TOUCH_INLINE = "hal_mouse_touch_cursor_opaque(LAYER_DIALOG_X, LAYER_DIALOG_Y,"


def _func_body(path, name):
    src = path.read_text(encoding="utf-8")
    m = re.search(r"(?:^|\n)[ \t\w\*]*\b" + re.escape(name) +
                  r"\s*\([^)]*\)\s*\n?\{", src)
    assert m, f"{path.name}: function {name}() not found"
    start = src.index("{", m.start())
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError(f"{path.name}: unbalanced braces in {name}()")


# --- 1. The bug stand: dialog_layer_blit() must touch the dialog rect
#      BEFORE its vram_write (the sole composite -> VRAM funnel). ------


def test_dialog_layer_blit_touches_before_vram_write():
    body = _func_body(LAYER_DIALOG_C, "dialog_layer_blit")
    assert DIALOG_TOUCH_INLINE in body, (
        "dialog_layer_blit() must report the full dialog rect to the cursor "
        "layer via the OPAQUE touch (hal_mouse_touch_cursor_opaque("
        "LAYER_DIALOG_X, LAYER_DIALOG_Y, LAYER_DIALOG_W, LAYER_DIALOG_H)) "
        "before its vram_write — the composite is pixel-for-pixel opaque over "
        "the whole rect, so the layer may skip the erase + redraw immediately "
        "without a VBLANK gate (devdoc 108 + 109)")
    assert "vram_write" in body
    assert body.index("hal_mouse_touch_cursor") < body.index("vram_write"), (
        "the cursor-layer touch must precede the vram_write, else the blit "
        "clobbers the cursor and its saved background goes stale (devdoc 108)")


# --- 2. Every direct-VRAM dialog write path keeps the contract. --------


def test_dialog_direct_vram_paths_keep_the_contract():
    # OOM degraded paths write straight to VRAM (no composite buffer).
    show = _func_body(LAYER_DIALOG_C, "layer_dialog_show")
    page = _func_body(LAYER_DIALOG_C, "layer_dialog_render_page")
    assert "hal_mouse_touch_cursor(LAYER_DIALOG_X, LAYER_DIALOG_Y," in show, (
        "layer_dialog_show() OOM path writes the box straight to VRAM — "
        "must touch the dialog rect first (devdoc 108)")
    assert "hal_mouse_touch_cursor(LAYER_DIALOG_X, LAYER_DIALOG_Y," in page, (
        "layer_dialog_render_page() OOM path writes text straight to VRAM — "
        "must touch the dialog rect first (devdoc 108)")

    bg = _func_body(LAYER_DIALOG_C, "fill_dialog_bg")
    assert "hal_mouse_touch_cursor(x, y, w, h)" in bg, (
        "fill_dialog_bg() writes the dialog fill to VRAM (e.g. the save/load "
        "slot grid) — must touch its own rect first (devdoc 108)")

    # layer_dialog_hide() may keep the stronger un-bounded form.
    hide = _func_body(LAYER_DIALOG_C, "layer_dialog_hide")
    assert "hal_mouse_invalidate_cursor" in hide or \
           "hal_mouse_touch_cursor(LAYER_DIALOG_X, LAYER_DIALOG_Y," in hide


# --- 3. cursor_touch() must implement the four-way overlap test and be a
#        no-op for non-overlapping writes (overlap decides, not the caller).
# -----------------------------------------------------------------------


def test_cursor_touch_overlap_guard():
    src = CURSOR_C.read_text(encoding="utf-8")
    body = _func_body(CURSOR_C, "cursor_touch")
    assert len(body) <= 500, (
        "cursor_touch must stay a small overlap guard (erase only on "
        "overlap); bloating it would tempt shortcuts")
    assert "cursor_overlap_rect" in body or "x < bg->x" in body, (
        "cursor_touch must delegate to / inline a four-way overlap test — "
        "it may not erase unconditionally (that would turn every non-"
        "overlapping dialog write into a flicker, devdoc 108)")
    assert "cursor_erase" in body, (
        "an overlapping touch must erase the saved cursor (restore its still-"
        "current background) and invalidate, so cursor_render re-captures "
        "the fresh content (devdoc 108)")
    assert "valid = 0" in body, (
        "an overlapping touch must invalidate the saved state")
    # The four-way intersection lives with the layer (file-level) — edges
    # both ways so a corner overlap can't slip through to erase=off-path.
    assert "bg->x < x + w" in src and "bg->y < y + h" in src, (
        "the overlap test must compare both axes (the write rect's far edge "
        "against the cursor's near edge) — a one-sided test resurrects the "
        "stale-background erase on corner overlaps (devdoc 108)")


# --- 3b. Opaque touch (devdoc 109): full coverage skips the erase; partial /
#         transparent writers must never reach it. -------------------------


def test_cursor_touch_opaque_skips_erase_when_covered():
    src = CURSOR_C.read_text(encoding="utf-8")
    body = _func_body(CURSOR_C, "cursor_touch_opaque")
    assert re.search(r"static int cursor_covered_fully\s*\(", src), (
        "cursor_touch_opaque needs a 24x24 full-coverage predicate "
        "cursor_covered_fully() (box corners inside the reported rect) to "
        "decide when the write clears the arrow (devdoc 109)")
    assert "!cursor_covered_fully" in body, (
        "cursor_touch_opaque must ERASE only when the box is NOT fully "
        "covered (straddling the rect border); a fully-covered box relies on "
        "the writer's opaque pixels to clear the arrow (devdoc 109)")
    assert "valid = 0" in body and "cursor_erase" in body
    assert "cursor_overlap_rect" in body, (
        "the opaque touch must still gate on overlap (no-op otherwise), or a "
        "non-overlapping opaque write would invalidate the cursor for nothing")


def test_cursor_render_stale_redraw_skips_vblank():
    body = _func_body(CURSOR_C, "cursor_render")
    assert "stale_same_pos" in body, (
        "cursor_render must implement a steady-position stale-redraw fast "
        "path: saved-state invalid AND draw position unchanged after an "
        "overlapping write (devdoc 109)")
    i = body.index("stale_same_pos")
    j = body.index("cursor_draw", i)
    assert "hal_vblank_wait" not in body[i:j], (
        "the steady-position stale redraw must NOT gate on hal_vblank_wait — "
        "waiting defers the redraw to the next VBLANK (~1 full frame), so the "
        "arrow is absent from the scanout for a full frame per reveal pass = "
        "the ~20 Hz typewriter-cursor flicker (devdoc 109)")
    assert "hal_vblank_wait" in body[j:], (
        "the move/teleport/force path must keep the VBLANK-synced erase+draw "
        "pair (no half-drawn cursor on moves)")


# --- 3c. Composite splice (devdoc 110): the arrow goes into the dialog
#         buffer BEFORE its vram_write, so the slow bank-switched VRAM write
#         lands with the cursor already on screen. -------------------------


def test_dialog_layer_blit_splices_before_vram_write():
    body = _func_body(LAYER_DIALOG_C, "dialog_layer_blit")
    assert "cursor_composite_splice(dialog_blit_tmp" in body, (
        "dialog_layer_blit must splice the arrow into the THROWAWAY write "
        "copy (dialog_blit_tmp) so the single vram_write carries the cursor "
        "ON SCREEN for its whole duration — the pass-end stale redraw alone "
        "still leaves the arrow missing for the whole slow write = the "
        "residual typewriter flicker (devdoc 110)")
    assert body.index("hal_mouse_touch_cursor") < body.index(
        "cursor_composite_splice") < body.index("vram_write"), (
        "order must be: opaque touch (erase straddlers) -> splice arrow into "
        "the throwaway copy -> vram_write with the arrow already in it "
        "(devdoc 110)")


def test_dialog_blit_tmp_buffers_arrow_away_from_persistent_composite():
    # devdoc 111: the arrow must never be baked into the durable dialog_layer
    # composite (not repainted every pass — a baked arrow survives dither
    # holes and later re-blits, showing as residue the moment the cursor
    # moves).  The splice works on a one-shot copy backed by the pure buffer.
    src = LAYER_DIALOG_C.read_text(encoding="utf-8")
    blit = _func_body(LAYER_DIALOG_C, "dialog_layer_blit")
    assert "cursor_composite_splice(dialog_layer" not in blit, (
        "cursor_composite_splice must never target the durable composite — "
        "baking the transient arrow into dialog_layer re-emits it on later "
        "blits and into later splice backgrounds = move residue (devdoc 111)")
    assert "cursor_composite_splice(dialog_blit_tmp" in blit
    assert blit.index("memcpy(dialog_blit_tmp, dialog_layer") < \
           blit.index("cursor_composite_splice(dialog_blit_tmp"), (
        "the throwaway copy must be backed by the pure composite BEFORE the "
        "arrow is blended in, so the adopted saved background is clean "
        "dialog text, not a stale arrow (devdoc 111)")
    show = _func_body(LAYER_DIALOG_C, "layer_dialog_show")
    assert 'layer_snapshot_alloc_dialog("dialog_blit_tmp")' in show, (
        "dialog_blit_tmp must be allocated lazily alongside dialog_layer "
        "(heap; OOM degrades the blit to the pass-end redraw)")
    reset = _func_body(LAYER_DIALOG_C, "layer_dialog_reset")
    assert "dialog_blit_tmp" in reset, (
        "dialog_blit_tmp must be freed in layer_dialog_reset with the other "
        "dialog buffers")


def test_cursor_composite_splice_blends_and_adopts_bg():
    src = CURSOR_C.read_text(encoding="utf-8")
    body = _func_body(CURSOR_C, "cursor_composite_splice")
    assert "is_fill_pixel" in body and "is_cursor_pixel" in body, (
        "the splice must blend the arrow glyph (white fill / black outline / "
        "transparent) over the composite exactly like cursor_draw does "
        "(devdoc 110)")
    assert "memcpy" in body, (
        "the splice must adopt the pre-arrow composite box pixels as the "
        "saved background (memcpy from the buffer) so a later erase restores "
        "clean dialog text, not a baked-in arrow (devdoc 110)")
    assert "valid = 1" in body, (
        "after splicing, the saved cursor state is valid at the composite "
        "position — the pass-end transparent_render/cursor_render early-"
        "returns, the arrow is already in the buffer being written (devdoc "
        "110)")
    assert "hal_vblank_wait" not in body, (
        "the splice must be VBLANK-free AND VRAM-free (pure RAM buffer "
        "blend) — any vblank wait reintroduces the full-frame absence it "
        "exists to kill (devdoc 110)")


# --- 4. HAL forwarding exist and routes to the engine layer. -----------


def test_hal_forwards_touch():
    src = HAL_MOUSE_C.read_text(encoding="utf-8")
    assert "void hal_mouse_touch_cursor(int x, int y, int w, int h)" in src
    assert "cursor_touch(x, y, w, h)" in src, (
        "hal_mouse_touch_cursor must forward to the engine cursor layer "
        "(cursor_touch) exactly like the other hal_mouse_*_cursor() calls")
    assert src.index("hal_mouse_touch_cursor(int x, int y, int w, int h)") < \
           src.index("cursor_touch(x, y, w, h)")
    assert "hal_mouse_touch_cursor_opaque" in src and \
           "cursor_touch_opaque(x, y, w, h)" in src, (
        "hal_mouse_touch_cursor_opaque must forward to cursor_touch_opaque "
        "(devdoc 109)")


# --- 5. Menu overlay blits keep the contract (all three VRAM writers). --


def test_menu_layer_blits_touch_before_write():
    blit = _func_body(MENU_LAYER_C, "menu_layer_blit")
    rect = _func_body(MENU_LAYER_C, "menu_layer_blit_rect")
    close = _func_body(MENU_LAYER_C, "menu_layer_close")
    for name, body in (("menu_layer_blit", blit),
                       ("menu_layer_blit_rect", rect),
                       ("menu_layer_close", close)):
        assert "hal_mouse_touch_cursor" in body, (
            f"{name}() writes the menu composite to VRAM — must touch the "
            f"region first (devdoc 108 layer contract)")
        assert body.index("hal_mouse_touch_cursor") < \
               body.index("ram_write"), (
            f"{name}() must touch the cursor layer before its vram_write/"
            f"render_blit_transparent, else a parked cursor over the menu is "
            f"clobbered with a stale background behind it (devdoc 108)")