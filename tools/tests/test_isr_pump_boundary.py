"""The Timer-B handler owns the clock only (devdoc 176).

DOS/4GW delivers a hardware IRQ on its own stack segment (measured SS=0x00B0
while the flat data selector is DS=0x0160).  Inside such a handler a write
through a pointer to a *stack local* lands at a bogus linear address, so the
caller keeps a stale value: fmopn_reg_addr()'s bank/addr out-params all came
back as 0 and every FM register write went to register 0x00 -- a silent BGM
that nevertheless looked perfectly busy in a call counter.

The fix keeps the engine out of the handler: it advances the clock and bumps a
global unit counter, and the main thread drains that counter into
audio_tick_isr().  These assertions fail if anyone moves the pump back in.

1. bgm_irq_handler() calls no engine code and does no logging.
2. It only advances the clock and accumulates units.
3. core/plat must not depend on core/engine (no audio_* calls).
4. The main-thread drain exists and every pump entry point uses it.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

HAL_IRQ_C = (ROOT / "core" / "plat" / "hal_irq.c").read_text("utf-8")
AUDIO_C = (ROOT / "core" / "engine" / "audio.c").read_text("utf-8")
FRAME_C = (ROOT / "core" / "engine" / "frame.c").read_text("utf-8")
TRANSITION_C = (ROOT / "core" / "engine" / "transition.c").read_text("utf-8")


def _strip_comments(src):
    """Drop C comments so prose mentioning engine calls is not mistaken for a
    call (the handler's own comment names audio_tick_isr_pending())."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def _func_body(src, name):
    """Text of a C function body, from its opening brace to column-0 '}'."""
    m = re.search(r"^\w[\w \*]*\b%s\s*\([^;]*?\)\s*\{" % re.escape(name),
                  src, re.M)
    if not m:
        raise AssertionError(f"function {name}() not found")
    start = m.end() - 1
    end = src.index("\n}\n", start)
    return src[start:end]


# --- 1. no engine work inside the handler --------------------------------

def test_handler_runs_no_engine_code():
    body = _strip_comments(_func_body(HAL_IRQ_C, "bgm_irq_handler"))
    for forbidden in ("audio_tick_isr(", "audio_tick(", "fmseq", "hal_log"):
        assert forbidden not in body, (
            f"bgm_irq_handler() must not run {forbidden!r}: DOS/4GW gives the "
            "IRQ its own stack segment, where pointer-to-stack writes are lost "
            "(devdoc 176)"
        )


# --- 2. clock + unit counter only ----------------------------------------

def test_handler_advances_clock_and_counts_units():
    body = _func_body(HAL_IRQ_C, "bgm_irq_handler")
    assert "hal_wallclock_fixed_advance(BGM_TIMER_B_UNITS)" in body
    assert "g_irq_units_total += BGM_TIMER_B_UNITS" in body


# --- 3. platform layer must not call into the engine ---------------------

def test_hal_irq_does_not_call_engine():
    assert '#include "audio.h"' not in HAL_IRQ_C
    calls = re.findall(r"\baudio_\w+\s*\(", _strip_comments(HAL_IRQ_C))
    assert not calls, f"hal_irq.c calls engine code: {sorted(set(calls))}"


# --- 4. the pump runs on the main stack ---------------------------------

def test_pending_units_are_drained_on_the_main_thread():
    assert "void audio_tick_isr_pending(void)" in AUDIO_C
    drain = _func_body(AUDIO_C, "audio_tick_isr_pending")
    assert "hal_bgm_irq_take_pending_units()" in drain
    assert "audio_tick_isr(units)" in drain

    # Every path that can advance the audio during the ISR-owned mode must
    # drain, otherwise BGM stalls in that phase (main loop, decode, transition).
    for name, src in (("frame.c", FRAME_C), ("transition.c", TRANSITION_C)):
        assert "audio_tick_isr_pending()" in src, (
            f"{name} never drains the Timer-B pending units (devdoc 176)"
        )


def test_pending_units_use_a_main_thread_cursor():
    """The drain must not mask interrupts: a consumed cursor written only by
    the main thread makes the read/clear race-free on this target."""
    drain = _func_body(HAL_IRQ_C, "hal_bgm_irq_take_pending_units")
    assert "g_irq_units_total" in drain
    assert "consumed" in drain
    assert "_disable(" not in drain and "_enable(" not in drain
