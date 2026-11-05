#!/usr/bin/env python3
"""Render a MIDI file to WAV through the system libfluidsynth (devdocs/150).

The host already has libfluidsynth.so.2 and a GM soundfont installed, so this
binds the shared library directly with ctypes -- no sudo, no new Python
dependency, mirroring the SDL3-ctypes approach in tools/diag/np2kai_audio.py.

Purpose (devdocs/150): produce a "reference rendition" of the source MIDI for
① a human A/B listen and ② a *clean* control input for the onset detector.
The GM soundfont is NOT a PC-98 timbre reference -- timbre judgement stays with
the fmbench oracle (devdocs/136).  Host-only; nothing ships to the engine.

Usage:
    python -m tools.naiz_audio.gm_render song.mid out.wav [--rate 44100]
"""

import argparse
import ctypes
import ctypes.util
import os
import wave
from pathlib import Path

SOUNDFONT_CANDIDATES = [
    "/usr/share/sounds/sf2/TimGM6mb.sf2",
    "/usr/share/sounds/sf2/default-GM.sf2",
    "/usr/share/sounds/sf2/FluidR3_GM.sf2",
]

# fluid_player_status (fluidsynth >= 2.0)
PLAYER_READY, PLAYER_PLAYING, PLAYER_STOPPING, PLAYER_DONE = 0, 1, 2, 3


class GMRenderError(RuntimeError):
    pass


def _load_lib():
    name = ctypes.util.find_library("fluidsynth") or "libfluidsynth.so.2"
    try:
        lib = ctypes.CDLL(name)
    except OSError as exc:
        raise GMRenderError(f"libfluidsynth not loadable ({name}): {exc}")
    lib.new_fluid_settings.restype = ctypes.c_void_p
    lib.delete_fluid_settings.argtypes = [ctypes.c_void_p]
    lib.new_fluid_synth.argtypes = [ctypes.c_void_p]
    lib.new_fluid_synth.restype = ctypes.c_void_p
    lib.delete_fluid_synth.argtypes = [ctypes.c_void_p]
    lib.fluid_settings_setnum.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                          ctypes.c_double]
    lib.fluid_synth_sfload.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                       ctypes.c_int]
    lib.fluid_synth_sfload.restype = ctypes.c_int
    lib.new_fluid_player.argtypes = [ctypes.c_void_p]
    lib.new_fluid_player.restype = ctypes.c_void_p
    lib.delete_fluid_player.argtypes = [ctypes.c_void_p]
    lib.fluid_player_add.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.fluid_player_add.restype = ctypes.c_int
    lib.fluid_player_play.argtypes = [ctypes.c_void_p]
    lib.fluid_player_play.restype = ctypes.c_int
    lib.fluid_player_get_status.argtypes = [ctypes.c_void_p]
    lib.fluid_player_get_status.restype = ctypes.c_int
    lib.fluid_synth_write_s16.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
        ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.fluid_synth_write_s16.restype = ctypes.c_int
    return lib


def find_soundfont(explicit=None):
    if explicit:
        if not os.path.isfile(explicit):
            raise GMRenderError(f"soundfont not found: {explicit}")
        return explicit
    for cand in SOUNDFONT_CANDIDATES:
        if os.path.isfile(cand):
            return cand
    raise GMRenderError(
        "no GM soundfont found; install timgm6mb-soundfont or pass --sf2")


def render(midi_path, out_wav, rate=44100, sf2=None, block=1024,
           max_seconds=600.0):
    """Render midi_path to out_wav (S16 stereo).  Returns (rate, frames).

    Raises GMRenderError on any failure and if the output is silent, so a
    mis-routed render never passes as a "quiet" success (AGENTS §九.6).
    """
    lib = _load_lib()
    sf = find_soundfont(sf2)

    settings = lib.new_fluid_settings()
    if not settings:
        raise GMRenderError("new_fluid_settings failed")
    synth = lib.new_fluid_synth(settings)
    if not synth:
        lib.delete_fluid_settings(settings)
        raise GMRenderError("new_fluid_synth failed")

    player = None
    frames = []
    try:
        lib.fluid_settings_setnum(settings, b"synth.sample-rate",
                                  ctypes.c_double(rate))
        if lib.fluid_synth_sfload(synth, sf.encode(), 1) < 0:
            raise GMRenderError(f"fluid_synth_sfload failed for {sf}")
        player = lib.new_fluid_player(synth)
        if not player:
            raise GMRenderError("new_fluid_player failed")
        if lib.fluid_player_add(player, str(midi_path).encode()) != 0:
            raise GMRenderError(f"fluid_player_add failed for {midi_path}")
        if lib.fluid_player_play(player) != 0:
            raise GMRenderError("fluid_player_play failed")

        buf = (ctypes.c_int16 * (block * 2))()
        peak = 0
        n_frames = 0
        max_frames = int(max_seconds * rate)
        while lib.fluid_player_get_status(player) == PLAYER_PLAYING:
            lib.fluid_synth_write_s16(synth, block, buf, 0, 2, buf, 1, 2)
            frames.append(bytes(buf))
            n_frames += block
            peak = max(peak, max(abs(v) for v in buf))
            if n_frames >= max_frames:
                raise GMRenderError("render exceeded max_seconds (hung player?)")
        if n_frames == 0 or peak == 0:
            raise GMRenderError("rendered nothing / silence (bad sf2 or MIDI?)")
    finally:
        if player:
            lib.delete_fluid_player(player)
        lib.delete_fluid_synth(synth)
        lib.delete_fluid_settings(settings)

    pcm = b"".join(frames)
    out = Path(out_wav)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return rate, n_frames


def main():
    ap = argparse.ArgumentParser(description="Render MIDI -> WAV via libfluidsynth")
    ap.add_argument("midi")
    ap.add_argument("out")
    ap.add_argument("--rate", type=int, default=44100)
    ap.add_argument("--sf2", default=None, help="explicit soundfont path")
    args = ap.parse_args()
    try:
        rate, n = render(args.midi, args.out, rate=args.rate, sf2=args.sf2)
    except GMRenderError as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
    print(f"rendered {n} frames @ {rate} Hz -> {args.out} "
          f"({n / rate:.2f}s)")


if __name__ == "__main__":
    main()
