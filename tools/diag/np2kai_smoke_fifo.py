#!/usr/bin/env python3
# 无 pty 环境下的 NP2kai 冒烟: 用 FIFO 替代 pty 捕获串口, 并用 screendig 抓屏
import os, sys, time, subprocess, shutil
sys.path.insert(0, '/home/edo/naiz')
from tools.naiz_lib import np2kai_capture as cap

HDI = sys.argv[1] if len(sys.argv) > 1 else 'disks/demo-a2.hdi'
ROOT = '/home/edo/naiz'
FIFO = os.path.join(ROOT, 'tmp_le', 'ser.fifo')
LOG = os.path.join(ROOT, 'tmp_le', 'serial_os_test.log')

cap.kill_stale_emulators()
if os.path.exists(FIFO):
    os.unlink(FIFO)
os.mkfifo(FIFO)

updates = {
    'SCSIHDD0': os.path.join(ROOT, HDI),
    'com1_m_o': FIFO, 'com1_m_i': FIFO,
    'com1port': 1, 'com1para': 0xE3, 'com1_bps': 9600,
}
cfg = cap.write_emulator_toml(updates)
print('config:', cfg)

cmd = [cap.EMULATOR, '--start']
print('launch:', cmd)
proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    # FIFO 读端: NP2kai 会以写方式打开 com1_m_o; 读端需要常驻
    deadline = time.time() + 120
    with open(LOG, 'wb') as slog:
        # 非阻塞读 FIFO: 打开读端会阻塞直到写端打开, 用线程化处理简化
        import threading
        stop = threading.Event()
        def reader():
            try:
                with open(FIFO, 'rb') as f:
                    while not stop.is_set():
                        data = f.read1(4096) if hasattr(f,'read1') else f.read(4096)
                        if not data:
                            break
                        slog.write(data); slog.flush()
            except OSError:
                pass
        t = threading.Thread(target=reader, daemon=True)
        t.start()
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            time.sleep(2)
            sz = os.path.getsize(LOG)
            if sz > 200:
                # 引擎已输出, 再等几秒抓尾
                time.sleep(10)
                break
    stop.set()
finally:
    proc.terminate()
    try: proc.wait(10)
    except Exception: proc.kill()

print('--- serial log (%d bytes) ---' % os.path.getsize(LOG))
data = open(LOG,'rb').read()
print(data.decode('utf-8','replace')[:2000] or '(空)')
if not data:
    print('!! 串口为空 —— 需要抓屏看 fatal 信息')
