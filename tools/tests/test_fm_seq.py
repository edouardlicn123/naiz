"""S4 fmseq host tests (devdocs/123 M2).

Compiles core/lib/fmseq.c (+ fmopn.c, midi.c) with the host gcc into a temp
shared object and drives it through ctypes.  The voice allocator is pure
logic (zero outb()), so allocation, steal, sustain, bend, percussion mapping
and SSG decay are all proven here without an emulator.

Assertions cover:
  - note-on reproduces the full register program (24 op regs + B0/B4 +
    A4/A0 + keyon) and the operator->register-slot map lands on the right TLs
  - velocity attenuates every op TL (max +15 at vel 1)
  - note-off keyoffs and frees the voice; sustain pedal holds it instead
    and pedal-up breathes the pending notes
  - steal order: coldest free, then pedal-pending, then oldest (proven by
    register evidence, not timers); a repeated note never re-keys the voice it
    just released (devdoc 156 click-free allocation)
  - GM ch 10 drives the 3 SSG percussion voices with the right register
    set (tone / noise / tone+noise) and the reg-7 mixer semantics
  - SSG software volume decay frees a voice and silences the mixer
  - bend rewrites A4/A0 only for sounding voices on the bent channel
  - gm_map selects the patch family; out-of-range programs hit the
    unmapped callback and fall back to family 0
  - end-to-end: a real SMF built by gen_test_midi parses and replays
"""

import ctypes
import os
import re
import struct
import subprocess
import sys
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools", "naiz_audio"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools", "tests"))

from test_fmopn import _good_patch, _ratio  # noqa: E402
from naiz_audio import gen_test_midi  # noqa: E402

LIB_C_FILES = ["fmseq.c", "fmopn.c", "midi.c"]
_BASE = os.path.join(REPO_ROOT, "core", "lib")
_CACHE = {}


def _build_fmseq():
    mtime = max(os.stat(os.path.join(_BASE, f)).st_mtime for f in LIB_C_FILES)
    if _CACHE.get("mtime") == mtime:
        return _CACHE["lib"], mtime
    with tempfile.TemporaryDirectory(prefix="fmseq_test_") as tmp:
        so = os.path.join(tmp, "fmseq.so")
        cmd = ["gcc", "-O2", "-shared", "-fPIC", "-I", _BASE,
               "-fno-stack-protector"] + [os.path.join(_BASE, f)
                                          for f in LIB_C_FILES]
        cmd += ["-o", so, "-lm"]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        _CACHE["lib"] = ctypes.CDLL(so)
        _CACHE["mtime"] = mtime
        return _CACHE["lib"], mtime


class MidEventT(ctypes.Structure):
    _fields_ = [("tick_ms", ctypes.c_uint32),
                ("b0", ctypes.c_uint8),
                ("b1", ctypes.c_uint8),
                ("b2", ctypes.c_uint8)]


class SinkT(ctypes.Structure):
    _fields_ = [("ctx", ctypes.c_void_p),
                ("write", ctypes.c_void_p)]


_WRITE_FN = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int,
                             ctypes.c_uint8, ctypes.c_uint8)
_UNMAPPED_FN = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int)


