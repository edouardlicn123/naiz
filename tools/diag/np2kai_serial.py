"""
NP2kai serial debugging tool.

Generates a serialwrite COM, injects it into the HDI, patches AUTOEXEC.BAT,
creates a PTY for COM1, launches the emulator, and captures serial output.

Usage:
    python -m tools.diag.np2kai_serial --game demo-A1 --hdi disks/demo-A1.hdi
    python -m tools.diag.np2kai_serial --game demo-A1 --hdi disks/demo-A1.hdi --timeout 20
    python -m tools.diag.np2kai_serial --hdi disks/demo-A1.hdi --listen-only
"""

import argparse
import os
import pty
import select
import shutil
import struct
import subprocess
import sys
import threading
import time
import tomllib

PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..'))
GAMES_DIR = os.path.join(PROJECT_ROOT, 'games')
DISKS_DIR = os.path.join(PROJECT_ROOT, 'disks')
EMULATOR = "/usr/local/bin/wxnp21kai"
CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME",
                            os.path.join(os.environ["HOME"], ".config")),
                          "wxnp21kai")
CONFIG_PATH = os.path.join(CONFIG_DIR, "wxnp21kai.toml")


def generate_com():
    """Generate serialwrite COM to a temp file."""
    from tools.diag.gen_com import make_serialwrite
    code = make_serialwrite()
    out = "/tmp/serialwrite.com"
    with open(out, "wb") as f:
        f.write(code)
    return out


def inject_com(game_name, com_path):
    """Copy COM to game dir and rebuild HDI."""
    from tools.naiz_img.inject_common import inject_into_hdi
    game_dir = os.path.join(GAMES_DIR, game_name)
    os.makedirs(game_dir, exist_ok=True)
    shutil.copy2(com_path, os.path.join(game_dir, "serialwrite.com"))
    output = os.path.join(DISKS_DIR, f"{game_name}.hdi")
    print(f"[serial] Injecting serialwrite.com into {output}")
    inject_into_hdi(output, game_name, game_dir)
    return output


def backup_autoexec(hdi_path):
    """Read current AUTOEXEC.BAT content for later restore."""
    from tools.diag.hdi_patch_autoexec import _read_root_entry, _dos_name
    from tools.naiz_img.hdi import HDIImage
    from tools.naiz_img.fat import NAIZFatFS
    img = HDIImage(hdi_path)
    fs = NAIZFatFS(img)
    name_8_3 = _dos_name("AUTOEXEC.BAT")
    fname = name_8_3[0] + name_8_3[1]
    entry_off, entry = _read_root_entry(fs, fname)
    if entry is None:
        print("[serial] WARNING: AUTOEXEC.BAT not found, nothing to backup")
        return None
    orig_size = struct.unpack_from('<I', entry, 28)[0]
    orig_cluster = struct.unpack_from('<H', entry, 26)[0]
    chain = fs._get_cluster_chain(orig_cluster)
    cluster_off = fs.data_offset + (chain[0] - 2) * fs.cluster_size
    content = fs._read_bytes(cluster_off, orig_size)
    return content


def patch_autoexec_in_hdi(hdi_path, content_bytes):
    """Patch AUTOEXEC.BAT in HDI."""
    from tools.diag.hdi_patch_autoexec import patch_autoexec
    patch_autoexec(hdi_path, content_bytes)


