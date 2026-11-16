#!/usr/bin/env python3
"""devdoc 211 clock probe -- PTY serial capture in a pty-less container.

This container's host devpts mount is unusable (ptmxmode=000 and the slave
side never materialises), but `unshare -m` gives a PRIVATE mount namespace
where a fresh devpts instance works: open /dev/pts/ptmx by hand, unlock the
slave with TIOCSPTLCK (0x40045431), read its number with TIOCGPTN
(0x80045430), and the slave path /dev/pts/N becomes openable.

That is everything `pty.openpty()` would have done, minus the C library's
assumption that /dev/ptmx exists.  The emulator is then pointed at the slave
path for com1_m_o/com1_m_i exactly as tools/env_setup/env_test.py does, the
master fd is drained into logs/clock_probe.log, and the run lasts a FIXED
wall-clock duration -- a 1000 ms measurement window needs at least 30 s of
idle engine to say anything.

Run inside the namespace:
    unshare -m bash -c 'mkdir -p /dev/pts && \
        mount -t devpts -o ptmxmode=0666 devpts /dev/pts && \
        python3 tools/diag/vclock_pty_probe.py <seconds>'

Everything in THIS file assumes /dev/pts/ptmx is already mounted.  The
mount lives only inside the unshare'd process tree, which is fine: the
emulator is spawned as a child and inherits the namespace.
"""
import os
import re
import struct
import fcntl
import subprocess
import sys
import time

sys.path.insert(0, '/home/edo/naiz')
from tools.naiz_lib import np2kai_capture as cap   # noqa: E402

ROOT = '/home/edo/naiz'
LOG = os.path.join(ROOT, 'logs', 'clock_probe.log')

TIOCGPTN = 0x80045430
TIOCSPTLCK = 0x40045431


def open_pty_pair():
    """Allocate a PTY without pty.openpty(): open the mounted ptmx directly.

    Keeps the slave fd open for the whole capture -- NP2kai opens the slave
    BY PATH after its fork, and a closed slave makes the endpoint unopenable
    -> silently empty serial (0.2.132 lesson, docs/FAQ §PTY slave 提前关闭).
    """
    master = os.open('/dev/pts/ptmx', os.O_RDWR | os.O_NOCTTY)
    fcntl.ioctl(master, TIOCSPTLCK, struct.pack('i', 0))
    num = struct.unpack('i', fcntl.ioctl(master, TIOCGPTN,
                                         struct.pack('i', 0)))[0]
    slave_path = f'/dev/pts/{num}'
    slave = os.open(slave_path, os.O_RDWR | os.O_NOCTTY)
    return master, slave, slave_path


def main():
    seconds = 35
    for a in sys.argv[1:]:
        if a.isdigit():
            seconds = int(a)
    hdi = 'disks/demo-a2.hdi'
    for a in sys.argv[1:]:
        if a.startswith('--hdi='):
            hdi = a.split('=', 1)[1]

    stale = cap.kill_stale_emulators()
    if stale:
        print(f'[probe] killed {len(stale)} stale emulator(s)')

    master, slave, slave_path = open_pty_pair()
    print(f'[probe] PTY OK: master={master} slave={slave_path}')

    cap.write_emulator_toml({
        'SCSIHDD0': os.path.join(ROOT, hdi),
        'com1_m_o': slave_path, 'com1_m_i': slave_path,
        'com1port': 1, 'com1para': 0xE3, 'com1_bps': 9600,
    })

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    chunks = []

    with open(LOG, 'wb') as slog:
        proc = subprocess.Popen([cap.EMULATOR, '--start'],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        print(f'[probe] emulator launched, capturing {seconds}s ...')
        end = time.time() + seconds
        try:
            while time.time() < end:
                if proc.poll() is not None:
                    print('[probe] emulator exited early')
                    break
                try:
                    data = os.read(master, 4096)
                except BlockingIOError:
                    time.sleep(0.05)
                    continue
                except OSError:
                    break
                if data:
                    chunks.append(data)
                    slog.write(data)
                    slog.flush()
        finally:
            proc.terminate()
            try:
                proc.wait(10)
            except Exception:
                proc.kill()

    blob = b''.join(chunks)
    text = blob.decode('utf-8', 'replace')
    vw = re.findall(r'\[VW\][^\r\n]*', text)
    ap = re.findall(r'\[AP\][^\r\n]*', text)
    vc = re.findall(r'\[VC\][^\r\n]*', text)

    print(f'[probe] {len(blob)} bytes -> {LOG}')
    print(f'[probe] [VW]={len(vw)}  [AP]={len(ap)}  [VC]={len(vc)}')

    if vw:
        print('\n--- [VW] first 5 ---')
        for line in vw[:5]:
            print('  ' + line)
        print('\n--- [VW] last 5 ---')
        for line in vw[-5:]:
            print('  ' + line)
        # The count IS the signal: healthy ≈ 1 per second.
        print(f'\n[probe] VW rate: {len(vw)} lines / {seconds}s '
              f'= {len(vw)/seconds:.2f} /s (healthy ≈ 1.0)')
    else:
        print('\n!! no [VW] lines')
        if blob:
            print('head of serial output:')
            print(text[:500])
        else:
            print('serial was EMPTY -- boot failure? take a screenshot.')

    if ap:
        print('\n--- [AP] last 5 ---')
        for line in ap[-5:]:
            print('  ' + line)
    return 0


if __name__ == '__main__':
    sys.exit(main())
