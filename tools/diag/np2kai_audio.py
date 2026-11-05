r"""
np2kai_audio.py — reliable NP2kai audio capture for offline spectrum diagnosis.

Why this exists (devdocs/141 §六.1): earlier attempts to record the emulator's
audio produced silent (near-all-zero) files, which made the runtime "engine vs
host" discrimination impossible.  The old method recorded the PulseAudio sink
`.monitor` source with `parec`; it silently captured a microphone when `default`
was not the monitor, lost the first notes to `parec` startup latency, and was
contaminated by any other PA client on the same sink.

This tool captures the emulator's *own* device stream instead, using SDL3's
`disk` audio driver: launching wxnp21kai with
`SDL_AUDIODRIVER=disk SDL_AUDIO_DISK_OUTPUT_FILE=<path>` writes exactly what
the emulator hands to the audio device as raw `S16 / 2ch / <rate>` PCM, bypassing
PulseAudio entirely.  It never touches projects/, games/ or the HDI image; it
launches through the existing `makegame.sh test <game> --serial` path and reads
the serial log that path writes (`logs/serial_<game>.log`).

Every run is gated: a silent capture is a hard failure (non-zero exit), never a
"quiet pass" file (AGENTS §九.6 — a false pass is worse than a failure).

Usage:
    # Prove the SDL3 disk-driver capture chain works, without booting NP2kai.
    python -m tools.diag.np2kai_audio --smoke --out /tmp/smoke.raw

    # Record ~8s of the emulator's output once the serial log shows BGM start.
    python -m tools.diag.np2kai_audio --game demo-a2 \
        --after 'BGM' --duration 8 --out logs/audio_demo-a2.raw
"""

import argparse
import ctypes
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

# Marker proving the engine finished init and the window is up.  The engine
# logs "bootmenu: enter" once the boot menu is drawn; np2kai_ab's "nb_init
# start" is not emitted by the current engine build, so accept either.
BOOT_MARKER = r"(nb_init start|bootmenu: enter)"
# RMS below this (in 16-bit units) counts as silence.  A real capture of FM
# music sits in the hundreds-to-thousands; a mis-routed/empty capture is ~0.
SILENCE_RMS = 8.0


def _log(msg):
    print(msg, flush=True)


def rms_of(path):
    """Return (rms, peak, n_samples) of a headerless S16LE file."""
    import numpy as np
    x = np.fromfile(str(path), dtype="<i2")
    if x.size == 0:
        return 0.0, 0.0, 0
    x = x.astype(np.float64)
    return float(np.sqrt((x ** 2).mean())), float(abs(x).max()), int(x.size)


def _analyze(path, rate, channels):
    """Print the devdocs/136 P1b metric set for the captured signal."""
    from tools.naiz_audio import spectrum_report as sr
    try:
        _fs, mono = sr.load(path, rate=rate, channels=channels)
        m = sr.analyze(mono, rate)
    except Exception as exc:  # analysis is best-effort, never fatal
        _log(f"[audio] analysis skipped: {exc}")
        return
    _log("[audio] metrics: " + ", ".join(f"{k}={v}" for k, v in m.items()))


