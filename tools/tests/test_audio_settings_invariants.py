"""Source-level invariants for devdoc 118 / 120.

These are structural guards, in the spirit of test_hdi_freshness_guard.py:
they assert the *shape* of a code path rather than re-implementing it in
Python.  Their value is that deleting the guard turns them red, so nobody
inherits a "protection" that was never checked.

1. Every audio play entry is gated by its switch — a switch that is only
   checked in the settings UI is a switch the engine ignores.
2. A disabled PCM channel releases the shared path only when it owns it.
3. A466 volume encoding is VOL6 (0xA0) | attenuation, clamped to 0..15.
4. USER.CFG is the only file prefs.c writes, and the only file it reads.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

AUDIO_C = (ROOT / "core" / "engine" / "audio.c").read_text("utf-8")
PREFS_C = (ROOT / "core" / "engine" / "prefs.c").read_text("utf-8")
HAL_AUDIO_C = (ROOT / "core" / "plat" / "hal_audio.c").read_text("utf-8")
NB_SETTING_C = (ROOT / "core" / "engine" / "nb_setting.c").read_text("utf-8")


def _func_body(src, name):
    """Text of a C function body, from its opening brace to column-0 '}'."""
    m = re.search(r"^\w[\w \*]*\b%s\s*\([^;]*?\)\s*\{" % re.escape(name),
                  src, re.M)
    if not m:
        raise AssertionError(f"function {name}() not found")
    start = m.end() - 1
    end = src.index("\n}\n", start)
    return src[start:end]


# --- 1. every play entry is gated -----------------------------------------

def test_bgm_start_gated_by_switch():
    body = _func_body(AUDIO_C, "audio_bgm_start")
    assert "g_bgm_on" in body, "audio_bgm_start does not consult the BGM switch"


def test_snd_play_gated_by_switch():
    body = _func_body(AUDIO_C, "audio_snd_play")
    assert "g_snd_on" in body, "audio_snd_play does not consult the sound switch"


def test_vc_play_gated_by_switch():
    body = _func_body(AUDIO_C, "audio_vc_play")
    assert "g_vc_on" in body, "audio_vc_play does not consult the voice switch"


def test_nb_audio_has_no_bypass_of_the_three_entries():
    """nb_audio.c must keep routing through the three public entries: a new
    direct call to pcm_play or hal_pcm_play would bypass every gate."""
    nb_audio = (ROOT / "core" / "engine" / "nb_audio.c").read_text("utf-8")
    assert "audio_bgm_start" in nb_audio
    assert "audio_snd_play" in nb_audio
    assert "audio_vc_play" in nb_audio
    for forbidden in ("pcm_play", "hal_pcm_play", "hal_midi_out"):
        assert forbidden not in nb_audio, (
            f"nb_audio.c references {forbidden}: it would bypass the switches"
        )


# --- 2. precise cut on the shared PCM path --------------------------------

def test_pcm_release_clears_channel_ownership():
    body = _func_body(AUDIO_C, "pcm_release")
    assert "g_pcm_channel = PCM_CH_NONE" in body, (
        "pcm_release leaves g_pcm_channel stale: the next disable would cut "
        "a channel that no longer owns the path"
    )


def test_pcm_play_records_channel_ownership():
    body = _func_body(AUDIO_C, "pcm_play")
    assert "g_pcm_channel = chan" in body, (
        "pcm_play must record which channel took the shared path"
    )


def test_disable_only_releases_its_own_channel():
    """Turning sound effects off must not cut a playing voice (and vice
    versa) — both share one PCM path (F02 §6.3)."""
    assert "static void pcm_disable(int chan)" in AUDIO_C
    body = _func_body(AUDIO_C, "pcm_disable")
    assert "g_pcm_channel == chan" in body, (
        "pcm_disable releases unconditionally: it would silence the other "
        "PCM channel too"
    )
    snd = _func_body(AUDIO_C, "audio_set_snd_enabled")
    vc = _func_body(AUDIO_C, "audio_set_vc_enabled")
    assert "pcm_disable(PCM_CH_SND)" in snd
    assert "pcm_disable(PCM_CH_VC)" in vc
    assert "pcm_release" not in snd, "sound switch must cut precisely, not all"
    assert "pcm_release" not in vc, "voice switch must cut precisely, not all"


def test_stop_all_still_releases_everything():
    """audio_stop_all is the scene-end silence and must not be narrowed to a
    single channel by the precise-cut refactor."""
    body = _func_body(AUDIO_C, "audio_stop_all")
    assert "pcm_release()" in body


# --- 3. A466 encoding -----------------------------------------------------

def test_pcm_volume_writes_vol6_or_attenuation():
    body = _func_body(HAL_AUDIO_C, "hal_pcm_set_volume")
    assert "PCM_VOL_PATH_PCM" in body and "PCM_VOL_ATTEN_MAX" in body
    assert re.search(r"outb\(\s*PCM_STATUS_PORT\s*,", body), (
        "hal_pcm_set_volume never writes A466"
    )
    # 0xA0 is VOL6 + zero attenuation; anything else is the wrong path.
    assert re.search(r"#define\s+PCM_VOL_PATH_PCM\s+0xA0\b", HAL_AUDIO_C)


def test_pcm_volume_clamped_to_four_bits():
    body = _func_body(HAL_AUDIO_C, "hal_pcm_set_volume")
    assert body.count("if (step < 0)") >= 1
    assert "step > PCM_VOL_ATTEN_MAX" in body
    assert re.search(r"#define\s+PCM_VOL_ATTEN_MAX\s+15\b", HAL_AUDIO_C)


def test_pcm_play_honours_the_stored_volume():
    """hal_pcm_play used to hardcode 0xA0 (always maximum)."""
    body = _func_body(HAL_AUDIO_C, "hal_pcm_play")
    assert "PCM_VOL_PATH_PCM | g_pcm_vol" in body, (
        "hal_pcm_play still forces full volume, ignoring the setting"
    )
    assert "outb(PCM_STATUS_PORT, 0xA0)" not in body


def test_a46a_bit5_is_not_called_fifosize():
    """F02 §4.4: A468 bit5 is the FIFO IRQ permit; while set, A46A is the
    interrupt-interval register.  A 'fifosize' name hides a real trap."""
    assert "PCM_CTRL_A46A_FIFO" not in HAL_AUDIO_C, (
        "the misnamed macro is back: A468 bit5 is the IRQ permit, and A46A "
        "decodes as the interrupt interval while it is set"
    )
    assert re.search(r"#define\s+PCM_CTRL_A46A_IRQ\s+0x20\b", HAL_AUDIO_C)


def test_a46a_dactrl_is_written_after_bit5_is_cleared():
    """The six-step init must drop bit5 before programming the D/A mode,
    otherwise 0x50 lands in the interrupt-interval register."""
    body = _func_body(HAL_AUDIO_C, "hal_pcm_play")
    clear_at = body.index("PCM_CTRL_OUT_EN | rate_code")
    dactrl_at = body.index("PCM_DACTRL_8BIT_MONO_R")
    assert clear_at < dactrl_at, "D/A mode is programmed before bit5 is dropped"


# --- 4. persistence target ------------------------------------------------

def test_prefs_saves_only_user_cfg():
    body = _func_body(PREFS_C, "prefs_save")
    writes = re.findall(r'fopen\(\s*"([^"]+)"\s*,\s*"w"', body)
    assert writes == ["USER.CFG"], (
        f"prefs_save must write only USER.CFG, got {writes}"
    )
    for project_key in ("dlgstyle", "btnstyle", "blacktitle", "blackdialog"):
        assert f'fprintf(f, "{project_key}=' not in body, (
            f"prefs_save still writes the build-owned key {project_key}"
        )


def test_prefs_load_reads_only_user_cfg():
    """USER.CFG is the only runtime file (devdoc 120).

    settings.txt is gone: every project-level value reaches the engine as a
    compile-time macro in nb_config.h, so there is no second file to parse and
    nothing build can overwrite a preference in.
    """
    body = _func_body(PREFS_C, "prefs_load")
    reads = re.findall(r'fopen\(\s*"([^"]+)"\s*,\s*"r"', body)
    assert reads == ["USER.CFG"], (
        f"USER.CFG must be the only file read, got {reads}"
    )
    assert '"settings.txt"' not in PREFS_C, (
        "prefs.c still references settings.txt; the file no longer exists"
    )
    for key in ("lang", "text_speed", "bgm", "snd", "vc", "bgm_vol", "pcm_vol"):
        assert f'strcmp(key, "{key}")' in body, (
            f"{key} is not read from USER.CFG"
        )


def test_prefs_lang_getter_and_setter_share_one_field():
    """The 0.3.011-0.3.013 bug, frozen (devdoc 120).

    prefs_set_lang() wrote g_pref.lang while prefs_get_lang() read a different
    struct, so a boot-menu language choice was saved and then ignored. Both
    halves of one preference must name the same field.
    """
    setter = _func_body(PREFS_C, "prefs_set_lang")
    getter = _func_body(PREFS_C, "prefs_get_lang")
    fields = re.findall(r"g_pref\.\w+", setter)
    assert fields, "prefs_set_lang must record into g_pref"
    read_field = re.search(r"return\s+g_pref\.(\w+)", getter)
    assert read_field, (
        "prefs_get_lang must return the field prefs_set_lang writes "
        f"(expected g_pref.{fields[0]})"
    )
    assert read_field.group(1) == fields[0].split(".")[1], (
        f"prefs_get_lang returns g_pref.{read_field.group(1)} but "
        f"prefs_set_lang writes {fields[0]}: the choice is saved and ignored"
    )


def test_prefs_lang_falls_back_to_project_default():
    """With no player choice, the language must come from config.toml."""
    getter = _func_body(PREFS_C, "prefs_get_lang")
    assert "NAIZ_DEFAULT_LANG" in getter, (
        "prefs_get_lang must fall back to the project's NAIZ_DEFAULT_LANG"
    )
    body = _func_body(PREFS_C, "prefs_load")
    assert "NAIZ_DEFAULT_LANG" not in body, (
        "prefs_load must not copy the default into g_pref: that would pin the "
        "shipping default into USER.CFG and freeze later default_lang changes. "
        "The fallback belongs in prefs_get_lang only."
    )


def test_prefs_uses_compile_time_project_config():
    """Project config must come from nb_config.h, never from a parsed file."""
    for macro, fn in (("NAIZ_VERSION", "prefs_get_version"),
                      ("NAIZ_BLACKLETTER_TITLE", "prefs_get_blackletter_title"),
                      ("NAIZ_BLACKLETTER_DIALOG", "prefs_get_blackletter_dialog")):
        assert macro in _func_body(PREFS_C, fn), (
            f"{fn} must return {macro} (config.toml -> nb_config.h)"
        )
    load = _func_body(PREFS_C, "prefs_load")
    assert "dlg_set_style(NAIZ_DLGSTYLE)" in load, (
        "dialog style must come from NAIZ_DLGSTYLE"
    )
    assert "btn_set_style(NAIZ_BTNSTYLE)" in load, (
        "button style must come from NAIZ_BTNSTYLE"
    )


def test_prefs_is_never_opened_for_writing():
    """No path anywhere in prefs.c may write anything but USER.CFG."""
    for m in re.finditer(r'fopen\([^)]*\)', PREFS_C):
        assert '"w"' not in m.group(0) or "USER.CFG" in m.group(0), (
            f"prefs.c opens a file for writing: {m.group(0)}"
        )
