"""Frame-budget watchdog + transition drain-hold contracts (devdoc 185).

Capture #1 of the play-session monitor exposed a tooling trap: the DOS
GETTIME clock is chunky under NP2kai (frozen seconds, then +1000..+6000 ms
jumps), so a watchdog built on hal_wallclock_ms() reports phantom 1000 ms
"stalls" (93 in capture #1).  Capture #2 (smooth-clock watchdog) showed the
real shape: an ~48 ms emulation baseline plus 77 genuine hitches of
250-1500 ms clustering right after scene entries -- the post-cover preload
drain ran one 250-500 ms decode per visible frame.  The fix holds the
full-black transition cover until the queue drains.

These contracts pin both fixes at the source level so neither can silently
regress:

  1. vblank_wait() must measure with hal_wallclock_smooth_ms() -- the only
     real-time clock in the engine (Timer-B ISR at ~62 ticks/s in the shipped
     BGM-IRQ configuration); hal_wallclock_ms() in the watchdog body is a
     regression to the chunky clock (test 1).
  2. The watchdog must keep its 40 ms stall threshold and its 125 ms serial
     throttle (9600 baud: a record costs ~1 ms/char, unthrottled logging
     distorts the very frames it measures) (test 2).
  3. transition_tick() must hold the armed cover while preload_pending() > 0
     (the drain-hold), and the hold must be bounded (TRANSITION_HOLD_MAX) so
     a pathological queue can never cover forever (test 3).
  4. transition_start() must reset the hold counter (test 4).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RENDER = ROOT / "core" / "engine" / "render.c"
TRANSITION = ROOT / "core" / "engine" / "transition.c"


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def test_watchdog_uses_smooth_clock():
    body = strip_comments(RENDER.read_text(encoding="utf-8", errors="replace"))
    start = body.index("void vblank_wait(void)")
    fn = body[start:start + 2200]
    assert "hal_wallclock_smooth_ms()" in fn
    assert "hal_wallclock_ms()" not in fn, (
        "vblank_wait watchdog regressed to the chunky DOS clock -- capture #1 "
        "showed 93 phantom [STALL] dt=1000 records from clock jumps, not work")


def test_watchdog_threshold_and_throttle():
    body = strip_comments(RENDER.read_text(encoding="utf-8", errors="replace"))
    start = body.index("void vblank_wait(void)")
    fn = body[start:start + 2200]
    assert "dt >= 40" in fn, "stall threshold (>=2 dropped frames) missing"
    assert "125" in fn, "serial throttle (125 ms) missing -- 9600 baud backpressure"


def test_transition_holds_cover_until_drained():
    body = strip_comments(TRANSITION.read_text(encoding="utf-8", errors="replace"))
    start = body.index("void transition_tick(void)")
    fn = body[start:]
    assert re.search(r"preload_pending\(\)\s*>\s*0", fn), (
        "transition no longer holds the black cover while the preload queue "
        "drains -- post-cover stall train returns (devdoc 185 capture #2)")
    assert "TRANSITION_HOLD_MAX" in fn, "drain-hold must be bounded"
    # the hold path must NOT fall through to the sweep switch
    hold_idx = fn.index("drain-hold phase") if "drain-hold phase" in fn else \
        fn.index("preload_pending()")
    assert "return;" in fn[hold_idx:hold_idx + 400]


def test_transition_start_resets_hold():
    body = strip_comments(TRANSITION.read_text(encoding="utf-8", errors="replace"))
    start = body.index("void transition_start(")
    fn = body[start:body.index("int transition_active(void)")]
    assert "hold = 0" in fn, "stale hold counter across arms short-circuits the next hold"
