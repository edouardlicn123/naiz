#!/usr/bin/env python3
"""Python wrapper around the fmbench YM2608 render oracle (devdocs/136 P1a).

Compiles a `.fmp` text source to its 32-byte binary (via fm_patch), feeds the
raw bytes to the fmbench CLI, and reads the rendered WAV back as a numpy
array.  Results are cached by a hash of (patch bytes + job parameters).

fmbench is a host-only developer tool: nothing here ships to the engine or
the HDI.  Requires numpy (present in tools/env_setup/venv).

Usage:
    fm_render.py <patch.fmp> <out.wav> [--note N] [--vel N] [--dur MS]
                 [--bend N] [--tail MS] [--clock N] [--fidelity min|med|max]
                 [--no-lfo] [--raw-note] [--no-cache]
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from naiz_audio import fm_patch  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = REPO_ROOT / 'tools' / 'naiz_audio' / 'fmbench'
BENCH_BIN = BENCH_DIR / 'fmbench'
CACHE_DIR = BENCH_DIR / '.cache'

DEFAULT_CLOCK = 7987200
DEFAULT_TAIL_MS = 200
BEND_CENTRE = 8192


class RenderError(RuntimeError):
    """fmbench could not be built or run, or produced an unreadable WAV."""


def ensure_fmbench(rebuild=False):
    """Return the fmbench binary path, building it if needed."""
    if rebuild or not BENCH_BIN.exists():
        proc = subprocess.run(
            ['make', '-C', str(BENCH_DIR)],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise RenderError(
                "fmbench build failed:\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    if not BENCH_BIN.exists():
        raise RenderError(f"fmbench binary missing after build: {BENCH_BIN}")
    return BENCH_BIN


def load_patch(patch):
    """Accept a .fmp path or 32 raw bytes; return the compiled 32-byte blob."""
    if isinstance(patch, (bytes, bytearray)):
        blob = bytes(patch)
        if len(blob) != 32:
            raise RenderError(f"raw patch must be 32 bytes, got {len(blob)}")
        return blob
    return fm_patch.compile_source(patch)


def _norm_events(events):
    """Normalise events to a list of (note, vel, start_ms, dur_ms, bend)."""
    out = []
    for e in events:
        if len(e) == 4:
            note, vel, start_ms, dur_ms = e
            bend = BEND_CENTRE
        elif len(e) == 5:
            note, vel, start_ms, dur_ms, bend = e
        else:
            raise RenderError(f"event needs 4 or 5 fields, got {len(e)}: {e!r}")
        out.append((int(note), int(vel), int(start_ms), int(dur_ms), int(bend)))
    if not out:
        raise RenderError("no events to render")
    return out


def _bench_id():
    """Identity of the fmbench binary so cache entries invalidate on rebuild."""
    st = BENCH_BIN.stat()
    return f"{st.st_size}:{st.st_mtime_ns}"


def _job_key(blob, events, clock, fidelity, tail_ms, lfo, raw_note):
    payload = json.dumps({
        'patch': blob.hex(),
        'events': events,
        'clock': clock,
        'fidelity': fidelity,
        'tail_ms': tail_ms,
        'lfo': lfo,
        'raw_note': raw_note,
        'bench': _bench_id(),
    }, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]


def read_wav32(path):
    """Read a 32-bit signed stereo WAV -> (rate, int32 array shape (N, 2))."""
    with wave.open(str(path), 'rb') as wf:
        rate = wf.getframerate()
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        frames = wf.getnframes()
        raw = wf.readframes(frames)
    if width != 4:
        raise RenderError(f"{path}: expected 32-bit samples, got {width * 8}")
    if channels != 2:
        raise RenderError(f"{path}: expected stereo, got {channels} ch")
    data = np.frombuffer(raw, dtype='<i4')
    return rate, data.reshape(-1, 2)


def write_wav32(path, rate, samples):
    """Write an int32 array shape (N, 2) as a 32-bit signed stereo WAV."""
    samples = np.asarray(samples, dtype='<i4')
    if samples.ndim != 2 or samples.shape[1] != 2:
        raise RenderError(f"samples must be (N, 2), got shape {samples.shape}")
    payload = samples.tobytes()
    with wave.open(str(path), 'wb') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(4)
        wf.setframerate(rate)
        wf.writeframes(payload)


def _run_fmbench(bin_path, blob, events, clock, fidelity, tail_ms, lfo,
                 raw_note, out_wav):
    with tempfile.TemporaryDirectory() as td:
        patch_bin = Path(td) / 'patch.bin'
        patch_bin.write_bytes(blob)
        ev_path = Path(td) / 'events.txt'
        lines = [f"{n} {v} {s} {d} {b}" for (n, v, s, d, b) in events]
        ev_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

        cmd = [str(bin_path), str(patch_bin), str(out_wav),
               '--clock', str(clock),
               '--fidelity', fidelity,
               '--events', str(ev_path),
               '--tail', str(tail_ms)]
        if not lfo:
            cmd.append('--no-lfo')
        if raw_note:
            cmd.append('--raw-note')

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RenderError(
                f"fmbench failed (rc={proc.returncode}):\n{proc.stderr}")


def render(patch, events, *, clock=DEFAULT_CLOCK, fidelity='min',
           tail_ms=DEFAULT_TAIL_MS, lfo=True, raw_note=False,
           cache_dir=None, rebuild=False):
    """Render a patch + note list -> (rate, int32 array shape (N, 2)).

    patch: .fmp path or 32 raw bytes.
    events: iterable of (note, vel, start_ms, dur_ms[, bend]).
    Pass cache_dir=None to disable caching.
    """
    blob = load_patch(patch)
    ev = _norm_events(events)
    bin_path = ensure_fmbench(rebuild=rebuild)

    use_cache = cache_dir is not None
    if use_cache:
        cache_dir = Path(cache_dir)
        key = _job_key(blob, ev, clock, fidelity, tail_ms, lfo, raw_note)
        cached = cache_dir / f"{key}.wav"
        if cached.exists():
            return read_wav32(cached)

    with tempfile.TemporaryDirectory() as td:
        out_wav = Path(td) / 'out.wav'
        _run_fmbench(bin_path, blob, ev, clock, fidelity, tail_ms, lfo,
                     raw_note, out_wav)
        rate, samples = read_wav32(out_wav)
        if use_cache:
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / f"{key}.wav").write_bytes(out_wav.read_bytes())
    return rate, samples


def main():
    ap = argparse.ArgumentParser(
        description="Render a .fmp patch + note via fmbench to a WAV")
    ap.add_argument("patch", help="path to the .fmp text source")
    ap.add_argument("out", help="output WAV path")
    ap.add_argument("--note", type=int, default=60)
    ap.add_argument("--vel", type=int, default=96)
    ap.add_argument("--dur", type=int, default=1000)
    ap.add_argument("--bend", type=int, default=BEND_CENTRE)
    ap.add_argument("--tail", type=int, default=DEFAULT_TAIL_MS)
    ap.add_argument("--clock", type=int, default=DEFAULT_CLOCK)
    ap.add_argument("--fidelity", choices=['min', 'med', 'max'], default='min')
    ap.add_argument("--no-lfo", action='store_true')
    ap.add_argument("--raw-note", action='store_true')
    ap.add_argument("--no-cache", action='store_true')
    args = ap.parse_args()

    if not os.path.isfile(args.patch):
        print(f"ERROR: no such patch file: {args.patch}")
        sys.exit(1)
    events = [(args.note, args.vel, 0, args.dur, args.bend)]
    cache_dir = None if args.no_cache else CACHE_DIR
    try:
        rate, samples = render(
            args.patch, events, clock=args.clock, fidelity=args.fidelity,
            tail_ms=args.tail, lfo=not args.no_lfo,
            raw_note=args.raw_note, cache_dir=cache_dir)
    except (RenderError, fm_patch._PatchError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    write_wav32(args.out, rate, samples)
    print(f"fm_render: rate={rate} samples={len(samples)} -> {args.out}")


if __name__ == '__main__':
    main()
