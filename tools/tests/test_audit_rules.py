"""tools.audit: rule checkers and git-aware incremental state."""

import json
import subprocess

import pytest

from tools.audit import audit, state, verify
from tools.audit.rules_c import (check_c1, check_c4, check_c5, check_c11,
                                 check_c14, check_c21, check_c22, check_c23,
                                 check_c24, check_c25)
from tools.audit.rules_p import (check_p1, check_p2, check_p3, check_p5,
                                 check_p6, check_p7, check_p8, check_p9,
                                 check_p10, check_p14)
from tools.audit.rules_s import check_s2


def _hits(fn, text):
    return list(fn(text, "<mem>"))


# ---------------------------------------------------------------------------
# rule checkers: positive / negative samples
# ---------------------------------------------------------------------------

def test_c5_sprintf_detected_snprintf_not():
    assert len(_hits(check_c5, "void f(){ sprintf(a,\"%d\",1); }")) == 1
    assert len(_hits(check_c5, "void f(){ snprintf(a,8,\"%d\",1); }")) == 0


def test_c11_assert_detected():
    assert len(_hits(check_c11, "void f(){ assert(x > 0); }")) == 1
    assert len(_hits(check_c11, "void f(){ }")) == 0


def test_c1_malloc_null_check():
    guarded = "void f(){ char *p = malloc(16); if (p == NULL) return; }"
    unguarded = "void f(){ char *p = malloc(16); p[0] = 1; }"
    assert _hits(check_c1, guarded) == []
    assert len(_hits(check_c1, unguarded)) == 1


def test_p1_bare_except_detected():
    text = ("try:\n"
            "    x()\n"
            "except:\n"
            "    pass\n"
            "try:\n"
            "    y()\n"
            "except OSError as e:\n"
            "    pass\n")
    hits = _hits(check_p1, text)
    assert len(hits) == 1
    assert hits[0][0] == 3


def test_p7_shell_true_detected():
    text = "subprocess.run(cmd, shell=True)"
    assert len(_hits(check_p7, text)) == 1
    assert _hits(check_p7, "subprocess.run([\"ls\"])") == []


def test_s2_eval_detected():
    assert len(_hits(check_s2, "eval \"$x\"")) == 1
    assert len(_hits(check_s2, "echo ok")) == 0


# ---------------------------------------------------------------------------
# AST C-window rules: positive / negative samples
# ---------------------------------------------------------------------------

def test_c1_grouped_and_delayed():
    grouped = ("void f(){ char *a = calloc(1, 8); char *b = calloc(1, 8);"
               " if (!a || !b) { free(a); free(b); return; } }")
    embedded = ("void f(){ if ((p = malloc(8)) == NULL) return; }")
    delayed = ("void f(){ char *a = malloc(8); g(); g(); g(); g();"
               " if (!a) return; }")
    assert _hits(check_c1, grouped) == []
    assert _hits(check_c1, embedded) == []
    assert len(_hits(check_c1, delayed)) == 1


def test_c4_member_chain_terminator():
    ok = ("void f(){ strncpy(cfg.name, s, sizeof(cfg.name) - 1);"
          " cfg.name[sizeof(cfg.name) - 1] = '\\0'; }")
    ok_dot = ("void f(){ strncpy(nb.chapter_title, s,"
              " sizeof(nb.chapter_title) - 1); "
              "nb.chapter_title[sizeof(nb.chapter_title) - 1] = '\\0'; }")
    bad = "void f(){ char b[16]; strncpy(b, s, 15); }"
    assert _hits(check_c4, ok) == []
    assert _hits(check_c4, ok_dot) == []
    assert len(_hits(check_c4, bad)) == 1


def test_c14_consistent_logging_only():
    logs = ("static int f(void){ if (x) { hal_log(\"a\"); return 0; }\n"
            "  if (y) { return -1; }\n  return 0; }")
    silent = ("static int g(void){ if (x) { return -1; }\n  return 0; }")
    assert len(_hits(check_c14, logs)) == 1
    assert _hits(check_c14, silent) == []


