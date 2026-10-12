"""Frame pump + MAG progress-hook contract guard (devdoc 129).

Symptom: the formal BGM was audible but audibly stuttering, froze for the
whole time a `question` screen was open, and dropped out during the first
`char`/`cg` decode of a scene.

Three independent root causes, one contract each:

1.  **`hal_wallclock_smooth_advance()` is the sole writer of the virtual
    clock.**  `hal_wallclock_smooth_ms()` used to ADVANCE the clock by a
    bounded delta on every call, and three consumers (`audio_tick`,
    `nb_dialog_reveal_tick`, `anim_tick`) each polled it — so the BGM tempo
    was literally (calls per pass) x (passes per second).  Blocked in a
    menu, zero calls, the clock stalled; with the typewriter polling, 2-3
    calls per pass and the clock raced.  The split makes the clock
    independent of the caller count, which is what makes `audio_tick()`
    idempotent within a frame and the decode hook safe.

2.  **`engine_frame_pump()` exists and is called by every self-contained
    input loop.**  A loop that spins without it never advances BGM/PCM/
    typewriter/animation — the "question stops the music" bug.  Each loop
    in devdoc 129 §2.1 must call the pump.

3.  **`mag_set_progress_hook()` pumps audio from inside the decoder.**
    `mag.c` is a platform-agnostic lib and may not call into the engine,
    so the hook is the bridge.  There are FOUR call sites — the RLE loop
    and the 4bpp expand loop, on both the heap (`mag_decode`) and pool
    (`mag_decode_into`) ownership paths — and `audio_init()` must register
    the hook.  Missing any one of them re-freezes BGM in exactly one path.

These tests parse the C sources; a regression that unfreezes the clock,
drops a frame_pump from a blocking loop, or removes one decode call site
fails here.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HAL_H = ROOT / "core" / "plat" / "hal.h"
HAL_PC98_C = ROOT / "core" / "plat" / "hal_pc98.c"
FRAME_C = ROOT / "core" / "engine" / "frame.c"
FRAME_H = ROOT / "core" / "engine" / "frame.h"
MAG_C = ROOT / "core" / "lib" / "mag.c"
MAG_H = ROOT / "core" / "lib" / "mag.h"
AUDIO_C = ROOT / "core" / "engine" / "audio.c"
VCLOCK_H = ROOT / "core" / "lib" / "vclock.h"

# Every self-contained input loop from devdoc 129 §2.1 plus main.c's three.
# A loop missing here is a loop that freezes BGM.
PUMP_CALLERS = [
    ("core/engine/main.c", 3),
    ("core/engine/nb_interact.c", 1),
    ("core/engine/nb_menu.c", 1),
    ("core/engine/nb_setting.c", 1),
    ("core/engine/nb_saveload.c", 1),
    ("core/engine/nb_save_dialog.c", 1),
    ("core/engine/nb_cggallery.c", 2),
    ("core/engine/nb_special.c", 1),
]


def _src(rel):
    p = ROOT / rel
    assert p.exists(), f"{rel} is missing"
    return p.read_text(encoding="utf-8")


def _func_body(src, name):
    """Return the body of the first definition of `name` in `src`."""
    m = re.search(r"(?:^|\n)[ \t\w\*]*\b" + re.escape(name) +
                  r"\s*\([^)]*\)\s*\n?\{", src)
    assert m, f"function {name}() not found"
    start = src.index("{", m.start())
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError(f"{name}(): unbalanced braces")


# --- 1. clock ownership: one writer, readers side-effect free ---------------

def test_smooth_advance_is_the_only_clock_writer():
    """The reader must be a plain read of vclock, and the writer must go
    through it.  The accumulator itself moved into lib/vclock (devdoc 129
    follow-up); what must hold is the split, not where the += lives."""
    c = HAL_PC98_C.read_text(encoding="utf-8")
    body = _func_body(c, "hal_wallclock_smooth_ms")
    assert "vclock_ms" in body, "reader must delegate to vclock"
    for bad in ("+=", "delta", "hal_wallclock_ms", "vclock_advance"):
        assert bad not in body, (
            f"hal_wallclock_smooth_ms() still moves the clock ({bad!r})"
        )


def test_smooth_advance_owns_the_step():
    c = HAL_PC98_C.read_text(encoding="utf-8")
    body = _func_body(c, "hal_wallclock_smooth_advance")
    assert "vclock_advance" in body, (
        "hal_wallclock_smooth_advance() must be the only writer path"
    )
    # exactly one vclock state, and nothing else pokes the accumulator
    assert c.count("VClock g_vclock") == 1, "vclock state must be a single instance"
    assert "vclock_advance" in body, "advance must go through vclock"


def test_smooth_step_is_slewed_not_clamped(monkeypatch=None):
    """The flutter defect: a floor/ceiling clamp on the step.

    The smoothing policy lives in lib/vclock; this pins that the old clamp
    constants are gone and the slew bound is what bounds the step, so the
    BGM's note onsets stay evenly spaced (devdoc 129 follow-up).
    """
    h = HAL_H.read_text(encoding="utf-8")
    for dead in ("SMOOTH_CLOCK_MIN_MS", "SMOOTH_CLOCK_MAX_MS"):
        assert dead not in h, f"{dead} (the flutter-causing clamp) is back in hal.h"
    vh = VCLOCK_H.read_text(encoding="utf-8")
    assert "VCLOCK_SLEW_UNITS" in vh, "vclock must bound step change via the slew"


def test_smooth_advance_is_declared_in_hal_h():
    assert "void hal_wallclock_smooth_advance(void)" in HAL_H.read_text(
        encoding="utf-8")


# --- 2. the frame pump and its call sites -----------------------------------

def test_frame_pump_sequence_is_exact():
    """vblank, clock, anim, audio, reveal — in that order, nothing dropped.

    Order matters twice: the clock must land BEFORE the consumers read it,
    and vblank_wait() must come first so the CPU yields at least once.
    """
    body = _func_body(FRAME_C.read_text(encoding="utf-8"), "engine_frame_pump")
    order = [call for call in ("vblank_wait()",
                               "hal_wallclock_smooth_advance()",
                               "anim_tick()",
                               "audio_tick()",
                               "nb_dialog_reveal_tick()")
             if call in body]
    assert order == ["vblank_wait()", "hal_wallclock_smooth_advance()",
                     "anim_tick()", "audio_tick()",
                     "nb_dialog_reveal_tick()"], (
        f"frame pump drifted (missing or reordered): {order}")


def test_every_blocking_loop_pumps_frames():
    """No self-contained input loop may spin without the pump (devdoc 129 §2.1)."""
    for rel, expected in PUMP_CALLERS:
        n = _src(rel).count("engine_frame_pump();")
        assert n == expected, (
            f"{rel} calls engine_frame_pump() {n}x, expected {expected}"
        )


# --- 3. decode progress hook: four sites, one registration ------------------

def test_mag_progress_hook_api_exists():
    h = MAG_H.read_text(encoding="utf-8")
    assert "void mag_set_progress_hook(void (*fn)(void))" in h
    c = MAG_C.read_text(encoding="utf-8")
    assert "MAG_PROGRESS_STRIDE" in c, "stride constant missing"
    assert re.search(r"static\s+void\s*\(\*g_mag_progress_hook\)\(void\)",
                     c), "hook storage missing"


def test_decode_has_four_pump_sites():
    """RLE loop + 4bpp expand loop, on BOTH the heap and the pool path.

    Losing one site re-freezes BGM on exactly one decode path.
    """
    c = MAG_C.read_text(encoding="utf-8")
    assert c.count("g_mag_progress_hook();") == 4, (
        f"expected 4 decode pump sites, found {c.count('g_mag_progress_hook();')}"
    )
    # ...and they must live in both decoders, not one four times.
    heap = _func_body(c, "mag_decode")
    pool = _func_body(c, "mag_decode_into")
    assert heap.count("g_mag_progress_hook();") == 2, "mag_decode lost a pump site"
    assert pool.count("g_mag_progress_hook();") == 2, "mag_decode_into lost a pump site"


def test_hook_is_null_guarded_and_bounded():
    """An unset hook must cost nothing, and a set hook must not spin forever."""
    c = MAG_C.read_text(encoding="utf-8")
    for guard in ("if (g_mag_progress_hook && _prog >= MAG_PROGRESS_STRIDE)",
                  "if (g_mag_progress_hook && (i % MAG_PROGRESS_STRIDE) == "
                  "(MAG_PROGRESS_STRIDE - 1))"):
        assert guard in c, f"missing stride guard: {guard}"
    assert "_prog = 0;" in c, "progress counter is never reset — stride fires once"


def test_engine_registers_the_hook_in_audio_init():
    """audio_init() must install the pump, else the hook is dead code."""
    body = _func_body(AUDIO_C.read_text(encoding="utf-8"), "audio_init")
    assert "mag_set_progress_hook(audio_tick)" in body, (
        "audio_init() no longer routes mag decode progress into audio_tick()"
    )
