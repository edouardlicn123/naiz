"""Naiz Queue contract guard (devdoc 177).

The engine used to execute one job at a time: the scene transition owned a
`for (frame...) hal_vblank_wait()` loop, the script interpreter sat out the
whole sweep, and every image/BGM the next scene needed was read + parsed on
the first frame that showed it.  devdoc 177 splits the work into three layers
and these tests pin the split:

* Layer 0 — the Timer-B ISR is the sole clock writer; its accumulated units
  are drained on the main thread in <= one hardware period per call, with a
  timestamp that keeps advancing inside the drain (no time bunched at `now`).
* Layer 1 — production is decoupled from consumption: the transition becomes
  an armed state machine stepped once per frame, the interpreter is gated on
  it, and a preload queue decodes the incoming scene's assets behind the
  sweep.  The image cache grows to hold a whole scene and gains a `ready` bit
  so a half-filled slot can never be served.
* Layer 2 — `engine_frame_pump()` stays the single `vblank_wait()` point; the
  new steps are appended after the existing ticks.

Any of these reverting re-introduces a blocking sweep or an on-demand decode
stall, so each is asserted against the C sources.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
AUDIO_C = ROOT / "core" / "engine" / "audio.c"
AUDIO_H = ROOT / "core" / "engine" / "audio.h"
HAL_H = ROOT / "core" / "plat" / "hal.h"
TRANSITION_C = ROOT / "core" / "engine" / "transition.c"
TRANSITION_H = ROOT / "core" / "engine" / "transition.h"
IMAGE_CACHE_C = ROOT / "core" / "engine" / "image_cache.c"
FRAME_C = ROOT / "core" / "engine" / "frame.c"
NB_C = ROOT / "core" / "engine" / "nb.c"
PRELOAD_C = ROOT / "core" / "engine" / "preload_queue.c"
PRELOAD_H = ROOT / "core" / "engine" / "preload_queue.h"


def _src(path):
    assert path.exists(), f"{path.name} is missing"
    return path.read_text(encoding="utf-8")


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


# --- Layer 0: split drain ---------------------------------------------------

def test_audio_tick_isr_carries_an_absolute_timestamp():
    """The drain replays many periods in one call, so each sub-tick needs its
    own timestamp; without now_ms_abs the whole batch would be scheduled at the
    same instant and the BGM would bunch up."""
    assert "void audio_tick_isr(unsigned long delta_units, unsigned long now_ms_abs)" \
        in _src(AUDIO_H), "audio.h must declare the two-argument audio_tick_isr()"
    body = _func_body(_src(AUDIO_C), "audio_tick_isr")
    assert "now_ms_abs" in body, "audio_tick_isr() must consume the timestamp"
    assert "delta_units" in body, "audio_tick_isr() must consume the unit delta"


def test_isr_pending_drains_in_bounded_periods():
    """One call must never replay more than a hardware period at a time while
    loop capacity remains (a slow frame can have banked dozens), and the
    timestamp must advance with each replayed period instead of staying at
    `now` for the whole batch."""
    c = _src(AUDIO_C)
    body = _func_body(c, "audio_tick_isr_pending")
    assert "while (units > AUDIO_ISR_PERIOD_UNITS)" in body, (
        "the drain must loop over banked units in bounded periods")
    assert "BGM_TIMER_B_UNITS" in c, (
        "AUDIO_ISR_PERIOD_UNITS must derive from the hardware period")
    assert re.search(r"start\s*\+=\s*AUDIO_ISR_PERIOD_UNITS\s*/\s*16UL", body), (
        "each replayed period must advance the sub-tick timestamp")
    assert re.search(r"audio_tick_isr\(units,\s*now\)", body), (
        "the remainder must be drained with the live timestamp")


# --- Layer 1: transition state machine --------------------------------------

def test_transition_is_started_and_ticked_not_looped():
    """transition_run()'s blocking for-loop owned a vblank_wait per step and
    starved the preload queue; the state machine renders one step per frame."""
    c = _src(TRANSITION_C)
    h = _src(TRANSITION_H)
    for decl in ("void transition_start(", "void transition_tick(void)",
                 "int transition_active(void)"):
        assert decl in h, f"transition.h must declare {decl}"
    assert "transition_run" not in h and "transition_run" not in c, (
        "transition_run() must be gone (devdoc 177)")
    assert not re.search(r"for\s*\([^)]*frame", c), (
        "transition.c must not loop over frames; one step per pump call")
    tick = _func_body(c, "transition_tick")
    assert "g_transition.active = 0;" in tick, "the last step must disarm"
    assert "vm_request_process()" in tick, (
        "the last step must wake the gated script interpreter")
    assert "fill_rect(" in tick and "palette_set_all(" in tick, (
        "the final frame must black the palette and paint the covered rect "
        "(this moved out of scene_end())")


def test_interpreter_is_gated_on_the_transition():
    """nb_process() must not execute the new script while the sweep is armed,
    and must NOT use vm_pause_process(): the non-AUTOEXIT input-wait loop only
    breaks on input, so a cleared VMFLAG_PROCESS would hang until a keypress.
    `break` is the established idiom (see the display-yield branch)."""
    body = _func_body(_src(NB_C), "nb_process")
    m = re.search(r"if \(transition_active\(\)\) \{([^}]*)\}", body)
    assert m, "nb_process() must gate on transition_active()"
    assert "break;" in m.group(1), (
        "the gate must break out of the command loop while a sweep is armed")
    assert "vm_pause_process" not in m.group(1), (
        "the transition gate must not clear VMFLAG_PROCESS (input-wait hang)")


# --- Layer 1: image cache capacity + readiness ------------------------------

def test_image_cache_holds_a_scene_and_never_serves_partial_slots():
    c = _src(IMAGE_CACHE_C)
    m = re.search(r"#define IMAGE_CACHE_SLOTS (\d+)", c)
    assert m and int(m.group(1)) >= 32, (
        "the cache must hold a whole preloaded scene (>= 32 slots)")
    assert re.search(r"int\s+ready;", c), "slots must carry a ready bit"
    lookup = _func_body(c, "image_cache_lookup")
    assert re.search(r"if \(!g_image_cache\[i\]\.ready\)\s*\n\s*return NULL;", lookup), (
        "lookup() must treat a not-ready slot as a miss")


# --- Layer 1: preload queue wiring ------------------------------------------

def test_preload_queue_api_exists():
    h = _src(PRELOAD_H)
    for decl in ("void preload_queue_init(void)", "int preload_step(void)",
                 "int preload_pending(void)"):
        assert decl in h, f"preload_queue.h must declare {decl}"
    assert re.search(r"#define PRELOAD_QUEUE_CAP (\d+)", h), (
        "the queue must have a fixed capacity (no heap growth)")
    body = _func_body(_src(PRELOAD_C), "preload_step")
    assert "image_prefetch(" in body, (
        "preload_step() must decode through image_prefetch()")
    assert re.search(r"return image_prefetch\(\(unsigned short\)id\) == 0;", body), (
        "preload_step() must report success/failure so a failure stops the "
        "frame's consumption (Tier 1 heap guard)")


def test_scene_preload_is_queued_before_the_transition_and_drained_by_the_pump():
    """The incoming script's assets must be queued in nb_load() before
    scene_end() arms the sweep, and the frame pump must drain the queue after
    its existing ticks -- that ordering is the whole point of the split."""
    nb = _src(NB_C)
    load = _func_body(nb, "nb_load")
    i_queue = load.find("nb_preload_scene();")
    i_end = load.find("scene_end(")
    assert i_queue != -1, "nb_load() must call nb_preload_scene()"
    assert i_end != -1 and i_queue < i_end, (
        "the preload must be queued BEFORE scene_end() arms the transition")

    pump = _func_body(_src(FRAME_C), "engine_frame_pump")
    i_reveal = pump.find("nb_dialog_reveal_tick();")
    i_tick = pump.find("transition_tick();")
    i_pre = pump.find("preload_step()")
    assert i_reveal != -1 and i_tick != -1 and i_pre != -1, (
        "the pump must keep its reveal tick and add transition/preload steps")
    assert i_reveal < i_pre and i_tick < i_pre, (
        "preload_step() must run after the reveal and transition ticks")
    assert "vblank_wait()" in pump[:i_reveal], (
        "the pump must stay the single vblank_wait() point")


# --- Layer 1: BGM preload ---------------------------------------------------

def test_bgm_is_parsed_in_the_preload_window():
    """A scene's BGM must be read + parsed while the transition covers the
    screen, and audio_bgm_start() must adopt that table instead of reading the
    archive on the frame the music starts."""
    h = _src(AUDIO_H)
    assert "void audio_preload_bgm(const char *key)" in h, (
        "audio.h must declare audio_preload_bgm()")
    c = _src(AUDIO_C)
    pre = _func_body(c, "audio_preload_bgm")
    assert "bgm_load_events(" in pre, (
        "the preload must share the archive/MIDI path with audio_bgm_start()")
    assert "g_bgm_pre" in pre and "midi_free(" in pre, (
        "the preload cache must be single-entry and replaced without leaking")
    start = _func_body(c, "audio_bgm_start")
    assert "g_bgm_pre.ev" in start and "g_bgm_pre.ev = NULL;" in start, (
        "audio_bgm_start() must adopt the staged table and consume the cache")
    nb = _src(NB_C)
    assert "audio_preload_bgm(args[brace]);" in _func_body(nb, "nb_preload_scene"), (
        "nb_preload_scene() must hand bgm keys to audio_preload_bgm()")
