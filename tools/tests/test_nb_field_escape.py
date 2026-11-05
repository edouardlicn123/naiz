"""Comma-escape semantics for NB comma-delimited fields.

A question option is written "label,var,op,delta", so a label containing a
comma needs an escape:

    question(Pick one?;Ira\\, Jr.,bond_ira,+,1)

The engine splits fields in nb_next_field() (core/engine/nb_commands.c); the
i18n extractor has to derive byte-identical keys or the string silently renders
untranslated.  naiz_lib.nb_line.next_field() is the Python mirror of that C
function, so these tests pin the contract both sides implement.

The question PROMPT (argv[0]) is never comma-split by the engine, so a comma
there is literal and must NOT be escaped -- also pinned below.
"""

from pathlib import Path

import pytest

from naiz_conv.i18n_gen import COMMON_QUESTION_OPTS, extract_texts
from naiz_lib.nb_line import next_field, parse_nb_line, split_semi

ENGINE_SRC = Path(__file__).resolve().parents[2] / "core/engine/nb_commands.c"


# --- next_field(): the Python mirror of nb_next_field() --------------------

@pytest.mark.parametrize("segment,expected", [
    # plain fields, unchanged from the pre-escape behaviour
    ("Yes,bond_ira,+,1", "Yes"),
    ("bond_ira,+,1", "bond_ira"),
    ("+,1", "+"),
    # the feature: an escaped comma stays inside the field
    (r"Ira\, Jr.,bond_ira,+,1", "Ira, Jr."),
    (r"A\, B\, C,v,o,0", "A, B, C"),
    (r",leading,v,o,0", ""),
    (r"trailing\,,v,o,0", "trailing,"),
    # "\," must not consume the following delimiter
    (r"x\,,v,o,0", "x,"),
    # an escaped backslash is a literal backslash, and does NOT shield a comma
    (r"back\\slash,v,o,0", "back\\slash"),
    (r"a\\,b,v,o,0", "a\\"),
    # unknown escapes are preserved verbatim -- no silent mangling
    (r"C:\path,v,o,0", "C:\\path"),
    (r"\n,v,o,0", "\\n"),
    # whitespace handling around the delimiter -- blanks are trimmed on both
    # sides, so "Yes ,v" and "Yes,v" resolve to one key
    ("  Yes  ,bond_ira,+,1", "Yes"),
    ("\tYes\t,v,o,0", "Yes"),
    ("   ,v,o,0", ""),
    (r"Ira\, Jr.  ,bond_ira,+,1", "Ira, Jr."),
    # an escaped comma at the very end of a field
    (r"Ira\," + ",v,o,0", "Ira,"),
])
def test_next_field_extraction(segment, expected):
    got, _rest = next_field(segment)
    assert got == expected, f"{segment!r} -> {got!r}, expected {expected!r}"


def test_next_field_returns_remainder():
    _f, rest = next_field("Yes,bond_ira,+,1")
    assert rest == "bond_ira,+,1"
    _f, rest = next_field(r"Ira\, Jr.,bond_ira,+,1")
    assert rest == "bond_ira,+,1"


def test_next_field_last_field_without_comma_not_consumed():
    """nb_next_field() returns 0 for a trailing field with no delimiter; callers
    read the remainder directly.  A label with no comma must not be invented."""
    assert next_field("Yes") == (None, "Yes")


def test_next_field_chains_over_a_full_option_segment():
    """Walk a whole 'label,var,op,delta' segment the way cmd_question does:
    three nb_next_field() calls, then the delta taken as the remainder
    (nb_question.c reads it with atoi() on the raw tail)."""
    seg = r"Ira\, Jr.,bond_ira,+,1"
    label, rest = next_field(seg)
    var, rest = next_field(rest)
    op, rest = next_field(rest)
    assert (label, var, op) == ("Ira, Jr.", "bond_ira", "+")
    delta_tail = rest.strip()
    assert delta_tail == "1"
    assert next_field(delta_tail) == (None, delta_tail)


