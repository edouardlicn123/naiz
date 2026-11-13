#!/usr/bin/env python3
"""Clock probe run: boot the engine, leave it alone, capture [VW] for N seconds.

devdoc 211 §5.3 needs ONE thing the host tests cannot give: what the real
window measurement looks like on the emulator.  The PTY path
(np2kai_serial.py) is unavailable here -- the container's devpts instance
leaves ptmx unopenable, so pty.openpty() raises EIO ("out of pty devices").
A FIFO works just as well for a one-directional capture and needs no PTY at
all.

Difference from np2kai_smoke_fifo.py: that tool stops as soon as the engine
has said anything (~10 s), which is far too short to see a VCLOCK_WINDOW_MS
(1000 ms) window settle -- the whole point is a 30 s idle run.  This one runs
for a fixed wall-clock duration and reports the [VW] line count, because the
COUNT is the signal: a healthy clock closes ~1 window per second.

Usage:
    python tools/diag/vclock_probe.py [seconds] [--hdi disks/demo-a2.hdi]

Reading the result (devdoc 211 §5.3, docs/A03 §9.5):
    passes~176 accum~1000 raw~91   healthy
    passes huge                    too many advances per window
    accum << 1000                  hal_wallclock_ms() is not advancing
    only 3-4 lines in 30 s         windows almost never close
"""
import os
import re
import sys
import subprocess
import threading
import time

sys.path.insert(0, '/home/edo/naiz')
from tools.naiz_lib import np2kai_capture as cap   # noqa: E402

ROOT = '/home/edo/naiz'
FIFO = os.path.join(ROOT, 'tmp_le', 'clock_probe.fifo')
LOG = os.path.join(ROOT, 'tmp_le', 'clock_probe.log')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    duration = 35
    if args:
        try:
            duration = int(args[0])
        except ValueError:
            pass
    hdi = 'disks/demo-a2.hdi'
    for a in sys.argv[1:]:
        if a.startswith('--hdi='):
            hdi = a.split('=', 1)[1]

    cap.kill_stale_emulators()
    for p in (FIFO, LOG):
        if os.path.exists(p):
            os.unlink(p)
    os.makedirs(os.path.dirname(FIFO), exist_ok=True)
    os.mkfifo(FIFO)

    cap.write_emulator_toml({
        'SCSIHDD0': os.path.join(ROOT, hdi),
        'com1_m_o': FIFO, 'com1_m_i': FIFO,
        'com1port': 1, 'com1para': 0xE3, 'com1_bps': 9600,
    })

    print(f'[probe] HDI={hdi}  duration={duration}s  fifo={FIFO}')
    proc = subprocess.Popen([cap.EMULATOR, '--start'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    chunks = []
    stop = threading.Event()

    def reader():
        try:
            with open(FIFO, 'rb') as f:
                while not stop.is_set():
                    data = f.read1(4096) if hasattr(f, 'read1') else f.read(4096)
                    if not data:
                        time.sleep(0.05)
                        continue
                    chunks.append(data)
        except OSError:
            pass

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    try:
        # Fixed wall-clock run: do NOT stop early on first output.  The whole
        # measurement is "what does the clock do while nobody touches it".
        time.sleep(duration)
    finally:
        stop.set()
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()

    blob = b''.join(chunks)
    with open(LOG, 'wb') as f:
        f.write(blob)

    text = blob.decode('utf-8', 'replace')
    vw = re.findall(r'\[VW\][^\r\n]*', text)
    ap = re.findall(r'\[AP\][^\r\n]*', text)
    vc = re.findall(r'\[VC\][^\r\n]*', text)

    print(f'[probe] captured {len(blob)} bytes -> {LOG}')
    print(f'[probe] [VW]={len(vw)}  [AP]={len(ap)}  [VC]={len(vc)}')

    if vw:
        print('\n--- [VW] first 5 ---')
        for line in vw[:5]:
            print('  ' + line)
        print('\n--- [VW] last 5 ---')
        for line in vw[-5:]:
            print('  ' + line)
    else:
        print('\n!! no [VW] lines -- observer not installed, or trace '
              'compiled out, or the engine never reached the frame pump')

    if ap:
        print('\n--- [AP] last 5 ---')
        for line in ap[-5:]:
            print('  ' + line)

    if not blob:
        print('\n!! serial output EMPTY -- check the screen; a boot failure '
              'produces no serial at all')
    return 0


if __name__ == '__main__':
    sys.exit(main())
