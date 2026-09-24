"""Human/AI verification notes for audit candidates.

A candidate (relpath:lineno) that a reviewer has examined can be recorded
here so later runs can annotate it as [verified-ok/fixed] instead of re-listing
it as raw noise.  The notes live in a file independent from audit_state.json:

    verify_notes.json

Each note snapshots the content hash of the file at review time; when the file
changes (sha256 differs) the note is reported as [stale] and does not suppress
the finding (verified markers only annotate, they never filter).
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

VERIFY_VERSION = 2
VERIFY_NAME = "verify_notes.json"
VERDICTS = ("ok", "fixed", "todo")


def project_root():
    return Path(__file__).resolve().parents[2]


def verify_path(root=None):
    return (root or project_root()) / VERIFY_NAME


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def line_text(root, loc):
    """Return the flagged line's text, or None when unreadable/out of range."""
    rel, _, lineno = loc.partition(":")
    try:
        lines = (Path(root) / rel).read_text(encoding="utf-8",
                                             errors="replace").splitlines()
    except OSError:
        return None
    try:
        return lines[int(lineno) - 1]
    except (ValueError, IndexError):
        return None


def load(root=None):
    path = verify_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict) or data.get("version") not in (1, 2):
        return {}
    notes = data.get("notes", {})
    return notes if isinstance(notes, dict) else {}


def save(root, notes):
    data = {
        "version": VERIFY_VERSION,
        "notes": {loc: note for loc, note in sorted(notes.items())},
    }
    path = verify_path(root)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


def add(root, loc, verdict, text, sha=None, line=None):
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}, got {verdict!r}")
    notes = load(root)
    if sha is None:
        try:
            sha = sha256_of(Path(root) / loc.split(":", 1)[0])
        except OSError:
            sha = ""
    if line is None:
        line = line_text(root, loc)
    notes[loc] = {
        "verdict": verdict,
        "text": text,
        "date": datetime.now().isoformat(timespec="seconds"),
        "sha256": sha,
        "line": line,
    }
    return save(root, notes), notes[loc]


def fresh(root, loc, note):
    """True when the reviewed code is unchanged since the note was written.

    Line-level freshness is authoritative when the note captured the exact
    flagged line (version 2): an unrelated edit elsewhere in the file no
    longer stales the review.  Version 1 notes (no line snapshot) fall back
    to whole-file sha256 equality.
    """
    if "line" in note and note.get("line") is not None:
        return note["line"] == line_text(root, loc)
    sha = note.get("sha256")
    if not sha:
        return False
    try:
        return sha == sha256_of(Path(root) / loc.split(":", 1)[0])
    except OSError:
        return False


def note_for(notes, rel, lineno):
    return notes.get(f"{rel}:{lineno}")


# make pytest importable from tools/
__all__ = ["load", "save", "add", "note_for", "verify_path", "project_root",
           "sha256_of", "VERIFY_VERSION", "VERIFY_NAME", "VERDICTS"]