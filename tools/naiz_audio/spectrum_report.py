#!/usr/bin/env python3
"""Objective timbre metrics for FM patch work (devdocs/136 P1b).

Turns "does it sound like a flute?" into numbers, so patch tuning stops being
guesswork.  Works on any mono/stereo PCM (NP2kai capture, WAV) or on an oracle
render via fm_render.  The metric definitions match devdocs/136 P1b:

    harmonic ratios   steady-state FFT at integer multiples of f0, dB rel 1f
    attack_ms         RMS envelope 10% -> 90% of peak
    vibrato_hz/cent   pitch contour -> modulation rate + peak deviation
    centroid_hz       magnitude-weighted mean frequency (brightness)
    inharmonic_ratio  energy away from f0 multiples / total (breath/noise)
    peak / rms        level normalisation (for P1c equal-loudness alignment)

Requires numpy (no scipy).  Host-only; nothing here ships to the engine.
"""

import argparse
import json
import sys

import numpy as np

BEND_CENTRE = 8192


def load_raw(path, rate, channels):
    """Load a headerless interleaved PCM file -> (rate, mono float64 [-1,1])."""
    x = np.fromfile(path, dtype='<i2')
    if x.size == 0:
        raise ValueError(f"{path}: empty")
    if channels not in (1, 2):
        raise ValueError("channels must be 1 or 2")
    if x.size % channels != 0:
        x = x[:x.size - (x.size % channels)]
    if channels == 2:
        x = x.reshape(-1, 2).mean(axis=1)
    return float(rate), x.astype(np.float64) / 32768.0


def load_wav(path):
    """Load a PCM WAV -> (rate, mono float64 [-1,1]).  Requires 16/32-bit."""
    import wave
    with wave.open(str(path), 'rb') as wf:
        rate = wf.getframerate()
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())
    if width == 2:
        x = np.frombuffer(raw, dtype='<i2').astype(np.float64) / 32768.0
    elif width == 4:
        x = np.frombuffer(raw, dtype='<i4').astype(np.float64) / 2147483648.0
    else:
        raise ValueError(f"{path}: unsupported sample width {width * 8} bit")
    if channels == 2:
        x = x.reshape(-1, 2).mean(axis=1)
    return float(rate), x


def load(path, rate=None, channels=2):
    """Dispatch on extension: .wav -> load_wav, else raw PCM."""
    if str(path).lower().endswith('.wav'):
        return load_wav(path)
    if rate is None:
        raise ValueError("raw PCM needs an explicit --rate")
    return load_raw(path, rate, channels)


def _stft(x, fs, win_s, hop_s):
    n = 1 << int(np.ceil(np.log2(max(win_s * fs, 8.0))))
    hop = max(1, int(round(hop_s * fs)))
    win = np.hanning(n)
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    mags = []
    for start in range(0, len(x) - n + 1, hop):
        mags.append(np.abs(np.fft.rfft(x[start:start + n] * win)))
    if not mags:
        raise ValueError("signal shorter than one STFT window")
    return freqs, np.array(mags)


def _frame_rms(x, fs, win_ms=5.0, hop_ms=2.5):
    n = max(1, int(round(win_ms * 1e-3 * fs)))
    hop = max(1, int(round(hop_ms * 1e-3 * fs)))
    out = []
    for start in range(0, len(x) - n + 1, hop):
        out.append(np.sqrt(np.mean(x[start:start + n] ** 2)))
    return np.array(out), n, hop


def _peak_interp(freqs, mag, lo, hi):
    """Parabolic peak interpolation in the log-magnitude (dB) domain."""
    band = (freqs >= lo) & (freqs <= hi)
    bi = np.where(band)[0]
    if bi.size == 0 or mag[band].max() <= 0:
        return None
    j = int(np.argmax(mag[band]))
    pk = float(freqs[bi[j]])
    if 0 < j < bi.size - 1:
        a, b, c = mag[bi[j - 1]], mag[bi[j]], mag[bi[j + 1]]
        la, lb, lc = (_to_db(a), _to_db(b), _to_db(c))
        den = la - 2 * lb + lc
        if den != 0:
            pk += 0.5 * (la - lc) / den * (freqs[1] - freqs[0])
    return pk


def estimate_f0(x, fs, lo, hi, win_s=0.046, hop_s=0.0115):
    freqs, mags = _stft(x, fs, win_s, hop_s)
    peaks = []
    for m in mags:
        p = _peak_interp(freqs, m, lo, hi)
        if p is not None:
            peaks.append(p)
    if not peaks:
        raise ValueError("no pitch peak found in band")
    return float(np.median(peaks))


