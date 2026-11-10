"""devdoc 205 §15.1: nameinput is blocking and drains input on every exit.

`CMD_BLOCKING` is documentation-only metadata (the dispatcher does not read
it), so the handler must build its own loop.  Every exit must drain the
keyboard/mouse boundary before switching scenes, or the first frame of the
next scene consumes a stale key press.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
COMMANDS = ROOT / "core" / "engine" / "nb_commands.c"
NAMEINPUT = ROOT / "core" / "engine" / "nb_nameinput.c"


def _read(path):
    return path.read_text(encoding="utf-8")


def test_nameinput_is_registered_as_blocking():
    src = _read(COMMANDS)
    m = re.search(r'\{"nameinput"\s*,\s*cmd_nameinput\s*,\s*([^}]+)\}', src)
    assert m, "nameinput is not registered in cmd_table"
    assert "CMD_BLOCKING" in m.group(1), "nameinput must be CMD_BLOCKING"


def test_every_nameinput_exit_drains_before_switching():
    src = _read(NAMEINPUT)
    assert "input_drain_boundary()" in src, (
        "nameinput must call input_drain_boundary()"
    )
    for fn, scene in (("ni_exit_start", "nbook001.nb"),
                      ("ni_exit_back", "mainmenu.nb")):
        pattern = (
            fn + r".*?input_drain_boundary\(\).*?scene_switch\(\""
            + re.escape(scene) + r"\""
        )
        assert re.search(pattern, src, re.S), (
            f"{fn} must drain input then switch to {scene}"
        )


def test_autoexit_headless_branch_exists():
    assert "#ifdef AUTOEXIT" in _read(NAMEINPUT), (
        "the headless AUTOEXIT branch is required for probe runs"
    )