def test_c21_unbounded_string_ops():
    assert len(_hits(check_c21,
                     "void f(){ strcpy(a, b); strcat(a, b); }")) == 2
    assert len(_hits(check_c21,
                     "void f(){ gets(buf); }")) == 1
    assert _hits(check_c21, "void f(){ snprintf(a, 8, \"%s\", b); }") == []


# ---------------------------------------------------------------------------
# Tier-2 deterministic rules: C22 INT_MIN, C23 double-free, C24 memcpy size,
# C25 use-after-free
# ---------------------------------------------------------------------------

def test_c22_intmin_negation():
    assert len(_hits(check_c22,
                     "void f(){ int val = g(); int d = -val; }")) == 1
    assert len(_hits(check_c22,
                     "void f(){ int val = g(); int d = 0 - val; }")) == 1
    assert _hits(check_c22,
                 "void f(){ int val = g(); int d = x - val; }") == []
    assert _hits(check_c22,
                 "void f(){ int val = g(); int d = a[i] - val; }") == []
    assert _hits(check_c22, "void f(){ int val = g(); val--; }") == []
    # The canonical safe form is exempt.
    assert _hits(check_c22,
                 "void f(){ int val = g();"
                 " int d = (val == INT_MIN) ? INT_MIN : -val; }") == []
    assert _hits(check_c22, "void f(int val){ int d = -val; }") == []


def test_c23_double_free_only_same_path():
    assert len(_hits(check_c23,
                     "void f(){ void *p = malloc(4); free(p); free(p); }")) == 1
    assert _hits(check_c23,
                 "void f(){ void *p = malloc(4); free(p); p = NULL;"
                 " free(p); }") == []
    assert _hits(check_c23,
                 "void f(){ if (x) { free(p); return 1; } free(p);"
                 " return 0; }") == []
    assert _hits(check_c23,
                 "void f(){ void *a = calloc(1,4); void *b = calloc(1,4);"
                 " if (!a || !b) { free(a); free(b); return 1; }"
                 " free(a); free(b); return 0; }") == []


def test_c24_memcpy_size_crosscheck():
    assert len(_hits(check_c24,
                     "void f(){ char a[8]; memcpy(a, b, 16); }")) == 1
    assert len(_hits(check_c24,
                     "void f(){ char a[8]; char b[32];"
                     " memcpy(a, b, sizeof(b)); }")) == 1
    assert _hits(check_c24, "void f(){ char a[8]; memcpy(a, b, sizeof(a)); }") == []
    assert _hits(check_c24, "void f(){ char a[8]; memcpy(a, b, 8); }") == []
    # pointer / unknown-size targets stay with the C9 heuristic
    assert _hits(check_c24,
                 "void f(){ void *p; memcpy(p, b, sizeof(b)); }") == []


def test_c25_use_after_free_same_block():
    assert len(_hits(check_c25,
                     "void f(){ void *p = malloc(4); free(p); p->x = 1; }")) == 1
    assert len(_hits(check_c25,
                     "void f(){ void *p = malloc(4); free(p); p[0] = 1; }")) == 1
    assert _hits(check_c25,
                 "void f(){ void *p = malloc(4); free(p);"
                 " p = malloc(8); p->x = 1; }") == []
    assert _hits(check_c25,
                 "void f(){ if (!p) { free(p); return 1; } p->x = 1; }") == []


# ---------------------------------------------------------------------------
# AST Python rules: positive / negative samples
# ---------------------------------------------------------------------------

def test_p2_with_ownership():
    ok = 'with open("a.txt") as f:\n    data = f.read()\n'
    leak = 'f = open("a.txt")\ndata = f.read()\nf.close()\n'
    assert _hits(check_p2, ok) == []
    assert len(_hits(check_p2, leak)) == 1


def test_p3_assert_detected():
    assert len(_hits(check_p3, "assert x == 1\n")) == 1
    assert _hits(check_p3, "x = 1\n") == []


def test_p5_read_length_check():
    ok = "data = f.read(100)\nif len(data) != 100:\n    raise OSError('x')\n"
    bad = "data = f.read(100)\n"
    assert _hits(check_p5, ok) == []
    assert len(_hits(check_p5, bad)) == 1


