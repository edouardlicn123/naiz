"""IMAGE.DAT archive format: TOC iteration and shared-palette verification."""

import struct

import pytest

from naiz_lib import image_dat
from naiz_lib import mag_codec


def _build_image_dat(entries):
    """entries: list of (name_bytes_12, data_bytes). Returns IMAGE.DAT bytes."""
    count = len(entries)
    header_size = image_dat.IMAGE_DAT_HEADER + count * image_dat.IMAGE_DAT_TOC_SIZE
    buf = bytearray(struct.pack('<I', count))
    offset = header_size
    for name, data in entries:
        buf.extend(name.ljust(12, b'\0'))
        buf.extend(struct.pack('<II', offset, len(data)))
        offset += len(data)
    for _, data in entries:
        buf.extend(data)
    return bytes(buf)


def _mag_with_palette(pal):
    w, h = 2, 2
    return mag_codec.encode_mag(bytes(4), w, h, pal, bpp=8)


def _shared_256_palette():
    pal = [(0, 0, 0)] * 256
    pal[7] = (255, 255, 255)
    pal[15] = (255, 255, 255)
    for j in range(248, 256):
        pal[j] = (0, 0, 0)
    pal[1] = (100, 50, 25)
    return pal


# ---------------------------------------------------------------------------
# iter_image_dat_toc
# ---------------------------------------------------------------------------

def test_toc_iteration_roundtrip():
    data = b"ENTRY0DATA"
    img = _build_image_dat([(b"A.DAT", data), (b"B.DAT", b"XYZ")])
    toc = list(image_dat.iter_image_dat_toc(img))
    assert len(toc) == 2
    assert toc[0][1] == b"A.DAT" + b"\x00" * 7
    assert toc[0][3] == 10
    assert img[toc[0][2]:toc[0][2] + toc[0][3]] == data
    assert toc[1][1] == b"B.DAT" + b"\x00" * 7
    assert img[toc[1][2]:toc[1][2] + toc[1][3]] == b"XYZ"


def test_toc_truncated_header():
    assert list(image_dat.iter_image_dat_toc(b"")) == []
    assert list(image_dat.iter_image_dat_toc(b"\x02\x00\x00\x00")) == []


def test_toc_truncated_entries_stops():
    img = _build_image_dat([(b"A.DAT", b"D")])
    truncated = img[:-1]
    toc = list(image_dat.iter_image_dat_toc(truncated))
    assert len(toc) <= 1


# ---------------------------------------------------------------------------
# verify_shared_palette
# ---------------------------------------------------------------------------

def test_verify_shared_palette_ok():
    pal = _shared_256_palette()
    mag = _mag_with_palette(pal)
    img = _build_image_dat([(b"A.MAG", mag), (b"B.MAG", mag)])
    assert image_dat.verify_shared_palette(img) == []


def test_verify_shared_palette_protected_indices():
    pal = _shared_256_palette()
    pal[7] = (0, 0, 0)  # white index corrupted
    mag = _mag_with_palette(pal)
    img = _build_image_dat([(b"A.MAG", mag)])
    errors = image_dat.verify_shared_palette(img)
    assert any("idx 7" in e for e in errors)


def test_verify_shared_palette_detects_mismatch():
    pal_a = _shared_256_palette()
    pal_b = list(_shared_256_palette())
    pal_b[1] = (0, 0, 0)  # different entry 1
    mag_a = _mag_with_palette(pal_a)
    mag_b = _mag_with_palette(pal_b)
    img = _build_image_dat([(b"A.MAG", mag_a), (b"B.MAG", mag_b)])
    errors = image_dat.verify_shared_palette(img)
    assert any("differs" in e for e in errors)


def test_verify_shared_palette_truncated():
    pal = _shared_256_palette()
    mag = _mag_with_palette(pal)
    img = _build_image_dat([(b"A.MAG", mag)])
    # Corrupt the payload so eoff+esz overruns the buffer
    bad = img[:len(img) - 5]
    errors = image_dat.verify_shared_palette(bad)
    assert any("truncated" in e for e in errors)


def test_verify_shared_palette_empty_input():
    assert image_dat.verify_shared_palette(b"") == []
    assert image_dat.verify_shared_palette(b"\x00\x00\x00\x00") == []
