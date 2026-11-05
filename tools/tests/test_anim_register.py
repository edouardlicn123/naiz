"""anim_register unit tests — bare-name animation asset DB registration.

Covers directory scanning (kind mapping, unrelated-file skipping, stem
validation), full sync semantics: add / update / prune / unchanged,
same-stem png+pal coexistence via the composite primary key, and the
read-only reconciliation entry point diff_project() behind --check
(devdoc 79).
"""

import sqlite3
import sys

import pytest

from naiz_build import anim_project, anim_register
from naiz_build.anim_project import scaffold
from naiz_build.anim_register import diff_project, scan_anim_dir, sync_project


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_anim(tmp_path, files):
    """Create assets/p/anim/<files>; keys are filenames, values bytes."""
    anim_dir = tmp_path / "assets" / "p" / "anim"
    anim_dir.mkdir(parents=True, exist_ok=True)
    for filename, data in files.items():
        (anim_dir / filename).write_bytes(data)
    return anim_dir


def _rows(db_path):
    conn = sqlite3.connect(db_path)
    rows = sorted(conn.execute(
        "SELECT name, kind, filename FROM assets ORDER BY name, kind"))
    conn.close()
    return rows


def _make_project(tmp_path, files):
    """Scaffold a valid animation project, then drop anim/ files into it."""
    scaffold("p", repo_root=tmp_path)
    return _make_anim(tmp_path, files)


def _db_path(tmp_path):
    return anim_project.db_path_for("p", repo_root=tmp_path)


# ---------------------------------------------------------------------------
# scan_anim_dir
# ---------------------------------------------------------------------------

def test_scan_maps_kinds_and_skips_unrelated(tmp_path):
    anim_dir = _make_anim(tmp_path, {
        "frame001.png": b"a", "frame002.PNG": b"b",
        "diff1.pal": b"c", "images.map": b"d"})
    scanned = scan_anim_dir(anim_dir)
    assert set(scanned) == {
        ("frame001", "png"), ("frame002", "png"), ("diff1", "pal")}
    name, kind = ("frame001", "png")
    filename, mtime, size = scanned[(name, kind)]
    assert (filename, size) == ("frame001.png", 1)
    assert mtime > 0


def test_scan_empty_dir_returns_empty(tmp_path):
    anim_dir = _make_anim(tmp_path, {})
    assert scan_anim_dir(anim_dir) == {}


def test_scan_missing_dir_fails(tmp_path, capsys):
    with pytest.raises(SystemExit) as ei:
        scan_anim_dir(tmp_path / "assets" / "p" / "anim")
    assert ei.value.code == 1
    assert "素材目录不存在" in capsys.readouterr().err


def test_scan_rejects_illegal_stem(tmp_path):
    anim_dir = tmp_path / "assets" / "p" / "anim"
    anim_dir.mkdir(parents=True)
    (anim_dir / ".hidden.png").write_bytes(b"x")
    with pytest.raises(SystemExit):
        scan_anim_dir(anim_dir)


@pytest.mark.parametrize("bad", ["a/b", "a\\b", ".", "..", ""])
def test_validate_stem_rejects_separators(bad):
    with pytest.raises(SystemExit):
        anim_register._validate_stem(bad)


# ---------------------------------------------------------------------------
# sync_project
# ---------------------------------------------------------------------------

def test_sync_add_then_unchanged(tmp_path):
    _make_project(tmp_path, {"a.png": b"x", "d.pal": b"y"})
    added, updated, removed, unchanged = sync_project("p", repo_root=tmp_path)
    assert (len(added), len(updated), len(removed), unchanged) == (2, 0, 0, 0)
    assert _rows(_db_path(tmp_path)) == [
        ("a", "png", "a.png"), ("d", "pal", "d.pal")]

    # Second sync without changes -> everything unchanged, no writes
    added, updated, removed, unchanged = sync_project("p", repo_root=tmp_path)
    assert (len(added), len(updated), len(removed), unchanged) == (0, 0, 0, 2)


def test_sync_updates_changed_file(tmp_path):
    anim_dir = _make_project(tmp_path, {"a.png": b"short"})
    sync_project("p", repo_root=tmp_path)
    (anim_dir / "a.png").write_bytes(b"longer-content")
    added, updated, removed, unchanged = sync_project("p", repo_root=tmp_path)
    assert (len(added), len(removed), unchanged) == (0, 0, 0)
    assert updated == [("a", "png")]


