#!/usr/bin/env python3
"""ttf2font.py — Render a TTF font into MHVN98 FONT.DAT-format 16x16 bitmap.

Used to build BLACK.DAT (blackletter Latin dialog glyphs, 16x16) for the
Naiz blackletter feature.

FONT.DAT layout (same as psf2font.py):
  Range list: 128 x (start LE16, end LE16), slot 0 used, rest 0xFFFF
  Info list:  N x (offset LE16, w, h)
  Glyph data: N glyphs, each 16 rows x (2 data bytes + 2 pad bytes) = 64 B

The engine font.c parser derives bytes_per_row=(16+7)/8=2 and row_bytes=4,
so a 16x16 glyph occupies 64 bytes in the file and 32 bytes (16x16 1-bit)
in the engine glyph cache.

Usage:
    python3 tools/naiz_conv/ttf2font.py \
        tools/naiz_font/UnifrakturMaguntia.ttf \
        tools/naiz_font/BLACK.DAT [--start 0x20 --end 0x7E]
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from PIL import Image, ImageDraw, ImageFont

from naiz_lib.font_dat import build_font_dat

CELL_W = 16
CELL_H = 16
ROW_BYTES = 4  # 2 data bytes + 2 pad per row
GLYPH_STRIDE = CELL_H * ROW_BYTES  # 64 bytes per glyph in file


def glyph_bits(font_path, ch, thresh=96, size=80):
    """Render one char to a 16x16 1-bit bitmap (32 bytes, MSB first).

    The char is drawn on a generous canvas (never clipped), the ink bbox
    is scaled to fit a 16x16 cell (aspect preserved, <=14 px), then
    bottom-aligned to row 15 and horizontally centered.
    """
    font = ImageFont.truetype(font_path, size)
    canvas = Image.new('L', (size * 4, size * 4), 0)
    ImageDraw.Draw(canvas).text((0, 0), ch, fill=255, font=font)

    bbox = canvas.getbbox()
    if not bbox:
        return bytearray(32)

    x0, y0, x1, y1 = bbox
    ink_w, ink_h = x1 - x0, y1 - y0
    scale = min(14.0 / ink_w, 14.0 / ink_h)
    scaled_w = max(1, int(ink_w * scale))
    scaled_h = max(1, int(ink_h * scale))

    region = canvas.crop(bbox).resize((scaled_w, scaled_h), Image.LANCZOS)
    out = Image.new('L', (CELL_W, CELL_H), 0)
    ox = (CELL_W - scaled_w) // 2
    oy = CELL_H - scaled_h - 1  # bottom-align to row 15
    if oy < 0:
        oy = 0
    out.paste(region, (ox, oy))

    bits = bytearray(32)
    px = out.load()
    for r in range(CELL_H):
        hi = lo = 0
        for c in range(CELL_W):
            if px[c, r] > thresh:
                if c < 8:
                    hi |= 1 << (7 - c)
                else:
                    lo |= 1 << (15 - c)
        bits[r * 2] = hi
        bits[r * 2 + 1] = lo
    return bits


def build_black_dat(font_path, start, end):
    """Build BLACK.DAT bytes (FONT.DAT format, 16x16 glyphs)."""

    def glyph_bytes_for(cp):
        bits = glyph_bits(font_path, chr(cp))
        out = bytearray()
        for row in range(CELL_H):
            out.append(bits[row * 2])        # high byte (leftmost)
            out.append(bits[row * 2 + 1])    # low byte
            out.extend((0, 0))               # 2 pad bytes
        return bytes(out)

    return build_font_dat(start, end, CELL_W, CELL_H, ROW_BYTES, glyph_bytes_for)


def main():
    parser = argparse.ArgumentParser(description='TTF -> 16x16 FONT.DAT bitmap')
    parser.add_argument('input', help='Input TTF path')
    parser.add_argument('output', help='Output FONT.DAT (e.g. BLACK.DAT)')
    parser.add_argument('--start', type=lambda s: int(s, 0), default=0x20,
                        help='First ASCII codepoint (default 0x20)')
    parser.add_argument('--end', type=lambda s: int(s, 0), default=0x7E,
                        help='Last ASCII codepoint (default 0x7E)')
    args = parser.parse_args()

    if args.start < 0 or args.end > 0x7F or args.start > args.end:
        print(f"ERROR: bad range {args.start:#x}-{args.end:#x}")
        sys.exit(1)

    data = build_black_dat(args.input, args.start, args.end)
    Path(args.output).write_bytes(data)
    total = args.end - args.start + 1
    print(f"Generated {args.output} ({len(data)} bytes, {total} chars, "
          f"{CELL_W}x{CELL_H}, stride {GLYPH_STRIDE}B)")


if __name__ == '__main__':
    main()
