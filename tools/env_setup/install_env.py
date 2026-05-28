#!/usr/bin/env python3
"""
Naiz 开发环境安装工具
由 start.sh 的 env_menu 调用，CLI 子命令模式。
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
import tomllib
from datetime import datetime

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "env_install.log")

NP2KAI_DIR = "/tmp/NP2kai"
NP2KAI_REPO = "https://github.com/AZO234/NP2kai.git"
NP2KAI_REPO_MIRROR = "https://gitcode.com/edouardlicn123/NP2kai.git"

GCC_IA16_DIR = "/tmp/gcc-ia16"
GCC_IA16_REPO = "https://github.com/tkchia/gcc-ia16.git"
GCC_IA16_REPO_MIRROR = "https://gitcode.com/edouardlicn123/gcc-ia16.git"
GCC_IA16_BRANCH = "gcc-6_3_0-ia16-tkchia"
BINUTILS_IA16_DIR = "/tmp/binutils-ia16"
BINUTILS_IA16_REPO = "https://github.com/tkchia/binutils-ia16.git"
BINUTILS_IA16_REPO_MIRROR = "https://gitee.com/edouardlicn/binutils-ia16.git"
GCC_IA16_PREFIX = "/opt/gcc-ia16"

NAIZ_CONF_DIR = os.path.expanduser("~/.config/naiz")
NAIZ_CONF_FILE = os.path.join(NAIZ_CONF_DIR, "env.conf")

REPO_MAP = {
    "np2kai":   {"github": NP2KAI_REPO,           "china": NP2KAI_REPO_MIRROR},
    "gcc":      {"github": GCC_IA16_REPO,         "china": GCC_IA16_REPO_MIRROR},
    "binutils": {"github": BINUTILS_IA16_REPO,    "china": BINUTILS_IA16_REPO_MIRROR},
}

RETROARCH_LATEST = "1.22.2"
RETROARCH_APPIMAGE_URL = (
    f"https://buildbot.libretro.com/stable/{RETROARCH_LATEST}/linux/x86_64/RetroArch.7z"
)
RETROARCH_APPIMAGE_DIR = os.path.expanduser("~/Applications")
RETROARCH_BIN_SYMLINK = "/usr/local/bin/retroarch"

# 由 main() 初始化，决定 git 仓库来源
MIRROR = None


def log_write(text):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n")


def _detect_pkg_manager():
    if shutil.which("apt-get"):
        return "apt"
    if shutil.which("pacman"):
        return "pacman"
    return None


def _is_deepin():
    try:
        with open("/etc/os-release") as f:
            return "ID=deepin" in f.read()
    except:
        return False


def _is_pikaos():
    try:
        with open("/etc/os-release") as f:
            return "ID=pika" in f.read()
    except:
        return False


def _sudo_init():
    """Ensure sudo credential is cached before calling sudo-based run_step.
    Tries sudo -n (non-interactive); if that fails, prompts with getpass
    into sudo -S so subsequent sudo -n calls work without a TTY."""
    if os.geteuid() == 0:
        return
    # Check if credential is already cached
    r = subprocess.run(["sudo", "-n", "true"], capture_output=True)
    if r.returncode == 0:
        return
    # Prompt and cache via -S
    import getpass
    try:
        pw = getpass.getpass("[sudo] 密码: ")
    except (EOFError, KeyboardInterrupt):
        print("\n[✗] 需要 sudo 权限")
        sys.exit(1)
    r = subprocess.run(["sudo", "-S", "-v"], input=pw + "\n", text=True,
                       capture_output=True)
    if r.returncode != 0:
        print("[✗] sudo 验证失败")
        sys.exit(1)


def _read_conf():
    """读取 ~/.config/naiz/env.conf，返回 dict。"""
    cfg = {}
    if os.path.exists(NAIZ_CONF_FILE):
        with open(NAIZ_CONF_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    return cfg


def _write_conf(cfg):
    """写入 ~/.config/naiz/env.conf。"""
    os.makedirs(NAIZ_CONF_DIR, exist_ok=True)
    with open(NAIZ_CONF_FILE, "w") as f:
        f.write("# Naiz 环境配置\n")
        f.write("# 由 install_env.py 自动管理\n\n")
        for k, v in cfg.items():
            f.write(f"{k}={v}\n")


def _resolve_repo(name, mirror=None, interactive=True):
    """
    根据配置或参数选择仓库 URL。
    mirror=None   → 读 ~/.config/naiz/env.conf 或交互询问
    mirror="github" → GitHub
    mirror="china"  → 国内镜像
    """
    if name not in REPO_MAP:
        print(f"[!] 未知仓库: {name}")
        return None

    cfg = _read_conf()

    # 参数优先
    if mirror is None:
        mirror = cfg.get("mirror", "")

    if mirror in REPO_MAP[name]:
        return REPO_MAP[name][mirror]

    # 不存在，选默认：优先尝试 github
    if cfg.get("mirror") in REPO_MAP[name]:
        return REPO_MAP[name][cfg["mirror"]]

    return REPO_MAP[name]["github"]


def _set_mirror(mirror_name):
    global MIRROR
    MIRROR = mirror_name
    cfg = _read_conf()
    cfg["mirror"] = MIRROR
    _write_conf(cfg)
    print(f"  已设置镜像源: {mirror_name}")


def _mirror_init():
    """
    首次运行（无配置时）交互询问镜像源。
    """
    cfg = _read_conf()
    if "mirror" in cfg:
        return cfg["mirror"]

    print("")
    print("───── Git 仓库来源选择 ─────")
    print("  1) GitHub（默认，海外直连）")
    print("  2) 国内镜像（Gitee/GitCode，中国大陆加速）")
    print(f"  (可后期修改 {NAIZ_CONF_FILE})")
    while True:
        try:
            choice = input("  请选择 [1/2] (默认 1): ").strip()
            if choice in ("", "1"):
                mirror = "github"
                break
            elif choice == "2":
                mirror = "china"
                break
        except (EOFError, KeyboardInterrupt):
            print("\n  已取消")
            sys.exit(1)
    cfg["mirror"] = mirror
    _write_conf(cfg)
    print(f"  已保存到 {NAIZ_CONF_FILE}")
    return mirror


def run_step(title, cmd, sudo=False, env=None):
    log_write(f"===== {title} =====")
    log_write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print(f"[*] {title}...")
    sys.stdout.flush()

    full_cmd = (["sudo", "-n"] if sudo else []) + (cmd if isinstance(cmd, list) else ["sh", "-c", cmd])
    result = subprocess.run(
        full_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    log_write(result.stdout)
    if result.returncode == 0:
        print(f"[✓] {title}")
        return True
    else:
        print(f"[✗] {title} (exit={result.returncode})")
        for line in result.stdout.strip().split("\n")[-5:]:
            print(f"    {line}")
        return False


def _git_clone_with_retry(url, dest, desc="源码", max_retries=3):
    clone_env = os.environ.copy()
    clone_env["GIT_SSL_NO_VERIFY"] = "1"
    if os.path.exists(dest):
        shutil.rmtree(dest, ignore_errors=True)
        if os.path.exists(dest):
            # 残留 root 文件，用 sudo 清理
            subprocess.run(["sudo", "rm", "-rf", dest], capture_output=True)
            if os.path.exists(dest):
                print(f"  [!] 无法删除 {dest}，请手动执行：sudo rm -rf {dest}")
                return False
    git_cmd = ["git", "clone", "--depth", "1", url, dest]
    for i in range(1, max_retries + 1):
        ok = run_step(f"克隆 {desc} (尝试 {i}/{max_retries})", git_cmd, env=clone_env)
        if ok and os.path.exists(dest):
            return True
        if i < max_retries:
            delay = 5
            print(f"  等待 {delay} 秒后重试...")
            sys.stdout.flush()
            time.sleep(delay)
    # 检测 SSH 认证失败，提示注册/配置
    if url.startswith("git@"):
        auth_hints = {
            "git@gitee.com": "Gitee → 请先在 Gitee 添加 SSH 公钥: https://gitee.com/profile/sshkeys",
            "git@gitcode.com": "GitCode → 请先在 GitCode 添加 SSH 公钥: https://gitcode.com/-/user_settings/keys",
        }
        for host, hint in auth_hints.items():
            if host in url:
                print(f"[!] {hint}")
    return False


def _get_np2kai_source():
    if os.path.exists(NP2KAI_DIR):
        return NP2KAI_DIR
    url = _resolve_repo("np2kai", MIRROR)
    ok = _git_clone_with_retry(url, NP2KAI_DIR, desc="NP2kai 源码")
    if not ok:
        print("[✗] NP2kai 克隆失败，终止安装")
        sys.exit(1)
    return NP2KAI_DIR


def _run_check(name, check_cmd):
    r = subprocess.run(
        check_cmd, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True,
    )
    status = r.stdout.strip().split("\n")[0]
    print(f"  {name:20} {status}")


def cmd_pip_install():
    print("")
    print("───── Python 依赖安装 ─────")
    requirements = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if not os.path.exists(requirements):
        print(f"[✗] 未找到 requirements.txt: {requirements}")
        sys.exit(1)
    venv_python = os.path.dirname(sys.executable)
    pip_cmd = [os.path.join(venv_python, "pip"), "install", "-r", requirements]
    run_step("安装 Python 依赖", pip_cmd)


def cmd_build_i286():
    print("")
    print("[DEPRECATED] i286 核心已废弃，请使用 IA32 核心 (wxnp21kai, wxWidgets/GTK3)")
    print("===== 编译 i286 核心 =====")

    np2kai_dir = _get_np2kai_source()
    _patch_sdl2ttf_cmake(np2kai_dir)
    build_dir = os.path.join(np2kai_dir, "build")

    print("--- 应用上游补丁 ---")
    cmake_file = os.path.join(np2kai_dir, "CMakeLists.txt")

    subprocess.run(
        ["sed", "-i",
         's/"VERMOUTH_LIB")/"VERMOUTH_LIB" "SUPPORT_DEBUGSS")/',
         cmake_file],
        check=False)

    # Enable SASI hard disk controller support for i286 SDL/Unix build
    compiler_h = os.path.join(np2kai_dir, "sdl", "unix", "compiler.h")
    if os.path.exists(compiler_h):
        with open(compiler_h, "r") as f:
            content = f.read()
        if "SUPPORT_SASI" not in content:
            content = content.replace(
                "#define\tUSE_SDL_JOYSTICK",
                "#define\tUSE_SDL_JOYSTICK\n\n#define SUPPORT_SASI")
            with open(compiler_h, "w") as f:
                f.write(content)
            print("  已添加 SUPPORT_SASI 宏")
        else:
            print("  SUPPORT_SASI 已存在，跳过")

    _patch_np2_idetype(np2kai_dir)

    # Fix sxsi_issasi(): allow NC drives at 0x02-0x03 (SASI mode) and
    # NC at 0x01 when only HDD1 is configured.
    sxsi_c = os.path.join(np2kai_dir, "fdd", "sxsi.c")
    if os.path.exists(sxsi_c):
        with open(sxsi_c, "r") as f:
            sxsi_content = f.read()
        old_fn = ("BOOL sxsi_issasi(void) {\n\n\tREG8\tdrv;\n\tSXSIDEV\tsxsi;\n\tBOOL\tret;\n\n"
                  "\tret = FALSE;\n\tfor (drv=0x00; drv<0x04; drv++) {\n"
                  "\t\tsxsi = sxsi_getptr(drv);\n"
                  "\t\tif (sxsi) {\n"
                  "\t\t\tif ((drv < 0x02) && (sxsi->devtype == SXSIDEV_HDD)) {\n"
                  "\t\t\t\tif (sxsi->flag & SXSIFLAG_READY) {\n"
                  "\t\t\t\t\tif (sxsi->mediatype & SXSIMEDIA_INVSASI) {\n"
                  "\t\t\t\t\t\treturn(FALSE);\n"
                  "\t\t\t\t\t}\n"
                  "\t\t\t\t\tret = TRUE;\n"
                  "\t\t\t\t}\n"
                  "\t\t\t}\n"
                  "\t\t\telse {\n"
                  "\t\t\t\treturn(FALSE);\n"
                  "\t\t\t}\n"
                  "\t\t}\n"
                  "\t}\n"
                  "\treturn(ret);\n"
                  "}")
        new_fn = ("BOOL sxsi_issasi(void) {\n\n\tREG8\tdrv;\n\tSXSIDEV\tsxsi;\n\tBOOL\tret;\n\n"
                  "\tret = FALSE;\n\tfor (drv=0x00; drv<0x04; drv++) {\n"
                  "\t\tsxsi = sxsi_getptr(drv);\n"
                  "\t\tif (sxsi == NULL) continue;\n"
                  "\t\tif (drv < 0x02) {\n"
                  "\t\t\tif (sxsi->devtype == SXSIDEV_HDD) {\n"
                  "\t\t\t\tif (sxsi->flag & SXSIFLAG_READY) {\n"
                  "\t\t\t\t\tret = TRUE;\n"
                  "\t\t\t\t}\n"
                  "\t\t\t}\n"
                  "\t\t\telse if (sxsi->devtype != SXSIDEV_NC) {\n"
                  "\t\t\t\treturn(FALSE);\n"
                  "\t\t\t}\n"
                  "\t\t}\n"
                  "\t\telse {\n"
                  "\t\t\tif (sxsi->devtype != SXSIDEV_NC) {\n"
                  "\t\t\t\treturn(FALSE);\n"
                  "\t\t\t}\n"
                  "\t\t}\n"
                  "\t}\n"
                  "\treturn(ret);\n"
                  "}")
        if old_fn in sxsi_content:
            sxsi_content = sxsi_content.replace(old_fn, new_fn)
            with open(sxsi_c, "w") as f:
                f.write(sxsi_content)
            print("  已修复 sxsi_issasi() NC 检测逻辑")
        else:
            print("  sxsi_issasi() 已修复，跳过")

    # Fix gethddtype(): don't set INVSASI for non-SASI-standard geometries.
    # SASI expects 256B sectors / 33 SPT; our HDI uses 512B / 17 SPT.
    # gethddtype() was returning SXSIMEDIA_INVSASI+7 (0x0F), causing
    # sxsi_issasi() to reject the disk. We change the fallback to 7 (unknown type).
    if os.path.exists(sxsi_c):
        with open(sxsi_c, "r") as f:
            sxsi_content = f.read()
        if "return(SXSIMEDIA_INVSASI + 7);" in sxsi_content:
            sxsi_content = sxsi_content.replace(
                "return(SXSIMEDIA_INVSASI + 7);",
                "return(7);		// 非 SASI 标准几何，标记为未知类型但不设为 INVSASI")
            with open(sxsi_c, "w") as f:
                f.write(sxsi_content)
            print("  已修复 gethddtype() INVSASI 标记")
        else:
            print("  gethddtype() 已修复，跳过")
    subprocess.run(
        ["sed", "-i",
         '/target_link_libraries(NP2kai_SDL2_base.*lib_dl_libraries})/ s|})|} crypto)|',
         cmake_file],
        check=False)

    _patch_fontmng_sdlttf(np2kai_dir)

    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)

    ok = run_step("生成构建系统 (i286 core, SDL2)",
                  ["cmake", "-S", np2kai_dir, "-B", build_dir,
                   "-DBUILD_I286=ON", "-DBUILD_SDL=ON",
                   "-DUSE_SDL=2", "-DBUILD_WX=OFF"])
    if not ok:
        sys.exit(1)

    ok = run_step("编译 sdlnp2kai_sdl2",
                  ["cmake", "--build", build_dir, "--target", "sdlnp2kai_sdl2",
                   "-j", str(os.cpu_count() or 4)])
    if not ok:
        sys.exit(1)

    binary = os.path.join(build_dir, "sdlnp2kai_sdl2")
    if os.path.exists(binary):
        print(f"[✓] 编译完成：{binary}")
    else:
        print(f"[✗] 编译失败：未生成 {binary}")
        sys.exit(1)

    run_step("安装到 /usr/local/bin",
             ["cp", binary, "/usr/local/bin/sdlnp2kai_sdl2"], sudo=True)

    if os.path.exists("/usr/local/bin/sdlnp2kai_sdl2"):
        print(f"[✓] 安装验证: sdlnp2kai_sdl2")
    else:
        print("[!] 警告: 未找到已安装的 i286 核心")
        print("    请检查 /usr/local/bin/ 或运行 start.sh → 检测开发环境")


EMULATORS = {
    "ia32": "/usr/local/bin/wxnp21kai",
}

def _pick_emulator(emulator_arg):
    available = {}
    for name, path in EMULATORS.items():
        if os.path.exists(path):
            available[name] = path

    if not available:
        print("[✗] 未找到任何 NP2kai 模拟器")
        for name, path in EMULATORS.items():
            print(f"    {name}: {path}")
        print("    请先运行菜单选项编译模拟器")
        sys.exit(1)

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


def cmd_test_hdi(hdi_path=None, emulator=None):
    print("")
    print("===== NP2kai 测试启动 =====")

    project_root = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    disks_dir = os.path.join(project_root, "disks")

    # ── 1. 选择模拟器版本 ──
    emu_name = _pick_emulator(emulator)
    binary = EMULATORS[emu_name]
    print(f"  模拟器: {emu_name} → {binary}")

    # ── 2. 选择 HDI ──
    if hdi_path:
        if os.path.isfile(hdi_path):
            selected = hdi_path
        else:
            # treat as game name: look in disks/<name>.hdi
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

    # ── 3. 日志 ──
    os.makedirs(os.path.join(project_root, "logs"), exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_name = f"test_{os.path.splitext(os.path.basename(selected))[0]}_{timestamp}.log"
    log_path = os.path.join(project_root, "logs", log_name)

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"=== Naiz NP2kai Test ===\n")
        f.write(f"HDI:  {selected}\n")
        f.write(f"Time: {datetime.now().isoformat()}\n")

    # ── 4. 生成 wx 前端 config 文件 (TOML) ──
    cfg_dir = os.path.join(os.environ.get("XDG_CONFIG_HOME",
                                        os.path.join(os.environ["HOME"], ".config")),
                          "wxnp21kai")
    os.makedirs(cfg_dir, exist_ok=True)
    cfg_path = os.path.join(cfg_dir, "wxnp21kai.toml")

    # Copy BIOS/font ROMs to config dir (wx frontend auto-discovers when biospath is empty)
    bios_src = os.path.join(project_root, "core", "sdlnp2kai")
    for rom in ["bios.rom", "font.rom"]:
        src = os.path.join(bios_src, rom)
        dst = os.path.join(cfg_dir, rom)
        if os.path.exists(src) and (not os.path.exists(dst) or
                                    os.path.getsize(dst) != os.path.getsize(src)):
            shutil.copy2(src, dst)
            print(f"  [✓] 已复制: {rom}")

    try:
        with open(cfg_path, 'rb') as f:
            cfg = tomllib.load(f)
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        cfg = {}

    sec = cfg.setdefault('NP21kai', {})
    sec['SCSIHDD0'] = selected

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
    with open(cfg_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    basename = os.path.basename(selected)
    size_str = os.path.getsize(selected)
    print("")
    print("═══════════════════════════════════")
    print(f"  模拟器: {emu_name}")
    print(f"  配置:   {cfg_path}")
    print(f"  HDI:    {basename}")
    print(f"  大小:   {size_str} 字节")
    print(f"  路径:   {selected}")
    print(f"  日志:   {log_path}")
    print("═══════════════════════════════════")
    print("")
    print("  提示: 点击 NP2kai 窗口获得键盘焦点")
    print("        Alt+F4 强制退出模拟器")
    print("")

    # ── 5. 确认 ──
    try:
        confirm = input("  按 Enter 启动 NP2kai，或 Ctrl+C 取消...")
    except (EOFError, KeyboardInterrupt):
        print("\n已取消")
        sys.exit(0)

    # ── 6. 启动 ──
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n--- Launch ---\n")
        f.write(f"emulator: {emu_name}\n")
        f.write(f"binary:   {binary}\n")
        f.write(f"hdi:      {selected}\n")
        f.write(f"cfg:      {cfg_path}\n")

    print(f"启动: {binary}")
    with open(log_path, "a", encoding="utf-8") as f:
        result = subprocess.run(
            [binary],
            stdout=f,
            stderr=subprocess.STDOUT,
        )

    print(f"[✓] 模拟器已退出 (exit={result.returncode})")
    print(f"    日志: {log_path}")


def cmd_check():
    print("")
    print("───── 模拟器 ─────")
    _run_check("wxnp21kai (ia32, wxWidgets/GTK3)",
        "test -f /usr/local/bin/wxnp21kai && echo '/usr/local/bin/wxnp21kai' || echo '未安装'")
    _run_check("np2kai_libretro",
        "ls /usr/lib/libretro/np2kai_libretro.so 2>/dev/null || echo '未安装'")
    _run_check("retroarch",
        "which retroarch 2>/dev/null || echo '未安装'")
    _run_check("sdlnp21kai_sdl2 (ia32, SDL2, deprecated)",
        "test -f /usr/local/bin/sdlnp21kai_sdl2 && echo '/usr/local/bin/sdlnp21kai_sdl2' || echo '未安装'")
    _run_check("i286 core (SDL2, deprecated)",
        "test -f /tmp/NP2kai/build/sdlnp2kai_sdl2 && echo '/tmp/NP2kai/build/sdlnp2kai_sdl2' || test -f /usr/local/bin/sdlnp2kai_sdl2 && echo '/usr/local/bin/sdlnp2kai_sdl2' || echo '未安装'")
    print("")
    print("───── 开发工具 ─────")
    _run_check("gcc",
        "gcc --version 2>&1 | head -1 || echo '未安装'")
    _run_check("g++",
        "g++ --version 2>&1 | head -1 || echo '未安装'")
    _run_check("make",
        "make --version 2>&1 | head -1 || echo '未安装'")
    _run_check("ia16-elf-gcc",
        "which ia16-elf-gcc 2>/dev/null && ia16-elf-gcc --version 2>&1 | head -1 || echo '未安装'")
    _run_check("liblz4-dev",
        "dpkg -l liblz4-dev 2>/dev/null | tail -1 | awk '{print $1, $2}' || pacman -Q lz4 2>/dev/null | awk '{print $1, $2}' || echo '未安装'")
    print("")


def cmd_deps():
    pm = _detect_pkg_manager()
    if _is_deepin():
        docker_list = "/etc/apt/sources.list.d/docker.list"
        if os.path.exists(docker_list):
            run_step("禁用损坏的 docker repo (Deepin 不兼容)",
                     ["sed", "-i", "s/^deb/#deb/", docker_list], sudo=True)
    _pkg_install({
        "apt": ["build-essential", "liblz4-dev"],
        "pacman": ["base-devel", "lz4"],
    }[pm or "apt"], "安装基础开发依赖")


def cmd_gcc_ia16():
    if _is_deepin() or _is_pikaos():
        _install_gcc_ia16_deepin()
        return
    pm = _detect_pkg_manager()
    if pm == "apt":
        run_step("添加 PPA: tkchia/build-ia16",
                 ["add-apt-repository", "-y", "ppa:tkchia/build-ia16"], sudo=True)
        run_step("更新软件源", ["apt-get", "update"], sudo=True)
        _apt_install(["gcc-ia16-elf"], "安装 gcc-ia16-elf")
    elif pm == "pacman":
        print("[*] Arch Linux: gcc-ia16-elf 可通过 AUR 安装")
        print("    例如: yay -S gcc-ia16-elf 或从 https://aur.archlinux.org/packages/gcc-ia16-elf 手动构建")
    else:
        print("[!] 未检测到支持的包管理器，请手动安装 gcc-ia16-elf")


def _install_gcc_ia16_deepin():
    """On Deepin (no PPA support), build gcc-ia16 from GitHub source."""
    _apt_install([
        "flex", "bison", "texinfo",
        "libgmp-dev", "libmpc-dev", "libmpfr-dev",
    ], "安装 GCC 构建依赖")

    # ── 1. binutils ──
    if not os.path.exists(f"{GCC_IA16_PREFIX}/bin/ia16-elf-as"):
        binutils_url = _resolve_repo("binutils", MIRROR)
        ok = _git_clone_with_retry(binutils_url, BINUTILS_IA16_DIR, desc="binutils-ia16 源码")
        if not ok:
            # 主源失败，尝试另一个
            alt = "china" if MIRROR == "github" else "github"
            alt_url = REPO_MAP["binutils"][alt]
            _git_clone_with_retry(alt_url, BINUTILS_IA16_DIR, desc="binutils-ia16 备用源")
        if os.path.exists(BINUTILS_IA16_DIR):
            os.makedirs(f"{BINUTILS_IA16_DIR}/build", exist_ok=True)
            run_step("配置 binutils-ia16",
                     ["sh", "-c", f"cd {BINUTILS_IA16_DIR}/build && ../configure --target=ia16-elf --prefix={GCC_IA16_PREFIX} --disable-nls --disable-readline --disable-gdb --disable-libdecnumber --disable-sim"])
            run_step("编译 binutils-ia16",
                     ["sh", "-c", f"make -j{os.cpu_count() or 4} -C {BINUTILS_IA16_DIR}/build"])
            run_step("安装 binutils-ia16",
                     ["make", "-C", f"{BINUTILS_IA16_DIR}/build", "install"], sudo=True)

    # ── 2. gcc-ia16 ──
    if not os.path.exists(f"{GCC_IA16_PREFIX}/bin/ia16-elf-gcc"):
        gcc_url = _resolve_repo("gcc", MIRROR)
        ok = _git_clone_with_retry(gcc_url, GCC_IA16_DIR, desc="gcc-ia16 源码")
        if not ok:
            alt = "china" if MIRROR == "github" else "github"
            alt_url = REPO_MAP["gcc"][alt]
            ok = _git_clone_with_retry(alt_url, GCC_IA16_DIR, desc="gcc-ia16 备用源")
        if ok and os.path.exists(GCC_IA16_DIR):
            run_step("检出 gcc-ia16 分支",
                     ["git", "-C", GCC_IA16_DIR, "checkout", GCC_IA16_BRANCH])
            os.makedirs(f"{GCC_IA16_DIR}/build", exist_ok=True)
            run_step("配置 gcc-ia16",
                     ["sh", "-c", f"cd {GCC_IA16_DIR}/build && ../configure --target=ia16-elf --prefix={GCC_IA16_PREFIX} --enable-languages=c --disable-nls --without-headers"])
            run_step("编译 gcc-ia16 (all-gcc, 耗时较长)",
                     ["sh", "-c", f"make -j{os.cpu_count() or 4} -C {GCC_IA16_DIR}/build all-gcc"])
            run_step("安装 gcc-ia16",
                     ["make", "-C", f"{GCC_IA16_DIR}/build", "install-gcc"], sudo=True)

    # ── 3. 创建软链接到 PATH ──
    for tool in ["ia16-elf-gcc", "ia16-elf-g++", "ia16-elf-as",
                 "ia16-elf-ld", "ia16-elf-ar", "ia16-elf-ranlib"]:
        src = f"{GCC_IA16_PREFIX}/bin/{tool}"
        dst = f"/usr/local/bin/{tool}"
        if os.path.exists(src) and not os.path.exists(dst):
            run_step(f"链接 {tool} 到 /usr/local/bin",
                     ["ln", "-sf", src, dst], sudo=True)

    run_step("验证安装", ["ia16-elf-gcc", "--version"])


def _patch_sdl2ttf_cmake(np2kai_dir):
    cmake_module = os.path.join(np2kai_dir, "cmake", "FindSDL2_ttf.cmake")
    if os.path.exists(cmake_module):
        print("  FindSDL2_ttf.cmake 已存在，跳过")
        return
    os.makedirs(os.path.dirname(cmake_module), exist_ok=True)
    with open(cmake_module, "w") as f:
        f.write("""find_package(PkgConfig QUIET)
