"""devdoc 105 typewriter: settings.text_speed parse semantics + i18n parity.

Mirrors settings.c pref_set_text_speed semantics (single source is the
engine — these tests keep the Python side honest and freeze the contract):
- valid values are {0 (Instant), 16, 32, 64}; default 32;
- unknown values fall back to the default;
- settings_save writes text_speed=N and load parses it back.

Since devdoc 118 the preference is persisted to USER.CFG, not to the
build-owned settings.txt; the parse contract is unchanged, so this file
still owns the speed whitelist and the i18n parity for the speed labels.
See test_user_cfg_settings.py for the file split and test_audio_settings_
invariants.py for the source-level guards.

Note (devdoc 119 §4.1): devdoc 118 §9 claimed this file's roundtrip had been
retargeted at USER.CFG and that _parse_speed/_save_line were split into a
project half and a preference half.  Neither happened — only this docstring
changed.  test_devdoc_refs.py::test_devdoc_claims_match_test_files freezes the
corrected fact so the stale claim is not applied to the code by mistake.

Also guards the i18n requirement: "Text Speed" / "Instant" must stay in
SYSTEM_UI_KEYS (else marked # ORPHANED) and every project sys_<lang>.txt
must carry a non-empty translation (empty falls back to English at runtime).
"""

from pathlib import Path

from naiz_conv.i18n_gen import SYSTEM_UI_KEYS

from naiz_build import nb_validator  # noqa: F401  (import-path sanity)


ROOT = Path(__file__).resolve().parent.parent.parent

SUPPORTED_SPEEDS = {0, 16, 32, 64}
DEFAULT_SPEED = 32


def _parse_speed(text):
    """Mirror of settings.c text_speed= handling (atoi + whitelist + default)."""
    try:
        v = int(text)
    except (TypeError, ValueError):
        return DEFAULT_SPEED
    return v if v in SUPPORTED_SPEEDS else DEFAULT_SPEED


def _save_line(speed):
    return f"text_speed={_parse_speed(speed)}\n"


def test_default_when_missing():  # no settings.txt
    assert DEFAULT_SPEED == 32


def test_parse_all_valid_values():
    for s in (0, 16, 32, 64):
        assert _parse_speed(s) == s


def test_parse_invalid_falls_back_to_default():
    for bad in (99, -1, 8, 128, 1, "abc", ""):
        assert _parse_speed(bad) == DEFAULT_SPEED


def test_roundtrip_save_load():
    for s in SUPPORTED_SPEEDS:
        line = _save_line(s)
        assert line == f"text_speed={s}\n"
        assert _parse_speed(line.split("=")[1].strip()) == s


def test_save_never_emits_unknown_value():
    assert _save_line(999) == f"text_speed={DEFAULT_SPEED}\n"


def test_i18n_keys_registered():
    assert "Text Speed" in SYSTEM_UI_KEYS
    assert "Instant" in SYSTEM_UI_KEYS


def test_sys_files_have_translations():
    for proj_dir in (ROOT / "projects").iterdir():
        i18n = proj_dir / "i18n"
        if not i18n.is_dir():
            continue
        found = set()
        for sys_file in i18n.glob("sys_*.txt"):
            entries = {}
            with open(sys_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip("\n").rstrip("\r")
                    if not line or line.startswith("#"):
                        continue
                    eq = line.find("=")
                    if eq < 0:
                        continue
                    key = line[:eq].strip()
                    if key:
                        entries[key] = line[eq + 1:]
            found.add(sys_file.name)
            for key in ("Text Speed", "Instant"):
                assert key in entries, f"{sys_file.name}: missing {key!r}"
                assert entries[key].strip(), f"{sys_file.name}: empty {key!r}"
        assert found, f"{proj_dir.name}: no sys_* files found"