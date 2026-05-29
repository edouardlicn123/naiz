"""
Search for files in an HDI by name pattern, display FAT chain, search file data.

Usage:
    python -m tools.diag.hdi_find_file disks/demo-A1.hdi "*.LOG"
    python -m tools.diag.hdi_find_file disks/demo-A1.hdi "ENGINE.LOG" --chain
    python -m tools.diag.hdi_find_file disks/demo-A1.hdi --search "Naiz engine"
    python -m tools.diag.hdi_find_file disks/demo-A1.hdi "" --list-all
"""

import argparse
import fnmatch
import os
import re
import struct
import sys

from ..naiz_img.hdi import HDIImage
from ..naiz_img.fat import NAIZFatFS, FAT16_EOC, FAT12_EOC


def _iter_all_entries(fs):
    seen = set()
    def _walk(entry, path):
        key = id(entry)
        if key in seen:
            return
        seen.add(key)
        yield path, entry
        if entry.is_directory:
            for name, child in sorted(entry.children.items()):
                yield from _walk(child, f"{path}/{name}")
    yield from _walk(fs.root, '')


def _format_fat_chain(fs, start_cluster):
    if start_cluster < 2:
        return "(none)"
    chain = fs._get_cluster_chain(start_cluster)
    if not chain:
        return "(empty)"
    return " -> ".join(str(c) for c in chain) + " -> EOC"


def main():
    parser = argparse.ArgumentParser(description="Search files in an HDI by name pattern")
    parser.add_argument('hdi', help='Path to HDI file')
    parser.add_argument('pattern', nargs='?', default='*', help='Filename glob pattern (default: *)')
    parser.add_argument('--chain', action='store_true', help='Show FAT cluster chain')
    parser.add_argument('--hex', action='store_true', help='Show file content as hex dump')
    parser.add_argument('--dump', action='store_true', help='Show file content as text (printable only)')
    parser.add_argument('--search', metavar='TEXT', help='Search for text in file data')
    parser.add_argument('--list-all', action='store_true', help='List all files (ignores pattern)')
    parser.add_argument('--raw-bytes', action='store_true', help='Output raw bytes for first match (for piping)')
    args = parser.parse_args()

    if not os.path.isfile(args.hdi):
        print(f"[hdi_find_file] ERROR: file not found: {args.hdi}")
        sys.exit(1)

    img = HDIImage(args.hdi)
    fs = NAIZFatFS(img)

    if args.list_all:
        pattern = '*'
    else:
        pattern = args.pattern

    matches = []
    for path, entry in _iter_all_entries(fs):
        if entry.is_directory:
            continue
        name = entry.display_name
        if fnmatch.fnmatch(name.upper(), pattern.upper()):
            matches.append((path, entry))

    if not matches:
        print(f"[hdi_find_file] No files matching '{pattern}'")
        sys.exit(0)

    if args.search:
        text = args.search.encode('ascii', errors='replace')
        found = []
        for path, entry in matches:
            data = fs.read_file(entry)
            if text in data:
                pos = data.index(text)
                found.append((path, entry, pos, data))
        if not found:
            print(f"[hdi_find_file] Search string '{args.search}' not found in matching files")
            sys.exit(0)
        print(f"[hdi_find_file] Found '{args.search}' in {len(found)} file(s):")
        for path, entry, pos, data in found:
            context_start = max(0, pos - 16)
            context_end = min(len(data), pos + len(text) + 16)
            context = data[context_start:context_end]
            printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in context)
            print(f"  {path:40s}  offset={pos}  cluster={entry.cluster}")
            print(f"  {'':40s}  context: {printable}")
        sys.exit(0)

    for path, entry in matches:
        chain_info = ""
        if args.chain:
            chain_info = f"  chain=[{_format_fat_chain(fs, entry.cluster)}]"
        print(f"{path:40s}  cluster={entry.cluster:5d}  size={entry.size:8d}{chain_info}")

        if args.hex or args.dump:
            data = fs.read_file(entry)
            if data:
                if len(data) > 512:
                    data = data[:512]
                    print(f"  (showing first 512 of {entry.size} bytes)")
                if args.hex:
                    for i in range(0, len(data), 16):
                        chunk = data[i:i + 16]
                        hex_str = ' '.join(f'{b:02x}' for b in chunk)
                        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
                        print(f"  {i:04x}: {hex_str:48s} {ascii_str}")
                else:
                    printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
                    print(f"  content: {printable}")

    if args.raw_bytes and matches:
        path, entry = matches[0]
        data = fs.read_file(entry)
        sys.stdout.buffer.write(data)


if __name__ == '__main__':
    main()
