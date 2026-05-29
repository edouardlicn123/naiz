"""
Patch AUTOEXEC.BAT in a compiled HDI directly (without rebuild).

Usage:
    python -m tools.diag.hdi_patch_autoexec disks/demo-A1.hdi "TESTLOG.COM"
    python -m tools.diag.hdi_patch_autoexec disks/demo-A1.hdi --file custom.bat
    python -m tools.diag.hdi_patch_autoexec disks/demo-A1.hdi --list
"""

import argparse
import os
import struct
import sys

from ..naiz_img.hdi import HDIImage
from ..naiz_img.fat import NAIZFatFS


def _read_root_entry(fs, name_8_3):
    root_off = fs.root_offset
    root_len = fs.root_sectors * fs.bytes_per_sector
    raw = fs._read_bytes(root_off, root_len)
    for i in range(fs.root_entries):
        off = i * 32
        entry = raw[off:off + 32]
        if entry[0] == 0:
            break
        if entry[0] == 0xE5:
            continue
        if entry[0:11] == name_8_3:
            return off, entry
    return None, None


def _dos_name(name):
    name = name.upper()
    if '.' in name:
        base, ext = name.rsplit('.', 1)
    else:
        base, ext = name, ''
    base = base[:8].ljust(8, ' ')
    ext = ext[:3].ljust(3, ' ')
    return base.encode('ascii'), ext.encode('ascii')


def patch_autoexec(hdi_path, content, dry_run=False):
    if isinstance(content, str):
        content = content.encode('ascii')

    if not content.endswith(b'\r\n'):
        content = content.rstrip(b'\n\r') + b'\r\n'

    img = HDIImage(hdi_path)
    fs = NAIZFatFS(img)

    name_8_3 = _dos_name('AUTOEXEC.BAT')
    fname = name_8_3[0] + name_8_3[1]

    entry_off, entry = _read_root_entry(fs, fname)
    if entry is None:
        print("[hdi_patch_autoexec] ERROR: AUTOEXEC.BAT not found in root directory")
        sys.exit(1)

    orig_cluster = struct.unpack_from('<H', entry, 26)[0]
    orig_size = struct.unpack_from('<I', entry, 28)[0]
    orig_chain = fs._get_cluster_chain(orig_cluster)

    if len(content) > len(orig_chain) * fs.cluster_size:
        print(f"[hdi_patch_autoexec] ERROR: new content ({len(content)} bytes) exceeds original allocation "
              f"({len(orig_chain)} clusters \u00d7 {fs.cluster_size} = {len(orig_chain) * fs.cluster_size} bytes)")
        print(f"  Use inject.py to rebuild instead.")
        sys.exit(1)

    if dry_run:
        print(f"[hdi_patch_autoexec] Would patch AUTOEXEC.BAT in: {hdi_path}")
        print(f"  Original cluster: {orig_cluster}")
        print(f"  Original size:    {orig_size} bytes")
        print(f"  New size:         {len(content)} bytes")
        print(f"  New content:")
        for line in content.decode('ascii', errors='replace').splitlines():
            print(f"    > {line}")
        return

    cluster_off = fs.data_offset + (orig_chain[0] - 2) * fs.cluster_size
    fs._write_bytes(cluster_off, content)
    if len(content) < fs.cluster_size:
        fs._write_bytes(cluster_off + len(content), b'\x00' * (fs.cluster_size - len(content)))

    root_off = fs.root_offset + entry_off + 28
    fs._write_bytes(root_off, struct.pack('<I', len(content)))

    fs.img.save()

    print(f"[hdi_patch_autoexec] Patched AUTOEXEC.BAT in: {hdi_path}")
    print(f"  Cluster: {orig_chain[0]}")
    print(f"  Size:    {len(content)} bytes")
    for line in content.decode('ascii', errors='replace').splitlines():
        print(f"    > {line}")


def list_root(fs):
    root_off = fs.root_offset
    root_len = fs.root_sectors * fs.bytes_per_sector
    raw = fs._read_bytes(root_off, root_len)
    print(f"{'Name':20s} {'Cluster':>8} {'Size':>8}")
    print("-" * 40)
    for i in range(fs.root_entries):
        off = i * 32
        entry = raw[off:off + 32]
        if entry[0] == 0:
            break
        if entry[0] == 0xE5:
            continue
        name = entry[0:11].decode('ascii', errors='replace')
        attr = entry[11]
        clus = struct.unpack_from('<H', entry, 26)[0]
        size = struct.unpack_from('<I', entry, 28)[0]
        if attr & 0x10:
            name += '/'
        print(f"{name:20s} {clus:8d} {size:8d}")


def main():
    parser = argparse.ArgumentParser(description="Patch AUTOEXEC.BAT in a compiled HDI directly")
    parser.add_argument('hdi', help='Path to HDI file')
    parser.add_argument('command', nargs='?', help='AUTOEXEC.BAT content (command line), mutually exclusive with --file')
    parser.add_argument('-f', '--file', help='Read AUTOEXEC.BAT content from file')
    parser.add_argument('--list', action='store_true', help='List root directory entries')
    parser.add_argument('-n', '--dry-run', action='store_true', help='Preview without writing')
    args = parser.parse_args()

    if not os.path.isfile(args.hdi):
        print(f"[hdi_patch_autoexec] ERROR: file not found: {args.hdi}")
        sys.exit(1)

    if args.list:
        img = HDIImage(args.hdi)
        fs = NAIZFatFS(img)
        list_root(fs)
        sys.exit(0)

    content = None
    if args.file:
        with open(args.file, 'rb') as f:
            content = f.read()
    elif args.command:
        content = args.command
    else:
        parser.print_help()
        sys.exit(1)

    patch_autoexec(args.hdi, content, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
