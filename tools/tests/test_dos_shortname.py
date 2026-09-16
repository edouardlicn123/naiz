"""DOS 8.3 short-name hygiene for game-run files.

Guards the AGENTS rule that every file the game reads at runtime (i18n/
translations, scene scripts, deployed assets) must map to a unique 8.3
short name on the HDI.  to_dos_name truncates a base name to 8 chars, so
system_chi.txt and system_cht.txt BOTH collapse to SYSTEM_C.TXT and one
silently clobbers the other — the root cause of the "繁体字占空位" bug.
After the fix the system table files are sys_<lang>.txt (≤8-char base),
leaving role_*/game_* (exactly 8-char bases) untouched.
"""

import pytest

from naiz_lib import to_dos_name
from naiz_img.inject_common import _check_dos_collision

from naiz_font.gen_cjk_font import RUNTIME_LANGS


ROOT = Path = __import__("pathlib").Path(__file__).resolve().parent.parent.parent
PROJECTS = ROOT / "projects"


# --------------------------------------------------------- inject helper

def test_inject_collision_check_raises():
    with pytest.raises(RuntimeError, match="8.3 name collision"):
        _check_dos_collision(["system_chi.txt", "system_cht.txt"], "i18n/")


def test_inject_collision_check_accepts_unique():
    # sys_chi/sys_cht produce distinct short names after the rename fix.
    _check_dos_collision(["sys_chi.txt", "sys_cht.txt", "game_chi.txt"], "i18n/")


# ----------------------------------------------------- project i18n files

def _project_i18n_files():
    for proj in sorted(PROJECTS.iterdir()):
        i18n = proj / "i18n"
        if i18n.is_dir():
            yield proj.name, sorted(p.name for p in i18n.iterdir() if p.is_file())


def test_i18n_short_names_unique_per_project():
    for proj, files in _project_i18n_files():
        seen = {}
        for f in files:
            base8, ext3 = to_dos_name(f)
            short = (base8.ljust(8, b' '), ext3.ljust(3, b' '))
            assert short not in seen, (
                f"{proj}/i18n: '{f}' and '{seen[short]}' both map to "
                f"'{short[0].decode()}.{short[1].decode()}'"
            )
            seen[short] = f


def test_i18n_filenames_are_8_3():
    for proj, files in _project_i18n_files():
        for f in files:
            base, _, ext = f.rpartition(".")
            assert len(base) <= 8, f"{proj}/i18n/{f}: base '{base}' > 8 chars"
            assert len(ext) <= 3, f"{proj}/i18n/{f}: ext '{ext}' > 3 chars"


def test_no_legacy_system_undirected_files():
    for proj, files in _project_i18n_files():
        legacy = [f for f in files if f.startswith("system_")]
        assert not legacy, f"{proj}/i18n: legacy system_* files remain: {legacy}"


# ------------------------------------------------ engine/tool naming agree

def test_every_cjk_lang_has_unique_sys_and_role_game_files():
    for proj, files in _project_i18n_files():
        for lang in RUNTIME_LANGS:
            if lang == "eng":
                continue  # eng is the base workbook; no sys_eng.txt ships
            sys_f = f"sys_{lang}.txt"
            if sys_f in files:
                assert f"system_{lang}.txt" not in files, (
                    f"{proj}/i18n: both {sys_f} and legacy system_{lang}.txt exist"
                )
            for prefix in ("role", "game"):
                assert f"{prefix}_{lang}.txt" in files, (
                    f"{proj}/i18n: missing {prefix}_{lang}.txt (engine tr_init loads it)"
                )


# -------------------------------------------------------- scene scripts

def test_scene_scripts_are_8_3():
    for scene_dir in PROJECTS.glob("*/scene"):
        for f in scene_dir.iterdir():
            if not f.is_file():
                continue
            base, _, ext = f.name.rpartition(".")
            assert len(base) <= 8, f"{f}: base '{base}' > 8 chars"
            assert len(ext) <= 3, f"{f}: ext '{ext}' > 3 chars"