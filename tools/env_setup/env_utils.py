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

try:
    from i18n import tr
except ImportError:  # imported as `tools.env_setup` (repo root on sys.path)
    from tools.i18n import tr

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

NAIZ_CONF_DIR = os.path.expanduser("~/.config/naiz")
NAIZ_CONF_FILE = os.path.join(NAIZ_CONF_DIR, "env.conf")

# Shared by naiz and the sibling naiz-studio repository.  Keep in sync with
# tools/env_setup/ensure_venv.sh, which is the shell-side entry point.
VENV_DIR = os.path.expanduser("~/venv")
VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python3")

REPO_MAP = {
    "np2kai":   {"github": NP2KAI_REPO,           "china": NP2KAI_REPO_MIRROR},
    "gcc":      {"github": GCC_IA16_REPO,         "china": GCC_IA16_REPO_MIRROR},
    "binutils": {"github": BINUTILS_IA16_REPO,    "china": BINUTILS_IA16_REPO_MIRROR},
    "sdl3":     {"github": SDL3_REPO,             "china": SDL3_REPO_MIRROR},
    "sdl_ttf":  {"github": SDL3_TTF_REPO,         "china": SDL3_TTF_REPO_MIRROR},
    "openwatcom": {"github": OW_REPO,             "china": OW_REPO_MIRROR},
}

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
        print(tr("[*] Using NAIZ_SUDO_PASS environment variable"))
    else:
        import getpass
        try:
            pw = getpass.getpass(tr("[sudo] password: "))
        except (EOFError, KeyboardInterrupt):
            print(f"\n[✗] {tr('sudo privileges required')}")
            sys.exit(1)
    r = subprocess.run(["sudo", "-S", "-v"], input=pw + "\n", text=True,
                       capture_output=True)
    if r.returncode != 0:
        print(f"[✗] {tr('sudo authentication failed')}")
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
        f.write("# Naiz environment configuration\n")
        f.write("# Auto-managed by install_env.py\n\n")
        for k, v in cfg.items():
            f.write(f"{k}={v}\n")


def _resolve_repo(name, mirror=None, interactive=True):
    if name not in REPO_MAP:
        print(f"[!] {tr('Unknown repository:')} {name}")
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
    print(f"  {tr('Mirror source set:')} {mirror_name}")


def _mirror_init():
    cfg = _read_conf()
    if "mirror" in cfg:
        return cfg["mirror"]
    print("")
    print(f"───── {tr('Git repository source selection')} ─────")
    print(f"  1) {tr('GitHub (default, direct overseas connection)')}")
    print(f"  2) {tr('Domestic mirror (Gitee/GitCode, mainland China acceleration)')}")
    print(f"  ({tr('Can be changed later at')} {NAIZ_CONF_FILE})")
    while True:
        try:
            choice = input(f"  {tr('Please choose')} [1/2] ({tr('default')} 1): ").strip()
            if choice in ("", "1"):
                mirror = "github"
                break
            elif choice == "2":
                mirror = "china"
                break
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {tr('Cancelled')}")
            sys.exit(1)
    cfg["mirror"] = mirror
    _write_conf(cfg)
    print(f"  {tr('Saved to')} {NAIZ_CONF_FILE}")
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


def _git_clone_with_retry(url, dest, desc="source", max_retries=3, branch=None):
    clone_env = os.environ.copy()
    if os.path.exists(dest):
        bak = dest + ".bak"
        if os.path.exists(bak):
            shutil.rmtree(bak, ignore_errors=True)
        os.rename(dest, bak)
        print(f"  [!] {tr('Moved old directory to')} {bak}")
        if os.path.exists(dest):
            subprocess.run(["sudo", "rm", "-rf", dest], capture_output=True)
            if os.path.exists(dest):
                print(f"  [!] {tr('Cannot delete')} {dest}, {tr('please run manually:')} sudo rm -rf {dest}")
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
        title = f"{tr('Cloning')} {desc} ({tr('attempt')} {i}/{max_retries})"
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
            print(f"  {tr('Waiting')} {delay}s {tr('before retry...')}")
            sys.stdout.flush()
            time.sleep(delay)
    if url.startswith("git@"):
        auth_hints = {
            "git@gitee.com": tr("Gitee → please add your SSH public key on Gitee first: https://gitee.com/profile/sshkeys"),
            "git@gitcode.com": tr("GitCode → please add your SSH public key on GitCode first: https://gitcode.com/-/user_settings/keys"),
        }
        for host, hint in auth_hints.items():
            if host in url:
                print(f"[!] {hint}")
    return False


def _get_np2kai_source():
    if os.path.exists(NP2KAI_DIR):
        return NP2KAI_DIR
    url = _resolve_repo("np2kai", MIRROR)
    ok = _git_clone_with_retry(url, NP2KAI_DIR, desc=tr("NP2kai source"), branch="wx_alpha")
    if not ok:
        print(f"[✗] {tr('NP2kai clone failed, aborting install')}")
        sys.exit(1)
    return NP2KAI_DIR