def measure_attack_ms(x, fs):
    """10% -> 90% of peak RMS (ms).  None if the envelope never rises."""
    env, _, hop = _frame_rms(x, fs)
    if env.size == 0 or env.max() <= 0:
        return None
    peak = env.max()
    i_peak = int(np.argmax(env))
    t10 = t90 = None
    for i in range(i_peak + 1):
        if t10 is None and env[i] >= 0.10 * peak:
            t10 = i
        if t90 is None and env[i] >= 0.90 * peak:
            t90 = i
    if t10 is None or t90 is None:
        return None
    return (t90 - t10) * hop / fs * 1000.0


def _bandpass(x, fs, lo, hi):
    n = len(x)
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / fs)
    spec[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(spec, n)


def _hilbert(x):
    """Analytic signal via FFT (Hilbert transform), no scipy needed."""
    n = len(x)
    spec = np.fft.fft(x)
    h = np.zeros(n)
    h[0] = 1
    if n % 2 == 0:
        h[n // 2] = 1
        h[1:n // 2] = 2
    else:
        h[1:(n + 1) // 2] = 2
    return np.fft.ifft(spec * h)


def _longest_run(mask):
    """Return (start, stop) of the longest contiguous True run in `mask`."""
    best = (0, 0)
    start = None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start > best[1] - best[0]:
                best = (start, i)
            start = None
    if start is not None and len(mask) - start > best[1] - best[0]:
        best = (start, len(mask))
    return best


def measure_vibrato(x, fs, f0):
    """Return (rate_hz, depth_cents) from the instantaneous frequency.

    Bandpasses around f0, takes the analytic signal's phase derivative over
    the longest loud run, detrends, block-averages to ~200 Hz, then reads the
    modulation rate off an FFT.  Block averaging is essential: the raw
    per-sample IF contour is dominated by numerical jitter at fs/2.
    """
    if f0 is None or f0 <= 0:
        return None, None
    y = _bandpass(x, fs, f0 * 0.75, f0 * 1.35)
    z = _hilbert(y)
    env = np.abs(z)
    if env.max() <= 0:
        return None, None
    a, b = _longest_run(env > env.max() * 0.25)
    if b - a < int(fs * 0.1):
        return None, None
    inst = np.diff(np.unwrap(np.angle(z[a:b]))) / (2.0 * np.pi) * fs
    med = float(np.median(inst))
    if med <= 0:
        return None, None
    cents = 1200.0 * np.log2(np.clip(inst, 1e-6, None) / med)
    idx = np.arange(cents.size)
    cents = cents - np.polyval(np.polyfit(idx, cents, 1), idx)
    blk = max(1, int(round(fs / 200.0)))
    nb = cents.size // blk
    if nb < 16:
        return None, None
    c = cents[:nb * blk].reshape(nb, blk).mean(axis=1)
    depth = float(np.percentile(c, 99) - np.percentile(c, 1))
    sp = np.abs(np.fft.rfft(c * np.hanning(nb)))
    fr = np.fft.rfftfreq(nb, blk / float(fs))
    if len(fr) <= 2:
        return None, depth
    bin_ = int(np.argmax(sp[1:])) + 1
    rate = float(fr[bin_])
    # Plausibility guard: the OPNA LFO only reaches roughly 4-25 Hz, and a real
    # vibrato shows a clear spectral peak.  Without this, noise / percussive
    # transients report spurious 60+ Hz "rates" (seen on piano/bell/perc/sfx).
    band = (fr[1:] >= 2.5) & (fr[1:] <= 30.0)
    peak = float(sp[bin_])
    floor = float(np.median(sp[1:])) + 1e-9
    if not band.any() or rate < 2.5 or rate > 30.0 or peak < 4.0 * floor:
        return None, None
    return rate, depth


def _steady_spectrum(x, fs, win_s, hop_s, thresh=0.5):
    """Magnitude spectrum averaged over the loud (sustain) frames."""
    freqs, mags = _stft(x, fs, win_s, hop_s)
    levels = mags.max(axis=1)
    loud = levels >= levels.max() * thresh
    if not loud.any():
        return freqs, np.zeros_like(freqs)
    return freqs, mags[loud].mean(axis=0)


def analyze(x, fs, f0=None, *, lo=180.0, hi=2500.0, win_s=0.046,
            hop_s=0.0115, n_harm=6, pitch_tol=0.03):
    """Compute the devdocs/136 P1b metric set for one sustained tone."""
    x = np.asarray(x, dtype=np.float64)
    if x.size == 0:
        raise ValueError("empty signal")
    if f0 is None:
        f0 = estimate_f0(x, fs, lo, hi, win_s, hop_s)

    freqs, spec = _steady_spectrum(x, fs, win_s, hop_s)
    df = freqs[1] - freqs[0]

    def band_level(fc):
        idx = int(np.argmin(np.abs(freqs - fc)))
        return float(spec[max(0, idx - 2):idx + 3].max())

    lvl1 = band_level(f0)
    harmonics = {}
    for k in range(2, n_harm + 1):
        if f0 * k > fs / 2:
            break
        harmonics[f"{k}f"] = round(_to_db(band_level(f0 * k)) - _to_db(lvl1), 1)

    # inharmonic energy: total minus energy within +/- pitch_tol of k*f0
    total = float(np.sum(spec ** 2))
    if total > 0:
        keep = np.zeros_like(spec, dtype=bool)
        for k in range(1, int((fs / 2) / max(f0, 1e-9)) + 1):
            fc = f0 * k
            keep |= np.abs(freqs - fc) <= max(pitch_tol * fc, df)
        inharmonic = 1.0 - float(np.sum(spec[keep] ** 2)) / total
    else:
        inharmonic = None

    band = (freqs >= lo) & (freqs <= hi)
    if spec[band].sum() > 0:
        centroid = float(np.sum(freqs[band] * spec[band]) / np.sum(spec[band]))
    else:
        centroid = None

    peak = float(np.max(np.abs(x)))
    rms = float(np.sqrt(np.mean(x ** 2)))
    vib_hz, vib_cent = measure_vibrato(x, fs, f0)

    return {
        "f0_hz": round(float(f0), 1),
        "harmonics_db": harmonics,
        "attack_ms": _round(measure_attack_ms(x, fs), 1),
        "vibrato_hz": _round(vib_hz, 2),
        "vibrato_cent": _round(vib_cent, 0),
        "centroid_hz": _round(centroid, 0),
        "inharmonic_ratio": _round(inharmonic, 3),
        "peak": round(peak, 4),
        "rms": round(rms, 5),
        "peak_rms_db": _round(_to_db(peak) - _to_db(rms), 1) if rms > 0 else None,
    }


def _to_db(v):
    return 20.0 * np.log10(v + 1e-12)


def _round(v, n):
    return None if v is None else round(float(v), int(n))


def note_to_hz(note):
    """MIDI note -> equal-tempered frequency (A4=note 69=440 Hz)."""
    return 440.0 * 2.0 ** ((note - 69) / 12.0)


def render_and_analyze(patch, note=60, vel=96, dur_ms=1000, *,
                       cache_dir=None, **kw):
    """Render a .fmp via fm_render, then analyze the FM channel (L)."""
    from naiz_audio import fm_render
    rate, samples = fm_render.render(
        patch, [(note, vel, 0, dur_ms, BEND_CENTRE)], cache_dir=cache_dir)
    f0 = note_to_hz(note)
    return analyze(samples[:, 0].astype(np.float64) / 2147483648.0, rate, f0, **kw)


def main():
    ap = argparse.ArgumentParser(description="FM timbre metrics (devdocs/136)")
    ap.add_argument("input", help="capture (raw PCM or .wav) or a .fmp patch")
    ap.add_argument("--rate", type=int, default=48000, help="raw PCM rate")
    ap.add_argument("--channels", type=int, default=2)
    ap.add_argument("--f0", type=float, default=None, help="known fundamental Hz")
    ap.add_argument("--note", type=int, default=None, help="known MIDI note")
    ap.add_argument("--lo", type=float, default=180.0)
    ap.add_argument("--hi", type=float, default=2500.0)
    ap.add_argument("--oracle", action='store_true',
                    help="treat input as a .fmp and render via fmbench")
    ap.add_argument("--json", action='store_true')
    args = ap.parse_args()

    if args.f0 is not None:
        f0 = args.f0
    elif args.note is not None:
        f0 = note_to_hz(args.note)
    else:
        f0 = None

    try:
        if args.oracle:
            metrics = render_and_analyze(
                args.input, note=args.note if args.note is not None else 60,
                cache_dir=fm_render_cache(), lo=args.lo, hi=args.hi)
        else:
            fs, x = load(args.input, args.rate, args.channels)
            metrics = analyze(x, fs, f0, lo=args.lo, hi=args.hi)
    except (ValueError, OSError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    if args.json:
        print(json.dumps(metrics, indent=2))
        return
    print(f"f0            : {metrics['f0_hz']} Hz")
    print(f"attack        : {metrics['attack_ms']} ms")
    print(f"centroid      : {metrics['centroid_hz']} Hz")
    print(f"vibrato       : {metrics['vibrato_hz']} Hz / {metrics['vibrato_cent']} cent")
    print(f"inharmonic    : {metrics['inharmonic_ratio']}")
    print(f"peak/rms      : {metrics['peak']} / {metrics['rms']} "
          f"({metrics['peak_rms_db']} dB)")
    print("harmonics (dB rel 1f):")
    for k, v in metrics['harmonics_db'].items():
        print(f"  {k}: {v:+}")


def fm_render_cache():
    from naiz_audio import fm_render
    return fm_render.CACHE_DIR


if __name__ == "__main__":
    main()
