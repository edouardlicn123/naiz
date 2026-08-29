#!/usr/bin/env python3
"""
CJK字库生成工具 — GNU Unifont .hex → CJK.DAT (16×16位掩码, 32字节/字)
使用透明字形方案，0像素不写入VRAM，避免黑边问题。

CJK.DAT格式:
  Header:  "CJKF" (4B) + range_count (uint16 LE) + reserved (uint32 LE)  = 10B
  Range[i]: start_cp (uint32 LE) + end_cp (uint32 LE)
           + glyph_offset (uint32 LE) + reserved (uint32 LE)  = 16B each
  Glyph:   32 bytes each (16行×2字节/行, 1bit/pixel, MSB左对齐)

Usage:
  python3 tools/naiz_font/gen_cjk_font.py unifont.hex -o CJK.DAT
  python3 tools/naiz_font/gen_cjk_font.py unifont.hex -o CJK.DAT \\
      --range U+4E00,U+9FFF --range U+3040,U+30FF
"""

import argparse
import struct
import sys
from pathlib import Path

GLYPH_BYTES = 32  # 16 rows × 2 bytes/row (bit-packed)

DEFAULT_RANGES = [
    ("Basic Latin",              0x0020, 0x007E),
    ("CJK Symbols & Punctuation",0x3000, 0x303F),
    ("Hiragana",                0x3040, 0x309F),
    ("Katakana",                0x30A0, 0x30FF),
    ("CJK Unified Ideographs",  0x4E00, 0x9FFF),
    ("Hangul Syllables",       0xAC00, 0xD7A3),
]

# Per-language range presets: name -> [(range_name, start, end), ...]
EXTENDED_LATIN = ("Extended Latin", 0x00C0, 0x00FF)
BASIC_LATIN = ("Basic Latin", 0x0020, 0x007E)
CJK_SYMBOLS = ("CJK Symbols & Punctuation", 0x3000, 0x303F)
HIRAGANA = ("Hiragana", 0x3040, 0x309F)
KATAKANA = ("Katakana", 0x30A0, 0x30FF)
CJK_IDEO = ("CJK Unified Ideographs", 0x4E00, 0x9FFF)
HANGUL = ("Hangul Syllables", 0xAC00, 0xD7A3)

LANG_RANGES = {
    "EN": [BASIC_LATIN],
    "FR": [BASIC_LATIN, EXTENDED_LATIN],
    "DE": [BASIC_LATIN, EXTENDED_LATIN],
    "IT": [BASIC_LATIN, EXTENDED_LATIN],
    "ES": [BASIC_LATIN, EXTENDED_LATIN],
    "PT": [BASIC_LATIN, EXTENDED_LATIN],
    "JP": [BASIC_LATIN, CJK_SYMBOLS, HIRAGANA, KATAKANA, CJK_IDEO],
    "CN": [BASIC_LATIN, CJK_SYMBOLS, CJK_IDEO],
    "CT": [BASIC_LATIN, CJK_SYMBOLS, CJK_IDEO],
    "KR": [BASIC_LATIN, CJK_SYMBOLS, CJK_IDEO, HANGUL],
}


def parse_range(s):
    parts = s.split(",")
    if len(parts) != 2:
        raise ValueError(f"Invalid range: {s}")
    a = parts[0].strip()
    b = parts[1].strip()
    if a.startswith("U+"): a = a[2:]
    if b.startswith("U+"): b = b[2:]
    return int(a, 16), int(b, 16)


