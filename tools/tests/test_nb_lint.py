"""Regression tests for nb_validator V1-V4 (devdoc 104).

Covers: var bounds vs variables.json, question segment deep check, delay
positive-only, unknown command / asset checks, and the accepted-list
mechanism (nb_lint_accepted.txt).
"""

import json
import sqlite3

from naiz_build import nb_validator as nv

VAR_BOND = [{"id": "bond", "name": "Bond", "desc": "", "initial": 0,
             "min": 0, "max": 100}]


def make_project(tmp_path, variables=None, accepted=None, extra_img=()):
    """Create a minimal project: ASSETS.DB + variables.json + scene/*.nb."""
    db = sqlite3.connect(str(tmp_path / "ASSETS.DB"))
    db.execute("CREATE TABLE img_map (name TEXT, type TEXT)")
    db.executemany("INSERT INTO img_map VALUES (?, ?)",
                   [("fond", "IMG"), ("anim1", "ANI")] + list(extra_img))
    db.commit()
    db.close()
    if variables is not None:
        (tmp_path / "variables.json").write_text(
            json.dumps({"variables": variables}), encoding="utf-8")
    if accepted is not None:
        (tmp_path / "nb_lint_accepted.txt").write_text(accepted, encoding="utf-8")
    (tmp_path / "scene").mkdir()
    return tmp_path


def write_script(proj, name, content):
    p = proj / "scene" / f"{name}.nb"
    p.write_text(content, encoding="utf-8")
    return p


def errs_of(proj, nb_path):
    ref = nv.load_reference(str(proj))
    return nv.validate_scene(nb_path, ref)


def test_var_set_in_bounds_ok(tmp_path):
    proj = make_project(tmp_path, VAR_BOND)
    nb = write_script(proj, "t001", "var(bond,=,50)\nvar(bond,+,30)\n")
    assert errs_of(proj, nb) == []


def test_var_set_out_of_bounds_red(tmp_path):
    proj = make_project(tmp_path, VAR_BOND)
    nb = write_script(proj, "t001", "var(bond,=,101)\n")
    errs = errs_of(proj, nb)
    assert len(errs) == 1
    assert "out of bounds" in errs[0]


def test_var_delta_initial_negative_red(tmp_path):
    proj = make_project(tmp_path, VAR_BOND)
    nb = write_script(proj, "t001", "var(bond,-,1)\n")
    errs = errs_of(proj, nb)
    assert len(errs) == 1
    assert "out of bounds" in errs[0]


def test_var_unknown_id_red(tmp_path):
    proj = make_project(tmp_path, VAR_BOND)
    nb = write_script(proj, "t001", "var(ghost,=,1)\n")
    errs = errs_of(proj, nb)
    assert len(errs) == 1
    assert "not in variables.json" in errs[0]


def test_var_bad_op_red(tmp_path):
    proj = make_project(tmp_path, VAR_BOND)
    nb = write_script(proj, "t001", "var(bond,*,1)\n")
    errs = errs_of(proj, nb)
    assert len(errs) == 1
    assert "op=" in errs[0]


def test_var_non_numeric_delta_red(tmp_path):
    proj = make_project(tmp_path, VAR_BOND)
    nb = write_script(proj, "t001", "var(bond,+,abc)\n")
    errs = errs_of(proj, nb)
    assert len(errs) == 1
    assert "not a numeric literal" in errs[0]


def test_var_checks_skipped_without_table(tmp_path):
    proj = make_project(tmp_path, None)
    nb = write_script(proj, "t001", "var(bond,+,50)\nvar(ghost,=,1)\n")
    assert errs_of(proj, nb) == []


def test_question_valid_ok(tmp_path):
    proj = make_project(tmp_path, VAR_BOND)
    nb = write_script(proj, "t001",
                      "question(Go?;Yes,bond,+,1;No,bond,+,1)\n")
    assert errs_of(proj, nb) == []


