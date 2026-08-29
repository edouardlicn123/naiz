#!/usr/bin/env python3
"""
.NB script syntax validator.

Reads ASSETS.DB (img_map) + characters.json + expressions.json
for reference data, scans all .nb files in scene/, and validates
each line against known commands and their expected argument
signatures.

Usage:
    python nb_validator.py <project_dir>

Exit code = number of errors found (0 = clean).
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from naiz_lib.nb_line import parse_nb_line


# ── Known commands & their signatures ──────────────────────────────────────
# (min_args, max_args_or_None, description)
SIGNATURES = {
    'bg':       (1, 3, 'bg(key[, effect[, transition]])'),
    'char':     (1, 4, 'char(name, pos[, expr[, type]])'),
    'scene':    (1, None, 'scene(name)'),
    'sceneconf': (0, 0, 'sceneconf(){title[,type]}'),
    'mainmenu': (5, None, 'mainmenu(x, y, w, h, opt, ...)'),
    'host':     (0, 0, 'host(){text}'),
    'question': (2, None, 'question(prompt, opt, ...)'),
    'bgm':      (1, 1, 'bgm(key|stop)'),
    'sound':    (1, 1, 'sound(key)'),
    'voice':    (1, 1, 'voice(key)'),
    'loadscene': (0, 0, 'loadscene()'),
    'startsetting': (0, 0, 'startsetting()'),
    'var':      (3, 3, 'var(id, op(=|+| -), value)'),
    'playanima': (0, 2, 'playanima([once|loop[,sec]]){name}'),
    'waitanima': (0, 0, 'waitanima(){}'),
    'stopanima': (0, 0, 'stopanima(){}'),
    'delay':     (1, 1, 'delay(seconds)'),
}

# Stub commands: registered in the engine cmd_table but their handlers only
# log "not implemented yet" (nb_mainmenu.c).  Deliberately kept flagged here
# so a script using one fails validation instead of silently no-op'ing.
STUBS = frozenset({'settingmenu', 'cgvmenu', 'musicmenu'})


def load_reference(project_dir):
    """Read img_map from ASSETS.DB + characters/expressions from JSON.

    Returns (img_keys, anim_keys, char_keys, expr_set, nb_files).
    """
    db_path = Path(project_dir) / 'ASSETS.DB'
    db = sqlite3.connect(str(db_path))
    cur = db.execute("SELECT name FROM img_map WHERE type='IMG'")
    img_keys = {row[0] for row in cur}
    cur = db.execute("SELECT name FROM img_map WHERE type='ANI'")
    anim_keys = {row[0] for row in cur}
    db.close()

    char_keys = {}
    expr_set = set()

    char_path = Path(project_dir) / 'characters.json'
    if char_path.exists():
        with open(char_path, 'r', encoding='utf-8') as f:
            cdata = json.load(f)
        for c in cdata.get('characters', []):
            char_keys[c['key']] = c['id']

    expr_path = Path(project_dir) / 'expressions.json'
    if expr_path.exists():
        with open(expr_path, 'r', encoding='utf-8') as f:
            edata = json.load(f)
        for e in edata.get('expressions', []):
            expr_set.add((e['char_id'], e['expr']))

    # Scene scripts: scan the filesystem instead of a DB table
    scene_dir = Path(project_dir) / 'scene'
    nb_files = set()
    if scene_dir.is_dir():
        for p in scene_dir.glob('*.nb'):
            nb_files.add(p.stem)  # e.g. "nbook001"

    return img_keys, anim_keys, char_keys, expr_set, nb_files


def validate_scene(nb_path, ref):
    """Validate a single .nb file.  Return list of error strings."""
    img_keys, anim_keys, char_keys, expr_set, nb_files = ref
    errors = []
    text_ref = nb_path.read_text(encoding='utf-8', errors='replace')

    for lineno, line in enumerate(text_ref.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        ci = stripped.find('#')
        while ci >= 0:
            depth = 0
            before_hash = stripped[:ci]
            if '{' in before_hash or '}' in before_hash:
                for c in before_hash:
                    if c == '{': depth += 1
                    if c == '}': depth -= 1
            if depth <= 0:
                stripped = before_hash.rstrip()
                if not stripped:
                    break
                ci = -1
            else:
                ci = stripped.find('#', ci + 1)

        if not stripped:
            continue

        cmd = None
        args = []
        text = None
        raw = None

        parsed = parse_nb_line(stripped)
        if parsed is None:
            errors.append(f"  {nb_path.name}:{lineno}: "
                          f"line does not match any known command format: {line!r}")
            continue
        cmd, args, text, raw = parsed

        if raw is not None:
            parts = [p for p in raw.split(',') if p]
            for i, a in enumerate(parts):
                a_stripped = a.strip()
                if a != a_stripped:
                    errors.append(
                        f"  {nb_path.name}:{lineno}: arg[{i}] has "
                        f"leading/trailing whitespace: {a!r}")
                if not a_stripped:
                    errors.append(
                        f"  {nb_path.name}:{lineno}: arg[{i}] is empty")

        if cmd in STUBS:
            errors.append(f"  {nb_path.name}:{lineno}: "
                          f"stub command '{cmd}' — not implemented")
            continue

        if cmd in SIGNATURES:
            min_a, max_a, desc = SIGNATURES[cmd]
            if len(args) < min_a:
                errors.append(
                    f"  {nb_path.name}:{lineno}: '{cmd}' needs ≥{min_a} "
                    f"args, got {len(args)}  ({desc})")
            elif max_a is not None and len(args) > max_a:
                errors.append(
                    f"  {nb_path.name}:{lineno}: '{cmd}' needs ≤{max_a} "
                    f"args, got {len(args)}  ({desc})")

            if cmd == 'bg' and len(args) >= 1 and args[0] == 'hidedialog':
                pass
            elif cmd == 'bg' and len(args) >= 1:
                if args[0] not in img_keys:
                    errors.append(
                        f"  {nb_path.name}:{lineno}: bg key {args[0]!r} "
                        "not in img_map (type=IMG)")

            elif cmd == 'char':
                if len(args) >= 1 and args[0] == 'hideall':
                    pass
                elif len(args) >= 1 and args[0] not in char_keys:
                    errors.append(
                        f"  {nb_path.name}:{lineno}: char name "
                        f"{args[0]!r} not in characters.json")
                if len(args) >= 3 and args[0] in char_keys:
                    cid = char_keys[args[0]]
                    if (cid, args[2]) not in expr_set:
                        errors.append(
                            f"  {nb_path.name}:{lineno}: expression "
                            f"{args[2]!r} not defined for {args[0]} "
                            f"(char_id={cid})")

            elif cmd == 'playanima':
                if text is None or not text.strip():
                    errors.append(
                        f"  {nb_path.name}:{lineno}: playanima needs "
                        "animation name in {}")
                elif text.strip() not in anim_keys:
                    errors.append(
                        f"  {nb_path.name}:{lineno}: playanima name "
                        f"{text.strip()!r} not in img_map (type=ANI)")
                if len(args) >= 1 and args[0] not in ('once', 'loop'):
                    errors.append(
                        f"  {nb_path.name}:{lineno}: playanima mode "
                        f"{args[0]!r} must be 'once' or 'loop'")
                if len(args) >= 2:
                    try:
                        if not float(args[1]) > 0:
                            raise ValueError
                    except ValueError:
                        errors.append(
                            f"  {nb_path.name}:{lineno}: playanima seconds "
                            f"{args[1]!r} must be a positive number")

            elif cmd == 'scene' and len(args) >= 1:
                if raw and ';' in raw:
                    segments = [seg.strip() for seg in raw.split(';') if seg.strip()]
                    for seg in segments:
                        seg_target = seg.split(',')[-1].strip() if ',' in seg else seg.strip()
                        if seg_target in ('end', 'logo', 'op', 'mainmenu'):
                            continue
                        found = False
                        for stem in nb_files:
                            if stem == seg_target or stem == f'nbook{seg_target}':
                                found = True
                                break
                        if not found:
                            errors.append(
                                f"  {nb_path.name}:{lineno}: scene target "
                                f"{seg_target!r} no matching .nb file found")
                else:
                    sid = args[0]
                    if sid not in ('end', 'logo', 'op', 'mainmenu'):
                        found = False
                        for stem in nb_files:
                            if stem == sid or stem == f'nbook{sid}':
                                found = True
                                break
                        if not found:
                            errors.append(
                                f"  {nb_path.name}:{lineno}: scene id {sid!r} "
                                "no matching .nb file found")

        elif cmd in char_keys:
            if text is None or not text.strip():
                errors.append(
                    f"  {nb_path.name}:{lineno}: dialogue command "
                    f"'{cmd}' needs text in {{}}")

        else:
            errors.append(f"  {nb_path.name}:{lineno}: "
                          f"unknown command '{cmd}'")

    return errors


def validate_project(project_dir):
    """Validate all .nb files under project_dir/scene/."""
    proj = Path(project_dir)
    db_path = proj / 'ASSETS.DB'
    if not db_path.exists():
        print(f"ERROR: {db_path} not found")
        return 1

    ref = load_reference(project_dir)
    scene_dir = proj / 'scene'
    if not scene_dir.is_dir():
        print("OK: no scene/ directory — nothing to validate")
        return 0

    nb_files = sorted(scene_dir.glob('*.nb'))
    if not nb_files:
        print(f"OK: no .nb files in {scene_dir}")
        return 0

    total_errors = 0
    for nb in nb_files:
        errs = validate_scene(nb, ref)
        if errs:
            print(f"{nb.name}:")
            for e in errs:
                print(e)
            total_errors += len(errs)

    return total_errors


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <project_dir>")
        sys.exit(1)

    n_err = validate_project(sys.argv[1])
    if n_err == 0:
        print("NB validator: OK — 0 errors")
    else:
        print(f"NB validator: {n_err} error(s)")

    sys.exit(min(n_err, 255) if n_err else 0)


if __name__ == '__main__':
    main()
