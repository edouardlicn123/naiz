#!/usr/bin/env python3
"""Compare an engine BGM recording against the source MIDI (devdocs/150).

Emits the numbers that attribute the "flutter/buzz" to one of the three axes
(devdocs/148 §五):

    * timing   -- detected note onsets vs the MIDI's intended note times
                  (IOI spread, latency, drift, residual jitter)
    * pitch    -- per-onset f0 vs the MIDI note numbers (future: per-note)
    * timbre   -- spectrum metrics (centroid, >5 kHz share) via spectrum_report

The MIDI timeline comes from the engine's *own* parser (tools.naiz_audio.midi_ref
binds core/lib/midi.c), so the reference is byte-identical to what the driver
schedules.  Optionally renders a GM reference (gm_render) as a clean control.

Host-only developer tool; nothing ships to the engine or the HDI.

Usage:
    # record then compare (needs DISPLAY + a fresh HDI + NP2kai)
    python -m tools.diag.bgm_compare --game demo-a2 \
        --mid 'assets/demo-a2/bgm/Melody Town Theme.mid' --gm /tmp/ref.wav

    # compare an existing capture
    python -m tools.diag.bgm_compare \
        --rec logs/aud001.raw --rate 44100 --channels 2 \
        --mid 'assets/demo-a2/bgm/Melody Town Theme.mid'
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from tools.naiz_audio import spectrum_report as sr          # noqa: E402
from tools.naiz_audio import midi_ref                        # noqa: E402

# Onsets within this window are treated as one chord/event when deduping the
# MIDI reference (chords otherwise inflate the count and defeat matching).
CHORD_WINDOW_MS = 60.0
# Matching tolerance between a detected onset and a reference note time.
MATCH_TOL_MS = 120.0


def dedup(times, window=CHORD_WINDOW_MS):
    out = []
    for t in sorted(times):
        if not out or t - out[-1] > window:
            out.append(t)
    return out


def hf_share(x, fs, split_hz=5000.0):
    """Fraction of spectral energy above split_hz (brightness / buzz proxy)."""
    if x.size < 1024:
        return None
    n = 1 << int(np.ceil(np.log2(min(len(x), fs // 4))))
    win = np.hanning(n)
    hop = max(1, n // 2)
    hi = lo = 0.0
    for s in range(0, len(x) - n + 1, hop):
        spec = np.abs(np.fft.rfft(x[s:s + n] * win)) ** 2
        freqs = np.fft.rfftfreq(n, 1.0 / fs)
        hi += float(spec[freqs >= split_hz].sum())
        lo += float(spec.sum())
    return round(hi / lo, 4) if lo > 0 else None


def analyze_recording(rec, rate, channels, mid):
    """Return the comparison report dict for one recording vs one MIDI."""
    fs, x = sr.load(rec, rate, channels)
    onsets = sr.detect_onsets(x, fs)
    events, len_ms = midi_ref.parse(mid)
    ref_all = [t for t, _, _, _ in midi_ref.note_ons(events)]
    ref = dedup(ref_all)
    deltas, unmatched = sr.match_onsets(onsets, ref, tol_ms=MATCH_TOL_MS)
    return {
        "rec": str(rec),
        "mid": str(mid),
        "duration_s": round(len(x) / fs, 2),
        "midi_len_ms": len_ms,
        "midi_note_ons": len(ref_all),
        "midi_events_deduped": len(ref),
        "detected_onsets": len(onsets),
        "matched": len(deltas),
        "unmatched_ref": unmatched,
        "match_frac": round(len(deltas) / len(ref), 3) if ref else None,
        "onset_ioi": sr.measure_ioi(onsets),
        "residual": sr.residual_jitter(deltas),
        "hf_share": hf_share(x, fs),
    }


def record(game, out, after, duration, rate, channels):
    """Record via the NP2kai capture tool; returns the .seg path."""
    from tools.diag import np2kai_audio
    ok, gate, msg = np2kai_audio.preflight(game)
    if not ok:
        raise RuntimeError(f"preflight {gate}: {msg}")
    args = argparse.Namespace(
        game=game, out=out, after=after, duration=duration, rate=rate,
        channels=channels, boot_timeout=60.0, after_timeout=60.0,
        boot_presses=3, max_presses=40, press_interval=1.5,
        window_timeout=20.0, keep_log=False)
    _, start, end = np2kai_audio.capture(args)
    if end <= start:
        raise RuntimeError("no audio captured")
    seg = out + ".seg"
    if not os.path.isfile(seg):
        raise RuntimeError(f"expected capture segment {seg} missing")
    return seg


def _print_report(rep):
    print(f"recording      : {rep['rec']}  ({rep['duration_s']} s)")
    print(f"midi           : {rep['mid']}  (len {rep['midi_len_ms']} ms)")
    print(f"note-ons       : midi {rep['midi_note_ons']} "
          f"({rep['midi_events_deduped']} deduped) | detected "
          f"{rep['detected_onsets']}")
    print(f"matched        : {rep['matched']}  "
          f"(frac {rep['match_frac']}, unmatched_ref {rep['unmatched_ref']})")
    io = rep["onset_ioi"]
    print(f"onset IOI      : mean {io['ioi_mean_ms']} ms std {io['ioi_std_ms']} "
          f"p95 {io['ioi_p95_ms']} cv {io['ioi_cv']}")
    rj = rep["residual"]
    print(f"residual jitter: latency {rj['latency_ms']} ms "
          f"drift {rj['drift_ms_per_s']} ms/s | std {rj['jitter_std_ms']} ms "
          f"p95 {rj['jitter_p95_ms']} ms (n {rj['n']})")
    print(f">5kHz share    : {rep['hf_share']}")


def main():
    ap = argparse.ArgumentParser(description="BGM recording vs MIDI (devdocs/150)")
    ap.add_argument("--rec", help="existing capture (raw S16LE / .wav / .seg)")
    ap.add_argument("--game", help="record via NP2kai (needs DISPLAY + fresh HDI)")
    ap.add_argument("--mid", required=True, help="source MIDI file")
    ap.add_argument("--gm", help="optional: render a GM reference to this .wav")
    ap.add_argument("--rate", type=int, default=44100)
    ap.add_argument("--channels", type=int, default=2)
    ap.add_argument("--after", default="BGM", help="record start marker")
    ap.add_argument("--duration", type=float, default=12.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        if args.gm:
            from tools.naiz_audio import gm_render
            gm_render.render(args.mid, args.gm)
            print(f"[bgm_compare] GM reference -> {args.gm}")
        rec = args.rec
        if args.game:
            rec = record(args.game, f"logs/aud_{args.game}.raw", args.after,
                         args.duration, args.rate, args.channels)
        if not rec:
            print("ERROR: need --rec or --game")
            sys.exit(1)
        rep = analyze_recording(rec, args.rate, args.channels, args.mid)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        _print_report(rep)


if __name__ == "__main__":
    main()
