"""
NP2kai screenshot capture tool.

Finds the NP2kai emulator window, captures it via ImageMagick (import),
and saves to a file. Handles the correct window selection (main display,
not toolbar/tray sub-windows).

Usage:
    python -m tools.diag.np2kai_screenshot
    python -m tools.diag.np2kai_screenshot -o /tmp/np2kai.png
    python -m tools.diag.np2kai_screenshot --wait 10
    python -m tools.diag.np2kai_screenshot --launch -- -o /tmp/boot.png
    python -m tools.diag.np2kai_screenshot --list-windows
"""

import argparse
import os
import subprocess
import sys
import time


WINDOW_TITLE_KEYWORD = "NP21kai"

TOOLBAR_SIZE_THRESHOLD = 300


def find_np2kai_windows():
    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", ""],
            capture_output=True, text=True, timeout=5
        )
        all_wids = result.stdout.strip().split()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("[screenshot] ERROR: xdotool not found or timed out")
        return []

    candidates = []
    for wid in all_wids:
        try:
            title = subprocess.run(
                ["xdotool", "getwindowname", wid],
                capture_output=True, text=True, timeout=2
            ).stdout.strip()
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            continue

        if "NP21kai" in title or "np21kai" in title.lower():
            geo = subprocess.run(
                ["xdotool", "getwindowgeometry", wid],
                capture_output=True, text=True, timeout=2
            ).stdout
            w = 0
            h = 0
            pos_x = 0
            pos_y = 0
            for line in geo.splitlines():
                if line.startswith("  Geometry:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        dims = parts[1]
                        if "x" in dims:
                            w_str, h_str = dims.split("x")
                            w = int(w_str)
                            h = int(h_str)
                if line.startswith("  Position:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        pos_str = parts[1]
                        if "," in pos_str:
                            px, py = pos_str.split(",")
                            pos_x = int(px)
                            pos_y = int(py)

            candidates.append({
                "wid": int(wid),
                "title": title,
                "w": w,
                "h": h,
                "x": pos_x,
                "y": pos_y,
            })

    return candidates


def pick_main_display(candidates):
    if not candidates:
        return None

    non_toolbar = [c for c in candidates if c["w"] > TOOLBAR_SIZE_THRESHOLD and c["h"] > TOOLBAR_SIZE_THRESHOLD]
    if non_toolbar:
        return max(non_toolbar, key=lambda c: c["w"] * c["h"])

    return max(candidates, key=lambda c: c["w"] * c["h"])


def capture(wid, output_path):
    result = subprocess.run(
        ["import", "-window", str(wid), output_path],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        print(f"[screenshot] ERROR: import failed: {error_msg}")
        return False
    if not os.path.isfile(output_path):
        print(f"[screenshot] ERROR: output file not created: {output_path}")
        return False
    return True


def launch_emulator():
    try:
        proc = subprocess.Popen(
            ["/usr/local/bin/wxnp21kai"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc
    except FileNotFoundError:
        print("[screenshot] ERROR: /usr/local/bin/wxnp21kai not found")
        return None


def list_windows(candidates):
    if not candidates:
        print("[screenshot] No NP2kai windows found")
        return

    print(f"[screenshot] Found {len(candidates)} NP2kai window(s):")
    print(f"  {'WID':>12s}  {'Title':30s}  {'Geometry':>12s}  {'Position':>14s}")
    print(f"  {'-'*12}  {'-'*30}  {'-'*12}  {'-'*14}")
    for c in candidates:
        geo = f"{c['w']}x{c['h']}"
        pos = f"({c['x']},{c['y']})"
        marker = "  <<< main display" if c == pick_main_display(candidates) else ""
        print(f"  {c['wid']:>12d}  {c['title']:30s}  {geo:>12s}  {pos:>14s}{marker}")

    main = pick_main_display(candidates)
    if main:
        print(f"\n  Recommended WID: {main['wid']} ({main['title']})")


def main():
    parser = argparse.ArgumentParser(description="Capture NP2kai emulator screenshot")
    parser.add_argument('-o', '--output', default='/tmp/np2kai_screenshot.png',
                        help='Output PNG path (default: /tmp/np2kai_screenshot.png)')
    parser.add_argument('-w', '--wait', type=int, default=5,
                        help='Seconds to wait for emulator boot before capture (default: 5)')
    parser.add_argument('--launch', action='store_true',
                        help='Launch emulator automatically before capture')
    parser.add_argument('--launch-timeout', type=int, default=30,
                        help='Max seconds to wait for emulator to appear (default: 30)')
    parser.add_argument('--list-windows', action='store_true',
                        help='List NP2kai windows and exit')
    parser.add_argument('--wid', type=int, default=None,
                        help='Capture specific window ID (auto-detect if omitted)')
    args = parser.parse_args()

    if args.list_windows:
        candidates = find_np2kai_windows()
        list_windows(candidates)
        sys.exit(0)

    emu_proc = None
    if args.launch:
        print(f"[screenshot] Launching emulator...")
        emu_proc = launch_emulator()
        if emu_proc is None:
            sys.exit(1)
        deadline = time.time() + args.launch_timeout
        found = False
        while time.time() < deadline:
            candidates = find_np2kai_windows()
            if pick_main_display(candidates) is not None:
                found = True
                break
            time.sleep(1)
        if not found:
            print(f"[screenshot] Emulator window not found within {args.launch_timeout}s")
            if emu_proc:
                emu_proc.terminate()
            sys.exit(1)

    if args.wid is not None:
        wid = args.wid
        candidates = find_np2kai_windows()
        if not any(c["wid"] == wid for c in candidates):
            print(f"[screenshot] WARNING: WID {wid} not found in NP2kai window list")
    else:
        candidates = find_np2kai_windows()
        main = pick_main_display(candidates)
        if main is None:
            print("[screenshot] No NP2kai window found")
            print("  Make sure the emulator is running, or use --launch")
            sys.exit(1)
        wid = main["wid"]
        print(f"[screenshot] Found: WID={wid} ({main['title']})  {main['w']}x{main['h']}")

    if args.wait > 0:
        print(f"[screenshot] Waiting {args.wait}s before capture...")
        time.sleep(args.wait)

    print(f"[screenshot] Capturing WID={wid} -> {args.output}")
    if capture(wid, args.output):
        size = os.path.getsize(args.output)
        print(f"[screenshot] OK: {size} bytes written")
    else:
        print("[screenshot] FAILED")
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
