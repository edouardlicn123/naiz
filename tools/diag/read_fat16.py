#!/usr/bin/env python3
"""Read FAT16 partition from base_msdos5_scsi_48m_clean.hdi and list all files.

Uses NAIZFatFS from naiz_img to avoid duplicating FAT parsing logic.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from naiz_img import NAIZFatFS, open_image
from naiz_lib import COMMERCIAL_BASE_HDI


HDI_PATH = COMMERCIAL_BASE_HDI


def main():
    img = open_image(HDI_PATH)
    fs = NAIZFatFS(img)

    print(f"Partition offset: {fs.part_offset} (0x{fs.part_offset:x})")
    print(f"BytesPerSector   = {fs.bytes_per_sector}")
    print(f"SectorsPerCluster = {fs.sectors_per_cluster}")
    print(f"ReservedSectors  = {fs.reserved_sectors}")
    print(f"NumFATs          = {fs.num_fats}")
    print(f"RootEntries      = {fs.root_entries}")
    print(f"FATsectors       = {fs.fat_sectors}")
    print(f"RootSectors      = {fs.root_sectors}")
    print(f"FAT type         = FAT{fs.fat_type}")
    print(f"Total clusters   = {fs._max_cluster - 2}")
    print()

    # Walk the root directory
    print("=== Root Directory Files ===")
    print(f"{'Name':<12} {'Size':>10} {'Attr':<6} {'Cluster':>7}")
    print('-' * 45)

    for name, entry in sorted(fs.root.children.items()):
        attr_chars = []
        if entry.attr & 0x01: attr_chars.append('R')
        if entry.attr & 0x02: attr_chars.append('H')
        if entry.attr & 0x04: attr_chars.append('S')
        if entry.attr & 0x08: attr_chars.append('V')
        if entry.attr & 0x10: attr_chars.append('D')
        if entry.attr & 0x20: attr_chars.append('A')
        attr_str = ''.join(attr_chars) if attr_chars else '-'
        size_str = '' if entry.is_directory else str(entry.size)
        print(f"{name:<12} {size_str:>10} {attr_str:<6} {entry.cluster:>7}")

    # Print CONFIG.SYS and AUTOEXEC.BAT contents
    for name in ('CONFIG.SYS', 'AUTOEXEC.BAT'):
        entry = fs.resolve_path(name)
        if entry:
            print(f"\n=== {name} ===")
            content = fs.read_file(entry)
            print(content.decode('ascii', errors='replace'))


if __name__ == '__main__':
    main()
