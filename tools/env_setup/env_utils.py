#!/usr/bin/env python3
"""
env_utils.py — Shared utilities for Naiz environment setup
"""
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "env_install.log")

NP2KAI_DIR = "/tmp/NP2kai"
NP2KAI_REPO = "https://github.com/AZO234/NP2kai.git"
# NOTE: wx front-end lives on the wx_alpha branch; the mirror below returns
# HTTP 403 since 2026-04 and needs a replacement mirror before it can be used.
NP2KAI_REPO_MIRROR = "https://gitcode.com/edouardlicn123/NP2kai.git"

GCC_IA16_DIR = "/tmp/gcc-ia16"
GCC_IA16_REPO = "https://github.com/tkchia/gcc-ia16.git"
GCC_IA16_REPO_MIRROR = "https://gitcode.com/edouardlicn123/gcc-ia16.git"
GCC_IA16_BRANCH = "gcc-6_3_0-ia16-tkchia"
BINUTILS_IA16_DIR = "/tmp/binutils-ia16"
BINUTILS_IA16_REPO = "https://github.com/tkchia/binutils-ia16.git"
BINUTILS_IA16_REPO_MIRROR = "https://gitee.com/edouardlicn/binutils-ia16.git"
GCC_IA16_PREFIX = "/opt/gcc-ia16"

SDL3_DIR = "/tmp/SDL3"
SDL3_REPO = "https://github.com/libsdl-org/SDL.git"
# NOTE: gitee.com/libsdl-org is stale (SDL2-era tags only); the fresh
# mirror lives under the mirrors_libsdl-org org.
SDL3_REPO_MIRROR = "https://gitee.com/mirrors_libsdl-org/SDL.git"
SDL3_TAG = "release-3.4.14"
SDL3_TTF_DIR = "/tmp/SDL_ttf"
SDL3_TTF_REPO = "https://github.com/libsdl-org/SDL_ttf.git"
SDL3_TTF_REPO_MIRROR = "https://gitee.com/mirrors_libsdl-org/SDL_ttf.git"
SDL3_TTF_TAG = "release-3.2.2"

OW_DIR = os.path.expanduser("~/open-watcom-v2")
OW_BIN = os.path.join(OW_DIR, "rel")
OW_REPO = "https://github.com/open-watcom/open-watcom-v2.git"
# Domestic mirror of open-watcom-v2 (GitCode, edouardlicn123).  GitHub clone of this large repo
# is frequently reset/stalls on restricted networks; the mirror is reachable
# and fast.  Selected via `mirror=china` or NAIZ_OW_REPO.
OW_REPO_MIRROR = "https://gitcode.com/edouardlicn123/open-watcom-v2.git"
DJGPP_DIR = os.path.expanduser("~/build-djgpp")
DJGPP_BIN = os.path.join(DJGPP_DIR, "djgpp", "bin", "i586-pc-msdosdjgpp-gcc")

NAIZ_CONF_DIR = os.path.expanduser("~/.config/naiz")
NAIZ_CONF_FILE = os.path.join(NAIZ_CONF_DIR, "env.conf")

REPO_MAP = {
    "np2kai":   {"github": NP2KAI_REPO,           "china": NP2KAI_REPO_MIRROR},
    "gcc":      {"github": GCC_IA16_REPO,         "china": GCC_IA16_REPO_MIRROR},
    "binutils": {"github": BINUTILS_IA16_REPO,    "china": BINUTILS_IA16_REPO_MIRROR},
    "sdl3":     {"github": SDL3_REPO,             "china": SDL3_REPO_MIRROR},
    "sdl_ttf":  {"github": SDL3_TTF_REPO,         "china": SDL3_TTF_REPO_MIRROR},
    "openwatcom": {"github": OW_REPO,             "china": OW_REPO_MIRROR},
}

RETROARCH_LATEST = "1.22.2"
RETROARCH_APPIMAGE_URL = (
    f"https://buildbot.libretro.com/stable/{RETROARCH_LATEST}/linux/x86_64/RetroArch.7z"
)
RETROARCH_APPIMAGE_DIR = os.path.expanduser("~/Applications")
RETROARCH_BIN_SYMLINK = "/usr/local/bin/retroarch"

MIRROR = None

EMULATORS = {
    "ia32": "/usr/local/bin/wxnp21kai",
}

EMULATOR_DEV = {
    "ia32": "/tmp/NP2kai/build_wx/wxnp21kai",
}


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
    except OSError:
        return False


def _is_pikaos():
    try:
        with open("/etc/os-release") as f:
            return any(line.strip() == "ID=pika" for line in f)
    except OSError:
        return False