def _sdl_disk_smoke(out_path):
    """Write a 0.5s 440Hz tone through the SDL3 disk driver.

    This exercises the exact mechanism the emulator capture relies on
    (SDL_OpenAudioDeviceStream + SDL disk driver), so it self-proves the chain
    without needing to boot NP2kai.
    """
    import math
    import struct

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)

    lib = ctypes.CDLL("libSDL3.so.0")

    class Fmt(ctypes.Structure):
        _fields_ = [("format", ctypes.c_uint16),
                    ("channels", ctypes.c_int),
                    ("freq", ctypes.c_int)]

    lib.SDL_InitSubSystem.argtypes = [ctypes.c_uint32]
    lib.SDL_InitSubSystem.restype = ctypes.c_bool
    lib.SDL_GetCurrentAudioDriver.restype = ctypes.c_char_p
    lib.SDL_OpenAudioDeviceStream.argtypes = [
        ctypes.c_uint32, ctypes.POINTER(Fmt), ctypes.c_void_p, ctypes.c_void_p]
    lib.SDL_OpenAudioDeviceStream.restype = ctypes.c_void_p
    lib.SDL_ResumeAudioStreamDevice.argtypes = [ctypes.c_void_p]
    lib.SDL_PutAudioStreamData.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    lib.SDL_GetAudioStreamQueued.argtypes = [ctypes.c_void_p]
    lib.SDL_GetAudioStreamQueued.restype = ctypes.c_int
    lib.SDL_DestroyAudioStream.argtypes = [ctypes.c_void_p]
    lib.SDL_QuitSubSystem.argtypes = [ctypes.c_uint32]

    if not lib.SDL_InitSubSystem(0x10):  # SDL_INIT_AUDIO
        _log("[audio] smoke: SDL_InitSubSystem(AUDIO) failed")
        return False
    drv = lib.SDL_GetCurrentAudioDriver()
    _log(f"[audio] smoke: audio driver = {drv!r}")
    if drv != b"disk":
        _log("[audio] smoke: expected the 'disk' driver; wrong env?")
        return False

    fmt = Fmt(0x8010, 2, 44100)  # SDL_AUDIO_S16, stereo, 44.1k
    stream = lib.SDL_OpenAudioDeviceStream(
        0xFFFFFFFF, ctypes.byref(fmt), None, None)  # DEFAULT_PLAYBACK
    if not stream:
        _log("[audio] smoke: SDL_OpenAudioDeviceStream failed")
        return False
    lib.SDL_ResumeAudioStreamDevice(stream)

    n = int(0.5 * 44100)
    buf = bytearray()
    for i in range(n):
        s = int(8000 * math.sin(2 * math.pi * 440.0 * i / 44100.0))
        buf += struct.pack("<hh", s, s)
    cbuf = (ctypes.c_char * len(buf)).from_buffer(buf)
    lib.SDL_PutAudioStreamData(stream, cbuf, len(buf))

    # Drain: wait for the queued bytes to be consumed by the disk writer.
    deadline = time.time() + 5.0
    while time.time() < deadline and lib.SDL_GetAudioStreamQueued(stream) > 0:
        time.sleep(0.05)
    time.sleep(0.2)
    lib.SDL_DestroyAudioStream(stream)
    lib.SDL_QuitSubSystem(0x10)
    return out.is_file() and out.stat().st_size > 0


def _serial_path(game):
    return Path(PROJECT_ROOT, "logs", f"serial_{game}.log")


def _read(path, offset=0):
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            return fh.read().decode("latin-1", "replace")
    except OSError:
        return ""


def _wait_for(path, pattern, timeout, since=0, poll=0.25):
    rx = re.compile(pattern)
    end = time.time() + timeout
    while True:
        if rx.search(_read(path, since)):
            return True
        if time.time() >= end:
            return False
        time.sleep(poll)


def _preserve(path):
    if not path.is_file():
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    kept = path.with_name(f"{path.stem}_prev{stamp}{path.suffix}")
    path.rename(kept)
    _log(f"[audio] previous serial log kept as {kept.name}")


def _find_window(timeout):
    """Return the newest live NP2kai window id, or None."""
    end = time.time() + timeout
    while time.time() < end:
        wins = find_np2kai_windows()
        if wins:
            return wins[-1]["wid"]
        time.sleep(1.0)
    return None


def _press_space(wid):
    """Press Space via XTEST (wxWidgets drops XSendEvent), with a hold long
    enough for the engine's polling loop to sample it (see np2kai_ab.py)."""
    subprocess.run(["xdotool", "windowactivate", "--sync", str(wid)],
                   capture_output=True, timeout=10)
    subprocess.run(["xdotool", "windowraise", str(wid)],
                   capture_output=True, timeout=10)
    subprocess.run(["xdotool", "keydown", "--clearmodifiers", "space"],
                   capture_output=True, timeout=10)
    time.sleep(0.35)
    subprocess.run(["xdotool", "keyup", "--clearmodifiers", "space"],
                   capture_output=True, timeout=10)


