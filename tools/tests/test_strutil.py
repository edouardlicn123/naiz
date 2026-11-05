"""str_toc8 host tests (engine-side 8.3 TOC key resolution).

Compiles core/lib/strutil.c with the host gcc into a temp shared object and
drives it through ctypes.  The core assertion is that the C helper — which
the engine uses to resolve a script audio key to the packed AUDIO.DAT TOC
name — produces byte-for-byte the same result as the toolchain's
to_dos_name()[0].strip(), so pack and lookup can never drift apart.

Regression basis: melody_town / icy_garden are the first audio keys whose
8.3 short name differs from the full key; before str_toc8 the engine looked
up the full name and AUDIO.DAT never matched (c56 -> c57).
"""

import ctypes
import os
import subprocess
import sys
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from naiz_lib import to_dos_name  # noqa: E402

_BASE = os.path.join(REPO_ROOT, "core", "lib")
_CACHE = {}


def _load_strutil():
    mtime = os.stat(os.path.join(_BASE, "strutil.c")).st_mtime
    if _CACHE.get("mtime") == mtime:
        return _CACHE["lib"]
    with tempfile.TemporaryDirectory(prefix="strutil_test_") as tmp:
        so = os.path.join(tmp, "strutil.so")
        cmd = ["gcc", "-O2", "-shared", "-fPIC", "-I", _BASE,
               os.path.join(_BASE, "strutil.c"), "-o", so]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        lib = ctypes.CDLL(so)
        lib.str_toc8.argtypes = [ctypes.c_char_p, ctypes.c_size_t,
                                 ctypes.c_char_p]
        lib.str_toc8.restype = ctypes.c_char_p
        _CACHE["lib"] = lib
        _CACHE["mtime"] = mtime
        return lib


def _expected(key):
    base8 = to_dos_name(key)[0]
    return base8.rstrip(b" ").decode("ascii")


@pytest.mark.parametrize("key", [
    "melody_town",            # truncated: MELODY_T
    "icy_garden",             # truncated: ICY_GARD
    "test1",                  # short: identity
    "chime",
    "hi",
    "piano",
    "synlead",
    "eightchr",               # exactly 8 chars
    "ninechars",              # -> NINECHAR
    "a.b",                    # dotted: base is 'a'
    "file.name.mid",          # rsplit: base is 'file.name' -> FILE.NAM
    "LowerCase",              # uppercase folding
    "ALLUPPER",
    "",                       # empty key
])
def test_str_toc8_matches_toolchain(key):
    lib = _load_strutil()
    buf = ctypes.create_string_buffer(9)
    key_b = key.encode("ascii")
    lib.str_toc8(buf, len(buf), key_b)
    assert buf.value.decode("ascii") == _expected(key)


def test_str_toc8_nul_terminates_short_buffer():
    """Even undersized buffers must stay NUL-terminated (never overflow)."""
    lib = _load_strutil()
    buf = ctypes.create_string_buffer(4)
    lib.str_toc8(buf, len(buf), b"melody_town")
    assert buf.value == b"MEL"