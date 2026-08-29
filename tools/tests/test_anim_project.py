"""anim_project unit tests — animation/projects/<name>/ architecture.

Covers scaffold creation (config.toml + scripts/ + db/), the project
validity gate (directory / config.toml / [project] name == dir name),
candidate enumeration, and both CLI subcommands.
"""

import sys

import pytest

from naiz_build import anim_project
from naiz_build.anim_project import (
    db_path_for,
    iter_projects,
    load_project,
    scaffold,
)


# ---------------------------------------------------------------------------
# scaffold
# ---------------------------------------------------------------------------

def test_scaffold_creates_layout(tmp_path):
    d = scaffold("myproj", repo_root=tmp_path)
    assert d == tmp_path / "animation" / "projects" / "myproj"
    assert (d / "scripts").is_dir()
    assert (d / "db").is_dir()
    config = (d / "config.toml").read_text(encoding="utf-8")
    assert 'name = "myproj"' in config
    assert 'version = "0.1.000"' in config


def test_scaffold_existing_dir_rejected(tmp_path, capsys):
    scaffold("p", repo_root=tmp_path)
    with pytest.raises(SystemExit) as ei:
        scaffold("p", repo_root=tmp_path)
    assert ei.value.code == 1
    assert "已存在" in capsys.readouterr().err


@pytest.mark.parametrize("bad", ["", ".", "..", ".hid", "a/b", "a\\b"])
def test_scaffold_illegal_name_rejected(tmp_path, bad):
    with pytest.raises(SystemExit):
        scaffold(bad, repo_root=tmp_path)


# ---------------------------------------------------------------------------
# load_project validity gate
# ---------------------------------------------------------------------------

def test_load_project_valid(tmp_path):
    scaffold("p", repo_root=tmp_path)
    d, cfg = load_project("p", repo_root=tmp_path)
    assert d == tmp_path / "animation" / "projects" / "p"
    assert cfg.get_str("project", "name") == "p"


def _expect_load_fail(tmp_path, capsys, frag):
    with pytest.raises(SystemExit) as ei:
        load_project("p", repo_root=tmp_path)
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "anim_project:" in err
    assert frag in err
    return err


def test_load_project_missing_dir(tmp_path, capsys):
    err = _expect_load_fail(tmp_path, capsys, "动画项目不存在")
    assert "init" in err


def test_load_project_missing_config(tmp_path, capsys):
    (tmp_path / "animation" / "projects" / "p").mkdir(parents=True)
    _expect_load_fail(tmp_path, capsys, "缺少项目设置文件")


def test_load_project_bad_toml(tmp_path, capsys):
    d = tmp_path / "animation" / "projects" / "p"
    d.mkdir(parents=True)
    (d / "config.toml").write_text("[project\n", encoding="utf-8")
    _expect_load_fail(tmp_path, capsys, "解析失败")


def test_load_project_missing_name(tmp_path, capsys):
    d = tmp_path / "animation" / "projects" / "p"
    d.mkdir(parents=True)
    (d / "config.toml").write_text(
        '[project]\nversion = "0.1.000"\n', encoding="utf-8")
    _expect_load_fail(tmp_path, capsys, "[project] name")


def test_load_project_name_mismatch(tmp_path, capsys):
    d = tmp_path / "animation" / "projects" / "p"
    d.mkdir(parents=True)
    (d / "config.toml").write_text(
        '[project]\nname = "other"\n', encoding="utf-8")
    _expect_load_fail(tmp_path, capsys, "不一致")


# ---------------------------------------------------------------------------
# iter_projects
# ---------------------------------------------------------------------------

def test_iter_projects_sorted_and_candidates_only(tmp_path):
    root = tmp_path / "animation" / "projects"
    for name in ("b_proj", "a_proj"):
        d = scaffold(name, repo_root=tmp_path)
    # bare directory without config.toml is not a candidate
    (root / "noconfig").mkdir()
    # stray file is ignored
    (root / "stray.txt").write_text("x", encoding="utf-8")

    assert iter_projects(repo_root=tmp_path) == ["a_proj", "b_proj"]


def test_iter_projects_missing_root(tmp_path):
    assert iter_projects(repo_root=tmp_path) == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_main_init_and_list(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(anim_project, "PROJECTS_ROOT",
                        tmp_path / "animation" / "projects")
    monkeypatch.setattr(sys, "argv", ["anim_project", "init", "cli_p"])
    anim_project.main()
    assert "动画项目初始化" in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["anim_project", "list"])
    anim_project.main()
    assert capsys.readouterr().out.strip() == "cli_p"


def test_db_path_layout(tmp_path):
    p = db_path_for("p", repo_root=tmp_path)
    assert p == (tmp_path / "animation" / "projects" / "p" / "db" / "p.db")