pkg_check_modules(PC_SDL2_ttf QUIET SDL2_ttf)

find_path(SDL2_ttf_INCLUDE_DIR SDL_ttf.h
    HINTS ${PC_SDL2_ttf_INCLUDE_DIRS}
    PATH_SUFFIXES SDL2
)
find_library(SDL2_ttf_LIBRARY
    NAMES SDL2_ttf
    HINTS ${PC_SDL2_ttf_LIBRARY_DIRS}
)

if(SDL2_ttf_LIBRARY AND SDL2_ttf_INCLUDE_DIR)
    set(SDL2_ttf_FOUND TRUE)
    add_library(SDL2_ttf::SDL2_ttf UNKNOWN IMPORTED)
    set_target_properties(SDL2_ttf::SDL2_ttf PROPERTIES
        IMPORTED_LOCATION "${SDL2_ttf_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${SDL2_ttf_INCLUDE_DIR}")
    message("-- Found: SDL2_ttf (via FindSDL2_ttf.cmake, "
            ${PC_SDL2_ttf_VERSION} ")")
else()
    message(FATAL_ERROR "-- Not found: SDL2_ttf "
            "(tried FindSDL2_ttf.cmake)")
endif()
""")
    print("  已创建 FindSDL2_ttf.cmake (pkg-config 回退)")


def _patch_np2_idetype(np2kai_dir):
    """Guard idetype references in sdl/np2.c for SUPPORT_SASI-only builds.

    np2.c lines 569/583 reference np2cfg.idetype[] inside a
    #if defined(SUPPORT_IDEIO) || defined(SUPPORT_SASI) block, but
    the struct field only exists when SUPPORT_IDEIO is defined (pccore.h:219).
    When SASI is enabled without IDE, HDD check always matches, CDROM never.
    """
    np2_file = os.path.join(np2kai_dir, "sdl", "np2.c")
    if not os.path.exists(np2_file):
        return
    with open(np2_file, "r") as f:
        content = f.read()

    hdd_old = '\t\t\t\t\tif(np2cfg.idetype[j] == SXSIDEV_HDD) {\n'
    hdd_new = ('\t\t\t\t\t#if defined(SUPPORT_IDEIO)\n'
               '\t\t\t\t\tif(np2cfg.idetype[j] == SXSIDEV_HDD) {\n'
               '\t\t\t\t\t#else\n'
               '\t\t\t\t\tif(1) {\n'
               '\t\t\t\t\t#endif\n')
    cdrom_old = '\t\t\t\t\t\tif(np2cfg.idetype[j] == SXSIDEV_CDROM) {\n'
    cdrom_new = ('\t\t\t\t\t\t#if defined(SUPPORT_IDEIO)\n'
                 '\t\t\t\t\t\tif(np2cfg.idetype[j] == SXSIDEV_CDROM) {\n'
                 '\t\t\t\t\t\t#else\n'
                 '\t\t\t\t\t\tif(0) {\n'
                 '\t\t\t\t\t\t#endif\n')

    dirty = False
    if hdd_old in content:
        content = content.replace(hdd_old, hdd_new)
        dirty = True
    if cdrom_old in content:
        content = content.replace(cdrom_old, cdrom_new)
        dirty = True

    if dirty:
        with open(np2_file, "w") as f:
            f.write(content)
        print("  已修复 np2.c idetype 编译条件")
    else:
        print("  np2.c idetype 已修复，跳过")


def _patch_fontmng_sdlttf(np2kai_dir):
    fontmng_file = os.path.join(np2kai_dir, "sdl", "fontmng.c")
    if not os.path.exists(fontmng_file):
        print(f"[✗] 未找到 {fontmng_file}")
        return
    with open(fontmng_file, "r") as f:
        content = f.read()
    if "SDL_ttf.h" in content:
        print("  SDL_ttf.h 包含已存在，跳过")
        return
    patch_line = '#if defined(SUPPORT_SDL_TTF)\n#include <SDL2/SDL_ttf.h>\n#endif\n'
    content = content.replace(
        "#include <fontmng.h>",
        "#include <fontmng.h>\n\n" + patch_line, 1)
    with open(fontmng_file, "w") as f:
        f.write(content)
    print("  已添加 SDL_ttf.h 包含")


def _np2kai_deps(pkg_manager="apt"):
    deps = {
        "apt": [
            "git", "cmake", "ninja-build", "build-essential",
            "libwxgtk3.2-dev", "libsdl3-dev", "libsdl3-ttf-dev",
            "libgl1-mesa-dev", "libssl-dev",
            "libusb-1.0-0-dev", "libcdio-dev",
        ],
        "pacman": [
            "git", "cmake", "ninja", "base-devel",
            "wxgtk3", "sdl3", "sdl3_ttf",
            "libusb", "libcdio",
        ],
    }
    return deps.get(pkg_manager, deps["apt"])


def _np2kai_x_deps(pkg_manager="apt"):
    """X/GTK2 可选依赖，仅构建 X port 时需要"""
    deps = {
        "apt": [
            "libx11-dev", "libglib2.0-dev", "libgtk2.0-dev",
            "libfreetype-dev", "libfontconfig1-dev",
        ],
        "pacman": [
            "libx11", "glib2", "gtk2",
            "freetype2", "fontconfig",
        ],
    }
    return deps.get(pkg_manager, deps["apt"])


def _apt_install(packages, title=None):
    if not packages:
        return True
    if title is None:
        title = f"安装 {', '.join(packages[:3])}{'...' if len(packages)>3 else ''}"
    run_step("修复 apt 依赖关系", ["apt-get", "--fix-broken", "install", "-y"], sudo=True)
    return run_step(title,
                    ["apt-get", "install", "-y", "--no-install-recommends"] + packages,
                    sudo=True)


def _pacman_install(packages, title=None):
    if not packages:
        return True
    if title is None:
        title = f"安装 {', '.join(packages[:3])}{'...' if len(packages)>3 else ''}"
    run_step("同步 pacman 数据库", ["pacman", "-Sy"], sudo=True)
    return run_step(title,
                    ["pacman", "-S", "--noconfirm", "--needed"] + packages,
                    sudo=True)


def _pkg_install(packages, title=None):
    pm = _detect_pkg_manager()
    if pm == "apt":
        return _apt_install(packages, title)
    elif pm == "pacman":
        return _pacman_install(packages, title)
    else:
        print(f"[!] 未检测到支持的包管理器 (apt/pacman)，请手动安装: {', '.join(packages)}")
        return False


def cmd_np2kai():
    pm = _detect_pkg_manager()
    if not pm:
        print("[!] 未检测到支持的包管理器 (apt/pacman)")
        sys.exit(1)

    _pkg_install(_np2kai_deps(pm), "安装 NP2kai 编译依赖")

    np2kai_dir = _get_np2kai_source()
    build_dir = os.path.join(np2kai_dir, "build")

    print("--- 应用上游补丁 ---")
    cmake_file = os.path.join(np2kai_dir, "CMakeLists.txt")
    subprocess.run(
        ["sed", "-i",
         's/"VERMOUTH_LIB")/"VERMOUTH_LIB" "SUPPORT_DEBUGSS")/',
         cmake_file],
        check=False)

    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)

    ok = run_step("生成构建系统 (wxWidgets + SDL3, GPU)",
                  ["cmake", "-S", np2kai_dir, "-B", build_dir,
                   "-DBUILD_WX=ON", "-DBUILD_SDL=OFF",
                   "-DUSE_SDL=3", "-DBUILD_X=OFF"])
    if not ok:
        sys.exit(1)

    ok = run_step("编译 NP2kai (wxWidgets port)",
                  ["cmake", "--build", build_dir, "-j", str(os.cpu_count() or 4)])
    if not ok:
        sys.exit(1)

    # cmake --install requires sudo (no TTY in subprocess), so this is best-effort
    run_step("安装到 /usr/local/bin",
             ["cmake", "--install", build_dir], sudo=True)

    built = [n for n in ["wxnp21kai"]
             if os.path.exists(os.path.join(build_dir, n))]
    installed = [n for n in ["/usr/local/bin/wxnp21kai"]
                 if os.path.exists(n)]
    if built:
        print(f"[✓] 编译完成: {', '.join(built)}")
    if installed:
        print(f"[✓] 已安装: {', '.join(installed)}")
    elif built:
        print("[!] 编译完成但未安装到系统 (缺少 sudo 交互权限)")
        print("    如需安装，请手动执行:")
        for b in built:
            print(f"    sudo cp {os.path.join(build_dir, b)} /usr/local/bin/")


def cmd_np2kai_libretro():
    pm = _detect_pkg_manager()
    if pm:
        _pkg_install(_np2kai_deps(pm), "安装 libretro 编译依赖")

    np2kai_dir = _get_np2kai_source()

    ver = "0.86.0.22"
    henv = os.environ.copy()
    henv["NP2KAI_VERSION"] = ver
    henv["NP2KAI_HASH"] = "libretro"

    run_step("编译 NP2kai libretro 核心",
             ["make", "-C", os.path.join(np2kai_dir, "sdl"),
              "-j", str(os.cpu_count() or 4)],
             env=henv)

    so_path = os.path.join(np2kai_dir, "sdl", "np2kai_libretro.so")
    if not os.path.exists(so_path):
        print("[✗] libretro 核心编译失败，未生成 np2kai_libretro.so")
        sys.exit(1)

    cores_dir = "/usr/lib/libretro"
    run_step(f"创建 {cores_dir}", ["mkdir", "-p", cores_dir], sudo=True)
    run_step("安装 libretro 核心到系统",
             ["cp", so_path, os.path.join(cores_dir, "np2kai_libretro.so")],
             sudo=True)
    print(f"[✓] libretro 核心已安装: {cores_dir}/np2kai_libretro.so")


def _install_retroarch_appimage():
    """Fallback: download RetroArch AppImage for distros without retroarch package."""
    if os.uname().machine != "x86_64":
        print("[!] AppImage 仅支持 x86_64 架构，请手动安装 RetroArch")
        return False

    _apt_install(["wget", "p7zip"], "安装下载工具和 p7zip")

    os.makedirs(RETROARCH_APPIMAGE_DIR, exist_ok=True)

    download_path = "/tmp/RetroArch.7z"
    ok = run_step("下载 RetroArch AppImage",
                  ["sh", "-c", f"wget -O '{download_path}' '{RETROARCH_APPIMAGE_URL}' "
                              f"|| curl -fsSL '{RETROARCH_APPIMAGE_URL}' -o '{download_path}'"])
    if not ok or not os.path.exists(download_path):
        print("[!] 下载失败，请手动下载并解压:")
        print(f"    {RETROARCH_APPIMAGE_URL}")
        print(f"    解压到: {RETROARCH_APPIMAGE_DIR}/")
        return False

    ok = run_step("解压 RetroArch AppImage",
                  ["7z", "x", download_path, f"-o{RETROARCH_APPIMAGE_DIR}/", "-y"])
    os.unlink(download_path)
    if not ok:
        return False

    appimage = None
    for f in os.listdir(RETROARCH_APPIMAGE_DIR):
        if f.endswith(".AppImage") and "RetroArch" in f:
            appimage = os.path.join(RETROARCH_APPIMAGE_DIR, f)
            break

    if not appimage:
        print("[!] 未在解压目录中找到 RetroArch AppImage 文件")
        return False

    os.chmod(appimage, 0o755)

    ok = run_step("创建 retroarch 命令",
                  ["ln", "-sf", appimage, RETROARCH_BIN_SYMLINK],
                  sudo=True)
    if not ok:
        return False

    print(f"[✓] RetroArch AppImage: {appimage}")
    print("[*] RetroArch 启动命令: retroarch")
    return True


def cmd_retroarch():
    pkg_ok = _pkg_install({
        "apt": ["retroarch", "retroarch-assets"],
        "pacman": ["retroarch"],
    }[_detect_pkg_manager() or "apt"], "安装 RetroArch")

    if not pkg_ok and _detect_pkg_manager() == "apt":
        print("[*] apt 中未找到 RetroArch 包，尝试下载 AppImage...")
        _install_retroarch_appimage()

    retroarch_cfg = os.path.expanduser("~/.config/retroarch/retroarch.cfg")
    cores_dir = "/usr/lib/libretro"
    if os.path.exists(retroarch_cfg):
        print(f"[*] RetroArch 配置文件已存在: {retroarch_cfg}")
    else:
        os.makedirs(os.path.dirname(retroarch_cfg), exist_ok=True)
        with open(retroarch_cfg, "w") as f:
            f.write(f'libretro_directory = "{cores_dir}"\n')
            f.write('libretro_info_path = "/usr/share/libretro/info"\n')
        print(f"[✓] 已创建默认 RetroArch 配置文件")

    has_core = os.path.exists(f"{cores_dir}/np2kai_libretro.so")
    print(f"[*] NP2kai libretro 核心: {'已安装' if has_core else '未安装 (请先运行: np2kai-libretro)'}")
    print("[*] RetroArch 启动命令: retroarch")
    print("[*] 在 RetroArch 中: Load Core → 选择 np2kai_libretro")
    print("[*] PC-98 BIOS 文件请放入 ~/.config/retroarch/system/np2kai/")


def cmd_system_tools():
    cmd_deps()
    cmd_gcc_ia16()


def cmd_backup_emu():
    cmd_np2kai_libretro()
    cmd_retroarch()


def cmd_interactive():
    """交互式安装菜单（原 start.sh env_menu 内容）"""
    _sudo_init()
    while True:
        print("\n===== 开发环境 =====")
        print("1. Python 依赖安装")
        print("2. 系统依赖与交叉编译器 (deps + gcc-ia16)")
        print("3. NP2kai 模拟器 (wxWidgets/GTK3) [主模拟器]")
        print("4. 备用模拟器 (RetroArch + libretro 核心) [备用]")
        print("5. 编译 i286 核心 [DEPRECATED]")
        print("6. 环境检测")
        print("7. 镜像源设置")
        print("0. 退出")
        print("====================")
        choice = input("请选择 [0-7]: ").strip()

        if choice == "1":
            cmd_pip_install()
            input("按 Enter 键继续...")
        elif choice == "2":
            cmd_system_tools()
            input("按 Enter 键继续...")
        elif choice == "3":
            cmd_np2kai()
            input("按 Enter 键继续...")
        elif choice == "4":
            cmd_backup_emu()
            input("按 Enter 键继续...")
        elif choice == "5":
            cmd_build_i286()
            input("按 Enter 键继续...")
        elif choice == "6":
            cmd_check()
            input("按 Enter 键继续...")
        elif choice == "7":
            print("\n───── Git 仓库来源 ─────")
            print("  1) GitHub（海外直连）")
            print("  2) 国内镜像（Gitee/GitCode，中国大陆加速）")
            m = input("请选择 [1/2]: ").strip()
            if m == "1":
                _set_mirror("github")
            elif m == "2":
                _set_mirror("china")
            input("按 Enter 键继续...")
        elif choice == "0":
            break
        else:
            print("无效选项")


def main():
    VALID_COMMANDS = {"check", "deps", "gcc-ia16", "np2kai", "np2kai-libretro",
                      "retroarch", "system-tools", "backup-emu", "pip-install",
                      "build-i286", "test-hdi"}
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
        choices=list(EMULATORS.keys()),
        help="指定模拟器版本: ia32 (默认, wxnp21kai) (仅 test-hdi)",
    )
    parser.add_argument(
        "--mirror",
        default=None,
        choices=["github", "china"],
        help="Git 仓库来源: github (默认) 或 china (国内镜像)",
    )
    args = parser.parse_args()

    # 初始化镜像源
    global MIRROR
    if args.mirror:
        _set_mirror(args.mirror)
    else:
        MIRROR = _mirror_init()

    # 无参 → 交互模式
    if args.command is None:
        cmd_interactive()
        return

    # 验证子命令
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

    # Pre-cache sudo credential for commands that need it
    needs_sudo = {"deps", "gcc-ia16", "np2kai", "np2kai-libretro",
                  "retroarch", "system-tools", "backup-emu", "build-i286"}
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
    }
    if args.command == "test-hdi":
        cmd_test_hdi(hdi_path=args.hdi, emulator=args.emulator)
    else:
        commands[args.command]()


if __name__ == "__main__":
    main()
