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

    # nb_var_table.h: count + typedef only (no data table -> no per-TU copy)
    lines = header_preamble('export_vars.py', var_path, output_path, 'NB_VAR_TABLE_H')
    lines.append('#define NB_VAR_COUNT %d' % len(vars_list))
    lines.append('')
    lines.append('typedef struct {')
    lines.append('    const char *id;')
    lines.append('    const char *name;')
    lines.append('    const char *desc;')
    lines.append('    int initial;')
    lines.append('    int min;')
    lines.append('    int max;')
    lines.append('} NbVarDef;')
    lines.extend(header_footer('NB_VAR_TABLE_H'))
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    # nb_var_defs.h: data table, included only by nb_vars.c
    defs_path = os.path.join(os.path.dirname(output_path), 'nb_var_defs.h')
    dlines = header_preamble('export_vars.py', var_path, defs_path, 'NB_VAR_DEFS_H')
    dlines.append('#include "nb_var_table.h"')
    dlines.append('')
    dlines.append('static const NbVarDef var_defs[NB_VAR_COUNT] = {')
    for v in vars_list:
        dlines.append('    {"%s", "%s", "%s", %d, %d, %d},' % (
            escape(v['id']),
            escape(v.get('name', '')),
            escape(v.get('desc', '')),
            v.get('initial', 0),
            v.get('min', 0),
            v.get('max', 9999),
        ))
    dlines.append('};')
    dlines.extend(header_footer('NB_VAR_DEFS_H'))
    with open(defs_path, 'w') as f:
        f.write('\n'.join(dlines))

    print("export_vars: %d variables -> %s (+ nb_var_defs.h)" % (len(vars_list), output_path))
    return len(vars_list)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: export_vars.py <project_dir> <output_path>")
        sys.exit(1)

    generate(sys.argv[1], sys.argv[2])