def preflight(game):
    """Return (ok, gate, message)."""
    if not os.environ.get("DISPLAY"):
        return False, "NO_DISPLAY", "DISPLAY is unset (headless shell?)"
    if not Path(PROJECT_ROOT, "makegame.sh").is_file():
        return False, "NO_MAKEGAME", "makegame.sh not found"
    hdi = Path(PROJECT_ROOT, "disks", f"{game}.hdi")
    if not hdi.is_file():
        return False, "NO_HDI", (f"{hdi} not injected (run 'makegame.sh "
                                  f"build {game}' then 'makegame.sh make "
                                  f"{game}')")
    engine = Path(PROJECT_ROOT, "games", game, "engine.exe")
    if engine.is_file() and hdi.stat().st_mtime < engine.stat().st_mtime:
        return False, "STALE_HDI", (f"{hdi} is older than {engine}; rebuild "
                                    f"+ re-make before trusting a capture")
    if not Path(EMULATOR).exists():
        return False, "NO_EMULATOR", f"{EMULATOR} not installed"
    return True, "", ""


def capture(args):
    log_path = _serial_path(args.game)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not args.keep_log:
        _preserve(log_path)

    killed = kill_stale_emulators()
    if killed:
        _log(f"[audio] killed {killed} stale emulator instance(s)")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)

    env = dict(os.environ)
    env["SDL_AUDIODRIVER"] = "disk"
    env["SDL_AUDIO_DISK_OUTPUT_FILE"] = str(out)

    proc = subprocess.Popen(
        ["bash", "makegame.sh", "test", args.game, "--serial"],
        cwd=PROJECT_ROOT, env=env, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True)
    start_off = 0
    try:
        if not _wait_for(log_path, BOOT_MARKER, args.boot_timeout):
            _log("[audio] emulator did not reach the boot menu before timeout")
            return out, 0, 0
        # Leave the boot menu and start the game so a scene with BGM loads.
        if args.boot_presses > 0:
            wid = _find_window(args.window_timeout)
            if wid is None:
                _log("[audio] no NP2kai window; cannot drive the boot menu")
                return out, 0, 0
            for _ in range(args.boot_presses):
                _press_space(wid)
                time.sleep(args.press_interval)
        # Leave the boot menu and advance dialog until the --after marker
        # appears (scene 001 BGM after one press; later scenes need more).
        if args.max_presses > 0:
            wid = _find_window(args.window_timeout)
            if not wid:
                _log("[audio] emulator window never appeared")
                return out, 0, 0
            pressed = 0
            for _ in range(args.max_presses):
                if re.search(args.after, _read(log_path)):
                    break
                _press_space(wid)
                time.sleep(args.press_interval)
                wid = wid or _find_window(1.0)
        if args.after and not _wait_for(log_path, args.after,
                                        args.after_timeout):
            _log(f"[audio] marker {args.after!r} never appeared")
            return out, 0, 0
        # Record the byte offset at the moment the marker fires; the disk
        # writer flushes in small chunks, so this is within a few ms.
        start_off = out.stat().st_size if out.is_file() else 0
        _log(f"[audio] recording {args.duration}s from offset {start_off} ...")
        time.sleep(args.duration)
        end_off = out.stat().st_size if out.is_file() else 0
    finally:
        kill_stale_emulators()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
    return out, start_off, end_off