@pytest.fixture(scope="module")
def lib():
    lib, _ = _build_fmseq()
    lib.fmseq_size.restype = ctypes.c_size_t
    lib.fmseq_init.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                               ctypes.c_void_p, _UNMAPPED_FN, ctypes.c_void_p]
    lib.fmseq_events.argtypes = [ctypes.c_void_p,
                                 ctypes.POINTER(MidEventT), ctypes.c_int]
    lib.fmseq_pump.argtypes = [ctypes.c_void_p, ctypes.POINTER(SinkT),
                               ctypes.c_uint64]
    lib.fmseq_stop.argtypes = [ctypes.c_void_p, ctypes.POINTER(SinkT)]
    lib.fmseq_fm_voices.argtypes = [ctypes.c_void_p]
    lib.fmseq_fm_voices.restype = ctypes.c_int
    lib.fmseq_finished.argtypes = [ctypes.c_void_p]
    lib.fmseq_finished.restype = ctypes.c_int
    lib.fmopn_note_ratio.argtypes = [ctypes.c_int, ctypes.c_void_p,
                                     ctypes.c_void_p]
    lib.fmopn_bend_ratio.argtypes = [ctypes.c_int, ctypes.c_void_p,
                                     ctypes.c_void_p]
    lib.midi_parse.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                               ctypes.POINTER(ctypes.POINTER(MidEventT)),
                               ctypes.POINTER(ctypes.c_int),
                               ctypes.POINTER(ctypes.c_uint32)]
    lib.midi_parse.restype = ctypes.c_int
    lib.midi_free.argtypes = [ctypes.POINTER(MidEventT)]
    lib.fmseq_loop_start.argtypes = [ctypes.c_uint64, ctypes.c_uint64,
                                     ctypes.c_uint64]
    lib.fmseq_loop_start.restype = ctypes.c_uint64
    return lib


_FAM0 = _good_patch()


def _family(n):
    """Patch n: family 0 keeps the real layout (chip TLs 40/42/44/46), the
    rest get a uniform TL (40 + 20*n) so family selection is observable."""
    b = (ctypes.c_uint8 * 32)()
    for i in range(32):
        b[i] = _FAM0[i]
    if n > 0:
        for off in (1, 7, 13, 19):
            b[off] = 40 + 20 * n
    return b


class Seq:
    """Fmseq harness: a ctypes-allocated sequence + recorded write log.

    Events are loaded ONCE (pump advances a monotonic clock; reloading would
    reset the decay baseline / replay cursor mid-scenario).
    """

    def __init__(self, lib, nfamily=2, gm_mode=None):
        self.lib = lib
        self.nfamily = nfamily
        self.log = []
        self._pending = []
        self._cb = _WRITE_FN(self._on_write)
        self._unmapped_cb = _UNMAPPED_FN(self._on_unmapped)  # keep alive
        self._unmapped = []
        sink = SinkT()
        sink.write = ctypes.cast(self._cb, ctypes.c_void_p)
        self._sink = sink

        seq = ctypes.create_string_buffer(lib.fmseq_size())
        self._seq = seq

        pat = (ctypes.c_uint8 * 32 * nfamily)()
        for i in range(nfamily):
            p = _family(i)
            for k in range(32):
                pat[i][k] = p[k]
        self._pat = pat

        gm = (ctypes.c_uint8 * 128)()
        if gm_mode == "all2":
            for i in range(128):
                gm[i] = 1      # everything -> family 1
        elif gm_mode == "bad":
            for i in range(128):
                gm[i] = 99     # beyond the family table
        self._gm = gm

        lib.fmseq_init(ctypes.addressof(seq), ctypes.addressof(pat),
                       nfamily, ctypes.addressof(gm),
                       self._unmapped_cb, None)

    def _on_write(self, ctx, bank, reg, val):
        self.log.append((bank, reg, val))

    def _on_unmapped(self, ctx, ch, program, family):
        self._unmapped.append((ch, program, family))

    def push(self, events):
        self._pending.extend(events)

    def load(self):
        arr = (MidEventT * len(self._pending))(*[MidEventT(ms_, b0, b1, b2)
                                                 for ms_, b0, b1, b2
                                                 in self._pending])
        self._arr = arr
        self.lib.fmseq_events(ctypes.addressof(self._seq), arr, len(arr))

    def pump(self, ms):
        self.lib.fmseq_pump(ctypes.addressof(self._seq),
                            ctypes.byref(self._sink), ms)

    def stop(self):
        self.lib.fmseq_stop(ctypes.addressof(self._seq),
                            ctypes.byref(self._sink))

    def voices(self):
        return self.lib.fmseq_fm_voices(ctypes.addressof(self._seq))

    def writes(self, bank=0, reg=None, val=None):
        return [(b, r, v) for b, r, v in self.log
                if b == bank and (reg is None or r == reg)
                and (val is None or v == val)]

    def keyons(self, mask=0x0F):
        return self.writes(0, 0x28, 0xF0 | mask if False else None)

    def keyoff(self, ch):
        sel = ch if ch < 3 else 4 + (ch - 3)
        return self.writes(0, 0x28, sel)


