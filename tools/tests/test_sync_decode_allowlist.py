"""Sync-decode allowlist guard (devdoc 180 §五).

The engine's recurring "stutter" class is a synchronous disk read + MAG
decode landing on a visible frame (devdocs 131 / 177 §1.1 / 180): one call
costs 30-50 ms, so the frame it runs on drops 1-3 vblanks.  devdoc 177 moved
scene-start decodes behind the transition (Naiz Queue) and devdoc 180 moved
mid-script lookahead decodes into the same queue, but the *permission* to
decode synchronously is still granted per call site -- and nothing stopped a
future feature from adding a new one.

Existing contract tests pin the behaviours that were fixed; this test pins
the *population* of sync I/O call sites.  The counts below are an allowlist:
introducing an additional image_load()/mag_decode()/mag_decode_into()/
farchive_read_alloc()/file_read_all() call in any engine file fails here
until the change either

  * routes through the Naiz Queue instead (preload_push + image_prefetch,
    consumed by engine_frame_pump), or
  * is consciously allowlisted in EXPECTED below with a justification --
    queue internals, sprite-op cache reloads, UI screens and boot loaders
    are the legitimate members.

Unlisted engine files default to DENY (zero sync calls).  Comment lines
(continuation `*`, `/*`, `//`) are ignored so doc edits cannot trip the
guard; substring matching counts the definition of image_load() itself.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent.parent
ENGINE = ROOT / "core" / "engine"
LIB = ROOT / "core" / "lib"

SYMBOLS = ("image_load(", "mag_decode(", "mag_decode_into(",
           "farchive_read_alloc(", "file_read_all(")

# file name -> {symbol: expected non-comment call count}
#  - image.c: the cache loader itself (image_load's own definition line
#    counts once via substring match; mag_decode x2 = load + prefetch)
#  - layer_sprite.c / scene_display.c: cache-hit reloads on sprite ops plus
#    the deliberate sync fallback when the queue has not drained yet
#  - nb_anim.c: playback decodes each animation frame from a resident blob
#    (decode-per-frame is the animation design; the blob read is per-anim)
#  - nb_cggallery.c / nb_saveload.c / bootmenu.c: UI screens, user-triggered,
#    thumbnails decode in batch (small images) -- acceptable, not gameplay
#  - nb_scene_menu.c: UI grid, one 160x100 thumbnail per visible cell,
#    user-triggered (same class as nb_cggallery.c)
#  - audio.c: BGM fallback read (177 D6), PCM/SE read (deferred, 177 §9.3)
#  - unlisted files: DENY -- any sync call fails the test
EXPECTED = {
    "image.c": {"image_load(": 1, "mag_decode(": 2,
                "farchive_read_alloc(": 4},
    "layer_sprite.c": {"image_load(": 3},
    "scene_display.c": {"image_load(": 2},
    "nb_anim.c": {"mag_decode(": 1, "mag_decode_into(": 1},
    "nb_cggallery.c": {"image_load(": 3},
    "nb_scene_menu.c": {"image_load(": 1},
    "nb_saveload.c": {"image_load(": 1},
    "bootmenu.c": {"image_load(": 1},
    "audio.c": {"farchive_read_alloc(": 3},
    "nb.c": {},
    "main.c": {},
    "nb_commands.c": {},
    "frame.c": {},
}

# Library internals and boot-time loaders: out of the engine's stutter path
# (they run before the frame loop exists).  Everything else under core/lib
# must stay free of the symbols (they implement or must not bypass them).
LIB_EXEMPT = {"mag.c", "farchive.c", "naiz_file.c",      # primitives
              "cjk.c", "font.c", "tr.c"}                 # boot-time loaders


def _strip_comments_and_literals(line, in_block_comment):
    """Strip C comments and string/char literals from one source line.

    Returns ``(cleaned_line, still_in_block_comment)``.

    Comments (line ``//`` and block ``/* */``) must go first so that
    ``some_call(); // image_load("x");`` does not register a false positive
    on the commented-out symbol, and so ``/* image_load("x"); */`` (block
    middle line) is not counted.  String/char literal stripping prevents
    log messages such as ``NB_DEBUG("mag_decode(foo)")`` from looking like
    a real call site.
    """
    out = []
    i = 0
    n = len(line)
    while i < n:
        if in_block_comment:
            end = line.find("*/", i)
            if end == -1:
                # rest of line is inside the block comment
                return "".join(out), True
            out.append(" " * (end + 2 - i))
            i = end + 2
            in_block_comment = False
            continue

        # block comment start
        if line.startswith("/*", i):
            end = line.find("*/", i + 2)
            if end == -1:
                out.append(" " * (n - i))
                return "".join(out), True
            out.append(" " * (end + 2 - i))
            i = end + 2
            continue

        # line comment
        if line.startswith("//", i):
            break  # rest of line is comment, drop it

        # string literal
        if line[i] == '"':
            j = i + 1
            while j < n and line[j] != '"':
                if line[j] == '\\':
                    j += 2
                else:
                    j += 1
            j = min(j + 1, n)
            out.append('""')
            i = j
            continue

        # char literal
        if line[i] == "'":
            j = i + 1
            while j < n and line[j] != "'":
                if line[j] == '\\':
                    j += 2
                else:
                    j += 1
            j = min(j + 1, n)
            out.append("''")
            i = j
            continue

        out.append(line[i])
        i += 1

    return "".join(out), in_block_comment


def _call_counts(path):
    """Non-comment, non-literal occurrences of each allowlist symbol.

    Comments (both ``//`` and ``/* */``, including multi-line blocks) and
    C string/char literals are stripped before scanning so that commented-
    out or log-message versions of the symbols cannot skew the count in
    either direction (false positive or false negative).
    """
    counts = {}
    in_block = False
    for line in path.read_text(encoding="utf-8").splitlines():
        s, in_block = _strip_comments_and_literals(line, in_block)
        for sym in SYMBOLS:
            if sym in s:
                counts[sym] = counts.get(sym, 0) + 1
    return counts


def test_engine_sync_io_call_sites_match_the_allowlist():
    """Every sync read/decode call site in the engine must be a conscious
    allowlist entry.  A new call site on a gameplay frame re-introduces the
    devdoc 131/177/180 stutter class -- route it through the Naiz Queue
    (preload_push) or extend EXPECTED with a justification."""
    for c_file in sorted(ENGINE.glob("*.c")):
        expected = EXPECTED.get(c_file.name, {})
        got = _call_counts(c_file)
        for sym, n in got.items():
            assert sym in expected and n == expected[sym], (
                f"{c_file.name}: {sym} x{n} (allowlist: "
                f"{expected.get(sym, 'DENY')}).  A new sync read/decode on a "
                f"visible frame is the stutter class of devdocs 131/177/180 "
                f"-- route it through preload_push() or update EXPECTED in "
                f"test_sync_decode_allowlist.py with a justification")


def test_lib_tree_stays_free_of_engine_sync_io():
    """The decode/read primitives must not gain engine callers via the lib
    tree either; only the primitives themselves and boot-time loaders may
    reference them."""
    for c_file in sorted(LIB.glob("*.c")):
        if c_file.name in LIB_EXEMPT:
            continue
        got = _call_counts(c_file)
        assert not got, (
            f"lib/{c_file.name}: unexpected sync call {got} -- engine I/O "
            f"belongs in core/engine and must go through the allowlist")