def build_parser():
    p = argparse.ArgumentParser(
        description="Reliable NP2kai audio capture (SDL3 disk driver)")
    p.add_argument("--game", help="game dir under games/ (capture mode)")
    p.add_argument("--smoke", action="store_true",
                   help="write a 0.5s tone through the SDL3 disk driver and "
                        "assert non-silence; never boots the emulator")
    p.add_argument("--out", required=True, help="output raw S16LE file path")
    p.add_argument("--after", default="BGM",
                   help="serial regex; start the recording once it appears "
                        "(default: BGM)")
    p.add_argument("--duration", type=float, default=8.0,
                   help="seconds to record after the marker (default 8)")
    p.add_argument("--boot-timeout", type=float, default=60.0,
                   help="seconds to wait for the engine to reach nb_init")
    p.add_argument("--after-timeout", type=float, default=60.0,
                   help="seconds to wait for the --after marker")
    p.add_argument("--boot-presses", type=int, default=3,
                   help="Space presses after the boot menu appears, to Start "
                        "Game and reach a scene with BGM (default 3; 0 = wait "
                        "for an external driver)")
    p.add_argument("--max-presses", type=int, default=40,
                   help="max Space presses after boot to hit --after marker "
                        "(advances dialog/scene transitions; default 40)")
    p.add_argument("--press-interval", type=float, default=1.5,
                   help="seconds between boot Space presses (default 1.5)")
    p.add_argument("--window-timeout", type=float, default=20.0,
                   help="seconds to wait for the emulator window (default 20)")
    p.add_argument("--rate", type=int, default=44100,
                   help="capture sample rate (default 44100)")
    p.add_argument("--channels", type=int, default=2,
                   help="capture channel count (default 2)")
    p.add_argument("--analyze", action="store_true",
                   help="print spectrum metrics for the captured segment")
    p.add_argument("--keep-log", action="store_true",
                   help="do not preserve/rotate the previous serial log")
    return p


def main():
    args = build_parser().parse_args()

    if args.smoke:
        env_ok = os.environ.get("SDL_AUDIODRIVER") == "disk"
        if not env_ok:
            os.environ["SDL_AUDIODRIVER"] = "disk"
            os.environ["SDL_AUDIO_DISK_OUTPUT_FILE"] = str(args.out)
            _log("[audio] smoke: set SDL_AUDIODRIVER=disk in-process; re-exec")
            os.execv(sys.executable, [sys.executable, "-m",
                                      "tools.diag.np2kai_audio"] + sys.argv[1:])
        ok = _sdl_disk_smoke(args.out)
        rms, peak, n = rms_of(args.out) if ok else (0.0, 0.0, 0)
        _log(f"[audio] smoke: wrote {n} samples rms={rms:.1f} peak={peak:.0f}")
        if rms < SILENCE_RMS:
            _log("[audio] smoke FAILED: captured signal is silent")
            sys.exit(1)
        _log("[audio] smoke PASSED: SDL3 disk-driver capture chain works")
        sys.exit(0)

    if not args.game:
        _log("[audio] --game is required (or use --smoke)")
        sys.exit(1)

    ok, gate, msg = preflight(args.game)
    if not ok:
        _log(f"[audio] preflight {gate}: {msg}")
        sys.exit(1)

    out, start_off, end_off = capture(args)
    if end_off <= start_off:
        _log(f"[audio] no audio captured (offsets {start_off}..{end_off})")
        sys.exit(1)

    # Align the segment to the 16-bit frame boundary and cut it out.
    seg = Path(args.out)
    data = seg.read_bytes()[start_off - (start_off % 2):end_off - (end_off % 2)]
    seg.with_name(seg.name + ".seg").write_bytes(data)
    seg = seg.with_name(seg.name + ".seg")

    rms, peak, n = rms_of(seg)
    _log(f"[audio] captured {n} samples ({n / args.channels / args.rate:.2f}s) "
         f"rms={rms:.1f} peak={peak:.0f} -> {seg}")
    if rms < SILENCE_RMS:
        _log("[audio] FAIL: capture is silent (likely wrong source / no BGM)")
        sys.exit(1)
    if args.analyze:
        _analyze(seg, args.rate, args.channels)
    sys.exit(0)


if __name__ == "__main__":
    main()
