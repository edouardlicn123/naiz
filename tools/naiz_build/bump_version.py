#!/usr/bin/env python3
"""
版本号自增工具 — 每次代码修改后调用，将全部项目 config.toml 统一到同一新号。

用法:
    python -m tools.naiz_build.bump_version [game]
    python -m tools.naiz_build.bump_version [game] --minor

版本格式: X.Y.ZZZ  (如 0.1.001 → 0.1.002)
--minor: Y+1 且 ZZZ 归零  (如 0.1.069 → 0.2.000)

一次调用作用于 projects/ 下全部项目：统一目标 = 所有项目当前版本的最大值 +1，
因此历史漂移会在下次 bump 时自愈收敛到同一号（防多个版本号发散）。
[game] 为可选兼容参数，仅校验该项目存在，不影响作用范围。

以按行替换写回，保留 config.toml 中全部 # 注释与文件格式。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from naiz_build.project_config import ProjectConfig


ROOT = Path(__file__).resolve().parent.parent.parent

_VERSION_RE = re.compile(r'^\d+\.\d+\.\d+$')


def compute_next_version(ver: str, minor: bool = False) -> str:
    """Return the next version string for a given X.Y.ZZZ version.

    minor=False: patch +1 (0.1.069 -> 0.1.070).
    minor=True:  minor +1, patch reset to 000 (0.1.069 -> 0.2.000).

    Raises ValueError for malformed input or patch overflow.
    """
    if not _VERSION_RE.match(ver):
        raise ValueError(f"version '{ver}' does not match X.Y.ZZZ format")
    major, y, patch = ver.split(".")
    if minor:
        return f"{major}.{int(y) + 1}.000"
    try:
        new_patch = int(patch) + 1
    except ValueError:
        raise ValueError(f"cannot parse version '{ver}', expected X.Y.ZZZ")
    if new_patch >= 1000:
        raise ValueError(
            f"patch overflow {new_patch} >= 1000, version format X.Y.ZZZ exhausted"
        )
    return f"{major}.{y}.{new_patch:03d}"


def compute_unified_version(versions, minor: bool = False) -> str:
    """Return the single next version for a set of project versions.

    Target is computed from the maximum current version, so any drift
    self-heals: every project converges to max + 1 (or a minor bump of max).
    """
    parsed = []
    for ver in versions:
        if not _VERSION_RE.match(ver):
            raise ValueError(f"version '{ver}' does not match X.Y.ZZZ format")
        parsed.append(tuple(int(p) for p in ver.split(".")))
    mx = max(parsed)
    return compute_next_version(f"{mx[0]}.{mx[1]}.{mx[2]:03d}", minor=minor)


def _project_configs(projects_root):
    return sorted(projects_root.glob("*/config.toml"))


def bump_all_projects(projects_root, minor: bool = False):
    """Read every project's version and write the unified next version to all."""
    config_paths = _project_configs(projects_root)
    if not config_paths:
        print(f"ERROR: no project config.toml found under {projects_root}")
        sys.exit(1)

    entries = []
    for path in config_paths:
        try:
            cfg = ProjectConfig(path.parent)
        except ValueError as e:
            print(f"ERROR: config.toml parse error: {path}: {e}")
            sys.exit(1)
        ver = cfg.version() or "0.0.000"
        if not _VERSION_RE.match(ver):
            print(f"ERROR: version '{ver}' in {path} does not match X.Y.ZZZ format")
            sys.exit(1)
        entries.append((path, cfg, ver))

    try:
        target = compute_unified_version([ver for _, _, ver in entries], minor=minor)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    for path, cfg, ver in entries:
        # Line-based replacement: only touch the version= line, keep all comments/format.
        new_raw, n = re.subn(
            r'(?m)^( *version *=[ \t]*")[0-9]+\.[0-9]+\.[0-9]+(")',
            rf'\g<1>{target}\g<2>',
            cfg.raw,
        )
        if n != 1:
            print(f"ERROR: could not locate exactly one 'version = \"X.Y.ZZZ\"' line in {path} (found {n})")
            sys.exit(1)
        path.write_text(new_raw, encoding="utf-8")
        print(f"  {path.parent.name}: {ver} → {target}")


def main():
    args = [a for a in sys.argv[1:] if a != "--minor"]
    minor = "--minor" in sys.argv[1:]
    if args:
        # Optional compatibility arg: validate the named project exists.
        check = ROOT / "projects" / args[0] / "config.toml"
        if not check.exists():
            print(f"ERROR: config.toml not found: {check}")
            sys.exit(1)
    bump_all_projects(ROOT / "projects", minor=minor)


if __name__ == "__main__":
    main()