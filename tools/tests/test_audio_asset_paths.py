"""Repository guards for the audio source-asset layout.

BGM/SND/VC payloads are the one asset class whose sources live under
assets/<project>/ rather than projects/<project>/: only the packed
AUDIO.DAT reaches games/<game>/, so the project directory has nothing to
do with them (pack_audio.py reads them from naiz_lib.project_assets_dir).
These tests pin that single-source-of-truth rule at the repo level, where
build_game's fail-loud exit is the last line of defence, not the first.

Deleting or loosening any assertion here lets audio sources drift back into
projects/<project>/ silently — pack_audio would then exit 1 on a missing
file only after someone noticed the wrong directory.

test_scene_audio_keys_are_registered closes the matching gap on the script
side: nb_validator only checks IMG/ANI/CG names, so a scene may reference an
audio key that no ASSETS.DB row backs.
"""

import sqlite3
from pathlib import Path

import pytest

from naiz_lib import PROJECT_ROOT, project_assets_dir, to_dos_name
from naiz_lib.nb_line import parse_nb_line

PROJECTS_DIR = Path(PROJECT_ROOT) / "projects"
# Source dirs that must never reappear under a project directory.
AUDIO_SOURCE_DIRS = ("bgm", "se", "voice")
# NB command -> the img_map type its brace payload must be registered under.
AUDIO_CMD_TYPES = {"bgm": "BGM", "sound": "SND", "voice": "VC"}


def _projects_with_audio():
    """[(project_dir, assets_dir, rows)] for every project with audio rows."""
    found = []
    for proj in sorted(PROJECTS_DIR.iterdir()):
        db_path = proj / "ASSETS.DB"
        if not db_path.is_file():
            continue
        db = sqlite3.connect(db_path)
        try:
            rows = db.execute(
                "SELECT id, filename, type, name FROM img_map "
                "WHERE type IN ('BGM','SND','VC') ORDER BY id"
            ).fetchall()
        finally:
            db.close()
        if rows:
            found.append((proj, project_assets_dir(str(proj)), rows))
    return found


def test_audio_sources_live_under_assets_project_dir():
    """Every BGM/SND/VC row resolves to a real file under assets/<project>/."""
    projects = _projects_with_audio()
    assert projects, "no project registers audio assets; guard would be vacuous"
    for proj, assets_dir, rows in projects:
        assert Path(assets_dir) == Path(PROJECT_ROOT) / "assets" / proj.name
        for _id, filename, asset_type, name in rows:
            path = Path(assets_dir) / filename
            assert path.is_file(), (
                f"{proj.name}: {asset_type} row {filename!r} does not resolve "
                f"under the source root: {path}")


@pytest.mark.parametrize("dirname", AUDIO_SOURCE_DIRS)
def test_no_audio_source_dirs_under_projects(dirname):
    """projects/<game>/{bgm,se,voice} must not exist — sources moved out."""
    stale = [p.name for p in sorted(PROJECTS_DIR.iterdir())
             if (p / dirname).is_dir()]
    assert not stale, (
        f"audio sources belong under assets/<project>/, but {dirname}/ still "
        f"exists in: {', '.join(stale)}")


def test_audio_asset_names_are_83_clean_and_unique():
    """The AUDIO.DAT TOC key is the `name` column: 8.3, non-empty, unique.

    Mirrors pack_audio's per-build collision check at repo level so a bad
    name is caught by pytest rather than at build time.
    """
    projects = _projects_with_audio()
    assert projects, "no project registers audio assets; guard would be vacuous"
    for proj, _assets_dir, rows in projects:
        seen = {}
        for _id, filename, _type, name in rows:
            assert name, f"{proj.name}: {filename} has no name column"
            base8, _ext3 = to_dos_name(name)
            short = base8.rstrip(b" ").decode("ascii", errors="replace")
            assert short, f"{proj.name}: {filename} has an empty short name"
            assert short not in seen, (
                f"{proj.name}: {seen.get(short)} and {filename} both "
                f"truncate to the AUDIO.DAT TOC name {short!r}")
            seen[short] = filename


def test_project_assets_dir_keys_off_project_name():
    """The wrapper derives assets/<project>; drift here breaks every build."""
    assert project_assets_dir("/somewhere/else/demo-a2") == \
        str(Path(PROJECT_ROOT) / "assets" / "demo-a2")
    assert project_assets_dir("/somewhere/else/demo-a2", repo_root="/tmp/rt") \
        == "/tmp/rt/assets/demo-a2"


def _scene_audio_keys(proj):
    """[(scene_name, lineno, cmd, key)] for one project's scenes.

    Parsing goes through naiz_lib.nb_line so the brace payload is read with
    the same single implementation the engine and i18n_gen use (AGENTS.md
    §14.9: comma semantics must not be re-derived).  Keyword forms such as
    bgm(stop) carry no brace payload and yield an empty key, dropped here.
    """
    scene_dir = proj / "scene"
    if not scene_dir.is_dir():
        return []
    found = []
    for nb in sorted(scene_dir.glob("*.nb")):
        text = nb.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            parsed = parse_nb_line(line)
            if parsed is None or parsed.cmd not in AUDIO_CMD_TYPES:
                continue
            key = (parsed.text or "").strip()
            if key:
                found.append((nb.name, lineno, parsed.cmd, key))
    return found


def test_scene_audio_keys_are_registered():
    """Every bgm/sound/voice key a scene plays must exist in ASSETS.DB.

    nb_validator.py loads only the IMG/ANI/CG name sets, so an unregistered
    audio key passes lint and `build` untouched and surfaces at runtime as a
    single "BGM WARN: 'x' is not a registered BGM asset" serial line — the
    silent-failure mode AGENTS.md §9.6 ranks worse than a hard error.
    """
    registered = {}
    for proj, _assets_dir, rows in _projects_with_audio():
        registered[proj.name] = {(name, asset_type)
                                 for _id, _filename, asset_type, name in rows}

    checked = 0
    for proj in sorted(PROJECTS_DIR.iterdir()):
        keys = _scene_audio_keys(proj)
        if not keys:
            continue
        checked += len(keys)
        assert proj.name in registered, (
            f"{proj.name}: scenes play audio but ASSETS.DB registers no "
            f"BGM/SND/VC rows")
        bad = [f"{scene}:{lineno}: {cmd}(){{'{key}'}} has no "
               f"{AUDIO_CMD_TYPES[cmd]} row named '{key}'"
               for scene, lineno, cmd, key in keys
               if (key, AUDIO_CMD_TYPES[cmd]) not in registered[proj.name]]
        assert not bad, (
            f"{proj.name}: audio keys used in scenes but not registered in "
            f"ASSETS.DB:\n  " + "\n  ".join(bad))
    assert checked, "no scene plays audio; guard would be vacuous"