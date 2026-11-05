"""
截图捕获模块

基于 tools/diag/np2kai_screenshot.py 改进，
添加连续截图、会话管理功能。
"""

import os
import subprocess
import time
from datetime import datetime

try:
    from naiz_lib import np2kai_capture
except ImportError:
    from tools.naiz_lib import np2kai_capture


class NP2kaiCapture:
    """NP2kai window capturer"""

    def __init__(self, output_dir="/tmp/naiz_screendig"):
        self.output_dir = output_dir
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = os.path.join(output_dir, f"session_{self.session_id}")
        os.makedirs(self.session_dir, exist_ok=True)
        print(f"[capture] Session created: {self.session_dir}")

    def find_windows(self):
        """Find all NP2kai windows"""
        return np2kai_capture.find_np2kai_windows()

    def pick_main_display(self, candidates):
        """Pick the main display window"""
        return np2kai_capture.pick_main_display(candidates)

    def capture_single(self, wid, output_path):
        """Capture a single screenshot"""
        return np2kai_capture.capture(wid, output_path, tag="[capture]")

    def capture_sequence(self, wid, interval=2.0, count=None, duration=None):
        """Capture a sequence of screenshots"""
        screenshots = []
        start_time = time.time()
        print(f"[capture] Starting sequence: interval={interval}s, count={count}, duration={duration}")

        try:
            while True:
                # 检查停止条件
                if count and len(screenshots) >= count:
                    break
                if duration and (time.time() - start_time) >= duration:
                    break

                # 生成时间戳文件名
                timestamp = datetime.now().strftime("%H%M%S_%f")[:-3]
                filename = f"screenshot_{timestamp}.png"
                filepath = os.path.join(self.session_dir, filename)

                # 捕获截图
                if self.capture_single(wid, filepath):
                    elapsed = time.time() - start_time
                    print(f"[capture] #{len(screenshots)+1}: {filename} ({elapsed:.1f}s)")
                    screenshots.append({
                        "filename": filename,
                        "timestamp": timestamp,
                        "elapsed": elapsed,
                        "size": os.path.getsize(filepath)
                    })
                else:
                    print(f"[capture] Failed: {filename}")

                # 等待下次截图
                if interval > 0:
                    time.sleep(interval)

        except KeyboardInterrupt:
            print(f"\n[capture] Stopped after {len(screenshots)} screenshots")

        return screenshots

    def launch_emulator(self):
        """Launch the emulator"""
        return np2kai_capture.launch_emulator()
