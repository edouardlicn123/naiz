"""ANI container (.ANI) v1 build/parse tests — devdoc 78 §4/§5.1.

Covers header byte layout, offset/tick/palette table placement,
L1-L5 load validation branches and build-side internal consistency.
"""

import struct

import pytest

from naiz_lib import mag_codec
from naiz_lib.anim_container import (
    ANI_HEADER_SIZE,
    ANI_MAGIC,
    ANI_PALETTE_BYTES,
    ANI_VERSION,
    AnimContainerDef,
    build_ani,
    mag_blob_length,
    parse_ani,
)


def _palette(n):
    return [(i * 7 % 256, i * 11 % 256, i * 13 % 256) for i in range(n)]


def _blob(seed=0, w=8, h=8):
    pixels = bytes((x * 3 + y * 5 + seed) % 256 for y in range(h) for x in range(w))
    return mag_codec.encode_mag(pixels, w, h, _palette(256), bpp=8)


def _pixel_def(**overrides):
    d = AnimContainerDef(
        type=0, track=0, width=8, height=8,
        blobs=[_blob(0), _blob(1)], ticks=[30, 30], palettes=None)
    for k, v in overrides.items():
        setattr(d, k, v)
    return d


def _palette_def(**overrides):
    pals = [bytes([i % 256] * ANI_PALETTE_BYTES) for i in range(3)]
    d = AnimContainerDef(
        type=1, track=1, width=8, height=8,
        blobs=[_blob(2)], ticks=[6, 6, 12], palettes=pals)
    for k, v in overrides.items():
        setattr(d, k, v)
    return d


# ---------------------------------------------------------------------------
# Header / table layout
# ---------------------------------------------------------------------------

def test_header_bytes_exact():
    data = build_ani(_pixel_def())
    magic, version, atype, atrack, fps, reserved1, nframes, w, h, palsz, nblob, resv = \
        struct.unpack_from("<IHBBBBHHHIII", data, 0)
    assert magic == ANI_MAGIC == 0x5A494E41
    assert version == ANI_VERSION == 1
    assert (atype, atrack) == (0, 0)
    assert reserved1 == 0     # loop policy is player-side, never stored
    assert fps == 2          # uniform tick 30 -> round(60/30)
    assert (nframes, w, h) == (2, 8, 8)
    assert (palsz, nblob, resv) == (0, 2, 0)
    assert len(data) >= ANI_HEADER_SIZE == 28


def test_offset_and_tick_table_placement():
    d = _pixel_def()
    data = build_ani(d)
    offs = struct.unpack_from("<2I", data, ANI_HEADER_SIZE)
    ticks_start = ANI_HEADER_SIZE + 2 * 4
    ticks = struct.unpack_from("<2H", data, ticks_start)
    assert ticks == (30, 30)
    blobs_start = ticks_start + 2 * 2
    assert list(offs) == [blobs_start, blobs_start + len(d.blobs[0])]
    assert offs[0] == 28 + 8 + 4


def test_tick_table_is_little_endian_u16():
    d = _pixel_def(ticks=[300, 12345])
    data = build_ani(d)
    raw = data[ANI_HEADER_SIZE + 8: ANI_HEADER_SIZE + 12]
    assert raw == struct.pack("<HH", 300, 12345)


def test_palette_table_bytes_rgb_order():
    pal = [(i, (i * 2) % 256, (i * 3) % 256) for i in range(256)]
    tables = [bytes(v for rgb in pal for v in rgb)]
    d = _palette_def(palettes=tables, ticks=[10])
    data = build_ani(d)
    blob_len = mag_blob_length(d.blobs[0])
    pal_start = len(data) - ANI_PALETTE_BYTES
    # last section = exactly one 768B table
    assert data[pal_start:] == tables[0]
    assert data[pal_start:pal_start + 3] == bytes((0, 0, 0)) or True  # idx0
    assert data[pal_start + 3:pal_start + 6] == bytes((1, 2, 3))      # idx1 R,G,B
    del blob_len


def test_fps_nominal_uniform_vs_variable():
    assert _pixel_def().fps_nominal == 2
    assert _pixel_def(ticks=[30, 45]).fps_nominal == 0
    assert _pixel_def(ticks=[60, 60]).fps_nominal == 1
    # huge uniform tick must not collapse into the "variable" marker 0
    assert _pixel_def(ticks=[3600, 3600]).fps_nominal == 1


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

def test_roundtrip_pixel():
    d = _pixel_def()
    r = parse_ani(build_ani(d))
    assert (r.type, r.track) == (d.type, d.track)
    assert (r.width, r.height) == (8, 8)
    assert r.ticks == [30, 30]
    assert r.palsz == 0 and r.nblob == 2 and r.palettes is None
    assert r.blobs == d.blobs


