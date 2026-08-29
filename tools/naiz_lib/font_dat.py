"""Shared FONT.DAT (MHVN98) container builder.

Both psf2font.py (PSF1 console fonts) and ttf2font.py (TrueType fonts)
produce the same MHVN98 FONT.DAT container layout:

  range list  — RANGE_COUNT x 4 bytes; entry 0 = (start, end) 16-bit pairs,
                remaining entries = 0xFFFF/0xFFFF (unused ranges)
  info list   — (glyph_count) x 4 bytes; each = (gaddr, cell_w, cell_h)
                <HBB, where gaddr is the glyph's byte offset in the file
  glyph data  — fixed stride per glyph (cell_h rows x row bytes)

The only per-source difference is the glyph encoding itself, so callers pass
a callable that yields the raw glyph byte string for each codepoint.
"""

import struct

RANGE_COUNT = 128


def build_font_dat(start, end, cell_w, cell_h, row_bytes, glyph_bytes_for):
    """Build FONT.DAT binary.

    @param start  First codepoint covered by the range list
    @param end    Last codepoint covered by the range list
    @param cell_w Glyph cell width (font info record)
    @param cell_h Glyph cell height (font info record)
    @param row_bytes Bytes per glyph row in the data section (stride / cell_h)
    @param glyph_bytes_for Callable(cp) -> raw glyph bytes (cell_h rows)
    @return FONT.DAT bytes
    """
    total = end - start + 1
    glyph_stride = cell_h * row_bytes
    info_base = RANGE_COUNT * 4
    first_glyph_offset = info_base + total * 4

    rangelist = bytearray(RANGE_COUNT * 4)
    struct.pack_into('<HH', rangelist, 0, start, end)
    for i in range(1, RANGE_COUNT):
        struct.pack_into('<HH', rangelist, i * 4, 0xFFFF, 0xFFFF)

    infolist = bytearray(total * 4)
    glyphdata = bytearray()
    for i in range(total):
        cp = start + i
        gaddr = first_glyph_offset + i * glyph_stride
        struct.pack_into('<HBB', infolist, i * 4, gaddr, cell_w, cell_h)
        glyphdata.extend(glyph_bytes_for(cp))

    return bytes(rangelist) + bytes(infolist) + bytes(glyphdata)