# --- the guard can actually fail -------------------------------------------

def test_mirror_detects_an_unescaped_comma():
    """Without the escape the label truncates at the comma -- this is the bug
    the feature exists to prevent, so assert the mirror really sees it."""
    assert next_field("Ira, Jr.,bond_ira,+,1")[0] == "Ira"
    assert next_field(r"Ira\, Jr.,bond_ira,+,1")[0] == "Ira, Jr."


def test_c_implementation_declares_the_same_escapes():
    """The C parser and the Python mirror are kept in step by hand.  Pin the two
    escapes in both so one cannot drift away unnoticed."""
    body = ENGINE_SRC.read_text("utf-8").split("int nb_next_field(", 1)[1]
    body = body.split("\n}", 1)[0]
    assert "p[1] == ','" in body and "p[1] == '\\\\'" in body, (
        "nb_next_field() no longer recognises the \\, and \\\\ escapes that "
        "naiz_lib.nb_line.next_field() implements"
    )


# --- i18n extraction: keys must match what the engine looks up -------------

def _extract_one_line(line, tmp_path):
    """Run extract_texts() over a single line through the real extraction path."""
    nb = tmp_path / "scene.nb"
    nb.write_text(line + "\n", encoding="utf-8")
    return extract_texts([str(nb)])


def _question_line(opts="Ira,bond_ira,+,1;Neon,bond_neon,+,1",
                   prompt="Go with whom?"):
    return "question(%s;%s)" % (prompt, opts)


def test_question_prompt_keeps_its_commas(tmp_path):
    """argv[0] is used verbatim by the engine, so a comma in the question text
    is literal -- escaping it would break the key."""
    line = _question_line(prompt="Well, who, then?")
    _d, question, _m = _extract_one_line(line, tmp_path)
    assert "Well, who, then?" in question
    assert "Well" not in question


def test_question_option_with_escaped_comma_yields_unescaped_key(tmp_path):
    line = _question_line(opts=r"Ira\, Jr.,bond_ira,+,1")
    _d, question, menu = _extract_one_line(line, tmp_path)
    assert "Ira, Jr." in question, "key must be unescaped to match tr() lookup"
    assert r"Ira\, Jr." not in question
    assert menu == set()


def test_common_options_go_to_sys_and_story_options_to_game(tmp_path):
    line = _question_line(opts="Yes,bond_ira,+,1;Run away,go,-1")
    _d, question, menu = _extract_one_line(line, tmp_path)
    assert menu == {"Yes"}, "Yes is common vocabulary -> sys_*"
    assert "Run away" in question, "a story-specific answer -> game_*"
    assert "Run away" not in menu


def test_common_option_table_covers_the_agreed_vocabulary():
    for k in ("Yes", "No", "[Yes]", "[No]", "OK", "Cancel", "Okay",
              "Back", "Return", "Continue", "Retry", "Quit", "Exit", "Close"):
        assert k in COMMON_QUESTION_OPTS, f"{k!r} dropped from the common table"


def test_character_names_as_options_land_in_story_not_sys(tmp_path):
    """Option labels naming a character are story content, not UI vocabulary,
    even though the same word may exist in role_<lang>.txt under a lowercased
    key -- tr() looks the option up by its exact source string."""
    _d, question, menu = _extract_one_line(_question_line(), tmp_path)
    assert {"Ira", "Neon"} <= question
    assert not ({"Ira", "Neon"} & menu)


def test_extract_texts_end_to_end(tmp_path):
    nb = tmp_path / "scene.nb"
    nb.write_text(
        "question(Pick who?;Ira\\, Jr.,bond_ira,+,1;Yes,bond_neon,+,1)\n",
        encoding="utf-8")
    dialogue, question, menu = extract_texts([str(nb)])
    assert "Pick who?" in question
    assert "Ira, Jr." in question
    assert menu == {"Yes"}
    assert dialogue == set()