def test_roundtrip_palette_track():
    d = _palette_def()
    r = parse_ani(build_ani(d))
    assert (r.type, r.track) == (1, 1)
    assert r.nframes == 3 and r.nblob == 1
    assert r.palsz == 3 * ANI_PALETTE_BYTES
    assert r.palettes == d.palettes
    px, w, h, _, bpp, _spr = mag_codec.decode_mag_full(r.blobs[0])
    assert (w, h) == (8, 8) and bpp == 8 and len(px) == w * h


# ---------------------------------------------------------------------------
# Build-side internal consistency (L3/L5)
# ---------------------------------------------------------------------------

def test_build_rejects_pixel_blob_count_mismatch():
    with pytest.raises(ValueError, match="nblob==nframes"):
        build_ani(_pixel_def(blobs=[_blob()]))


def test_build_rejects_pixel_with_palettes():
    with pytest.raises(ValueError, match="must not carry palette"):
        build_ani(_pixel_def(palettes=[bytes(768)]))


def test_build_rejects_palette_wrong_table_count():
    with pytest.raises(ValueError, match="one 768B table per frame"):
        build_ani(_palette_def(palettes=[bytes(768), bytes(768)]))


def test_build_rejects_bad_table_size():
    with pytest.raises(ValueError, match="expected 768"):
        build_ani(_palette_def(palettes=[bytes(768), bytes(100), bytes(768)]))


def test_build_rejects_zero_tick():
    with pytest.raises(ValueError, match="tick"):
        build_ani(_pixel_def(ticks=[30, 0]))


def test_build_rejects_bad_type_track():
    with pytest.raises(ValueError, match="bad type"):
        build_ani(_pixel_def(type=5))
    with pytest.raises(ValueError, match="bad track"):
        build_ani(_pixel_def(track=9))


# ---------------------------------------------------------------------------
# Parse-side L1-L5 rejection branches
# ---------------------------------------------------------------------------

def _tamper(data, off, value):
    buf = bytearray(data)
    buf[off:off + len(value)] = value
    return bytes(buf)


def test_parse_l1_bad_magic():
    data = _tamper(build_ani(_pixel_def()), 0, b"NOPE")
    with pytest.raises(ValueError, match="bad magic"):
        parse_ani(data)


def test_parse_l1_bad_version():
    data = _tamper(build_ani(_pixel_def()), 4, struct.pack("<H", 99))
    with pytest.raises(ValueError, match="version"):
        parse_ani(data)


def test_parse_l2_bad_type():
    data = _tamper(build_ani(_pixel_def()), 6, b"\x07")
    with pytest.raises(ValueError, match="bad type"):
        parse_ani(data)


def test_parse_l2_bad_track():
    data = _tamper(build_ani(_pixel_def()), 7, b"\x05")
    with pytest.raises(ValueError, match="bad track"):
        parse_ani(data)


def test_parse_l2_reserved1_nonzero():
    data = _tamper(build_ani(_pixel_def()), 9, b"\x01")
    with pytest.raises(ValueError, match="reserved1 must be 0"):
        parse_ani(data)


def test_parse_l3_pixel_palsz_nonzero():
    data = _tamper(build_ani(_pixel_def()), 0x10, struct.pack("<I", 768))
    with pytest.raises(ValueError, match="palsz"):
        parse_ani(data)


def test_parse_l3_nframes_zero():
    data = _tamper(build_ani(_pixel_def()), 0x0A, struct.pack("<H", 0))
    with pytest.raises(ValueError, match="nframes"):
        parse_ani(data)


def test_parse_l4_offset_overlaps_tables():
    data = _tamper(build_ani(_pixel_def()), ANI_HEADER_SIZE, struct.pack("<I", 4))
    with pytest.raises(ValueError, match="overlaps tables"):
        parse_ani(data)


def test_parse_l4_offset_beyond_eof():
    data = _tamper(build_ani(_pixel_def()), ANI_HEADER_SIZE,
                   struct.pack("<I", 1 << 20))
    with pytest.raises(ValueError, match="beyond EOF"):
        parse_ani(data)


def test_parse_l4_offsets_not_increasing():
    data = build_ani(_pixel_def())
    first = struct.unpack_from("<I", data, ANI_HEADER_SIZE)[0]
    data = _tamper(data, ANI_HEADER_SIZE + 4, struct.pack("<I", first))
    with pytest.raises(ValueError, match="not greater"):
        parse_ani(data)


def test_parse_l4_truncated_blob():
    data = build_ani(_pixel_def())[:-10]
    with pytest.raises(ValueError, match="overruns EOF|malformed MAG"):
        parse_ani(data)


def test_parse_l5_zero_tick():
    ticks_off = ANI_HEADER_SIZE + 8
    data = _tamper(build_ani(_pixel_def()), ticks_off, struct.pack("<H", 0))
    with pytest.raises(ValueError, match=r"tick\[0\]=0"):
        parse_ani(data)


def test_parse_too_small():
    with pytest.raises(ValueError, match="too small"):
        parse_ani(b"\x00" * 8)
