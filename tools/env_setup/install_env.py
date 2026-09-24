#!/usr/bin/env python3
"""
Naiz 开发环境安装工具
由 start.sh 的 env_menu 调用，CLI 子命令模式。
"""

import argparse
import os
import sys
from datetime import datetime

from .env_utils import (
    LOG_DIR, LOG_FILE, MIRROR,
    _sudo_init, _set_mirror, _mirror_init,
    _read_conf, _write_conf,
    _pkg_install,
)
from .env_build import (
    cmd_pip_install, cmd_install_watcom, cmd_install_djgpp,
    cmd_build_i286, cmd_gcc_ia16, cmd_np2kai,
    cmd_np2kai_libretro, cmd_deps,
)
from .env_test import (
    cmd_test_hdi, cmd_check, cmd_retroarch,
)


def cmd_system_tools():
    _pkg_install(["build-essential", "cmake", "git", "pkg-config",
                  "libgtk-3-dev", "libglib2.0-dev"],
                 "安装系统工具")


def cmd_backup_emu():
    print("")
    print("===== 安装备用模拟器 (RetroArch + NP2kai libretro) =====")
    cmd_np2kai_libretro()
    cmd_retroarch()


def cmd_mirror():
    """Interactively choose the Git repository source (GitHub / domestic mirror)."""
    cfg = _read_conf()
    current = cfg.get("mirror", "github")
    print("\n───── Git 仓库来源设置 ─────")
    print(f"  当前: {current}")
    print("  1) GitHub（海外直连）")
    print("  2) 国内镜像（Gitee/GitCode，中国大陆加速）")
    m = input("请选择 [1/2]: ").strip()
    if m == "1":
        _set_mirror("github")
    elif m == "2":
        _set_mirror("china")
    else:
        print("无效选项")


def main():
    VALID_COMMANDS = {"check", "deps", "gcc-ia16", "np2kai", "np2kai-libretro",
                      "retroarch", "system-tools", "backup-emu", "pip-install",
                      "build-i286", "test-hdi", "install-watcom", "install-djgpp",
                      "mirror"}
    parser = argparse.ArgumentParser(description="Naiz 开发环境安装工具")
    parser.add_argument(
        "command",
        nargs="?",
        default=None,
        help="要执行的子命令 (无参时进入交互模式)",
    )
    parser.add_argument(
        "--hdi",
        default=None,
        help="指定 HDI 路径 (仅 test-hdi)",
    )
    parser.add_argument(
        "--emulator", "-e",
        default=None,
        choices=["ia32"],
        help="指定模拟器版本: ia32 (默认, wxnp21kai) (仅 test-hdi)",
    )
    parser.add_argument(
        "--serial",
        action="store_true",
        default=False,
        help="启用串口调试 (PTY 管道，日志写入 logs/serial_<game>.log) (仅 test-hdi)",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        default=False,
        help="跳过交互提示，直接启动模拟器 (仅 test-hdi)",
    )
    parser.add_argument(
        "--mirror",
        default=None,
        choices=["github", "china"],
        help="Git 仓库来源: github (默认) 或 china (国内镜像)",
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
        print(f"[✗] 未知子命令: {args.command}")
        print(f"    可选: {', '.join(sorted(VALID_COMMANDS))}")
        sys.exit(1)

    if args.command != "check":
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"操作: {args.command}\n")
            f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*60}\n\n")

    needs_sudo = {"deps", "gcc-ia16", "np2kai", "np2kai-libretro",
                  "retroarch", "system-tools", "backup-emu", "build-i286",
                  "install-watcom", "install-djgpp"}
    if args.command in needs_sudo:
        _sudo_init()

    commands = {
        "check": cmd_check,
        "deps": cmd_deps,
        "gcc-ia16": cmd_gcc_ia16,
        "np2kai": cmd_np2kai,
        "np2kai-libretro": cmd_np2kai_libretro,
        "retroarch": cmd_retroarch,
        "system-tools": cmd_system_tools,
        "backup-emu": cmd_backup_emu,
        "pip-install": cmd_pip_install,
        "build-i286": cmd_build_i286,
        "test-hdi": cmd_test_hdi,
        "install-watcom": cmd_install_watcom,
        "install-djgpp": cmd_install_djgpp,
    }
    if args.command == "test-hdi":
        cmd_test_hdi(hdi_path=args.hdi, emulator=args.emulator, serial=args.serial, auto=args.auto)
    else:
        commands[args.command]()


if __name__ == "__main__":
    main()
