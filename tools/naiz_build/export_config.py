#!/usr/bin/env python3
"""Export config.toml to C header for engine compilation.

Reads config.toml and generates nb_config.h:
  - NAIZ_TRANSITION_TYPE — scene transition type
  - NAIZ_TRANSITION_FRAMES — scene transition frame count

Usage:
    python export_config.py <project_dir> <output_path>
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from naiz_build.project_config import ProjectConfig
from naiz_build.c_header import header_preamble, header_footer

TRANSITION_MAP = {
    "cut": 0,
    "vblinds": 1,
    "hblinds": 2,
    "dblinds": 3,
    "rdblinds": 4,
    "pfade": 5,
    "checker": 6,
}

def generate(project_dir, output_path):
    if not os.path.isfile(os.path.join(project_dir, 'config.toml')):
        print(f"  WARN: config.toml not found at {os.path.join(project_dir, 'config.toml')}, skipping")
        return 0

    cfg = ProjectConfig(project_dir)
    config_path = cfg.path

    ttype = cfg.get_str("transition", "type", "pfade")
    if ttype not in TRANSITION_MAP:
        print(f"  WARN: unknown transition '{ttype}', defaulting to pfade")
        ttype = "pfade"
    tval = TRANSITION_MAP[ttype]

    tframes = cfg.get_int("transition", "frames", 16)
    if tframes is None or tframes < 1 or tframes > 64:
        print(f"  WARN: invalid transition_frames {tframes}, defaulting to 16")
        tframes = 16

    lines = header_preamble('export_config.py', config_path, output_path, 'NAIZ_CONFIG_H')
    lines.append('#define NAIZ_TRANSITION_TYPE %d' % tval)
    lines.append('#define NAIZ_TRANSITION_FRAMES %d' % tframes)
    lines.extend(header_footer('NAIZ_CONFIG_H'))

    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print("export_config: transition=%s frames=%d -> %s" % (ttype, tframes, output_path))
    return 1


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: export_config.py <project_dir> <output_path>")
        sys.exit(1)

    generate(sys.argv[1], sys.argv[2])