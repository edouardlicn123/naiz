"""M1 fmopn host tests (devdocs/123 S1).

Compiles core/lib/fmopn.c with the host gcc into a temp shared object and
drives it through ctypes.  This is the plan's core risk-reduction: the FM
register model is pure logic (zero outb()), so its correctness is proven
here without an emulator.

Assertions cover:
  - the 1-3-2-4 op reorder (file slot -> register slot) is pinned in code
  - every MIDI note 0..127 lands on a valid block/fnum whose implied
    frequency is within 0.6% of the ideal (monotone, no gaps, clamped top)
  - the canonical anchors A4/C4 hit the reference table values
  - bend stays within +-2 semitones and reverts at centre
  - patch round-trip through a 32B blob and per-slot accessors agree
  - register addressing keeps FM1-3 in bank 0 and FM4-6 in bank 1
"""

import ctypes
import math
import os
import subprocess
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FMOPN_C = os.path.join(REPO_ROOT, "core", "lib", "fmopn.c")
FMOPN_H = os.path.join(REPO_ROOT, "core", "lib", "fmopn.h")

# Master clock 7.9872MHz; freq = (fnum << block) * 7987200 / (144 * 2**20).
_MCLK = 7987200.0
_MCLK_DIV = 144.0 * (1 << 20)


def _freq_of(block, fnum):
    return (fnum << block) * _MCLK / _MCLK_DIV


_BUILD_CACHE = {}


def _build_fmopn():
    """Return (lib, src_mtime) — compile once per process, cached."""
    mtime = os.stat(FMOPN_C).st_mtime
    if _BUILD_CACHE.get("mtime") == mtime:
        return _BUILD_CACHE["lib"], mtime
    with tempfile.TemporaryDirectory(prefix="fmopn_test_") as tmp:
        so = os.path.join(tmp, "fmopn.so")
        cmd = ["gcc", "-O2", "-shared", "-fPIC", "-I", os.path.dirname(FMOPN_H),
               "-fno-stack-protector", FMOPN_C, "-o", so, "-lm"]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        # dlopen keeps the image alive even though the tempdir is removed on
        # context exit; the cache keeps returning the same loaded CDLL.
        _BUILD_CACHE["lib"] = ctypes.CDLL(so)
        _BUILD_CACHE["mtime"] = mtime
        return _BUILD_CACHE["lib"], mtime


@pytest.fixture(scope="module")
def fmopn():
    lib, _ = _build_fmopn()

    # note/bend ratio
    lib.fmopn_note_ratio.argtypes = [ctypes.c_int,
                                     ctypes.POINTER(ctypes.c_int),
                                     ctypes.POINTER(ctypes.c_int)]
    lib.fmopn_bend_ratio.argtypes = [ctypes.c_int,
                                     ctypes.POINTER(ctypes.c_int),
                                     ctypes.POINTER(ctypes.c_int)]
    lib.fmopn_keyon_value.argtypes = [ctypes.c_int, ctypes.c_int]
    lib.fmopn_keyon_value.restype = ctypes.c_uint8
    lib.fmopn_ssg_period_fine.argtypes = [ctypes.c_int]
    lib.fmopn_ssg_period_fine.restype = ctypes.c_uint8
    lib.fmopn_ssg_period_coarse.argtypes = [ctypes.c_int]
    lib.fmopn_ssg_period_coarse.restype = ctypes.c_uint8
    lib.fmopn_patch_validate.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    lib.fmopn_patch_validate.restype = ctypes.c_int

    for name in ("fmopn_patch_fb_alg", "fmopn_patch_pan"):
        getattr(lib, name).argtypes = [ctypes.POINTER(ctypes.c_uint8)]
        getattr(lib, name).restype = ctypes.c_uint8
    for name in ("fmopn_op_dt_mul", "fmopn_op_tl", "fmopn_op_ks_ar",
                 "fmopn_op_am_d1r", "fmopn_op_d2r", "fmopn_op_sl_rr"):
        getattr(lib, name).argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_int]
        getattr(lib, name).restype = ctypes.c_uint8

    for name in ("fmopn_op_addr", "fmopn_ch_addr"):
        getattr(lib, name).argtypes = [ctypes.c_int, ctypes.c_uint8,
                                       ctypes.POINTER(ctypes.c_int),
                                       ctypes.POINTER(ctypes.c_uint8)]

    return lib


def _ratio(lib, fn_name, *args):
    block = ctypes.c_int()
    fnum = ctypes.c_int()
    fn = getattr(lib, fn_name)
    fn(ctypes.c_int(args[0]), ctypes.byref(block), ctypes.byref(fnum))
    return block.value, fnum.value


