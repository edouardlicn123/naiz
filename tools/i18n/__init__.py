"""Naiz dev-tools i18n (Python side).

Mirrors tools/i18n/lang.sh.  English strings are the lookup keys; missing
keys fall back to the English original (never blank).  Language preference
lives in ``$PROJECT_ROOT/.naiz_lang`` (eng|chi|jpn|kor), overridable via
the ``NAIZ_LANG`` environment variable.
"""

import os
from pathlib import Path

from . import strings as _strings

SUPPORTED = ("eng", "chi", "jpn", "kor")
DEFAULT = "eng"


def _project_root() -> Path:
    # tools/i18n/__init__.py -> tools/i18n/ -> tools/ -> project root
    return Path(__file__).resolve().parent.parent.parent


def _lang_file() -> Path:
    return _project_root() / ".naiz_lang"


def current_lang() -> str:
    """Return the active language code (eng|chi|jpn|kor), default eng."""
    lang = os.environ.get("NAIZ_LANG", "").strip()
    if not lang:
        f = _lang_file()
        if f.is_file():
            lang = f.read_text(encoding="utf-8").strip()
    return lang if lang in SUPPORTED else DEFAULT


def set_lang(lang: str) -> None:
    """Persist the language choice to $PROJECT_ROOT/.naiz_lang."""
    if lang not in SUPPORTED:
        raise ValueError(f"invalid language: {lang}")
    _lang_file().write_text(f"{lang}\n", encoding="utf-8")


_TABLE = getattr(_strings, "TABLES", {})


def tr(text: str) -> str:
    """Translate ``text`` into the active language; fall back to English."""
    lang = current_lang()
    if lang == DEFAULT:
        return text
    return _TABLE.get(lang, {}).get(text, text)
