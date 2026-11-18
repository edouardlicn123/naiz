#!/usr/bin/env python3
"""
env_test.py — Test/check command handlers for Naiz environment setup
"""
import os
import shutil
import subprocess
import sys
from datetime import datetime
try:
    from i18n import tr
except ImportError:  # imported as `tools.env_setup` (repo root on sys.path)
    from tools.i18n import tr
from ..naiz_lib import COMMERCIAL_BIOS_DIR, np2kai_capture
from .env_utils import (
    LOG_DIR, LOG_FILE,
    NP2KAI_DIR,
    EMULATORS, EMULATOR_DEV,
    MIRROR,
    log_write, run_step, _sudo_init,
    _resolve_repo, _get_np2kai_source,
    _pkg_install, _run_check, _check_file, _check_np2kai_patches,
)


def _pick_emulator(emulator_arg):
    available = {}
    for name, path in EMULATORS.items():
        if os.path.exists(path):
            available[name] = path

    if not available:
        dev_exists = any(os.path.exists(p) for p in EMULATOR_DEV.values())
        if not dev_exists:
            print(f"[✗] {tr('No NP2kai emulator found')}")
            for name, path in EMULATORS.items():
                print(f"    {name}: {path}")
            print(f"    {tr('Please run the menu option to build the emulator first')}")
            sys.exit(1)
        for name, path in EMULATOR_DEV.items():
            if os.path.exists(path):
                return name

    if emulator_arg:
        if emulator_arg not in EMULATORS:
            print(f"[✗] {tr('Invalid emulator:')} {emulator_arg}")
            print(f"    {tr('Available:')} {', '.join(EMULATORS.keys())}")
            sys.exit(1)
        if emulator_arg not in available:
            print(f"[✗] {emulator_arg} {tr('not installed:')} {EMULATORS[emulator_arg]}")
            sys.exit(1)
        return emulator_arg

    if len(available) == 1:
        return list(available.keys())[0]

    print(f"\n{tr('Select emulator version:')}")
    keys = list(available.keys())
    defaults = {"ia32": tr("wxWidgets/GTK3, full SCSI/IDE HDD support (recommended)")}
    for i, k in enumerate(keys, 1):
        desc = defaults.get(k, "")
        print(f"  {i}) {k} — {desc}")
    while True:
        try:
            choice = input(f"  {tr('Choose')} [1-{len(keys)}] ({tr('default')} 1): ").strip()
            if choice == "":
                idx = 0
            else:
                idx = int(choice) - 1
            if 0 <= idx < len(keys):
                return keys[idx]
        except (ValueError, IndexError):
            pass
        print(f"  {tr('Invalid selection, please try again')}")


