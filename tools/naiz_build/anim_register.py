#!/usr/bin/env python3
"""Register animation frame assets into the per-project animation DB.

Scans assets/<project>/anim/ for *.png / *.pal and upserts a name index
into animation/projects/<project>/db/<project>.db, so animation
scripts (.na) reference bare logical names (no path prefix, no
extension). PNG files
remain the data source; the DB is a namespace index only (never stores
image bytes; .ANI assembly embeds pixels and never touches game
ASSETS.DB).

Prerequisite: a valid animation project architecture created by
`anima.sh init <project>` (see anim_project.py).

Schema (composite key allows the same stem as .png + .pal):

    CREATE TABLE IF NOT EXISTS assets (
        name     TEXT NOT NULL,   -- logical name = filename stem
        filename TEXT NOT NULL,   -- relative to assets/<project>/anim/
        kind     TEXT NOT NULL,   -- 'png' | 'pal'
        mtime    REAL NOT NULL,
        size     INTEGER NOT NULL,
        PRIMARY KEY (name, kind)
    )

Usage:
    python -m tools.naiz_build.anim_register <project>            # sync
    python -m tools.naiz_build.anim_register --check <project>    # read-only

Sync semantics: full directory scan -> diff against DB rows -> one
transaction upserting new/changed rows and pruning rows whose file
vanished. Summary prints added/updated/removed/unchanged counts.

Check semantics (--check): the same scan+diff without writing anything;
exits 1 when any difference exists, so callers can gate on it. The
shared read-only entry point is diff_project().
"""

import argparse
import sqlite3
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "tools"))

from naiz_build.anim_project import db_path_for, load_project  # noqa: E402

_SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    name     TEXT NOT NULL,
    filename TEXT NOT NULL,
    kind     TEXT NOT NULL,
    mtime    REAL NOT NULL,
    size     INTEGER NOT NULL,
    PRIMARY KEY (name, kind)
)
"""

_KINDS = {"png": ".png", "pal": ".pal"}


def _fail(msg):
    print(f"anim_register: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _validate_stem(stem):
    if not stem or stem.startswith(".") or "/" in stem or "\\" in stem:
        _fail(f"非法素材名（文件主干）: '{stem}'")
    return stem


def scan_anim_dir(anim_dir):
    """Scan anim/ and return {(name, kind): (filename, mtime, size)}."""
    if not anim_dir.is_dir():
        _fail(f"素材目录不存在: {anim_dir}（需先创建并放入 png/pal）")
    scanned = {}
    for path in sorted(anim_dir.iterdir()):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        kind = next((k for k, ext in _KINDS.items() if suffix == ext), None)
        if kind is None:
            continue  # unrelated files (e.g. .map) are ignored silently
        name = _validate_stem(path.stem)
        scanned[(name, kind)] = (path.name, path.stat().st_mtime, path.stat().st_size)
    return scanned


def _read_db_rows(conn):
    """Read the assets table into {(name, kind): (filename, mtime, size)}."""
    return {
        (name, kind): (filename, mtime, size)
        for name, kind, filename, mtime, size in conn.execute(
            "SELECT name, kind, filename, mtime, size FROM assets")
    }


def _diff_maps(scanned, existing):
    """Compare scan results against DB rows -> diff counts/tuples."""
    added = sorted(set(scanned) - set(existing))
    removed = sorted(set(existing) - set(scanned))
    shared = set(scanned) & set(existing)
    updated = sorted(k for k in shared if scanned[k] != existing[k])
    unchanged = len(shared) - len(updated)
    return added, updated, removed, unchanged


def diff_project(project, repo_root=None):
    """Read-only reconciliation of anim/ contents against the project DB.

    Requires a valid animation project architecture (anima.sh init) and
    an existing DB (register must have run at least once). Never writes;
    fails when the DB is missing so callers never mistake "no DB" for
    "everything registered".
    Returns (added, updated, removed, unchanged).
    """
    repo_root = Path(repo_root) if repo_root else _REPO_ROOT
    load_project(project, repo_root=repo_root)
    anim_dir = repo_root / "assets" / project / "anim"
    db_path = db_path_for(project, repo_root=repo_root)
    scanned = scan_anim_dir(anim_dir)
    if not db_path.is_file():
        _fail(f"登记库不存在: {db_path}"
              f"（先运行 anima.sh register {project}）")
    conn = sqlite3.connect(db_path)
    try:
        return _diff_maps(scanned, _read_db_rows(conn))
    finally:
        conn.close()


def sync_project(project, repo_root=None):
    """Sync anim/ contents into the project DB (.../db/<project>.db).

    Requires a valid animation project architecture (anima.sh init).
    Returns (added, updated, removed, unchanged) counts.
    """
    repo_root = Path(repo_root) if repo_root else _REPO_ROOT
    load_project(project, repo_root=repo_root)
    anim_dir = repo_root / "assets" / project / "anim"
    db_path = db_path_for(project, repo_root=repo_root)
    scanned = scan_anim_dir(anim_dir)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(_SCHEMA)
    existing = _read_db_rows(conn)
    added, updated, removed, unchanged = _diff_maps(scanned, existing)

    with conn:
        for key in removed:
            conn.execute("DELETE FROM assets WHERE name=? AND kind=?", key)
        for key in added + updated:
            filename, mtime, size = scanned[key]
            conn.execute(
                "INSERT OR REPLACE INTO assets "
                "(name, kind, filename, mtime, size) VALUES (?,?,?,?,?)",
                (key[0], key[1], filename, mtime, size))
    conn.close()
    return added, updated, removed, unchanged


def main():
    parser = argparse.ArgumentParser(
        description="登记 anim/ 素材到项目动画数据库"
                    "（animation/projects/<项目>/db/<项目>.db）")
    parser.add_argument("project", help="项目名（assets/<项目>/anim/ 与库名同名）")
    parser.add_argument("--check", action="store_true",
                        help="只读对账（不写库）；存在差异时退出码 1")
    args = parser.parse_args()

    anim_dir = _REPO_ROOT / "assets" / args.project / "anim"
    if args.check:
        added, updated, removed, unchanged = diff_project(args.project)
    else:
        added, updated, removed, unchanged = sync_project(args.project)

    print(f"=== 动画素材{'对账' if args.check else '登记'}: {args.project} ===")
    print(f"  扫描目录: {anim_dir}")
    print(f"  新增 {len(added)} / 更新 {len(updated)} / "
          f"删除 {len(removed)} / 未变 {unchanged}")
    for key in added:
        print(f"    + {key[0]}.{key[1]}")
    for key in updated:
        print(f"    ~ {key[0]}.{key[1]}")
    for key in removed:
        print(f"    - {key[0]}.{key[1]}")
    print(f"→ {db_path_for(args.project)}")

    if args.check and (added or updated or removed):
        print("anim_register: 对账发现差异（未同步），退出码 1", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
