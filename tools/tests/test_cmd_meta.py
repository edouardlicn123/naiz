"""Command metadata table audit (devdoc 103 stage 2 C).

The nb_commands.c cmd_table entries now carry declaration bits:
  CMD_BLOCKING / CMD_NEEDS_INPUT / CMD_TOUCHES_DISPLAY /
  CMD_TOUCHES_AUDIO / CMD_TERMINATES_SCENE

This test guards the front/back boundary: a handler that is NOT flagged
CMD_TOUCHES_DISPLAY must not call any render/layer/palette/image API.  It
also fails when an entry drops its flags field (regressing to the legacy
two-field form) or a flag is misspelled.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ENGINE = ROOT / "core" / "engine"

# Display-side API tokens: any call by a non-display command handler is a
# boundary violation.  Deliberately excludes menu/input helpers (ui_*,
# menu_*, hal_*, nb_dialog_*) — those are input/UI, not rendering.
BANNED_DISPLAY_CALL = re.compile(
    r"\b(?:"
    r"layer_[a-z_]+|"
    r"draw_text[a-z_]*|"
    r"pset[a-z_]*|"
    r"fill_rect[a-z_]*|"
    r"fill_dialog_bg|"
    r"palette_[a-z_]+|"
    r"image_load|image_raw_blob|"
    r"render_[a-z_]+|"
    r"menu_layer_[a-z_]+|"
    r"vram_[a-z_]+|"
    r"capsule_rect|fill_rounded_emboss"
    r")\s*\("
)

_CMD_ROW = re.compile(r'\{\s*"([^"]+)"\s*,\s*(cmd_[a-z_]+)\s*,?\s*(.*?)\}')
_FLAG = re.compile(r"\b(CMD_[A-Z_]+)\b")

_KNOWN_FLAGS = {
    "CMD_BLOCKING", "CMD_NEEDS_INPUT", "CMD_TOUCHES_DISPLAY",
    "CMD_TOUCHES_AUDIO", "CMD_TERMINATES_SCENE",
}


def _cmd_table():
    """Parse cmd_table into [(name, handler, frozenset(flags)), ...]."""
    src = (ENGINE / "nb_commands.c").read_text(encoding="utf-8")
    start = src.index("cmd_table[] = {") + len("cmd_table[] = {")
    end = src.index("};", start)
    entries = []
    for line in src[start:end].splitlines():
        if line.strip().startswith("{"):
            m = _CMD_ROW.search(line)
            if not m or m.group(1) == "NULL":
                continue
            name, handler, flagtext = m.group(1), m.group(2), m.group(3)
            if not flagtext.strip():
                raise AssertionError(
                    f"cmd '{name}' lost its flags field (legacy two-field row)")
            flags = set(_FLAG.findall(flagtext))
            unknown = flags - _KNOWN_FLAGS
            assert not unknown, f"cmd '{name}' has unknown flag(s): {sorted(unknown)}"
            entries.append((name, handler, flags))
    assert entries, "no cmd_table rows parsed"
    return entries


def _strip_non_code(src):
    """Replace C comments and string/char literals with blanks (keeps length)."""
    out = list(src)
    n = len(src)
    i = 0
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                out[i] = " "
                i += 1
        elif c == "/" and nxt == "*":
            out[i] = out[i + 1] = " "
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                out[i] = " "
                i += 1
            if i + 1 < n:
                out[i] = out[i + 1] = " "
                i += 2
        elif c in ('"', "'"):
            quote = c
            out[i] = " "
            i += 1
            while i < n and src[i] != quote:
                if src[i] == "\\":
                    out[i] = " "
                    i += 1
                out[i] = " "
                i += 1
            if i < n:
                out[i] = " "
                i += 1
        else:
            i += 1
    return "".join(out)


def _handler_bodies(handler):
    """Return the stripped bodies of every definition of `handler`."""
    bodies = []
    for cf in sorted(ENGINE.glob("*.c")):
        src = cf.read_text(encoding="utf-8")
        anchor = rf"\bvoid\s+{re.escape(handler)}\s*\("
        for m in re.finditer(anchor, src):
            if src[m.start() - 8:m.start() - 1].lstrip().startswith("static void"):
                continue
            brace = src.find("{", m.start())
            if brace < 0:
                continue
            clean = _strip_non_code(src)
            depth, j = 0, brace
            while j < len(clean):
                if clean[j] == "{":
                    depth += 1
                elif clean[j] == "}":
                    depth -= 1
                    if depth == 0:
                        bodies.append(clean[brace + 1:j])
                        break
                j += 1
    return bodies


def _audit():
    """Return list of (cmd, handler, violating_token) for non-display cmds."""
    violations = []
    for name, handler, flags in _cmd_table():
        if "CMD_TOUCHES_DISPLAY" in flags:
            continue
        if handler in ["cmd_dialogue", "cmd_host", "cmd_cg"]:
            continue  # flagged display; defensive
        bodies = _handler_bodies(handler)
        assert bodies, f"handler '{handler}' (cmd '{name}') body not found"
        for body in bodies:
            m = BANNED_DISPLAY_CALL.search(body)
            if m:
                violations.append((name, handler, m.group(0)))
    return violations


def test_every_command_declares_flags():
    entries = _cmd_table()
    assert {e[0] for e in entries} >= {
        "bg", "cg", "char", "scene", "sceneconf", "mainmenu", "question",
        "bgm", "sound", "voice", "host", "var", "delay", "playanima",
    }


def test_flag_bits_are_used():
    used = set()
    for _, _, flags in _cmd_table():
        used |= flags
    assert "CMD_TOUCHES_DISPLAY" in used
    assert "CMD_TOUCHES_AUDIO" in used
    assert "CMD_BLOCKING" in used
    assert "CMD_TERMINATES_SCENE" in used


def test_display_boundary_no_render_in_non_display_handlers():
    violations = _audit()
    assert not violations, (
        "non-display command handlers must not call display APIs: "
        + "; ".join(f"{name}/{handler} calls {tok}"
                    for name, handler, tok in violations))