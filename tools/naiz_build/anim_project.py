#!/usr/bin/env python3
"""Animation project architecture (animation/projects/<name>/).

Single source of truth for locating and validating animation projects.
Each project is a directory under animation/projects/ named after the
project, containing:

    config.toml          # [project] name (= directory name) / version / desc
    scripts/*.na         # animation scripts owned by this project
                         # (.na suffix separates them from story .nb)
    db/<name>.db         # bare-name asset index (built by anim_register.py)

Frame/pal source assets stay at assets/<project>/anim/ (shared with the
game build pipeline); built .ANI files stay at the global
animation/output/. A directory counts as an animation project only when
config.toml exists and its [project] name matches the directory name.

Usage:
    python -m tools.naiz_build.anim_project init <project>
    python -m tools.naiz_build.anim_project list
"""

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "tools"))

from naiz_build.project_config import load_project_config  # noqa: E402

PROJECTS_ROOT = _REPO_ROOT / "animation" / "projects"

_CONFIG_TEMPLATE = """\
# =============================================================
# Naiz 动画工程配置 (TOML) — 支持 # 注释
# Naiz animation project configuration (TOML), supports # comments
#
# [project] name 是本目录作为动画项目的判定依据，必须与目录名一致。
# The [project] name identifies this directory as an animation project;
# it must match the directory name exactly.
# =============================================================

[project]
# 项目名（必须与本目录同名；脚本 animaconf 第三参数须与此一致）
# Project name (must equal the directory name; scripts reference it as
# the third animaconf argument)
name = "{name}"

# 版本号 X.Y.ZZZ（.ANI 为独立分发产物，当前仅作标识记录）
# Version X.Y.ZZZ (.ANI files are standalone artifacts; informational)
version = "0.1.000"

# 描述（简短说明，仅用于项目内辨识）
# Description (short note for identification within the project)
description = ""
"""


def _fail(msg):
    print(f"anim_project: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _validate_project_name(project):
    if (not project or project in ('.', '..')
            or project.startswith('.') or '/' in project or '\\' in project):
        _fail(f"非法项目名: '{project}'")
    return project


def project_dir(project, repo_root=None):
    """Return the project root directory for one project name."""
    _validate_project_name(project)
    if repo_root is None:
        return PROJECTS_ROOT / project
    return Path(repo_root) / "animation" / "projects" / project


def db_dir_for(project, repo_root=None):
    """Return the project's asset-index DB directory (.../db/)."""
    return project_dir(project, repo_root) / "db"


def db_path_for(project, repo_root=None):
    """Return the project's asset-index DB path (.../db/<project>.db)."""
    return db_dir_for(project, repo_root) / f"{project}.db"


def scripts_dir_for(project, repo_root=None):
    """Return the project's animation script directory."""
    return project_dir(project, repo_root) / "scripts"


def load_project(project, repo_root=None):
    """Validate the project architecture and return (dir, ProjectConfig).

    Fails with SystemExit(1) when the directory is missing, config.toml
    is absent/unparseable, or [project] name != directory name.
    """
    d = project_dir(project, repo_root)
    if not d.is_dir():
        _fail(f"动画项目不存在: {d}（先运行 anima.sh init {project}）")
    try:
        cfg = load_project_config(d)
    except FileNotFoundError:
        _fail(f"缺少项目设置文件: {d}/config.toml（动画项目须由 "
              f"anima.sh init 创建）")
    except ValueError as e:
        _fail(f"{d}/config.toml 解析失败: {e}")
    name = cfg.get_str("project", "name")
    if not name:
        _fail(f"{d}/config.toml 缺少 [project] name")
    if name != project:
        _fail(f"config.toml name '{name}' 与目录名 '{project}' 不一致"
              f"（{d}/config.toml）")
    return d, cfg


def iter_projects(repo_root=None):
    """List project names (sorted) — directories holding a config.toml.

    Names are candidates; full validity is enforced by load_project().
    """
    root = PROJECTS_ROOT if repo_root is None else (
        Path(repo_root) / "animation" / "projects")
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir()
                  if d.is_dir() and (d / "config.toml").is_file())


def scaffold(project, repo_root=None):
    """Create the project skeleton: config.toml + scripts/ + db/.

    Fails when the directory already exists (no silent overwrite).
    Returns the created project directory.
    """
    d = project_dir(project, repo_root)
    if d.exists():
        _fail(f"项目目录已存在: {d}")
    (d / "scripts").mkdir(parents=True)
    (d / "db").mkdir()
    (d / "config.toml").write_text(
        _CONFIG_TEMPLATE.format(name=project), encoding="utf-8")
    print(f"=== 动画项目初始化: {project} ===")
    print(f"  {d}/config.toml   (name={project})")
    print(f"  {d}/scripts/      （放 <名>.na 动画脚本）")
    print(f"  {d}/db/           （register 生成的登记库）")
    print(f"素材请放 assets/{project}/anim/（png/pal），"
          f"然后运行 anima.sh register {project}")
    return d


def main():
    parser = argparse.ArgumentParser(
        description="动画项目架构工具（animation/projects/<名>/）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="创建项目骨架（config+scripts+db）")
    p_init.add_argument("project", help="项目名")

    sub.add_parser("list", help="列出候选动画项目（每行一个）")

    args = parser.parse_args()

    if args.cmd == "init":
        scaffold(args.project)
    elif args.cmd == "list":
        projects = iter_projects()
        if not projects:
            print("(无动画项目 — 用 anima.sh init <项目> 创建)", file=sys.stderr)
        for p in projects:
            print(p)


if __name__ == "__main__":
    main()
