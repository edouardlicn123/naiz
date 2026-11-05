"""FMP/VOPM patch text export contracts (devdoc 186 §三 B, was 161 §三 B).

fmp_export.py decomposes the single-source 32-byte patch layout (fm_patch.py)
into FMP `@` and VOPM paste text for human audit.  Contracts:

  1. field decomposition matches the documented layout exactly: op bytes
     DT<<4|MUL / TL / KS<<6|AR / AM<<7|D1R / D2R / SL<<4|RR, globals
     FB<<3|ALG and PAN<<6|AMS<<4|PMS.
  2. FMP line order is the verified reference order (F03 §4.3): AR DR SR RR
     SL TL KS ML DT AMS, with SR == D2R.
  3. VOPM output carries DT2 = 0 (OPM-only field, absent on OPN) and the
     global PAN/AMS/PMS.
  4. the export accepts fm_patch.compile_source output unchanged (the two
     tools share the layout as their single source of truth).
  5. round-trip sanity: exported FMP fields re-assembled back to bytes equal
     the input blob (the export loses no register information).
"""
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools", "naiz_audio"))

from fmp_export import _fields, to_fmp, to_vopm  # noqa: E402
from fm_patch import parse_patch, to_bytes  # noqa: E402

_SRC = """alg=4 fb=5 pan=0xc0
op=1 dt=2 mul=9  tl=40 ks=0 ar=24 am=0 d1r=5 d2r=4 sl=1 rr=5
op=2 dt=0 mul=3  tl=42 ks=1 ar=20 am=0 d1r=5 d2r=3 sl=1 rr=6
op=3 dt=0 mul=4  tl=44 ks=1 ar=20 am=0 d1r=4 d2r=3 sl=1 rr=5
op=4 dt=0 mul=3  tl=46 ks=1 ar=24 am=0 d1r=5 d2r=4 sl=2 rr=6
"""

_EXAMPLE = (b"\x29\x28\x18\x05\x04\x15"
            b"\x03\x2a\x54\x05\x03\x16"
            b"\x04\x2c\x54\x04\x03\x15"
            b"\x03\x2e\x58\x05\x04\x26"
            b"\x2c\xc0" + b"\x00" * 6)


def _compile():
    params, ops = parse_patch(_SRC)
    return to_bytes(params, ops)


def test_accepts_compiled_blob():
    blob = _compile()
    assert len(blob) == 32
    ops, alg, fb, pan, ams, pms = _fields(blob)
    assert (alg, fb, pan) == (4, 5, 3)
    assert (ams, pms) == (0, 0)
    assert ops[0]["dt"] == 2 and ops[0]["mul"] == 9
    assert ops[0]["tl"] == 40 and ops[0]["ar"] == 24


def test_fmp_line_order():
    blob = _compile()
    text = to_fmp(blob, num=7, name="demo")
    lines = text.splitlines()
    assert lines[0] == "@ 7 4 5 =demo"
    # AR DR SR RR SL TL KS ML DT AMS  (SR == D2R, F03 §4.3)
    assert lines[1].split() == ["24", "5", "4", "5", "1", "40", "0", "9",
                                "2", "0"]
    assert lines[2].split()[2] == "3"      # op2 SR == d2r 3
    assert lines[4].split()[3] == "6"      # op4 RR == 6


def test_vopm_shape():
    blob = _compile()
    text = to_vopm(blob, name="demo")
    lines = text.splitlines()
    assert lines[0] == '@:0 :"demo"'
    assert "AL: 4" in lines and "FB: 5" in lines
    op1 = next(l for l in lines if l.startswith("AR: 24"))
    for token in ("D1R: 5", "D2R: 4", "RR: 5", "SL: 1", "TL: 40", "KS: 0",
                  "DT: 2", "MUL: 9", "DT2: 0", "AMS: 0"):
        assert token in op1, f"missing {token}"
    assert "PAN: 3" in text and "AMS: 0" in text and "PMS: 0" in text


def test_no_information_loss():
    blob = _compile()
    ops, alg, fb, pan, ams, pms = _fields(blob)
    rebuilt = bytearray(32)
    for i, o in enumerate(ops):
        base = i * 6
        rebuilt[base + 0] = (o["dt"] << 4) | o["mul"]
        rebuilt[base + 1] = o["tl"]
        rebuilt[base + 2] = (o["ks"] << 6) | o["ar"]
        rebuilt[base + 3] = (o["am"] << 7) | o["d1r"]
        rebuilt[base + 4] = o["d2r"]
        rebuilt[base + 5] = (o["sl"] << 4) | o["rr"]
    rebuilt[24] = (fb << 3) | alg
    rebuilt[25] = (pan << 6) | (ams << 4) | pms
    assert bytes(rebuilt) == blob


def test_example_blob_fixture():
    """The hand-packed example stays in lockstep with the real layout (guards
    against the fixture drifting from fm_patch's to_bytes)."""
    assert _EXAMPLE == _compile()
