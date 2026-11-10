"""devdoc 205 §15.1: string-variable generation and slot mapping guards.

`myname` must stay a genuine string variable in the generated tables; a
silent fallback to the integer-only layout would break the rename page.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PROJ = ROOT / "projects" / "demo-a2"
TABLE = ROOT / "core" / "engine" / "nb_var_table.h"
DEFS = ROOT / "core" / "engine" / "nb_var_defs.h"
CHARS = PROJ / "characters.json"


def _read(path):
    return path.read_text(encoding="utf-8")


def _variables():
    return json.loads(_read(PROJ / "variables.json"))["variables"]


def test_variables_json_declares_myname_as_string():
    vars_by_id = {v["id"]: v for v in _variables()}
    assert "myname" in vars_by_id, "myname is missing from variables.json"
    myname = vars_by_id["myname"]
    assert myname.get("type") == "string", "myname must be type=string"
    assert myname.get("initial") == "me", "myname default must be 'me'"


def test_generated_table_has_one_string_slot():
    src = _read(TABLE)
    m = re.search(r"#define\s+NB_STRVAR_COUNT\s+(\d+)", src)
    assert m, "NB_STRVAR_COUNT missing from nb_var_table.h"
    assert int(m.group(1)) == 1, "exactly one string variable is expected"


def test_var_str_slot_maps_exactly_one_string_variable():
    table = _read(TABLE)
    count_m = re.search(r"#define\s+NB_VAR_COUNT\s+(\d+)", table)
    assert count_m, "NB_VAR_COUNT missing"
    var_count = int(count_m.group(1))

    src = _read(DEFS)
    body = re.search(r"var_str_slot\[NB_VAR_COUNT\]\s*=\s*\{([^}]*)\}", src, re.S)
    assert body, "var_str_slot[] not found in nb_var_defs.h"
    slots = [int(x) for x in re.findall(r"-?\d+", body.group(1))]
    assert len(slots) == var_count, "var_str_slot[] size must match NB_VAR_COUNT"
    assert sum(1 for s in slots if s >= 0) == 1, "exactly one non-negative slot"


def test_string_defaults_fit_the_buffer():
    table = _read(TABLE)
    max_m = re.search(r"#define\s+NB_VAR_STR_MAX\s+(\d+)", table)
    assert max_m, "NB_VAR_STR_MAX missing"
    limit = int(max_m.group(1)) - 1
    for v in _variables():
        if v.get("type") != "string":
            continue
        assert len(v.get("initial", "")) <= limit, (
            f"{v['id']}: initial value exceeds NB_VAR_STR_MAX - 1"
        )
        assert v.get("maxlen", 0) <= limit, (
            f"{v['id']}: maxlen exceeds NB_VAR_STR_MAX - 1"
        )


def test_me_is_not_registered_in_characters_json():
    chars = json.loads(_read(CHARS))["characters"]
    keys = {c["key"] for c in chars}
    assert "me" not in keys, (
        "me is a reserved NB role and must not enter characters.json"
    )
