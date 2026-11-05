"""S3 fd: .fmp text -> 32-byte binary compiler (devdocs/123).

Round-trips the compiled bytes through the C validator (fmopn build from
test_fmopn) so the text authoring format is proven against the same rule
the engine will enforce, not just against a parallel Python check.
"""

import ctypes
import glob
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tools', 'naiz_audio'))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, 'tools', 'naiz_audio'))
sys.path.insert(0, os.path.join(REPO_ROOT, 'tools', 'tests'))

from naiz_audio import fm_patch
from test_fmopn import _build_fmopn

GOOD = """\
# lead
alg=4 fb=5 pan=0xc0
op=1 dt=2 mul=9 tl=40 ks=0 ar=24 am=0 d1r=5 d2r=4 sl=1 rr=5
op=2 dt=0 mul=4 tl=44 ks=1 ar=20 am=0 d1r=4 d2r=3 sl=1 rr=5
op=3 dt=0 mul=3 tl=42 ks=1 ar=20 am=0 d1r=5 d2r=3 sl=1 rr=6
op=4 dt=0 mul=3 tl=46 ks=1 ar=24 am=0 d1r=5 d2r=4 sl=2 rr=6
"""


def _validator():
    lib, _ = _build_fmopn()
    lib.fmopn_patch_validate.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    lib.fmopn_patch_validate.restype = ctypes.c_int
    return lib


def test_compile_good_roundtrip():
    params, ops = fm_patch.parse_patch(GOOD)
    blob = fm_patch.to_bytes(params, ops)
    assert len(blob) == 32
    assert blob[24] == (5 << 3) | 4
    assert blob[25] == 0xC0
    # C validator accepts it
    lib = _validator()
    arr = (ctypes.c_uint8 * 32).from_buffer_copy(blob)
    assert lib.fmopn_patch_validate(arr) == 0


def test_file_is_algorithm_order():
    """File idx k holds algorithm operator k+1 (identity OP_FILE)."""
    params, ops = fm_patch.parse_patch(GOOD)
    blob = fm_patch.to_bytes(params, ops)
    # op=1 sits at file idx 0 -> byte 0
    assert blob[0] == (2 << 4) | 9
    assert blob[1] == 40
    # op=2 sits at file idx 1 -> byte 6
    assert blob[6] == (0 << 4) | 4
    assert blob[7] == 44
    # op=3 sits at file idx 2 -> byte 12
    assert blob[12] == (0 << 4) | 3
    assert blob[13] == 42
    # op=4 sits at file idx 3 -> byte 18
    assert blob[18] == (0 << 4) | 3
    assert blob[19] == 46


def test_ctypes_round_trips_per_field():
    """Regslot accessors read op N from register slot fmopn_op_slot[N-1].

    Author op=N (algorithm operator) is stored in algorithm order, so the
    C reader must expose it at the register slot the algorithm assigns it
    ({0,2,1,3}[N-1]): op1->0, op2->2, op3->1, op4->3.
    """
    params, ops = fm_patch.parse_patch(GOOD)
    blob = fm_patch.to_bytes(params, ops)
    lib = _validator()
    arr = (ctypes.c_uint8 * 32).from_buffer_copy(blob)
    lib.fmopn_op_tl.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_int]
    lib.fmopn_op_tl.restype = ctypes.c_uint8
    lib.fmopn_op_dt_mul.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_int]
    lib.fmopn_op_dt_mul.restype = ctypes.c_uint8
    slot = ctypes.c_uint8 * 4
    op_to_slot = list(slot.in_dll(lib, "fmopn_op_slot"))
    assert op_to_slot == [0, 2, 1, 3]
    expect_tl = {1: 40, 2: 44, 3: 42, 4: 46}
    for opn, tl in expect_tl.items():
        assert lib.fmopn_op_tl(arr, op_to_slot[opn - 1]) == tl
    # regslot 0 (= op1) carries the modulator's dt/mul
    assert lib.fmopn_op_dt_mul(arr, op_to_slot[0]) == (2 << 4) | 9


def test_pan_default_c0():
    p = GOOD.replace('pan=0xc0', '')
    params, _ops = fm_patch.parse_patch(p)
    assert params['pan'][1] == 0xC0


def test_lfo_defaults_zero():
    """Absent ams=/pms= leave $B4 at pan-only, so old patches are unchanged."""
    params, ops = fm_patch.parse_patch(GOOD)
    assert params['ams'][1] == 0 and params['pms'][1] == 0
    assert fm_patch.to_bytes(params, ops)[25] == 0xC0


def test_ams_pms_encode_into_b4():
    params, ops = fm_patch.parse_patch(GOOD + "ams=3 pms=5\n")
    assert params['ams'][1] == 3 and params['pms'][1] == 5
    blob = fm_patch.to_bytes(params, ops)
    assert blob[25] == 0xC0 | (3 << 4) | 5


def test_ams_pms_passes_c_validator():
    params, ops = fm_patch.parse_patch(GOOD + "ams=3 pms=7\n")
    blob = fm_patch.to_bytes(params, ops)
    lib = _validator()
    arr = (ctypes.c_uint8 * 32).from_buffer_copy(blob)
    assert lib.fmopn_patch_validate(arr) == 0


GOOD_OP4 = "op=4 dt=0 mul=3 tl=46 ks=1 ar=24 am=0 d1r=5 d2r=4 sl=2 rr=6"