def _note_on(note, vel=0x7F, ch=0):
    return [(0, 0x90 | ch, note, vel)]


def _note_off(note, ch=0):
    return [(0, 0x80 | ch, note, 0)]


def test_note_on_program(lib):
    s = Seq(lib)
    s.push(_note_on(69))
    s.load()
    s.pump(0)
    log = s.log

    assert log[-1] == (0, 0x28, 0xF0)          # keyon ch0 all-ops
    # block5/fnum520 for A4 across the two freq regs
    assert (0, 0xA4, 0x2A) in log and (0, 0xA0, 0x08) in log
    # op TLs land at their register-slot addresses.  Register-slot r sits
    # at base + 4*r (per ymfm/OPN, operator = address bits 2-3, channel =
    # bits 0-1); the file maps file idx -> register slot via fmopn_op_slot,
    # so register slots 0,1,2,3 read file slots 0,2,1,3 (TLs 40,42,44,46).
    assert (0, 0x40, 40) in log                # regslot0 (file idx0 = op1)
    assert (0, 0x44, 42) in log                # regslot1 (file idx2 = op3)
    assert (0, 0x48, 44) in log                # regslot2 (file idx1 = op2)
    assert (0, 0x4C, 46) in log                # regslot3 (file idx3 = op4)
    assert (0, 0xB0, (5 << 3) | 4) in log      # FB=5 AL=4
    assert (0, 0xB4, 0xC0) in log              # pan both
    # full program: 24 op regs + B0 + B4 + A4 + A0 + keyon
    assert len(log) == 29
    # bank-1 (ch 4-6) addressing is NOT touched by a ch0 note
    assert s.writes(bank=1) == []
    assert s.voices() == 1


def test_ch4_goes_bank1(lib):
    s = Seq(lib)
    for n in range(4):                       # fill ch0..ch3
        s.push(_note_on(69 + n, 0x7F))
    s.load()
    s.pump(0)
    # the 4th voice (ch3) keys via the extended port's keyon select 4
    assert (0, 0x28, 0xF4) in s.log
    assert s.writes(bank=1) != []


def test_note_off_keyoffs_and_frees(lib):
    s = Seq(lib)
    s.push(_note_on(60))
    s.push([(10, 0x80, 60, 0)])
    s.load()
    s.pump(0)
    assert s.voices() == 1
    s.pump(10)
    assert s.keyoff(0)                      # keyon keymask 0 = off
    assert s.voices() == 0


def test_velocity_scales_tl(lib):
    for vel, att in ((127, 0), (64, 7), (1, 15)):
        s = Seq(lib)
        s.push(_note_on(69, vel))
        s.load()
        s.pump(0)
        assert (0, 0x40, 40 + att) in s.log, f"vel {vel}"


def test_sustain_pedal_holds_note(lib):
    s = Seq(lib)
    s.push([(0, 0xB0, 64, 0x7F)] + _note_on(60)
           + [(10, 0x80, 60, 0), (20, 0xB0, 64, 0)])
    s.load()
    s.pump(0)
    assert s.keyoff(0) == []                 # pedal down holds the note
    assert s.voices() == 1
    s.pump(10)                               # note-off: absorbed by pedal
    assert s.voices() == 1
    s.pump(20)                               # pedal up breathes it
    assert len(s.keyoff(0)) == 1
    assert s.voices() == 0


