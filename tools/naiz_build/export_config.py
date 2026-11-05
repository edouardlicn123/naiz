#!/usr/bin/env python3
"""Export config.toml to C header for engine compilation.

Reads config.toml and generates nb_config.h.  config.toml is the single
source of truth for every project-level configuration value: the runtime
reads these as compile-time constants, so no settings.txt is deployed and
the build never overwrites anything the player owns.

Exports:
  - NAIZ_VERSION             project version (bump_version maintains it)
  - NAIZ_DLGSTYLE            dialog background style  (0-9)
  - NAIZ_BTNSTYLE            button colour scheme    (0-4)
  - NAIZ_BLACKLETTER_TITLE   blackletter on LOAD/SAVE page title
  - NAIZ_BLACKLETTER_DIALOG  blackletter on body ASCII
  - NAIZ_DEFAULT_LANG        shipping default language (first-boot fallback)
  - NAIZ_TRANSITION_TYPE     scene transition type
  - NAIZ_TRANSITION_FRAMES   scene transition frame count

Out-of-range values are hard errors, not warnings: a silently clamped
style or an untranslatable default_lang would ship a build that runs but
does not look or read like the project (AGENTS.md §九.6).

Usage:
    python export_config.py <project_dir> <output_path>
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from naiz_build.project_config import ProjectConfig
from naiz_lib.langdefs import LANG_CODE_SET as VALID_LANGS
from naiz_build.c_header import escape, header_preamble, header_footer

TRANSITION_MAP = {
    "cut": 0,
    "vblinds": 1,
    "hblinds": 2,
    "dblinds": 3,
    "rdblinds": 4,
    "pfade": 5,
    "checker": 6,
}

# Inclusive ranges mirrored from the layer/button style encoders.
DLGSTYLE_RANGE = (0, 9)
BTNSTYLE_RANGE = (0, 4)


def _style(cfg, section, rng, path):
    """Read a style code, refusing anything the layer modules cannot show."""
    lo, hi = rng
    val = cfg.get_int(section, "style", lo)
    if val is None or not (lo <= val <= hi):
        print(f"  ERROR: [{section}].style={val!r} outside {lo}-{hi} in {path}")
        sys.exit(1)
    return val


def _default_lang(cfg, path):
    """Shipping default language: must be a real code that has translations.

    An unresolvable default_lang would degrade to English at first boot with
    nothing logged on the player side, so both checks are hard errors.
    """
    lang = cfg.get_str("i18n", "default_lang", "eng")
    if lang not in VALID_LANGS:
        print(f"  ERROR: [i18n].default_lang='{lang}' is not a known language "
              f"code in {path} (known: {', '.join(sorted(VALID_LANGS))})")
        sys.exit(1)
    available = set(cfg.get_list("i18n", "targets", None) or [])
    available.add(cfg.get_str("i18n", "source_lang", "eng"))
    if lang not in available:
        print(f"  ERROR: [i18n].default_lang='{lang}' has no translation in "
              f"{path}: add it to [i18n].targets or set source_lang='{lang}'")
        sys.exit(1)
    return lang


def generate(project_dir, output_path):
    if not os.path.isfile(os.path.join(project_dir, 'config.toml')):
        print(f"  WARN: config.toml not found at {os.path.join(project_dir, 'config.toml')}, skipping")
        return 0

    cfg = ProjectConfig(project_dir)
    config_path = cfg.path

    version = cfg.version()
    if not version:
        # Not fatal: the UI simply omits the version field when it is empty.
        print("  WARN: [project].version missing; runtime will show no version")
    dlgstyle = _style(cfg, "dialog", DLGSTYLE_RANGE, config_path)
    btnstyle = _style(cfg, "button", BTNSTYLE_RANGE, config_path)
    bl_title = 1 if cfg.get_bool("blackletter", "title", False) else 0
    bl_dialog = 1 if cfg.get_bool("blackletter", "dialog", False) else 0
    default_lang = _default_lang(cfg, config_path)

    # Transition keeps its historical lenient handling; changing it here would
    # alter behaviour for projects that already rely on the default.
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
    lines.append('#define NAIZ_VERSION "%s"' % escape(version))
    lines.append('#define NAIZ_DLGSTYLE %d' % dlgstyle)
    lines.append('#define NAIZ_BTNSTYLE %d' % btnstyle)
    lines.append('#define NAIZ_BLACKLETTER_TITLE %d' % bl_title)
    lines.append('#define NAIZ_BLACKLETTER_DIALOG %d' % bl_dialog)
    lines.append('#define NAIZ_DEFAULT_LANG "%s"' % escape(default_lang))
    lines.append('')
    lines.append('#define NAIZ_TRANSITION_TYPE %d' % tval)
    lines.append('#define NAIZ_TRANSITION_FRAMES %d' % tframes)
    lines.extend(header_footer('NAIZ_CONFIG_H'))

    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print("export_config: version=%s dlgstyle=%d btnstyle=%d blackletter=%d/%d "
          "default_lang=%s transition=%s frames=%d -> %s"
          % (version, dlgstyle, btnstyle, bl_title, bl_dialog, default_lang,
             ttype, tframes, output_path))
    return 1


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: export_config.py <project_dir> <output_path>")
        sys.exit(1)

    generate(sys.argv[1], sys.argv[2])