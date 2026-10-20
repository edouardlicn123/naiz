"""OPNA six-voice enable guard (devdoc 156).

YM2608 powers up with reg $29 bit7 (SCH) clear, where the manual says
"Channel 4-6 is not good at assign" -- only channels 1-3 sound.  The fmseq
allocator spreads voices over 6 channels, so without writing SCH=1 every note
placed on voice 3-5 silently disappears (icy_garden: 34 of 287 notes) and no
compiler diagnostic fires -- the "silent failure" class AGENTS §九.6 forbids.

These tests read the HAL source; dropping the $29 write fails here.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HAL_AUDIO_C = ROOT / "core" / "plat" / "hal_audio.c"
ENGINE_AUDIO_C = ROOT / "core" / "engine" / "audio.c"


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


def test_init_enables_all_six_fm_voices():
    body = _fn_body(HAL_AUDIO_C.read_text(encoding="utf-8"), "hal_fm_init")
    m = re.search(r"hal_fm_write_reg\(\s*0\s*,\s*0x29\s*,\s*(\w+)\s*\)", body)
    assert m, "hal_fm_init must write reg $29 to enable channels 4-6"
    val = int(m.group(1), 0)
    assert val & 0x80, "$29 bit7 (SCH) must be set: six-voice mode"
    assert val & 0x3F == 0, "$29 bits0-5 are timer IRQ enables; keep them 0"


def test_bgm_start_stops_prior_fm_voices():
    """audio_bgm_start must key off any still-sounding FM voices before it
    installs a new event stream.  A mid-scene bgm(){key} over a playing song
    otherwise leaves the old voices ringing and the per-voice ages stale, so
    the coldest-free allocator re-keys a release tail (devdoc 157).  The call
    sits before bgm_release(); deleting it fails here."""
    body = _fn_body(ENGINE_AUDIO_C.read_text(encoding="utf-8"), "audio_bgm_start")
    stop = body.find("fmseq_stop(")
    release = body.find("bgm_release()")
    assert stop != -1, "audio_bgm_start must fmseq_stop() the previous BGM"
    assert release != -1 and stop < release, \
        "fmseq_stop() must run before bgm_release() swaps the event table"