def cmd_test_hdi(hdi_path=None, emulator=None, serial=False, auto=False):
    print("")
    print(f"===== {tr('NP2kai test launch')} =====")

    project_root = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    disks_dir = os.path.join(project_root, "disks")

    emu_name = _pick_emulator(emulator)
    binary = EMULATORS.get(emu_name, EMULATORS["ia32"])
    dev_bin = EMULATOR_DEV.get(emu_name, "")
    if dev_bin and os.path.exists(dev_bin):
        binary = dev_bin
    print(f"  {tr('emulator:')} {emu_name} -> {binary}")

    if hdi_path:
        if os.path.isfile(hdi_path):
            selected = hdi_path
        else:
            guess = os.path.join(disks_dir, f"{hdi_path}.hdi")
            if os.path.isfile(guess):
                selected = guess
            else:
                print(f"[✗] {tr('HDI file does not exist:')} {hdi_path}")
                print(f"    {tr('Also not found:')} {guess}")
                sys.exit(1)
    else:
        if not os.path.isdir(disks_dir):
            print(f"[✗] {tr('disks/ directory not found:')} {disks_dir}")
            sys.exit(1)

        hdis = sorted([f for f in os.listdir(disks_dir) if f.endswith(".hdi")])
        if not hdis:
            print(f"[✗] {tr('No .hdi files under disks/')}")
            print(f"    {tr('Please run make_hdi.sh first to generate a disk image')}")
            sys.exit(1)

        if len(hdis) == 1:
            selected = os.path.join(disks_dir, hdis[0])
        else:
            print(f"{tr('Available HDI images:')}")
            for i, name in enumerate(hdis, 1):
                print(f"  {i}) {name}")
            while True:
                try:
                    choice = input(f"  {tr('Choose test image')} [1-{len(hdis)}]: ").strip()
                    idx = int(choice) - 1
                    if 0 <= idx < len(hdis):
                        selected = os.path.join(disks_dir, hdis[idx])
                        break
                except (ValueError, IndexError):
                    pass
                print(f"  {tr('Invalid selection, please try again')}")

    os.makedirs(os.path.join(project_root, "logs"), exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_name = f"test_{os.path.splitext(os.path.basename(selected))[0]}_{timestamp}.log"
    log_path = os.path.join(project_root, "logs", log_name)

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("=== Naiz NP2kai Test ===\n")
        f.write(f"HDI:  {selected}\n")
        f.write(f"Time: {datetime.now().isoformat()}\n")

    cfg_dir = os.path.join(os.environ.get("XDG_CONFIG_HOME",
                                        os.path.join(os.environ["HOME"], ".config")),
                          "wxnp21kai")
    os.makedirs(cfg_dir, exist_ok=True)
    cfg_path = os.path.join(cfg_dir, "wxnp21kai.toml")

    bios_src = COMMERCIAL_BIOS_DIR
    for rom in ["bios.rom", "BIOS.ROM", "font.rom", "FONT.ROM"]:
        src = os.path.join(bios_src, rom)
        if not os.path.exists(src):
            continue
        dst_name = rom.lower()
        dst = os.path.join(cfg_dir, dst_name)
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copy2(src, dst)
            print(f"  [✓] {tr('Copied:')} {src} -> {dst_name}")

    sec = {'SCSIHDD0': selected}

    serial_pty = None
    if serial:
        stale = np2kai_capture.kill_stale_emulators()
        if stale:
            print(f"  {tr('Cleaning up stale emulator instances:')} {stale}")
        import pty as pty_mod
        master_fd, slave_fd = pty_mod.openpty()
        slave_name = os.ttyname(slave_fd)
        sec['com1_m_o'] = slave_name
        sec['com1_m_i'] = slave_name
        sec['com1port'] = 1
        sec['com1para'] = 0xE3
        sec['com1_bps'] = 9600
        serial_pty = (master_fd, slave_fd, slave_name)

    np2kai_capture.write_emulator_toml(sec, config_dir=cfg_dir, config_path=cfg_path)

    cmd = [binary]
    # Serial capture must boot DOS on its own; without '--start' the
    # emulator stalls on the config window and the serial chain is silent
    # until a manual click.  `--auto` additionally enables auto-run.
    if serial or auto:
        cmd.append("--start")
    print(f"  {tr('Launching:')} {' '.join(cmd)}")

    if serial and serial_pty:
        master_fd, slave_fd, slave_name = serial_pty
        # Keep slave_fd open for the whole capture: NP2kai opens the PTY
        # slave by path after the fork, and closing it first makes the slave
        # endpoint unopenable -> serial is silently empty (0.2.132).
        serial_log = os.path.join(project_root, "logs",
                                  f"serial_{os.path.splitext(os.path.basename(selected))[0]}.log")
        with open(serial_log, "wb") as slog:
            process = subprocess.Popen(cmd, stdout=None, stderr=None)
            print(f"  {tr('Serial log:')} {serial_log}")
            try:
                while True:
                    data = os.read(master_fd, 4096)
                    if not data:
                        break
                    slog.write(data)
                    slog.flush()
                    sys.stdout.buffer.write(data)
                    sys.stdout.flush()
            except OSError:
                pass
            process.wait()
        try:
            os.close(master_fd)
            os.close(slave_fd)
        except OSError:
            pass
    else:
        subprocess.run(cmd)

    print("")


def cmd_audio_latency(level):
    """Set the NP2kai audio buffer latency (BGM artefact mitigation).

    devdoc 154: the emulator's SDL output path inserts silence whenever its
    audio queue starves, giving a periodic AM whose frequency follows the
    buffer block size (Latencys -> np2cfg.delayms).  Pushing Latencys to the
    Long/Max cluster moves that artefact below audibility.  This is a
    host-side emulator setting, so it is applied here (launcher), never by
    the game.  Runs `makegame.sh audio` -> this command.
    """
    print("")
    print(f"===== {tr('Emulator audio latency setting')} =====")

    levels = np2kai_capture.audio_latency_levels()
    by_key = {k: m for k, _l, m, _b in levels}
    if level is None or level not in by_key:
        print(f"[✗] {tr('Unknown level:')} {level}")
        print(f"    {tr('Available:')} " + ", ".join(k for k, _l, _m, _b in levels))
        sys.exit(1)

    try:
        cpath = np2kai_capture.apply_audio_latency(level)
    except ValueError:
        print(f"[✗] {tr('Unknown level:')} {level}")
        sys.exit(1)

    if cpath is None:
        print(f"[✓] {tr('Off — emulator audio latency unchanged (using its current settings)')}")
    else:
        print(f"[✓] {tr('Written to:')} {cpath}")
        print(f"    Latencys = {by_key[level]}"
              f"   SampleHz = {np2kai_capture.AUDIO_LATENCY_SAMPLE_HZ}")
        print(f"    ({tr('global setting, affects all games; to revert choose Off or change it back manually')})")
    print("")


def cmd_check():
    project_root = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

    print("")
    print(f"───── {tr('Emulators')} ─────")
    _check_file("wxnp21kai (ia32)",
        "/usr/local/bin/wxnp21kai")
    _check_file("np2kai_libretro",
        "~/.config/retroarch/cores/np2kai_libretro.so")
    _check_file("sdlnp2kai (i286)",
        "/usr/local/bin/sdlnp2kai")

    print(f"\n───── {tr('Toolchains')} ─────")
    if os.path.exists("/opt/gcc-ia16/bin/ia16-elf-gcc"):
        _run_check("ia16-elf-gcc",
            ["/opt/gcc-ia16/bin/ia16-elf-gcc", "--version"])
    else:
        _check_file("ia16-elf-gcc", "/opt/gcc-ia16/bin/ia16-elf-gcc")
    _check_file("wcl386",
        "~/open-watcom-v2/rel/binl64/wcl386")
    _check_file("ia16-elf-g++",
        "/opt/gcc-ia16/bin/ia16-elf-g++")

    print(f"\n───── {tr('Dependency libraries')} ─────")
    _run_check("SDL2",
        ["pkg-config", "--modversion", "sdl2"])
    _run_check("GTK3",
        ["pkg-config", "--modversion", "gtk+-3.0"])
    _run_check("wxWidgets",
        ["wx-config", "--version"])

    print(f"\n───── {tr('Environment')} ─────")
    _run_check("Python",
        ["python3", "--version"])
    _run_check("CMake",
        ["cmake", "--version"])
    _run_check("Git",
        ["git", "--version"])

    print(f"\n───── {tr('NP2kai patches')} ─────")
    _check_np2kai_patches()

    print("")