def _bent(lib, bend, block0, fnum0):
    block = ctypes.c_int(block0)
    fnum = ctypes.c_int(fnum0)
    lib.fmopn_bend_ratio(ctypes.c_int(bend), ctypes.byref(block), ctypes.byref(fnum))
    return block.value, fnum.value


def test_op_slot_order_pinned():
    """The 1-3-2-4 reorder must stay as defined (silent-pitch-slip guard)."""
    lib, _ = _build_fmopn()
    lib.fmopn_op_slot  # exported data; verify via addr of the symbol
    # ctypes: get the symbol value
    slot_type = ctypes.c_uint8 * 4
    slots = slot_type.in_dll(lib, "fmopn_op_slot")
    assert list(slots) == [0, 2, 1, 3]


def test_all_notes_valid_and_accurate(fmopn):
    chip_max = _freq_of(7, 1023)   # ~6928 Hz: block7/fnum1023 is the ceiling
    prev_freq = None
    for note in range(128):
        block, fnum = _ratio(fmopn, "fmopn_note_ratio", note)
        assert 0 <= block <= 7
        assert 0 <= fnum <= 1023
        got = _freq_of(block, fnum)
        want = 440.0 * math.pow(2.0, (note - 69) / 12.0)
        if want <= chip_max:               # notes below the ceiling: strict
            err = abs(got - want) / want
            assert err <= 0.006, f"note {note}: got {got:.2f} want {want:.2f}"
        else:                              # above: must sit exactly at the cap
            assert block == 7 and fnum == 1023
        if prev_freq is not None:
            assert got >= prev_freq * 0.995  # monotone within tolerance
        prev_freq = got


def test_anchors(fmopn):
    block, fnum = _ratio(fmopn, "fmopn_note_ratio", 69)  # A4
    assert (block, fnum) == (4, 520)
    block, fnum = _ratio(fmopn, "fmopn_note_ratio", 60)  # C4
    assert (block, fnum) == (3, 618)


def test_top_clamp(fmopn):
    block, fnum = _ratio(fmopn, "fmopn_note_ratio", 127)
    assert block == 7
    assert fnum <= 1023


def test_bend_centre_is_neutral(fmopn):
    for note in (30, 69, 90):
        b0, f0 = _ratio(fmopn, "fmopn_note_ratio", note)
        assert _bent(fmopn, 8192, b0, f0) == (b0, f0)


def test_bend_range(fmopn):
    for note in (50, 69, 90):
        b0, f0 = _ratio(fmopn, "fmopn_note_ratio", note)
        base = _freq_of(b0, f0)
        for bend in (0, 4096, 8192, 12288, 16383):
            bb, fn_ = _bent(fmopn, bend, b0, f0)
            got = _freq_of(bb, fn_)
            semis = (bend - 8192) / 8192.0 * 2.0      # +-2 st total
            want = base * math.pow(2.0, semis / 12.0)
            assert abs(got - want) / want <= 0.02, f"note {note} bend {bend}"
        # extremes must actually move
        assert _freq_of(*_bent(fmopn, 16383, b0, f0)) > base * 1.04
        assert _freq_of(*_bent(fmopn, 0, b0, f0)) < base * 0.96


def test_keyon_values(fmopn):
    # ch 0..2 -> 0..2; ch 3..5 -> 4..6
    for ch in range(6):
        want_sel = ch if ch < 3 else 4 + (ch - 3)
        v = fmopn.fmopn_keyon_value(ch, 0x0F)
        assert v == (0xF0 | want_sel)
        v = fmopn.fmopn_keyon_value(ch, 0x01)   # key-only op1
        assert v == (0x10 | want_sel)
    v = fmopn.fmopn_keyon_value(2, 0)          # note off
    assert v == 0x02


def test_ssg_period_split(fmopn):
    assert fmopn.fmopn_ssg_period_fine(0x0BC0) == 0xC0
    assert fmopn.fmopn_ssg_period_coarse(0x0BC0) == 0x0B
    assert fmopn.fmopn_ssg_period_fine(1) == 1
    assert fmopn.fmopn_ssg_period_coarse(1) == 0
    assert fmopn.fmopn_ssg_period_coarse(4095) == 0x0F


def _good_patch():
    """A valid 32-byte patch.  Ops are stored in FILE order 1-3-2-4, i.e.
    file slot k holds chip register slot fmopn_op_slot[k] = {0,2,1,3}.
    Each op has a distinct TL so the file<->chip reorder is observable."""
    p = ctypes.c_uint8 * 32
    b = p()
    # file slot 0 = chip slot 0: dt=2 mul=9, tl=40
    b[0] = 0x29
    b[1] = 40
    b[2] = 0x18                      # KS=0 AR=24
    b[3] = 0x05                      # AM=0 D1R=5
    b[4] = 4
    b[5] = 0x15                      # SL=1 RR=5
    # file slot 1 = chip slot 2: tl=44
    b[6] = 0x18
    b[7] = 44
    b[8] = 0x0C
    b[9] = 0x03
    b[10] = 3
    b[11] = 0x23
    # file slot 2 = chip slot 1: tl=42
    b[12] = 0x0A
    b[13] = 42
    b[14] = 0x10
    b[15] = 0x04
    b[16] = 3
    b[17] = 0x24
    # file slot 3 = chip slot 3: tl=46
    b[18] = 0x30
    b[19] = 46
    b[20] = 0x18
    b[21] = 0x06
    b[22] = 4
    b[23] = 0x16
    b[24] = (5 << 3) | 4             # FB=5 AL=4
    b[25] = 0xC0                     # pan both full
    return b


