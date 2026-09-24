#!/usr/bin/env python3
"""render_title.py — Render LOAD/SAVE blackletter titles to MAG sprites.

Uses UnifrakturMaguntia (SIL OFL 1.1) to render white "LOAD"/"SAVE" text on
a transparent background (~40px tall), then encodes each as a sprite-class
MAG via naiz_conv.mag_convert (alpha<128 -> transparent index 15).

Outputs (project_dir/images/):
    loadtitle.MAG, savetitle.MAG   sprite MAGs referenced by the engine
Also writes RGBA source PNGs + gray preview PNGs into assets/images/ for
sanity checking.

Usage:
    python3 tools/naiz_conv/render_title.py \
        tools/naiz_font/UnifrakturMaguntia.ttf projects/demo-a2
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from naiz_conv.mag_convert import convert_image

from PIL import Image, ImageDraw, ImageFont

TARGET_H = 40  # target ink height (px)
PREVIEW_BG = (32, 32, 32)


def render_text_rgba(font_path, text, target_h=TARGET_H):
    """Render white text on transparent RGBA at roughly target_h tall."""
    font = ImageFont.truetype(font_path, 96)
    canvas = Image.new('RGBA', (1600, 400), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text((0, 0), text, font=font, fill=(255, 255, 255, 255))

    bbox = canvas.getbbox()
    if not bbox:
        return None, (0, 0)
    x0, y0, x1, y1 = bbox
    ink = canvas.crop(bbox)

    scale = target_h / (y1 - y0)
    w = max(1, int((x1 - x0) * scale))
    h = max(1, int((y1 - y0) * scale))
    return ink.resize((w, h), Image.LANCZOS), (w, h)


def make_preview(rgba, bg=PREVIEW_BG):
    """Composite RGBA onto a solid background for visual inspection."""
    bg_img = Image.new('RGBA', rgba.size, bg + (255,))
    bg_img.alpha_composite(rgba)
    return bg_img.convert('RGB')


def main():
    parser = argparse.ArgumentParser(description='Render LOAD/SAVE blackletter MAGs')
    parser.add_argument('ttf', help='Path to UnifrakturMaguntia.ttf')
    parser.add_argument('project_dir', help='Path to project (demo-a2)')
    args = parser.parse_args()

    ttf = Path(args.ttf)
    if not ttf.exists():
        print(f"ERROR: ttf not found: {ttf}", file=sys.stderr)
        sys.exit(1)

    proj = Path(args.project_dir)
    mag_dir = proj / 'images'
    png_dir = proj / 'assets' / 'images'
    mag_dir.mkdir(parents=True, exist_ok=True)
    png_dir.mkdir(parents=True, exist_ok=True)

    for name, text in (('loadtitle', 'LOAD'), ('savetitle', 'SAVE')):
        rgba, size = render_text_rgba(str(ttf), text)
        if rgba is None:
            print(f"ERROR: no ink for '{text}'", file=sys.stderr)
            sys.exit(1)
        w, h = size

        mag_path = mag_dir / f'{name}.MAG'
        mag_data = convert_image(rgba, sprite=True)
        mag_path.write_bytes(mag_data)
        print(f"  MAG {mag_path} ({w}x{h}, {len(mag_data)} bytes)")

        rgba.save(png_dir / f'{name}.png')
        make_preview(rgba).save(png_dir / f'{name}_preview.png')
        print(f"  PNG {png_dir / (name + '.png')} + preview")


if __name__ == '__main__':
    main()
