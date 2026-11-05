"""P1b timbre acceptance for the demo-a2 FM patch families (devdocs/136).

Two layers:

  * analyzer self-tests (synthetic signals) — always run, no oracle, and they
    prove the metric code measures what it claims (vibrato rate, attack,
    harmonics).  A wrong analyzer is worse than none.
  * oracle regression — renders every family through the fmbench oracle and
    checks the targets.toml bands.  Skipped when the oracle cannot be built
    (no g++/make in this environment).

The oracle is the ymfm-based `tools/naiz_audio/fmbench` CLI wrapped by
`naiz_audio/fm_render.py`; the metric code is `naiz_audio/spectrum_report.py`.
"""

import os
import sys

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(REPO_ROOT, 'tools'))
sys.path.insert(0, os.path.join(REPO_ROOT, 'tools', 'naiz_audio'))

from naiz_audio import spectrum_report as sr  # noqa: E402
from naiz_audio import gm_families  # noqa: E402

import tomllib  # noqa: E402

FM_DIR = os.path.join(REPO_ROOT, 'assets', 'demo-a2', 'fm')
TARGETS_TOML = os.path.join(FM_DIR, 'targets.toml')

PROBE_NOTE = 60
PROBE_DUR_MS = 1500
FAMILY_NAMES = [name for name, _progs in gm_families.FAMILIES]


# ---------------------------------------------------------------------------
# targets.toml loading + band checking
# ---------------------------------------------------------------------------

def load_targets():
    with open(TARGETS_TOML, 'rb') as fh:
        return tomllib.load(fh)


def check_family(name, metrics, spec):
    """Return a list of human-readable band violations ([] == in band)."""
    bad = []

    def band(field, key):
        if key not in spec:
            return
        lo, hi = spec[key]
        value = metrics.get(field)
        if value is None:
            bad.append(f"{name}: {key} not measured (got None)")
        elif not (lo <= value <= hi):
            bad.append(f"{name}: {key}={value} outside [{lo}, {hi}]")

    band('attack_ms', 'attack_ms')
    band('centroid_hz', 'centroid_hz')
    band('vibrato_hz', 'vibrato_hz')
    band('vibrato_cent', 'vibrato_cent')
    for key, rng in spec.get('harmonics', {}).items():
        lo, hi = rng
        value = metrics.get('harmonics_db', {}).get(key)
        if value is None:
            bad.append(f"{name}: harmonic {key} not measured")
        elif not (lo <= value <= hi):
            bad.append(f"{name}: {key}={value} outside [{lo}, {hi}]")
    return bad


# ---------------------------------------------------------------------------
# analyzer self-tests (synthetic; always run)
# ---------------------------------------------------------------------------

def _synth(inst_f, fs=48000, dur=1.0, partials=(1.0, 0.2, 0.1)):
    t = np.arange(int(fs * dur)) / fs
    phase = 2.0 * np.pi * np.cumsum(inst_f) / fs
    x = np.zeros_like(t)
    for k, amp in enumerate(partials, start=1):
        x += amp * np.sin(k * phase)
    return x


def test_analyzer_vibrato_rate():
    """A synthetic 6 Hz / 40-cent vibrato must read back ~6 Hz."""
    fs = 48000
    t = np.arange(fs) / fs
    inst = 440.0 * 2.0 ** ((40.0 / 1200.0) * np.sin(2.0 * np.pi * 6.0 * t))
    x = _synth(inst, fs)
    rate, depth = sr.measure_vibrato(x, fs, 440.0)
    assert rate is not None and 5.0 <= rate <= 7.0, f"rate={rate}"
    assert depth is not None and depth > 40.0, f"depth={depth}"


def test_analyzer_vibrato_rejects_flat_tone():
    """A steady tone has no vibrato -> measure_vibrato returns None."""
    fs = 48000
    x = _synth(np.full(fs, 440.0), fs)
    rate, _depth = sr.measure_vibrato(x, fs, 440.0)
    assert rate is None, f"flat tone reported vibrato at {rate} Hz"


def test_analyzer_attack():
    """A 10 ms linear ramp must measure a small, finite attack time."""
    fs = 48000
    ramp = np.linspace(0.0, 1.0, int(0.010 * fs))
    x = np.concatenate([np.zeros(200), ramp, np.ones(4000)])
    ms = sr.measure_attack_ms(x, fs)
    assert ms is not None and 0.0 < ms < 25.0, f"attack={ms}"


