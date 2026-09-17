#!/usr/bin/env python3
"""WAV -> .pcm (8bit mono, 86-board rate code) converter (devdoc 101).

The engine plays sound/voice by streaming .pcm bytes into the 86-board
YM3433B FIFO — no runtime conversion.  Conversion cost + 16bit->8bit
downsample + stereo->mono merge + sample-rate snap happen here, at build
time, so the runtime path is a bare push of raw samples.

The real hardware accepts only 8 discrete PCM rates (3-bit code, A468
bits 2-0).  The source WAV sample rate is snapped to the nearest of these
(exactly matching the engine speed), and each sample is shifted to 8-bit.

Volume 1.0 means the source is used verbatim (8-bit shift only); a smaller
volume scales samples before the shift.  This mirrors how the 86-board
masters output volume — the knob is left at full, shaping happens here.

Usage:
    wav_convert.py <project_dir> <src.wav> <dst.pcm> --type SND|VC --name <key> [--vol 0.9]

Registers the new .pcm in ASSETS.DB img_map (type SND/VC) so the asset
table and AUDIO.DAT pick it up:
    INSERT INTO img_map (filename, type, name) VALUES (<dst>, <type>, <key>);
"""

import argparse
import os
import sqlite3
import struct
import sys
from pathlib import Path

# 86-board PCM rate code -> actual sample rate (Hz).  Order matters: the
# code is the index, so the list is indexed by the 3-bit field (devdoc 101
# §2.2).  Doubles are used for the snap only; the emitted byte is the code.
_PCM_RATES = (44100.0, 33075.0, 22050.0, 16537.5, 11025.0, 8268.75, 5501.25, 4134.375)

MAGIC = b"NAIZPCM\x00"  # 8-byte magic, byte 8 is the rate code
HDR_LEN = 16  # magic(8) + rate(1) + flags(1) + reserved(6)


def snap_rate(source_hz):
    """Nearest 86-board rate code for a source sample rate."""
    best = 0
    best_d = float("inf")
    for code, hz in enumerate(_PCM_RATES):
        d = abs(hz - source_hz)
        if d < best_d:
            best_d = d
            best = code
    return best


