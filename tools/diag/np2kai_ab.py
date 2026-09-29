r"""
np2kai_ab.py — interactive A/B probe for NP2kai (serial + synthetic input).

Answers the question a serial trace alone cannot: "given exactly N inputs
after state X is reached, does the engine do Y?"  It boots a game in NP2kai,
captures the engine's serial log, drives the mouse/keyboard with xdotool, and
verifies whether a marker appears or stays absent during a silent window.

The tool is a READ-ONLY diagnostic.  It never touches projects/, games/ or the
HDI image: it launches the emulator through the existing
`makegame.sh test <game> --serial` path and reads the serial log that
`tools.env_setup.env_test.cmd_test_hdi` writes (`logs/serial_<game>.log`,
renamed to `*_prev<ts>.log` first so an earlier trace is not destroyed).  Note that scene resolution is archive-first
(core/engine/nb.c: nb_load prefers SCENE.DAT and falls back to loose files),
so a loose LOGO.NB injected into the image can NOT override the archived
script — preparing a custom boot scene is the caller's job (rebuild the game
data first, see devdoc 117 §6).

Every failure mode is a named gate.  A run can never report PASS unless the
emulator booted, the window was found, the target state was actually reached,
and the synthetic input was observed by the engine (b=1 samples in the log).
Skipping the last check is how a 12ms synthetic click yields a confident but
completely bogus verdict — the button was never sampled, so the measurement
proved nothing.

Usage:
    # one click must leave the post-CG dialogue page (devdoc 117 A/B)
    python -m tools.diag.np2kai_ab --game demo-a2 \
        --advance-to 'cg: id=' --target 'line\[9\]:' \
        --expect 'line\[10\]:' --clicks 1 --quiet 10

    # two clicks are required (the pre-fix behaviour)
    python -m tools.diag.np2kai_ab --game demo-a2 \
        --advance-to 'cg: id=' --target 'line\[9\]:' \
        --expect 'line\[10\]:' --clicks 2 --quiet 10 \
        --label PREFIX_CONTROL

Verdict:
    PASS   --expect appeared in the silent window after the N clicks
    HOLD   --expect did NOT appear (state kept, as intended)
    <gate> -- run invalid, verdict suppressed
"""

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.naiz_lib import PROJECT_ROOT
from tools.naiz_lib.np2kai_capture import (
    EMULATOR, find_np2kai_windows, kill_stale_emulators,
)

# Marker proving the engine finished init and entered nb_init.
BOOT_MARKER = "nb_init start"
# Marker proving the engine samples button state (mouse.c NAIZ_DEBUG line).
BTN_DOWN_MARKER = "b=1"

# Per-channel marker proving the engine actually consumed an input in the
# measurement window.  main.c logs one of these two lines on the branch it
# took; the reveal-jump decision is identical on both (main.c:165-168 mouse,
# main.c:198-201 keyboard), so either channel measures the same behaviour.
SAMPLE_MARKERS = {
    "click": BTN_DOWN_MARKER,
    "key": "[INPUT] Key confirmed",
}
# First serial chatter, used only to tell "booting" from "dead".
FIRST_CHATTER = "[MOUSE]"

# xdotool click(1) holds the button for ~12ms, which NP2kai's sampling misses
# entirely; a held press/release is the only shape the engine actually sees.
BTN_HOLD_S = 0.15

VERDICT_WIDTH = 52


def _log(msg):
    print(msg, flush=True)


def _serial_path(game):
    """The log env_test.cmd_test_hdi writes — its name is fixed there
    (serial_<hdi-stem>.log), so the probe must watch that exact path."""
    return Path(PROJECT_ROOT) / "logs" / f"serial_{Path(game).name}.log"


