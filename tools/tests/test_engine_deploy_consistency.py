"""Engine deploy-consistency guard (0.3.053, devdoc 165).

Why this file exists
--------------------
``makegame.sh build <game>`` re-runs ``compile_engine()``
(``tools/naiz_build/build_game.py``), which executes ``core/build.sh`` — i.e.
``make -C core``.  That ``make`` does **not** carry the diagnostic
``EXTRA_DEFS`` unless the caller exported it for the *whole* pipeline, so a
``build`` issued with a clean environment silently recompiles the engine
**without** the flag the previous build used.

Two failures were caused by exactly this, both on the Timer-B ISR work
(``NAIZ_BGM_IRQ``):

* c79 (0.3.051): ``make``-style flag builds interleaved with clean ones left
  ``a_main.o`` flagless and ``a_hal_pc98.o`` flagged — mixed objects, one
  undefined reference, a probe silently compiled away.
* c81 (0.3.053): the post-verification "restore the default engine" step left
  the *deployed* tree (``games/<game>/engine.exe``) and ``disks/<game>.hdi``
  carrying the **no-ISR** engine, so a later "the stall is still there" report
  was measured against the co-operative pump, not the interrupt pump.

The lesson is the same as ``test_hdi_freshness_guard.py``: an engine that was
not the one you think you deployed still logs perfectly normal lines, so the
verdict is invalid with no error raised.

What is asserted here
---------------------
The **invariants**, not the artifact bytes (a byte check would go red on every
source edit and be skipped):

* ``deploy_engine()`` copies the engine with ``safe_copy2`` (a byte copy), so
  the deployed tree is a faithful mirror of ``core/engine.exe`` — the property
  the opt-in state check below relies on;
* ``build`` really does recompile the engine, so the flag-through-the-pipeline
  hazard is real and cannot be assumed away;
* the ``EXTRA_DEFS`` escape hatch is documented where a builder will look for
  it (``core/Makefile``), so a flag build has a stated channel.

The state check (deployed tree == core engine) is opt-in via
``NAIZ_CHECK_DEPLOY=1`` for a build host, skipping when artifacts are absent
(same convention as ``test_palette_reserved_slots.py`` /
``test_hdi_freshness_guard.py``).
"""

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
BUILD_GAME_PY = ROOT / "tools" / "naiz_build" / "build_game.py"
MAKEFILE = ROOT / "core" / "Makefile"
MAKEGAME_SH = ROOT / "makegame.sh"


def _read(path):
    if not path.is_file():
        pytest.skip(f"{path} not found")
    return path.read_text(encoding="utf-8")


def test_deploy_engine_copies_bytes_not_timestamps():
    # The opt-in state check equates games/<game>/engine.exe with
    # core/engine.exe.  That equivalence only holds if deploy_engine() copies
    # content (safe_copy2), not just touches mtimes.
    text = _read(BUILD_GAME_PY)
    start = text.index("def deploy_engine(")
    end = text.index("\ndef ", start + 10)
    body = text[start:end]

    assert "safe_copy2" in body, (
        "deploy_engine() must copy the engine with safe_copy2 (a byte copy); "
        "a mtime-only deploy would let the deployed tree and core/engine.exe "
        "diverge, and the deploy-consistency state check would be meaningless")
    assert "engine_src" in body and "engine.exe" in body, (
        "deploy_engine() must copy core/engine.exe into the game dir")


def test_build_recompiles_the_engine():
    # If `build` did not recompile, the flag-through-pipeline hazard could not
    # exist and this guard would be guarding nothing.  Pin the mechanism.
    text = _read(BUILD_GAME_PY)
    start = text.index("def compile_engine(")
    end = text.index("\ndef ", start + 10)
    body = text[start:end]

    assert "build.sh" in body or "make" in body, (
        "compile_engine() must invoke the core build (build.sh / make); "
        "`build` recompiling the engine is the reason EXTRA_DEFS has to span "
        "the whole pipeline (devdoc 165, c79/c81)")


def test_extrad_defs_channel_is_documented():
    # A flag build needs a stated channel; core/Makefile is where a builder
    # looks.  Removing the documented hook would leave no sanctioned way to
    # build the ISR variant and invite ad-hoc edits.
    text = _read(MAKEFILE)
    assert "EXTRA_DEFS" in text, (
        "core/Makefile must expose the EXTRA_DEFS hook used to build the "
        "NAIZ_BGM_IRQ variant; without it there is no supported flag channel")


def test_makegame_build_passes_environment_to_compile():
    # `build` runs in-process (python -m build_game), so EXTRA_DEFS reaches
    # compile_engine() only because it is inherited from the environment.
    # Assert build_game is invoked as a module (subprocess would need an
    # explicit env= to be flag-aware).  This pins the mechanism the docs
    # rely on ("export EXTRA_DEFS=... then run the whole build+make").
    text = _read(MAKEGAME_SH)
    build_branch = text[text.index("    build)")::]
    build_branch = build_branch[:build_branch.index("    make)")]
    assert "naiz_build.build_game" in build_branch, (
        "makegame.sh build must invoke tools.naiz_build.build_game, the entry "
        "point that runs compile_engine() in-process and thus inherits the "
        "caller's EXTRA_DEFS")


@pytest.mark.skipif(os.environ.get("NAIZ_CHECK_DEPLOY") != "1",
                    reason="state check is opt-in: it would go red on every "
                           "source edit (see module docstring)")
def test_deployed_engine_matches_core_engine():
    # Opt-in mirror of the invariant `deploy_engine()` is supposed to
    # establish: the tree the emulator boots is the tree we just built.
    core_engine = ROOT / "core" / "engine.exe"
    if not core_engine.is_file():
        pytest.skip("core/engine.exe not built (run make -C core)")
    checked = 0
    for game_dir in sorted((ROOT / "games").glob("*")):
        deployed = game_dir / "engine.exe"
        if not deployed.is_file():
            continue
        assert deployed.read_bytes() == core_engine.read_bytes(), (
            f"{deployed} differs from core/engine.exe: the deployed engine is "
            f"not the one that was just built.  A `build` issued without "
            f"EXTRA_DEFS in the environment recompiles the engine flagless "
            f"(devdoc 165, c79/c81).  Rebuild with the intended flags exported, "
            f"then ./makegame.sh build <game> && ./makegame.sh make <game>")
        checked += 1
    if checked == 0:
        pytest.skip("no deployed projects found (run makegame.sh build first)")