def save_toml(hdi_abs_path, slave_name):
    """Write wxnp21kai.toml with serial config."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        with open(CONFIG_PATH, 'rb') as f:
            cfg = tomllib.load(f)
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        cfg = {}

    sec = cfg.setdefault('NP21kai', {})
    sec['SCSIHDD0'] = hdi_abs_path
    sec['com1_m_o'] = slave_name
    sec['com1_m_i'] = slave_name
    sec['com1port'] = 1  # COMPORT_COM1 (0 = COMPORT_NONE = disabled)
    sec['com1para'] = 0xE3
    sec['com1_bps'] = 9600

    def _toml_val(v):
        if isinstance(v, bool):
            return 'true' if v else 'false'
        if isinstance(v, int):
            return str(v)
        if isinstance(v, str):
            return "'" + v.replace("'", "''") + "'"
        if isinstance(v, list):
            items = ', '.join(_toml_val(x) for x in v)
            return f'[{items}]'
        return str(v)

    lines = []
    for sk, sv in cfg.items():
        lines.append(f'[{sk}]')
        for k, v in sv.items():
            lines.append(f'{k} = {_toml_val(v)}')
        lines.append('')

    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return CONFIG_PATH


def run_emulator(hdi_path, serial_out, timeout_sec):
    """Launch emulator with serial PTY, capture output."""
    print(f"[serial] Creating PTY for serial capture...")
    master_fd, slave_fd = pty.openpty()
    slave_name = os.ttyname(slave_fd)

    hdi_abs = os.path.abspath(hdi_path)
    cfg_path = save_toml(hdi_abs, slave_name)
    print(f"[serial] Config: {cfg_path}")
    print(f"[serial] PTY slave: {slave_name}")
    print(f"[serial] Starting emulator (timeout={timeout_sec}s)...")
    print()

    proc = subprocess.Popen(
        [EMULATOR],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    captured_data = []
    serial_stop = threading.Event()

    def read_serial():
        while not serial_stop.is_set():
            r, _, _ = select.select([master_fd], [], [], 0.5)
            if r:
                try:
                    data = os.read(master_fd, 4096)
                    if not data:
                        break
                    text = data.decode("utf-8", errors="replace")
                    print(text, end="", flush=True)
                    captured_data.append(text)
                except OSError:
                    break

    st = threading.Thread(target=read_serial, daemon=True)
    st.start()

    exit_code = None
    try:
        proc.wait(timeout=timeout_sec)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=5)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
            exit_code = proc.returncode

    serial_stop.set()
    st.join(timeout=2)
    os.close(master_fd)
    os.close(slave_fd)

    output = "".join(captured_data)
    if serial_out:
        with open(serial_out, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"\n[serial] Output saved to: {serial_out}")

    print(f"\n[serial] Emulator exit code: {exit_code}")
    return output


def main():
    parser = argparse.ArgumentParser(
        description="NP2kai serial debugging tool")
    parser.add_argument('--game', '-g',
                        help='Game name (directory under games/)')
    parser.add_argument('--hdi',
                        help='HDI path (default: disks/<game>.hdi)')
    parser.add_argument('--timeout', '-t', type=int, default=30,
                        help='Emulator timeout in seconds (default: 30)')
    parser.add_argument('-o', '--output',
                        help='Save serial output to file')
    parser.add_argument('--listen-only', action='store_true',
                        help='Only listen on serial, do not inject or patch')
    parser.add_argument('--no-restore', action='store_true',
                        help='Do not restore AUTOEXEC.BAT after test')
    args = parser.parse_args()

    if not args.hdi and not args.game:
        parser.print_help()
        sys.exit(1)

    hdi_path = args.hdi
    if not hdi_path and args.game:
        hdi_path = os.path.join(DISKS_DIR, f"{args.game}.hdi")

    if not os.path.isfile(hdi_path):
        print(f"[serial] ERROR: HDI not found: {hdi_path}")
        sys.exit(1)

    autoexec_backup = None

    if not args.listen_only:
        if not args.game:
            print("[serial] ERROR: --game required for injection")
            sys.exit(1)

        com_path = generate_com()
        print(f"[serial] Generated: {com_path}")
        hdi_path = inject_com(args.game, com_path)

        print(f"[serial] Backing up current AUTOEXEC.BAT...")
        autoexec_backup = backup_autoexec(hdi_path)
        if autoexec_backup:
            print(f"[serial] Backed up {len(autoexec_backup)} bytes")

        game_upper = args.game.upper()
        autoexec_content = f"@ECHO OFF\r\nCD \\{game_upper}\r\nSERIALWRITE.COM"
        print(f"[serial] Patching AUTOEXEC.BAT (CD \\{game_upper} + SERIALWRITE.COM)")
        patch_autoexec_in_hdi(hdi_path, autoexec_content.encode())

    if not os.path.isdir(CONFIG_DIR):
        print(f"[serial] ERROR: config dir not found: {CONFIG_DIR}")
        print("  Run install_env.py or create ~/.config/wxnp21kai/ first")
        sys.exit(1)

    output = run_emulator(hdi_path, args.output, args.timeout)

    if "Hello from DOS!" in output:
        print("[serial] RESULT: DOS serial output received - boot chain OK")
    elif output:
        print(f"[serial] RESULT: Received {len(output)} chars, "
              f"no expected marker ('Hello from DOS!')")
    else:
        print("[serial] RESULT: No serial output received")
        print("  Possible causes: DOS didn't boot, CONFIG.SYS hung, "
              "or COM port init failed")

    if autoexec_backup and not args.no_restore:
        print(f"[serial] Restoring AUTOEXEC.BAT ({len(autoexec_backup)} bytes)")
        patch_autoexec_in_hdi(hdi_path, autoexec_backup)


if __name__ == '__main__':
    main()
