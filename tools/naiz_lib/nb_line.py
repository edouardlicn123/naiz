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


def split_semi(raw):
    """Split a paren-arg raw string into ';'-delimited segments.

    Mirrors the engine tokenizer nb_parse_line_semi (core/engine/nb_parser.c):
    ';' is the top-level argument delimiter for multi-segment commands
    (question/scene); commas inside a segment are left intact and consumed
    later.  Whitespace is stripped and empty segments are dropped.
    """
    if raw is None:
        return []
    return [seg.strip() for seg in raw.split(';') if seg.strip()]


def next_field(segment):
    """Return (field, rest) for one comma-delimited field of a segment.

    Byte-for-byte mirror of nb_next_field() in core/engine/nb_commands.c, so
    the keys this module extracts are exactly the keys the engine looks up in
    tr().  Keep both implementations in step -- they are the only thing
    standing between a script edit and a silently untranslated string.

    Escapes: "\\," is a literal comma inside the field, "\\\\" a literal
    backslash, and any other "\\x" is preserved verbatim.  Surrounding blanks
    are trimmed, matching nb_next_field().  Returns (None, segment) when no
    delimiter remains, mirroring nb_next_field()'s "a LAST field without a
    trailing comma is NOT consumed" contract.
    """
    s = segment
    i = 0
    while i < len(s) and s[i] in ' \t':
        i += 1

    # Locate the first delimiter, skipping every backslash-escaped pair.
    j = i
    while j < len(s):
        if s[j] == '\\' and j + 1 < len(s):
            j += 2
            continue
        if s[j] == ',':
            break
        j += 1
    if j >= len(s):
        return None, segment

    # Trim trailing blanks so "Yes ,v" and "Yes,v" resolve to the same key.
    end = j
    while end > i and s[end - 1] in ' \t':
        end -= 1

    # Collapse the two defined escapes; leave any other "\x" alone.
    out = []
    p = i
    while p < end:
        if s[p] == '\\' and p + 1 < end and s[p + 1] in (',', '\\'):
            p += 1
        out.append(s[p])
        p += 1

    rest = s[j + 1:]
    k = 0
    while k < len(rest) and rest[k] in ' \t':
        k += 1
    return ''.join(out), rest[k:]


def has_field_delim(segment):
    """True when an unescaped comma remains in the segment.

    Mirror of nb_has_field_delim() in core/engine/nb_commands.c.  Code that
    only needs to *peek* for the next delimiter must use this instead of
    ``',' in segment``, or an escaped comma looks like a field boundary.
    """
    j = 0
    while j < len(segment):
        if segment[j] == '\\' and j + 1 < len(segment):
            j += 2
            continue
        if segment[j] == ',':
            return True
        j += 1
    return False


def option_fields(segment):
    """Split a question/scene option segment into (label, var, op, delta).

    Mirrors how cmd_question (core/engine/nb_question.c) actually reads it:
    three nb_next_field() calls, then the delta taken from the remaining tail
    rather than through the field splitter.  Returns None when the segment does
    not supply at least three delimiters -- the "got N fields" case a
    malformed script hits.
    """
    label, rest = next_field(segment)
    if label is None:
        return None
    var, rest = next_field(rest)
    if var is None:
        return None
    op, rest = next_field(rest)
    if op is None:
        return None
    return label, var, op, rest.strip()


def raw_fields(segment):
    """Return the segment's field slices, still escaped, final field included.

    Same boundary rules as next_field() but nothing is unescaped and the last
    field is kept, so a linter can inspect the author's original spacing.  An
    escaped comma stays inside its field, so "Ira\\, Jr." is one slice and is
    not mistaken for a field with stray whitespace.
    """
    out, start, i = [], 0, 0
    while i < len(segment):
        if segment[i] == '\\' and i + 1 < len(segment):
            i += 2
            continue
        if segment[i] == ',':
            out.append(segment[start:i])
            start = i + 1
        i += 1
    out.append(segment[start:])
    return out
