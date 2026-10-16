"""OPNA LFO enable guard (devdoc 123 S7 / F03 §3.3).

The patch format carries per-channel LFO depth in $B4 (bits5-4 AMS, bits2-0
PMS), but the chip-wide LFO oscillates only when reg $22 has bit3 set.  If
that write is ever dropped, every AMS/PMS-carrying patch silently loses its
vibrato/tremolo and no compiler diagnostic fires — the exact "silent failure"
class AGENTS §九.6 forbids.

These tests read the HAL source; removing the $22 write or the rate macro
fails here.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HAL_AUDIO_C = ROOT / "core" / "plat" / "hal_audio.c"


def _hal_audio():
    return HAL_AUDIO_C.read_text(encoding="utf-8")


def _fn_body(src, name):
    m = re.search(r"\b" + re.escape(name) + r"\s*\([^)]*\)\s*\{", src)
    assert m, f"{name} not found in hal_audio.c"
    i = m.end()
    depth = 1
    while depth:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
        i += 1
    return src[m.start():i]


def test_lfo_rate_macro_defined():
    src = _hal_audio()
    m = re.search(r"#define\s+FM_LFO_RATE\s+(\d+)", src)
    assert m, "FM_LFO_RATE macro missing"
    assert 0 <= int(m.group(1)) <= 7, "LFRQ is a 3-bit field (0..7)"


def test_init_enables_lfo():
    body = _fn_body(_hal_audio(), "hal_fm_init")
    assert re.search(r"hal_fm_write_reg\(\s*0\s*,\s*0x22\s*,", body), \
        "hal_fm_init must write reg $22 to enable the LFO"
    assert "0x08" in body and "FM_LFO_RATE" in body, \
        "$22 write must set bit3 (enable) and the FM_LFO_RATE speed bits"
