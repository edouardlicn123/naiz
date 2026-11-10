#!/usr/bin/env python3
"""Export variables.json to C headers for engine compilation.

Reads variables.json and generates:
  - nb_var_table.h   — NB_VAR_COUNT + NbVarDef typedef (included by save.h)
  - nb_var_defs.h    — const var_defs[] data table (included by nb_vars.c only)

Usage:
    python export_vars.py <project_dir> <output_path>
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from naiz_build.c_header import escape, header_preamble, header_footer


def generate(project_dir, output_path):
    var_path = os.path.join(project_dir, 'variables.json')
    if not os.path.isfile(var_path):
        print(f"  WARN: variables.json not found at {var_path}, skipping")
        return 0

    with open(var_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    vars_list = data.get('variables', [])
    if not vars_list:
        print("  WARN: variables.json has no 'variables' array, skipping")
        return 0

    # Collect the string-variable slots.  `type` defaults to "int" so existing
    # integer-only projects need no change (devdoc 205 §5.1).
    str_vars = []
    for i, v in enumerate(vars_list):
        vtype = v.get('type', 'int')
        if vtype not in ('int', 'string'):
            print(f"  ERROR: variable '{v.get('id', '?')}' has unknown type "
                  f"{vtype!r} in {var_path} (expected int|string)")
            sys.exit(1)
        if vtype == 'string':
            str_vars.append(i)
    str_count = len(str_vars)
    str_maxlen = max([int(vars_list[i].get('maxlen', 0)) for i in str_vars] or [0])

    # nb_var_table.h: count + typedef only (no data table -> no per-TU copy)
    lines = header_preamble('export_vars.py', var_path, output_path, 'NB_VAR_TABLE_H')
    lines.append('#define NB_VAR_COUNT %d' % len(vars_list))
    lines.append('#define NB_STRVAR_COUNT %d' % str_count)
    # Max bytes per string slot (NUL included): 12 codepoints * 3 bytes
    # (ASCII or kana) + NUL = 37 <= 40.  Raising it requires a save-version
    # bump because the array lives in SaveData (devdoc 205 §5.2).
    lines.append('#define NB_VAR_STR_MAX 40')
    lines.append('#define NB_VAR_MAXLEN %d' % str_maxlen)
    lines.append('')
    lines.append('/* String slot count clamped to >=1 so a project without string')
    lines.append(' * variables still declares a valid C array. */')
    lines.append('#define NB_STRVAR_SLOTS %d' % (str_count if str_count > 0 else 1))
    lines.append('')
    lines.append('typedef struct {')
    lines.append('    const char *id;')
    lines.append('    const char *name;')
    lines.append('    const char *desc;')
    lines.append('    int initial;')
    lines.append('    int min;')
    lines.append('    int max;')
    lines.append('    int is_string;          /* 1 = string slot, 0 = int */')
    lines.append('    const char *initial_str; /* string default; "" for int vars */')
    lines.append('    int maxlen;             /* codepoint limit for string vars */')
    lines.append('} NbVarDef;')
    lines.extend(header_footer('NB_VAR_TABLE_H'))
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    # nb_var_defs.h: data table, included only by nb_vars.c
    defs_path = os.path.join(os.path.dirname(output_path), 'nb_var_defs.h')
    dlines = header_preamble('export_vars.py', var_path, defs_path, 'NB_VAR_DEFS_H')
    dlines.append('#include "nb_var_table.h"')
    dlines.append('')
    dlines.append('/* int variable index -> string slot; -1 = not a string variable */')
    dlines.append('static const int var_str_slot[NB_VAR_COUNT] = {')
    slot_map = []
    next_slot = 0
    for v in vars_list:
        if v.get('type', 'int') == 'string':
            slot_map.append(next_slot)
            next_slot += 1
        else:
            slot_map.append(-1)
    dlines.append('    ' + ', '.join(str(s) for s in slot_map))
    dlines.append('};')
    dlines.append('')
    dlines.append('static const NbVarDef var_defs[NB_VAR_COUNT] = {')
    for v in vars_list:
        is_string = 1 if v.get('type', 'int') == 'string' else 0
        if is_string:
            initial_int = 0
            initial_str = escape(str(v.get('initial', '')))
            maxlen = int(v.get('maxlen', 0))
            vmin, vmax = 0, 0
        else:
            initial_int = int(v.get('initial', 0))
            initial_str = ''
            maxlen = 0
            vmin = int(v.get('min', 0))
            vmax = int(v.get('max', 9999))
        dlines.append('    {"%s", "%s", "%s", %d, %d, %d, %d, "%s", %d},' % (
            escape(v['id']),
            escape(v.get('name', '')),
            escape(v.get('desc', '')),
            initial_int,
            vmin,
            vmax,
            is_string,
            initial_str,
            maxlen,
        ))
    dlines.append('};')
    dlines.extend(header_footer('NB_VAR_DEFS_H'))
    with open(defs_path, 'w') as f:
        f.write('\n'.join(dlines))

    print("export_vars: %d variables (%d string) -> %s (+ nb_var_defs.h)" %
          (len(vars_list), str_count, output_path))
    return len(vars_list)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: export_vars.py <project_dir> <output_path>")
        sys.exit(1)

    generate(sys.argv[1], sys.argv[2])
