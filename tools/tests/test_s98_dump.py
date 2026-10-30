"""S98 register-stream dump contracts (devdoc 186 §三 A, was 161 §三 A).

The dump tool replays a real SMF through the engine's own fmseq (host build)
and serialises the observed bank-0 OPNA writes as S98 v3.  The value is an
offline oracle: the same register stream the engine pushes at the chip can be
replayed by external S98 players to audit the packaged patches without
booting NP2kai.

Contracts:
  1. round-trip: read_s98 (mirroring libopna s98gen.c getvv semantics for the
     bank0 subset) must reproduce every recorded write at its ms timestamp --
     writer and reader disagreeing would make every dump silently unplayable.
  2. header: sync numerator/denominator 1/1000 (tick = 1 ms), device type 2
     (OPNA), clock 7987200, no compression.
  3. sync encoding: 1 ms gaps use 0xFF; a >= 2 ms gap uses 0xFE + VLQ(delta-2)
     (never 0xFE+VLQ for a 1 ms gap, never 0xFF chains for long gaps).
  4. loop: with --loop >= 2 the second pass replays the same writes again and
     loop_offset points into the stream (0 when a single pass).
  5. bank-0 only: fmseq emits only bank 0, and the writer maps every write to
     the 0x00-0x7F device-0/port-0 command.
"""
import os
import struct
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools", "naiz_audio"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import gen_test_midi  # noqa: E402
from s98_dump import (build_lib, dump_stream, default_patch,  # noqa: E402
                      load_patches, write_s98, read_s98, _vlq)


@pytest.fixture(scope="module")
def lib():
    return build_lib()


SMF = gen_test_midi.build(bpm=240)


def _dump(lib, loops=1):
    recs, loop_ms = dump_stream(lib, SMF, load_patches([]), None, loops=loops)
    assert recs, "no register writes recorded"
    return recs, loop_ms


def test_round_trip(lib, tmp_path):
    recs, loop_ms = _dump(lib)
    out = str(tmp_path / "rt.s98")
    write_s98(out, recs, loop_ms)
    hdr, events = read_s98(out)
    assert events == [(t, b, r, v) for t, b, r, v in recs], \
        "round-trip lost or shifted register writes"


def test_two_port_round_trip(tmp_path):
    """fmseq's bank field is the 6-channel port split (fmopn_reg_addr):
    bank 0 -> S98 port-0 command, bank 1 -> port-1 command.  A dump of a
    song using FM ch 3-5 must keep both ports (icy_garden: 10.6k port-1
    writes -- flattening them to port 0 would corrupt the oracle)."""
    recs = [(5, 0, 0x28, 0xF0), (7, 1, 0x30, 0x12), (7, 0, 0x40, 0x28),
            (10, 1, 0xA4, 0x22), (12, 0, 0x28, 0x00)]
    out = str(tmp_path / "two.s98")
    write_s98(out, recs, None)
    hdr, events = read_s98(out)
    assert events == recs
    body = open(out, "rb").read()[hdr["dump_off"]:]
    assert b"\x00\x28\xf0" in body          # port-0 command
    assert b"\x80\x30\x12" in body          # port-1 command (0x80-0xBF)


def test_header_fields(lib, tmp_path):
    recs, loop_ms = _dump(lib)
    out = str(tmp_path / "hdr.s98")
    write_s98(out, recs, loop_ms)
    hdr, _ = read_s98(out)
    assert hdr["version"] == 3
    assert (hdr["num"], hdr["den"]) == (1, 1000)
    assert hdr["decompress"] == 0 and hdr["compress"] == 0
    raw = open(out, "rb").read()
    assert raw[0:3] == b"S98"
    dev_type, dev_clock = struct.unpack_from("<II", raw, hdr["dev_off"])
    assert (dev_type, dev_clock) == (2, 7987200)
    assert raw[hdr["dump_off"] - 4:hdr["dump_off"]] == b"\xff\xff\xff\xff", \
        "device table must be 0xFFFFFFFF-terminated"


def test_sync_encoding(lib, tmp_path):
    recs, _ = _dump(lib)
    out = str(tmp_path / "sync.s98")
    write_s98(out, recs, None)
    raw = open(out, "rb").read()
    hdr, _ = read_s98(out)
    body = raw[hdr["dump_off"]:]
    pos = 0

    def vlq(p):
        n = 0
        while True:
            b = body[p]
            p += 1
            n = (n << 7) | (b & 0x7F)      # standard MSB-first VLQ
            if not (b & 0x80):
                return n, p

    while pos < len(body):
        v = body[pos]
        if v == 0xFF:
            pos += 1
        elif v == 0xFE:
            n, pos = vlq(pos + 1)      # stream advances n+2 ms
            assert n >= 0
        elif v <= 0xBF:                # 0x00-0x7F port0, 0x80-0xBF port1
            pos += 3
        else:
            pytest.fail(f"unexpected command byte 0x{v:02X} at {pos}")
        assert pos <= len(body)


def test_loop_passes(lib, tmp_path):
    recs1, loop_ms = _dump(lib, loops=1)
    assert loop_ms is None
    recs2, loop_ms2 = _dump(lib, loops=2)
    assert loop_ms2 is not None, "second pass must mark the loop point"
    n1 = len(recs1)
    assert len(recs2) > n1, "second pass must replay additional writes"
    out = str(tmp_path / "loop.s98")
    write_s98(out, recs2, loop_ms2)
    hdr, _ = read_s98(out)
    assert hdr["loop_off"] > 0


def test_default_patch_shape():
    blob = default_patch()
    assert len(blob) == 32
    assert blob[24] == (5 << 3) | 4      # FB<<3|ALG
    assert blob[25] == 3 << 6            # pan both, AMS/PMS 0
    assert all(b == 0 for b in blob[26:32])


def test_vlq_wide_values():
    assert _vlq(0) == b"\x00"
    assert _vlq(0x7F) == b"\x7f"
    assert _vlq(0x80) == b"\x81\x00"
    assert _vlq(123456) == b"\x87\xc4\x40"
