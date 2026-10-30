#!/usr/bin/env python3
"""Dump the engine's FM sequence path to an S98 v3 register stream (devdoc 186,
was 模仿升级计划 161 §三 A).

Builds core/lib/fmseq.c (+fmopn.c, midi.c) with the host gcc, parses a real
SMF with the engine's own midi_parse(), replays it through fmseq_pump() with a
recording sink, and writes the observed OPNA port-A register writes as an S98
v3 file.  The result is a cross-replayer oracle: the same stream the engine
would push at the chip can be replayed offline by s98play / foobar2000
plugins to audit the packaged AUDIO.DAT patches without booting NP2kai.

S98 v3 encoding emitted (single device, bank0/port-A only):
  header (0x64 bytes): magic "S98", version 3, sync numerator=1,
      denominator=1000 (one sync == 1 ms), no compression, device table at
      0x64, dump body after it, loop offset pointing at the second pass when
      --loop >= 1 (0 = none), title/comment offsets 0.
  device table: one 0x10-byte entry {type=2 (OPNA), clock=7987200, 0, 0}
      terminated by 0xFFFFFFFF.
  command stream: 0xFF = advance 1 ms; 0xFE + VLQ(n) = advance n+2 ms;
      0x00-0x7F [reg val] = device 0 port 0 register write, 0x80-0xBF [reg
      val] = device 0 port 1.  fmseq's bank field is the 6-channel port
      split (fmopn_reg_addr: bank 0 = FM ch 0-2 port A, bank 1 = FM ch 3-5
      port B, chip register 0x100|reg), so the dump maps bank 0 -> port-0
      commands and bank 1 -> port-1 commands 1:1.
  The built-in reader (read_s98) mirrors this encoding 1:1 for round-trip
  verification; semantics follow libopna s98gen.c getvv (BSD-2, attribution
  in devdoc 186 §五).

Patches: --patch FILE (repeatable) takes 32-byte .fmp binaries (fm_patch.py
layout).  Without --patch a documented neutral patch (the fm_patch.py
docstring example) is used.  The game's shipped timbres live in AUDIO.DAT;
pass them here once extracted to audit the real packaging.

Usage:
    s98_dump.py <input.mid> <out.s98> [--patch FILE ...] [--gmmap FILE]
                [--loop N]
"""

import argparse
import ctypes
import os
import struct
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB_DIR = os.path.join(REPO_ROOT, "core", "lib")
LIB_C_FILES = ["fmseq.c", "fmopn.c", "midi.c"]

_S98_CLOCK = 7987200
_DEVICE_OPNA = 2
_HEADER_SIZE = 0x64
_LOOP_NONE = 0


class MidEventT(ctypes.Structure):
    _fields_ = [("tick_ms", ctypes.c_uint32),
                ("b0", ctypes.c_uint8),
                ("b1", ctypes.c_uint8),
                ("b2", ctypes.c_uint8)]


class SinkT(ctypes.Structure):
    _fields_ = [("ctx", ctypes.c_void_p),
                ("write", ctypes.c_void_p)]


_WRITE_FN = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int,
                             ctypes.c_uint8, ctypes.c_uint8)
_UNMAPPED_FN = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int)

_CACHE = {}


def build_lib():
    """Compile fmseq+fmopn+midi with the host gcc; return the CDLL."""
    mtime = max(os.stat(os.path.join(LIB_DIR, f)).st_mtime for f in LIB_C_FILES)
    if _CACHE.get("mtime") == mtime:
        return _CACHE["lib"]
    with tempfile.TemporaryDirectory(prefix="s98_dump_") as tmp:
        so = os.path.join(tmp, "fmseq.so")
        cmd = ["gcc", "-O2", "-shared", "-fPIC", "-I", LIB_DIR,
               "-fno-stack-protector"] + [os.path.join(LIB_DIR, f)
                                          for f in LIB_C_FILES]
        cmd += ["-o", so, "-lm"]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        _CACHE["lib"] = ctypes.CDLL(so)
        _CACHE["mtime"] = mtime
        return _CACHE["lib"]


def _bind(lib):
    lib.fmseq_size.restype = ctypes.c_size_t
    lib.fmseq_init.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                               ctypes.c_void_p, _UNMAPPED_FN, ctypes.c_void_p]
    lib.fmseq_events.argtypes = [ctypes.c_void_p,
                                 ctypes.POINTER(MidEventT), ctypes.c_int]
    lib.fmseq_pump.argtypes = [ctypes.c_void_p, ctypes.POINTER(SinkT),
                               ctypes.c_uint64]
    lib.fmseq_stop.argtypes = [ctypes.c_void_p, ctypes.POINTER(SinkT)]
    lib.fmseq_loop_start.argtypes = [ctypes.c_uint64, ctypes.c_uint64,
                                     ctypes.c_uint64]
    lib.fmseq_loop_start.restype = ctypes.c_uint64
    lib.midi_parse.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                               ctypes.POINTER(ctypes.POINTER(MidEventT)),
                               ctypes.POINTER(ctypes.c_int),
                               ctypes.POINTER(ctypes.c_uint32)]
    lib.midi_parse.restype = ctypes.c_int
    lib.midi_free.argtypes = [ctypes.POINTER(MidEventT)]


