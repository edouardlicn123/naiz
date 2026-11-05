#!/usr/bin/env python3
"""Reference note/event timeline from the engine's own SMF parser (devdocs/150).

Compiles ``core/lib/midi.c`` with the host gcc into a shared object and drives
it through ctypes, so the timeline used for a recording-vs-MIDI comparison is
produced by *exactly* the same parser (and the same tempo->millisecond
conversion) the engine runs at playback time.  No new Python dependency; the C
source is the single source of truth (devdocs/136/150).

Host-only developer tool: nothing here ships to the engine or the HDI.

Usage:
    from naiz_audio import midi_ref
    events, len_ms = midi_ref.parse("song.mid")
    for t_ms, ch, note, vel in midi_ref.note_ons(events):
        ...
"""

import ctypes
import os
import subprocess
import tempfile

REPO_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", ".."))
_LIB_DIR = os.path.join(REPO_ROOT, "core", "lib")
_SRC = os.path.join(_LIB_DIR, "midi.c")

_CACHE = {}


class MidEvent(ctypes.Structure):
    """Mirror of MidEvent in core/lib/midi.h (b2 is 0 for 2-byte statuses)."""
    _fields_ = [
        ("tick_ms", ctypes.c_uint32),
        ("b0", ctypes.c_uint8),
        ("b1", ctypes.c_uint8),
        ("b2", ctypes.c_uint8),
    ]


def _build():
    """Compile midi.c to a shared object (rebuilt when the source changes)."""
    mtime = os.stat(_SRC).st_mtime
    if _CACHE.get("mtime") == mtime:
        return _CACHE["lib"]
    if not os.path.isfile(_SRC):
        raise RuntimeError(f"missing {_SRC}")
    so = os.path.join(tempfile.gettempdir(), "naiz_midi_ref.so")
    cmd = ["gcc", "-O2", "-shared", "-fPIC", "-fno-stack-protector",
           "-I", _LIB_DIR, _SRC, "-o", so]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"gcc failed building midi.c:\n{res.stderr}")
    lib = ctypes.CDLL(so)
    lib.midi_parse.argtypes = [
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32,
        ctypes.POINTER(ctypes.POINTER(MidEvent)), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_uint32)]
    lib.midi_parse.restype = ctypes.c_int
    lib.midi_free.argtypes = [ctypes.POINTER(MidEvent)]
    lib.midi_free.restype = None
    _CACHE["lib"] = lib
    _CACHE["mtime"] = mtime
    return lib


def parse(path):
    """Parse an SMF file -> (events, len_ms).

    events is a list of dicts {t_ms, b0, b1, b2} sorted by tick_ms.  len_ms is
    the song length (last voice event / any end-of-track, via the tempo map).
    Raises RuntimeError on a parser error so callers never fail silently.
    """
    with open(path, "rb") as fh:
        data = fh.read()
    if not data:
        raise RuntimeError(f"{path}: empty file")
    lib = _build()
    buf = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
    ev = ctypes.POINTER(MidEvent)()
    count = ctypes.c_int(0)
    len_ms = ctypes.c_uint32(0)
    rc = lib.midi_parse(buf, ctypes.c_uint32(len(data)),
                        ctypes.byref(ev), ctypes.byref(count),
                        ctypes.byref(len_ms))
    if rc != 0:
        raise RuntimeError(f"{path}: midi_parse failed (rc={rc})")
    try:
        events = [{"t_ms": int(ev[i].tick_ms), "b0": int(ev[i].b0),
                   "b1": int(ev[i].b1), "b2": int(ev[i].b2)}
                  for i in range(count.value)]
    finally:
        if ev:
            lib.midi_free(ev)
    return events, int(len_ms.value)


def note_ons(events):
    """Yield (t_ms, channel, note, velocity) for note-on (0x9x, vel > 0)."""
    out = []
    for e in events:
        if (e["b0"] & 0xF0) == 0x90 and e["b2"] > 0:
            out.append((e["t_ms"], e["b0"] & 0x0F, e["b1"], e["b2"]))
    return out


def note_offs(events):
    """Yield (t_ms, channel, note) for note-off (0x8x or 0x9x with vel 0)."""
    out = []
    for e in events:
        st = e["b0"] & 0xF0
        if st == 0x80 or (st == 0x90 and e["b2"] == 0):
            out.append((e["t_ms"], e["b0"] & 0x0F, e["b1"]))
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description="SMF timeline via core/lib/midi.c")
    ap.add_argument("midi")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()
    events, len_ms = parse(args.midi)
    ons = note_ons(events)
    print(f"{args.midi}: {len(events)} events, {len(ons)} note-ons, "
          f"len_ms={len_ms}")
    print(f"  channels: {sorted({c for _, c, _, _ in ons})}")
    for t_ms, ch, note, vel in ons[:args.limit]:
        print(f"  note-on t={t_ms:>7} ch={ch} note={note:>3} vel={vel}")


if __name__ == "__main__":
    main()
