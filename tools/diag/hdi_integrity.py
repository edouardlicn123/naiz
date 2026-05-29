"""
HDI integrity check: save/verify SHA256 checkpoints of the data area.

Purpose: detect whether NP2kai actually writes disk changes back to the .hdi file.
Usage:
    python -m tools.diag.hdi_integrity save disks/demo-A1.hdi --label before_test
    python -m tools.diag.hdi_integrity verify disks/demo-A1.hdi
    python -m tools.diag.hdi_integrity check disks/demo-A1.hdi
    python -m tools.diag.hdi_integrity list
    python -m tools.diag.hdi_integrity clean
"""

import argparse
import hashlib
import json
import os
import sys

from ..naiz_img.hdi import HDIImage
from ..naiz_img.fat import NAIZFatFS

CHECKPOINT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', '.hdi_checkpoints'))


def _ensure_dir():
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)


def _checkpoint_path(hdi_path):
    name = os.path.basename(hdi_path)
    return os.path.join(CHECKPOINT_DIR, f"{name}.json")


def _hash_data_area(fs):
    data_len = (fs.total_sectors - fs.reserved_sectors - fs.num_fats * fs.fat_sectors - fs.root_sectors) * fs.bytes_per_sector
    h = hashlib.sha256()
    offset = fs.data_offset
    chunk = 65536
    while data_len > 0:
        n = min(chunk, data_len)
        h.update(fs._read_bytes(offset, n))
        offset += n
        data_len -= n
    return h.hexdigest()


def _hash_full_file(hdi_path):
    h = hashlib.sha256()
    with open(hdi_path, 'rb') as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _collect_metadata(fs):
    return {
        'total_sectors': fs.total_sectors,
        'reserved_sectors': fs.reserved_sectors,
        'num_fats': fs.num_fats,
        'fat_sectors': fs.fat_sectors,
        'root_sectors': fs.root_sectors,
        'bytes_per_sector': fs.bytes_per_sector,
        'sectors_per_cluster': fs.sectors_per_cluster,
        'data_offset': fs.data_offset,
        'part_offset': fs.part_offset,
    }


def cmd_check(hdi_path):
    if not os.path.isfile(hdi_path):
        print(f"[hdi_integrity] ERROR: file not found: {hdi_path}")
        sys.exit(1)

    img = HDIImage(hdi_path)
    fs = NAIZFatFS(img)
    data_hash = _hash_data_area(fs)

    print(f"[hdi_integrity] HDI:  {hdi_path}")
    print(f"[hdi_integrity] Size: {os.path.getsize(hdi_path)} bytes")
    print(f"[hdi_integrity] Data area SHA256: {data_hash}")


def cmd_save(hdi_path, label=None):
    if not os.path.isfile(hdi_path):
        print(f"[hdi_integrity] ERROR: file not found: {hdi_path}")
        sys.exit(1)

    _ensure_dir()
    img = HDIImage(hdi_path)
    fs = NAIZFatFS(img)
    data_hash = _hash_data_area(fs)
    full_hash = _hash_full_file(hdi_path)
    meta = _collect_metadata(fs)

    cp = {
        'label': label or 'unnamed',
        'hdi': os.path.basename(hdi_path),
        'data_sha256': data_hash,
        'full_sha256': full_hash,
        'metadata': meta,
    }

    cp_path = _checkpoint_path(hdi_path)
    with open(cp_path, 'w') as f:
        json.dump(cp, f, indent=2)

    print(f"[hdi_integrity] Checkpoint saved: {cp_path}")
    print(f"[hdi_integrity] Label: {cp['label']}")
    print(f"[hdi_integrity] Data area SHA256: {data_hash}")
    print(f"[hdi_integrity] Full file SHA256:  {full_hash}")


def cmd_verify(hdi_path):
    if not os.path.isfile(hdi_path):
        print(f"[hdi_integrity] ERROR: file not found: {hdi_path}")
        sys.exit(1)

    cp_path = _checkpoint_path(hdi_path)
    if not os.path.isfile(cp_path):
        print(f"[hdi_integrity] No checkpoint found for {hdi_path}")
        print(f"  Expected: {cp_path}")
        print(f"  Run 'save' first.")
        sys.exit(1)

    with open(cp_path) as f:
        cp = json.load(f)

    img = HDIImage(hdi_path)
    fs = NAIZFatFS(img)
    current_data_hash = _hash_data_area(fs)
    current_full_hash = _hash_full_file(hdi_path)

    print(f"[hdi_integrity] Verifying: {hdi_path}")
    print(f"[hdi_integrity] Checkpoint label: {cp.get('label', '?')}")
    print(f"")
    print(f"  Data area:")
    print(f"    Saved:    {cp['data_sha256']}")
    print(f"    Current:  {current_data_hash}")
    if current_data_hash == cp['data_sha256']:
        print(f"    Result:   MATCH \u2713  (no disk writes detected)")
    else:
        print(f"    Result:   DIFFERENT \u2717  (disk was modified!)")

    print(f"")
    print(f"  Full file:")
    print(f"    Saved:    {cp['full_sha256']}")
    print(f"    Current:  {current_full_hash}")
    if current_full_hash == cp['full_sha256']:
        print(f"    Result:   MATCH \u2713")
    else:
        print(f"    Result:   DIFFERENT \u2717")

    return current_data_hash != cp['data_sha256']


def cmd_list():
    _ensure_dir()
    files = sorted(os.listdir(CHECKPOINT_DIR))
    if not files:
        print("[hdi_integrity] No checkpoints found")
        return
    print(f"[hdi_integrity] Checkpoints ({CHECKPOINT_DIR}):")
    for fname in files:
        with open(os.path.join(CHECKPOINT_DIR, fname)) as f:
            cp = json.load(f)
        hdi_name = cp.get('hdi', '?')
        label = cp.get('label', '?')
        data_hash = cp.get('data_sha256', '?')[:16]
        print(f"  {fname:40s}  hdi={hdi_name:20s}  label={label:15s}  sha256={data_hash}...")


def cmd_clean():
    _ensure_dir()
    files = os.listdir(CHECKPOINT_DIR)
    if not files:
        print("[hdi_integrity] No checkpoints to clean")
        return
    for fname in files:
        os.remove(os.path.join(CHECKPOINT_DIR, fname))
    print(f"[hdi_integrity] Removed {len(files)} checkpoint(s)")


def main():
    parser = argparse.ArgumentParser(description="HDI integrity checker: save/verify SHA256 checkpoints")
    sub = parser.add_subparsers(dest='command', required=True)

    p_save = sub.add_parser('save', help='Save SHA256 checkpoint')
    p_save.add_argument('hdi', help='Path to HDI file')
    p_save.add_argument('-l', '--label', default=None, help='Optional label for checkpoint')

    p_verify = sub.add_parser('verify', help='Verify HDI against saved checkpoint')
    p_verify.add_argument('hdi', help='Path to HDI file')

    p_check = sub.add_parser('check', help='Quick check: compute and display SHA256')
    p_check.add_argument('hdi', help='Path to HDI file')

    p_list = sub.add_parser('list', help='List saved checkpoints')

    p_clean = sub.add_parser('clean', help='Remove all saved checkpoints')

    args = parser.parse_args()

    if args.command == 'check':
        cmd_check(args.hdi)
    elif args.command == 'save':
        cmd_save(args.hdi, args.label)
    elif args.command == 'verify':
        cmd_verify(args.hdi)
    elif args.command == 'list':
        cmd_list()
    elif args.command == 'clean':
        cmd_clean()


if __name__ == '__main__':
    main()