def default_patch():
    """Neutral 32-byte patch: the fm_patch.py docstring example."""
    ops = [
        # (dt, mul, tl, ks, ar, am, d1r, d2r, sl, rr)
        (2, 9, 40, 0, 24, 0, 5, 4, 1, 5),
        (0, 3, 42, 1, 20, 0, 5, 3, 1, 6),
        (0, 4, 44, 1, 20, 0, 4, 3, 1, 5),
        (0, 3, 46, 1, 24, 0, 5, 4, 2, 6),
    ]
    blob = bytearray(32)
    for i, (dt, mul, tl, ks, ar, am, d1r, d2r, sl, rr) in enumerate(ops):
        base = i * 6
        blob[base + 0] = (dt << 4) | mul
        blob[base + 1] = tl
        blob[base + 2] = (ks << 6) | ar
        blob[base + 3] = (am << 7) | d1r
        blob[base + 4] = d2r
        blob[base + 5] = (sl << 4) | rr
    blob[24] = (5 << 3) | 4          # FB<<3|ALG
    blob[25] = 3 << 6                # pan both channels, AMS/PMS 0
    return bytes(blob)


def load_patches(paths):
    blobs = []
    for p in paths or []:
        data = open(p, "rb").read()
        if len(data) != 32:
            raise SystemExit(f"ERROR: {p}: patch must be 32 bytes, "
                             f"got {len(data)}")
        blobs.append(data)
    if not blobs:
        blobs = [default_patch()]
    return blobs


def dump_stream(lib, smf_bytes, patch_blobs, gm_map_bytes=None, loops=1):
    """Replay the SMF through fmseq; return [(t_ms, bank, reg, val)] and the
    ms position where pass 2 begins (loop point), or None."""
    _bind(lib)

    recs = []

    def on_write(ctx, bank, reg, val):
        recs.append((int(cur[0]), int(bank), int(reg), int(val)))

    cb = _WRITE_FN(on_write)
    unmapped_cb = _UNMAPPED_FN(lambda ctx, ch, prog, fam: None)
    sink = SinkT()
    sink.write = ctypes.cast(cb, ctypes.c_void_p)

    seq = ctypes.create_string_buffer(lib.fmseq_size())
    pat = (ctypes.c_uint8 * 32 * len(patch_blobs))()
    for i, blob in enumerate(patch_blobs):
        for k, v in enumerate(blob):
            pat[i][k] = v
    gm = (ctypes.c_uint8 * 128)()
    if gm_map_bytes:
        if len(gm_map_bytes) != 128:
            raise SystemExit("ERROR: --gmmap must be 128 bytes")
        for k, v in enumerate(gm_map_bytes):
            gm[k] = v
    lib.fmseq_init(ctypes.addressof(seq), ctypes.addressof(pat),
                   len(patch_blobs), ctypes.addressof(gm),
                   unmapped_cb, None)

    ev_ptr = ctypes.POINTER(MidEventT)()
    count = ctypes.c_int()
    len_ms = ctypes.c_uint32()
    buf = ctypes.create_string_buffer(smf_bytes, len(smf_bytes))
    if lib.midi_parse(buf, len(smf_bytes), ctypes.byref(ev_ptr),
                      ctypes.byref(count), ctypes.byref(len_ms)) != 0:
        raise SystemExit("ERROR: midi_parse rejected the input SMF")
    if count.value <= 0 or len_ms.value == 0:
        raise SystemExit("ERROR: empty or zero-length stream")

    cur = [0]
    lib.fmseq_events(ctypes.addressof(seq), ev_ptr, count.value)
    for ms in range(1, len_ms.value + 1):
        cur[0] = ms
        lib.fmseq_pump(ctypes.addressof(seq), ctypes.byref(sink), ms)

    loop_ms = None
    start = len_ms.value
    for _ in range(max(0, loops - 1)):
        # Engine loop flow (audio.c ISR path): fmseq_stop() keyoffs every
        # voice and rewinds the event cursor to 0, then fmseq_loop_start()
        # rebases the pass start; the next pump replays the song.
        lib.fmseq_stop(ctypes.addressof(seq), ctypes.byref(sink))
        start = lib.fmseq_loop_start(start, len_ms.value, cur[0])
        loop_ms = loop_ms or cur[0]
        for ms in range(cur[0] + 1, start + len_ms.value + 1):
            cur[0] = ms
            lib.fmseq_pump(ctypes.addressof(seq), ctypes.byref(sink), ms)
    lib.midi_free(ev_ptr)
    return recs, loop_ms


