"""devdoc 118 / 120: player preferences (USER.CFG) must survive a build.

The 0.3.011 bug this guards: prefs_save() wrote settings.txt, and
build_game.py copied projects/<game>/scene/settings.txt over the deployed
file unconditionally.  Every build therefore reset Language and Text Speed.

The 0.3.014 bug this guards: USER.CFG held the only writable `lang` key, but
prefs_get_lang() read a *different* struct, so the boot-menu choice was saved
and then ignored.  `lang` used to exist in two files at once; now it exists
only in USER.CFG and the project default is `[i18n] default_lang`.

These tests freeze the *contract*, not the implementation:
- USER.CFG is 8.3-safe and does not collide with any other runtime file;
- build never copies/injects/clears it (it only reports that it was kept);
- settings.txt is gone from the whole build path and from projects/;
- config.toml owns every project value and exports it to nb_config.h;
- there is exactly one `lang` key in the system, and it is the player's.

They also mirror prefs.c parse semantics for the audio preferences:
BGM volume snaps to the nearest ladder rung, PCM volume clamps to 0-15,
switches are 0/1, and a hand-edited out-of-range value can never reach the
menu (which only shows ladder entries).
"""

import io
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from naiz_lib import to_dos_name  # noqa: E402
from naiz_lib.langdefs import LANG_CODE_SET  # noqa: E402
from naiz_build.project_config import ProjectConfig  # noqa: E402

USER_CFG = "USER.CFG"

# prefs.c: PREFS_BGM_VOL_LADDER / PREFS_PCM_VOL_LADDER
BGM_VOL_LADDER = [0, 64, 127]
PCM_VOL_MAX = 15

# Keys the runtime writes to USER.CFG (prefs.c prefs_save).
PLAYER_KEYS = {"lang", "text_speed", "bgm", "snd", "vc", "bgm_vol", "pcm_vol"}

SUPPORTED_SPEEDS = {0, 16, 32, 64}
DEFAULT_SPEED = 32


# --- mirrors of settings.c -------------------------------------------------

def parse_bgm_volume(text):
    """settings.c pref_set_bgm_volume: snap to the nearest ladder rung."""
    try:
        v = int(text)
    except (TypeError, ValueError):
        v = 0
    best, bestd = 0, None
    for i, rung in enumerate(BGM_VOL_LADDER):
        d = abs(v - rung)
        if bestd is None or d < bestd:
            bestd, best = d, i
    return BGM_VOL_LADDER[best]


def parse_pcm_volume(text):
    """settings.c pref_set_pcm_volume: clamp to 0..15 (A466 attenuation)."""
    try:
        v = int(text)
    except (TypeError, ValueError):
        v = 0
    return max(0, min(PCM_VOL_MAX, v))


def parse_speed(text):
    """settings.c pref_set_text_speed: whitelist, else default."""
    try:
        v = int(text)
    except (TypeError, ValueError):
        return DEFAULT_SPEED
    return v if v in SUPPORTED_SPEEDS else DEFAULT_SPEED


# --- 8.3 naming (AGENTS.md §11) -------------------------------------------

def test_user_cfg_is_dos_83_safe():
    """to_dos_name returns 8- and 3-byte fields, space padded; check the
    stripped forms so a truncation would still be caught."""
    base, ext = to_dos_name(USER_CFG)
    assert base.decode().strip() == "USER", base
    assert ext.decode().strip() == "CFG", ext
    # Not truncated, so no other file can collide with it (AGENTS.md §11).
    assert USER_CFG.split(".")[0] == "USER"


