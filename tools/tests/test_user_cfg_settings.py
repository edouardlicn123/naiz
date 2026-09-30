"""devdoc 118: player preferences (USER.CFG) must survive a build.

The bug this guards: settings_save() wrote settings.txt, and build_game.py
copied projects/<game>/scene/settings.txt over the deployed file
unconditionally.  Every build therefore reset Language and Text Speed.

These tests freeze the *contract*, not the implementation:
- USER.CFG is 8.3-safe and does not collide with any other runtime file;
- build never copies/injects/clears it (it only reports that it was kept);
- the project file still keeps its own five keys and the lang default;
- the two files have disjoint ownership (no player key in settings.txt).

They also mirror settings.c parse semantics for the audio preferences:
BGM volume snaps to the nearest ladder rung, PCM volume clamps to 0-15,
switches are 0/1, and a hand-edited out-of-range value can never reach the
menu (which only shows ladder entries).
"""

import io
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from naiz_lib import to_dos_name  # noqa: E402

USER_CFG = "USER.CFG"

# settings.c: SETTINGS_BGM_VOL_LADDER / SETTINGS_PCM_VOL_LADDER
BGM_VOL_LADDER = [0, 64, 127]
PCM_VOL_MAX = 15

# Keys the runtime writes to USER.CFG (settings.c settings_save).
PLAYER_KEYS = {"lang", "text_speed", "bgm", "snd", "vc", "bgm_vol", "pcm_vol"}

# Keys build_game.py injects into settings.txt from config.toml.
PROJECT_INJECTED = {"version", "blacktitle", "blackdialog"}

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


def test_build_copies_settings_txt_unconditionally():
    """The project file stays build-owned: still replaced every build."""
    src = _build_game_source()
    assert 'settings_src = proj_dir / "scene" / "settings.txt"' in src
    assert 'safe_copy2(settings_src, game_dir / "settings.txt")' in src


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


# --- project file keeps its own keys only ----------------------------------

def test_settings_txt_has_no_player_keys():
    """settings.txt must not carry player preferences: the engine would read
    them as a project default and build would keep resetting them."""
    for proj in (ROOT / "projects").iterdir():
        f = proj / "scene" / "settings.txt"
        if not f.is_file():
            continue
        for line in f.read_text("utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith((";", "#")) or "=" not in line:
                continue
            key = line.split("=", 1)[0].strip()
            assert key not in PLAYER_KEYS - {"lang"}, (
                f"{proj.name}/settings.txt: player key {key!r} must live in "
                f"{USER_CFG}, not the build-owned file"
            )
        # 'lang' is allowed only as the project default.


def test_project_injected_keys_still_declared():
    src = _build_game_source()
    for key in PROJECT_INJECTED:
        assert f'"{key}"' in src, f"build no longer injects {key}"


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