def _apt_has(package):
    """Return True if the package exists in the apt cache."""
    r = subprocess.run(["apt-cache", "show", package],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return r.returncode == 0 and bool(r.stdout.strip())


def _apt_install(packages, title=None):
    if title is None:
        title = f"{tr('Installing')} {' '.join(packages)}"
    ne = os.environ.copy()
    ne["DEBIAN_FRONTEND"] = "noninteractive"
    ok = run_step(title,
                  ["apt-get", "install", "-y"] + packages,
                  sudo=True, env=ne)
    if not ok:
        r = subprocess.run(
            ["dpkg", "--audit"], capture_output=True, text=True)
        if r.returncode != 0 or "not configured" in r.stdout.lower():
            print(f"[!] {tr('Detected abnormal dpkg state, auto-fixing...')}")
            # Force-remove packages stuck in postinst that block dpkg --configure
            stuck = subprocess.run(
                ["dpkg", "--audit"], capture_output=True, text=True)
            for line in stuck.stdout.splitlines():
                if "half-installed" in line or "unpacked" in line:
                    pkg = line.split()[-1] if line.split() else None
                    if pkg:
                        print(f"  {tr('Force-removing stuck package:')} {pkg}")
                        subprocess.run(
                            ["dpkg", "--remove", "--force-remove-reinstreq",
                             "--force-all", pkg],
                            capture_output=True, text=True, env=ne)
            run_step(tr("Fix dpkg state"), ["dpkg", "--configure", "-a"], sudo=True, env=ne)
            ok = run_step(title,
                          ["apt-get", "install", "-y"] + packages,
                          sudo=True, env=ne)
    if not ok:
        print(f"[✗] {tr('Dependency installation failed:')} {' '.join(packages)}")
        print(f"    {tr('Please verify the package names exist for this distro, or install manually and retry')}")
        sys.exit(1)


def _pacman_install(packages, title=None):
    if title is None:
        title = f"{tr('Installing')} {' '.join(packages)}"
    ok = run_step(title,
                  ["pacman", "-S", "--noconfirm"] + packages,
                  sudo=True)
    if not ok:
        print(f"[✗] {tr('Dependency installation failed:')} {' '.join(packages)}")
        sys.exit(1)


def _pkg_install(packages, title=None):
    pm = _detect_pkg_manager()
    if pm == "apt":
        _apt_install(packages, title)
    elif pm == "pacman":
        _pacman_install(packages, title)
    else:
        print(f"[!] {tr('Unsupported package manager, please install manually:')} {' '.join(packages)}")


def _run_check(label, argv):
    """Probe a tool/library (argv as list, no shell) and report its version."""
    r = subprocess.run(
        argv, capture_output=True, text=True, timeout=30)
    if r.returncode == 0:
        out = (r.stdout or r.stderr).strip()
        if out:
            print(f"  {label:24} {out.splitlines()[0]}")
            return
    print(f"  {label:24} {tr('not installed')}")


def _check_file(label, path):
    """Report a fixed install path; expand ~ like a login shell would."""
    if path.startswith("~"):
        path = os.path.expanduser(path)
    if os.path.exists(path):
        print(f"  {label:24} {path}")
    else:
        print(f"  {label:24} {tr('not installed')}")


def _check_np2kai_patches():
    PATCH_CATEGORIES = {
        "01-": tr("display-required"), "02-": tr("display-required"), "03-": tr("display-required"),
        "04-": tr("input-fix"), "05-": tr("mouse"),
    }
    patch_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "np2kaipatch"))
    # Patches are baked into the installed binary by cmd_np2kai(); the
    # /tmp source checkout is only needed for a rebuild, not at runtime.
    patch_label = tr("NP2kai patches")
    if os.path.exists(EMULATORS["ia32"]):
        print(f"  {patch_label:24} {tr('emulator installed (patches baked in), source dir can be omitted')}")
        return True
    if not os.path.isdir(NP2KAI_DIR):
        print(f"  {patch_label:24} {tr('source not checked out (emulator not installed)')}")
        print(f"  {'':24} {tr('Please run first:')} start.sh np2kai")
        return False
    if not os.path.isdir(os.path.join(NP2KAI_DIR, ".git")):
        print(f"  {patch_label:24} {tr('not a Git repo (emulator not installed)')}")
        print(f"  {'':24} {tr('Please run first:')} start.sh np2kai")
        return False
    lines = []
    applied = 0
    total = 0
    for patch_file in sorted(os.listdir(patch_dir)):
        if not patch_file.endswith(".patch"):
            continue
        total += 1
        prefix = patch_file[:3]
        cat = PATCH_CATEGORIES.get(prefix, tr("other"))
        r = subprocess.run(
            ["git", "apply", "--reverse", "--check",
             os.path.join(patch_dir, patch_file)],
            cwd=NP2KAI_DIR, capture_output=True, text=True)
        ok = (r.returncode == 0)
        if ok:
            applied += 1
        lines.append((ok, f"[{cat:8}] {patch_file:40} {'✓' if ok else tr('✗ missing')}"))
    if total == 0:
        print(f"  {patch_label:24} {tr('no patch files')}")
        return False
    for _, line in lines:
        print(f"    {line}")
    if applied == total:
        print(f"  {patch_label:24} {applied}/{total} {tr('all applied ✓')}")
        return True
    print(f"  {patch_label:24} {applied}/{total} ({total-applied} {tr('missing')} ⚠)")
    return False
