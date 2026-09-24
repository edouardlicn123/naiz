"""
Patch AUTOEXEC.BAT in a compiled HDI directly (without rebuild).

Usage:
    python -m tools.diag.hdi_patch_autoexec disks/demo-A1.hdi "TESTLOG.COM"
    python -m tools.diag.hdi_patch_autoexec disks/demo-A1.hdi --file custom.bat
    python -m tools.diag.hdi_patch_autoexec disks/demo-A1.hdi --list
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from naiz_lib import to_dos_name
from naiz_img.hdi import HDIImage
from naiz_img.fat import NAIZFatFS, get_entry_cluster, get_entry_size, set_entry_size


def patch_autoexec(hdi_path, content, dry_run=False):
    if isinstance(content, str):
        content = content.encode('ascii')

    if not content.endswith(b'\r\n'):
        content = content.rstrip(b'\n\r') + b'\r\n'

    img = HDIImage(hdi_path)
    fs = NAIZFatFS(img)

    name_8_3 = to_dos_name('AUTOEXEC.BAT')
    root_data = fs.read_root()
    entry_off = NAIZFatFS.find_entry_offset(root_data, name_8_3[0], name_8_3[1])
    if entry_off is None:
        print("[hdi_patch_autoexec] ERROR: AUTOEXEC.BAT not found in root directory")
        sys.exit(1)
    entry = root_data[entry_off:entry_off + 32]
    if len(entry) < 32:
        print("[hdi_patch_autoexec] ERROR: AUTOEXEC.BAT entry truncated in root directory")
        sys.exit(1)

    orig_cluster = get_entry_cluster(root_data, entry_off)
    orig_size = get_entry_size(root_data, entry_off)
    orig_chain = fs._get_cluster_chain(orig_cluster)

    if len(content) > len(orig_chain) * fs.cluster_size:
        print(f"[hdi_patch_autoexec] ERROR: new content ({len(content)} bytes) exceeds original allocation "
              f"({len(orig_chain)} clusters \u00d7 {fs.cluster_size} = {len(orig_chain) * fs.cluster_size} bytes)")
        print("  Use inject.py to rebuild instead.")
        sys.exit(1)

    if dry_run:
        print(f"[hdi_patch_autoexec] Would patch AUTOEXEC.BAT in: {hdi_path}")
        print(f"  Original cluster: {orig_cluster}")
        print(f"  Original size:    {orig_size} bytes")
        print(f"  New size:         {len(content)} bytes")
        print("  New content:")
        for line in content.decode('ascii', errors='replace').splitlines():
            print(f"    > {line}")
        return

    for i, c in enumerate(orig_chain):
        off = fs.data_offset + (c - 2) * fs.cluster_size
        chunk = content[i * fs.cluster_size:(i + 1) * fs.cluster_size]
        fs._write_bytes(off, chunk.ljust(fs.cluster_size, b'\x00'))

    set_entry_size(root_data, entry_off, len(content))
    fs.write_root(root_data)

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
    for off, key, attr in NAIZFatFS.iter_dir_entries(raw):
        entry = raw[off:off + 32]
        name = entry[0:11].decode('ascii', errors='replace')
        clus = get_entry_cluster(raw, off)
        size = get_entry_size(raw, off)
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