def test_sync_prunes_vanished_files(tmp_path):
    anim_dir = _make_project(tmp_path, {"a.png": b"x", "b.png": b"y"})
    sync_project("p", repo_root=tmp_path)
    (anim_dir / "b.png").unlink()
    added, updated, removed, unchanged = sync_project("p", repo_root=tmp_path)
    assert (len(added), len(updated), unchanged) == (0, 0, 1)
    assert removed == [("b", "png")]
    assert _rows(_db_path(tmp_path)) == [("a", "png", "a.png")]


def test_sync_same_stem_png_and_pal_coexist(tmp_path):
    _make_project(tmp_path, {"flash.png": b"x", "flash.pal": b"y"})
    sync_project("p", repo_root=tmp_path)
    assert _rows(_db_path(tmp_path)) == [
        ("flash", "pal", "flash.pal"), ("flash", "png", "flash.png")]


def test_sync_creates_db_parent_dirs(tmp_path):
    _make_project(tmp_path, {"a.png": b"x"})
    added, *_rest = sync_project("p", repo_root=tmp_path)
    assert len(added) == 1
    assert _db_path(tmp_path).is_file()


def test_sync_requires_project_architecture(tmp_path, capsys):
    _make_anim(tmp_path, {"a.png": b"x"})   # assets only, no scaffold
    with pytest.raises(SystemExit) as ei:
        sync_project("p", repo_root=tmp_path)
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "anim_project:" in err
    assert "init" in err


# ---------------------------------------------------------------------------
# diff_project (--check) — read-only reconciliation (devdoc 79)
# ---------------------------------------------------------------------------

def test_diff_reports_drift_without_writing(tmp_path):
    anim_dir = _make_project(tmp_path, {"a.png": b"x", "b.png": b"y"})
    sync_project("p", repo_root=tmp_path)

    # Drift: new file, vanished file, changed content
    (anim_dir / "c.png").write_bytes(b"z")
    (anim_dir / "b.png").unlink()
    (anim_dir / "a.png").write_bytes(b"changed")

    before = _rows(_db_path(tmp_path))
    added, updated, removed, unchanged = diff_project("p", repo_root=tmp_path)
    assert added == [("c", "png")]
    assert updated == [("a", "png")]
    assert removed == [("b", "png")]
    assert unchanged == 0
    # Read-only guarantee: DB rows untouched by diff_project
    assert _rows(_db_path(tmp_path)) == before


def test_diff_requires_existing_db(tmp_path, capsys):
    _make_project(tmp_path, {"a.png": b"x"})
    with pytest.raises(SystemExit) as ei:
        diff_project("p", repo_root=tmp_path)
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "登记库不存在" in err
    assert "register" in err


def test_diff_clean_when_in_sync(tmp_path):
    _make_project(tmp_path, {"a.png": b"x"})
    sync_project("p", repo_root=tmp_path)
    added, updated, removed, unchanged = diff_project("p", repo_root=tmp_path)
    assert (len(added), len(updated), len(removed), unchanged) == (0, 0, 0, 1)


# ---------------------------------------------------------------------------
# CLI summary
# ---------------------------------------------------------------------------

def test_main_summary_output(tmp_path, monkeypatch, capsys):
    _make_project(tmp_path, {"a.png": b"x", "b.png": b"y"})
    monkeypatch.setattr(anim_register, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(anim_project, "PROJECTS_ROOT",
                        tmp_path / "animation" / "projects")
    monkeypatch.setattr(sys, "argv", ["anim_register", "p"])
    anim_register.main()
    out = capsys.readouterr().out
    assert "新增 2 / 更新 0 / 删除 0 / 未变 0" in out
    assert "+ a.png" in out and "+ b.png" in out


def test_main_check_exit_codes(tmp_path, monkeypatch, capsys):
    _make_project(tmp_path, {"a.png": b"x"})
    monkeypatch.setattr(anim_register, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(anim_project, "PROJECTS_ROOT",
                        tmp_path / "animation" / "projects")
    anim_dir = tmp_path / "assets" / "p" / "anim"

    # Register first so the DB exists
    monkeypatch.setattr(sys, "argv", ["anim_register", "p"])
    anim_register.main()
    capsys.readouterr()

    # Drift -> --check exits 1 and lists the unregistered file
    (anim_dir / "new.png").write_bytes(b"n")
    monkeypatch.setattr(sys, "argv", ["anim_register", "--check", "p"])
    with pytest.raises(SystemExit) as ei:
        anim_register.main()
    assert ei.value.code == 1
    out = capsys.readouterr().out
    assert "对账" in out and "+ new.png" in out

    # Sync then re-check clean -> exit 0
    monkeypatch.setattr(sys, "argv", ["anim_register", "p"])
    anim_register.main()
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", ["anim_register", "--check", "p"])
    anim_register.main()
    out = capsys.readouterr().out
    assert "新增 0 / 更新 0 / 删除 0 / 未变 2" in out
