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

from .hdi import HDIImage
from .fat import NAIZFatFS
from .inject_common import inject_into_hdi


PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
GAMES_DIR = os.path.join(PROJECT_ROOT, 'games')
DISKS_DIR = os.path.join(PROJECT_ROOT, 'disks')
DEFAULT_BASE = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'base_msdos5_scsi_48m.hdi'))


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

    game_dir = os.path.join(GAMES_DIR, args.game)
    if not os.path.isdir(game_dir):
        print(f"Error: game directory not found: {game_dir}")
        sys.exit(1)

    print(f"Copying base HDI: {args.base}")
    shutil.copy2(args.base, output)
    print(f"Output: {output}")

    inject_into_hdi(output, args.game, game_dir,
                    no_config=args.no_config, no_autoexec=args.no_autoexec)


if __name__ == '__main__':
    main()