def load_unifont(hex_path):
    """Return { codepoint: bytes(32) } — accepts 8px and 16px glyphs, centers 8px to 16×16"""
    glyphs = {}
    with open(hex_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            cp_str, rest = line.split(":", 1)
            hex_data = rest.split()[0].strip()
            hex_len = len(hex_data)
            if hex_len not in (32, 64):
                continue
            try:
                cp = int(cp_str, 16)
            except ValueError:
                continue
            try:
                raw = bytes.fromhex(hex_data)
            except ValueError:
                continue
            if hex_len == 32 and len(raw) == 16:
                # 8×16 → center in 16×16
                new_raw = bytearray(GLYPH_BYTES)
                for row in range(16):
                    new_raw[row * 2] = raw[row]
                    new_raw[row * 2 + 1] = 0x00
                glyphs[cp] = bytes(new_raw)
            elif len(raw) == GLYPH_BYTES:
                glyphs[cp] = raw
    return glyphs


def generate_all_langs(hex_path, output_dir="."):
    """Generate per-language CJK files for all languages in LANG_RANGES."""
    if not Path(hex_path).exists():
        print(f"Error: file not found: {hex_path}")
        sys.exit(1)

    print(f"Loading .hex: {hex_path}")
    glyphs = load_unifont(hex_path)
    print(f"  Loaded {len(glyphs)} glyphs")

    out_dir = Path(output_dir)
    for lang, preset in LANG_RANGES.items():
        ranges = [(s, e) for _, s, e in preset]
        out_file = out_dir / f"CJK_{lang}.DAT"
        generate_cjk_file(glyphs, ranges, str(out_file))
        print()


def generate_cjk_file(glyphs, ranges, output_path):
    """Generate a single CJK file from glyphs and ranges."""
    header_size = 10 + len(ranges) * 16
    total_glyphs = 0
    range_entries = []
    offset = header_size
    missing = 0

    glyph_data = bytearray()
    for start, end in ranges:
        count = end - start + 1
        range_entries.append((start, end, offset, 0))
        for cp in range(start, end + 1):
            if cp in glyphs:
                glyph_data.extend(glyphs[cp])
            else:
                glyph_data.extend(b'\x00' * GLYPH_BYTES)
                missing += 1
        offset += count * GLYPH_BYTES
        total_glyphs += count

    with open(output_path, "wb") as f:
        f.write(b"CJKF")
        f.write(struct.pack("<H", len(range_entries)))
        f.write(struct.pack("<I", 0))
        for start, end, goff, _ in range_entries:
            f.write(struct.pack("<IIII", start, end, goff, 0))
        f.write(glyph_data)

    fsize = Path(output_path).stat().st_size
    print(f"  Wrote: {output_path} ({len(ranges)} ranges, {total_glyphs} codepoints, {fsize:,} B)")


def main():
    parser = argparse.ArgumentParser(
        description="Generate CJK.DAT from GNU Unifont .hex")
    parser.add_argument("hex_file", nargs="?", default=None,
                        help="GNU Unifont .hex file (required for generation)")
    parser.add_argument("-o", "--output", default="CJK.DAT",
                        help="Output path (default: CJK.DAT)")
    parser.add_argument("--range", action="append", metavar="U+XXXX,U+YYYY",
                        help="Unicode range to include (repeatable)")
    parser.add_argument("--lang", metavar="LANG",
                        help="Language code (EN/FR/DE/IT/ES/PT/JP/CN/CT/KR)")
    parser.add_argument("--all-langs", action="store_true",
                        help="Generate all per-language CJK files at once")
    parser.add_argument("--list-ranges", action="store_true",
                        help="Print default ranges and exit")
    args = parser.parse_args()

    if args.list_ranges:
        print("Default CJK ranges:")
        for name, start, end in DEFAULT_RANGES:
            print(f"  {name}: U+{start:04X}–U+{end:04X}  ({end - start + 1} codepoints)")
        print("\nPer-language presets:")
        for lang, preset in LANG_RANGES.items():
            names = ", ".join(r[0] for r in preset)
            print(f"  {lang}: {names}")
        sys.exit(0)

    if args.all_langs:
        if not args.hex_file:
            parser.error("--all-langs requires a hex_file argument")
        out_dir = str(Path(args.output).parent) if args.output != "CJK.DAT" else "."
        generate_all_langs(args.hex_file, out_dir)
        sys.exit(0)

    if not args.hex_file:
        parser.error("hex_file is required for generation (use --list-ranges to see presets)")

    if args.lang:
        lang_upper = args.lang.upper()
        if lang_upper not in LANG_RANGES:
            print(f"Error: unknown language '{args.lang}' (use: {', '.join(LANG_RANGES)})")
            sys.exit(1)
        ranges = [(s, e) for _, s, e in LANG_RANGES[lang_upper]]
        if not args.output or args.output == "CJK.DAT":
            args.output = f"CJK_{lang_upper}.DAT"
    elif args.range:
        ranges = [parse_range(r) for r in args.range]
    else:
        ranges = [(s, e) for _, s, e in DEFAULT_RANGES]

    if not Path(args.hex_file).exists():
        print(f"Error: file not found: {args.hex_file}")
        sys.exit(1)

    print(f"Loading .hex: {args.hex_file}")
    glyphs = load_unifont(args.hex_file)
    print(f"  Loaded {len(glyphs)} glyphs")

    header_size = 10 + len(ranges) * 16  # 10B header + N×16B range entries
    total_glyphs = 0
    range_entries = []
    offset = header_size
    missing = 0

    glyph_data = bytearray()
    for start, end in ranges:
        count = end - start + 1
        range_entries.append((start, end, offset, 0))
        for cp in range(start, end + 1):
            if cp in glyphs:
                glyph_data.extend(glyphs[cp])
            else:
                glyph_data.extend(b'\x00' * GLYPH_BYTES)
                missing += 1
        offset += count * GLYPH_BYTES
        total_glyphs += count

    with open(args.output, "wb") as f:
        f.write(b"CJKF")
        f.write(struct.pack("<H", len(range_entries)))
        f.write(struct.pack("<I", 0))
        for start, end, goff, _ in range_entries:
            f.write(struct.pack("<IIII", start, end, goff, 0))
        f.write(glyph_data)

    fsize = Path(args.output).stat().st_size
    print(f"\nWrote: {args.output}")
    print(f"  Header: {header_size} B")
    print(f"  Ranges: {len(range_entries)}")
    print(f"  Codepoints: {total_glyphs} (missing: {missing})")
    print(f"  File size: {fsize:,} B ({fsize / 1024 / 1024:.2f} MiB)")

    # Verify
    with open(args.output, "rb") as f:
        magic = f.read(4)
        if magic != b"CJKF":
            raise RuntimeError(f"Bad magic: {magic}, expected CJKF")
        rc = struct.unpack("<H", f.read(2))[0]
        _ = f.read(4)  # skip reserved
        print("\nVerification:")
        print(f"  Magic: {magic}  Ranges: {rc}")
        for i in range(rc):
            s = struct.unpack("<I", f.read(4))[0]
            e = struct.unpack("<I", f.read(4))[0]
            o = struct.unpack("<I", f.read(4))[0]
            _ = f.read(4)
            print(f"  [{i}] U+{s:04X}–U+{e:04X}  offset={o}")

        # Validate header_size consistency
        expected_header = 10 + rc * 16
        if rc > 0:
            f.seek(10)  # back to first range entry
            s = struct.unpack("<I", f.read(4))[0]
            e = struct.unpack("<I", f.read(4))[0]
            o = struct.unpack("<I", f.read(4))[0]
            if o != expected_header:
                print(f"  [WARN] first range glyph_offset={o}, expected {expected_header}")
                print("  [WARN] Regenerate file — old CJK.DAT has stale offsets!")
            else:
                print(f"  [OK]   header_size={expected_header}, glyph_offset matches")

    print("\nDone.")


if __name__ == "__main__":
    main()