def wav_to_pcm(src, vol):
    """Read a WAV, return (rate_code, pcm_bytes) ready for the .pcm header.

    Accepts any byte count; validates the RIFF/fmt headers.  Mono is kept
    as-is, stereo is averaged.  16-bit is right-shifted then scaled; 8-bit
    is scaled directly.  Other bit depths raise ValueError (not supported
    by the 86-board path).  Raises ValueError on malformed input.
    """
    data = src.read()
    if len(data) < 44 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file (or shorter than 44 bytes)")

    if len(data) < 36 or data[12:16] != b"fmt ":
        raise ValueError("missing fmt chunk")

    fmt_size = struct.unpack_from('<I', data, 16)[0]
    if fmt_size < 16:
        raise ValueError(f"fmt chunk too small ({fmt_size})")

    audio_format, channels, sample_rate, _, _, bits = struct.unpack_from(
        '<HHIIHH', data, 20)

    if audio_format != 1:
        raise ValueError(f"unsupported format tag {audio_format} (need PCM 1)")
    if channels not in (1, 2):
        raise ValueError(f"unsupported channel count {channels}")
    if bits not in (8, 16):
        raise ValueError(f"unsupported bit depth {bits}")

    if not (0.0 < vol <= 1.0):
        raise ValueError(f"volume out of range: {vol}")

    # Locate the 'data' chunk (position may be before/after other chunks).
    pos = 12
    data_off, data_len = None, 0
    while pos + 8 <= len(data):
        cid = data[pos:pos + 4]
        (clen,) = struct.unpack_from('<I', data, pos + 4)
        if cid == b'data':
            data_off = pos + 8
            data_len = clen
            break
        pos = pos + 8 + clen + (clen & 1)  # chunks are word-aligned
    if data_off is None:
        raise ValueError("no data chunk")

    raw_len = min(data_len, len(data) - data_off)
    if raw_len == 0:
        raise ValueError("empty data chunk")
    if bits == 16:
        if raw_len % 2:
            raw_len -= 1
        nsamp = raw_len // 2
        samples = struct.unpack_from('<%dh' % nsamp, data, data_off)
        mono = []
        if channels == 2:
            for i in range(nsamp // 2):
                s = (samples[2 * i] + samples[2 * i + 1]) // 2
                mono.append(s)
        else:
            mono = list(samples)
        pcm = bytearray(len(mono))
        for i, s in enumerate(mono):
            v = int(s * vol) >> 8  # 16bit -> 8bit
            if v < -128:
                v = -128
            elif v > 127:
                v = 127
            pcm[i] = v & 0xFF
    else:  # 8-bit unsigned
        if channels == 2:
            span = raw_len - (raw_len & 1)
            nframe = span // 2
            pcm = bytearray(nframe)
            for i in range(nframe):
                s = (data[data_off + 2 * i] - 128 +
                     data[data_off + 2 * i + 1] - 128) // 2
                s = int(s * vol)
                s = max(-128, min(127, s))
                pcm[i] = s & 0xFF
        else:
            pcm = bytearray(raw_len)
            for i in range(raw_len):
                s = int((data[data_off + i] - 128) * vol)
                s = max(-128, min(127, s))
                pcm[i] = s & 0xFF

    rate_code = snap_rate(sample_rate)
    hdr = MAGIC + bytes([rate_code, 0]) + b"\0" * 6
    return rate_code, bytes(hdr) + bytes(pcm)


def register_asset(project_dir, dst_pcm, asset_type, name):
    """INSERT the .pcm into ASSETS.DB img_map (SND or VC).  Idempotent:
    an existing row with the same filename updates name/type instead."""
    db_path = os.path.join(project_dir, 'ASSETS.DB')
    if not os.path.isfile(db_path):
        print(f"ERROR: ASSETS.DB not found: {db_path}")
        sys.exit(1)
    if asset_type not in ('SND', 'VC'):
        raise ValueError(f"audio asset type must be SND or VC, got {asset_type}")

    db = sqlite3.connect(db_path)
    try:
        row = db.execute(
            "SELECT id FROM img_map WHERE filename=? AND type IN ('SND','VC')",
            (dst_pcm,)).fetchone()
        if row is not None:
            db.execute(
                "UPDATE img_map SET type=?, name=? WHERE id=?",
                (asset_type, name, row[0]))
            print(f"  ASSETS.DB: updated id={row[0]} → {dst_pcm} ({asset_type})")
        else:
            cur = db.execute(
                "INSERT INTO img_map (filename, type, name) VALUES (?,?,?)",
                (dst_pcm, asset_type, name))
            print(f"  ASSETS.DB: registered id={cur.lastrowid} {dst_pcm} ({asset_type})")
        db.commit()
    finally:
        db.close()


def main():
    ap = argparse.ArgumentParser(description="WAV -> 86-board .pcm")
    ap.add_argument("project_dir", help="project directory (ASSETS.DB lives here)")
    ap.add_argument("src", help="source WAV file")
    ap.add_argument("dst", help="output .pcm file")
    ap.add_argument("--type", choices=('SND', 'VC'), required=True)
    ap.add_argument("--name", required=True, help="script key (e.g. chime)")
    ap.add_argument("--vol", type=float, default=1.0, help="volume scale 0-1")
    args = ap.parse_args()

    dst = Path(args.dst)
    if dst.suffix.lower() != ".pcm":
        print(f"ERROR: destination must end in .pcm: {args.dst}")
        sys.exit(1)

    try:
        with open(args.src, 'rb') as f:
            rate_code, payload = wav_to_pcm(f, args.vol)
    except OSError as e:
        print(f"ERROR: cannot read {args.src}: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"ERROR: {args.src}: {e}")
        sys.exit(1)

    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        dst.write_bytes(payload)
    except OSError as e:
        print(f"ERROR: cannot write {args.dst}: {e}")
        sys.exit(1)
    print(f"  {args.src} → {args.dst}: 8bit mono, rate code {rate_code} "
          f"({_PCM_RATES[rate_code]:.0f} Hz), {len(payload)} bytes")

    register_asset(args.project_dir, args.dst, args.type, args.name)


if __name__ == '__main__':
    main()