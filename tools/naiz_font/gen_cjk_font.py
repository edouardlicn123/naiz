#!/usr/bin/env python3
"""
CJK字库生成工具 — GNU Unifont .hex → CJK.DAT (16×16位掩码, 32字节/字)
使用透明字形方案，0像素不写入VRAM，避免黑边问题。

CJK.DAT格式:
  Header:  "CJKF" (4B) + range_count (uint16 LE) + reserved (uint32 LE)  = 10B
  Range[i]: start_cp (uint32 LE) + end_cp (uint32 LE)
           + glyph_offset (uint32 LE) + reserved (uint32 LE)  = 16B each
  Glyph:   32 bytes each (16行×2字节/行, 1bit/pixel, MSB左对齐)

字形源（逐码位优先级从左到右）:
  P1  GNU Unifont .hex（全 BMP 覆盖）
  P2  CJKF 图集子集（tools/naiz_font/CJK.DAT，旧 6 区间内容）
  (兜底) 零填字形 + 逐码位 WARN，永不静默

Usage:
  python3 tools/naiz_font/gen_cjk_font.py unifont.hex -o CJK.DAT
  python3 tools/naiz_font/gen_cjk_font.py unifont.hex -o CJK.DAT \\
      --range U+4E00,U+9FFF --range U+3040,U+30FF
  python3 tools/naiz_font/gen_cjk_font.py --collect-dir projects/demo-a2 \\
      --collect-lang kor --atlas tools/naiz_font/CJK.DAT -o CJK_KOR.DAT
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
# No Basic Latin anywhere: ASCII (U+0020-007E) is owned by FONT.DAT at runtime
# (render_text.c ASCII path), the CJK fonts carry multibyte codepoints only.
EXTENDED_LATIN = ("Latin-1 Supplement", 0x00A0, 0x00FF)  # full block (was U+00C0-00FF, missed ¡¿×÷)
CJK_SYMBOLS = ("CJK Symbols & Punctuation", 0x3000, 0x303F)
HIRAGANA = ("Hiragana", 0x3040, 0x309F)
KATAKANA = ("Katakana", 0x30A0, 0x30FF)
CJK_IDEO = ("CJK Unified Ideographs", 0x4E00, 0x9FFF)
HANGUL = ("Hangul Syllables", 0xAC00, 0xD7A3)

# Preset keys follow the runtime language codes (settings_menu.c), uppercased.
# CJK file names therefore match what cjk_load_for_lang() builds: CJK_<LANG>.DAT.
# ASI: ASCII is FONT.DAT-owned, so these are the multibyte-only blocks per family.
LANG_RANGES = {
    "ENG": [],
    "FRE": [EXTENDED_LATIN],
    "GER": [EXTENDED_LATIN],
    "ITA": [EXTENDED_LATIN],
    "SPA": [EXTENDED_LATIN],
    "POR": [EXTENDED_LATIN],
    "JPN": [CJK_SYMBOLS, HIRAGANA, KATAKANA, CJK_IDEO],
    "CHI": [CJK_SYMBOLS, CJK_IDEO],
    "CHT": [CJK_SYMBOLS, CJK_IDEO],
    "KOR": [CJK_SYMBOLS, CJK_IDEO, HANGUL],
}

# Runtime language codes from core/engine/settings_menu.c (single source of truth).
RUNTIME_LANGS = ["eng", "jpn", "chi", "cht", "kor", "fre", "ger", "ita", "spa", "por"]
CJK_FAMILY = {"jpn", "chi", "cht", "kor"}
LATIN_FAMILY = {"fre", "ger", "ita", "spa", "por"}
CJK_BASE = (0x3000, 0x303F)   # CJK Symbols & Punctuation, mandatory for CJK-family
LATIN_BASE = (0x00A0, 0x00FF)  # Latin-1 Supplement, mandatory for Latin-family

MAX_RANGES = 2048        # mirror core/lib/cjk.c MAX_CJK_RANGES
WARN_LIST_MAX = 60       # per-missing-block WARN line cap


def parse_range(s):
    parts = s.split(",")
    if len(parts) != 2:
        raise ValueError(f"Invalid range: {s}")
    a = parts[0].strip()
    b = parts[1].strip()
    if a.startswith("U+"):
        a = a[2:]
    if b.startswith("U+"):
        b = b[2:]
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


def _iter_multibyte_cps(text):
    """Yield printable multibyte codepoints (>= 0x80) from a string."""
    for ch in text:
        cp = ord(ch)
        if 0x80 <= cp <= 0xD7FF or 0xE000 <= cp <= 0x10FFFF:
            yield cp


def collect_nb_cps(nb_path):
    """Collect multibyte codepoints from every non-comment NB line."""
    cps = set()
    with open(nb_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line or line.lstrip().startswith("#"):
                continue
            cps.update(_iter_multibyte_cps(line))
    return cps


def collect_i18n_cps(i18n_path):
    """Collect multibyte codepoints from i18n translation VALUES (right of '=').

    Mirrors tr.c/load_file + i18n_gen conventions: skip blanks and '#' comment
    lines (incl. '# ORPHANED:'), split at the first '='.  Untranslated 'key='
    entries contribute nothing.
    """
    cps = set()
    with open(i18n_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            eq = line.find("=")
            if eq < 0:
                continue
            cps.update(_iter_multibyte_cps(line[eq + 1:]))
    return cps


def collect_cps(proj_dir, lang, with_base=True):
    """Collect corpus codepoints for a runtime language code.

    Sources: project scene/*.nb (all text payloads) + i18n/*_<lang>.txt values.
    Optionally folds in the language-family base block.
    """
    cps = set()
    proj = Path(proj_dir)
    scene = proj / "scene"
    if scene.is_dir():
        for nb in sorted(scene.glob("*.nb")):
            cps |= collect_nb_cps(nb)
    i18n = proj / "i18n"
    if i18n.is_dir():
        for prefix in ("system", "role", "game"):
            f = i18n / f"{prefix}_{lang}.txt"
            if f.exists():
                cps |= collect_i18n_cps(f)
    if with_base:
        for bs, be in lang_base_ranges(lang):
            cps.update(range(bs, be + 1))
    return cps


def lang_base_ranges(lang):
    """Family base ranges for a runtime language code (empty for eng)."""
    if lang in CJK_FAMILY:
        return [CJK_BASE]
    if lang in LATIN_FAMILY:
        return [LATIN_BASE]
    return []


def merge_ranges(cps):
    """Merge sorted codepoints into ascending inclusive ranges [(start,end),...].

    Ascending order is REQUIRED by the engine binary search (cjk.c); the first
    range's glyph_offset must equal the header size (enforced by generate_cjk_file).
    """
    ranges = []
    for cp in sorted(cps):
        if ranges and cp == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], cp)
        else:
            ranges.append((cp, cp))
    return ranges


def subset_from_atlas(atlas_path, cps=None):
    """Read a codepoint→glyph dict from a CJKF atlas (P2 glyph source).

    Returns only the requested cps the atlas covers; when cps is None every
    atlas glyph is returned.
    """
    data = Path(atlas_path).read_bytes()
    if data[:4] != b"CJKF":
        raise ValueError(f"{atlas_path}: not a CJKF atlas")
    rc = struct.unpack("<H", data[4:6])[0]
    out = {}
    for i in range(rc):
        off = 10 + i * 16
        start, end, goff = struct.unpack("<III", data[off:off + 12])
        for cp in range(start, end + 1):
            if cps is not None and cp not in cps:
                continue
            base = goff + (cp - start) * GLYPH_BYTES
            out[cp] = data[base:base + GLYPH_BYTES]
    return out


def merge_glyph_sources(sources, cps):
    """Pick the first available glyph for each cp across ordered sources."""
    glyphs = {}
    for cp in cps:
        for src in sources:
            if cp in src:
                glyphs[cp] = src[cp]
                break
    return glyphs


def generate_cjk_file(glyphs, ranges, output_path):
    """Generate a single CJK file from a glyph dict and ascending ranges.

    Codepoints inside ranges without a source glyph become zero-filled and are
    reported with per-codepoint WARN lines (first WARN_LIST_MAX) — never silent.
    Returns the list of missing codepoints.
    """
    if len(ranges) > MAX_RANGES:
        raise ValueError(
            f"{len(ranges)} ranges exceed engine MAX_CJK_RANGES ({MAX_RANGES})")
    header_size = 10 + len(ranges) * 16
    range_entries = []
    offset = header_size
    missing = []

    glyph_data = bytearray()
    for start, end in ranges:
        count = end - start + 1
        range_entries.append((start, end, offset, 0))
        for cp in range(start, end + 1):
            g = glyphs.get(cp)
            if g is not None and len(g) == GLYPH_BYTES:
                glyph_data.extend(g)
            else:
                glyph_data.extend(b"\x00" * GLYPH_BYTES)
                missing.append(cp)
        offset += count * GLYPH_BYTES

    with open(output_path, "wb") as f:
        f.write(b"CJKF")
        f.write(struct.pack("<H", len(range_entries)))
        f.write(struct.pack("<I", 0))
        for start, end, goff, _ in range_entries:
            f.write(struct.pack("<IIII", start, end, goff, 0))
        f.write(glyph_data)

    if missing:
        print(f"  WARN: {len(missing)} codepoints have no glyph source:")
        for cp in missing[:WARN_LIST_MAX]:
            ch = chr(cp) if 0x20 <= cp <= 0xFFFF and not (0xD800 <= cp <= 0xDFFF) else ""
            print(f"    U+{cp:04X} {ch}")
        if len(missing) > WARN_LIST_MAX:
            print(f"    ... and {len(missing) - WARN_LIST_MAX} more")

    fsize = Path(output_path).stat().st_size
    total_glyphs = sum(e - s + 1 for s, e, _, _ in range_entries)
    print(f"  Wrote: {output_path} ({len(range_entries)} ranges, "
          f"{total_glyphs} codepoints, {fsize:,} B)")
    return missing


def load_sources(hex_path, atlas_path):
    """Load glyph sources in priority order: hex (P1) then atlas (P2)."""
    sources = []
    if hex_path and Path(hex_path).exists():
        print(f"Loading .hex: {hex_path}")
        glyphs = load_unifont(hex_path)
        print(f"  Loaded {len(glyphs)} glyphs")
        sources.append(glyphs)
    if atlas_path:
        print(f"Loading atlas: {atlas_path}")
        sources.append(subset_from_atlas(atlas_path))
    return sources


def _cps_from_preset(preset):
    """Expand a [(name,start,end),...] preset into a codepoint set."""
    return set().union(*(range(s, e + 1) for _, s, e in preset))


def _validate_collect_lang(lang):
    lang_l = lang.lower()
    if lang_l not in RUNTIME_LANGS:
        raise ValueError(f"unknown runtime language: '{lang}' (use: {', '.join(RUNTIME_LANGS)})")
    return lang_l


def main():
    parser = argparse.ArgumentParser(
        description="Generate CJK.DAT from GNU Unifont .hex / CJKF atlas")
    parser.add_argument("hex_file", nargs="?", default=None,
                        help="GNU Unifont .hex file (P1 glyph source, optional)")
    parser.add_argument("-o", "--output", default="CJK.DAT",
                        help="Output path (default: CJK.DAT)")
    parser.add_argument("--range", action="append", metavar="U+XXXX,U+YYYY",
                        help="Unicode range to include (repeatable)")
    parser.add_argument("--lang", metavar="LANG",
                        help="Language preset (ENG/FRE/GER/ITA/SPA/POR/JPN/CHI/CHT/KOR)")
    parser.add_argument("--all-langs", action="store_true",
                        help="Generate all per-language preset CJK files at once")
    parser.add_argument("--atlas", metavar="PATH",
                        help="CJKF atlas file as P2 glyph source (e.g. tools/naiz_font/CJK.DAT)")
    parser.add_argument("--collect-dir", metavar="PROJ_DIR",
                        help="Project dir for corpus-driven collection (scene/ + i18n/)")
    parser.add_argument("--collect-lang", metavar="LANG",
                        help="Runtime lang code for corpus-driven generation "
                             "(eng/jpn/chi/cht/kor/fre/ger/ita/spa/por)")
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

    sources = load_sources(args.hex_file, args.atlas)
    if not sources:
        parser.error("no glyph source: provide hex_file, --atlas, or both")

    if args.collect_lang:
        if not args.collect_dir:
            parser.error("--collect-lang requires --collect-dir")
        lang_l = _validate_collect_lang(args.collect_lang)
        print(f"Collecting corpus for '{lang_l}' from {args.collect_dir}")
        cps = collect_cps(args.collect_dir, lang_l, with_base=True)
        print(f"  {len(cps)} codepoints (corpus + family base)")
        ranges = merge_ranges(cps)
        glyphs = merge_glyph_sources(sources, cps)
        out = args.output if args.output != "CJK.DAT" \
            else f"CJK_{lang_l.upper()}.DAT"
        generate_cjk_file(glyphs, ranges, out)
        sys.exit(0)

    if args.all_langs:
        if not args.hex_file:
            parser.error("--all-langs requires a hex_file argument")
        out_dir = str(Path(args.output).parent) if args.output != "CJK.DAT" else "."
        for lang in sorted(LANG_RANGES):
            cps = _cps_from_preset(LANG_RANGES[lang])
            glyphs = merge_glyph_sources(sources, cps)
            ranges = merge_ranges(cps)
            out_file = Path(out_dir) / f"CJK_{lang}.DAT"
            generate_cjk_file(glyphs, ranges, str(out_file))
        sys.exit(0)

    if args.lang:
        lang_upper = args.lang.upper()
        if lang_upper not in LANG_RANGES:
            print(f"Error: unknown language '{args.lang}' (use: {', '.join(sorted(LANG_RANGES))})")
            sys.exit(1)
        cps = _cps_from_preset(LANG_RANGES[lang_upper])
        if not args.output or args.output == "CJK.DAT":
            args.output = f"CJK_{lang_upper}.DAT"
    elif args.range:
        cps = set().union(*(set(range(a, b + 1)) for a, b in
                            [parse_range(r) for r in args.range]))
    else:
        cps = _cps_from_preset([(n, s, e) for n, s, e in DEFAULT_RANGES])

    ranges = merge_ranges(cps)
    glyphs = merge_glyph_sources(sources, cps)
    generate_cjk_file(glyphs, ranges, args.output)
    sys.exit(0)


if __name__ == "__main__":
    main()