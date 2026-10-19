"""Guard tests for the makegame.sh audio-latency menu (devdoc 154).

The NP2kai SDL output path inserts silence whenever its audio queue starves.
The resulting gain modulation (AM) tracks the buffer block size
(Latencys -> np2cfg.delayms), so the only fix is a host-side emulator setting
applied by the launcher -- never by the game.  These tests pin:

  * the canonical level table (ms -> block clusters from devdoc 154),
  * that the makegame.sh menu agrees with that table (no drift),
  * that "off" leaves the emulator config untouched,
  * that a real level writes Latencys + SampleHz into wxnp21kai.toml.
"""

import os
import re
import tomllib
from pathlib import Path

from tools.naiz_lib import np2kai_capture

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAKEGAME = PROJECT_ROOT / "makegame.sh"

# Block clusters measured in devdoc 154 §二 (SampleHz = 44100).
EXPECTED_MS = {"off": None, "short": 47, "normal": 93, "long": 186, "max": 372}
EXPECTED_BLOCKS = {"short": 2048, "normal": 4096, "long": 8192, "max": 16384}


def test_level_table_matches_devdoc_154_clusters():
    got = {k: ms for k, _l, ms, _b in np2kai_capture.AUDIO_LATENCY_LEVELS}
    assert got == EXPECTED_MS, got
    blocks = {k: b for k, _l, _m, b in np2kai_capture.AUDIO_LATENCY_LEVELS
              if b is not None}
    assert blocks == EXPECTED_BLOCKS, blocks


def test_makegame_menu_matches_level_table():
    """Every Latencys value in makegame.sh must match the canonical table."""
    src = MAKEGAME.read_text(encoding="utf-8")
    src_ms = {int(m) for m in re.findall(r"Latencys=(\d+)", src)}
    assert src_ms, "makegame.sh has no Latencys= menu entries"

    table_ms = {ms for _k, _l, ms, _b in np2kai_capture.AUDIO_LATENCY_LEVELS
                if ms is not None}
    assert src_ms == table_ms, f"menu {src_ms} != table {table_ms}"


def test_makegame_exposes_audio_subcommand():
    src = MAKEGAME.read_text(encoding="utf-8")
    assert re.search(r"^\s*audio\)", src, re.M), "no `audio)` case in makegame.sh"
    assert "audio_menu" in src, "audio_menu not wired into makegame.sh"


def test_off_leaves_config_untouched(tmp_path):
    assert np2kai_capture.apply_audio_latency("off") is None
    assert not list(tmp_path.iterdir())


def test_level_writes_latencys_and_samplehz(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "wxnp21kai"
    cfg_dir.mkdir()
    cfg = cfg_dir / "wxnp21kai.toml"
    cfg.write_text("[NP21kai]\nLatencys = 93\nOther = 7\n", encoding="utf-8")

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = np2kai_capture.apply_audio_latency("long")

    assert Path(path) == cfg
    sec = tomllib.loads(cfg.read_text(encoding="utf-8"))["NP21kai"]
    assert sec["Latencys"] == 186
    assert sec["SampleHz"] == 44100
    assert sec["Other"] == 7  # unrelated keys preserved


def test_unknown_level_raises():
    try:
        np2kai_capture.apply_audio_latency("bogus")
    except ValueError:
        return
    raise AssertionError("apply_audio_latency('bogus') did not raise")