def test_p6_path_concat_direct_and_tracked():
    direct = 'with open("/x/" + name + ".dat", "wb") as f: pass\n'
    tracked = ('p = "/x/" + name + ".dat"\n'
               'with open(p, "wb") as f: pass\n')
    regex_ok = 'RE = re.compile(r"^" + TOK + r"*")\n'
    assert len(_hits(check_p6, direct)) == 1
    assert len(_hits(check_p6, tracked)) == 1
    assert _hits(check_p6, regex_ok) == []


def test_p8_function_body_import():
    bad = "def f():\n    import os\n    return os.sep\n"
    top = "import os\n\ndef f():\n    return os.sep\n"
    assert len(_hits(check_p8, bad)) == 1
    assert _hits(check_p8, top) == []


def test_p9_mutable_default():
    assert len(_hits(check_p9, "def f(x=[]):\n    pass\n")) == 1
    assert _hits(check_p9, "def f(x=None):\n    pass\n") == []


def test_p10_sys_exit_string():
    assert len(_hits(check_p10, "import sys\nsys.exit('done')\n")) == 1
    assert _hits(check_p10, "import sys\nsys.exit(1)\n") == []


def test_p14_dynamic_exec_detected():
    assert len(_hits(check_p14, "os.system(cmd)\n")) == 1
    assert len(_hits(check_p14, "exec(code)\n")) == 1
    assert _hits(check_p14, "subprocess.run(args)\n") == []


# ---------------------------------------------------------------------------
# verify notes (independent verify_notes.json)
# ---------------------------------------------------------------------------

def test_verify_roundtrip_and_stale(tmp_path):
    assert not verify.verify_path(tmp_path).exists()
    vp, note = verify.add(tmp_path, "core/engine/a.c:43", "ok", "benign")
    assert vp.is_file()
    notes = verify.load(tmp_path)
    assert notes["core/engine/a.c:43"]["verdict"] == "ok"
    assert "date" in notes["core/engine/a.c:43"]
    assert "sha256" in notes["core/engine/a.c:43"]
    assert verify.note_for(notes, "core/engine/a.c", 43)["verdict"] == "ok"
    assert verify.note_for(notes, "core/engine/a.c", 44) is None
    bad = verify.load(tmp_path)["core/engine/a.c:43"]
    with pytest.raises(ValueError):
        verify.add(tmp_path, "x:1", "bogus", "")


def test_audit_annotates_verified(tmp_path, capsys):
    _write(tmp_path / "core/engine/leaky.c",
           'void f(){ char *p = malloc(8); p[0] = 1; }\n')
    verify.add(tmp_path, "core/engine/leaky.c:1", "ok", "embedded, OOM ignored")
    out = capsys.readouterr().out
    rc = audit.run_audit(root=tmp_path, reset=True, save_state=False,
                         manual=False)
    printed = capsys.readouterr().out
    assert rc == 0
    assert "[verified-ok]" in printed
    assert "1 verified" in printed


# ---------------------------------------------------------------------------
# verify CLI --note parsing
# ---------------------------------------------------------------------------

def test_cli_note_inline_specs(tmp_path, monkeypatch):
    from tools.audit import audit, verify
    monkeypatch.setattr(verify, "project_root", lambda: tmp_path)
    rc = audit.main(["--note", "core/engine/a.c:43:ok:text one",
                     "--note", "core/engine/b.c:7:fixed:fixme here"])
    assert rc == 0
    notes = verify.load(tmp_path)
    assert notes["core/engine/a.c:43"]["verdict"] == "ok"
    assert notes["core/engine/a.c:43"]["text"] == "text one"
    assert notes["core/engine/b.c:7"]["verdict"] == "fixed"
    assert notes["core/engine/b.c:7"]["text"] == "fixme here"


def test_cli_note_colon_in_text_kept():
    from tools.audit import audit
    specs = audit.parse_note_specs(["core/engine/a.c:3:ok:note says 'a:b'"])
    assert specs == [("core/engine/a.c:3", "ok", "note says 'a:b'")]


def test_cli_note_bare_single_fallback():
    from tools.audit import audit
    specs = audit.parse_note_specs(["core/engine/a.c:3"], verdict="ok",
                                   text="legacy mode")
    assert specs == [("core/engine/a.c:3", "ok", "legacy mode")]


