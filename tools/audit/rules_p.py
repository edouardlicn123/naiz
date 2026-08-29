"""Python anti-regression rules (AGENTS section 17, P1-P14).

AUTO rules are deterministic; HEUR rules emit candidates for confirmation.

All checkers operate on the real Python AST (ast.parse) instead of regular
expressions, so comments/strings can never be mistaken for code and
multi-line constructs are handled exactly.
"""

import ast
import re

# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

_PATH_CALLER_NAMES = {"open", "os.path.join", "join", "Path", "io.open"}

# (func_node) -> True when the called function is a known path consumer
def _is_path_call(node):
    if isinstance(node, ast.Name):
        return node.id in ("open", "Path", "join")
    if isinstance(node, ast.Attribute):
        dotted = _dotted_name(node)
        return dotted in ("os.path.join", "io.open")
    return False


def _dotted_name(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _parent_map(tree):
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _ancestor_chain(parents, node):
    chain = []
    cur = node
    while cur in parents:
        cur = parents[cur]
        chain.append(cur)
    return chain


def _inside_context_expr(node, tree):
    """True when node appears inside the context_expr of some ast.With.

    'with open(..) as f:' owns its open() call; any other open() is not tied
    to a context manager and is reportable.
    """
    for w in ast.walk(tree):
        if isinstance(w, ast.With):
            for item in w.items:
                ctx = item.context_expr
                if ctx is node or (isinstance(ctx, ast.Call)
                                   and _subtree_contains(ctx, node)):
                    return True
    return False


def _subtree_contains(root, target):
    return target is root or any(_subtree_contains(c, target)
                                for c in ast.iter_child_nodes(root))


def _has_str_operand(node):
    """True when a BinOp's subtree contains a string constant (incl. f-strings)."""
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            return True
        if isinstance(n, ast.JoinedStr):
            return True
    return False


def _func_body_of(parents, tree, node):
    """Return the statement list whose node is a member (else None)."""
    body = getattr(tree, "body", None)
    if isinstance(body, list) and node in body:
        return body
    p = parents.get(node)
    while p is not None:
        b = getattr(p, "body", None)
        if isinstance(b, list) and node in b:
            return b
        node = p
        p = parents.get(node)
    return None


def _next_siblings(body, node, limit=6):
    try:
        idx = body.index(node)
    except ValueError:
        return []
    return body[idx + 1:idx + 1 + limit]


# ---------------------------------------------------------------------------
# P1 bare except
# ---------------------------------------------------------------------------


def check_p1(text, _path):
    tree = ast.parse(text)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            out.append((node.lineno, "bare except: must specify exception type"))
    return out


# ---------------------------------------------------------------------------
# P2 open() must use with / ownership confirmed
# ---------------------------------------------------------------------------


def check_p2(text, _path):
    tree = ast.parse(text)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        ok = (isinstance(func, ast.Name) and func.id == "open") or \
             (isinstance(func, ast.Attribute) and func.attr == "open"
              and _dotted_name(func) in ("io.open", "os.open"))
        if not ok:
            continue
        if _inside_context_expr(node, tree):
            continue
        out.append((node.lineno,
                    "open( without 'with' context ownership (confirm manual close)"))
    return out


# ---------------------------------------------------------------------------
# P3 assert banned in production code
# ---------------------------------------------------------------------------


def check_p3(text, _path):
    tree = ast.parse(text)
    return [(node.lineno, "assert used; convert to explicit raise")
            for node in ast.walk(tree) if isinstance(node, ast.Assert)]


# ---------------------------------------------------------------------------
# P5 binary read length validation
# ---------------------------------------------------------------------------


def check_p5(text, _path):
    tree = ast.parse(text)
    parents = _parent_map(tree)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute)
                and node.func.attr == "read" and node.args):
            continue
        num = node.args[0]
        if not (isinstance(num, ast.Constant)
                and isinstance(num.value, int)):
            continue
        # find the variable this read result is assigned to, if any
        var = None
        stmt = node
        if isinstance(parents.get(node), ast.Assign):
            stmt = parents[node]
            for t in stmt.targets:
                if isinstance(t, ast.Name):
                    var = t.id
                    break
        body = _func_body_of(parents, tree, stmt)
        satisfied = False
        for sib in _next_siblings(body, stmt):
            seg = ast.get_source_segment(text, sib)
            if var:
                if re.search(r"\blen\s*\(\s*" + re.escape(var) + r"\s*\)",
                             seg or ""):
                    satisfied = True
                    break
                if re.search(r"\b" + re.escape(var) + r"\b"
                             r"\s*(?:==|!=|<=|>=|<|>)\s*" +
                             str(num.value) + r"\b", seg or ""):
                    satisfied = True
                    break
            if seg and ("raise " in seg or "assert " in seg):
                satisfied = True
                break
        if not satisfied:
            out.append((node.lineno, "read(n) without a length check "
                                     "in the following statements"))
    return out


# ---------------------------------------------------------------------------
# P6 path built by string concatenation (incl. assignment tracking)
# ---------------------------------------------------------------------------