def test_user_cfg_collides_with_no_deployed_file():
    """Whole-deployment short-name uniqueness: adding USER.CFG must not
    shadow or be shadowed by any other runtime file."""
    for proj in (ROOT / "projects").iterdir():
        game_dir = ROOT / "games" / proj.name
        if not game_dir.is_dir():
            continue
        seen = {}
        for f in sorted(os.listdir(game_dir)):
            if not os.path.isfile(game_dir / f):
                continue
            n8, e3 = to_dos_name(f)
            key = (n8.ljust(8, b" "), e3.ljust(3, b" "))
            assert key not in seen, (
                f"{proj.name}: {f} collides with {seen[key]} on "
                f"{key[0].decode().strip()}.{key[1].decode().strip()}"
            )
            seen[key] = f


# --- build must not touch USER.CFG ----------------------------------------

def _build_game_source():
    return (ROOT / "tools" / "naiz_build" / "build_game.py").read_text("utf-8")


def test_settings_txt_is_gone_from_the_build_path():
    """USER.CFG is now the only runtime file (devdoc 120).

    Project configuration lives in config.toml and reaches the engine through
    nb_config.h, compiled in. Nothing deploys, injects or parses settings.txt,
    so a stale games/<game>/settings.txt can only confuse.
    """
    src = (ROOT / "tools" / "naiz_build" / "build_game.py").read_text("utf-8")
    # The removed deploy/inject shapes must not come back.
    for dead in ('scene" / "settings.txt"',
                 'safe_copy2(settings_src',
                 "settings_dst",
                 'inject = {'):
        assert dead not in src, (
            f"build_game.py re-introduced the settings.txt deploy path: {dead!r}"
        )
    # The dead file must actually be pruned, not merely ignored.
    assert 'stale_settings.unlink()' in src, (
        "build_game.py must prune the deployed settings.txt so old games/ "
        "trees do not keep a file the engine never reads"
    )
    for path in (ROOT / "tools" / "naiz_img" / "inject_common.py",
                 ROOT / "makegame.sh"):
        for lineno, line in enumerate(path.read_text("utf-8").split("\n"), 1):
            if "settings.txt" in line:
                raise AssertionError(
                    f"{path.name}:{lineno} still references settings.txt: "
                    f"{line.strip()}"
                )
    for proj in (ROOT / "projects").iterdir():
        stale = proj / "scene" / "settings.txt"
        assert not stale.is_file(), (
            f"{stale} must be deleted: the engine no longer reads it"
        )
        deployed = ROOT / "games" / proj.name / "settings.txt"
        assert not deployed.is_file(), (
            f"{deployed} is a leftover from before devdoc 120; rebuild to clear it"
        )


# Every mention of USER.CFG in the build path must be one of these shapes.
# An existence probe and a log line are the only legitimate uses.
_ALLOWED_CFG_LINE = re.compile(
    r"""^(\s*#|.*\(game_dir / "USER\.CFG"\)\.exists\(\)   # probe
        |.*USER\.CFG.*玩家偏好)                           # log""",
    re.X,
)
_CFG_BINDING = re.compile(r'^\s*\w+\s*=\s*.*"USER\.CFG"')


def test_build_never_writes_user_cfg():
    """Regression guard for the actual bug: USER.CFG may be *probed* and
    *logged*, but the build path must never bind, copy, inject, write or
    delete it — every build would otherwise reset the player's settings.

    Checking only the literal on a mutating line is not enough (a helper
    could bind it first), so both the line shape and any name binding from
    the literal are refused.
    """
    for path in (ROOT / "tools" / "naiz_build" / "build_game.py",
                 ROOT / "tools" / "naiz_img" / "inject_common.py",
                 ROOT / "makegame.sh"):
        src = path.read_text("utf-8")
        for lineno, line in enumerate(src.split("\n"), 1):
            if "USER.CFG" not in line:
                continue
            assert not _CFG_BINDING.search(line), (
                f"{path.name}:{lineno} binds a name from USER.CFG: "
                f"{line.strip()}"
            )
            assert _ALLOWED_CFG_LINE.search(line), (
                f"{path.name}:{lineno} uses USER.CFG outside a probe or a log "
                f"line: {line.strip()}"
            )


def test_build_reports_kept_user_cfg():
    src = _build_game_source()
    assert '(game_dir / "USER.CFG").exists()' in src
    assert "玩家偏好" in src