def test_steal_oldest(lib):
    s = Seq(lib)
    for n in range(60, 66):                  # six held voices, oldest 60
        s.push(_note_on(n, 0x7F, 0))
    s.push(_note_on(71, 0x7F, 0))            # no free, no pending
    s.load()
    s.pump(0)
    # a forced keyoff hit ch0 (the oldest), followed by the re-key
    ko = [i for i, e in enumerate(s.log)
          if e[1] == 0x28 and e[2] == 0]
    assert len(ko) == 1
    rest = s.log[ko[0]:]
    assert (0, 0x28, 0xF0) in rest           # the stolen ch regained keyon
    blk, fn = _ratio(lib, "fmopn_note_ratio", 71)
    assert (0, 0xA4, (blk << 3) | (fn >> 8)) in s.log
    assert (0, 0xA0, fn & 0xFF) in s.log
    assert s.voices() == 6


def test_steal_prefers_pending(lib):
    s = Seq(lib)
    s.push([(0, 0xB0, 64, 0x7F)] + _note_on(60) + [(1, 0x80, 60, 0)])
    for n in (62, 64, 65, 67, 69):           # five held voices
        s.push(_note_on(n))
    s.push(_note_on(71))                     # must reclaim the pending v0
    s.load()
    s.pump(1)
    blk, fn = _ratio(lib, "fmopn_note_ratio", 71)
    assert (0, 0xA4, (blk << 3) | (fn >> 8)) in s.log
    assert len(s.keyoff(0)) == 1             # exactly one forced keyoff (v0)


def test_percussion_kick(lib):
    s = Seq(lib)
    s.push(_note_on(36, 0x60, 9))
    s.load()
    s.pump(0)
    log = s.log
    assert (0, 0x28, 0) not in log           # never keys an FM channel
    assert s.writes(bank=1) == []
    # SSG0 tone period regs written, amplitude reg 8, mixer enables ch A tone
    blk, fn = _ratio(lib, "fmopn_note_ratio", 36)
    freq = (fn << blk) * 7987200.0 / (288.0 * (1 << 20))
    period = max(1, min(4095, int(124800.0 / freq)))
    got = next((v for b, r, v in log if r == 0x00), 0) \
        | (next((v for b, r, v in log if r == 0x01), 0) << 8)
    assert abs(got - period) <= 1            # C float rounding, not a bug
    assert (0, 0x07, 0x3E) in log            # mixer: only chA tone enabled
    amp = (0x60 * 255) >> 7 >> 4
    assert (0, 0x08, amp) in log


def test_percussion_hat(lib):
    s = Seq(lib)
    s.push(_note_on(42, 0x60, 9))
    s.load()
    s.pump(0)
    log = s.log
    assert (0, 0x06, 0x02) in log            # noise period
    # reg7 = disable mask: everything off except chC noise (bit5 enabled)
    assert (0, 0x07, 0x1F) in log
    assert (0, 0x0A, ((0x60 * 255) >> 7 >> 4)) in log
    assert not any(e[1] in (0x04, 0x05) for e in log)   # no tone period


def test_percussion_snare(lib):
    s = Seq(lib)
    s.push(_note_on(38, 0x60, 9))
    s.load()
    s.pump(0)
    log = s.log
    assert (0, 0x06, 0x09) in log            # noise period for the body
    # reg7: everything off except chB tone+noise (bits 1 and 4 enabled)
    assert (0, 0x07, 0x2D) in log
    assert (0, 0x09, ((0x60 * 255) >> 7 >> 4)) in log
    assert any(e[1] in (0x02, 0x03) for e in log)      # tone period regs


def test_ssg_decay_silences_mixer(lib):
    s = Seq(lib)
    s.push(_note_on(42, 0x7F, 9))            # loud hat; vmax amp = 0x0F
    s.load()
    s.pump(0)
    assert (0, 0x0A, 0x0F) in s.log
    s.pump(2000)                             # 2 s of decay
    s.pump(4000)
    assert (0, 0x0A, 0) in s.log
    assert s.log[-1] == (0, 0x07, 0x3F)      # whole mixer silenced when free


