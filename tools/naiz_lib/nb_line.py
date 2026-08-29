"""Shared NB script line parser.

Consolidates the previously duplicated NB command-line parsing regexes
in naiz_build/nb_validator.py and naiz_conv/i18n_gen.py.

Returns an NbLine named tuple with:
  cmd  - command name
  args - list of stripped argument strings (empty entries dropped)
  text - dialogue text string, or None for the bare `cmd(args)` form
  raw  - raw parenthesized argument string (without parens), or None
"""

import re
from collections import namedtuple

NbLine = namedtuple('NbLine', 'cmd args text raw')

# Form 1: cmd(args){text}  — dialogue lines with optional args
_RE_FORM = re.compile(r'^(\w+)(?:\(([^)]*)\))?\{([^}]*)\}')
# Form 2: cmd(args)       — bare command lines (no trailing text)
_RE_BARE = re.compile(r'^(\w+)\(([^)]*)\)\s*$')


def parse_nb_line(line):
    """Parse one NB script line.

    Returns an NbLine(cmd, args, text, raw), or None for blank / comment /
    unrecognized lines. Blank and '#' comment lines are skipped by the caller
    before invoking this function; this guard is kept for robustness.
    """
    line = line.strip()
    if not line or line.startswith('#'):
        return None

    m = _RE_FORM.match(line)
    if m:
        paren = m.group(2)
        args = [a.strip() for a in paren.split(',') if a.strip()] if paren else []
        return NbLine(m.group(1), args, m.group(3), paren)

    m = _RE_BARE.match(line)
    if m:
        paren = m.group(2)
        args = [a.strip() for a in paren.split(',')] if paren else []
        return NbLine(m.group(1), args, None, paren)

    return None