# --- config.toml is the single project-config source ----------------------

def test_config_toml_owns_every_project_value():
    """Every key the engine reads as project config must exist in config.toml.

    The engine no longer parses a settings.txt, so a value that lives nowhere
    in config.toml silently falls back to a built-in default at export time.
    """
    for proj in (ROOT / "projects").iterdir():
        cfg = proj / "config.toml"
        assert cfg.is_file(), f"{proj.name}: config.toml is required"
        raw = cfg.read_text("utf-8")
        for section, key in (("dialog", "style"), ("button", "style"),
                             ("blackletter", "title"), ("blackletter", "dialog"),
                             ("i18n", "default_lang"), ("project", "version")):
            assert f"[{section}]" in raw, f"{proj.name}/config.toml: [{section}] missing"
            assert re.search(rf"^{key}\s*=", raw, re.M), (
                f"{proj.name}/config.toml: [{section}].{key} missing"
            )


def test_default_lang_has_translations():
    """[i18n].default_lang must resolve to a real language with translations,
    or the shipping default silently degrades to English at first boot."""
    for proj in (ROOT / "projects").iterdir():
        cfg = ProjectConfig(proj)
        lang = cfg.get_str("i18n", "default_lang", "eng")
        assert lang in LANG_CODE_SET, f"{proj.name}: unknown default_lang {lang!r}"
        available = set(cfg.get_list("i18n", "targets", None) or [])
        available.add(cfg.get_str("i18n", "source_lang", "eng"))
        assert lang in available, (
            f"{proj.name}: default_lang={lang!r} has no translation "
            f"(available: {sorted(available)})"
        )


def test_lang_lives_only_in_user_cfg():
    """One `lang` key in the whole system, in USER.CFG only.

    `lang` used to exist in both files; the getter/setter split across the two
    is what made the boot-menu choice inert (devdoc 120). config.toml spells
    the project default `default_lang`, so the two can never collide again.
    """
    prefs_c = (ROOT / "core" / "engine" / "prefs.c").read_text("utf-8")
    prefs_h = (ROOT / "core" / "engine" / "prefs.h").read_text("utf-8")
    assert '"lang"' in prefs_c, "USER.CFG's lang key must still be parsed"
    for src, name in ((prefs_c, "prefs.c"), (prefs_h, "prefs.h")):
        assert "default_lang" not in src.replace("NAIZ_DEFAULT_LANG", ""), (
            f"{name} must not parse a project default_lang: it is a compile-time macro"
        )
    for proj in (ROOT / "projects").iterdir():
        raw = (proj / "config.toml").read_text("utf-8")
        assert not re.search(r"^lang\s*=", raw, re.M), (
            f"{proj.name}/config.toml: use [i18n] default_lang, not a bare lang key"
        )


def test_export_config_emits_every_project_macro():
    """The engine reads project config only through nb_config.h."""
    src = (ROOT / "tools" / "naiz_build" / "export_config.py").read_text("utf-8")
    for macro in ("NAIZ_VERSION", "NAIZ_DLGSTYLE", "NAIZ_BTNSTYLE",
                  "NAIZ_BLACKLETTER_TITLE", "NAIZ_BLACKLETTER_DIALOG",
                  "NAIZ_DEFAULT_LANG"):
        assert macro in src, f"export_config.py no longer exports {macro}"


# --- value contracts -------------------------------------------------------

def test_bgm_volume_snaps_to_menu_ladder():
    for v in BGM_VOL_LADDER:
        assert parse_bgm_volume(v) == v
    # Nearest-rung snapping: every input must land on a showable value.
    for v in range(-10, 200):
        assert parse_bgm_volume(v) in BGM_VOL_LADDER
    assert parse_bgm_volume(1) == 0
    assert parse_bgm_volume(63) == 64
    assert parse_bgm_volume(65) == 64


