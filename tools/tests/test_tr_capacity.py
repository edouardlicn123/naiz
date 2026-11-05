"""Translation/script line capacity guard (devdoc 121).

This guard ensures translation buffers and script line limits are large
enough for "5 dialog boxes" worth of text (3 lines × ~28 CJK chars per box)
and will fail loudly if they aren't. It also enforces consistency between
the engine constants (TR_KEY_LEN/TR_VAL_LEN/NB_LINE_MAX/dialog buffers).
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
TR_H = ROOT / "core/lib/tr.h"
TR_C = ROOT / "core/lib/tr.c"
NB_INTERNAL_H = ROOT / "core/engine/nb_internal.h"
NB_DIALOG_C = ROOT / "core/engine/nb_dialog.c"
LAYER_DIALOG_C = ROOT / "core/engine/layer_dialog.c"
PROJECTS = ROOT / "projects"


def _define(path: Path, name: str) -> int:
    m = re.search(r"#define\s+%s\s+(\d+)" % re.escape(name), path.read_text("utf-8"))
    if not m:
        raise RuntimeError("cannot find #define %s in %s" % (name, path))
    return int(m.group(1))


def _decl_array_dim(path: Path, name: str) -> int:
    s = path.read_text("utf-8")
    # numeric literal
    m = re.search(r"char\s+%s\s*\[\s*(\d+)\s*\]" % re.escape(name), s)
    if m: return int(m.group(1))
    m = re.search(r"uint8_t\s+%s\s*\[\s*(\d+)\s*\]" % re.escape(name), s)
    if m: return int(m.group(1))
    # macro - check same file first, then tr.h
    m = re.search(r"(?:char|uint8_t)\s+%s\s*\[\s*([A-Za-z_][A-Za-z0-9_]*)\s*\]" % re.escape(name), s)
    if m:
        mac = m.group(1)
        # try same file
        try:
            return _define(path, mac)
        except Exception:
            pass
        # try tr.h
        try:
            return _define(TR_H, mac)
        except Exception:
            pass
    raise RuntimeError("cannot find array %s in %s" % (name, path))


def test_tr_h_defines():
    tr_key = _define(TR_H, "TR_KEY_LEN")
    tr_val = _define(TR_H, "TR_VAL_LEN")
    assert tr_key >= 1024, tr_key
    assert tr_val >= 1280, tr_val


def test_tr_c_uses_tr_h_constants():
    trc = TR_C.read_text("utf-8")
    # Should not define local TR_KEY_LEN/TR_VAL_LEN anymore
    assert re.search(r"#define\s+TR_KEY_LEN\s+128\b", trc) is None
    assert re.search(r"#define\s+TR_VAL_LEN\s+256\b", trc) is None
    # line buffer should be TR_LINE_MAX
    m = re.search(r"char\s+line\s*\[\s*TR_LINE_MAX\s*\]", trc)
    assert m, "line[] should use TR_LINE_MAX"


def test_nb_line_max():
    nb_line = _define(NB_INTERNAL_H, "NB_LINE_MAX")
    assert nb_line >= 1152, nb_line


def test_dialog_buffers_match_tr_val():
    tr_val = _define(TR_H, "TR_VAL_LEN")
    d1 = _decl_array_dim(NB_DIALOG_C, "dialog_text_buf")
    d2 = _decl_array_dim(LAYER_DIALOG_C, "dialog_render_text")
    assert d1 >= tr_val, (d1, tr_val)
    assert d2 >= tr_val, (d2, tr_val)


def _project_i18n_files():
    for proj in sorted(PROJECTS.iterdir()):
        i18n = proj / "i18n"
        if i18n.is_dir():
            yield proj.name, sorted(p.name for p in i18n.iterdir() if p.is_file())


def test_i18n_lines_under_limits():
    tr_key = _define(TR_H, "TR_KEY_LEN")
    tr_val = _define(TR_H, "TR_VAL_LEN")
    tr_line_max = tr_key + tr_val + 4  # approximation for sanity; engine uses TR_LINE_MAX
    for proj, files in _project_i18n_files():
        for fname in files:
            path = PROJECTS / proj / "i18n" / fname
            try:
                text = path.read_text("utf-8", errors="strict")
            except Exception:
                text = path.read_text("latin-1")
            for lineno, line in enumerate(text.splitlines(), start=1):
                # check raw line bytes length
                b = line.encode("utf-8", errors="replace")
                if len(b) >= tr_key + tr_val + 2:  # rough; focus key/val split
                    pass  # skip heuristic for now
                # split by first =
                if "=" not in line or line.strip().startswith("#"):
                    continue
                eq = line.find("=")
                key = line[:eq]
                val = line[eq + 1:]
                kb = key.encode("utf-8", errors="replace")
                vb = val.encode("utf-8", errors="replace")
                assert len(kb) < tr_key, f"{proj}/{fname}:{lineno} key len {len(kb)} >= {tr_key}"
                assert len(vb) < tr_val, f"{proj}/{fname}:{lineno} val len {len(vb)} >= {tr_val}"


def test_nb_script_lines_under_limit():
    nb_line_max = _define(NB_INTERNAL_H, "NB_LINE_MAX")
    for proj in sorted(PROJECTS.iterdir()):
        scene = proj / "scene"
        if not scene.is_dir():
            continue
        for nb in sorted(scene.glob("*.nb")):
            try:
                text = nb.read_text("utf-8", errors="strict")
            except Exception:
                text = nb.read_text("latin-1")
            for lineno, line in enumerate(text.splitlines(), start=1):
                b = line.encode("utf-8", errors="replace")
                assert len(b) < nb_line_max, f"{nb}:{lineno} line len {len(b)} >= {nb_line_max}"