def test_pitch_bend_rewrites_pitch(lib):
    s = Seq(lib)
    s.push(_note_on(60))
    s.push([(1, 0xE0, 9000 & 0x7F, 9000 >> 7)])
    s.load()
    s.pump(0)
    pre = s.writes(0, 0xA4)
    s.pump(1)
    post = s.writes(0, 0xA4)
    assert len(post) == len(pre) + 1
    blk, fn = _ratio(lib, "fmopn_note_ratio", 60)
    b = ctypes.c_int(blk); f = ctypes.c_int(fn)
    lib.fmopn_bend_ratio(9000, ctypes.byref(b), ctypes.byref(f))
    assert post[-1] == (0, 0xA4, (b.value << 3) | (f.value >> 8))


def test_gm_family_selection(lib):
    s = Seq(lib, gm_mode="all2")
    s.push(_note_on(69))
    s.load()
    s.pump(0)
    assert (0, 0x40, 60) in s.log            # family 1 TL (40 + 1*20)

    # out-of-range program falls back to family 0 and reports
    s2 = Seq(lib, gm_mode="bad")
    s2.push([(0, 0xC0, 5, 0)] + _note_on(69))
    s2.load()
    s2.pump(0)
    assert s2._unmapped == [(0, 5, 0)]
    assert (0, 0x40, 40) in s2.log


def test_smf_end_to_end(lib):
    smf = gen_test_midi.build(bpm=120)
    buf = ctypes.create_string_buffer(smf)
    out = ctypes.POINTER(MidEventT)()
    n = ctypes.c_int()
    length = ctypes.c_uint32()
    rc = lib.midi_parse(ctypes.addressof(buf), len(smf),
                        ctypes.byref(out), ctypes.byref(n),
                        ctypes.byref(length))
    assert rc == 0 and n.value > 0
    evs = [(int(out[i].tick_ms), out[i].b0, out[i].b1, out[i].b2)
           for i in range(n.value)]
    lib.midi_free(out)

    s = Seq(lib)
    for e in evs:
        s.push([e])
    s.load()
    # gen_test_midi: C4 on@0 off@200, E4 on@700 off@900, G4 on@1400 off@1600
    s.pump(0)
    assert s.voices() == 1                   # C4 alone at t=0
    assert (0, 0x28, 0xF0) in s.log
    s.pump(250)
    assert s.voices() == 0                   # C4 released
    s.pump(750)
    assert s.voices() == 1                   # E4 on the coldest free voice
    s.pump(1450)
    assert s.voices() == 1                   # G4 likewise (never a live voice)
    s.pump(1700)
    assert s.voices() == 0
    assert any(s.log[i][1] == 0x28 and s.log[i][2] == 0
               for i in range(len(s.log)))       # released the single voice
    # three notes tuned on three distinct FNUM-low registers (<=3<4: bank 0),
    # since the coldest-free allocator spreads them over voices 0,1,2
    fnum_low = [e for e in s.log
                if e[0] == 0 and e[1] in (0xA0, 0xA1, 0xA2)]
    assert len(fnum_low) >= 3


# --- devdoc 156: coldest-free allocation (no keyon on a just-released voice) -

def _keyon_voices(s):
    """FM voice index of every keyon ($28 keymask 0xF*), in emission order."""
    out = []
    for _b, r, v in s.log:
        if r == 0x28 and (v & 0xF0) == 0xF0:
            sel = v & 0x0F
            out.append(sel if sel < 4 else 3 + (sel - 4))
    return out