def _sudo_init():
    if os.geteuid() == 0:
        return
    r = subprocess.run(["sudo", "-n", "true"], capture_output=True)
    if r.returncode == 0:
        return
    pw = os.environ.get("NAIZ_SUDO_PASS")
    if pw is not None:
        print("[*] 使用 NAIZ_SUDO_PASS 环境变量")
    else:
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
    os.makedirs(NAIZ_CONF_DIR, exist_ok=True)
    with open(NAIZ_CONF_FILE, "w") as f:
        f.write("# Naiz 环境配置\n")
        f.write("# 由 install_env.py 自动管理\n\n")
        for k, v in cfg.items():
            f.write(f"{k}={v}\n")


def _resolve_repo(name, mirror=None, interactive=True):
    if name not in REPO_MAP:
        print(f"[!] 未知仓库: {name}")
        return None
    cfg = _read_conf()
    if mirror is None:
        mirror = cfg.get("mirror", "")
    if mirror in REPO_MAP[name]:
        return REPO_MAP[name][mirror]
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


def run_step(title, cmd, sudo=False, env=None, cwd=None):
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
        cwd=cwd,
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


def _git_clone_with_progress(cmd, env=None):
    """Run git clone with real-time progress display.

    Returns (success: bool, returncode: int, full_output: str).
    """
    full_cmd = list(cmd)
    proc = subprocess.Popen(
        full_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    output_lines = []
    for line in iter(proc.stdout.readline, ""):
        line = line.rstrip("\n")
        output_lines.append(line)
        if line:
            print(f"  {line}", flush=True)
    proc.wait()
    full_output = "\n".join(output_lines)
    return proc.returncode == 0, proc.returncode, full_output


def _git_clone_with_retry(url, dest, desc="源码", max_retries=3, branch=None):
    clone_env = os.environ.copy()
    if os.path.exists(dest):
        bak = dest + ".bak"
        if os.path.exists(bak):
            shutil.rmtree(bak, ignore_errors=True)
        os.rename(dest, bak)
        print(f"  [!] 将旧目录移走至 {bak}")
        if os.path.exists(dest):
            subprocess.run(["sudo", "rm", "-rf", dest], capture_output=True)
            if os.path.exists(dest):
                print(f"  [!] 无法删除 {dest}，请手动执行：sudo rm -rf {dest}")
                return False
    git_cmd = [
        "git", "clone",
        # Harden against transient TLS resets (GnuTLS -110) on large clones:
        # force HTTP/1.1, tolerate slow transfers, enlarge the post buffer.
        "-c", "http.version=HTTP/1.1",
        "-c", "http.lowSpeedLimit=1",
        "-c", "http.lowSpeedTime=30",
        "-c", "http.postBuffer=524288000",
        "--depth", "1", "--single-branch", "--progress",
    ]
    if branch:
        git_cmd += ["--branch", branch]
    git_cmd += [url, dest]
    for i in range(1, max_retries + 1):
        title = f"克隆 {desc} (尝试 {i}/{max_retries})"
        log_write(f"===== {title} =====")
        log_write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print(f"[*] {title}...")
        sys.stdout.flush()
        ok, rc, output = _git_clone_with_progress(git_cmd, env=clone_env)
        log_write(output)
        if ok and os.path.exists(dest):
            print(f"[✓] {title}")
            return True
        print(f"[✗] {title} (exit={rc})")
        if i < max_retries:
            delay = min(30, 5 * i)
            print(f"  等待 {delay} 秒后重试...")
            sys.stdout.flush()
            time.sleep(delay)
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
    ok = _git_clone_with_retry(url, NP2KAI_DIR, desc="NP2kai 源码", branch="wx_alpha")
    if not ok:
        print("[✗] NP2kai 克隆失败，终止安装")
        sys.exit(1)
    return NP2KAI_DIR


def _apt_has(package):
    """Return True if the package exists in the apt cache."""
    r = subprocess.run(["apt-cache", "show", package],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return r.returncode == 0 and bool(r.stdout.strip())


def _apt_install(packages, title=None):
    if title is None:
        title = f"安装 {' '.join(packages)}"
    ne = os.environ.copy()
    ne["DEBIAN_FRONTEND"] = "noninteractive"
    ok = run_step(title,
                  ["apt-get", "install", "-y"] + packages,
                  sudo=True, env=ne)
    if not ok:
        r = subprocess.run(
            ["dpkg", "--audit"], capture_output=True, text=True)
        if r.returncode != 0 or "not configured" in r.stdout.lower():
            print("[!] 检测到 dpkg 异常状态，正在自动修复...")
            # Force-remove packages stuck in postinst that block dpkg --configure
            stuck = subprocess.run(
                ["dpkg", "--audit"], capture_output=True, text=True)
            for line in stuck.stdout.splitlines():
                if "half-installed" in line or "unpacked" in line:
                    pkg = line.split()[-1] if line.split() else None
                    if pkg:
                        print(f"  强制移除卡住的包: {pkg}")
                        subprocess.run(
                            ["dpkg", "--remove", "--force-remove-reinstreq",
                             "--force-all", pkg],
                            capture_output=True, text=True, env=ne)
            run_step("修复 dpkg 状态", ["dpkg", "--configure", "-a"], sudo=True, env=ne)
            ok = run_step(title,
                          ["apt-get", "install", "-y"] + packages,
                          sudo=True, env=ne)
    if not ok:
        print(f"[✗] 依赖安装失败: {' '.join(packages)}")
        print("    请检查包名在当前发行版中是否存在，或手动安装后重试")
        sys.exit(1)


def _pacman_install(packages, title=None):
    if title is None:
        title = f"安装 {' '.join(packages)}"
    ok = run_step(title,
                  ["pacman", "-S", "--noconfirm"] + packages,
                  sudo=True)
    if not ok:
        print(f"[✗] 依赖安装失败: {' '.join(packages)}")
        sys.exit(1)


def _pkg_install(packages, title=None):
    pm = _detect_pkg_manager()
    if pm == "apt":
        _apt_install(packages, title)
    elif pm == "pacman":
        _pacman_install(packages, title)
    else:
        print(f"[!] 不支持的包管理器，请手动安装: {' '.join(packages)}")


def _run_check(label, argv):
    """Probe a tool/library (argv as list, no shell) and report its version."""
    r = subprocess.run(
        argv, capture_output=True, text=True, timeout=30)
    if r.returncode == 0:
        out = (r.stdout or r.stderr).strip()
        if out:
            print(f"  {label:24} {out.splitlines()[0]}")
            return
    print(f"  {label:24} 未安装")


def _check_file(label, path):
    """Report a fixed install path; expand ~ like a login shell would."""
    if path.startswith("~"):
        path = os.path.expanduser(path)
    if os.path.exists(path):
        print(f"  {label:24} {path}")
    else:
        print(f"  {label:24} 未安装")


def _check_np2kai_patches():
    PATCH_CATEGORIES = {
        "01-": "显示必需", "02-": "显示必需", "03-": "显示必需",
        "04-": "输入修正", "05-": "鼠标",
    }
    patch_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "np2kaipatch"))
    # Patches are baked into the installed binary by cmd_np2kai(); the
    # /tmp source checkout is only needed for a rebuild, not at runtime.
    if os.path.exists(EMULATORS["ia32"]):
        print(f"  {'NP2kai 补丁':24} 模拟器已安装（补丁已固化），源码目录可省略")
        return True
    if not os.path.isdir(NP2KAI_DIR):
        print(f"  {'NP2kai 补丁':24} 源码未检出（模拟器未安装）")
        print(f"  {'':24} 请先运行: start.sh np2kai")
        return False
    if not os.path.isdir(os.path.join(NP2KAI_DIR, ".git")):
        print(f"  {'NP2kai 补丁':24} 非 Git 仓库（模拟器未安装）")
        print(f"  {'':24} 请先运行: start.sh np2kai")
        return False
    lines = []
    applied = 0
    total = 0
    for patch_file in sorted(os.listdir(patch_dir)):
        if not patch_file.endswith(".patch"):
            continue
        total += 1
        prefix = patch_file[:3]
        cat = PATCH_CATEGORIES.get(prefix, "其他")
        r = subprocess.run(
            ["git", "apply", "--reverse", "--check",
             os.path.join(patch_dir, patch_file)],
            cwd=NP2KAI_DIR, capture_output=True, text=True)
        ok = (r.returncode == 0)
        if ok:
            applied += 1
        lines.append((ok, f"[{cat:8}] {patch_file:40} {'✓' if ok else '✗ 缺失'}"))
    if total == 0:
        print(f"  {'NP2kai 补丁':24} 无补丁文件")
        return False
    for _, line in lines:
        print(f"    {line}")
    if applied == total:
        print(f"  {'NP2kai 补丁':24} {applied}/{total} 全部已应用 ✓")
        return True
    print(f"  {'NP2kai 补丁':24} {applied}/{total} ({total-applied} 缺失 ⚠)")
    return False
