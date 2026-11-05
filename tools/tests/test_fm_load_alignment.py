"""FM family slot-alignment guard (devdoc 123 S7).

fm_load_patches() fills g_fm_patches[] and fmp_gm_map[] indexes it
positionally, so the load MUST keep one g_fm_patches slot per fmp_map entry.
The original code `continue`d past missing/invalid/dummy entries and only
advanced the slot counter on success, which shifts every later family down
by one: a single bad patch silently reroutes all higher GM programs (a flute
program ends up on the next family's timbre).  There is no compiler
diagnostic; only one WARN line differs.

These tests read engine/audio.c and assert the loop reserves a slot for
every entry (no early `continue`, unconditional `n++`).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
AUDIO_C = ROOT / "core" / "engine" / "audio.c"


def _fn_body(src, name):
    m = re.search(r"\b" + re.escape(name) + r"\s*\(void\)\s*\{", src)
    assert m, f"{name}(void) not found in audio.c"
    i = m.end()
    depth = 1
    while depth:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
        i += 1
    return src[m.start():i]


def test_loader_reserves_every_slot():
    body = _fn_body(AUDIO_C.read_text(encoding="utf-8"), "fm_load_patches")
    assert "continue" not in body, (
        "fm_load_patches must not skip an fmp_map entry: that shifts all "
        "later family indices and reroutes gm_map programs")
    assert re.search(r"\bn\+\+\s*;", body), "slot counter must advance per entry"
    assert re.search(r"g_fm_patches\[\s*n\s*\]\s*=\s*g_fm_default_patch", body), \
        "each slot must be pre-seeded with the default patch"


def test_gm_map_is_wired_to_the_family_table():
    """fm_gm_map[] and g_fm_families must reach fmseq_init together."""
    src = AUDIO_C.read_text(encoding="utf-8")
    m = re.search(r"fmseq_init\((.*?)\);", src, re.S)
    assert m, "fmseq_init call not found"
    args = m.group(1)
    assert "g_fm_patches" in args and "fmp_gm_map" in args \
        and "g_fm_families" in args, (
        "fmseq must receive the patch table, its count, and the gm_map so "
        "the positional family index is actually used")
