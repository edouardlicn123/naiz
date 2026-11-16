#!/usr/bin/env python3
# NP2kai 冒烟: 用 PTY 捕获串口, 固定时长或见首批输出即停
#
# 历史备注: 文件名沿用 np2kai_smoke_fifo —— 早期用 FIFO, 但本机 wxnp21kai 对
# com1_m_o 的普通文件/FIFO 只做 O_RDWR|O_NONBLOCK 探测后立即 close, 不转发
# 任何字节 (strace 可见); 只有 PTY slave 才真正接到 rs232c. 不要改回 FIFO.
#
# Usage:
#   python tools/diag/np2kai_smoke_fifo.py [hdi] [seconds]
#
# `seconds` pins the run to a FIXED wall-clock duration (0 = legacy behaviour:
# stop once the engine has produced some output).  A fixed duration is what a
# devdoc 211 clock measurement needs -- the point is what the clock does while
# nobody touches anything, and VCLOCK_WINDOW_MS is 1000 ms, so cutting the run
# short at the first byte measures nothing.
import os, sys, time, subprocess, pty, select, threading
sys.path.insert(0, '/home/edo/naiz')
from tools.naiz_lib import np2kai_capture as cap

HDI = sys.argv[1] if len(sys.argv) > 1 else 'disks/demo-a2.hdi'
try:
    RUN_SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 0
except ValueError:
    RUN_SECONDS = 0
ROOT = '/home/edo/naiz'
LOG = os.path.join(ROOT, 'tmp_le', 'serial_smoke.log')

cap.kill_stale_emulators()

master_fd, slave_fd = pty.openpty()
slave_name = os.ttyname(slave_fd)

updates = {
    'SCSIHDD0': os.path.join(ROOT, HDI),
    'com1_m_o': slave_name, 'com1_m_i': slave_name,
    'com1port': 1, 'com1para': 0xE3, 'com1_bps': 9600,
}
cfg = cap.write_emulator_toml(updates)
print('config:', cfg)
print('pty slave:', slave_name)
print('run_seconds:', RUN_SECONDS or '(legacy: stop at first output)')

cmd = [cap.EMULATOR, '--start']
print('launch:', cmd)
proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

stop = threading.Event()
with open(LOG, 'wb') as slog:
    def reader():
        while not stop.is_set():
            r, _, _ = select.select([master_fd], [], [], 0.2)
            if not r:
                continue
            try:
                data = os.read(master_fd, 4096)
            except OSError:
                break
            if not data:
                continue
            slog.write(data)
            slog.flush()

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        if RUN_SECONDS:
            # Fixed-duration mode: never stop early on first output.
            time.sleep(RUN_SECONDS)
        else:
            deadline = time.time() + 120
            while time.time() < deadline:
                if proc.poll() is not None:
                    break
                time.sleep(2)
                if os.path.getsize(LOG) > 200:
                    # 引擎已输出, 再等几秒抓尾
                    time.sleep(10)
                    break
    finally:
        stop.set()
        t.join(timeout=2)
        proc.terminate()
        try: proc.wait(10)
        except Exception: proc.kill()
        os.close(master_fd)
        os.close(slave_fd)

print('--- serial log (%d bytes) ---' % os.path.getsize(LOG))
data = open(LOG, 'rb').read()
print(data.decode('utf-8', 'replace')[:2000] or '(空)')
if not data:
    print('!! 串口为空 —— 需要抓屏看 fatal 信息')
