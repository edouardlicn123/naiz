#!/usr/bin/env python3
"""Generate a demo GM MIDI file for the Naiz engine (devdoc 101).

Produces a tiny single-track SMF (format 0, 480 PPQN): a C-major arpeggio
melody on channel 0 with a program change, a control-change volume, and a
Note-On/Off pair per note.  This exercises the full engine path:
tempo map, running-status-free events, note scheduling, and loop wrap.

Output is a standard .mid that also plays in any external GM player.

Usage:
    gen_test_midi.py <out.mid> [--bpm 120] [--program 0]
"""

import argparse
import struct
import sys


def _vlv(n):
    """Encoded VLV of n (7-bit groups, MSB continuation)."""
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def build(bpm=120, program=0):
    """Return a format-0 SMF byte string.

    Track layout:
      tempo (0x51 03, us/quarter for bpm)
      program change (ch0) + volume CC (ch0, 100)
      three notes (C4 E4 G4), each note-on at t, note-off at t+192 ticks
      end-of-track meta
    Division 480 PPQN.
    """
    us_per_quarter = int(60_000_000 / bpm)
    ppqn = 480

    track = bytearray()
    track += b"\x00\xFF\x51\x03" + struct.pack(">I", us_per_quarter)[1:4]
    track += b"\x00\xC0" + bytes([program])
    track += b"\x00\xB0\x07\x64"          # CC7 volume 100
    notes = (60, 64, 67)
    for i, n in enumerate(notes):
        t = 0 if i == 0 else 480           # chord at t=0, next notes together
        track += _vlv(t) + bytes([0x90, n, 0x60])
        track += _vlv(192) + bytes([0x80, n, 0x40])
    track += b"\x00\xFF\x2F\x00"

    hdr = b"MThd" + struct.pack(">IHHH", 6, 0, 1, ppqn)
    trk = b"MTrk" + struct.pack(">I", len(track)) + bytes(track)
    return hdr + trk


def main():
    ap = argparse.ArgumentParser(description="generate demo GM MIDI for Naiz")
    ap.add_argument("out", help="output .mid file path")
    ap.add_argument("--bpm", type=int, default=120)
    ap.add_argument("--program", type=int, default=0)
    args = ap.parse_args()

    if not (20 <= args.bpm <= 300):
        print(f"ERROR: bpm out of range: {args.bpm}")
        sys.exit(1)
    if not (0 <= args.program <= 127):
        print(f"ERROR: program out of range: {args.program}")
        sys.exit(1)

    data = build(args.bpm, args.program)
    try:
        with open(args.out, 'wb') as f:
            f.write(data)
    except OSError as e:
        print(f"ERROR: cannot write {args.out}: {e}")
        sys.exit(1)
    print(f"  {args.out}: format 0, 480 PPQN, {args.bpm} BPM, "
          f"program {args.program}, {len(data)} bytes")


if __name__ == '__main__':
    main()