def test_cli_note_multi_bare_rejected():
    from tools.audit import audit
    with pytest.raises(ValueError, match="single --note"):
        audit.parse_note_specs(["a:1", "b:2"], verdict="ok")


def test_cli_note_bare_without_verdict_rejected():
    from tools.audit import audit
    with pytest.raises(ValueError, match="requires --verdict"):
        audit.parse_note_specs(["a:1"])


def test_cli_note_bad_verdict_rejected():
    from tools.audit import audit
    with pytest.raises(ValueError, match="verdict must be one of"):
        audit.parse_note_specs(["a:1:noop"])


def test_cli_note_malformed_rejected():
    from tools.audit import audit
    with pytest.raises(ValueError, match="REL:LINENO"):
        audit.parse_note_specs(["core/engine/a.c"])


def test_verify_line_level_stale(tmp_path):
    from tools.audit import verify
    p = tmp_path / "core/engine/a.c"
    _write(p, 'void f(void){ char b[4]; sprintf(b, "%d", 1); }\n')
    vp, note = verify.add(tmp_path, "core/engine/a.c:1", "ok", "benign")
    assert note["line"] == 'void f(void){ char b[4]; sprintf(b, "%d", 1); }'
    assert verify.fresh(tmp_path, "core/engine/a.c:1", note)
    # Unrelated edit elsewhere in the file must NOT stale the note.
    _write(p, 'void f(void){ char b[4]; sprintf(b, "%d", 1); }\n// extra\n')
    assert verify.fresh(tmp_path, "core/engine/a.c:1", note)
    # Editing the flagged line itself stales it.
    _write(p, 'void f(void){ char b[8]; sprintf(b, "%d", 1); }\n')
    assert not verify.fresh(tmp_path, "core/engine/a.c:1", note)


def test_verify_v1_fallback_sha(tmp_path):
    from tools.audit import verify
    p = tmp_path / "core/engine/a.c"
    _write(p, 'void f(void){ char b[4]; sprintf(b, "%d", 1); }\n')
    note = {"verdict": "ok", "text": "", "date": "",
            "sha256": verify.sha256_of(p)}
    assert verify.fresh(tmp_path, "core/engine/a.c:1", note)
    _write(p, 'void f(void){ char b[4]; sprintf(b, "%d", 2); }\n')
    assert not verify.fresh(tmp_path, "core/engine/a.c:1", note)


def test_verify_accepts_legacy_v1_file(tmp_path):
    from tools.audit import verify
    verify.verify_path(tmp_path).write_text(
        json.dumps({"version": 1, "notes": {"a.c:1": {"verdict": "ok"}}}),
        encoding="utf-8")
    notes = verify.load(tmp_path)
    assert notes["a.c:1"]["verdict"] == "ok"


def _git(root, *args):
    r = subprocess.run(["git", "-C", str(root)] + list(args),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r


def test_since_gates_uncommitted_violations(tmp_path, capsys):
    from tools.audit import audit
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "audit@test")
    _git(tmp_path, "config", "user.name", "audit")
    _write(tmp_path / "core/engine/a.c",
           'void f(void){ char b[16]; snprintf(b, 16, "x"); }\n')
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    assert audit.run_audit(root=tmp_path, since="HEAD", save_state=False,
                           manual=False) == 0
    capsys.readouterr()
    _write(tmp_path / "core/engine/a.c",
           'void f(void){ char b[16]; sprintf(b, "%d", 1); }\n')
    rc = audit.run_audit(root=tmp_path, since="HEAD", save_state=False,
                         manual=False)
    printed = capsys.readouterr().out
    assert rc == 1
    assert "changed-lines=1" in printed
    assert "core/engine/a.c:1 -- C5/AUTO" in printed


