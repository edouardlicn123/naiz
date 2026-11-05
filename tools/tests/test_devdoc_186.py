"""Audio plan consolidation contracts (devdoc 186).

devdoc 186 superseded the five docs in devdocs/模仿升级计划/ (158-162): two
items were implemented (158-D same-key BGM guard, 161 S98/FMP export tools),
the rest were parked with re-verification conditions.  These source contracts
pin the implemented half:

  1. audio_bgm_start() must carry the same-key re-entry guard BEFORE any
     event-table consumption: replaying bgm(){key} while that exact BGM is
     still playing keeps the current phase instead of restarting it
     (BGMPlayerBase onresume semantics, MIT-attributed in 186 §五).
  2. The guard must require g_bgm.active -- a stale key alone must not block
     a fresh start.
  3. The state commit must record the key, and audio_bgm_stop() must clear
     it -- otherwise a stopped BGM would still guard its key and a legitimate
     cross-scene replay (stop_all -> bgm same key) would be skipped forever.
  4. The parked plan must live in devdoc 186 and the old folder must be gone
     (the licence attribution table rode along -- it must not be lost).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
AUDIO = ROOT / "core" / "engine" / "audio.c"
DEVDOCS = ROOT / "devdocs"


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def _bgm_start_body():
    body = strip_comments(AUDIO.read_text(encoding="utf-8", errors="replace"))
    start = body.index("void audio_bgm_start(")
    return body[start:start + 3000]


def test_same_key_guard_before_state_takeover():
    body = _bgm_start_body()
    guard = body.index("g_bgm.active && strcmp(g_bgm.key, key) == 0")
    takeover = body.index("g_bgm_pre.ev && strcmp(g_bgm_pre.key, key)")
    assert guard < takeover, (
        "same-key guard must run before the preload/event-table takeover -- "
        "a guarded start must not consume the pre-parsed table")


def test_guard_requires_active_state():
    body = _bgm_start_body()
    assert "g_bgm.active && strcmp(g_bgm.key, key) == 0" in body
    assert body.index("g_bgm.active && strcmp") < body.index("g_bgm.ev = ev")


def test_key_committed_on_start_and_cleared_on_stop():
    body = strip_comments(AUDIO.read_text(encoding="utf-8", errors="replace"))
    start = body.index("void audio_bgm_start(")
    commit = body[start:start + 3000]
    assert 'snprintf(g_bgm.key, sizeof g_bgm.key, "%s", key);' in commit, (
        "audio_bgm_start must record the key it started -- the guard reads it")
    stop = body.index("void audio_bgm_stop(")
    stop_body = body[stop:stop + 1500]
    assert 'g_bgm.key[0]' in stop_body, (
        "audio_bgm_stop must clear the key -- a stopped BGM must not guard "
        "its key against a legitimate cross-scene replay")


def test_plan_folder_gone_and_186_presents_plan():
    plan_dir = DEVDOCS / "模仿升级计划"
    assert not plan_dir.exists(), (
        "devdocs/模仿升级计划/ was consolidated into devdoc 186 and deleted")
    doc = (DEVDOCS / "186-音频升级计划收敛与取舍.md").read_text(
        encoding="utf-8", errors="replace")
    for needed in ("四、暂缓项登记", "五、引用面处置", "BSD-2", "MIT",
                   "USEFMGEN"):
        assert needed in doc, f"devdoc 186 must keep the {needed} record"
