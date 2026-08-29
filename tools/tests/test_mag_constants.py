"""MAG format constants: C header / Python mirror consistency.

core/lib/mag_format.h and tools/naiz_lib/mag_constants.py are a documented
C/Python mirror pair (devdocs/0.1版开发文档总结.html#doc-38 stage 11.1).  This test keeps them honest.
"""

import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAG_FORMAT_H = os.path.join(REPO_ROOT, "core", "lib", "mag_format.h")

from naiz_lib import mag_constants


def _parse_c_defines():
    """Parse MAG_* #define lines from mag_format.h into a dict."""
    if not os.path.exists(MAG_FORMAT_H):
        return {}
    defines = {}
    with open(MAG_FORMAT_H, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"#define\s+(MAG_\w+)\s+(.+?)\s*$", line)
            if m:
                defines[m.group(1)] = m.group(2).strip()
    return defines


def test_c_header_and_python_mirror_agree():
    c_defs = _parse_c_defines()
    assert c_defs, "mag_format.h should define MAG_* constants"

    for name, c_value in c_defs.items():
        assert hasattr(mag_constants, name), (
            f"Python mirror missing {name} (C defines {c_value})"
        )


def test_signature_value_consistency():
    assert mag_constants.MAG_SIGNATURE == b"MAKI02  "
    assert mag_constants.MAG_SIGNATURE_LEN == 8
    assert mag_constants.MAG_SPRITE_MARKER == b"sprt"
    assert mag_constants.MAG_HEADER_SIZE == 32
    assert mag_constants.MAG_USER_TERM == 0x1A


def test_model_codes():
    assert mag_constants.MAG_MODEL_3BIT == 0x03
    assert mag_constants.MAG_MODEL_5BIT == 0x68
    assert mag_constants.MAG_MODEL_8BIT == 0x99
    assert mag_constants.MAG_MODEL_8BIT2 == 0x88
