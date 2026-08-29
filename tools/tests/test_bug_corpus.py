"""Bug-regression corpus: every documented real bug (R1-R7) must still be
catchable by the current rule set.

Each entry embeds the minimal historical shape of a bug fixed in a previous
round.  If a rule refactor ever loses coverage, these tests fail so the
detector itself cannot silently regress.  This is the anti-regression layer
for the audit rules (as opposed to synthetic positive/negative samples in
test_audit_rules.py).
"""

import pytest

from tools.audit import audit

# (bug_round, rule_id, description, code)
CORPUS = [
    # --- C rules ---
    ("R1", "C1", "mag.c early: unchecked calloc",
     "void f(void){ uint8_t *p = calloc(1, 64); p[0] = 1; }"),
    ("R2", "C2", "nb.c early: fopen result not checked",
     "void f(void){ FILE *fp = fopen(\"x\", \"rb\"); fread(b, 1, 4, fp); }"),
    ("R2", "C3", "fread return value unchecked",
     "void f(void){ fread(buf, 1, n, fp); }"),
    ("R2", "C4", "save.c: strncpy without NUL terminator",
     "void f(void){ char b[16]; strncpy(b, s, 15); }"),
    ("R1", "C5", "historical sprintf use",
     "void f(void){ char b[16]; sprintf(b, \"%d\", 1); }"),
    ("R6", "C7", "save.c hardcoded fseek skip",
     "void f(void){ fseek(f, 20, SEEK_SET); }"),
    ("R6", "C8", "nb_vars: atoi result negated (INT_MIN UB)",
     "int n = atoi(s) - 1;"),
    ("R7", "C8", "nb_commands: negation of signed var (INT_MIN UB)",
     "int d = -val;"),
    ("R6", "C8", "nb_vars: vmax - delta underflow",
     "int nv = vmax - step;"),
    ("R7", "C9", "image.c/tr.c: memcpy size vs target",
     "void f(void){ memcpy(ref_r, p, sizeof(ref_r)); }"),
    ("R4", "C10", "switch without default",
     "void f(void){ switch (c) { case 1: break; } }"),
    ("R4", "C11", "assert() stripped by NDEBUG",
     "void f(void){ assert(x > 0); }"),
    ("R3", "C13", "unused static function",
     "static void helper(void){ }\nvoid f(void){ }"),
    ("R7", "C14", "image.c: silent error return in a logging function",
     "static int load(void){ if (x) { hal_log(\"ok\\r\\n\"); return 0; }\n"
     "  if (y) { return -1; }\n  return 0; }"),
    ("R2", "C15", "fopen without matching fclose",
     "void f(void){ FILE *fp = fopen(\"x\", \"rb\"); fread(b, 1, 4, fp); }"),
    ("R1", "C21", "unbounded strcpy",
     "void f(void){ strcpy(a, b); }"),

    # --- Tier-2 rules (R8: INT_MIN negation missed nb_question in R7) ---
    ("R8", "C22", "nb_question: -opt_deltas[hit] INT_MIN negation",
     "void f(void){ int opt_deltas[10]; nb_var_add(i, -opt_deltas[h]); }"),
    ("R8", "C22", "signed var negation",
     "void f(void){ int val = g(); int d = -val; }"),
    ("R8", "C23", "straight-line double free",
     "void f(void){ void *p = malloc(4); free(p); free(p); }"),
    ("R8", "C24", "memcpy size exceeds destination array",
     "void f(void){ char a[8]; memcpy(a, b, 16); }"),
    ("R8", "C25", "use-after-free dereference",
     "void f(void){ void *p = malloc(4); free(p); p->x = 1; }"),

    # --- P rules ---
    ("R1", "P1", "bare except",
     "try:\n    x()\nexcept:\n    pass\n"),
    ("R2", "P2", "open without with",
     "f = open(\"a.txt\")\ndata = f.read()\nf.close()\n"),
    ("R4", "P3", "assert instead of raise",
     "assert x == 1\n"),
    ("R2", "P5", "fat.py: read without length check",
     "data = f.read(100)\n"),
    ("R6", "P6", "build_game.py: string-concat path",
     "p = \"/x/\" + name + \".dat\"\nwith open(p, \"wb\") as f: pass\n"),
    ("R5", "P7", "env_build: shell=True injection",
     "subprocess.run(cmd, shell=True)\n"),
    ("R4", "P8", "inject_common: function-body import",
     "def f():\n    import os\n    return os.sep\n"),
    ("R4", "P9", "mutable default argument",
     "def f(x=[]):\n    pass\n"),
    ("R5", "P10", "mag_convert: sys.exit(string)",
     "import sys\nsys.exit('done')\n"),
    ("R5", "P14", "os.system dynamic command",
     "os.system(cmd)\n"),

    # --- S rules ---
    ("R5", "S1", "makegame.sh: unquoted $action in case",
     "case $action in\n    1) build ;;\nesac\n"),
    ("R5", "S2", "detect_watcom: eval",
     "eval \"$x\"\n"),
    ("R5", "S3", "which -> command -v",
     "which gcc\n"),
    ("R5", "S4", "readlink -f",
     "readlink -f \"$0\"\n"),
    ("R5", "S5", "makegame.sh: shift without $# guard",
     "#!/bin/bash\nSUB=\"${1:-}\"\nshift\necho \"$SUB\"\n"),
    ("R5", "S6", "for loop over unquoted list",
     "for f in $list\n    do :\n    done\n"),
    ("R6", "S8", "script without set -e",
     "#!/bin/bash\necho ok\n"),
]

IDS = [f"{ref}-{rid}" for ref, rid, _, _ in CORPUS]


def _fire(rule_id, code):
    registry = audit._build_registry()
    func, _level, _desc = registry[rule_id]
    return audit._run_rule(rule_id, func, code, "<corpus>")


@pytest.mark.parametrize("ref,rid,desc,code", CORPUS, ids=IDS)
def test_bug_corpus_still_caught(ref, rid, desc, code):
    hits = _fire(rid, code)
    assert hits, (
        f"[{ref}] {rid} ({desc}) no longer fires — the detector lost "
        f"coverage for this real bug class")


@pytest.mark.parametrize("ref,rid,desc,code", CORPUS, ids=IDS)
def test_bug_corpus_does_not_crash(ref, rid, desc, code):
    registry = audit._build_registry()
    func, _level, _desc = registry[rid]
    # Rule must not raise on corpus input (crash == audit false-negative).
    hits = audit._run_rule(rid, func, code, "<corpus>")
    assert isinstance(hits, list)
    for item in hits:
        assert len(item) == 2
        assert isinstance(item[0], int)
        assert isinstance(item[1], str)