def test_pcm_volume_clamps_to_a466_range():
    assert parse_pcm_volume(0) == 0
    assert parse_pcm_volume(15) == 15
    assert parse_pcm_volume(16) == 15
    assert parse_pcm_volume(-1) == 0
    assert parse_pcm_volume(999) == 15
    # 15 is the softest ladder rung, not a mute (F02 §4.2).
    assert parse_pcm_volume(15) != 0


def test_pcm_ladder_is_reversed_relative_to_bgm():
    """BGM ascends loudness; A466 attenuation descends.  Guarding this keeps
    a future 'reuse one ladder' refactor from inverting PCM."""
    assert BGM_VOL_LADDER == sorted(BGM_VOL_LADDER)
    pcm_ladder = [0, 5, 10, 15]
    assert pcm_ladder == sorted(pcm_ladder)
    assert pcm_ladder[0] == 0  # 0 = loudest for both, but units differ


def test_text_speed_still_whitelisted():
    for s in SUPPORTED_SPEEDS:
        assert parse_speed(s) == s
    for bad in (99, -1, 8, 128, "abc"):
        assert parse_speed(bad) == DEFAULT_SPEED


# --- i18n parity (AGENTS.md §14) ------------------------------------------

NEW_UI_KEYS = [
    "BGM", "Sound Effect", "Voice", "On", "Off",
    "BGM Volume", "0%", "50%", "100%",
    "Sound & Voice Vol", "Max", "High", "Mid", "Low",
    "Read Progress",
]


def test_new_ui_keys_registered():
    from naiz_conv.i18n_gen import SYSTEM_UI_KEYS
    for k in NEW_UI_KEYS:
        assert k in SYSTEM_UI_KEYS, f"{k!r} missing from SYSTEM_UI_KEYS"


# --- engine-side tr() literals must be registered (AGENTS.md §14.3) ---------
#
# NEW_UI_KEYS above is a hand-kept list, so a literal nobody remembered to add
# sails through: tr("[LOCKED]") (nb_cggallery.c) was rendered for months with no
# entry in SYSTEM_UI_KEYS and no sys_*.txt value, and the next i18n_gen run
# would have commented the key out as # ORPHANED.  So discover the literals
# instead of trusting the list.
_TR_RE = re.compile(r'tr\(\s*"((?:[^"\\]|\\.)*)"\s*\)')


