"""
Incremental file injector for FAT16 HDI images.

Copies a known-bootable base HDI and incrementally adds files
without rebuilding the entire FAT. Preserves the boot chain exactly.

Delegates all FAT operations to inject_common.inject_into_hdi().

Usage:
    python -m tools.naiz_img.inject_file \\
        --base disks/ENGINE_SAMPLE.hdi \\
        --game demo-A1 \\
        --output disks/demo-A1.hdi
"""

import argparse
import os
import shutil
import sys

from .inject_common import inject_into_hdi


PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
GAME_DIR = os.path.join(PROJECT_ROOT, 'games')


def main():
    parser = argparse.ArgumentParser(
        description='Inject game files into a bootable HDI without rebuilding FAT')
    parser.add_argument('--base', required=True,
                        help='Known-bootable base HDI (e.g., disks/ENGINE_SAMPLE.hdi)')
    parser.add_argument('--game', required=True,
                        help='Game name (e.g., demo-A1)')
    parser.add_argument('--game-dir', default=None,
                        help='Game files directory (default: games/<game>)')
    parser.add_argument('--output', required=True,
                        help='Output HDI path')
    parser.add_argument('--no-config', action='store_true',
                        help='Do not overwrite CONFIG.SYS')
    parser.add_argument('--no-autoexec', action='store_true',
                        help='Do not overwrite AUTOEXEC.BAT')
    args = parser.parse_args()

    game_dir = args.game_dir
    if game_dir is None:
        game_dir = os.path.join(GAME_DIR, args.game)
    if not os.path.isdir(game_dir):
        print(f"Error: game directory not found: {game_dir}")
        sys.exit(1)
    if not os.path.isfile(args.base):
        print(f"Error: base HDI not found: {args.base}")
        sys.exit(1)

    print(f"Copying base HDI: {args.base}")
    shutil.copy2(args.base, args.output)
    print(f"Output: {args.output}")

    inject_into_hdi(args.output, args.game, game_dir,
                    no_config=args.no_config, no_autoexec=args.no_autoexec)


if __name__ == '__main__':
    main()
