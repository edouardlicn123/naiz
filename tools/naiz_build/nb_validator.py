#!/usr/bin/env python3
"""
.NB script syntax validator.

Reads ASSETS.DB (img_map) + characters.json + expressions.json
+ variables.json
for reference data, scans all .nb files in scene/, and validates
each line against known commands and their expected argument
signatures.

Extended checks (devdoc 104): var bounds vs variables.json, question
segment structure (aligned to the engine ';'-split tokenizer), delay
must be positive, and a per-project accepted-list (nb_lint_accepted.txt)
that still prints matched findings without counting them.

Usage:
    python nb_validator.py <project_dir>

Exit code = number of errors found (0 = clean).
"""

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from naiz_lib.nb_line import parse_nb_line, split_semi


# ── Known commands & their signatures ──────────────────────────────────────
# (min_args, max_args_or_None, description)
SIGNATURES = {
    'bg':       (0, 2, 'bg(effect[,transition]){key} | bg(hidedialog)'),
    'cg':       (0, 1, 'cg(){key} | cg(hidedialog)'),
    'char':     (1, 3, 'char(pos[,expr[,type]]){name} | char(hideall)'),
    'scene':    (1, None, 'scene(name)'),
    'sceneconf': (0, 0, 'sceneconf(){title[,type]}'),
    'mainmenu': (5, None, 'mainmenu(x, y, w, h, opt, ...)'),
    'host':     (0, 0, 'host(){text}'),
    'bgm':      (0, 1, 'bgm(){key} | bgm(stop)'),
    'sound':    (0, 0, 'sound(){key}'),
    'voice':    (0, 0, 'voice(){key}'),
    'loadscene': (0, 0, 'loadscene()'),
    'cgvmenu':  (0, 0, 'cgvmenu()'),
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
STUBS = frozenset({'settingmenu', 'musicmenu'})

# Numeric literal accepted for var values / question deltas (engine atoi
# would silently coerce junk to 0 — a script typo we want red instead).
_NUM_LITERAL = re.compile(r'^[-+]?\d+$')


def load_reference(project_dir):
    """Read img_map from ASSETS.DB + characters/expressions/variables from JSON.

    Returns (img_keys, anim_keys, cg_keys, char_keys, expr_set, nb_files,
             var_tbl).
    var_tbl maps variable id to (min, max, initial); None bounds mean
    unbounded. Empty var_tbl (missing variables.json) disables var checks.
    """
    db_path = Path(project_dir) / 'ASSETS.DB'
    db = sqlite3.connect(str(db_path))
    cur = db.execute("SELECT name FROM img_map WHERE type='IMG'")
    img_keys = {row[0] for row in cur}
    cur = db.execute("SELECT name FROM img_map WHERE type='ANI'")
    anim_keys = {row[0] for row in cur}
    cur = db.execute("SELECT name FROM img_map WHERE type='CG'")
    cg_keys = {row[0] for row in cur}
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

    # Variable reference table: {id: (min, max, initial)}. None bounds mean
    # unbounded; missing file leaves the table empty (var checks disabled).
    var_tbl = {}
    var_path = Path(project_dir) / 'variables.json'
    if var_path.exists():
        with open(var_path, 'r', encoding='utf-8') as f:
            vdata = json.load(f)
        for v in vdata.get('variables', []):
            var_tbl[v['id']] = (v.get('min'), v.get('max'), v.get('initial', 0))

    return img_keys, anim_keys, cg_keys, char_keys, expr_set, nb_files, var_tbl


def validate_scene(nb_path, ref):
    """Validate a single .nb file.  Return list of error strings."""
    img_keys, anim_keys, cg_keys, char_keys, expr_set, nb_files, var_tbl = ref
    errors = []
    ranges = {vid: [ini, ini] for vid, (_, _, ini) in var_tbl.items()}
    text_ref = nb_path.read_text(encoding='utf-8', errors='replace')

    def check_var_segment(vid, op, val, lineno, prefix):
        """V1: validate a var / question-option assignment and propagate its
        known range.  prefix is '' for var commands and 'question: ' for
        option segments."""
        if op not in ('=', '+', '-'):
            errors.append(
                f"  {nb_path.name}:{lineno}: {prefix}var[{vid}] "
                f"op={op} not in =/+/ -")
            return
        if not _NUM_LITERAL.match(val):
            errors.append(
                f"  {nb_path.name}:{lineno}: {prefix}var[{vid}] value "
                f"{val!r} not a numeric literal")
            return
        if not var_tbl:
            return
        if vid not in var_tbl:
            errors.append(
                f"  {nb_path.name}:{lineno}: {prefix}var[{vid}] "
                f"not in variables.json")
            return
        mn, mx, _ = var_tbl[vid]
        iv = int(val)
        if op == '=':
            if (mn is not None and iv < mn) or (mx is not None and iv > mx):
                errors.append(
                    f"  {nb_path.name}:{lineno}: {prefix}var[{vid}] value "
                    f"{iv} out of bounds [{mn},{mx}]")
            ranges[vid] = [iv, iv]
            return
        cur = ranges.get(vid)
        if cur is None:
            return
        d = iv if op == '+' else -iv
        lo, hi = cur[0] + d, cur[1] + d
        if (mn is not None and lo < mn) or (mx is not None and hi > mx):
            errors.append(
                f"  {nb_path.name}:{lineno}: {prefix}var[{vid}] range "
                f"[{lo},{hi}] out of bounds [{mn},{mx}]")
        ranges[vid] = [lo, hi]

    def validate_question(raw, lineno):
        """V2: 'question' segment deep check, aligned to the engine
        ';'-split tokenizer (nb_parser.c nb_parse_line_semi)."""
        prompt_seg = raw.split(';', 1)[0].strip() if raw else ''
        if not prompt_seg:
            errors.append(
                f"  {nb_path.name}:{lineno}: question: prompt must be "
                "non-empty")
            return
        segs = split_semi(raw)
        opts = segs[1:]
        if not 1 <= len(opts) <= 10:
            errors.append(
                f"  {nb_path.name}:{lineno}: question: option count "
                f"{len(opts)} must be in [1,10]")
            return
        for i, seg in enumerate(opts, 1):
            fields = [f.strip() for f in seg.split(',')]
            if len(fields) != 4:
                errors.append(
                    f"  {nb_path.name}:{lineno}: question: segment {i} "
                    f"needs 'label,var,op,delta' (got {len(fields)} fields)")
                continue
            label, vid, op, dlt = fields
            if not label:
                errors.append(
                    f"  {nb_path.name}:{lineno}: question: segment {i} "
                    "label empty")
            check_var_segment(vid, op, dlt, lineno, 'question: ')

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

        if cmd == 'question':
            validate_question(raw, lineno)
            continue

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

            if cmd == 'var':
                if len(args) >= 3:
                    check_var_segment(args[0], args[1], args[2], lineno, '')

            elif cmd == 'bg':
                if args == ['hidedialog']:
                    pass  # keyword directive — no payload, no asset lookup
                elif text is not None and text.strip():
                    key = text.strip()
                    if key not in img_keys:
                        errors.append(
                            f"  {nb_path.name}:{lineno}: bg key {key!r} "
                            "not in img_map (type=IMG)")
                else:
                    errors.append(
                        f"  {nb_path.name}:{lineno}: bg asset key must be in "
                        f"braces 'bg(effect[,transition]){{key}}' — parens "
                        f"are reserved for params; 'bg(hidedialog)' closes "
                        f"the dialog")

            elif cmd == 'cg':
                if args == ['hidedialog']:
                    pass  # keyword directive — no payload, no asset lookup
                elif len(args) == 0 and text is not None and text.strip():
                    key = text.strip()
                    if key not in cg_keys:
                        errors.append(
                            f"  {nb_path.name}:{lineno}: cg key {key!r} "
                            "not in img_map (type=CG)")
                else:
                    errors.append(
                        f"  {nb_path.name}:{lineno}: cg asset key must be in "
                        f"braces 'cg(){{<key>}}' — parens are reserved for "
                        f"params; 'cg(hidedialog)' closes the dialog")

            elif cmd == 'char':
                if args == ['hideall']:
                    pass  # keyword directive — no payload, no lookup
                elif text is None or not text.strip():
                    errors.append(
                        f"  {nb_path.name}:{lineno}: char name must be in "
                        f"braces 'char(pos[,expr[,type]]){{name}}' — parens "
                        f"reserved for params; 'char(hideall)' hides all")
                else:
                    name = text.strip()
                    if name not in char_keys:
                        errors.append(
                            f"  {nb_path.name}:{lineno}: char name "
                            f"{name!r} not in characters.json")
                    else:
                        expr = args[1] if len(args) >= 2 else 'normal'
                        if (char_keys[name], expr) not in expr_set:
                            errors.append(
                                f"  {nb_path.name}:{lineno}: expression "
                                f"{expr!r} not defined for {name} "
                                f"(char_id={char_keys[name]})")

            elif cmd == 'bgm':
                if args == ['stop']:
                    pass  # keyword directive
                elif args:
                    errors.append(
                        f"  {nb_path.name}:{lineno}: bgm: only 'stop' is "
                        f"allowed in parens; the key goes in braces "
                        f"'bgm(){{key}}'")
                elif text is None or not text.strip():
                    errors.append(
                        f"  {nb_path.name}:{lineno}: bgm needs key in "
                        f"braces 'bgm(){{key}}'")

            elif cmd in ('sound', 'voice'):
                if text is None or not text.strip():
                    errors.append(
                        f"  {nb_path.name}:{lineno}: {cmd} needs key in "
                        f"braces '{cmd}(){{key}}'")

            elif cmd == 'sceneconf':
                if text is None or not text.strip():
                    errors.append(
                        f"  {nb_path.name}:{lineno}: sceneconf requires "
                        f"title in braces 'sceneconf(){{title[,type]}}'")

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

            elif cmd == 'delay' and len(args) >= 1:
                try:
                    if not float(args[0]) > 0:
                        raise ValueError
                except ValueError:
                    errors.append(
                        f"  {nb_path.name}:{lineno}: delay seconds "
                        f"{args[0]!r} must be a positive number")

            elif cmd == 'scene' and len(args) >= 1:
                if raw and ';' in raw:
                    for seg in split_semi(raw):
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


def load_accepted(project_dir):
    """Parse nb_lint_accepted.txt -> {file_stem: {lineno: pattern}}.

    Line format: 'file:lineno|pattern' ('#' comments / blank lines ignored).
    pattern is optional; when non-empty the source line must contain it.
    """
    acc = {}
    p = Path(project_dir) / 'nb_lint_accepted.txt'
    if not p.exists():
        return acc
    for line in p.read_text(encoding='utf-8').splitlines():
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        body, _, pattern = s.partition('|')
        file_stem, _, linestr = body.partition(':')
        if not file_stem or not linestr.isdigit():
            continue  # malformed entry ignored
        acc.setdefault(file_stem.strip(), {})[int(linestr)] = pattern.strip()
    return acc


def filter_accepted(errs, nb_path, accepted):
    """Partition errors into (kept, accepted_hits) given the project
    accepted-list.  Each error is expected in '  <file>:<lineno>: ...'
    form; hits are matched by file stem + lineno, with an optional
    pattern substring asserted against the source line."""
    kept = []
    hits = []
    by_line = accepted.get(nb_path.stem) if accepted else None
    if not by_line:
        return errs, hits
    text = nb_path.read_text(encoding='utf-8', errors='replace').splitlines()
    for e in errs:
        m = re.match(r'^  .*?:(\d+):', e)
        if not m:
            kept.append(e)
            continue
        ln = int(m.group(1))
        pat = by_line.get(ln)
        if pat is None:
            kept.append(e)
            continue
        if pat:
            src = text[ln - 1] if 1 <= ln <= len(text) else ''
            if pat not in src:
                kept.append(e)
                continue
        hits.append(e.strip())
    return kept, hits


def validate_project(project_dir):
    """Validate all .nb files under project_dir/scene/."""
    proj = Path(project_dir)
    db_path = proj / 'ASSETS.DB'
    if not db_path.exists():
        print(f"ERROR: {db_path} not found")
        return 1

    ref = load_reference(project_dir)
    accepted = load_accepted(project_dir)
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
        errs = filter_accepted(validate_scene(nb, ref), nb, accepted)
        kept, hits = errs
        if kept or hits:
            print(f"{nb.name}:")
            for e in kept:
                print(e)
            for h in hits:
                print(f"  (accepted: {h})")
            total_errors += len(kept)

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