def _preserve(path):
    """cmd_test_hdi truncates the log, so move any previous one aside first
    instead of destroying the user's last real playthrough trace."""
    if not path.is_file():
        return None
    stamp = time.strftime("%Y%m%d_%H%M%S")
    kept = path.with_name(f"{path.stem}_prev{stamp}{path.suffix}")
    path.rename(kept)
    _log(f"[ab] previous serial log kept as {kept.name}")
    return kept


def _read(path, offset=0):
    """Read the serial log from byte offset. Binary -> latin-1 (lossless)."""
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            return fh.read().decode("latin-1", "replace")
    except OSError:
        return ""


def _mark(path):
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _wait_for(path, pattern, timeout, since=0, poll=0.25):
    """Wait until pattern appears in the window that starts at `since`.

    The window is re-scanned from `since` on every poll instead of advancing
    with the read offset: the serial log arrives in chunks, so a marker line
    can straddle a chunk boundary and a moving-offset scan misses it entirely
    (which silently made the probe click past its own marker).
    """
    rx = re.compile(pattern)
    end = time.time() + timeout
    while True:
        if rx.search(_read(path, since)):
            return True
        if time.time() >= end:
            return False
        time.sleep(poll)


def _has_xdotool():
    try:
        subprocess.run(["xdotool", "version"], capture_output=True,
                       timeout=5)
        return True
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


def _focus(wid):
    subprocess.run(["xdotool", "windowactivate", "--sync", str(wid)],
                   capture_output=True, timeout=10)
    subprocess.run(["xdotool", "windowraise", str(wid)],
                   capture_output=True, timeout=10)
    time.sleep(0.2)


def _press(win, key):
    """Send a key via XTEST, NOT `xdotool key --window`.

    `--window` uses XSendEvent, and wxWidgets drops those synthetic events, so
    the boot menu never saw the Space press.  XTEST events are delivered to
    the focused window and are indistinguishable from real input.
    """
    # keydown/keyup with an explicit hold: `xdotool key` presses and releases
    # within ~12ms, and the engine polls the BIOS keyboard port, so a press
    # that begins and ends between two polls is never seen at all.  A hold of
    # a few frames is what a human press looks like to the polling loop.
    subprocess.run(["xdotool", "keydown", "--clearmodifiers", key],
                   capture_output=True, timeout=10)
    time.sleep(BTN_HOLD_S)
    subprocess.run(["xdotool", "keyup", "--clearmodifiers", key],
                   capture_output=True, timeout=10)
