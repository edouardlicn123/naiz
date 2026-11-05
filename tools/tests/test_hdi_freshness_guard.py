"""HDI freshness guard (0.3.010, devdoc 117 §5 / §8).

Why this file exists
--------------------
During the 0.3.009 A/B, a deliberately broken build reported ``PASS``.  The
cause was neither the probe nor the assertion: only ``makegame.sh build`` had
been run, which deploys the DOS tree, while the emulator boots
``disks/<game>.hdi`` — the artifact ``make`` injects.  The probe therefore
measured the *previous* engine, and because a stale HDI produces completely
normal log lines, **nothing in the run looked wrong**.  A verdict drawn that
way is invalid while reporting full confidence.

Two guards now refuse that run outright:

* ``makegame.sh test`` compares the HDI against ``games/<game>/engine.exe``
  and exits 1 before launching the emulator;
* ``tools/diag/np2kai_ab.py`` ``preflight()`` returns a ``STALE_HDI`` gate.

What is asserted here
---------------------
The **guards**, not the artifact state.  A test that failed whenever
``engine.exe`` is newer than the HDI would go red on every single source edit
and would soon be skipped or ignored, which defeats the purpose.  What must
never disappear is the guard itself, so that is a hard assertion.  The state
check is opt-in via ``NAIZ_CHECK_HDI=1`` for whoever wants it, skipping when
the build artifacts are absent (same convention as
``test_palette_reserved_slots.py``).
"""

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
MAKEGAME_SH = ROOT / "makegame.sh"
PROBE_PY = ROOT / "tools" / "diag" / "np2kai_ab.py"


def _makegame_text():
    if not MAKEGAME_SH.is_file():
        pytest.skip("makegame.sh not found")
    return MAKEGAME_SH.read_text(encoding="utf-8")


def _probe_text():
    if not PROBE_PY.is_file():
        pytest.skip("tools/diag/np2kai_ab.py not found")
    return PROBE_PY.read_text(encoding="utf-8")


def test_makegame_test_branch_gates_stale_hdi():
    # The guard has to sit in the `test` subcommand and before the emulator
    # is launched; a check placed after the exec would never run.
    text = _makegame_text()
    start = text.index("    test)")
    end = text.index("    build)", start)
    branch = text[start:end]

    assert "-ot" in branch, (
        "makegame.sh test must compare the HDI against engine.exe with -ot; "
        "a stale HDI boots the previous engine and every log line still looks "
        "normal, so the run reports full confidence while measuring nothing "
        "(devdoc 117 §5)")
    assert "engine.exe" in branch, (
        "the freshness check must be against games/<game>/engine.exe — that "
        "is the file `make` injects into the HDI")
    assert "makegame.sh make" in branch, (
        "the failure message must name the injection step (`make`); `build` "
        "only deploys the DOS tree and can never refresh the HDI, which is "
        "exactly the wrong signpost that caused the original confusion")
    assert branch.index("-ot") < branch.index("test-hdi"), (
        "the guard must run before the emulator is launched, otherwise it is "
        "dead code")


def test_probe_preflight_rejects_stale_hdi():
    text = _probe_text()
    start = text.index("def preflight(")
    end = text.index("def ", start + 10)
    body = text[start:end]

    assert "STALE_HDI" in body, (
        "the probe must gate on a stale HDI; running an A/B against the "
        "previous engine is how a broken build reported PASS (0.3.009)")
    assert "engine.exe" in body and "st_mtime" in body, (
        "STALE_HDI must compare the HDI mtime against games/<game>/engine.exe")


def test_probe_gates_exit_non_zero():
    # A gate that only prints its code leaves the caller with exit status 0,
    # so scripted A/B runs treat an invalid measurement as a valid one.
    text = _probe_text()
    start = text.index("def main(")
    body = text[start:]
    preflight_block = body[body.index("preflight(args.game)"):]

    assert re.search(r"sys\.exit\(1\)", preflight_block), (
        "a failed preflight must sys.exit(1); it used to `print` the code, so "
        "every gate except two dead ones reported success")
    assert not re.search(r"print\(\s*1 if gate", body), (
        "the old `print(1 if gate in (...))` must not come back: printing an "
        "exit code does not set one")


def test_no_hdi_message_points_at_the_injection_step():
    # build != make.  Telling a user to run `build` when the HDI is missing
    # sends them through a step that cannot possibly create it.
    text = _probe_text()
    start = text.index("NO_HDI")
    segment = text[start:start + 320]
    assert "makegame.sh make" in segment, (
        "the NO_HDI message must name `makegame.sh make` (the injection "
        "step), not just `build` — `build` deploys the DOS tree and can never "
        "create the HDI, so the old signpost sent people through a step that "
        "could not possibly fix anything")


@pytest.mark.skipif(os.environ.get("NAIZ_CHECK_HDI") != "1",
                    reason="state check is opt-in: it would go red on every "
                           "source edit (see module docstring)")
def test_hdi_is_not_older_than_engine():
    # Opt-in mirror of the runtime guards, for a build host that wants the
    # artifact state in CI as well.
    for game_dir in sorted((ROOT / "games").glob("*")):
        hdi = ROOT / "disks" / f"{game_dir.name}.hdi"
        engine = game_dir / "engine.exe"
        if not hdi.is_file() or not engine.is_file():
            continue
        assert hdi.stat().st_mtime >= engine.stat().st_mtime, (
            f"{hdi} is older than {engine}: the emulator would run the "
            f"previous engine (run 'makegame.sh build {game_dir.name}' then "
            f"'makegame.sh make {game_dir.name}')")
    else:
        if not list((ROOT / "games").glob("*")):
            pytest.skip("no built projects found (run makegame.sh build first)")