def test_repeat_note_does_not_rekey_its_own_voice(lib):
    """A repeated note must not key on the voice it just released.  OPNA (and
    NP2kai's fmgen) reset the operator phase on keyoff->keyon, so re-keying a
    still-ringing voice clicks; the coldest-free allocator lands the re-key on
    a colder voice instead (devdoc 156)."""
    s = Seq(lib)
    s.push([(0, 0x90, 69, 0x7F), (100, 0x80, 69, 0), (100, 0x90, 69, 0x7F)])
    s.load()
    s.pump(0)
    s.pump(100)
    keyoffs = [v for _b, r, v in s.log if r == 0x28 and v < 0x10]
    assert keyoffs == [0]                    # the first voice released, once
    assert _keyon_voices(s) == [0, 1]        # second note on a *different* voice


def test_repeat_note_rotates_through_voices(lib):
    """Six spaced repeats land on six distinct voices, then the seventh wraps
    to the coldest one -- the allocator never collapses a monophonic line onto
    one voice (which is what would re-key a ringing operator)."""
    s = Seq(lib)
    for k in range(7):
        t = k * 100
        s.push([(t, 0x90, 69, 0x7F), (t + 50, 0x80, 69, 0)])
    s.load()
    for k in range(7):
        s.pump(k * 100 + 60)
    assert _keyon_voices(s) == [0, 1, 2, 3, 4, 5, 0]
    assert s.voices() <= 1                   # never more than the one live note


def test_coldest_free_does_not_preempt_a_live_voice(lib):
    """With voices still sounding, the allocator keys on a free voice only:
    the register evidence shows two distinct keyon selects and no keyoff."""
    s = Seq(lib)
    s.push(_note_on(60, 0x7F, 0))            # voice 0, held
    s.push(_note_on(64, 0x7F, 0))            # voice 1, held
    s.load()
    s.pump(0)
    assert s.voices() == 2
    assert not any(_b == 0 and r == 0x28 and v < 0x10 for _b, r, v in s.log)
    assert _keyon_voices(s) == [0, 1]


def test_stop_resets_voice_ages_for_the_next_stream(lib):
    """fmseq_stop must reset per-voice ages, exactly like fmseq_init.  A scene
    switch stops the song (audio_stop_all) and the next scene restarts it on
    the SAME seq; stale ages make the coldest-free allocator keep picking the
    same voice and re-key a ringing opterator (the scene-2 start click,
    devdoc 157).  After stop, a fresh monophonic line must rotate 0,1,2,..."""
    s = Seq(lib)
    # scene 1: a few notes so the ages advance well past 0
    for k in range(4):
        t = k * 100
        s.push([(t, 0x90, 60 + k, 0x7F), (t + 50, 0x80, 60 + k, 0)])
    s.load()
    for k in range(4):
        s.pump(k * 100 + 60)
    s.stop()
    first_scene_voices = len(_keyon_voices(s))
    assert first_scene_voices == 4

    s.log.clear()
    # scene 2: same seq, restart; a monophonic line must rotate from voice 0
    s._pending = []
    s.push([(0, 0x90, 69, 0x7F)])
    s.push([(0, 0x90, 71, 0x7F)])
    s.push([(0, 0x90, 72, 0x7F)])
    s.load()
    s.pump(0)
    # three simultaneous notes land on three distinct voices starting at 0,
    # i.e. ages were reset (stale ages would collapse them onto one voice)
    assert _keyon_voices(s) == [0, 1, 2]


# --- devdoc 147: song length (A1), loop phase (A2), pump budget (A3) --------

def _vlq(n):
    """Encoded MIDI variable-length quantity."""
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def _smf_note_then_eot(eot_delta, with_eot=True, ppqn=480):
    """A one-track SMF: note on@0, note off@480 ticks, then (optionally) EOT
    eot_delta ticks later, so the EOT time exceeds the last voice event."""
    trk = bytearray()
    trk += _vlq(0) + bytes([0x90, 60, 0x60])       # note on @0
    trk += _vlq(480) + bytes([0x80, 60, 0x40])     # note off @480
    if with_eot:
        trk += _vlq(eot_delta) + bytes([0xFF, 0x2F, 0x00])
    hdr = b"MThd" + struct.pack(">IHHH", 6, 0, 1, ppqn)
    return hdr + b"MTrk" + struct.pack(">I", len(trk)) + bytes(trk)


