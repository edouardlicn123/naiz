# -*- coding: utf-8 -*-
"""
Naiz 剧本工坊 — 轻量 MIDI 预览合成器（纯 Python + numpy）

用途：把 assets/<game>/bgm/*.mid 渲染成 WAV 供浏览器 <audio> 试听。
定位：预览级音色（按 GM 音色族选波表），不是专业 MIDI 合成器；
      需要 GS/XG 级还原时请在模拟器/实机里听真实 PMD 输出。
"""
import math
import struct

import numpy as np

RATE = 22050                      # 预览采样率
MAX_SECONDS = 240                 # 超长 MIDI 截断保护

# GM 音色族 → 波表生成函数（输入频率 Hz，输出一个周期的 wavetable）
def _w_sine(f):
    t = np.arange(256) / 256.0
    return np.sin(2 * np.pi * f * t)

def _mk(adds):
    """adds: [(谐波倍数, 幅度)] → 生成周期波表函数"""
    def gen(f):
        t = np.arange(256) / 256.0
        w = np.zeros(256)
        for mult, amp in adds:
            w += amp * np.sin(2 * np.pi * f * mult * t)
        return w
    return gen

_W_TRIANGLE = _mk([(1, 1.0), (3, -0.125), (5, 0.04), (7, -0.02)])
_W_ORGAN    = _mk([(1, 1.0), (2, 0.5), (4, 0.25)])
_W_GUITAR   = _mk([(1, 1.0), (2, 0.35), (3, 0.22), (4, 0.12), (5, 0.07)])
_W_BASS     = _mk([(1, 1.0), (2, 0.4)])
_W_STRING   = _mk([(1, 1.0), (2, 0.5), (3, 0.33), (4, 0.25), (5, 0.2)])
_W_BRASS    = _mk([(1, 1.0), (2, 0.6), (3, 0.45), (4, 0.3), (5, 0.2), (6, 0.12)])
_W_SQUARE   = _mk([(1, 1.0), (3, 0.33), (5, 0.2), (7, 0.14), (9, 0.1)])
_W_SAW      = _mk([(n, 1.0 / n) for n in range(1, 9)])


def _family_wave(prog):
    """GM 音色编号 → 波表函数"""
    if prog < 8:      return _W_TRIANGLE      # 钢琴类
    if prog < 16:     return _w_sine          # 半音打击类
    if prog < 24:     return _W_ORGAN         # 风琴类
    if prog < 32:     return _W_GUITAR        # 吉他类
    if prog < 40:     return _W_BASS          # 贝斯类
    if prog < 56:     return _W_STRING        # 弦乐/合奏
    if prog < 64:     return _W_BRASS         # 铜管
    if prog < 80:     return _W_SQUARE        # 簧管
    if prog < 88:     return _w_sine          # 长笛
    if prog < 96:     return _W_SAW           # 合成主音
    return _W_TRIANGLE


def _note_freq(note):
    """MIDI 音符号 → 频率 Hz"""
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


def _render_note(out, start, dur, freq, vel, prog):
    """把一个音符渲染进混音缓冲（float32）"""
    wave_fn = _family_wave(prog)
    sr = RATE
    i0 = int(start * sr)
    n = int(dur * sr)
    if n <= 0 or i0 >= len(out):
        return
    n = min(n, len(out) - i0)
    seg = np.arange(n) / sr
    # 相位累加（频谱稳定的简单波表插值）
    ph = np.cumsum(np.full(n, freq / sr)) % 1.0
    tbl = wave_fn(freq)
    idx = (ph * 256).astype(np.int64) % 256
    sig = tbl[idx]
    # 包络：10ms 起音 → 保持 → 60ms 释放
    a = max(1, int(0.010 * sr))
    r = max(1, int(0.060 * sr))
    env = np.ones(n)
    if n > a + r:
        env[:a] = np.linspace(0, 1, a)
        env[-r:] *= np.linspace(1, 0, r)
    else:
        env = np.linspace(0, 1, n)
    amp = (vel / 127.0) * 0.32
    out[i0:i0 + n] += sig * env * amp


def _render_drum(out, start, dur, note, vel):
    """鼓（第 10 通道）：衰减噪声 + 低频 thump"""
    sr = RATE
    i0 = int(start * sr)
    n = int(min(dur, 0.35) * sr)
    if n <= 4 or i0 >= len(out):
        return
    n = min(n, len(out) - i0)
    rng = np.random.default_rng(note)
    noise = rng.standard_normal(n)
    env = np.exp(-np.arange(n) / (0.05 * sr))
    thump = np.sin(2 * np.pi * (55 if note < 42 else 90) * np.arange(n) / sr) * 0.6
    amp = (vel / 127.0) * 0.35
    out[i0:i0 + n] += (noise * 0.4 + thump) * env * amp


def _parse_vlq(data, pos):
    """MIDI 变长数量（VLQ）"""
    val = 0
    for _ in range(4):
        b = data[pos]
        pos += 1
        val = (val << 7) | (b & 0x7F)
        if not b & 0x80:
            break
    return val, pos


