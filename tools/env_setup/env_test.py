#!/usr/bin/env python3
"""
env_test.py — Test/check command handlers for Naiz environment setup
"""
import os
import shutil
import subprocess
import sys
from datetime import datetime
from ..naiz_lib import COMMERCIAL_BIOS_DIR, np2kai_capture
from .env_utils import (
    LOG_DIR, LOG_FILE,
    NP2KAI_DIR,
    RETROARCH_LATEST, RETROARCH_APPIMAGE_URL,
    RETROARCH_APPIMAGE_DIR, RETROARCH_BIN_SYMLINK,
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
            print("[✗] 未找到任何 NP2kai 模拟器")
            for name, path in EMULATORS.items():
                print(f"    {name}: {path}")
            print("    请先运行菜单选项编译模拟器")
            sys.exit(1)
        for name, path in EMULATOR_DEV.items():
            if os.path.exists(path):
                return name

    if emulator_arg:
        if emulator_arg not in EMULATORS:
            print(f"[✗] 无效模拟器: {emulator_arg}")
            print(f"    可选: {', '.join(EMULATORS.keys())}")
            sys.exit(1)
        if emulator_arg not in available:
            print(f"[✗] {emulator_arg} 未安装: {EMULATORS[emulator_arg]}")
            sys.exit(1)
        return emulator_arg

    if len(available) == 1:
        return list(available.keys())[0]

    print("\n选择模拟器版本:")
    keys = list(available.keys())
    defaults = {"ia32": "wxWidgets/GTK3, SCSI/IDE HDD 完整支持 (推荐)"}
    for i, k in enumerate(keys, 1):
        desc = defaults.get(k, "")
        print(f"  {i}) {k} — {desc}")
    while True:
        try:
            choice = input(f"  选择 [1-{len(keys)}] (默认 1): ").strip()
            if choice == "":
                idx = 0
            else:
                idx = int(choice) - 1
            if 0 <= idx < len(keys):
                return keys[idx]
        except (ValueError, IndexError):
            pass
        print("  无效选择，请重新输入")


def cmd_test_hdi(hdi_path=None, emulator=None, serial=False, auto=False):
    print("")
    print("===== NP2kai 测试启动 =====")

    project_root = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    disks_dir = os.path.join(project_root, "disks")

    emu_name = _pick_emulator(emulator)
    binary = EMULATORS.get(emu_name, EMULATORS["ia32"])
    dev_bin = EMULATOR_DEV.get(emu_name, "")
    if dev_bin and os.path.exists(dev_bin):
        binary = dev_bin
    print(f"  模拟器: {emu_name} -> {binary}")

    if hdi_path:
        if os.path.isfile(hdi_path):
            selected = hdi_path
        else:
            guess = os.path.join(disks_dir, f"{hdi_path}.hdi")
            if os.path.isfile(guess):
                selected = guess
            else:
                print(f"[✗] HDI 文件不存在: {hdi_path}")
                print(f"    也未找到: {guess}")
                sys.exit(1)
    else:
        if not os.path.isdir(disks_dir):
            print(f"[✗] 未找到 disks/ 目录: {disks_dir}")
            sys.exit(1)

        hdis = sorted([f for f in os.listdir(disks_dir) if f.endswith(".hdi")])
        if not hdis:
            print("[✗] disks/ 下没有 .hdi 文件")
            print("    请先运行 make_hdi.sh 生成磁盘镜像")
            sys.exit(1)

        if len(hdis) == 1:
            selected = os.path.join(disks_dir, hdis[0])
        else:
            print("可用 HDI 镜像:")
            for i, name in enumerate(hdis, 1):
                print(f"  {i}) {name}")
            while True:
                try:
                    choice = input(f"  选择测试镜像 [1-{len(hdis)}]: ").strip()
                    idx = int(choice) - 1
                    if 0 <= idx < len(hdis):
                        selected = os.path.join(disks_dir, hdis[idx])
                        break
                except (ValueError, IndexError):
                    pass
                print("  无效选择，请重新输入")

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
            print(f"  [✓] 已复制: {src} -> {dst_name}")

    sec = {'SCSIHDD0': selected}

    serial_pty = None
    if serial:
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
    if auto:
        cmd.append("--start")
    print(f"  启动: {' '.join(cmd)}")

    if serial and serial_pty:
        master_fd, slave_fd, slave_name = serial_pty
        os.close(slave_fd)
        serial_log = os.path.join(project_root, "logs",
                                  f"serial_{os.path.splitext(os.path.basename(selected))[0]}.log")
        with open(serial_log, "wb") as slog:
            process = subprocess.Popen(cmd, stdout=None, stderr=None)
            print(f"  串口日志: {serial_log}")
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
    else:
        subprocess.run(cmd)

    print("")


def cmd_check():
    project_root = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

    print("")
    print("───── 模拟器 ─────")
    _check_file("wxnp21kai (ia32)",
        "/usr/local/bin/wxnp21kai")
    _check_file("np2kai_libretro",
        "~/.config/retroarch/cores/np2kai_libretro.so")
    _check_file("sdlnp2kai (i286)",
        "/usr/local/bin/sdlnp2kai")

    print("\n───── 工具链 ─────")
    if os.path.exists("/opt/gcc-ia16/bin/ia16-elf-gcc"):
        _run_check("ia16-elf-gcc",
            ["/opt/gcc-ia16/bin/ia16-elf-gcc", "--version"])
    else:
        _check_file("ia16-elf-gcc", "/opt/gcc-ia16/bin/ia16-elf-gcc")
    _check_file("wcl386",
        "~/open-watcom-v2/rel/binl64/wcl386")
    _check_file("ia16-elf-g++",
        "/opt/gcc-ia16/bin/ia16-elf-g++")

    print("\n───── 依赖库 ─────")
    _run_check("SDL2",
        ["pkg-config", "--modversion", "sdl2"])
    _run_check("GTK3",
        ["pkg-config", "--modversion", "gtk+-3.0"])
    _run_check("wxWidgets",
        ["wx-config", "--version"])

    print("\n───── 环境 ─────")
    _run_check("Python",
        ["python3", "--version"])
    _run_check("CMake",
        ["cmake", "--version"])
    _run_check("Git",
        ["git", "--version"])

    print("\n───── NP2kai 补丁 ─────")
    _check_np2kai_patches()

    print("")


def _install_retroarch_appimage():
    import urllib.request

    appimage_name = "RetroArch.7z"
    appimage_path = os.path.join(RETROARCH_APPIMAGE_DIR, appimage_name)

    os.makedirs(RETROARCH_APPIMAGE_DIR, exist_ok=True)

    if os.path.exists(appimage_path):
        print(f"[✓] RetroArch AppImage 已下载: {appimage_path}")
    else:
        print("[*] 下载 RetroArch AppImage...")
        try:
            urllib.request.urlretrieve(RETROARCH_APPIMAGE_URL, appimage_path)
            print(f"[✓] 下载完成: {appimage_path}")
        except Exception as e:
            print(f"[✗] 下载失败: {e}")
            sys.exit(1)

    extract_dir = os.path.join(RETROARCH_APPIMAGE_DIR,
                               f"RetroArch-{RETROARCH_LATEST}")
    os.makedirs(extract_dir, exist_ok=True)

    print("[*] 解压 RetroArch...")
    try:
        import py7zr
        with py7zr.SevenZipFile(appimage_path, mode='r') as z:
            z.extractall(path=extract_dir)
    except ImportError:
        print("[!] 需要 py7zr 库，尝试 pip install py7zr")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "py7zr"],
            check=True)
        import py7zr
        with py7zr.SevenZipFile(appimage_path, mode='r') as z:
            z.extractall(path=extract_dir)

    retro_bin = os.path.join(extract_dir, "RetroArch")
    if os.path.exists(retro_bin):
        os.chmod(retro_bin, 0o755)
        subprocess.run(["sudo", "ln", "-sf", retro_bin,
                       RETROARCH_BIN_SYMLINK], check=True)
        print(f"[✓] RetroArch {RETROARCH_LATEST} 安装完成")
    else:
        print(f"[✗] 解压后未找到 RetroArch 可执行文件")
        sys.exit(1)


def cmd_retroarch():
    print("")
    print("===== 安装 RetroArch (备用模拟器) =====")
    _install_retroarch_appimage()