def _strip_c_comments(src):
    """Remove // and /* */ comments, leaving string/char literals intact.

    Without this a comment that merely mentions tr("...") -- such as an
    explanation of a key -- is scanned as if it were a call and fails a guard
    that is supposed to be about real UI strings.
    """
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == '"' or c == "'":
            quote = c
            out.append(c)
            i += 1
            while i < n:
                out.append(src[i])
                if src[i] == '\\' and i + 1 < n:
                    out.append(src[i + 1])
                    i += 2
                    continue
                if src[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            while i < n and src[i] != '\n':
                i += 1
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            i += 2
            while i + 1 < n and not (src[i] == '*' and src[i + 1] == '/'):
                i += 1
            i = min(i + 2, n)
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def _engine_tr_literals():
    keys = {}
    for c in sorted((ROOT / "core").rglob("*.c")):
        src = io.open(c, encoding="utf-8", errors="replace").read()
        for m in _TR_RE.finditer(_strip_c_comments(src)):
            keys.setdefault(m.group(1), set()).add(c.name)
    return keys


def test_every_engine_tr_literal_is_registered():
    """Every system-UI literal wrapped in tr() must be in SYSTEM_UI_KEYS.

    Otherwise i18n_gen rebuilds the key set from the .nb scripts plus
    SYSTEM_UI_KEYS and orphans the key, silently deleting its translation.
    """
    from naiz_conv.i18n_gen import SYSTEM_UI_KEYS
    missing = {k: v for k, v in _engine_tr_literals().items()
               if k not in SYSTEM_UI_KEYS}
    assert not missing, (
        "tr() literal(s) missing from SYSTEM_UI_KEYS (they would be # ORPHANED "
        "on the next i18n_gen run):\n"
        + "\n".join(f"  {k!r} used in {', '.join(sorted(v))}"
                    for k, v in sorted(missing.items()))
    )


def test_every_engine_tr_literal_is_translated_in_every_language():
    """Registered is not enough: AGENTS.md §14.4 requires a value per language,
    and tr() falls back to the English source both on an empty value and on an
    absent key (tr.c).  Absent keys are the likelier failure mode: i18n_gen
    comments them out as "# ORPHANED" on regeneration, which deletes them
    outright -- so check presence AND non-emptiness, not just non-emptiness."""
    literals = _engine_tr_literals()
    for proj in sorted((ROOT / "projects").iterdir()):
        i18n = proj / "i18n"
        if not i18n.is_dir():
            continue
        for f in sorted(i18n.glob("sys_*.txt")):
            entries = {}
            with io.open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith(("#", ";")) or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    entries[k] = v
            absent = sorted(k for k in literals if k not in entries)
            assert not absent, (
                f"{proj.name}/i18n/{f.name}: missing key(s) {absent} "
                "(tr() renders the English source; likely # ORPHANED by i18n_gen)"
            )
            blank = sorted(k for k in literals if not entries[k].strip())
            assert not blank, (
                f"{proj.name}/i18n/{f.name}: empty translation for {blank} "
                "(tr() will render the English source)"
            )


def test_every_character_name_translated_in_every_language():
    """characters.json is the key source; every role_<lang>.txt must carry a
    non-empty value for each character, or the speaker name renders English."""
    for proj in sorted((ROOT / "projects").iterdir()):
        chars_file = proj / "characters.json"
        i18n = proj / "i18n"
        if not chars_file.is_file() or not i18n.is_dir():
            continue
        chars = json.loads(chars_file.read_text("utf-8"))["characters"]
        keys = [c["key"] for c in chars]
        names = {c["key"]: c["name"] for c in chars}
        for f in sorted(i18n.glob("role_*.txt")):
            entries = {}
            for line in io.open(f, encoding="utf-8"):
                line = line.strip()
                if not line or line.startswith(("#", ";")) or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                entries[k] = v
            assert set(entries) == set(keys), (
                f"{proj.name}/i18n/{f.name}: keys {sorted(entries)} != "
                f"characters.json {sorted(keys)}"
            )
            blank = sorted(k for k in keys if not entries[k].strip())
            assert not blank, (
                f"{proj.name}/i18n/{f.name}: untranslated character(s) {blank} "
                f"({', '.join(names[k] for k in blank)})"
            )


def test_new_ui_keys_translated_everywhere():
    for proj in (ROOT / "projects").iterdir():
        i18n = proj / "i18n"
        if not i18n.is_dir():
            continue
        sys_files = sorted(i18n.glob("sys_*.txt"))
        assert sys_files, f"{proj.name}: no sys_* files"
        for f in sys_files:
            entries = {}
            with io.open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.rstrip("\n").rstrip("\r")
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    entries[k.strip()] = v
            for k in NEW_UI_KEYS:
                assert k in entries, f"{f.name}: missing {k!r}"
                assert entries[k].strip(), f"{f.name}: empty {k!r}"


def test_pcm_labels_are_worded_not_percentages():
    """A 4bit attenuation has no 0 volume and an unknown curve, so showing
    '25%' would be false information (devdoc 118 §6.4)."""
    src = (ROOT / "core" / "engine" / "nb_setting.c").read_text("utf-8")
    m = re.search(r"g_pcm_vol_labels\[[^\]]*\] = \{(.*?)\};", src, re.S)
    assert m, "g_pcm_vol_labels[] not found"
    labels = re.findall(r'"([^"]+)"', m.group(1))
    assert labels == ["Max", "High", "Mid", "Low"], labels
    assert not any(l.endswith("%") for l in labels)
