#!/usr/bin/env python3
"""
版本号自增工具 — 每次代码修改后调用，将 config.toml 的 version 最右段 +1。

用法:
    python -m tools.naiz_build.bump_version <game>
    python -m tools.naiz_build.bump_version <game> --minor

版本格式: X.Y.ZZZ  (如 0.1.001 → 0.1.002)
--minor: Y+1 且 ZZZ 归零  (如 0.1.069 → 0.2.000)

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


def bump_version(game_name: str, minor: bool = False):
    config_path = ROOT / "projects" / game_name / "config.toml"
    if not config_path.exists():
        print(f"ERROR: config.toml not found: {config_path}")
        sys.exit(1)

    try:
        cfg = ProjectConfig(config_path.parent)
    except ValueError as e:
        print(f"ERROR: config.toml parse error: {e}")
        sys.exit(1)

    ver = cfg.version() or "0.0.000"
    try:
        new_ver = compute_next_version(ver, minor=minor)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    raw = cfg.raw

    # Line-based replacement: only touch the version= line, keep all comments/format.
    new_raw, n = re.subn(
        r'(?m)^( *version *=[ \t]*")[0-9]+\.[0-9]+\.[0-9]+(")',
        rf'\g<1>{new_ver}\g<2>',
        raw,
    )
    if n != 1:
        print(f"ERROR: could not locate exactly one 'version = \"X.Y.ZZZ\"' line in {config_path} (found {n})")
        sys.exit(1)

    config_path.write_text(new_raw, encoding="utf-8")
    print(f"  version bumped: {ver} → {new_ver}")


def main():
    args = [a for a in sys.argv[1:] if a != "--minor"]
    minor = "--minor" in sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)
    bump_version(args[0], minor=minor)


if __name__ == "__main__":
    main()
