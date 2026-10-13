"""vclock host tests (devdoc 129 follow-up: BGM flutter fix).

Compiles core/lib/vclock.c with the host gcc into a temp shared object and
drives it through ctypes.  The module is pure integer arithmetic (no I/O, no
platform calls), so the whole state machine — including the NP2kai
cluster-delivery shape that caused the flutter — is provable here without an
emulator.

What is pinned:

  STEADY BEAT (the defect).  The old floor/ceiling clamp alternated a 40ms
  step and a 100ms step, a 2.5:1 ratio, which is what the ear heard as
  flutter.  Successive advances here must differ by at most VCLOCK_SLEW_UNITS
  so the BGM's note onsets land evenly.

  NO STALL.  A frozen platform clock (NP2kai's quantised seconds) must keep
  producing advances — that was the original "BGM stops" bug.

  NO BURST.  A platform jump after a frozen stretch must be drained across
  the passes it covers, not dumped into one pass.

  CORRECT TEMPO.  Over a run, the virtual total must track real elapsed time,
  so a song neither creeps nor races.

devdoc 133 added two fixes for the residual flutter the first design left:

  ADOPT THE FIRST WINDOW.  The step used to start at a nominal 640 units and
  slew to the measured rate, so a song played off-tempo for the first seconds
  ("starts fast then settles").  The first closed window is now adopted
  outright.

  SMOOTH THE MEASUREMENT.  The DOS second is quantised, so one window's
  `want` jitters by ~1/passes (~5% at 20 passes); chasing it every window was
  itself the audible flutter.  Later windows now move the target only a
  fraction of the way to each reading.
"""
import ctypes
import os
import subprocess
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VCLOCK_C = os.path.join(REPO_ROOT, "core", "lib", "vclock.c")
VCLOCK_H = os.path.join(REPO_ROOT, "core", "lib", "vclock.h")

UNITS = 16
SLEW = 8
INIT_STEP = 640
MAX_ADV_MS = 100
RATE_MIN_MS = 1
RATE_MAX_MS = 100

_BUILD_CACHE = {}


def _build_vclock():
    """Return a CDLL, compiled once per source mtime."""
    mtime = os.stat(VCLOCK_C).st_mtime
    if _BUILD_CACHE.get("mtime") == mtime:
        return _BUILD_CACHE["lib"]
    with tempfile.TemporaryDirectory(prefix="vclock_test_") as tmp:
        so = os.path.join(tmp, "vclock.so")
        cmd = ["gcc", "-O2", "-std=c99", "-Wall", "-Wextra", "-shared",
               "-fPIC", "-I", os.path.dirname(VCLOCK_H),
               VCLOCK_C, "-o", so]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0, f"vclock.c failed to compile:\n{proc.stderr}"
        lib = ctypes.CDLL(so)
        _BUILD_CACHE["lib"] = lib
        _BUILD_CACHE["mtime"] = mtime
    return lib


def _make_clock():
    lib = _build_vclock()

    class VClockT(ctypes.Structure):
        _fields_ = [
            ("virtual", ctypes.c_ulong),
            ("real_prev", ctypes.c_ulong),
            ("step", ctypes.c_ulong),
            ("target", ctypes.c_ulong),
            ("passes", ctypes.c_ulong),
            ("accum", ctypes.c_ulong),
            ("started", ctypes.c_int),
            ("calibrated", ctypes.c_int),
        ]

    lib.vclock_init.argtypes = [ctypes.POINTER(VClockT)]
    lib.vclock_init.restype = None
    lib.vclock_advance.argtypes = [ctypes.POINTER(VClockT), ctypes.c_ulong]
    lib.vclock_advance.restype = None
    lib.vclock_ms.argtypes = [ctypes.POINTER(VClockT)]
    lib.vclock_ms.restype = ctypes.c_ulong

    vc = VClockT()
    lib.vclock_init(ctypes.byref(vc))
    return lib, vc


def _run(reals):
    """Advance through readings, return (ms_trace, unit_steps)."""
    lib, vc = _make_clock()
    steps, ms = [], []
    for r in reals:
        lib.vclock_advance(ctypes.byref(vc), r)
        ms.append(lib.vclock_ms(ctypes.byref(vc)))
    before = 0
    for v in ms:
        steps.append(v - before)
        before = v
    return ms, steps, lib, vc