def test_split_semi_keeps_escaped_comma_inside_the_segment():
    raw = parse_nb_line(_question_line(opts=r"Ira\, Jr.,bond_ira,+,1")).raw
    segs = split_semi(raw)
    assert segs[0] == "Go with whom?"
    assert next_field(segs[1])[0] == "Ira, Jr."

# --- the validator must learn the same escape, and stay strict ------------
#
# nb_validator keeps its own field splitting; when the escape was added to the
# engine and to i18n_gen the validator still split on bare commas and rejected
# a perfectly legal "Ira\, Jr." label as "got 5 fields".  These tests pin the
# validator's behaviour in both directions: legal escapes pass, and genuinely
# malformed segments are still rejected.

def _validator_project(tmp_path):
    import json
    import sqlite3
    db = sqlite3.connect(str(tmp_path / "ASSETS.DB"))
    db.execute("CREATE TABLE img_map (name TEXT, type TEXT)")
    db.execute("INSERT INTO img_map VALUES ('fond', 'IMG')")
    db.commit()
    db.close()
    (tmp_path / "variables.json").write_text(
        json.dumps({"variables": [{"id": "bond", "name": "Bond", "desc": "",
                                  "initial": 0, "min": 0, "max": 100}]}),
        encoding="utf-8")
    (tmp_path / "scene").mkdir()
    for stem in ("nbook003", "nbook004"):
        (tmp_path / "scene" / f"{stem}.nb").write_text(
            "bg(normal){fond}\n", encoding="utf-8")
    return tmp_path


def _validate(tmp_path, line):
    from naiz_build import nb_validator as nv
    proj = _validator_project(tmp_path)
    nb = proj / "scene" / "nbook002.nb"
    nb.write_text(line + "\n", encoding="utf-8")
    return nv.validate_scene(nb, nv.load_reference(str(proj)))


def test_validator_accepts_escaped_comma_in_label(tmp_path):
    assert _validate(tmp_path, r"question(Pick one?;Ira\, Jr.,bond,+,1)") == []


def test_validator_rejects_unescaped_comma_in_label(tmp_path):
    """Without the escape every field shifts left: "Ira" becomes the label and
    "Jr." is then read as the VARIABLE, so the validator reports an unknown
    variable instead of accepting a silently truncated label."""
    errs = _validate(tmp_path, "question(Pick one?;Ira, Jr.,bond,+,1)")
    assert errs, "an unescaped comma must be reported"
    assert any("Jr." in e for e in errs), errs


def test_validator_rejects_short_segment_with_escaped_comma(tmp_path):
    errs = _validate(tmp_path, r"question(Pick one?;Ira\, Jr.,bond)")
    assert errs
    assert any("label,var,op,delta" in e for e in errs), errs


def test_validator_still_checks_the_var_of_an_escaped_label(tmp_path):
    """The escape must not smuggle a bad variable past the range checks."""
    errs = _validate(tmp_path, r"question(Pick one?;Ira\, Jr.,nosuchvar,+,1)")
    assert errs
    assert any("nosuchvar" in e for e in errs), errs


def test_validator_does_not_flag_inner_space_of_escaped_label(tmp_path):
    r"""' the cat' inside "Ira\, the cat" is label content, not sloppy spacing."""
    assert _validate(tmp_path, r"question(Pick one?;Ira\, the cat,bond,+,1)") == []


def test_validator_still_flags_real_stray_whitespace(tmp_path):
    errs = _validate(tmp_path, "question(Pick one?;Ira , bond , + , 1)")
    assert errs
    assert any("whitespace" in e for e in errs), errs


def test_validator_scene_target_still_resolves(tmp_path):
    """The scene branch resolves the target by walking fields rather than taking
    the last piece of a bare comma split; a normal conditional chain must still
    resolve to its trailing scene id."""
    assert _validate(tmp_path, "scene(bond,>=,1,003;bond,>=,2,004)") == []
