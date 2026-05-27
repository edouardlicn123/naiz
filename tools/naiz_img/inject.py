"""
参考 98Bridge (MIT) 的设计思路独立实现。
来源: https://github.com/NullMagic2/98Bridge

CLI entry point: inject game files into a base MS-DOS HDI image.

Usage:
    python -m tools.naiz_img.inject --game demo-A1
    python -m tools.naiz_img.inject --game mygame --output disks/mygame.hdi
"""

import argparse
import datetime
import os
import shutil
import sys
import tempfile

from .hdi import HDIImage
from .fat import NAIZFatFS


PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
REF_DISK = os.path.join(PROJECT_ROOT, 'tools', 'ref_disk')
REF_CONFIG = os.path.join(PROJECT_ROOT, 'tools', 'ref_config')
GAMES_DIR = os.path.join(PROJECT_ROOT, 'games')
DISKS_DIR = os.path.join(PROJECT_ROOT, 'disks')
DEFAULT_BASE = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'msdos5.hdi'))


def build_temp_dir(game, no_dos=False, no_config=False, no_autoexec=False):
    tmp = tempfile.mkdtemp(prefix='naiz_')
    if no_dos:
        if not os.path.isdir(os.path.join(tmp, 'DOS')):
            os.makedirs(os.path.join(tmp, 'DOS'), exist_ok=True)
    else:
        for root, dirs, files in os.walk(REF_DISK):
            for f in files:
                src = os.path.join(root, f)
                rel = os.path.relpath(src, REF_DISK)
                dst = os.path.join(tmp, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
    dst_config = os.path.join(tmp, 'CONFIG.SYS')
    dst_autoexec = os.path.join(tmp, 'AUTOEXEC.BAT')
    if not no_config:
        shutil.copy2(os.path.join(REF_CONFIG, 'CONFIG.SYS'), dst_config)
    if not no_autoexec:
        game_upper = game.upper()
        autoexec_content = (
            b'@ECHO OFF\r\n'
            b'PATH C:\\DOS;C:\\' + game_upper.encode() + b'\r\n'
            b'SET TEMP=C:\\DOS\r\n'
            b'SET DOSDIR=C:\\DOS\r\n'
            b'ECHO BOOT_OK > C:\\BOOTMARK.TXT\r\n'
            b'CD C:\\' + game_upper.encode() + b'\r\n'
            b'ENGINE.EXE\r\n'
        )
        with open(dst_autoexec, 'wb') as f:
            f.write(autoexec_content)
    game_dir = os.path.join(GAMES_DIR, game)
    if not os.path.isdir(game_dir):
        raise ValueError(f"Game directory not found: {game_dir}")
    for root, dirs, files in os.walk(game_dir):
        for f in files:
            src = os.path.join(root, f)
            rel = os.path.relpath(src, GAMES_DIR)
            dst = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    # Patch ROOTINFO.DAT font_path field (offset 0x16, 12 bytes) to a placeholder
    rootinfo_path = os.path.join(tmp, game, 'ROOTINFO.DAT')
    if os.path.isfile(rootinfo_path):
        with open(rootinfo_path, 'r+b') as f:
            f.seek(0x16)
            f.write(b'FONT.DAT\x00\x00\x00\x00')

    return tmp


def list_game_file_tree(game):
    game_dir = os.path.join(GAMES_DIR, game)
    if not os.path.isdir(game_dir):
        print(f"Game directory not found: {game_dir}")
        return
    for root, dirs, files in os.walk(game_dir):
        rel = os.path.relpath(root, game_dir)
        prefix = '' if rel == '.' else f"{rel}/"
        for f in files:
            print(f"  {prefix}{f}")
        for d in sorted(dirs):
            print(f"  {prefix}{d}/")


def main():
    parser = argparse.ArgumentParser(description='Inject game files into MS-DOS HDI')
    parser.add_argument('-g', '--game', required=True, help='Game name (directory under games/)')
    parser.add_argument('-b', '--base', default=DEFAULT_BASE, help=f'Base HDI image (default: {DEFAULT_BASE})')
    parser.add_argument('-o', '--output', default=None, help='Output HDI path (default: disks/<game>.hdi)')
    parser.add_argument('--preview', action='store_true', help='Preview file list without injecting')
    parser.add_argument('--list-files', action='store_true', help='List files in base HDI and exit')
    parser.add_argument('--no-dos', action='store_true', help='Skip DOS tools')
    parser.add_argument('--no-config', action='store_true', help='Do not overwrite CONFIG.SYS')
    parser.add_argument('--no-autoexec', action='store_true', help='Do not overwrite AUTOEXEC.BAT')
    parser.add_argument('-y', '--yes', action='store_true', help='Non-interactive mode')
    parser.add_argument('--extract', metavar='PATH', default=None,
                        help='Extract a file from the game HDI to logs/ (e.g. DEMO-A1/ENGINE.LOG)')
    args = parser.parse_args()

    if not os.path.isfile(args.base):
        print(f"Error: base HDI not found: {args.base}")
        sys.exit(1)

    output = args.output
    if output is None:
        os.makedirs(DISKS_DIR, exist_ok=True)
        output = os.path.join(DISKS_DIR, f"{args.game}.hdi")

    if args.list_files:
        print(f"Opening: {args.base}")
        img = HDIImage(args.base)
        fs = NAIZFatFS(img)
        print("\nFiles on base image:")
        for path, entry in fs.walk():
            if entry.is_directory:
                print(f"  {path}/")
            else:
                print(f"  {path}  ({entry.size} bytes)")
        sys.exit(0)

    if args.preview:
        print(f"Game: {args.game}")
        print("Files to inject:")
        list_game_file_tree(args.game)
        sys.exit(0)

    if args.extract:
        img = HDIImage(output)
        fs = NAIZFatFS(img)
        entry = fs.resolve_path(args.extract.replace('\\', '/'))
        if entry is None:
            print(f"Error: file not found in HDI: {args.extract}")
            sys.exit(1)
        if entry.is_directory:
            print(f"Error: path is a directory: {args.extract}")
            sys.exit(1)
        data = fs.read_file(entry)
        logs_dir = os.path.join(PROJECT_ROOT, 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime('%Y%m%d.%H%M%S')
        outname = f"ENGINE.RUN.{ts}.log"
        outpath = os.path.join(logs_dir, outname)
        with open(outpath, 'wb') as f:
            f.write(data)
        print(f"Extracted {len(data)} bytes to: {outpath}")
        sys.exit(0)

    if not args.yes:
        print(f"About to inject '{args.game}' into: {output}")
        print("Source files:")
        list_game_file_tree(args.game)
        resp = input("Proceed? [y/N] ").strip().lower()
        if resp != 'y':
            print("Aborted.")
            sys.exit(1)

    tmp = None
    try:
        tmp = build_temp_dir(args.game, no_dos=args.no_dos, no_config=args.no_config, no_autoexec=args.no_autoexec)
        print(f"Temp dir: {tmp}")
        print(f"Opening base: {args.base}")
        img = HDIImage(args.base)
        print(f"  sectors: {img.total_sectors}, sector size: {img.sector_size}")
        print(f"  geometry: {img.cylinders} cyls, {img.heads} heads, {img.spt} spt")
        fs = NAIZFatFS(img)
        print(f"  FAT type: FAT{fs.fat_type}")
        print(f"  cluster size: {fs.cluster_size}")
        print(f"Writing back from directory: {tmp}")
        files, dirs = fs.write_back_from_directory(tmp, save_path=output)
        print(f"Done: {files} files, {dirs} directories written")
        print(f"Output: {output}")
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
