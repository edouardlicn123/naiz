"""Shared helpers for naiz_cli subcommands.

ROOT resolution, venv path, and a few small reusable utilities that
every subcommand module needs.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from i18n import tr, current_lang
except ImportError:  # imported as `tools.naiz_cli` (repo root on sys.path)
    from tools.i18n import tr, current_lang


# --- ROOT resolution -------------------------------------------------------

def find_root() -> Path:
    """Walk up from CWD looking for core/engine/main.c; fall back to CWD."""
    cwd = Path.cwd().resolve()
    for p in [cwd, *cwd.parents]:
        if (p / "core" / "engine" / "main.c").is_file():
            return p
    return cwd


def require_root() -> Path:
    """Like find_root but hard-fails with a clear message if not found."""
    root = find_root()
    if not (root / "core" / "engine" / "main.c").is_file():
        print(tr("Error: cannot confirm Naiz project root (core/engine/main.c not found)"), file=sys.stderr)
        print(f"  cwd: {Path.cwd()}", file=sys.stderr)
        print(tr("Please run from the project root."), file=sys.stderr)
        sys.exit(1)
    return root


# --- Venv ------------------------------------------------------------------

VENV_DIR = Path.home() / "venv"
VENV_PYTHON = VENV_DIR / "bin" / "python3"


def ensure_venv_exists() -> None:
    """Soft check: print a friendly error and exit if the venv is missing."""
    if not VENV_DIR.is_dir():
        print(tr("Error: Python virtual environment not found"), file=sys.stderr)
        print(tr("Please run first: bash start.sh pip"), file=sys.stderr)
        sys.exit(1)


def get_venv_python() -> str:
    return str(VENV_PYTHON) if VENV_PYTHON.is_file() else sys.executable


# --- Pack mode helpers (shared with makegame) -----------------------------

PACK_FILE = ".naiz_pack"


def resolve_pack_mode(root: Path, explicit: str | None = None) -> tuple[str, str]:
    """Return (pack_mode, extender).

    Priority: explicit arg > env NAIZ_PACK > .naiz_pack file > auto-detect.
    """
    # 1. Explicit arg
    if explicit:
        return _normalize_pack(explicit)

    # 2. Env var
    env_val = os.environ.get("NAIZ_PACK", "").strip()
    if env_val:
        return _normalize_pack(env_val)

    # 3. Root-level file
    pfile = root / PACK_FILE
    if pfile.is_file():
        val = pfile.read_text().strip()
        if val:
            return _normalize_pack(val)

    # 4. Auto-detect
    if (root / "tools_commercial").is_dir():
        return "cmpack", "dos4g"
    if (root / "tools_open").is_dir():
        return "openpack", "dos32a"
    return "cmpack", "dos4g"


def _normalize_pack(raw: str) -> tuple[str, str]:
    raw = raw.strip().lower()
    if raw in ("cmp", "cmpack", "commercial"):
        return "cmpack", "dos4g"
    if raw in ("open", "openpack", "oss"):
        return "openpack", "dos32a"
    print(f"{tr('Error: invalid pack mode')} '{raw}' ({tr('options: cmpack | openpack')})", file=sys.stderr)
    sys.exit(1)


def describe_pack(pack_mode: str) -> str:
    if pack_mode == "openpack":
        return f"openpack (tools_open + DOS/32A {tr('open-source chain')})"
    return f"cmpack (tools_commercial + DOS/4GW {tr('commercial chain')})"


# --- Language helpers (Python mirror of tools/i18n/lang.sh) ---------------

LANG_FILE = ".naiz_lang"
VALID_LANGS = ("eng", "chi", "jpn", "kor")


def naiz_set_lang(root: Path, code: str) -> None:
    """Persist the language choice to ROOT/.naiz_lang."""
    if code not in VALID_LANGS:
        raise ValueError(f"[i18n] invalid language: {code}")
    (root / LANG_FILE).write_text(code + "\n")


def naiz_current_lang(root: Path) -> str:
    """Return current language (env var > file > default eng)."""
    env = os.environ.get("NAIZ_LANG", "").strip()
    if env in VALID_LANGS:
        return env
    f = root / LANG_FILE
    if f.is_file():
        val = f.read_text().strip()
        if val in VALID_LANGS:
            return val
    return "eng"


# --- Terminal helpers ------------------------------------------------------

def menu_prompt(label: str, choices: list[str], default: int | None = None,
                allow_blank: bool = False) -> str:
    """Print choices (1-indexed) and read input. Returns the raw string."""
    print(label)
    for i, c in enumerate(choices, 1):
        print(f"  {i}) {c}")
    if default is not None:
        prefix = f"[{default}]"
    else:
        prefix = ""
    try:
        return input(f"{tr('Choose')} {prefix}: ").strip()
    except EOFError:
        print()
        return ""


def press_enter() -> None:
    try:
        input(tr("Press Enter to continue..."))
    except EOFError:
        print()


def safe_int(s: str, lo: int, hi: int | None = None) -> int | None:
    """Parse s as int; return None on non-numeric or out-of-range."""
    if not s.isdigit():
        return None
    n = int(s)
    if n < lo:
        return None
    if hi is not None and n > hi:
        return None
    return n
