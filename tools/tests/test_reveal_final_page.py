"""Typewriter reveal regression guard (devdoc 105 / 0.2.127 + 0.2.128 +
0.2.130, devdoc 106 plan A+ / 0.2.133).

Five bug classes are frozen here:

1. Root cause (0.2.127): dialog_show() sets dialog_state.text = NULL on the
   final (or single) page, and nb_dialog_reveal_tick() used to abort with
   ``if (!dialog_state.text) return;`` — the body of a single-line dialogue
   never appeared.  The reveal must be driven purely by the page byte bounds
   (page_start/page_end of dialog_text_buf), never by the text pointer state.

2. Pacing (0.2.128): the reveal used a fixed "per-call +speed, every 60 calls
   = 1 char" accumulator that assumed a 60Hz pass rate — but under NP2kai the
   real pass rate is ~20Hz (devdoc 82), so the 64/s tier only typed ~21 chars/s.
   The reveal must pace off a wall clock (hal_wallclock_ms, the same
   mechanism anim_tick uses, later backed by vblank frames) so tier N means
   exactly N chars/sec.

3. Clock source (0.2.130): first the PIT ports 0x71/0x77 were used — an NP2kai
   probe proved they read back `nevent_getremain(NEVENT_ITIMER)/pccore.multiple`,
   a value driven by the emulated CPU clock, not wall time.  A vblank frame
   counter was tried next, but NP2kai's pass rate of ~20.5Hz (devdoc 82) only
   advanced ~342ms of clock per real second (3x slowdown).  The wall clock is
   therefore DOS system time (INT 21h AH=2Ch, 10ms granularity), pushed
   through int386() exactly like the CRT BIOS INT 18h calls in video.c; see
   the dedicated test below.

4. Micro-beat jitter (devdoc 106 / 0.2.133, virtual clock sunk to the HAL
   in devdoc 107 / 0.2.134): the incremental accumulator directly consumed
   raw per-pass wall-clock deltas.  An NP2kai serial probe proved that clock
   is whole-second quantized (dl=0 every sample) and delivered in chunks
   (frozen 3-6 real seconds, then a +1000..+6000ms jump), so the
   delta-driven reveal froze and then burst out the whole page.  The reveal
   must therefore recompute an ABSOLUTE expected position per pass
   (speed * elapsed / 1000 from a page baseline — no reveal_ms_frac
   accumulator), driven by a VIRTUAL clock whose per-pass delta is bounded
   (stall floor / catch-up ceiling).  Since 0.2.134 that virtual clock is the
   single HAL source hal_wallclock_smooth_ms() (SMOOTH_CLOCK_MIN/MAX_MS in
   hal.h), shared by typewriter / animation / BGM — the per-module local
   boxing (REVEAL_PASS_*) must not be reintroduced.

5. The "advance at least one char per call" conflation: a blanket per-frame
   floor is forbidden; the virtual-clock floor is a TIME bound (ms), not a
   char-per-call override, so the 16/32/64 speed tiers still set the rate.

These tests parse core/engine/nb_dialog.c and freeze the fix's shape (mirrors
test_cmd_doc_sync/test_langdefs_sync): a regression that reintroduces a
NULL-text abort, a per-call 60Hz accumulator, a per-frame speed-overriding
floor, a PIT/vblank-based wall clock, or the delta-driven micro-beat jitter
fails here.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NB_DIALOG_C = ROOT / "core" / "engine" / "nb_dialog.c"


def _func_body(name):
    src = NB_DIALOG_C.read_text(encoding="utf-8")
    m = re.search(r"\bvoid\s+" + re.escape(name) + r"\s*\(void\)\s*\n\{", src)
    assert m, f"nb_dialog.c: function {name}() not found"
    start = m.end() - 1  # position of '{'
    depth = 0
    for i in range(start, len(src)):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError(f"nb_dialog.c: unbalanced braces in {name}()")


def test_reveal_tick_never_depends_on_text_pointer():
    body = _func_body("nb_dialog_reveal_tick")
    assert "dialog_state.text" not in body, (
        "nb_dialog_reveal_tick() must not branch on dialog_state.text: the "
        "final page sets text=NULL while its body still needs revealing")


def test_reveal_tick_has_page_bound_guard():
    body = _func_body("nb_dialog_reveal_tick")
    assert "page_end" in body and "page_start" in body


def test_reveal_finish_not_gated_on_text_pointer():
    body = _func_body("nb_dialog_reveal_finish")
    assert "dialog_state.text" not in body, (
        "nb_dialog_reveal_finish() must jump-complete the body via page bounds, "
        "not skip it when text==NULL (final page)")


def test_reveal_tick_paced_by_wall_clock():
    body = _func_body("nb_dialog_reveal_tick")
    assert "hal_wallclock_smooth_ms" in body, (
        "reveal must pace off the virtual wall clock (hal_wallclock_smooth_ms, "
        "devdoc 107) so the speed setting is true chars/sec at the NP2kai "
        "~20Hz pass rate without freeze/burst on the chunked DOS clock")
    assert "hal_wallclock_ms" not in body or "hal_wallclock_smooth_ms" in body, (
        "raw hal_wallclock_ms() deltas are chunked under NP2kai and must not "
        "pace the reveal; the smooth virtual clock is the only micro-rhythm "
        "source (devdoc 107 / 0.2.134)")
    # Devdoc 106 plan A+ (0.2.133): the delta-driven incremental accumulator
    # is gone — the reveal recomputes an absolute target each pass.
    assert "reveal_ms_frac" not in body, (
        "devdoc 106 removed the incremental reveal_ms_frac accumulator (its "
        "raw per-pass deltas freeze-then-burst under NP2kai's chunked DOS "
        "clock); an absolute expected position is used instead")
    assert "reveal_char_count" in body, (
        "the absolute-position reveal must track a monotonic per-page char "
        "count to compare against the recomputed target")
    assert "reveal_frac" not in body


def test_reveal_tick_absolute_expected_position():
    body = _func_body("nb_dialog_reveal_tick")
    assert "target" in body and "reveal_page_ms" in body, (
        "reveal must compute an absolute target = speed * elapsed / 1000 "
        "from a page baseline (devdoc 106 plan A+), not accumulate deltas")


def test_reveal_virtual_clock_bounded_delta():
    # The per-pass virtual-clock bound (stall floor / catch-up ceiling) exists
    # to neutralize NP2kai's chunked DOS clock (devdoc 106).  Since 0.2.134 it
    # lives ONCE in the HAL (hal_wallclock_smooth_ms + SMOOTH_CLOCK_* in
    # hal.h), not duplicated per module as REVEAL_PASS_*.
    body = _func_body("nb_dialog_reveal_tick")
    assert "hal_wallclock_smooth_ms" in body, (
        "the reveal must consume the HAL smooth virtual clock whose per-pass "
        "delta is bounded (devdoc 107)")
    assert "REVEAL_PASS" not in body, (
        "REVEAL_PASS_MIN/MAX_MS were consumed by the HAL in 0.2.134 — the "
        "reveal must not re-own a second copy of the virtual-clock bounds "
        "(single source of truth in hal.h)")


def test_smooth_wallclock_bounds_in_hal():
    # The virtual-clock clamp must live in the HAL, shared by every
    # micro-rhythm consumer (typewriter / animation / BGM, devdoc 107).
    HAL = ROOT / "core" / "plat" / "hal_pc98.c"
    HDR = ROOT / "core" / "plat" / "hal.h"
    src = HAL.read_text(encoding="utf-8")
    hdr = HDR.read_text(encoding="utf-8")
    assert "hal_wallclock_smooth_ms" in src, (
        "hal_pc98.c must implement the smooth virtual clock")
    assert "smooth_inited" in src and "smooth_clock_total" in src, (
        "the smooth clock needs a baseline pass and an accumulated total")
    assert "SMOOTH_CLOCK_MIN_MS" in src and "SMOOTH_CLOCK_MAX_MS" in src, (
        "the per-pass delta clamp (stall floor / catch-up ceiling) must live "
        "with the HAL implementation (devdoc 107)")
    assert "SMOOTH_CLOCK_MIN_MS" in hdr and "SMOOTH_CLOCK_MAX_MS" in hdr, (
        "SMOOTH_CLOCK_* tuning constants must be exposed from hal.h")
    assert "hal_wallclock_smooth_ms" in hdr, (
        "hal.h must declare hal_wallclock_smooth_ms()")


def test_reveal_page_baseline_recalibrates():
    # The arm branch must reset the per-page char count and baseline, so a
    # smooth previous page never bursts the first characters of the next one.
    body = _func_body("nb_dialog_reveal_tick")
    assert "reveal_page_ms = now" in body, (
        "the arm pass must baseline the absolute target at the current "
        "virtual clock")
    assert "reveal_char_count = 0" in body, (
        "the arm pass must reset the per-page revealed-char count")
    src = NB_DIALOG_C.read_text(encoding="utf-8")
    start = src.index("dialog_state.reveal_active =")
    window = src[start:start + 400]
    assert "reveal_armed = 0" in window, (
        "dialog_show() must re-arm the clock baseline when starting a new "
        "page, else the carry-over time burst-skips the first characters")


def test_no_per_frame_floor():
    # A blanket "advance at least one char per call" floor silently overrides
    # the 16/32/64 speed settings; wall-clock pacing is the only clock source.
    # (devdoc 106's stall floor is a time bound in ms — REVEAL_PASS_MIN_MS —
    # and never hard-codes a char-per-call rate.)
    body = _func_body("nb_dialog_reveal_tick")
    assert "advanced" not in body


def test_reveal_no_wrap_reanchor_needed():
    # The raw-clock midnight/counter-wrap reanchor branch was deleted in
    # 0.2.134: the smooth HAL clock is monotonic by construction (its per-pass
    # deltas are clamped to [MIN,MAX] and only ever added), so the reveal must
    # not bookkeep previous raw samples or own a wrap path.
    body = _func_body("nb_dialog_reveal_tick")
    assert "reveal_char_count * 1000UL" not in body, (
        "the raw-clock wrap re-anchor is gone — the smooth HAL clock "
        "(devdoc 107) is monotonic, the page baseline is fixed at arm")
    assert "reveal_last_ms" not in body and "reveal_vnow" not in body, (
        "the reveal must not keep its own virtual-clock accumulator; elapsed "
        "is the monotonic hal_wallclock_smooth_ms() value directly")


def test_wallclock_backed_by_dos_system_time():
    # hal_wallclock_ms() must read DOS system time (INT 21h AH=2Ch) through
    # int386(), not the 8253 PIT and not a vblank frame counter.  NP2kai
    # probe (0.2.129) proved the PIT ports 0x71/0x77 read back
    # `nevent_getremain(NEVENT_ITIMER)/pccore.multiple` — a value driven by
    # the emulated CPU clock (readings non-monotonic) — so the PIT cannot
    # serve as a wall clock; and vblank frame counting under NP2kai's
    # ~20.5Hz pass rate (devdoc 82) only advanced ~342ms per real second.
    # DOS time-of-day is maintained by DOS in the emulator and on real
    # hardware alike (devdoc 82 §5.3 measured it exact under DPMI).
    HAL = ROOT / "core" / "plat" / "hal_pc98.c"
    src = HAL.read_text(encoding="utf-8")
    assert "int386" in src and "0x2C" in src, (
        "hal_wallclock_ms() must read DOS system time via INT 21h AH=2Ch "
        "(int386(), the same DPMI reflection channel video.c uses)")
    # Neither the PIT-based nor the vblank-frame wall clock may come back.
    # (History prose may name these; target the code, not the comment.)
    assert "static unsigned long wallclock_frames" not in src, (
        "vblank frame counter removed; it under-counts under NP2kai's ~20.5Hz "
        "pass rate (3x slowdown)")
    assert "PIT_CH0_PORT" not in src and "PIT_CMD_PORT" not in src, (
        "PIT port defines removed; DOS system time is the wall-clock source")