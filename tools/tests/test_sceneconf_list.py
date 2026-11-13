"""sceneconf third field: scene-list flag (devdoc 207).

sceneconf(){title[, type[, onlist|outlist]]} — the third field marks whether a
scene is planned for the scene menu.  Default is outlist; only an explicit
"onlist" opts in.  These guards pin the engine parsing, the lifecycle reset and
the validator's rejection of unknown flags.
"""

from pathlib import Path

import re

from naiz_build import nb_validator
from naiz_build.scene_menu import build_scene_menu
from naiz_lib.nb_line import next_field, parse_nb_line

ROOT = Path(__file__).resolve().parent.parent.parent
NB_C = ROOT / "core" / "engine" / "nb.c"
NB_COMMANDS_C = ROOT / "core" / "engine" / "nb_commands.c"
DEMO_SCENE = ROOT / "projects" / "demo-a2" / "scene"


def _sceneconf_fields(line):
    """Return the brace payload fields of a sceneconf line."""
    cmd, _args, text, _raw = parse_nb_line(line)
    assert cmd == "sceneconf", line
    title, rest = next_field(text)
    if title is None:
        return [text.strip(), "", ""]
    typ, rest2 = next_field(rest)
    if typ is None:
        return [title, rest.strip(), ""]
    return [title, typ, rest2.strip()]


def test_engine_parses_third_field():
    src = NB_COMMANDS_C.read_text(encoding="utf-8")
    body = src[src.index("static void cmd_sceneconf"):]
    body = body[:body.index("\n}\n")]
    # Two field splits (title, type) and the remaining tail as the list flag.
    assert body.count("nb_next_field(") == 2
    assert "nb_set_scene_conf(" in body
    assert body.count("nb_set_scene_conf(") == 1


def test_engine_validates_but_does_not_store_list_flag():
    # 0.4.029 (devdoc 208): membership is resolved at build time by
    # tools/naiz_build/scene_menu.py, so the engine only validates the flag.
    src = NB_C.read_text(encoding="utf-8")
    assert "scene_listed" not in src
    assert '"onlist"' in src and '"outlist"' in src
    assert "unknown list flag" in src


def test_build_time_scanner_filters_onlist():
    src = (ROOT / "tools" / "naiz_build" / "scene_menu.py").read_text(encoding="utf-8")
    assert "list_flag != 'onlist'" in src
    assert "type_ not in ('', 'normal')" in src


def test_all_project_sceneconf_fields_legal():
    for nb_path in sorted(DEMO_SCENE.glob("*.nb")):
        for line in nb_path.read_text(encoding="utf-8").splitlines():
            if not line.strip().startswith("sceneconf"):
                continue
            fields = _sceneconf_fields(line)
            assert fields[2] in ("", "onlist", "outlist"), (nb_path.name, line)


def test_demo_onlist_scenes(tmp_path):
    # devdoc 209: the gallery table must equal the demo's onlist set, with the
    # nbookNNN suffix as unlock id.  Both sides are derived from the scene
    # files, so flipping a scene between onlist/outlist needs no test edit.
    onlist = set()
    for nb_path in sorted(DEMO_SCENE.glob("*.nb")):
        first = nb_path.read_text(encoding="utf-8").splitlines()[0]
        if first.startswith("sceneconf") and _sceneconf_fields(first)[2] == "onlist":
            onlist.add(nb_path.name)

    header = tmp_path / "nb_scene_menu.h"
    build_scene_menu(ROOT / "projects" / "demo-a2", DEMO_SCENE,
                     header_path=header)
    listed = set(re.findall(r'"([^"]+\.nb)"', header.read_text(encoding="utf-8")))
    assert listed == onlist, (listed, onlist)


def test_validator_rejects_bad_list_flag(tmp_path):
    ref = nb_validator.load_reference(ROOT / "projects" / "demo-a2")

    bad = tmp_path / "bad.nb"
    bad.write_text("sceneconf(){T, normal, onlst}\n", encoding="utf-8")
    errs = nb_validator.validate_scene(bad, ref)
    assert any("invalid" in e for e in errs), errs

    good = tmp_path / "good.nb"
    good.write_text("sceneconf(){T, normal, onlist}\n", encoding="utf-8")
    assert nb_validator.validate_scene(good, ref) == []