def test_since_carries_previous_state(tmp_path):
    from tools.audit import audit, state
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "audit@test")
    _git(tmp_path, "config", "user.name", "audit")
    _write(tmp_path / "core/engine/a.c",
           'void f(void){ char b[16]; sprintf(b, "%d", 1); }\n')
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    assert audit.run_audit(root=tmp_path, reset=True, save_state=True,
                           manual=False) == 1
    assert state.load(tmp_path)["files"]["core/engine/a.c"]["violations"] == 1
    # since=HEAD (no new lines): file is out of scope, prior state carried.
    rc = audit.run_audit(root=tmp_path, since="HEAD", save_state=True,
                         manual=False)
    assert rc == 0
    st = state.load(tmp_path)
    assert "core/engine/a.c" in st["files"]
    assert st["files"]["core/engine/a.c"]["violations"] == 1, \
        "out-of-scope files must carry prior records"
    assert st["summary"]["changed"] == 0


# ---------------------------------------------------------------------------
# incremental state + exit codes
# ---------------------------------------------------------------------------

def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_tree(tmp):
    _write(tmp / "core/engine/bad.c",
           'void bad(void){ char b[4]; sprintf(b,"%d",1); }\n')
    _write(tmp / "core/engine/ok.c",
           'void ok(void){ char b[32]; snprintf(b,32,"x"); }\n')
    _write(tmp / "tools/clean.py",
           'import os\n\ndef f():\n    return os.path.join(os.environ["HOME"], "x")\n')
    _write(tmp / "makegame.sh",
           '#!/bin/bash\nset -euo pipefail\necho ok\n')


def test_full_run_exit_and_incremental_skip(tmp_path, capsys):
    _seed_tree(tmp_path)

    # First run (no state): bad.c sprintf is a deterministic AUTO violation.
    rc = audit.run_audit(root=tmp_path, reset=True, save_state=True,
                         manual=False)
    assert rc == 1
    st = state.load(tmp_path)
    assert st is not None and st["version"] == 2
    assert "core/engine/bad.c" in st["files"]
    assert st["files"]["core/engine/bad.c"]["violations"] >= 1
    assert st["summary"]["skipped"] == 0
    assert st["summary"]["changed"] == 4

    # Second run unchanged: everything skipped, no violations, rc 0.
    capsys.readouterr()
    rc2 = audit.run_audit(root=tmp_path, reset=False, save_state=True,
                          manual=False)
    out2 = capsys.readouterr().out
    assert rc2 == 0
    assert state.load(tmp_path)["summary"]["skipped"] == 4

    # Touch ok.c only: it is rechecked (changed), bad.c stays skipped, rc 0.
    _write(tmp_path / "core/engine/ok.c", 'void ok(void){ char b[32]; snprintf(b,32,"y"); }\n')
    capsys.readouterr()
    rc3 = audit.run_audit(root=tmp_path, reset=False, save_state=True,
                          manual=False)
    out3 = capsys.readouterr().out
    assert rc3 == 0
    assert "changed=1 skipped=3" in out3


def test_no_save_leaves_state_untouched(tmp_path):
    _seed_tree(tmp_path)
    assert not state.state_path(tmp_path).exists()
    audit.run_audit(root=tmp_path, reset=True, save_state=False, manual=False)
    assert not state.state_path(tmp_path).exists()


def test_incremental_carries_candidate_counts(tmp_path, capsys):
    _write(tmp_path / "core/engine/leaky2.c",
           'void f(){ char *p = malloc(8); p[0] = 1; }\n')
    rc = audit.run_audit(root=tmp_path, reset=True, save_state=True,
                         manual=False)
    assert rc == 0
    assert state.load(tmp_path)["summary"]["candidates"] == 1
    capsys.readouterr()
    audit.run_audit(root=tmp_path, reset=False, save_state=True, manual=False)
    capsys.readouterr()
    st2 = state.load(tmp_path)
    assert st2["summary"]["candidates"] == 1, \
        "incremental run must carry prior candidate counts"
    assert st2["summary"]["changed"] == 0


def test_reset_reruns_everything(tmp_path):
    _seed_tree(tmp_path)
    audit.run_audit(root=tmp_path, reset=True, save_state=True, manual=False)
    st = state.load(tmp_path)
    assert st["summary"]["changed"] == 4
    # Same content but forced reset -> full re-run again.
    audit.run_audit(root=tmp_path, reset=True, save_state=True, manual=False)
    assert state.load(tmp_path)["summary"]["changed"] == 4