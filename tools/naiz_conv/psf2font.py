#!/usr/bin/env python3
"""psf2font.py — Convert PSF1 console font to MHVN98 FONT.DAT format.

PSF1 format:
  Header: 4 bytes (magic 0x0436, mode, charsize)
  Glyph data: glyph_count × charsize bytes, row-major, MSB=leftmost

FONT.DAT format:
  Range list:  128 × uint16 start, uint16 end (LE16)
  Info list:   N × uint16 offset (LE16), uint8 w, uint8 h
  Glyph data:  N × 32 bytes (16 rows × 2 bytes big-endian word)

The PSF row byte goes into the high byte of a FONT.DAT row word;
the low byte is zero-padded.

Usage:
  python3 tools/naiz_conv/psf2font.py <input.psf.gz> <output.FONT.DAT>
  python3 tools/naiz_conv/psf2font.py --ascii-all <input.psf.gz> <output.FONT.DAT>
"""

import argparse
import gzip
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from naiz_lib.font_dat import build_font_dat

PSF1_MAGIC = b'\x36\x04'
FIRST_CHAR  = 0x21
LAST_CHAR   = 0x7E


def read_psf1(path):
    """Read PSF1 file, return (glyphs, charsize, glyph_count)."""
    if path.endswith('.gz'):
        with gzip.open(path, 'rb') as f:
            data = f.read()
    else:
        with open(path, 'rb') as f:
            data = f.read()

    if len(data) < 4:
        raise ValueError(f'File too small ({len(data)} bytes)')

    magic = data[0:2]
    if magic != PSF1_MAGIC:
        raise ValueError(f'Not a PSF1 file (magic {magic.hex()}, expected {PSF1_MAGIC.hex()})')

    mode = data[2]
    charsize = data[3]
    glyph_count = 512 if (mode & 3) else 256

    if charsize != 16:
        raise ValueError(f'Expected charsize=16 (8×16 font), got {charsize}')

    if glyph_count < LAST_CHAR + 1:
        raise ValueError(f'Font has only {glyph_count} glyphs, need at least {LAST_CHAR+1}')

    header_len = 4
    need = header_len + glyph_count * charsize
    if len(data) < need:
        raise ValueError(
            f'PSF data truncated: need {need} bytes, got {len(data)}')
    glyph_data = data[header_len:need]

    glyphs = []
    for i in range(glyph_count):
        glyphs.append(glyph_data[i * charsize : (i + 1) * charsize])

    return glyphs, charsize


def psf_glyph_to_font_row(row_byte):
    """Convert one PSF row byte to two FONT.DAT bytes (big-endian word)."""
    return bytes([row_byte, 0x00])


def build_font_dat_psf(glyphs, start, end):
    """Build FONT.DAT binary from list of PSF1 glyphs (8x16 cells)."""

    def glyph_bytes_for(cp):
        psf = glyphs[cp]
        out = bytearray()
        for row in range(16):
            out.extend(psf_glyph_to_font_row(psf[row]))
        return bytes(out)

    return build_font_dat(start, end, 8, 16, 2, glyph_bytes_for)


def main():
    parser = argparse.ArgumentParser(description='Convert PSF1 console font to MHVN98 FONT.DAT')
    parser.add_argument('input', help='Input PSF1 file (.psf or .psf.gz)')
    parser.add_argument('output', help='Output FONT.DAT file')
    parser.add_argument('--ascii-all', action='store_true',
                        help='Include all 128 ASCII chars (0x00-0x7F) instead of 0x21-0x7E')
    args = parser.parse_args()

    glyphs, _ = read_psf1(args.input)

    if args.ascii_all:
        start, end = 0x00, 0x7F
    else:
        start, end = FIRST_CHAR, LAST_CHAR

    data = build_font_dat_psf(glyphs, start, end)
    with open(args.output, 'wb') as f:
        f.write(data)

    total_chars = end - start + 1
    print(f"Generated {args.output} ({len(data)} bytes, {total_chars} chars, "
          f"range 0x{start:02X}-0x{end:02X})")


if __name__ == '__main__':
    main()