def test_analyzer_harmonics():
    """2f/3f levels in the spectrum must match the synthesised amplitudes."""
    fs = 48000
    x = _synth(np.full(fs, 300.0), fs, partials=(1.0, 0.1, 0.01))
    m = sr.analyze(x, fs, 300.0)
    h = m['harmonics_db']
    assert -22.0 < h['2f'] < -18.0, h      # 0.1  -> -20 dB
    assert -42.0 < h['3f'] < -38.0, h      # 0.01 -> -40 dB


# ---------------------------------------------------------------------------
# targets.toml schema
# ---------------------------------------------------------------------------

def test_targets_cover_every_family():
    targets = load_targets()
    assert list(targets.keys()) == FAMILY_NAMES, (
        "targets.toml families must match gm_families.FAMILIES order/set")


def test_targets_entries_well_formed():
    for name, spec in load_targets().items():
        assert isinstance(spec.get('calibrated'), bool), f"{name}: calibrated"
        for key, val in spec.items():
            if key == 'calibrated':
                continue
            if key == 'harmonics':
                for hkey, rng in val.items():
                    _assert_band(name, f"harmonics.{hkey}", rng)
            else:
                _assert_band(name, key, val)


def _assert_band(name, key, rng):
    assert isinstance(rng, list) and len(rng) == 2, f"{name}: {key} not a pair"
    lo, hi = rng
    assert lo < hi, f"{name}: {key} band [{lo}, {hi}] is empty/inverted"


def test_check_family_detects_violation():
    """The band checker must actually fail an out-of-band value."""
    spec = {'attack_ms': [10, 20], 'vibrato_hz': [4, 8]}
    good = {'attack_ms': 15, 'vibrato_hz': 6.0}
    assert check_family('x', good, spec) == []
    bad = {'attack_ms': 40, 'vibrato_hz': None}
    violations = check_family('x', bad, spec)
    assert len(violations) == 2, violations


# ---------------------------------------------------------------------------
# oracle regression (skipped without a buildable fmbench)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def oracle():
    from naiz_audio import fm_render
    try:
        fm_render.ensure_fmbench()
    except fm_render.RenderError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"fmbench oracle unavailable: {exc}")
    return fm_render


def _render_family(fm_render, name):
    path = os.path.join(FM_DIR, f'{name}.fmp')
    rate, samples = fm_render.render(
        path, [(PROBE_NOTE, 96, 0, PROBE_DUR_MS, 8192)],
        cache_dir=fm_render.CACHE_DIR)
    x = samples[:, 0].astype(np.float64) / 2147483648.0
    return rate, x


def test_oracle_pitch_is_engine_octave(oracle):
    """The oracle must render C4 at ~261.6 Hz, not half.

    fmbench mirrors the engine's note->register encoding (devdocs/138): ymfm's
    OPN phase step is (fnum<<1<<block)>>2 == fnum<<(block-1), the Yamaha OPNA
    formula, so the rendered pitch matches the chip.  A regression here means
    every downstream timbre measurement is an octave off.
    """
    rate, x = _render_family(oracle, 'guitar')
    f0 = sr.estimate_f0(x, rate, 120, 600)
    assert 0.97 <= f0 / 261.63 <= 1.03, f"oracle C4 = {f0:.1f} Hz (want ~261.6)"


def test_oracle_families_are_audible(oracle):
    """Every family must render a non-silent, pitched C4 probe."""
    silent = []
    for name in FAMILY_NAMES:
        _rate, x = _render_family(oracle, name)
        if float(np.max(np.abs(x))) <= 0.0:
            silent.append(name)
    assert not silent, f"families rendered silence: {silent}"


def test_oracle_calibrated_families_meet_bands(oracle):
    """Calibrated families must place every metric inside its targets band."""
    targets = load_targets()
    failures = []
    for name in FAMILY_NAMES:
        spec = targets[name]
        if not spec.get('calibrated'):
            continue
        rate, x = _render_family(oracle, name)
        metrics = sr.analyze(x, rate, sr.note_to_hz(PROBE_NOTE),
                             lo=120.0, hi=4000.0)
        failures.extend(check_family(name, metrics, spec))
    assert not failures, "calibrated families out of band:\n" + "\n".join(failures)
