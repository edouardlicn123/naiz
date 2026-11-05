"""P1b shape invariants for the shipped FM patch library (devdocs/136).

Static checks on the *compiled* 32-byte blobs — no oracle needed, fast.  These
guard the structural failure class found in P1a: a patch whose carriers are
all muted (tl=127) renders as pure silence regardless of the note, which is
exactly what `flute.fmp` was before the devdocs/136 op-label fix.
"""

import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, 'tools', 'naiz_audio'))

from naiz_audio import fm_patch  # noqa: E402

FM_DIR = os.path.join(REPO_ROOT, 'assets', 'demo-a2', 'fm')

# Algorithm -> carrier *algorithm operators* (1-indexed).  Carriers are the
# operators that reach the channel output; muting every one = silence.
CARRIERS = {
    0: (4,), 1: (4,), 2: (4,), 3: (4,),
    4: (2, 4),
    5: (2, 3, 4), 6: (2, 3, 4),
    7: (1, 2, 3, 4),
}
# Field offsets inside an operator's 6-byte block.
TL_FIELD = 1
MUL_FIELD = 0


def _patches():
    pats = sorted(glob.glob(os.path.join(FM_DIR, '*.fmp')))
    if not pats:
        raise RuntimeError(f"no .fmp files under {FM_DIR}")
    return pats


def _blob(path):
    return fm_patch.compile_source(path)


def _op_field(blob, op, field):
    """Read a field for algorithm operator `op` (1..4) from the blob.

    File idx k holds operator k+1; the MUL lives in the low nibble of byte 0.
    """
    return blob[(op - 1) * 6 + field]


def _tl(blob, op):
    return _op_field(blob, op, TL_FIELD)


def _alg(blob):
    return blob[24] & 0x07


def test_no_patch_is_silent():
    """Every shipped patch must have at least one unmuted carrier.

    A patch whose carriers are all tl=127 produces zero output for every
    note — the devdocs/136 flute bug.
    """
    for p in _patches():
        blob = _blob(p)
        alg = _alg(blob)
        carries = [op for op in CARRIERS[alg] if _tl(blob, op) < 127]
        assert carries, (
            f"{os.path.basename(p)}: alg={alg} has every carrier muted "
            f"(tl=127) -> silent")


def test_carrier_operators_match_algorithm():
    """The carrier set is derived from the algorithm's source-op numbering,
    which only makes sense because op=N is the algorithm operator (P1a)."""
    # alg4 pairs are op1->op2 and op3->op4: carriers are op2 and op4.
    blob = _blob(os.path.join(FM_DIR, 'flute.fmp'))
    assert _alg(blob) == 4
    assert CARRIERS[4] == (2, 4)


def test_flute_is_fundamental_carried():
    """flute must have an audible fundamental carrier (mul=1), not a
    sustained octave carrier (the pre-c64 'organ stop' bug)."""
    blob = _blob(os.path.join(FM_DIR, 'flute.fmp'))
    alg = _alg(blob)
    carrs = CARRIERS[alg]
    fundamental = [op for op in carrs
                   if _tl(blob, op) < 127 and (_op_field(blob, op, MUL_FIELD) & 0x0F) == 1]
    assert fundamental, (
        "flute: no unmuted fundamental (mul=1) carrier -> thin/octave voice")
    # no carrier may be a sustained high harmonic (mul>=2 with a low SL)
    for op in carrs:
        mul = _op_field(blob, op, MUL_FIELD) & 0x0F
        sl = (blob[(op - 1) * 6 + 5] >> 4) & 0x0F
        assert not (mul >= 2 and sl <= 4), (
            f"flute: carrier op{op} is a sustained octave (mul={mul}, sl={sl})")