def _vlq(n):
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def write_s98(path, recs, loop_ms=None):
    """Serialise records (t_ms, bank, reg, val) to an S98 v3 file."""
    recs = sorted(recs, key=lambda r: (r[0],))
    dev_table = struct.pack("<IIII", _DEVICE_OPNA, _S98_CLOCK, 0, 0) \
        + struct.pack("<I", 0xFFFFFFFF)
    dump_offset = _HEADER_SIZE + len(dev_table)

    stream = bytearray()
    loop_offset = _LOOP_NONE
    last_t = 0
    for t, bank, reg, val in recs:
        if loop_ms is not None and loop_offset == _LOOP_NONE and t >= loop_ms:
            loop_offset = dump_offset + len(stream)
            loop_ms = None            # mark emitted
        delta = t - last_t
        if delta == 1:
            stream.append(0xFF)
        elif delta >= 2:
            stream.append(0xFE)
            stream += _vlq(delta - 2)
        stream.append(0x00 if bank == 0 else 0x80)   # dev0 port 0 / port 1
        stream.append(reg)
        stream.append(val)
        last_t = t

    hdr = bytearray(_HEADER_SIZE)
    hdr[0:3] = b"S98"
    hdr[3] = 3
    struct.pack_into("<IIIIIIIII", hdr, 4,
                     1,              # sync numerator
                     1000,           # sync denominator -> tick = 1 ms
                     0,              # decompress
                     dump_offset,
                     _HEADER_SIZE,   # device table
                     loop_offset,
                     0,              # compress
                     0,              # title
                     0)              # comment
    with open(path, "wb") as f:
        f.write(bytes(hdr))
        f.write(dev_table)
        f.write(bytes(stream))
    return dump_offset, loop_offset


def read_s98(path):
    """Reader mirroring the writer (and libopna s98gen.c getvv semantics for
    the two-port subset): returns (header dict, [(t_ms, bank, reg, val)])."""
    data = open(path, "rb").read()
    if data[0:3] != b"S98":
        raise ValueError("bad magic")
    hdr = {"version": data[3]}
    (num, den, decompress, dump_off, dev_off, loop_off, compress,
     title_off, comment_off) = struct.unpack_from("<IIIIIIIII", data, 4)
    hdr.update(num=num, den=den, decompress=decompress, dump_off=dump_off,
               dev_off=dev_off, loop_off=loop_off, compress=compress,
               title_off=title_off, comment_off=comment_off)

    events = []
    t = 0
    pos = dump_off
    end = len(data)
    while pos < end:
        v = data[pos]
        pos += 1
        if v == 0xFF:
            t += 1
        elif v == 0xFE:
            n = 0
            while True:
                b = data[pos]
                pos += 1
                n = (n << 7) | (b & 0x7F)   # standard MSB-first VLQ
                if not (b & 0x80):
                    break
            t += n + 2
        elif v <= 0xBF:                     # 0x00-0x7F port 0, 0x80-0xBF port 1
            bank = 0 if v <= 0x7F else 1
            reg = data[pos]
            val = data[pos + 1]
            pos += 2
            events.append((t, bank, reg, val))
        else:
            raise ValueError(f"unsupported command 0x{v:02X} at {pos - 1}")
    return hdr, events


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", help="input .mid (SMF)")
    ap.add_argument("out", help="output .s98")
    ap.add_argument("--patch", action="append", default=[],
                    help="32-byte .fmp binary patch (repeatable)")
    ap.add_argument("--gmmap", help="128-byte GM program->family map")
    ap.add_argument("--loop", type=int, default=1,
                    help="total passes including the first (default 1)")
    args = ap.parse_args()

    lib = build_lib()
    smf = open(args.input, "rb").read()
    gm = open(args.gmmap, "rb").read() if args.gmmap else None
    recs, loop_ms = dump_stream(lib, smf, load_patches(args.patch), gm,
                                loops=args.loop)
    write_s98(args.out, recs, loop_ms)
    port0 = sum(1 for r in recs if r[1] == 0)
    print(f"{args.out}: {len(recs)} writes ({port0} port0 / "
          f"{len(recs) - port0} port1), last t={recs[-1][0]} ms, "
          f"loop={'yes' if loop_ms is not None else 'no'}")


if __name__ == "__main__":
    main()
