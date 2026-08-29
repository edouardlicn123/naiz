"""C-language anti-regression rules (AGENTS section 17, C1-C25).

Each checker takes the file text and returns a list of
(lineno, description) findings.  AUTO rules are deterministic;
HEUR rules produce candidates that need human confirmation.
"""

import re
from collections import Counter

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _line(text, pos):
    return text.count("\n", 0, pos) + 1


def _strip_c_comments(text):
    """Remove /*..*/ and //.. comments so rules do not fire on prose.

    Block comments are replaced with an equal number of newlines so reported
    line numbers stay aligned with the original source.
    """
    def _blk(m):
        return "\n" * m.group(0).count("\n")

    text = re.sub(r"/\*.*?\*/", _blk, text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def _find_switch_blocks(text):
    """Yield (start_line, block_text) for each switch (...) { ... } block."""
    blocks = []
    for m in re.finditer(r"\bswitch\s*\([^)]*\)\s*\{", text):
        start = m.end() - 1  # the '{'
        depth = 0
        pos = start
        while pos < len(text):
            ch = text[pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            pos += 1
        if depth != 0:
            continue
        blocks.append((_line(text, m.start()), text[start:pos + 1]))
    return blocks


def _has_null_check(text, var, after):
    """True if 'var' is null-checked inside the 400-char window after 'after'."""
    window = text[after:after + 400]
    return bool(re.search(r"\b" + re.escape(var) + r"\b\s*==\s*NULL", window) or
                re.search(r"\b" + re.escape(var) + r"\b\s*!=\s*NULL", window) or
                re.search(r"!\s*\b" + re.escape(var) + r"\b", window))


_CTRL_KEYWORDS = {"if", "for", "while", "switch", "return", "sizeof",
                  "do", "else"}


def _find_functions(text):
    """Return [(name, start, end)] brace-balanced function spans.

    Operates on comment-stripped text.  The header regex requires a '{'
    terminator and excludes control-flow keywords so 'if (...){' is not
    misread as a function.
    """
    out = []
    for m in re.finditer(
            r"(?m)(?:^|[;{}])\s*"
            r"(?:[A-Za-z_]\w*(?:\s*\*\s*)?\s+)*"
            r"(?P<name>[A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{", text):
        name = m.group("name")
        if name in _CTRL_KEYWORDS:
            continue
        start = m.end() - 1
        depth = 0
        pos = start
        while pos < len(text):
            ch = text[pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            pos += 1
        if depth == 0:
            out.append((name, m.start(), pos + 1))
    return out


def _func_span(functions, pos):
    for name, s, e in functions:
        if s <= pos < e:
            return (name, s, e)
    return None


# ---------------------------------------------------------------------------
# memory / file safety (C1-C9, C11, C14, C15)
# ---------------------------------------------------------------------------

RE_ALLOC = re.compile(
    r"(?:[A-Za-z_]\w*(?:\s*\*\s*)?\s+)?"
    r"(?P<var>[A-Za-z_]\w*)\s*=\s*(?:\([^;]*?\)\s*)?"
    r"(?:malloc|calloc|realloc)\s*\([^;]*;"
)

RE_ALLOC_EMBEDDED = re.compile(
    r"if\s*\(\s*\(?\s*(?P<var>[A-Za-z_]\w*)\s*=\s*"
    r"(?:\([^)]*\)\s*)?(?:malloc|calloc|realloc)\s*\([^;]*?\)\s*\)?"
    r"\s*(?P<cmp>==|!=)\s*NULL\s*\)"
)


def _immediate_null_test(text, var, start):
    """True when a NULL test for var appears within the next ~3 statements.

    Covers both 'x=malloc(n); if(!x) ...' and grouped allocs like
    'x=calloc(); y=calloc(); if(!x||!y) ...'.  Window is bounded so a null
    check much later (e.g. after unrelated statements) is still reported.
    """
    end = start
    for _ in range(3):
        nxt = text.find(";", end)
        if nxt == -1:
            end = min(len(text), end + 200)
            break
        end = nxt + 1
    window = text[start:min(end, start + 400)]
    return bool(re.search(r"\b" + re.escape(var) + r"\b\s*(?:==|!=)\s*NULL",
                          window) or
                re.search(r"!\s*\b" + re.escape(var) + r"\b", window))


def check_c1(text, _path):
    """malloc/calloc/realloc result must be NULL-checked (HEUR).

    Accepted forms: 'x = malloc(n); if (!x) ...' immediately after the
    statement, or an if-condition that embeds the alloc with a NULL compare.
    """
    out = []
    clean = _strip_c_comments(text)
    embedded = []
    for m in RE_ALLOC_EMBEDDED.finditer(clean):
        embedded.append((m.start(), m.end(), m.group("var")))
    for m in RE_ALLOC.finditer(clean):
        if any(s <= m.start() < e for s, e, _ in embedded):
            continue
        var = m.group("var")
        if _immediate_null_test(clean, var, m.end()):
            continue
        out.append((_line(clean, m.start()),
                    f"malloc/calloc/realloc result '{var}' not null-checked "
                    "immediately after the statement"))
    return out


RE_FOPEN = re.compile(r"(?P<var>[A-Za-z_]\w*)\s*=\s*fopen\s*\([^;]*;")


def check_c2(text, _path):
    """fopen result must be checked and failure handled."""
    out = []
    clean = _strip_c_comments(text)
    for m in RE_FOPEN.finditer(clean):
        if _has_null_check(clean, m.group("var"), m.end()):
            continue
        out.append((_line(clean, m.start()),
                    f"fopen result '{m.group('var')}' not null-checked here"))
    return out


def check_c3(text, _path):
    """fread/fwrite/fgets results should be checked (if-condition context)."""
    out = []
    clean = _strip_c_comments(text)
    for m in re.finditer(r"\b(fread|fwrite|fgets)\s*\(", clean):
        ctx = clean[max(0, m.start() - 120):m.start()]
        if re.search(r"\bif\s*\(|\bwhile\s*\(", ctx.splitlines()[-3:0] or ctx):
            continue
        out.append((_line(clean, m.start()),
                    f"'{m.group(1)}(' return value may be unchecked"))
    return out


def check_c4(text, _path):
    """strncpy must be followed by manual NUL termination (HEUR).

    The terminator assignment ('dest[i] = '\\0'' / '= 0') must appear within
    the following statements (up to 6 lines / 3 ';' boundaries); a terminator
    much further away is treated as missing so the reviewer confirms.
    """
    out = []
    clean = _strip_c_comments(text)
    funcs = _find_functions(clean)
    for m in re.finditer(r"\bstrncpy\s*\(\s*([A-Za-z_]\w*"
                         r"(?:\s*(?:->|\.)\s*[A-Za-z_]\w*)*)", clean):
        dest = m.group(1)
        span = _func_span(funcs, m.start())
        limit = span[2] if span else len(clean)
        end = m.end()
        for _ in range(3):
            nxt = clean.find(";", end)
            if nxt == -1 or nxt >= limit:
                end = min(limit, end + 160)
                break
            end = nxt + 1
        window = clean[m.end():min(end, m.end() + 400)]
        if re.search(re.escape(dest) + r"\s*\[[^]]*\]\s*=\s*(?:['\"]\\0['\"]|\b0\b)",
                     window):
            continue
        out.append((_line(clean, m.start()),
                    "strncpy without an explicit NUL terminator in the "
                    "following statements"))
    return out


def check_c5(text, _path):
    """sprintf is banned; use snprintf (AUTO)."""
    clean = _strip_c_comments(text)
    return [(_line(clean, m.start()), "sprintf() used; must be snprintf")
            for m in re.finditer(r"\bsprintf\s*\(", clean)]


def check_c8(text, _path):
    """Signed-int arithmetic edge patterns worth a manual look (HEUR)."""
    out = []
    clean = _strip_c_comments(text)
    for m in re.finditer(r"\b(atoi|strtol|atoi_a|strtoul)\s*\([^)]*\)"
                         r"\s*-\s*\w|-\s*\batoi\b", clean):
        out.append((_line(clean, m.start()),
                    "atoi/strtol result negated: INT_MIN edge is UB"))
    for m in re.finditer(r"\bvmax\s*-\s*\w+|-\s*\bval\b|\bvmin\s*\+\s*\w+", clean):
        out.append((_line(clean, m.start()),
                    "variable-range +/- with large script deltas"))
    return out


def check_c10(text, _path):
    """switch block missing a default branch (HEUR)."""
    out = []
    clean = _strip_c_comments(text)
    for line, block in _find_switch_blocks(clean):
        if not re.search(r"\bdefault\s*:", block):
            out.append((line, "switch block has no default branch"))
    return out


def check_c11(text, _path):
    """assert() is banned (AUTO)."""
    clean = _strip_c_comments(text)
    return [(_line(clean, m.start()), "assert() used; may be stripped by NDEBUG")
            for m in re.finditer(r"\bassert\s*\(", clean)]


def check_c21(text, _path):
    """strcpy/strcat/gets are unbounded and banned (AUTO).

    'gets' has no bounds argument at all; strcpy/strcat cannot declare how
    many bytes they copy, so any use is an audit-blocking violation.
    """
    clean = _strip_c_comments(text)
    out = []
    for m in re.finditer(r"\b(strcpy|strcat|gets)\s*\(", clean):
        out.append((_line(clean, m.start()),
                    f"{m.group(1)}() unbounded; use snprintf/strncpy + "
                    "explicit NUL"))
    return out


def check_c13(text, _path):
    """Unused static function detection (HEUR)."""
    out = []
    clean = _strip_c_comments(text)
    names = {}
    for m in re.finditer(r"^\s*static\s+(?:const\s+)?\w+(?:\s+\w+)*\s+"
                         r"(\w+)\s*\([^;]*\)\s*\{", clean, flags=re.M):
        names[m.group(1)] = m.start()
    for name, pos in names.items():
        uses = len(re.findall(r"\b" + re.escape(name) + r"\b", clean))
        if uses < 2:
            out.append((_line(clean, pos), f"static '{name}()' appears unused"))
        if len(names) <= 1:
            pass
    return out


def check_c14(text, _path):
    """Silent error returns in functions that otherwise log (HEUR).

    A braced 'if (...) { return err; }' without hal_log/NB_DEBUG is a
    candidate only when the enclosing function logs on other paths; pure
    validator functions that never log are not flagged (that is their norm).
    """
    out = []
    clean = _strip_c_comments(text)
    funcs = _find_functions(clean)
    for m in re.finditer(r"if\s*\([^)]*\)\s*\{[^{}]*?return\s*[^;]*;",
                         clean, flags=re.DOTALL):
        body = m.group(0)
        if "hal_log" in body or "NB_DEBUG" in body:
            continue
        if not re.search(r"\breturn\s*(NULL|0|1|-1)\s*;", body):
            continue
        span = _func_span(funcs, m.start())
        if span is None:
            continue
        fname, fs, fe = span
        if "hal_log" not in clean[fs:fe] and \
                "NB_DEBUG" not in clean[fs:fe]:
            continue
        out.append((_line(clean, m.start()),
                    f"error return path without hal_log (function '{fname}' "
                    "logs elsewhere)"))
    return out


def check_c15(text, _path):
    """File-level fopen/fclose balance as a leak hint (HEUR)."""
    clean = _strip_c_comments(text)
    opened = len(re.findall(r"\bfopen\s*\(", clean))
    closed = len(re.findall(r"\bfclose\s*\(", clean))
    if opened and opened > closed:
        return [(1, f"fopen count {opened} > fclose count {closed}; "
                     "verify every early return closes the stream")]
    return []


RE_MEMCPY = re.compile(
    r"\b(memcpy|memmove)\s*\(\s*(\w+)[^,]*,\s*\w+\s*,\s*(?:sizeof\(\w+\)|[^)]*)\s*\)")


def check_c9(text, _path):
    """memcpy/memmove size vs target buffer size (HEUR, manual confirm)."""
    out = []
    clean = _strip_c_comments(text)
    for m in RE_MEMCPY.finditer(clean):
        out.append((_line(clean, m.start()),
                    f"{m.group(1)} into '{m.group(2)}': confirm size fits target"))
    return out


def check_c7(text, _path):
    """Hardcoded numeric fseek/skip offsets near struct parsing (HEUR)."""
    out = []
    clean = _strip_c_comments(text)
    if re.search(r"\bfseek\s*\(", clean):
        for m in re.finditer(r"\bfseek\s*\([^;]*?,\s*(\d+)\s*,", clean):
            off = int(m.group(1))
            if off > 4:
                out.append((_line(clean, m.start()),
                            f"fseek offset {off}: verify against struct layout "
                            "(prefer offsetof)"))
    return out


def check_c6(text, path):
    """Index / pointer-bound review targets (HEUR lightweight)."""
    out = []
    clean = _strip_c_comments(text)
    if re.search(r"\b(atoi|strtol)\b|\[[^]]*\]\s*=\s*[^;]*;", clean):
        for m in re.finditer(r"&stream|\[[^]]*\]\s*\[\s*\w+\s*\]", clean):
            out.append((_line(clean, m.start()),
                        "array index / pointer bound: manually confirm range"))
            if len(out) >= 6:
                break
    return out


# ---------------------------------------------------------------------------
# Tier-2 deterministic rules: C22 INT_MIN negation, C23 double-free,
# C24 memcpy target-size cross-check, C25 use-after-free
# ---------------------------------------------------------------------------

RE_SIGNED_DECL = re.compile(
    r"(?:^|[;{}])\s*(?:register\s+|const\s+)?"
    r"(?:(?:signed\s+)?(?:int|short\b|long\s+long)|int8_t|int16_t|int32_t)"
    r"\s+(?P<var>[A-Za-z_]\w*)\s*(?:[;=,\[]|$)")


def _signed_decls(span_text):
    """Return set of function-local signed integer variable names."""
    return {m.group("var") for m in RE_SIGNED_DECL.finditer(span_text)}


RE_MINUS_VAR = re.compile(r"-\s*(?P<var>[A-Za-z_]\w*)\b")


def _is_negation(text, mstart):
    """True when the '-' before a variable is unary negation, not a binary
    subtraction (``x - var``), an index/deref subtraction (``a[i] - var``,
    ``f(x) - var``) or a pre-decrement (``--var``)."""
    if mstart > 0 and text[mstart - 1] == "-":
        return False  # --var decrement
    i = mstart - 1
    while i >= 0 and text[i] in " \t\r\n":
        i -= 1
    if i < 0:
        return True
    c = text[i]
    if c == "]" or c == ")" or c.isalnum() or c == "_":
        return False
    return True


def check_c22(text, _path):
    """Negating a function-local signed int: -x when x==INT_MIN is UB (AUTO).

    Recognises ``-var``, ``var * -1``, ``var / -1`` and ``0 - var`` for
    variables declared as signed integers in the same function.  A negation
    is exempt when the same statement already guards with an INT_MIN
    comparison (``(var == INT_MIN) ? INT_MIN : -var``), which is the
    canonical safe formulation.
    """
    out = []
    clean = _strip_c_comments(text)

    def _guarded(span, var, mstart):
        stmt = max(span.rfind(";", 0, mstart),
                   span.rfind("{", 0, mstart), 0)
        esc = re.escape(var) + r"(?:\[[^]]*\])?"
        guard = re.compile(esc + r"\s*(?:==|!=)\s*INT_MIN|INT_MIN\s*(?:==|!=)\s*" + esc)
        return bool(guard.search(span[stmt:mstart]))

    for name, fs, fe in _find_functions(clean):
        span = clean[fs:fe]
        for var in _signed_decls(span):
            reported = set()
            esc = re.escape(var)
            for m in RE_MINUS_VAR.finditer(span):
                if m.group("var") != var or not _is_negation(span, m.start()):
                    continue
                line = _line(clean, fs + m.start())
                if (line, var) in reported or _guarded(span, var, m.start()):
                    continue
                reported.add((line, var))
                out.append((line, f"negating signed '{var}': -INT_MIN is UB; "
                                  "widen to long/unsigned or guard"))
            for pat in (esc + r"\s*\*\s*-\s*1\b",
                        esc + r"\s*/\s*-\s*1\b",
                        r"0\s*-\s*" + esc + r"\b"):
                for m in re.finditer(pat, span):
                    line = _line(clean, fs + m.start())
                    if (line, var) in reported or _guarded(span, var, m.start()):
                        continue
                    reported.add((line, var))
                    out.append((line, f"negating signed '{var}': -INT_MIN is "
                                      "UB; widen to long/unsigned or guard"))
    return out


def _frees(span_text):
    return [(m.start(), m.group(1))
            for m in re.finditer(r"\bfree\s*\(\s*([A-Za-z_]\w*)\s*\)",
                                 span_text)]


def check_c23(text, _path):
    """free() of the same pointer twice on the SAME execution path (AUTO).

    A NULL/malloc reset between the frees clears the pointer, and a
    control-flow terminator (return/break/continue/goto/exit) between them
    puts the two frees on mutually exclusive paths — the common "free on each
    error path then on success" cleanup pattern is not a double free.
    """
    out = []
    clean = _strip_c_comments(text)
    term = re.compile(r"\b(?:return|break|continue|goto)\b|exit\s*\(")
    for name, fs, fe in _find_functions(clean):
        span = clean[fs:fe]
        seen = {}
        for pos, var in _frees(span):
            if var in seen:
                since = span[seen[var]:pos]
                if re.search(r"\b" + re.escape(var)
                             + r"\s*=\s*(?:NULL|\([^)]*\)\s*NULL)", since) or \
                        re.search(r"\b" + re.escape(var)
                                  + r"\s*=\s*\(?[^;]*?(?:malloc|calloc|realloc)"
                                     r"\s*\(", since):
                    del seen[var]
                    continue
                if term.search(since):
                    # reached only after an early return/break -> exclusive.
                    del seen[var]
                    continue
                out.append((_line(clean, fs + pos),
                            f"double free of '{var}' (no NULL reset between)"))
            else:
                seen[var] = pos
    return out


RE_MEMCPY_ARR = re.compile(
    r"\b(memcpy|memmove)\s*\(\s*([A-Za-z_]\w*)\s*,\s*[^,]+,\s*"
    r"(?:(\d+)|sizeof\s*\(\s*([A-Za-z_]\w*)\s*\))\s*\)")

RE_BYTE_ARRAY_DECL = re.compile(
    r"(?:^|[;{}])\s*(?:(?:unsigned\s+)?char|uint8_t|int8_t|BYTE|byte)\s+"
    r"(?P<name>[A-Za-z_]\w*)\s*\[\s*(?P<size>\d+)\s*\]\s*")


def check_c24(text, _path):
    """memcpy/memmove size exceeds the destination byte-array (AUTO).

    Only byte-sized element arrays with literal dimensions are compared;
    pointer targets / unknown sizes stay with the C9 heuristic.
    """
    out = []
    clean = _strip_c_comments(text)
    for name, fs, fe in _find_functions(clean):
        span = clean[fs:fe]
        arr = {m.group("name"): int(m.group("size"))
               for m in RE_BYTE_ARRAY_DECL.finditer(span)}
        if not arr:
            continue
        for m in RE_MEMCPY_ARR.finditer(span):
            dst = m.group(2)
            if dst not in arr:
                continue
            dst_sz = arr[dst]
            if m.group(3) is not None:
                n = int(m.group(3))
                if n > dst_sz:
                    out.append((_line(clean, fs + m.start()),
                                f"{m.group(1)} copies {n} bytes into "
                                f"'{dst}'[{dst_sz}]"))
            else:
                src = m.group(4)
                if src in arr and arr[src] > dst_sz:
                    out.append((_line(clean, fs + m.start()),
                                f"{m.group(1)} copies sizeof('{src}') "
                                f"[{arr[src]}] into '{dst}'[{dst_sz}]"))
    return out


def check_c25(text, _path):
    """Dereference of a freed pointer in the same block (HEUR).

    Scans from each free() to the end of the enclosing block (``}``, or a
    ``return``/``break``/``continue``/``goto``) looking for ``->``/``[``/
    ``(`` access of the pointer before any reassignment.  The classic
    "free on each error path then on success" pattern never shares a block
    with a later dereference, so it does not produce cross-branch noise.
    """
    out = []
    clean = _strip_c_comments(text)
    block_term = re.compile(r"[\}]|\b(?:return|break|continue|goto)\b|\bexit\s*\(")
    for name, fs, fe in _find_functions(clean):
        span = clean[fs:fe]
        for pos, var in _frees(span):
            tail = span[pos + len("free(") + len(var):]
            remain = block_term.split(tail, 1)[0]
            esc = re.escape(var)
            m = re.search(esc + r"\s*(?:->|\[|\()", remain)
            if m and not re.search(esc + r"\s*=", remain[:m.start()]):
                out.append((_line(clean, fs + pos),
                            f"'{var}' dereferenced after free() before "
                            "reassignment"))
    return out


# ---------------------------------------------------------------------------
# lifecycle / logic (C16-C20) -- MANUAL review hints only
# ---------------------------------------------------------------------------

MANUAL_NOTES = {
    "C6": "Index/pointer bounds: re-read mag.c (decoder stride/palette), "
          "nb_parser.c (token buffer), keyboard.c (BIOS ring), render_text.c "
          "(glyph coords) for out-of-range access.",
    "C7": "Struct offsets / file parsing: confirm save.c/save_io.c/save_sys.c "
          "use offsetof-derived sizes, not hardcoded skips.",
    "C9": "memcpy/memmove target capacity: verify each size argument against "
          "the destination array size (HEUR hits above need confirmation).",
    "C16": "Save-format jumps: read position + skip must equal the target "
          "field offset; re-check SaveData layout end to end.",
    "C17": "Cursor ghosting: in nb_save_dialog.c/nb_menu.c/nb.c every "
          "mouse_invalidate_cursor() must be followed by a full redraw of the "
          "old cursor area, else mouse_erase_cursor() first.",
    "C18": "Fast-path side effects: image cache hits must preserve every "
          "external side effect of the slow path (image_set_palette etc.).",
    "C19": "Interpreter: verify cmd_table dispatch, nb_load/scene_end state "
          "reset completeness, and VM variable/stack bounds.",
    "C20": "Dead logic: hunt always-true/always-false conditions and if() "
          "typos; re-check layer.c scene_end and the transition_run call.",
}


def registry():
    return {
        "C1": (check_c1, "HEUR", "malloc/calloc/realloc NULL check"),
        "C2": (check_c2, "HEUR", "fopen result check"),
        "C3": (check_c3, "HEUR", "fread/fwrite/fgets result check"),
        "C4": (check_c4, "HEUR", "strncpy NUL termination"),
        "C5": (check_c5, "AUTO", "sprintf banned, use snprintf"),
        "C7": (check_c7, "HEUR", "struct offset/skip sanity"),
        "C8": (check_c8, "HEUR", "signed-int edge arithmetic"),
        "C9": (check_c9, "HEUR", "memcpy/memmove target capacity"),
        "C10": (check_c10, "HEUR", "switch missing default"),
        "C11": (check_c11, "AUTO", "assert() banned"),
        "C21": (check_c21, "AUTO", "unbounded string ops (strcpy/strcat/gets)"),
        "C13": (check_c13, "HEUR", "unused static function"),
        "C14": (check_c14, "HEUR", "error path without hal_log"),
        "C15": (check_c15, "HEUR", "fopen/fclose balance"),
        "C22": (check_c22, "AUTO", "INT_MIN negation of signed int"),
        "C23": (check_c23, "AUTO", "double free without NULL reset"),
        "C24": (check_c24, "AUTO", "memcpy size vs dest array"),
        "C25": (check_c25, "HEUR", "use-after-free candidate"),
    }