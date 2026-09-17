"""Audio toolchain tests (devdoc 101): wav_convert, gen_test_midi, pack_audio.

Locks the .pcm container layout (NAIZPCM magic + rate code + data), the
SMF generator byte vector the engine parse path consumes, and the
AUDIO.DAT packer rules (BGM passthrough, .pcm header validation, 8.3
collision rejection) — mirroring the SCENE.DAT pack_scenes tests.
"""

import os
import sqlite3
import struct

import pytest

from naiz_build import pack_images
from naiz_lib import image_dat
from naiz_lib.toc_archive import make_toc_archive
from naiz_audio import gen_test_midi, wav_convert, pack_audio


# ---------------------------------------------------------------------------
# wav_convert
# ---------------------------------------------------------------------------

def _make_wav(path, rate=22050, channels=1, bits=16, seconds=0.01, tone=440):
    """Build a small valid WAV file (PCM, fmt + data chunks)."""
    n = int(rate * seconds)
    if bits == 16:
        samples = b''.join(
            struct.pack('<h', int(20000 * __import__('math').sin(2 * 3.14159 * tone * i / rate)))
            for i in range(n * channels))
    else:
        samples = bytes(int(128 + 100 * __import__('math').sin(2 * 3.14159 * tone * i / rate)) & 0xFF
                        for i in range(n * channels))

    fmt = struct.pack('<HHIIHH', 1, channels, rate, rate * channels * bits // 8,
                      channels * bits // 8, bits)
    header = b'RIFF' + struct.pack('<I', 4 + (8 + len(fmt)) + (8 + len(samples))) + b'WAVE'
    header += b'fmt ' + struct.pack('<I', len(fmt)) + fmt
    header += b'data' + struct.pack('<I', len(samples)) + samples
    with open(path, 'wb') as f:
        f.write(header)


def test_wav_convert_16bit_mono_basic(tmp_path):
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.pcm"
    _make_wav(src, rate=44100, channels=1, bits=16)
    with open(src, 'rb') as f:
        rate_code, payload = wav_convert.wav_to_pcm(f, 1.0)
    assert payload[0:8] == b"NAIZPCM\x00"
    assert payload[8] == 0                  # 44100 snaps to rate code 0
    assert payload[9] == 0
    assert payload[10:16] == b"\x00" * 6
    data = payload[16:]
    assert len(data) == int(44100 * 0.01)   # 16bit mono -> same count, 8bit
    assert all(0 <= b <= 255 for b in data)


def test_wav_convert_stereo_merges(tmp_path):
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.pcm"
    _make_wav(src, rate=22050, channels=2, bits=16)
    with open(src, 'rb') as f:
        rate_code, payload = wav_convert.wav_to_pcm(f, 1.0)
    assert payload[8] == 2                  # 22050 -> rate code 2
    assert len(payload[16:]) == int(22050 * 0.01)  # stereo pairs merged


def test_wav_convert_rate_snap(tmp_path):
    src = tmp_path / "in.wav"
    _make_wav(src, rate=33075, channels=1, bits=16)
    with open(src, 'rb') as f:
        _rc, payload = wav_convert.wav_to_pcm(f, 1.0)
    assert payload[8] == 1                  # 33075 -> rate code 1


def test_wav_convert_bad_file_raises(tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"RIFF" + b"\x00" * 40)
    with open(bad, 'rb') as f:
        with pytest.raises(ValueError):
            wav_convert.wav_to_pcm(f, 1.0)


def test_wav_convert_register_asset_idempotent(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    db = sqlite3.connect(proj / "ASSETS.DB")
    db.execute("CREATE TABLE img_map (id INTEGER PRIMARY KEY, filename TEXT, "
               "type TEXT, name TEXT DEFAULT '')")
    db.commit()
    db.close()

    dst = "se/ding.pcm"
    wav_convert.register_asset(str(proj), dst, "SND", "ding")
    wav_convert.register_asset(str(proj), dst, "SND", "ding2")

    db = sqlite3.connect(proj / "ASSETS.DB")
    rows = db.execute("SELECT id, filename, type, name FROM img_map").fetchall()
    db.close()
    assert len(rows) == 1
    assert rows[0][1] == dst
    assert rows[0][2] == "SND"
    assert rows[0][3] == "ding2"


# ---------------------------------------------------------------------------
# gen_test_midi
# ---------------------------------------------------------------------------

def test_gen_test_midi_byte_vector():
    midi = gen_test_midi.build(bpm=120, program=0)
    assert midi[0:8] == b"MThd" + struct.pack('>I', 6)
    fmt, _ntrks, div = struct.unpack('>HHH', midi[8:14])
    assert fmt == 0
    assert div == 480

    trk_len = struct.unpack('>I', midi[18:22])[0]
    assert len(midi) == 22 + trk_len

    # tempo meta + program + CC7 + 3 note pairs + end-of-track
    assert midi[22:26] == b"\x00\xFF\x51\x03"
    body = midi[22 + 4 + 1 + 2 + 1 + 3:]  # after tempo us3 + pgm + cc data
    assert b"\x90" in body and b"\x80" in body
    assert midi.endswith(b"\x00\xFF\x2F\x00")


# ---------------------------------------------------------------------------
# pack_audio
# ---------------------------------------------------------------------------

def _make_project(tmp_path, assets):
    proj = tmp_path / "proj"
    proj.mkdir()
    db = sqlite3.connect(proj / "ASSETS.DB")
    db.execute("CREATE TABLE img_map (id INTEGER PRIMARY KEY, filename TEXT, "
               "type TEXT, name TEXT DEFAULT '')")
    for i, (rel, atype, name) in enumerate(assets):
        path = proj / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(rel.encode() + b"DATA" if rel.endswith(".mid") else
                         _pcm_bytes())
        db.execute("INSERT INTO img_map (id, filename, type, name) "
                   "VALUES (?,?,?,?)", (i, rel, atype, name))
    db.commit()
    db.close()
    return proj


def _pcm_bytes(rate=0):
    return b"NAIZPCM\x00" + bytes([rate, 0]) + b"\x00" * 6 + b"\x7f\x80" * 4


def test_pack_audio_roundtrip(tmp_path):
    proj = _make_project(tmp_path, [
        ("bgm/test1.mid", "BGM", "test1"),
        ("se/chime.pcm", "SND", "chime"),
        ("voice/hi.pcm", "VC", "hi"),
    ])
    out = tmp_path / "out"
    out.mkdir()
    pack_audio.pack_audio(str(proj), str(out))

    dat = (out / "AUDIO.DAT").read_bytes()
    toc = list(image_dat.iter_image_dat_toc(dat))
    assert len(toc) == 3
    names = {t[1].rstrip(b'\0').decode().upper() for t in toc}
    assert names == {"TEST1", "CHIME", "HI"}
    for _i, name, eoff, esz in toc:
        payload = dat[eoff:eoff + esz]
        assert len(payload) == esz


def test_pack_audio_pcm_header_validated(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    db = sqlite3.connect(proj / "ASSETS.DB")
    db.execute("CREATE TABLE img_map (id INTEGER PRIMARY KEY, filename TEXT, "
               "type TEXT, name TEXT DEFAULT '')")
    (proj / "se").mkdir()
    (proj / "se" / "bad.pcm").write_bytes(b"NOTPCM" + b"\x00" * 20)
    db.execute("INSERT INTO img_map (filename, type, name) VALUES "
               "('se/bad.pcm','SND','bad')")
    db.commit()
    db.close()
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises((RuntimeError, SystemExit)):
        pack_audio.pack_audio(str(proj), str(out))


def test_pack_audio_collision_rejected(tmp_path):
    # long base names both truncate to the same 8.3 short name
    proj = _make_project(tmp_path, [
        ("bgm/verylongone.mid", "BGM", "verylongone"),
        ("bgm/verylongtwo.mid", "BGM", "verylongtwo"),
    ])
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises((RuntimeError, SystemExit)):
        pack_audio.pack_audio(str(proj), str(out))


def test_pack_audio_empty(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    db = sqlite3.connect(proj / "ASSETS.DB")
    db.execute("CREATE TABLE img_map (id INTEGER PRIMARY KEY, filename TEXT, "
               "type TEXT, name TEXT DEFAULT '')")
    db.commit()
    db.close()
    out = tmp_path / "out"
    out.mkdir()
    pack_audio.pack_audio(str(proj), str(out))
    assert not (out / "AUDIO.DAT").exists()


def test_pack_audio_reuses_make_toc_archive_roundtrip(tmp_path):
    proj = _make_project(tmp_path, [("bgm/t.mid", "BGM", "t")])
    out = tmp_path / "out"
    out.mkdir()
    pack_audio.pack_audio(str(proj), str(out))
    dat = (out / "AUDIO.DAT").read_bytes()
    _count, _name, eoff, esz = list(image_dat.iter_image_dat_toc(dat))[0]
    assert dat[eoff:eoff + esz] == b"bgm/t.midDATA"