def _click(win, settle):
    """Click the window centre. The point must come from the real geometry:
    a hardcoded (640,300) lands on the right border of a 640px-wide window
    and NP2kai then never samples the press."""
    wid = win["wid"]
    px = max(1, int(win.get("w", 640)) // 2)
    py = max(1, int(win.get("h", 400)) // 2)
    subprocess.run(["xdotool", "mousemove", "--window", str(wid),
                    str(px), str(py)], capture_output=True, timeout=10)
    time.sleep(0.05)
    subprocess.run(["xdotool", "mousedown", "1"], capture_output=True,
                   timeout=10)
    time.sleep(BTN_HOLD_S)
    subprocess.run(["xdotool", "mouseup", "1"], capture_output=True,
                   timeout=10)
    time.sleep(settle)


def _act(win, method, settle):
    """Deliver one advance input.

    "key" is the default: it goes through XTEST, which wxWidgets honours, and
    the reveal-jump decision under test is input-agnostic (main.c handles the
    keyboard and the mouse in the same branch), so Space measures exactly
    what a click measures.  "click" is kept for cases where only the mouse
    path is of interest, but its landing point is fragile: NP2kai's absolute
    mouse port does not always report the button.
    """
    if method == "key":
        _press(win, "space")
    else:
        _click(win, settle)
    time.sleep(settle)


def _pick_window(timeout):
    """Newest NP2kai window that still exists."""
    end = time.time() + timeout
    while time.time() < end:
        wins = find_np2kai_windows()
        if wins:
            return wins[-1]
        time.sleep(1.0)
    return None


def _strip_mouse(text, keep=60):
    """Drop the [MOUSE] spam so the remaining evidence is readable."""
    lines = [ln for ln in text.splitlines() if "[MOUSE]" not in ln]
    if len(lines) <= keep:
        return "\n".join(lines)
    return "\n".join(["  ... (%d lines elided) ..." % (len(lines) - keep)]
                     + lines[-keep:])


def preflight(game):
    """Returns (ok, gate_name, message)."""
    if not os.environ.get("DISPLAY"):
        return False, "NO_DISPLAY", "DISPLAY is unset (headless shell?)"
    if not _has_xdotool():
        return False, "NO_XDOTOOL", "xdotool not found on PATH"
    if not Path(PROJECT_ROOT, "makegame.sh").is_file():
        return False, "NO_MAKEGAME", "makegame.sh not found"
    hdi = Path(PROJECT_ROOT, "disks", f"{game}.hdi")
    if not hdi.is_file():
        # `build` only deploys the DOS tree; `make` is what injects the HDI.
        # The old message pointed at `build`, which can never create it.
        return False, "NO_HDI", (f"{hdi} not injected (run "
                                  f"'makegame.sh build {game}' then "
                                  f"'makegame.sh make {game}')")
    # Stale-HDI gate (0.3.010): booting a stale HDI runs an OLD engine and
    # every log line still looks normal, so a verdict drawn from it is invalid
    # with nothing to indicate failure.  This is what made a broken build
    # report PASS during the 0.3.009 A/B.
    engine = Path(PROJECT_ROOT, "games", game, "engine.exe")
    if engine.is_file() and hdi.stat().st_mtime < engine.stat().st_mtime:
        return False, "STALE_HDI", (f"{hdi} is older than {engine} — the "
                                    f"emulator would run the previous engine; "
                                    f"run 'makegame.sh build {game}' then "
                                    f"'makegame.sh make {game}'")
    if not Path(EMULATOR).exists():
        return False, "NO_EMULATOR", f"{EMULATOR} not installed"
    return True, "", ""


def run_probe(args):
    log_path = _serial_path(args.game)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not args.keep_log:
        _preserve(log_path)

    killed = kill_stale_emulators()
    if killed:
        _log(f"[ab] killed {killed} stale emulator instance(s)")

    proc = subprocess.Popen(
        ["bash", "makegame.sh", "test", args.game, "--serial"],
        cwd=PROJECT_ROOT, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        return _drive(args, proc, log_path)
    finally:
        kill_stale_emulators()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()


def _report(args, verdict, action_mark, log_path):
    tail = _read(log_path, action_mark)
    print("=" * VERDICT_WIDTH)
    print(f"LABEL        = {args.label}")
    print(f"TARGET after = {len(re.findall(args.target, tail))}"
          f"   (expected after {args.clicks} click(s))")
    print(f"EXPECT after = {len(re.findall(args.expect, tail))}")
    print(f"VERDICT      = {verdict}")
    print("=" * VERDICT_WIDTH)
    print("--- log since the action ([MOUSE] spam stripped) ---")
    print(_strip_mouse(tail))
    return verdict


def _drive(args, proc, log_path):
    # Phase 1 — wait for the engine to start talking, then the window.
    booted = _wait_for(log_path, re.escape(FIRST_CHATTER), 45)
    if not booted:
        return _report(args, "NOBOOT", 0, log_path)
    win = _pick_window(20)
    if not win:
        return _report(args, "NOWINDOW", 0, log_path)
    wid = win["wid"]
    _log(f"[ab] window {wid} {win['title']!r} "
         f"{win['w']}x{win['h']}+{win['x']}+{win['y']}")

    # Phase 2 — leave the boot language/settings menu.  It accepts both
    # Space/Enter/XFER (settings_menu.c) and a click on the highlighted row,
    # but xdotool's --window key events are XSendEvent synthetics that
    # wxWidgets frequently drops, so both are sent and either may win.
    _log("[ab] phase: passing boot language menu")
    passed = False
    for _ in range(args.boot_presses):
        _focus(wid)
        _press(win, "space")
        if args.input == "click":
            _click(win, 0.1)
        time.sleep(args.boot_settle)
        if re.search(re.escape(BOOT_MARKER), _read(log_path, 0)):
            passed = True
            break
    if not passed:
        _log("[ab] button-down samples seen: %d"
             % len(re.findall(re.escape(BTN_DOWN_MARKER),
                              _read(log_path, 0))))
        return _report(args, "STUCK_BOOT_MENU", 0, log_path)
    _log("[ab] engine reached nb_init")

    # Phase 3 — click forward until the state under test is reached.  The
    # marker is re-checked over the whole window accumulated since this phase
    # started, BEFORE every click, so a slow operation (a cg() blit takes
    # ~1s under NP2kai) can never be clicked past.
    _focus(wid)
    _log(f"[ab] phase: advancing to {args.advance_to!r} "
         f"(max {args.advance_clicks} clicks)")
    since = _mark(log_path)
    adv_end = -1
    for _ in range(args.advance_clicks):
        m = re.search(args.advance_to, _read(log_path, since))
        if m:
            adv_end = since + m.end()
            break
        _focus(win)
        _act(win, args.input, args.settle)
        time.sleep(args.advance_settle)
    if adv_end < 0:
        m = re.search(args.advance_to, _read(log_path, since))
        adv_end = since + m.end() if m else -1
    if adv_end < 0:
        return _report(args, "NEVER_REACHED_ADVANCE_TARGET", 0, log_path)
    _log(f"[ab] reached {args.advance_to!r}")

    # Phase 4 — the target state must appear AFTER the advance marker.  The
    # search starts at the marker's match end, not at "now": the target is
    # frequently logged while the advance sleep is still running (a cg() blit
    # takes ~1s), and starting from the current end would wait forever for an
    # occurrence that already scrolled by.
    if not _wait_for(log_path, args.target, args.target_timeout,
                     since=adv_end):
        tail = _read(log_path, adv_end)
        _log("[ab] diag: adv_end=%d size=%d tail_len=%d target_in_tail=%s"
             % (adv_end, _mark(log_path), len(tail),
                bool(re.search(args.target, tail))))
        _log("[ab] diag: tail head=%r" % tail[:120])
        return _report(args, "NEVER_REACHED_TARGET", adv_end, log_path)
    _log(f"[ab] target {args.target!r} reached")

    # Phase 5 — the measurement proper: let it settle, note the offset, then
    # apply exactly args.clicks inputs and watch the rest in silence.
    time.sleep(args.pre_settle)
    btn_before = len(re.findall(re.escape(BTN_DOWN_MARKER),
                                _read(log_path, 0)))
    action_mark = _mark(log_path)
    _log(f"[ab] phase: {args.clicks} {args.input} input(s), then {args.quiet}s silent")
    for _ in range(args.clicks):
        _focus(wid)
        _act(win, args.input, 0.15)

    # Phase 6 — silent window; the outcome is whatever shows up after the
    # action offset, so any pre-existing occurrence cannot skew the verdict.
    deadline = time.time() + args.quiet
    while time.time() < deadline:
        if re.search(args.expect, _read(log_path, action_mark)):
            break
        time.sleep(0.4)

    # Gate: the bug's deterministic signature.  Click counting alone cannot
    # see it: on a short line the typewriter finishes within ~0.6s, so a
    # first click may land after the reveal already ended and turn the page
    # even in a broken build.  What is stable is the page-open branch itself,
    # which nb_dialog.c reports as "typewriter armed (single page)" — the
    # empty-prefix repaint plus the timing-dependent swallowed click.
    forbidden = _wait_for(log_path, args.forbid, 0.0, since=adv_end)
    if forbidden:
        return _report(args, "BUG_SIGNATURE_PRESENT", adv_end, log_path)

    # Gate: if the engine never sampled an input at all, the press did not
    # reach it and the measurement is void (do not report a verdict).  The
    # sampled marker depends on the channel: a click shows up as a mouse
    # button-down sample, a key as the "[INPUT] Key confirmed" line that
    # main.c logs on the Space/Enter branch.  Gating on the mouse marker
    # alone reported a successful key run as INPUT_NOT_SAMPLED.
    sample_marker = SAMPLE_MARKERS[args.input]
    samples = len(re.findall(re.escape(sample_marker),
                             _read(log_path, action_mark)))
    if samples == 0:
        return _report(args, "INPUT_NOT_SAMPLED", action_mark, log_path)
    _log(f"[ab] inputs sampled after action: {samples}")

    appeared = bool(re.search(args.expect, _read(log_path, action_mark)))
    return _report(args, "PASS" if appeared else "HOLD",
                   action_mark, log_path)


def build_parser():
    p = argparse.ArgumentParser(
        description="NP2kai interactive A/B probe (serial + synthetic input)")
    p.add_argument("--game", required=True,
                   help="game directory name under games/ (e.g. demo-a2)")
    p.add_argument("--label", default="run", help="run label for the report")
    p.add_argument("--advance-to", required=True,
                   help="regex; click forward until it appears")
    p.add_argument("--target", required=True,
                   help="regex; the state under test (must appear on its own)")
    p.add_argument("--expect", required=True,
                   help="regex; appearing after the clicks = PASS")
    p.add_argument("--clicks", type=int, default=1,
                   help="inputs applied once the target is reached")
    p.add_argument("--forbid",
                   help="pattern that must NOT appear after --advance-to; "
                        "its presence reports BUG_SIGNATURE_PRESENT, the "
                        "deterministic A/B discriminator")
    p.add_argument("--input", choices=("key", "click"), default="key",
                   help="advance channel: XTEST Space (default) or mouse "
                        "click; both reach the same reveal-jump branch")
    p.add_argument("--advance-clicks", type=int, default=24,
                   help="max clicks spent reaching --advance-to")
    p.add_argument("--advance-settle", type=float, default=2.0,
                   help="seconds to watch for --advance-to after each click")
    p.add_argument("--target-timeout", type=float, default=15.0,
                   help="seconds to wait for --target after --advance-to")
    p.add_argument("--pre-settle", type=float, default=1.2,
                   help="quiet seconds between --target and the first click")
    p.add_argument("--settle", type=float, default=1.1,
                   help="settle seconds after each --advance-to click")
    p.add_argument("--quiet", type=float, default=10.0,
                   help="silent seconds watched after the clicks")
    p.add_argument("--boot-presses", type=int, default=14,
                   help="max Space presses to leave the boot language menu")
    p.add_argument("--boot-settle", type=float, default=0.6,
                   help="settle seconds after each boot Space press")
    p.add_argument("--keep-log", action="store_true",
                   help="append to the existing serial log instead of wiping")
    return p


def main():
    args = build_parser().parse_args()
    ok, gate, msg = preflight(args.game)
    if not ok:
        print("=" * VERDICT_WIDTH)
        print(f"VERDICT      = {gate}")
        print("=" * VERDICT_WIDTH)
        print(f"  {msg}")
        # A failed preflight makes the whole run meaningless, so it must be
        # visible to a caller: this used to `print` the code instead of
        # exiting with it, which reported success for every gate.
        sys.exit(1)
    verdict = run_probe(args)
    # Non-zero on any gate or on HOLD: the caller scripts these as an A/B, so
    # "did not behave as expected" and "run was invalid" must both be visible.
    sys.exit(0 if verdict in ("PASS",) else 1)


if __name__ == "__main__":
    main()
