"""
build_docs.py — 生成 naiz-guildbook 辅助资源

保留功能：
  - 复制 logo-mini.png → naiz-guildbook/
  - 生成 canvas 示意图（C03 HTML 引用）

用法：
  python3 -m tools.naiz_docs.build_docs
"""

import os
import shutil
from .gen_canvas_image import generate_canvas_diagram, generate_region_diagram, generate_screen_panorama

ASSETS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'assets')
OUT_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'naiz-guildbook')

LOGO_SRC = os.path.join(ASSETS_DIR, 'logomini.png')
LOGO_DST = os.path.join(OUT_DIR, 'logo-mini.png')


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    if os.path.exists(LOGO_SRC):
        shutil.copy2(LOGO_SRC, LOGO_DST)
        print(f'  logo-mini.png ({os.path.getsize(LOGO_DST)} bytes)')
    else:
        print('  WARNING: logomini.png not found')

    generate_canvas_diagram()
    generate_region_diagram()
    generate_screen_panorama()

    print(f'\nDone → {OUT_DIR}/')


if __name__ == '__main__':
    main()
