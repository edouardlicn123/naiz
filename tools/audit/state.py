"""Incremental audit state: git version + per-file content hashes.

The state file (`audit_state.json` at the repo root, git-tracked) records
the git HEAD at the time of the last audit and a sha256 for every audited
file.  A later run compares each file's current hash against the record:
identical hash -> file skipped (rule re-check unnecessary); missing/state
file absent -> full re-check.  Content hashes are authoritative over the
git commit id, so uncommitted working-tree edits are still detected.
"""

import hashlib
import json
import subprocess
from pathlib import Path

STATE_VERSION = 2
STATE_NAME = "audit_state.json"


def project_root():
    return Path(__file__).resolve().parents[2]


def state_path(root=None):
    return (root or project_root()) / STATE_NAME


def git_head(root=None):
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root or project_root()), capture_output=True, text=True,
            timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "no-git"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load(root=None):
    """Return the parsed state dict, or None when missing/invalid."""
    path = state_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("version") != STATE_VERSION:
        return None
    return data


def save(root, files, summary, checked_at=None):
    """Persist state for one audit run (git-tracked record file)."""
    data = {
        "version": STATE_VERSION,
        "git_head": git_head(root),
        "checked_at": checked_at,
        "files": {rel: {
            "sha256": info["sha256"],
            "violations": info["violations"],
            "candidates": info["candidates"],
            "findings": [
                {"line": f["line"], "rule": f["rule"], "level": f["level"]}
                for f in info.get("findings", [])
            ],
        } for rel, info in sorted(files.items())},
        "summary": summary,
    }
    path = state_path(root)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


# make pytest importable from tools/
__all__ = ["load", "save", "git_head", "sha256_of", "state_path",
           "project_root", "STATE_VERSION", "STATE_NAME"]