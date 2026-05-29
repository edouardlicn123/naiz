#!/usr/bin/env python3
"""Generate FONT.DAT for MHVN engine from ascii_char_cache in font_ascii.c.

FONT.DAT format (per fontfile.c):
- RangeList: 128×{uint16 first, uint16 last} = 512 bytes
- CharInfo: total_chars × uint32
- GlyphData: total_chars × 32 bytes (padded from 16 to 32)
"""

import re
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def parse_ascii_cache() -> bytes:
    src = REPO / "core" / "data" / "font_ascii.c"
    text = src.read_text()
    matches = re.findall(r'0b([01]{8})', text)
    if len(matches) != 1504:
        print(f"ERROR: expected 1504 bytes from ascii_char_cache, got {len(matches)}")
        sys.exit(1)
    return bytes(int(b, 2) for b in matches)


def generate_font(output_path: str):
    ascii_data = parse_ascii_cache()
    TOTAL_CHARS = 94
    FIRST_CHAR = 0x21
    LAST_CHAR = 0x7E

    # RangeList: 512 bytes (128 entries)
    rangelist = bytearray(512)
    struct.pack_into('<HH', rangelist, 0, FIRST_CHAR, LAST_CHAR)

    # CharInfo + GlyphData
    charinfo = bytearray(TOTAL_CHARS * 4)
    glyphdata = bytearray()

    for i in range(TOTAL_CHARS):
        offset = len(glyphdata)
        # entry: offset[0:21] | (w-1)[23] | yoff[24:27] | (h-1)[28:31]
        entry = offset | (0 << 23) | (0 << 24) | (0x0F << 28)
        struct.pack_into('<I', charinfo, i * 4, entry)

        row_data = ascii_data[i * 16 : (i + 1) * 16]
        glyphdata.extend(row_data)
        glyphdata.extend(b'\x00' * 16)

    out = REPO / output_path
    with open(out, 'wb') as f:
        f.write(rangelist)
        f.write(charinfo)
        f.write(glyphdata)

    total = len(rangelist) + len(charinfo) + len(glyphdata)
    print(f"Wrote {out} ({total} bytes, {TOTAL_CHARS} chars)")


def patch_rootinfo(dest_path: str, font_name: str = "FONT.DAT"):
    """Patch font_path at ROOTINFO.DAT offset +0x16 with null-padded font_name."""
    path = REPO / dest_path
    data = bytearray(path.read_bytes())
    font_bytes = font_name.encode('ascii')
    assert len(font_bytes) <= 12
    data[0x16:0x16 + 12] = font_bytes.ljust(12, b'\x00')
    path.write_bytes(data)
    print(f"Patched {path} font_path -> '{font_name}'")


if __name__ == '__main__':
    generate_font("games/demo-A1/FONT.DAT")
    patch_rootinfo("games/demo-A1/ROOTINFO.DAT")