def test_question_missing_delta_red(tmp_path):
    proj = make_project(tmp_path, VAR_BOND)
    nb = write_script(proj, "t001", "question(Prompt;A,bond,+)\n")
    errs = errs_of(proj, nb)
    assert len(errs) == 1
    assert "needs 'label,var,op,delta'" in errs[0]


def test_question_bad_op_red(tmp_path):
    proj = make_project(tmp_path, VAR_BOND)
    nb = write_script(proj, "t001", "question(Prompt;A,bond,x,1)\n")
    errs = errs_of(proj, nb)
    assert len(errs) == 1
    assert "op=x not in =/+/ -" in errs[0]


def test_question_unknown_var_red(tmp_path):
    proj = make_project(tmp_path, VAR_BOND)
    nb = write_script(proj, "t001", "question(Prompt;A,ghost,+,1)\n")
    errs = errs_of(proj, nb)
    assert len(errs) == 1
    assert "question: var[ghost] not in variables.json" in errs[0]


def test_question_too_many_options_red(tmp_path):
    proj = make_project(tmp_path, VAR_BOND)
    opts = ";".join(f"O{i},bond,+,1" for i in range(1, 12))
    nb = write_script(proj, "t001", f"question(Prompt;{opts})\n")
    errs = errs_of(proj, nb)
    assert len(errs) == 1
    assert "option count" in errs[0]


def test_question_empty_prompt_red(tmp_path):
    proj = make_project(tmp_path, VAR_BOND)
    nb = write_script(proj, "t001", "question(;A,bond,+,1)\n")
    errs = errs_of(proj, nb)
    assert len(errs) == 1
    assert "prompt must be non-empty" in errs[0]


def test_delay_positive_ok(tmp_path):
    proj = make_project(tmp_path, None)
    nb = write_script(proj, "t001", "delay(0.5)\n")
    assert errs_of(proj, nb) == []


def test_delay_nonpositive_red(tmp_path):
    proj = make_project(tmp_path, None)
    for txt, bad in [("delay(0)\n", "0"), ("delay(-1)\n", "-1"),
                     ("delay(abc)\n", "abc")]:
        nb = write_script(proj, "t001", txt)
        errs = errs_of(proj, nb)
        assert len(errs) == 1, txt
        assert "must be a positive number" in errs[0], txt
        assert bad in errs[0]


def test_unknown_command_red(tmp_path):
    proj = make_project(tmp_path, None)
    nb = write_script(proj, "t001", "frobnicate(1)\n")
    errs = errs_of(proj, nb)
    assert len(errs) == 1
    assert "unknown command 'frobnicate'" in errs[0]


def test_unknown_asset_red(tmp_path):
    proj = make_project(tmp_path, None)
    nb = write_script(proj, "t001", "bg(){ghost_id}\n")
    errs = errs_of(proj, nb)
    assert len(errs) == 1
    assert "not in img_map" in errs[0]


def test_accepted_filter_exempts_but_reports(tmp_path):
    proj = make_project(tmp_path, VAR_BOND,
                        accepted="t001:1|var(bond,=,101)\n")
    nb = write_script(proj, "t001", "var(bond,=,101)\n")
    errs = errs_of(proj, nb)
    assert len(errs) == 1  # validate_scene itself still reports it
    acc = nv.load_accepted(str(proj))
    kept, hits = nv.filter_accepted(errs, nb, acc)
    assert kept == []
    assert len(hits) == 1
    assert "var[bond]" in hits[0]


def test_accepted_pattern_mismatch_not_exempted(tmp_path):
    proj = make_project(tmp_path, VAR_BOND,
                        accepted="t001:1|nomatch\n")
    nb = write_script(proj, "t001", "var(bond,=,101)\n")
    errs = errs_of(proj, nb)
    acc = nv.load_accepted(str(proj))
    kept, hits = nv.filter_accepted(errs, nb, acc)
    assert len(kept) == 1
    assert hits == []


def test_validate_project_counts_exit_after_accepted(tmp_path):
    proj = make_project(tmp_path, VAR_BOND, accepted="t001:1|var\n")
    write_script(proj, "t001", "var(bond,=,101)\n")
    assert nv.validate_project(str(proj)) == 0