def _np2kai(passes, hz=25, tick_ms=1000):
    """Real readings for `passes` frames under NP2kai's quantised DOS clock.

    The clock reading is held for a whole real second (frames at `hz`), then
    jumps by tick_ms.  Returns readings that stay monotone.
    """
    frames_per_tick = max(1, int(round(hz * tick_ms / 1000.0)))
    out = []
    t = 0
    ticks = 0
    for i in range(passes):
        if i and i % frames_per_tick == 0:
            ticks += 1
            t += tick_ms
        out.append(t)
    return out


def _rate_change_run():
    """A monotone reading sequence whose pass rate drops mid-run.

    25Hz for a stretch, then 10Hz, without ever going backwards.  The reading
    only moves when a quantised second lands, so the pass rate is inferred
    from the number of frames between consecutive movements.
    """
    out = []
    t = 0
    # 25Hz: 100 frames, one second's worth
    for i in range(100):
        if i and i % 25 == 0:
            t += 1000
        out.append(t)
    # 10Hz from here on: 100 frames, ten seconds' worth of reading movement
    for i in range(100):
        if i and i % 10 == 0:
            t += 1000
        out.append(t)
    return out


# --- 1. the defect: step uniformity -----------------------------------------

def test_successive_advances_differ_by_at_most_the_slew():
    """The actual flutter defect: the old clamp alternated 40ms and 100ms."""
    reals = _np2kai(300, hz=25)
    ms, steps, lib, vc = _run(reals)
    body = steps[1:]                      # skip the baseline pass
    assert body, "no advances emitted"
    assert max(body) - min(body) <= 1, (
        f"ms steps vary by {max(body) - min(body)}: {sorted(set(body))}")


def test_frozen_clock_still_advances():
    """No stall: the original 'BGM stops in menus' bug must not return."""
    lib, vc = _make_clock()
    lib.vclock_advance(ctypes.byref(vc), 0)          # origin
    seen = [lib.vclock_ms(ctypes.byref(vc))]
    for _ in range(50):
        lib.vclock_advance(ctypes.byref(vc), 0)      # clock frozen
        seen.append(lib.vclock_ms(ctypes.byref(vc)))
    assert seen[-1] > 0, "clock stalled while the platform reported no time"
    deltas = [b - a for a, b in zip(seen[1:], seen[2:])]
    assert len(set(deltas)) == 1, f"frozen-clock beat is uneven: {deltas}"


def test_jump_is_not_dumped_in_one_pass():
    lib, vc = _make_clock()
    lib.vclock_advance(ctypes.byref(vc), 0)
    reals = [0] * 24 + [1000]
    ms, steps, _, _ = _run(reals)
    assert max(steps) <= MAX_ADV_MS, f"burst: {max(steps)}ms in one pass"


def test_rate_change_converges_without_lurch():
    """A big pass-rate change must converge gradually, never in one advance.

    The step size is *allowed* to move while converging — that is the whole
    point of the slew — so the assertion is on the maximum change of the
    emitted advance between consecutive passes, not on the total range.

    Note the reading sequence must stay monotone: concatenating two
    independently-generated runs would go backwards and exercise the wrap
    path, which is a different property (tested separately).
    """
    reals = _rate_change_run()
    lib, vc = _make_clock()
    units = []
    prev = 0
    for r in reals:
        lib.vclock_advance(ctypes.byref(vc), r)
        units.append(vc.virtual - prev)
        prev = vc.virtual
    body = units[1:]            # skip the baseline pass
    assert body, "no advances emitted"
    worst = max(abs(a - b) for a, b in zip(body, body[1:]))
    assert worst <= SLEW, (
        f"one pass changed the advance by {worst} units (slew={SLEW}): "
        "the clock lurched instead of converging")


# --- 2. tempo correctness ---------------------------------------------------

def test_long_run_tracks_real_time():
    lib, vc = _make_clock()
    lib.vclock_advance(ctypes.byref(vc), 0)
    reals = _np2kai(2000, hz=25)
    lib, vc = _make_clock()
    ms, steps, _, _ = _run(reals)
    real = reals[-1]
    # virtual should be within a few percent of real after a long run
    assert ms[-1] > real * 0.9, f"stalled: {ms[-1]} vs real {real}"
    assert ms[-1] < real * 1.1, f"raced ahead: {ms[-1]} vs real {real}"


def test_tempo_at_various_pass_rates():
    for hz in (15, 20, 25, 30):
        reals = _np2kai(1000, hz=hz)
        ms, steps, lib, vc = _run(reals)
        real = reals[-1]
        assert ms[-1] > real * 0.95, f"hz={hz}: stalled {ms[-1]} vs {real}"
        assert ms[-1] < real * 1.05, f"hz={hz}: raced {ms[-1]} vs {real}"


