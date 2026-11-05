"""
NP2kai 截图调试工具 - CLI 入口点

基于 tools/diag/np2kai_screenshot.py 改进，
添加连续截图、自动分析功能。

Usage:
    # 单次截图（兼容原工具）
    python -m naiz_screendig -o /tmp/screenshot.png

    # 连续截图（默认 2 秒间隔）
    python -m naiz_screendig --continuous

    # 连续截图 30 秒
    python -m naiz_screendig -c -d 30

    # 连续截图 20 张，并自动分析
    python -m naiz_screendig -c -n 20 --analyze

    # 启动模拟器并连续截图
    python -m naiz_screendig --launch -c -d 60 --analyze
"""

import argparse
import os
import subprocess
import sys
import time

from .screendig import ScreenDig
from .capture import NP2kaiCapture


def main():
    parser = argparse.ArgumentParser(
        description="NP2kai 截图调试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 连续截图（2秒间隔，无限）
  python -m naiz_screendig -c

  # 连续截图30秒
  python -m naiz_screendig -c -d 30

  # 截图20张并分析
  python -m naiz_screendig -c -n 20 --analyze

  # 自动启动模拟器并调试
  python -m naiz_screendig --launch -c -d 60 --analyze
        """
    )

    # 单次截图参数（兼容原工具）
    parser.add_argument('-o', '--output', default=None,
                        help='单次截图输出路径 (默认: /tmp/np2kai_screenshot.png)')
    parser.add_argument('-w', '--wait', type=int, default=5,
                        help='等待秒数后再截图 (默认: 5)')
    parser.add_argument('--list-windows', action='store_true',
                        help='列出 NP2kai 窗口并退出')

    # 连续截图参数
    parser.add_argument('--continuous', '-c', action='store_true',
                        help='连续截图模式')
    parser.add_argument('--interval', '-i', type=float, default=2.0,
                        help='截图间隔秒数 (默认: 2.0)')
    parser.add_argument('--count', '-n', type=int, default=None,
                        help='截图数量 (默认: 无限，Ctrl+C 停止)')
    parser.add_argument('--duration', '-d', type=float, default=None,
                        help='总持续时间秒数 (默认: 无限)')

    # 输出控制
    parser.add_argument('--output-dir', '-D', default='/tmp/naiz_screendig',
                        help='输出目录 (默认: /tmp/naiz_screendig)')

    # 分析参数
    parser.add_argument('--analyze', '-a', action='store_true',
                        help='分析截图并生成报告')
    parser.add_argument('--baseline', '-b', default=None,
                        help='基准图像路径（用于对比）')

    # 模拟器控制
    parser.add_argument('--launch', action='store_true',
                        help='自动启动 NP2kai 模拟器')
    parser.add_argument('--launch-timeout', type=int, default=30,
                        help='等待模拟器启动的最大秒数 (默认: 30)')

    args = parser.parse_args()

    # 列出窗口模式
    if args.list_windows:
        capture = NP2kaiCapture(args.output_dir)
        windows = capture.find_windows()
        if not windows:
            print("No NP2kai windows found")
            sys.exit(1)
        print(f"Found {len(windows)} NP2kai window(s):")
        for w in windows:
            main_w = capture.pick_main_display(windows)
            marker = "  <<< main" if main_w and w["wid"] == main_w["wid"] else ""
            print(f"  WID={w['wid']:>10d}  {w['w']}x{w['h']}  {w['title']}{marker}")
        sys.exit(0)

    # 启动模拟器
    emu_proc = None
    if args.launch:
        print("[main] Launching NP2kai emulator...")
        capture = NP2kaiCapture(args.output_dir)
        emu_proc = capture.launch_emulator()
        if emu_proc is None:
            sys.exit(1)

        # 等待模拟器窗口出现
        deadline = time.time() + args.launch_timeout
        found = False
        while time.time() < deadline:
            windows = capture.find_windows()
            if capture.pick_main_display(windows) is not None:
                found = True
                break
            time.sleep(1)

        if not found:
            print(f"[main] Emulator window not found within {args.launch_timeout}s")
            if emu_proc:
                emu_proc.terminate()
            sys.exit(1)
        print("[main] Emulator started")

    # 连续截图模式
    if args.continuous:
        screendig = ScreenDig(args.output_dir)
        result = screendig.run_debug_session(
            interval=args.interval,
            count=args.count,
            duration=args.duration,
            analyze=args.analyze,
            baseline_path=args.baseline,
            verbose=True
        )

        if emu_proc:
            emu_proc.terminate()
            try:
                emu_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                emu_proc.kill()

        sys.exit(0 if result else 1)

    # 单次截图模式（兼容原工具）
    output_path = args.output or '/tmp/np2kai_screenshot.png'
    output_dir = os.path.dirname(output_path) or '/tmp'
    capture = NP2kaiCapture(output_dir)

    windows = capture.find_windows()
    main_window = capture.pick_main_display(windows)
    if main_window is None:
        print("[main] No NP2kai window found")
        if emu_proc:
            emu_proc.terminate()
        sys.exit(1)

    wid = main_window["wid"]
    print(f"[main] Window: {main_window['title']} ({main_window['w']}x{main_window['h']})")

    if args.wait > 0:
        print(f"[main] Waiting {args.wait}s...")
        time.sleep(args.wait)

    print(f"[main] Capturing -> {output_path}")
    if capture.capture_single(wid, output_path):
        size = os.path.getsize(output_path)
        print(f"[main] OK: {size} bytes")

        if args.analyze:
            from .analyze import NP2kaiAnalyzer
            analyzer = NP2kaiAnalyzer()
            result = analyzer.analyze_screenshot(output_path, args.baseline)
            print(f"[main] Analysis: {result}")
    else:
        print("[main] FAILED")
        if emu_proc:
            emu_proc.terminate()
        sys.exit(1)

    if emu_proc:
        emu_proc.terminate()
        try:
            emu_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            emu_proc.kill()


if __name__ == '__main__':
    main()