def test_patch_validate_ok(fmopn):
    b = _good_patch()
    assert fmopn.fmopn_patch_validate(b) == 0


def test_patch_validate_errors(fmopn):
    b = _good_patch()

    bad = ctypes.c_uint8 * 32
    save = b[24]

    # reserved byte
    r = bad(*b)
    r[31] = 1
    assert fmopn.fmopn_patch_validate(r) & 0x01

    # DT > 7
    r = bad(*b)
    r[0] = (0x09 << 4) | 9
    assert fmopn.fmopn_patch_validate(r) & 0x02

    # TL bit7
    r = bad(*b)
    r[1] |= 0x80
    assert fmopn.fmopn_patch_validate(r) & 0x04

    # KS/AR bit5
    r = bad(*b)
    r[2] |= 0x20
    assert fmopn.fmopn_patch_validate(r) & 0x08

    # AM/D1R bits 6-5
    r = bad(*b)
    r[3] |= 0x40
    assert fmopn.fmopn_patch_validate(r) & 0x10

    # D2R bit7
    r = bad(*b)
    r[4] |= 0x80
    assert fmopn.fmopn_patch_validate(r) & 0x20

    # FB/AL bits 7-6
    r = bad(*b)
    r[24] = save | 0xC0
    assert fmopn.fmopn_patch_validate(r) & 0x80

    # PAN low nibble
    r = bad(*b)
    r[25] |= 0x01
    assert fmopn.fmopn_patch_validate(r) & 0x100


def test_patch_accessors(fmopn):
    b = _good_patch()
    assert fmopn.fmopn_patch_fb_alg(b) == (5 << 3) | 4
    assert fmopn.fmopn_patch_pan(b) == 0xC0

    # accessor regslot -> file slot -> byte: the reorder must make chip 0,1,2,3
    # read file slots 0, 2, 1, 3 respectively.
    assert fmopn.fmopn_op_dt_mul(b, 0) == 0x29
    assert fmopn.fmopn_op_tl(b, 0) == 40
    assert fmopn.fmopn_op_ks_ar(b, 0) == 0x18
    assert fmopn.fmopn_op_am_d1r(b, 0) == 0x05
    assert fmopn.fmopn_op_d2r(b, 0) == 4
    assert fmopn.fmopn_op_sl_rr(b, 0) == 0x15

    assert fmopn.fmopn_op_dt_mul(b, 1) == 0x0A
    assert fmopn.fmopn_op_tl(b, 1) == 42
    assert fmopn.fmopn_op_ks_ar(b, 1) == 0x10
    assert fmopn.fmopn_op_am_d1r(b, 1) == 0x04
    assert fmopn.fmopn_op_d2r(b, 1) == 3
    assert fmopn.fmopn_op_sl_rr(b, 1) == 0x24

    assert fmopn.fmopn_op_dt_mul(b, 2) == 0x18
    assert fmopn.fmopn_op_tl(b, 2) == 44

    assert fmopn.fmopn_op_dt_mul(b, 3) == 0x30
    assert fmopn.fmopn_op_tl(b, 3) == 46


def test_register_addressing(fmopn):
    bank = ctypes.c_int()
    addr = ctypes.c_uint8()

    # FM1-3 bank 0, FM4-6 bank 1
    for ch in range(3):
        fmopn.fmopn_op_addr(ch, 0x30, ctypes.byref(bank), ctypes.byref(addr))
        assert bank.value == 0
        assert addr.value == 0x30 + ch
    for ch in range(3, 6):
        fmopn.fmopn_op_addr(ch, 0x30, ctypes.byref(bank), ctypes.byref(addr))
        assert bank.value == 1
        assert addr.value == 0x30 + (ch - 3)

    # channel-level B0/B4
    fmopn.fmopn_ch_addr(4, 0xB4, ctypes.byref(bank), ctypes.byref(addr))
    assert bank.value == 1
    assert addr.value == 0xB4 + 1

    fmopn.fmopn_ch_addr(0, 0xA4, ctypes.byref(bank), ctypes.byref(addr))
    assert bank.value == 0
    assert addr.value == 0xA4