"""MAG (MAKI02) codec round-trip and format tests.

Covers encode_mag / decode_mag_full / decode_mag_palette / expand_comp,
exercising both 4bpp and 8bpp paths plus sprite/bg user-string handling.
"""

import pytest

from naiz_lib import mag_codec
from naiz_lib import mag_constants


# ---------------------------------------------------------------------------
# expand_comp
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bits,value,expected", [
    (8, 0xAB, 0xAB),
    (3, 0x05, 0b10110110),
    (5, 0x15, 0xAD),
    (4, 0x0F, 0xFF),
    (1, 0x01, 0xFF),
    (2, 0x00, 0x00),
    (3, 0x07, 0xFF),
])
def test_expand_comp(bits, value, expected):
    assert mag_codec.expand_comp(value, bits) == expected


def test_expand_comp_full_width_identity():
    assert mag_codec.expand_comp(0x42, 8) == 0x42


# ---------------------------------------------------------------------------
# Round-trips
# ---------------------------------------------------------------------------

def _palette(n):
    return [(i * 16 % 256, i * 8 % 256, i * 4 % 256) for i in range(n)]


def test_roundtrip_4bpp():
    w, h = 8, 8
    pixels = bytes((x + y) % 16 for y in range(h) for x in range(w))
    pal = _palette(16)
    data = mag_codec.encode_mag(pixels, w, h, pal, bpp=4)
    assert data.startswith(mag_constants.MAG_SIGNATURE)
    px, dw, dh, dpal, bpp, is_sprite = mag_codec.decode_mag_full(data)
    assert (dw, dh) == (w, h)
    assert bpp == 4
    assert not is_sprite
    assert px == pixels
    assert dpal[0] == pal[0]


def test_roundtrip_8bpp():
    w, h = 4, 4
    pixels = bytes((i * 17) % 256 for i in range(w * h))
    pal = _palette(256)
    data = mag_codec.encode_mag(pixels, w, h, pal, bpp=8)
    px, dw, dh, dpal, bpp, is_sprite = mag_codec.decode_mag_full(data)
    assert (dw, dh) == (w, h)
    assert bpp == 8
    assert px == pixels
    assert dpal[0] == pal[0]


def test_roundtrip_sprite_marker():
    w, h = 2, 2
    pixels = bytes([0, 1, 2, 3])
    pal = _palette(16)
    user = mag_constants.MAG_SPRITE_MARKER + bytes([mag_constants.MAG_USER_TERM])
    data = mag_codec.encode_mag(pixels, w, h, pal, bpp=4, user_string=user)
    _, _, _, _, _, is_sprite = mag_codec.decode_mag_full(data)
    assert is_sprite


def test_roundtrip_bg_string():
    w, h = 2, 2
    pixels = bytes([0, 1, 2, 3])
    pal = _palette(16)
    data = mag_codec.encode_mag(pixels, w, h, pal, bpp=4, user_string=b"naiz\x1a")
    _, _, _, _, _, is_sprite = mag_codec.decode_mag_full(data)
    assert not is_sprite


def test_roundtrip_wide_non_multiple():
    """Odd width forces padding paths in the stream codec."""
    w, h = 7, 3
    pixels = bytes((x * 3 + y) % 16 for y in range(h) for x in range(w))
    pal = _palette(16)
    data = mag_codec.encode_mag(pixels, w, h, pal, bpp=4)
    px, dw, dh, _, _, _ = mag_codec.decode_mag_full(data)
    assert (dw, dh) == (w, h)
    assert px == pixels


def test_bpp4_palette_limit():
    with pytest.raises(ValueError):
        mag_codec.encode_mag(bytes(4), 2, 2, _palette(17), bpp=4)


def test_bpp8_palette_limit():
    with pytest.raises(ValueError):
        mag_codec.encode_mag(bytes(4), 2, 2, _palette(257), bpp=8)


def test_decode_truncated_returns_none():
    data = mag_codec.encode_mag(bytes(4), 2, 2, _palette(16), bpp=4)
    assert mag_codec.decode_mag_full(data[:10]) is None


def test_decode_bad_signature_returns_none():
    assert mag_codec.decode_mag_full(b"NOTMAG\0\0" + b"\0" * 40) is None


# ---------------------------------------------------------------------------
# decode_mag_palette
# ---------------------------------------------------------------------------

def test_decode_palette_8bpp_256():
    w, h = 2, 2
    pal = _palette(256)
    data = mag_codec.encode_mag(bytes(4), w, h, pal, bpp=8)
    dpal = mag_codec.decode_mag_palette(data)
    assert len(dpal) == 256
    assert dpal[0] == pal[0]
    assert dpal[255] == pal[255]


def test_decode_palette_bad_signature_empty():
    assert mag_codec.decode_mag_palette(b"\0" * 48) == []