def check_p6(text, _path):
    tree = ast.parse(text)
    parents = _parent_map(tree)
    out = []
    used = set()
    reported_calls = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Add):
            continue
        if not _has_str_operand(node):
            continue
        if id(node) in used:
            continue

        chain = _ancestor_chain(parents, node)
        path_call = None
        for anc in chain:
            if isinstance(anc, ast.Call):
                path_call = anc
                break

        # direct use as an argument of a path-consuming call (dedupe per call)
        if path_call is not None and _is_path_call(path_call.func):
            if id(path_call) not in reported_calls:
                reported_calls.add(id(path_call))
                out.append((path_call.lineno,
                            "path built by '+' string concatenation into "
                            "a path call (use Path/join)"))
            for n in ast.walk(path_call):
                if isinstance(n, ast.BinOp):
                    used.add(id(n))
            continue

        # assignment tracking: str-concat result assigned, then fed to a
        # path call later in the same statement list
        assign = parents.get(node)
        if isinstance(assign, ast.Assign):
            targets = [t.id for t in assign.targets if isinstance(t, ast.Name)]
            body = _func_body_of(parents, tree, assign)
            for sib in (body or []):
                for sub in ast.walk(sib):
                    if (isinstance(sub, ast.Call)
                            and _is_path_call(sub.func)):
                        for arg in sub.args:
                            if (isinstance(arg, ast.Name)
                                    and arg.id in targets):
                                used.add(id(node))
                                out.append((node.lineno,
                                            "path from '+' concatenation "
                                            "later opened (use Path/join)"))
                                break
    return out


# ---------------------------------------------------------------------------
# P7 no shell=True
# ---------------------------------------------------------------------------


def check_p7(text, _path):
    tree = ast.parse(text)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) \
                    and kw.value.value is True:
                out.append((node.lineno,
                            "subprocess shell=True; use list argv"))
    return out


# ---------------------------------------------------------------------------
# P8 no function-body imports (aggregated per file to limit noise)
# ---------------------------------------------------------------------------


def check_p8(text, _path):
    tree = ast.parse(text)
    parents = _parent_map(tree)
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for anc in _ancestor_chain(parents, node):
            if isinstance(anc, (ast.FunctionDef, ast.AsyncFunctionDef,
                                ast.ClassDef)):
                hits.append((node.lineno, ast.get_source_segment(text, node)
                             or "import"))
                break
    if not hits:
        return []
    first = hits[0]
    note = f"{len(hits)} function-body import(s);"
    note += " move to module top unless an intentionally lazy optional dep"
    return [(first[0], note)]


# ---------------------------------------------------------------------------
# P9 no mutable default arguments
# ---------------------------------------------------------------------------


def check_p9(text, _path):
    tree = ast.parse(text)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for default in node.args.defaults + node.args.kw_defaults:
            if default is None:
                continue
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                out.append((node.lineno, "mutable default argument ([] or {})"))
                break
    return out


# ---------------------------------------------------------------------------
# P10 sys.exit with string message
# ---------------------------------------------------------------------------


def check_p10(text, _path):
    tree = ast.parse(text)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "exit"
                and isinstance(func.value, ast.Name)
                and func.value.id == "sys"):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, (ast.Constant, ast.JoinedStr)) and \
                isinstance(getattr(arg, "value", None), str):
            out.append((node.lineno,
                        "sys.exit('...') should print(...) then sys.exit(1)"))
    return out


# ---------------------------------------------------------------------------
# P14 dynamic code execution / shell escaping (AUTO)
# ---------------------------------------------------------------------------


def _is_dynamic_exec(node):
    """True for eval/exec calls and os.system/os.popen shell escapes.

    subprocess.Popen is intentionally excluded: with a list argv (and no
    shell=True, which P7 already rejects) it is the safe invocation form.
    """
    if isinstance(node.func, ast.Name):
        return node.func.id in ("eval", "exec")
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    dotted = _dotted_name(func)
    return dotted in ("os.system", "os.popen")


def check_p14(text, _path):
    tree = ast.parse(text)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_dynamic_exec(node):
            continue
        fname = _dotted_name(node.func) if isinstance(node.func, ast.Attribute) \
            else node.func.id
        out.append((node.lineno,
                    f"{fname}() rejected: dynamic code / shell escape"))
    return out


# ---------------------------------------------------------------------------
# MANUAL review hints (P4 struct bounds, P11 cursor propagation)
# ---------------------------------------------------------------------------

MANUAL_NOTES = {
    "P4": "struct.pack/unpack offsets: verify offset+size never exceeds the "
          "buffer (d88.py/raw.py/nhd.py/mag_codec.py/fat_fs.py).",
    "P11": "Mutable cursors (next_free/alloc_next_free) must be returned to "
          "the caller; re-check fat_table.py/inject_common.py.",
}


def registry():
    return {
        "P1": (check_p1, "AUTO", "bare except"),
        "P2": (check_p2, "HEUR", "open without with"),
        "P3": (check_p3, "AUTO", "assert banned"),
        "P5": (check_p5, "HEUR", "read length validation"),
        "P6": (check_p6, "HEUR", "path concatenation"),
        "P7": (check_p7, "AUTO", "subprocess shell=True"),
        "P8": (check_p8, "HEUR", "function-body imports"),
        "P9": (check_p9, "AUTO", "mutable default args"),
        "P10": (check_p10, "AUTO", "sys.exit(string)"),
        "P14": (check_p14, "AUTO", "eval/exec/os.system/os.popen"),
    }