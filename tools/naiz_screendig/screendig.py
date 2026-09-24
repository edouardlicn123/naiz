"""
主要的截图调试类

整合捕获和分析功能，提供简洁的 API。
"""

import os

from .capture import NP2kaiCapture


class ScreenDig:
    """Screenshot debugger"""

    def __init__(self, output_dir="/tmp/naiz_screendig"):
        self.capture = NP2kaiCapture(output_dir)
        self._analyzer = None
        self.session_data = {
            "session_id": self.capture.session_id,
            "start_time": self.capture.session_dir,
            "screenshots": [],
            "analysis": {}
        }

    @property
    def analyzer(self):
        """Lazy import of analyzer (requires PIL/numpy)"""
        if self._analyzer is None:
            try:
                from .analyze import NP2kaiAnalyzer
                self._analyzer = NP2kaiAnalyzer()
            except ImportError as e:
                print(f"[screendig] Warning: Cannot import analyzer (missing PIL/numpy): {e}")
                print("[screendig] Analysis features will be disabled")
                self._analyzer = None
        return self._analyzer

    def run_debug_session(self, interval=2.0, count=None, duration=None,
                         analyze=True, baseline_path=None, verbose=True):
        """Run a debug session"""
        print("\n[screendig] === NP2kai 截图调试会话 ===")
        print(f"[screendig] Session ID: {self.session_data['session_id']}")
        print(f"[screendig] Interval: {interval}s, Count: {count}, Duration: {duration}")
        print(f"[screendig] Output directory: {self.capture.session_dir}")
        print(f"[screendig] Analyze screenshots: {analyze}")
        if baseline_path:
            print(f"[screendig] Baseline: {baseline_path}")
        print()

        # 查找窗口
        windows = self.capture.find_windows()
        if not windows:
            print("[screendig] No NP2kai windows found")
            return None

        main_window = self.capture.pick_main_display(windows)
        if main_window is None:
            print("[screendig] No main display window found")
            return None

        wid = main_window["wid"]
        print(f"[screendig] Window found: {main_window['title']}")
        print(f"[screendig]    Resolution: {main_window['w']}x{main_window['h']}")
        print()

        # 捕获截图序列
        screenshots = self.capture.capture_sequence(wid, interval, count, duration)

        if not screenshots:
            print("[screendig] No screenshots captured")
            return None

        self.session_data["screenshots"] = screenshots
        print()

        # 分析截图
        if analyze and self.analyzer:
            print("[screendig] === 分析截图 ===")
            for shot in screenshots:
                filename = shot["filename"]
                filepath = os.path.join(self.capture.session_dir, filename)

                if verbose:
                    print(f"[screendig] 分析: {filename}")

                result = self.analyzer.analyze_screenshot(filepath, baseline_path)
                self.session_data["analysis"][filename] = result
        elif analyze:
            print("[screendig] Analysis skipped: analyzer not available (missing PIL/numpy)")

        print()

        # 保存会话数据和生成报告
        self._save_session_data()

        # 生成报告
        try:
            from .report import generate_html_report
            generate_html_report(self.session_data, self.capture.session_dir)
        except ImportError as e:
            print(f"[screendig] Warning: Cannot generate report: {e}")
        except Exception as e:
            print(f"[screendig] Warning: Failed to generate HTML report: {e}")

        print()
        print("[screendig] === 调试会话完成 ===")
        print(f"[screendig] Session ID: {self.session_data['session_id']}")
        print(f"[screendig] Screenshots: {len(screenshots)}")
        print(f"[screendig] Session directory: {self.capture.session_dir}")

        return self.session_data

    def _save_session_data(self):
        """Save session data to JSON"""
        import json
        from pathlib import Path

        session_path = Path(self.capture.session_dir) / "session_data.json"
        with open(session_path, 'w', encoding='utf-8') as f:
            json.dump(self.session_data, f, indent=2, ensure_ascii=False)
        print(f"[screendig] Session data saved: {session_path}")
