"""Version sync: unified bump across all projects + repo invariant.

Guards the AGENTS rule that every project must share one version number:
bump_version now writes the SAME next version to every project (max + 1),
so the only way the invariant below can fail is a manual edit or a bypass.
"""

import tomllib
from pathlib import Path

import pytest

from naiz_build.bump_version import bump_all_projects, compute_unified_version


ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# compute_unified_version pure function
# ---------------------------------------------------------------------------

def test_unified_patch_from_equal():
    assert compute_unified_version(["0.2.074", "0.2.074"]) == "0.2.075"


def test_unified_heals_drift_from_max():
    assert compute_unified_version(["0.2.075", "0.2.040"]) == "0.2.076"


def test_unified_single_project():
    assert compute_unified_version(["0.1.007"]) == "0.1.008"


def test_unified_minor_resets_patch():
    assert compute_unified_version(["0.2.074", "0.1.900"], minor=True) == "0.3.000"


def test_unified_malformed_rejected():
    with pytest.raises(ValueError):
        compute_unified_version(["0.2", "0.2.074"])


def test_unified_carries_leading_zeros():
    assert compute_unified_version(["0.1.069", "0.1.005"]) == "0.1.070"


# ---------------------------------------------------------------------------
# repo invariant: all projects must share one version number
# ---------------------------------------------------------------------------

def test_all_projects_share_one_version():
    versions = set()
    for cfg in sorted((ROOT / "projects").glob("*/config.toml")):
        with cfg.open("rb") as f:
            data = tomllib.load(f)
        versions.add((data.get("project") or {}).get("version", ""))
    assert len(versions) == 1, f"project versions diverged: {sorted(versions)}"


# ---------------------------------------------------------------------------
# write behavior: bump_all_projects unifies a drifted set in a tmpdir
# ---------------------------------------------------------------------------

def test_bump_all_projects_unifies(tmp_path):
    a = tmp_path / "gameA" / "config.toml"
    b = tmp_path / "gameB" / "config.toml"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_text('# keep this comment\n[project]\nversion = "0.2.075"\n', encoding="utf-8")
    b.write_text('[project]\nversion = "0.2.010"\n', encoding="utf-8")

    bump_all_projects(tmp_path)

    for cfg in (a, b):
        with cfg.open("rb") as f:
            data = tomllib.load(f)
        assert data["project"]["version"] == "0.2.076"
    assert "# keep this comment" in a.read_text(encoding="utf-8")


def test_bump_all_projects_minor(tmp_path):
    game = tmp_path / "solo" / "config.toml"
    game.parent.mkdir()
    game.write_text('[project]\nversion = "0.2.999"\n', encoding="utf-8")

    bump_all_projects(tmp_path, minor=True)

    with game.open("rb") as f:
        data = tomllib.load(f)
    assert data["project"]["version"] == "0.3.000"