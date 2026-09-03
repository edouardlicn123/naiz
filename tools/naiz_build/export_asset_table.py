#!/usr/bin/env python3
"""Export image DB + character JSON to C header for engine compilation.

Reads ASSETS.DB (img_map) + characters.json + expressions.json
and generates nb_asset_table.h:
  - asset_map[] — image key->id lookup (for cmd_bg, type='IMG')
  - char_map[] — character key->id lookup
  - expr_map[] — (char_id, expr)->asset_id lookup

Usage:
    python export_asset_table.py <project_dir> <output_path>
"""

import json
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from naiz_build.c_header import escape, header_preamble, header_footer


def load_json(project_dir, name):
    path = os.path.join(project_dir, name)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{name} not found: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate(project_dir, output_path):
    db_path = os.path.join(project_dir, 'ASSETS.DB')
    if not os.path.isfile(db_path):
        print(f"ERROR: ASSETS.DB not found: {db_path}")
        print("  Run pack_images first to generate ASSETS.DB")
        sys.exit(1)

    try:
        char_data = load_json(project_dir, 'characters.json')
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print("  Create a characters.json file in the project directory")
        sys.exit(1)

    try:
        expr_data = load_json(project_dir, 'expressions.json')
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print("  Create an expressions.json file in the project directory")
        sys.exit(1)

    db = None
    try:
        db = sqlite3.connect(db_path)
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to open ASSETS.DB: {e}")

    try:
        lines = header_preamble('export_asset_table.py', db_path, output_path, 'NB_ASSET_TABLE_H')

        # -- asset_map: image assets (type='IMG') --
        lines.append('/* Image asset key->ID lookup (for cmd_bg) */')
        lines.append('static const struct { const char *key; int id; } asset_map[] = {')
        img_rows = list(db.execute(
            "SELECT id, name FROM img_map WHERE type='IMG' ORDER BY id"
        ))
        if not img_rows:
            lines.append('    {"__dummy__", 0},')
        for row in img_rows:
            lines.append('    {"%s", %d},' % (escape(row[1]), row[0]))
        lines.append('    {NULL, 0}')
        lines.append('};')
        lines.append('')

        # -- spr_asset_map: sprite assets (type='SPR') --
        lines.append('/* Sprite asset key->ID lookup (for cmd_char) */')
        lines.append('static const struct { const char *key; int id; } spr_asset_map[] = {')
        spr_rows = list(db.execute(
            "SELECT id, name FROM img_map WHERE type='SPR' ORDER BY id"
        ))
        if not spr_rows:
            lines.append('    {"__dummy__", 0},')
        for row in spr_rows:
            lines.append('    {"%s", %d},' % (escape(row[1]), row[0]))
        lines.append('    {NULL, 0}')
        lines.append('};')
        lines.append('')

        # -- char_map: from characters.json --
        lines.append('/* Character key->ID mapping */')
        lines.append(
            'static const struct { const char *key; int id; const char *name; } char_map[] = {')
        chars = char_data.get('characters', [])
        for c in chars:
            lines.append('    {"%s", %d, "%s"},' % (
                escape(c['key']), c['id'], escape(c['name'])))
        lines.append('    {NULL, 0, NULL}')
        lines.append('};')
        lines.append('')

        # -- expr_map: from expressions.json --
        lines.append(
            '/* Expression lookup: (char_id, expr_name) -> asset_id */')
        lines.append(
            'static const struct { int char_id; const char *expr; int asset_id; } expr_map[] = {')
        exprs = expr_data.get('expressions', [])
        for e in exprs:
            lines.append('    {%d, "%s", %d},' % (e['char_id'], escape(e['expr']), e['asset_id']))
        lines.append('    {-1, NULL, 0}')
        lines.append('};')
        lines.append('')

        # -- anim_map: ANI assets (type='ANI') --
        lines.append('/* ANI asset key->ID lookup (for playanima) */')
        lines.append('static const struct { const char *name; int id; } anim_map[] = {')
        ani_rows = list(db.execute(
            "SELECT id, name FROM img_map WHERE type='ANI' ORDER BY id"
        ))
        if not ani_rows:
            lines.append('    {"__dummy__", 0},')
        for row in ani_rows:
            lines.append('    {"%s", %d},' % (escape(row[1]), row[0]))
        lines.append('    {NULL, 0}')
        lines.append('};')
        lines.append('')

        # -- cg_map: CG assets (type='CG') --
        lines.append('/* CG asset key->ID lookup (for cg command) */')
        lines.append('static const struct { const char *key; int id; } cg_map[] = {')
        cg_rows = list(db.execute(
            "SELECT id, name FROM img_map WHERE type='CG' ORDER BY id"
        ))
        if not cg_rows:
            lines.append('    {"__dummy__", 0},')
        for row in cg_rows:
            lines.append('    {"%s", %d},' % (escape(row[1]), row[0]))
        lines.append('    {NULL, 0}')
        lines.append('};')
        lines.append('')

        # -- CG_COUNT constant --
        lines.append('/* Number of registered CG assets */')
        lines.append('#define CG_COUNT %d' % len(cg_rows))
        lines.append('')

        lines.extend(header_footer('NB_ASSET_TABLE_H'))

        try:
            with open(output_path, 'w') as f:
                f.write('\n'.join(lines))
        except OSError as e:
            raise RuntimeError(f"Failed to write {output_path}: {e}")
    finally:
        if db:
            db.close()
    return len(img_rows), len(chars), len(exprs), len(spr_rows), len(cg_rows)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: export_asset_table.py <project_dir> <output_path>")
        sys.exit(1)

    n_img, n_char, n_expr, n_spr, n_cg = generate(sys.argv[1], sys.argv[2])
    print("export_asset_table: %d img, %d spr, %d cg, %d chars, %d expressions -> %s" % (
        n_img, n_spr, n_cg, n_char, n_expr, sys.argv[2]))