@pytest.mark.parametrize("mut, msg", [
    ("op=0 dt=0 mul=1 tl=40 ks=0 ar=20 am=0 d1r=5 d2r=4 sl=1 rr=5", "op=0 not in 1..4"),
    ("op=5 dt=0 mul=1 tl=40 ks=0 ar=20 am=0 d1r=5 d2r=4 sl=1 rr=5", "op=5 not in 1..4"),
    ("op=4 dt=9 mul=1 tl=40 ks=0 ar=20 am=0 d1r=5 d2r=4 sl=1 rr=5", "dt=9 out of range"),
    ("op=4 dt=0 mul=1 tl=200 ks=0 ar=20 am=0 d1r=5 d2r=4 sl=1 rr=5", "tl=200 out of range"),
    ("op=4 dt=0 mul=1 tl=40 ks=4 ar=20 am=0 d1r=5 d2r=4 sl=1 rr=5", "ks=4 out of range"),
    ("op=4 dt=0 mul=1 tl=40 ks=0 ar=40 am=0 d1r=5 d2r=4 sl=1 rr=5", "ar=40 out of range"),
    ("op=4 dt=0 mul=1 tl=40 ks=0 ar=20 am=2 d1r=5 d2r=4 sl=1 rr=5", "am=2 out of range"),
    ("op=4 dt=0 mul=1 tl=40 ks=0 ar=20 am=0 d1r=40 d2r=4 sl=1 rr=5", "d1r=40 out of range"),
    ("op=4 dt=0 mul=1 tl=40 ks=0 ar=20 am=0 d1r=5 d2r=40 sl=1 rr=5", "d2r=40 out of range"),
    ("op=4 dt=0 mul=1 tl=40 ks=0 ar=20 am=0 d1r=5 d2r=4 sl=16 rr=5", "sl=16 out of range"),
    ("op=4 dt=0 mul=1 tl=40 ks=0 ar=20 am=0 d1r=5 d2r=4 sl=1 rr=16", "rr=16 out of range"),
    (GOOD_OP4 + "\nfb=8", "fb=8 out of range"),
    (GOOD_OP4 + "\nalg=8", "alg=8 out of range"),
    (GOOD_OP4 + "\npan=0x10", "only the L/R bits"),
    (GOOD_OP4 + "\nams=4", "ams=4 out of range"),
    (GOOD_OP4 + "\npms=8", "pms=8 out of range"),
    ("op=4 dt=0 mul=3 tl=46 ks=1 ar=24 am=0 d1r=5 d2r=4 rr=6", "missing key"),
])
def test_bad_patches(mut, msg):
    text = GOOD.replace(GOOD_OP4, mut)
    with pytest.raises(fm_patch._PatchError) as ei:
        fm_patch.parse_patch(text)
    assert msg in str(ei.value)


def test_missing_opdef():
    text = GOOD.replace("op=2 dt=0 mul=4 tl=44 ks=1 ar=20 am=0 d1r=4 d2r=3 sl=1 rr=5\n", "")
    with pytest.raises(fm_patch._PatchError, match=r"missing op=2"):

        fm_patch.parse_patch(text)


def test_duplicate_op():
    text = GOOD + "op=1 dt=0 mul=1 tl=40 ks=0 ar=20 am=0 d1r=5 d2r=4 sl=1 rr=5\n"
    with pytest.raises(fm_patch._PatchError, match="duplicate op=1"):
        fm_patch.parse_patch(text)


def test_unknown_global_key():
    with pytest.raises(fm_patch._PatchError, match="op must precede 'foo'"):
        fm_patch.parse_patch("foo=1\n" + GOOD)


def test_op_label_semantics_pinned():
    """op=N is the *algorithm operator*; the compiler derives register slots
    from the C table.  Guards the devdocs/136 fix (op=N used to be misread as
    a raw register slot, which muted alg=4 carriers)."""
    from test_fmopn import FMOPN_H
    with open(FMOPN_H) as f:
        hdr = f.read()
    # the C comment still documents the hardware 1-3-2-4 register order
    assert "1-3-2-4" in hdr
    # compiler lays operators in algorithm order (identity), C maps to slots
    assert fm_patch.OP_FILE == [0, 1, 2, 3]
    lib = _validator()
    slot = ctypes.c_uint8 * 4
    # op N -> register slot for algorithm operator N
    assert list(slot.in_dll(lib, "fmopn_op_slot")) == [0, 2, 1, 3]


def test_project_patch_library_compiles():
    """Every demo-a2 FM family source compiles and passes the C validator.

    Devdoc 124 S6 default family set: 15 .fmp files under assets/demo-a2/fm/.
    Coverage/order vs ASSETS.DB is guarded by test_gm_map.py; here we only
    prove each shipped source is a valid 32-byte patch the engine will load.
    """
    lib = _validator()
    pats = sorted(glob.glob(os.path.join(REPO_ROOT, 'assets', 'demo-a2',
                                         'fm', '*.fmp')))
    assert len(pats) >= 1
    for p in pats:
        blob = fm_patch.compile_source(p)
        assert len(blob) == 32, f"{p}: compiled size must be 32"
        arr = (ctypes.c_uint8 * 32).from_buffer_copy(blob)
        assert lib.fmopn_patch_validate(arr) == 0, f"{p}: fails C validator"