def _parse(lib, smf):
    buf = ctypes.create_string_buffer(smf)
    out = ctypes.POINTER(MidEventT)()
    n = ctypes.c_int()
    length = ctypes.c_uint32()
    rc = lib.midi_parse(ctypes.addressof(buf), len(smf),
                        ctypes.byref(out), ctypes.byref(n),
                        ctypes.byref(length))
    assert rc == 0
    evs = [(int(out[i].tick_ms), out[i].b0, out[i].b1, out[i].b2)
           for i in range(n.value)]
    lib.midi_free(out)
    return evs, length.value


def test_song_length_includes_trailing_silence(lib):
    # 120 BPM (no tempo event -> 500000 us/quarter), 480 PPQN, so tick->ms is
    # tick * 500000 / 480 / 1000: last event @480 -> 500ms, EOT @960 -> 1000ms.
    smf = _smf_note_then_eot(eot_delta=480, with_eot=True)
    evs, length = _parse(lib, smf)
    assert evs[-1][0] == 500
    assert length == 1000
    assert length > evs[-1][0]          # trailing silence is preserved


def test_song_length_falls_back_without_eot(lib):
    smf = _smf_note_then_eot(eot_delta=0, with_eot=False)
    evs, length = _parse(lib, smf)
    assert evs[-1][0] == 500
    assert length == evs[-1][0]         # no EOT -> use the last voice event


def test_loop_start_preserves_phase(lib):
    f = lib.fmseq_loop_start
    # exactly one song elapsed -> advance by one length
    assert f(1000, 400, 1400) == 1400
    # overshoot inside the next song -> still exactly one length (phase kept)
    assert f(1000, 400, 1450) == 1400
    # not a full song yet -> clamp to now
    assert f(1000, 400, 1200) == 1200
    # starved two full songs -> skip whole lengths, land inside the current one
    assert f(1000, 400, 2200) == 2200
    assert f(1000, 400, 2250) == 2200
    # degenerate length -> now
    assert f(1000, 0, 1300) == 1300


def _pump_max_per_call():
    """The per-call dispatch cap, read from the header.

    devdoc 167 halved it (32 -> 16) while this test still hardcoded 32, so
    the expectation went stale: 40 events then need three pumps, not two.
    Deriving the cap keeps the test true for whatever the header says.
    """
    src = open(os.path.join(REPO_ROOT, "core", "lib", "fmseq.h"),
               encoding="utf-8").read()
    m = re.search(r"#define\s+FMSEQ_PUMP_MAX_PER_CALL\s+(\d+)", src)
    assert m, "FMSEQ_PUMP_MAX_PER_CALL not found in fmseq.h"
    return int(m.group(1))


def test_pump_budget_spreads_a_backlog(lib):
    # More note-ons than one pump may dispatch, all due at t=0: the backlog
    # must be spread over several calls, not flushed in a single pass
    # (devdoc 147 A3).
    cap = _pump_max_per_call()
    n = cap * 2 + 8
    s = Seq(lib)
    for i in range(n):
        s.push([(0, 0x90, 40 + i, 0x40)])
    s.load()
    s.pump(0)
    assert lib.fmseq_finished(ctypes.addressof(s._seq)) == 0   # backlog remains
    pumps = 1
    while not lib.fmseq_finished(ctypes.addressof(s._seq)):
        s.pump(0)
        pumps += 1
        assert pumps <= 8, "the backlog never drained"
    assert pumps == (n + cap - 1) // cap   # exactly ceil(n / cap) calls