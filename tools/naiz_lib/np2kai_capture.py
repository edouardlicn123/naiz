"""
np2kai_capture — shared NP2kai emulator window discovery, capture and config.

Consolidates near-identical code previously duplicated across:
  - tools/naiz_screendig/capture.py
plus the wxnp21kai.toml writer shared by screendig and np2kai_serial.
"""

import os
import subprocess

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore


WINDOW_TITLE_KEYWORD = "NP21kai"
TOOLBAR_SIZE_THRESHOLD = 300
EMULATOR = "/usr/local/bin/wxnp21kai"


def find_np2kai_windows():
    """Return a list of NP2kai window dicts via xdotool.

    Each dict has keys: wid, title, w, h, x, y.
    """
    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", ""],
            capture_output=True, text=True, timeout=5)
        all_wids = result.stdout.strip().split()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("[np2kai] ERROR: xdotool not found or timed out")
        return []

    candidates = []
    for wid in all_wids:
        try:
            title = subprocess.run(
                ["xdotool", "getwindowname", wid],
                capture_output=True, text=True, timeout=2).stdout.strip()
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            continue

        if WINDOW_TITLE_KEYWORD not in title and \
           WINDOW_TITLE_KEYWORD.lower() not in title.lower():
            continue

        geo = subprocess.run(
            ["xdotool", "getwindowgeometry", wid],
            capture_output=True, text=True, timeout=2).stdout
        w = h = pos_x = pos_y = 0
        for line in geo.splitlines():
            if line.startswith("  Geometry:"):
                parts = line.split()
                if len(parts) >= 2 and "x" in parts[1]:
                    ws, hs = parts[1].split("x")
                    w, h = int(ws), int(hs)
            elif line.startswith("  Position:"):
                parts = line.split()
                if len(parts) >= 2 and "," in parts[1]:
                    px, py = parts[1].split(",")
                    pos_x, pos_y = int(px), int(py)

        candidates.append({"wid": int(wid), "title": title,
                           "w": w, "h": h, "x": pos_x, "y": pos_y})

    return candidates


def pick_main_display(windows):
    """Return the main NP2kai display window dict, or None if none found."""
    if not windows:
        return None
    non_toolbar = [
        c for c in windows
        if c["w"] > TOOLBAR_SIZE_THRESHOLD and c["h"] > TOOLBAR_SIZE_THRESHOLD
    ]
    if non_toolbar:
        return max(non_toolbar, key=lambda c: c["w"] * c["h"])
    return max(windows, key=lambda c: c["w"] * c["h"])


def capture(wid, output_path, tag="[np2kai]"):
    """Capture a single window via ImageMagick 'import'. Returns bool."""
    try:
        result = subprocess.run(
            ["import", "-window", str(wid), output_path],
            capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        print(f"{tag} ERROR: import timed out for WID {wid}")
        return False
    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        print(f"{tag} ERROR: import failed: {error_msg}")
        return False
    if not os.path.isfile(output_path):
        print(f"{tag} ERROR: output file not created: {output_path}")
        return False
    return True


def launch_emulator(emulator=EMULATOR):
    """Launch the NP2kai emulator process. Returns Popen or None on failure."""
    try:
        return subprocess.Popen(
            [emulator], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print(f"[np2kai] ERROR: {emulator} not found")
        return None


def _toml_val(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        esc = v.replace('\\', '\\\\').replace('"', '\\"')
        esc = esc.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        return f'"{esc}"'
    if isinstance(v, list):
        items = ', '.join(_toml_val(x) for x in v)
        return f'[{items}]'
    return str(v)


def write_emulator_toml(updates, config_dir=None, config_path=None):
    """Read the existing wxnp21kai config, apply *updates* under the
    [NP21kai] section, and write it back.  Returns the config path.

    updates: dict of config keys -> str/int/bool/list.
    """
    if config_dir is None:
        config_dir = os.path.join(
            os.environ.get("XDG_CONFIG_HOME",
                           os.path.join(os.environ.get("HOME", "/tmp"), ".config")),
            "wxnp21kai")
    if config_path is None:
        config_path = os.path.join(config_dir, "wxnp21kai.toml")
    os.makedirs(config_dir, exist_ok=True)

    try:
        with open(config_path, 'rb') as f:
            cfg = tomllib.load(f)
    except (FileNotFoundError, ValueError):
        cfg = {}

    sec = cfg.setdefault('NP21kai', {})
    sec.update(updates)

    lines = []
    for sk, sv in cfg.items():
        lines.append(f'[{sk}]')
        for k, v in sv.items():
            lines.append(f'{k} = {_toml_val(v)}')
        lines.append('')

    with open(config_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return config_path