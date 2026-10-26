"""Timer-B tick period + PCM feed-rate contract guard (devdoc 169 §5.1.4).

devdoc 168 established that one OPNA Timer-B step is 2304 master clocks, not
1152: the manual's 1152 is expressed in phiM/2 cycles.  At NB=200 and the
86-board crystal (phiM = 7.9872 MHz) a step is 16.154 ms, i.e. 258 units of
1/16 ms -- not 129.  With 129 the ISR-built virtual clock ran at 49.8% of real
time, so BGM played at half speed and the PCM FIFO was starved.

Nothing in the C sources can catch that: 129 compiles, links and plays.  These
tests turn the derivation into something checkable, and they deliberately pin
the *comment and log text* as well as the constant -- a half-edited file
(constant fixed, comments still saying "8.064 ms / ~124Hz") is the failure
mode that sends the next reader back to 129.

They also pin the PCM feed-time contract (devdoc 169 §5.1.2): the pump must be
driven by "how much the clock advanced", never by differencing two virtual
timestamps (that quantises to whole ms -- 0.78% systematic underfeed in the
ISR path -- and inherits the music clock's slew in the co-operative path).

Everything here parses source text; no compilation and no emulator.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HAL_IRQ_C = ROOT / "core" / "plat" / "hal_irq.c"
HAL_H = ROOT / "core" / "plat" / "hal.h"
HAL_AUDIO_C = ROOT / "core" / "plat" / "hal_audio.c"
VCLOCK_C = ROOT / "core" / "lib" / "vclock.c"
AUDIO_C = ROOT / "core" / "engine" / "audio.c"
AUDIO_H = ROOT / "core" / "engine" / "audio.h"

# 86-board OPNA crystal (MAME pc9801_86.cpp:85; docs/refdocs/F07 §2.3).
PHI_M_MHZ = 7.9872
# One Timer-B step, in master clocks (F07 §3: ymfm / Nuked-OPN2 / BlastEm /
# NP2kai all agree; the manual's 1152 counts phiM/2 cycles).
MASTER_CLOCKS_PER_STEP = 2304
UNITS_PER_MS = 16  # VCLOCK_UNITS_PER_MS (core/lib/vclock.h:47)

# Stale values that must not survive in hal_irq.c once the constant is fixed.
STALE_TEXT = ("8.064", "124Hz", "1152*(256", "1152 * (256", "(0.02% short)")


def _read(path):
    assert path.exists(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def _define_int(src, name):
    """Integer value of a plain `#define NAME <int>` line, or None."""
    m = re.search(r"^#define\s+" + re.escape(name) + r"\s+(\d+)\s*$", src, re.M)
    return int(m.group(1)) if m else None


def _expected_units(nb):
    """Timer-B period in 1/16 ms units for reload value `nb`."""
    return MASTER_CLOCKS_PER_STEP * (256 - nb) / PHI_M_MHZ / 1000.0 * UNITS_PER_MS


def _expected_hz(nb):
    """Timer-B frequency in Hz for reload value `nb`."""
    return PHI_M_MHZ * 1e6 / (MASTER_CLOCKS_PER_STEP * (256 - nb))


def _timer_b_nb():
    nb = _define_int(_read(HAL_IRQ_C), "FM_TIMER_B_NB")
    assert nb is not None, "hal_irq.c must define FM_TIMER_B_NB as a plain int"
    assert 0 < nb < 256, f"FM_TIMER_B_NB={nb} is not an 8-bit reload value"
    return nb


def _timer_b_units():
    units = _define_int(_read(HAL_IRQ_C), "BGM_TIMER_B_UNITS")
    assert units is not None, (
        "hal_irq.c must define BGM_TIMER_B_UNITS as a plain int literal"
    )
    return units


# --- 1. the constant itself ---------------------------------------------

def test_timer_b_units_is_258():
    """devdoc 168: NB=200 at 7.9872 MHz is 16.154 ms == 258 units, not 129.

    129 is the value you get by reading the manual's 1152 as phiM cycles; it
    makes the ISR clock run at half speed.  Pinned to the literal so a
    "quiet" regression to 129 (or to the mean of the two) fails here.
    """
    assert _timer_b_units() == 258, (
        f"BGM_TIMER_B_UNITS={_timer_b_units()} -- must be 258 "
        "(devdoc 168; 129 is the half-period value)"
    )


def test_timer_b_units_matches_the_derivation():
    """The constant must follow from NB and the 86-board crystal.

    Catches the half-edit where someone changes FM_TIMER_B_NB and forgets the
    period constant (the two are coupled but the compiler cannot tell).
    """
    nb = _timer_b_nb()
    want = _expected_units(nb)
    got = _timer_b_units()
    assert abs(got - want) <= 1, (
        f"BGM_TIMER_B_UNITS={got} but NB={nb} at {PHI_M_MHZ} MHz gives "
        f"{want:.2f} units"
    )


def test_no_per_host_branching():
    """devdoc 168 §订正: the period is host-independent (NP2kai differs by
    0.16%).  A per-host #ifdef would re-introduce the half-speed bug on
    whichever branch is wrong, and is explicitly forbidden by devdoc 169 §六.
    """
    src = _read(HAL_IRQ_C)
    bad = [
        line.strip()
        for line in src.split("\n")
        if re.match(r"\s*#\s*(if|ifdef|elif)\b.*\bNP2", line, re.I)
        or re.match(r"\s*#\s*(ifdef|elif)\b.*\bHOST\b", line, re.I)
    ]
    assert not bad, f"hal_irq.c has per-host branching: {bad}"


# --- 2. comments and log are part of the spec ---------------------------

def test_comments_do_not_keep_the_old_numbers():
    """A half-edited file is worse than an unedited one: the stale comment
    tells the next reader that 8.064 ms / ~124 Hz is correct, so they "fix"
    the code back.  devdoc 169 §5.1.4 pins both the value and the prose.

    vclock.c is scanned too: its fixed-advance comment carried the same
    retracted 8.064 ms -> 129 units example, a second copy of the bug that
    the hal_irq.c-only scan would have let through.
    """
    stale = []
    for path in (HAL_IRQ_C, VCLOCK_C):
        src = _read(path)
        stale.extend(f"{path.name}:{s}" for s in STALE_TEXT if s in src)
    assert not stale, (
        "source files still carry the retracted period text "
        f"{stale} -- update the Timer-B / vclock comment blocks as well"
    )


def test_install_log_reports_the_real_rate():
    """The install log is the only runtime evidence a capture shows; while it
    said ~124Hz it hid the fact that the beat was 61.9Hz."""
    nb = _timer_b_nb()
    want = f"{_expected_hz(nb):.1f}Hz"
    src = _read(HAL_IRQ_C)
    found = want in src
    assert found, (
        f"the Timer-B install log must report {want} (NB={nb}), "
        f"not a stale rate; expected the literal {want!r} in hal_irq.c"
    )


# --- 3. PCM feed time source -------------------------------------------

def test_pcm_entry_is_units_based():
    """The pump takes 1/16 ms units so a 16.125 ms step is not truncated to
    16 ms (devdoc 169 §2.3).  The old ms entry point must be gone, not kept
    as a second way in -- two entry points means two time bases again.
    """
    for path in (HAL_H, HAL_AUDIO_C, AUDIO_C):
        retired = "hal_pcm_tick" in _read(path)
        assert not retired, (
            f"{path.name} still references the retired hal_pcm_tick(); "
            "use hal_pcm_advance_units()"
        )

    assert re.search(
        r"void\s+hal_pcm_advance_units\s*\(\s*uint32_t\s+\w+\s*\)", _read(HAL_H)
    ), "hal.h must declare void hal_pcm_advance_units(uint32_t units)"

    refs = {
        p
        for p in (ROOT / "core").rglob("*.c")
        if "hal_pcm_advance_units" in _read(p)
    }
    assert refs == {HAL_AUDIO_C, AUDIO_C}, (
        "hal_pcm_advance_units must be defined in hal_audio.c and called from "
        f"audio.c only; found {sorted(p.name for p in refs)}"
    )


def test_pcm_elapsed_time_comes_from_the_clock_step():
    """The pump must be told how far the clock advanced this tick, not how far
    two virtual timestamps differ (devdoc 169 §5.1.2).

    Differencing `hal_wallclock_smooth_ms()` truncates to whole milliseconds
    (0.78% systematic underfeed in the ISR path) and drags the music clock's
    deliberate slew into the sample rate in the co-operative path.
    """
    audio_c = _read(AUDIO_C)
    derived = "last_pcm_ms" in audio_c
    assert not derived, (
        "audio.c still derives the PCM step from a virtual-clock delta; the "
        "caller must pass the clock-advance amount instead"
    )
    assert re.search(
        r"void\s+audio_tick_isr\s*\(\s*unsigned\s+long\s+\w+\s*\)", audio_c
    ), "audio_tick_isr must take the elapsed 1/16 ms units as a parameter"
    assert re.search(
        r"void\s+audio_tick_isr\s*\(\s*unsigned\s+long\s+\w+\s*\)", _read(AUDIO_H)
    ), "audio.h must publish the units-taking audio_tick_isr prototype"
    assert re.search(
        r"audio_tick_isr\s*\(\s*BGM_TIMER_B_UNITS\s*\)", _read(HAL_IRQ_C)
    ), (
        "the Timer-B handler must feed the pump its own hardware period "
        "(audio_tick_isr(BGM_TIMER_B_UNITS))"
    )
    declared = "hal_wallclock_last_advance_units" in _read(HAL_H)
    assert declared, (
        "the co-operative path needs the emitted advance in units: declare "
        "hal_wallclock_last_advance_units() in hal.h"
    )
    used = "hal_wallclock_last_advance_units" in audio_c
    assert used, (
        "audio_tick() must pass the last emitted advance to audio_tick_isr()"
    )


def test_pump_carries_the_byte_remainder():
    """A late tick (two Timer-B periods = ~1422 bytes at 44.1kHz) exceeds one
    pump, and the remainder must be carried -- otherwise a single stall leaves
    the stream permanently short (devdoc 169 §2.3 defect 2)."""
    src = _read(HAL_AUDIO_C)
    carries_debt = "g_pcm_debt" in src
    assert carries_debt, (
        "hal_audio.c must carry the un-fed remainder (g_pcm_debt_bytes) "
        "instead of dropping it at the per-pump cap"
    )
    cap = _define_int(src, "PCM_TICK_MAX_BYTES")
    assert cap is not None, "PCM_TICK_MAX_BYTES must stay a literal #define"
    assert cap >= 2048, (
        f"PCM_TICK_MAX_BYTES={cap}: one 16.15ms step needs ~711 bytes and a "
        "double period ~1422, so the cap must be at least 2048"
    )