def test_no_runaway_when_platform_never_moves():
    """A frozen platform must keep a bounded, steady beat — never a stall,
    and never more than one nominal step per pass."""
    lib, vc = _make_clock()
    lib.vclock_advance(ctypes.byref(vc), 7)
    for _ in range(500):
        lib.vclock_advance(ctypes.byref(vc), 7)
    got = lib.vclock_ms(ctypes.byref(vc))
    # 500 passes x the nominal 40ms step = 20s: a steady beat, exactly what
    # keeps the BGM alive through a frozen clock.  Bounded, so not runaway.
    assert got == 500 * (INIT_STEP // UNITS), f"unexpected beat: {got}ms"


def test_backwards_reading_resynchronises():
    lib, vc = _make_clock()
    lib.vclock_advance(ctypes.byref(vc), 5000)
    lib.vclock_advance(ctypes.byref(vc), 10)     # impossible: went back
    got = lib.vclock_ms(ctypes.byref(vc))
    assert got <= 200, f"wrap produced {got}ms"


def test_init_is_zero_and_baseline_does_not_advance():
    lib, vc = _make_clock()
    assert lib.vclock_ms(ctypes.byref(vc)) == 0
    lib.vclock_advance(ctypes.byref(vc), 12345)
    assert lib.vclock_ms(ctypes.byref(vc)) == 0, "baseline pass must not advance"


# --- 3. devdoc 133: adopt the first window, smooth the rest -----------------

def _quantised_windows(sizes, tick_ms=1000):
    """Real readings where window k spans `sizes[k]` passes then ticks.

    Mirrors NP2kai: the DOS second is held flat and then delivered as one
    +tick_ms jump on the pass that closes the window.
    """
    out = []
    t = 0
    for size in sizes:
        for i in range(size):
            if i == size - 1:
                t += tick_ms
            out.append(t)
    return out


def test_first_window_is_adopted_not_ramped():
    """devdoc 133 §2.1: the first measured window must set the step outright.

    The old design started at VCLOCK_INIT_STEP_UNITS (640) and slewed to the
    measured rate, so a song played off-tempo for the first seconds.  15 passes
    per second is a 66.7 ms true step (1066 units), far from 640 -- if it is
    adopted, the step equals that on the closing pass itself, not several
    passes later.
    """
    reals = _np2kai(150, hz=15)          # 15 frames per delivered second
    lib, vc = _make_clock()
    adopted = None
    for r in reals:
        lib.vclock_advance(ctypes.byref(vc), r)
        if vc.calibrated:
            adopted = vc.step
            break
    want = 16000 // 15                    # 1066 units
    assert adopted == want, (
        f"first window not adopted outright: step={adopted}, want={want}")
    assert adopted != INIT_STEP, "step is still the nominal priming constant"


def test_quantised_jitter_is_smoothed():
    """devdoc 133 §2.2: the measured-rate jitter must not reach the step.

    Alternating 20/21-pass windows make `want` swing between 800 and 762 units
    (a ~5% jitter).  Without smoothing the step chases each reading and the
    beat wobbles (range ~38 units); with the IIR it stays near the average.
    """
    reals = _quantised_windows([20, 21] * 60)
    lib, vc = _make_clock()
    steps = []
    for r in reals:
        lib.vclock_advance(ctypes.byref(vc), r)
        steps.append(vc.step)
    body = steps[1000:]                   # well past the first-window adoption
    assert body, "no advances emitted"
    spread = max(body) - min(body)
    assert spread <= 24, (
        f"step swings by {spread} units chasing quantisation jitter: "
        f"{sorted(set(body))}")


def test_a_stalled_window_does_not_move_the_rate():
    """devdoc 133: a window that a single pass swallowed measures one pass per
    second -- real, but unrepresentative.  It must not slow the clock."""
    reals = _quantised_windows([20])      # first window adopts some rate
    lib, vc = _make_clock()
    for r in reals:
        lib.vclock_advance(ctypes.byref(vc), r)
    cal = vc.target
    lib.vclock_advance(ctypes.byref(vc), reals[-1] + 1000)  # one pass, one second
    assert vc.target == cal, (
        f"a one-pass window moved the target {cal} -> {vc.target}")
    assert vc.step == cal, f"the clock slowed to {vc.step}"
