#!/usr/bin/env python3
"""
Naiz 开发环境安装工具
由 start.sh 的 env_menu 调用，CLI 子命令模式。
"""

import argparse
import os
import sys
from datetime import datetime

try:
    from i18n import tr
except ImportError:  # imported as `tools.env_setup` (repo root on sys.path)
    from tools.i18n import tr
from .env_utils import (
    LOG_DIR, LOG_FILE, MIRROR,
    _sudo_init, _set_mirror, _mirror_init,
    _read_conf, _write_conf,
    _pkg_install,
)
from .env_build import (
    cmd_pip_install, cmd_install_watcom,
    cmd_build_i286, cmd_gcc_ia16, cmd_np2kai,
    cmd_deps,
)
from .env_test import (
    cmd_test_hdi, cmd_check, cmd_audio_latency,
)


def cmd_system_tools():
    _pkg_install(["build-essential", "cmake", "git", "pkg-config",
                  "libgtk-3-dev", "libglib2.0-dev"],
                 tr("Installing system tools"))


def cmd_mirror():
    """Interactively choose the Git repository source (GitHub / domestic mirror)."""
    cfg = _read_conf()
    current = cfg.get("mirror", "github")
    print(f"\n───── {tr('Git repository source setting')} ─────")
    print(f"  {tr('Current:')} {current}")
    print(f"  1) {tr('GitHub (direct overseas connection)')}")
    print(f"  2) {tr('Domestic mirror (Gitee/GitCode, mainland China acceleration)')}")
    m = input(f"{tr('Please choose')} [1/2]: ").strip()
    if m == "1":
        _set_mirror("github")
    elif m == "2":
        _set_mirror("china")
    else:
        print(tr("Invalid option"))


def main():
    VALID_COMMANDS = {"check", "deps", "gcc-ia16", "np2kai",
                      "system-tools", "pip-install",
                      "build-i286", "test-hdi", "install-watcom",
                      "mirror", "audio-latency"}
    parser = argparse.ArgumentParser(description=tr("Naiz development environment installer"))
    parser.add_argument(
        "command",
        nargs="?",
        default=None,
        help=tr("Subcommand to run (enter interactive mode with no args)"),
    )
    parser.add_argument(
        "--hdi",
        default=None,
        help=tr("HDI path (test-hdi only)"),
    )
    parser.add_argument(
        "--emulator", "-e",
        default=None,
        choices=["ia32"],
        help=tr("Emulator version: ia32 (default, wxnp21kai) (test-hdi only)"),
    )
    parser.add_argument(
        "--latency",
        default=None,
        help=tr("Emulator audio buffer latency level: off/short/normal/long/max (audio-latency only)"),
    )
    parser.add_argument(
        "--serial",
        action="store_true",
        default=False,
        help=tr("Enable serial debug (PTY pipe, logs to logs/serial_<game>.log) (test-hdi only)"),
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        default=False,
        help=tr("Skip interactive prompts, launch emulator directly (test-hdi only)"),
    )
    parser.add_argument(
        "--mirror",
        default=None,
        choices=["github", "china"],
        help=tr("Git repository source: github (default) or china (domestic mirror)"),
    )
    args = parser.parse_args()

    global MIRROR
    if args.mirror:
        _set_mirror(args.mirror)
    elif args.command in (None, "mirror"):
        # `start.sh mirror` (no subcommand) and the explicit `mirror`
        # subcommand both go straight to the source picker.
        MIRROR = _mirror_init()
        cmd_mirror()
        return
    else:
        MIRROR = _mirror_init()

    if args.command not in VALID_COMMANDS:
        print(f"[✗] {tr('Unknown subcommand:')} {args.command}")
        print(f"    {tr('Available:')} {', '.join(sorted(VALID_COMMANDS))}")
        sys.exit(1)

    if args.command != "check":
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"Operation: {args.command}\n")
            f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*60}\n\n")

    needs_sudo = {"deps", "gcc-ia16", "np2kai",
                  "system-tools", "build-i286",
                  "install-watcom"}
    if args.command in needs_sudo:
        _sudo_init()

    commands = {
        "check": cmd_check,
        "deps": cmd_deps,
        "gcc-ia16": cmd_gcc_ia16,
        "np2kai": cmd_np2kai,
        "system-tools": cmd_system_tools,
        "pip-install": cmd_pip_install,
        "build-i286": cmd_build_i286,
        "test-hdi": cmd_test_hdi,
        "install-watcom": cmd_install_watcom,
        "audio-latency": lambda: cmd_audio_latency(args.latency),
    }
    if args.command == "test-hdi":
        cmd_test_hdi(hdi_path=args.hdi, emulator=args.emulator, serial=args.serial, auto=args.auto)
    else:
        commands[args.command]()


if __name__ == "__main__":
    main()