def render_midi_file(path):
    """渲染 .mid → 16-bit 单声道 WAV bytes；解析失败抛 ValueError"""
    data = open(path, "rb").read()
    if data[0:4] != b"MThd":
        raise ValueError("不是 MIDI 文件（缺 MThd 头）")
    (hdr_len,) = struct.unpack_from(">I", data, 4)
    fmt, ntrk, division = struct.unpack_from(">HHH", data, 8)
    pos = 8 + hdr_len

    # SMPTE 时间格式回退为近似值
    if division & 0x8000:
        fps = 256 - (division >> 8)
        tpf = division & 0xFF
        ticks_per_sec = fps * tpf
    else:
        ticks_per_sec = None  # 等 tempo 定标

    # 收集全部轨道事件（绝对 tick）
    events = []  # (tick, kind, payload)
    for _ in range(ntrk):
        if data[pos:pos + 4] != b"MTrk":
            raise ValueError("MTrk 缺失")
        (tlen,) = struct.unpack_from(">I", data, pos + 4)
        end = pos + 8 + tlen
        p = pos + 8
        tick = 0
        running = 0
        while p < end:
            delta, p = _parse_vlq(data, p)
            tick += delta
            b = data[p]
            if b & 0x80:
                status = b
                p += 1
            else:
                status = running  # running status
            running = status
            hi = status & 0xF0
            ch = status & 0x0F
            if status == 0xFF:            # 元事件
                mtype = data[p]; p += 1
                mlen, p = _parse_vlq(data, p)
                if mtype == 0x51 and mlen == 3:      # tempo
                    events.append((tick, "tempo",
                                   (data[p] << 16) | (data[p + 1] << 8) | data[p + 2]))
                p += mlen
            elif status in (0xF0, 0xF7):  # 系统独占，跳过
                mlen, p = _parse_vlq(data, p)
                p += mlen
            elif hi == 0x90:              # note on
                events.append((tick, "on", (ch, data[p], data[p + 1])))
                p += 2
            elif hi == 0x80:              # note off
                events.append((tick, "off", (ch, data[p])))
                p += 2
            elif hi == 0xC0:              # program change
                events.append((tick, "prog", (ch, data[p])))
                p += 1
            elif hi in (0xB0, 0xA0, 0xE0):
                p += 2
            elif hi == 0xD0:
                p += 1
            else:
                p += 1
        pos = end

    events.sort(key=lambda e: e[0])

    # tick → 秒（默认 120 BPM）
    us_per_qn = 500000
    tpq = division & 0x7FFF if not division & 0x8000 else 480
    sec = 0.0
    last_tick = 0
    timed = []  # (sec, kind, payload)
    for tick, kind, payload in events:
        sec += (tick - last_tick) * us_per_qn / 1e6 / tpq
        last_tick = tick
        timed.append((sec, kind, payload))
    total = max((s for s, _, _ in timed), default=0.0) + 1.0
    total = min(total, MAX_SECONDS)

    out = np.zeros(int(total * RATE) + RATE, dtype=np.float32)
    progs = [0] * 16
    active = {}  # (ch, note) -> (start_sec, vel)
    for s, kind, payload in timed:
        if kind == "tempo":
            us_per_qn = max(1, payload)
        elif kind == "prog":
            progs[payload[0]] = payload[1]
        elif kind == "on":
            # 注意：payload = (ch, note, vel)，开关判断必须用力度 payload[2]；
            # MIDI 惯例 vel=0 的 note-on 等价 note-off
            key = (payload[0], payload[1])
            if payload[2] > 0:
                active[key] = (s, payload[2])
            else:
                st = active.pop(key, None)
                if st is not None:
                    start, vel = st
                    dur = max(0.05, s - start)
                    if payload[0] == 9:
                        _render_drum(out, start, dur, payload[1], vel)
                    else:
                        _render_note(out, start, dur,
                                     _note_freq(payload[1]), vel, progs[payload[0]])
        elif kind == "off":
            st = active.pop((payload[0], payload[1]), None)
            if st is None:
                continue
            start, vel = st
            dur = max(0.05, s - start)
            if payload[0] == 9:
                _render_drum(out, start, dur, payload[1], vel)
            else:
                _render_note(out, start, dur,
                             _note_freq(payload[1]), vel, progs[payload[0]])
    # 兜底：未关闭的音符
    for (ch, note), (start, vel) in active.items():
        dur = max(0.05, min(1.0, total - start))
        if ch == 9:
            _render_drum(out, start, dur, note, vel)
        else:
            _render_note(out, start, dur, _note_freq(note), vel, progs[ch])

    # 归一化 → int16 → WAV bytes
    peak = float(np.max(np.abs(out))) or 1.0
    out = out / peak * 0.85
    pcm = (out * 32767).astype("<i2").tobytes()
    import io
    import wave as wavmod
    buf = io.BytesIO()
    with wavmod.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return buf.getvalue()
