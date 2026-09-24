"""Command-table vs doc sync guard (devdoc 103 stage-F).

The engine command set has a single source of truth: the cmd_table in
core/engine/nb_commands.c.  The NB script command reference (docs/B92 §1)
must stay in sync with it — a new command added to the engine without a doc
row (or vice versa) drifts silently.  This test parses both sides and fails
whenever the command-name sets stop matching (mirrors test_langdefs_sync).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NB_COMMANDS_C = ROOT / "core" / "engine" / "nb_commands.c"
B92 = ROOT / "docs" / "B92-NB脚本命令参考.md"


def _cmd_table_names():
    src = NB_COMMANDS_C.read_text(encoding="utf-8")
    start = src.index("cmd_table[] = {") + len("cmd_table[] = {")
    end = src.index("};", start)
    names = set()
    for line in src[start:end].splitlines():
        m = re.search(r'\{\s*"([a-z_]+)"\s*,', line)
        if m:
            names.add(m.group(1))
    assert names, "nb_commands.c: no cmd_table rows parsed"
    return names


def _doc_command_names():
    section = B92.read_text(encoding="utf-8")
    start = section.index("## 1. NB 脚本命令参考")
    end = section.index("## 2.", start) if "## 2." in section[start:] else len(section)
    names = set()
    for line in section[start:end].splitlines():
        if not line.startswith("| "):
            continue
        cells = line.split("|")
        if len(cells) < 2:
            continue
        first = cells[1]
        toks = re.findall(r"`([a-z_/]+)`", first)
        for tok in toks:
            names.update(tok.split("/"))
    assert names, "B92: no command rows parsed"
    return names


def test_cmd_table_matches_doc():
    engine = _cmd_table_names()
    doc = _doc_command_names()
    assert engine == doc, (
        "cmd_table ↔ B92 §1 命令集漂移: "
        f"命令表独有={sorted(engine - doc)} 文档独有={sorted(doc - engine)}")


def test_expected_command_core_covered():
    engine = _cmd_table_names()
    assert {"bg", "cg", "char", "scene", "host", "question", "delay",
            "bgm", "sound", "voice", "playanima", "waitanima", "stopanima"} <= engine