#!/usr/bin/env python3
"""
env_toolchains.py — Toolchain build/install command handlers for Naiz env setup

Split from env_build.py (B5).  Covers: pip deps, Open Watcom, DJGPP, gcc-ia16.
env_build.py re-exports these for backward compatibility.
"""
import os
import shutil
import sys
try:
    from i18n import tr
except ImportError:  # imported as `tools.env_setup` (repo root on sys.path)
    from tools.i18n import tr
from .env_utils import (
    OW_DIR,
    GCC_IA16_DIR, GCC_IA16_REPO, GCC_IA16_PREFIX,
    MIRROR, _resolve_repo, VENV_DIR, VENV_PYTHON,
    run_step, _git_clone_with_retry, _pkg_install,
)


def cmd_pip_install():
    print("")
    print(f"───── {tr('Python dependency installation')} ─────")
    requirements = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if not os.path.exists(requirements):
        print(f"[✗] {tr('requirements.txt not found:')} {requirements}")
        sys.exit(1)

    venv_dir = VENV_DIR
    venv_python = VENV_PYTHON
    venv_pip = os.path.join(venv_dir, "bin", "pip")
    if not os.path.exists(venv_python):
        print(f"  [*] {tr('Creating virtual environment...')}")
        ok = run_step(tr("Create Python venv"),
                      [sys.executable, "-m", "venv", venv_dir])
        if not ok:
            sys.exit(1)

    pip_cmd = [venv_pip, "install", "-r", requirements]
    run_step(tr("Install Python dependencies"), pip_cmd)


def cmd_install_watcom():
    print("")
    print(f"───── {tr('Installing Open Watcom toolchain')} ─────")

    _pkg_install(["git", "build-essential", "dos2unix"], tr("Installing build dependencies"))

    if os.path.exists(os.path.join(OW_DIR, "rel", "binl64", "wcl386")) or \
       os.path.exists(os.path.join(OW_DIR, "rel", "binl", "wcl386")):
        print(f"[✓] {tr('Open Watcom already installed at')} {OW_DIR}")
        return

    repo_url = os.environ.get("NAIZ_OW_REPO") or _resolve_repo("openwatcom", MIRROR)
    ok = _git_clone_with_retry(repo_url, OW_DIR, desc=tr("Open Watcom v2 source"), max_retries=5)
    if not ok:
        print(f"[✗] {tr('Open Watcom clone failed')}")
        sys.exit(1)

    env = os.environ.copy()
    env["OWDOCBUILD"] = "0"
    env["OWNOWGML"] = "1"
    env["OWDISTRBUILD"] = "0"

    ok = run_step(tr("Build Open Watcom (skip docs, ~20-40 min)"),
                  ["bash", "-c", ". ./setvars.sh && ./build.sh rel"],
                  env=env, cwd=OW_DIR)
    if not ok:
        print(f"[✗] {tr('Open Watcom build failed')}")
        sys.exit(1)

    rel_bin = os.path.join(OW_DIR, "rel")
    wcl_path = None
    for candidate in ["binl64", "binl"]:
        p = os.path.join(rel_bin, candidate, "wcl386")
        if os.path.exists(p):
            wcl_path = p
            break
    if wcl_path:
        print(f"[✓] {tr('Open Watcom installation complete')}")
        print(f"    wcl386: {wcl_path}")
        print(f"    {tr('Please set the environment variables manually:')}")
        print(f"    export WATCOM={OW_DIR}/rel")
        print("    export PATH=$WATCOM/binl64:$PATH")
        print("    export INCLUDE=$WATCOM/h")
    else:
        print(f"[!] {tr('Build finished but wcl386 not found')}")
        print(f"    {tr('Please check')} {rel_bin}/")


def cmd_gcc_ia16():
    print("")
    print(f"───── {tr('Installing gcc-ia16 toolchain')} ─────")

    _pkg_install(["git", "build-essential", "flex", "bison", "libgmp-dev",
                  "libmpfr-dev", "libmpc-dev", "texinfo", "ccache"],
                 tr("Installing build dependencies"))

    if os.path.exists(f"{GCC_IA16_PREFIX}/bin/ia16-elf-gcc"):
        print(f"[✓] {tr('gcc-ia16 already installed:')} {GCC_IA16_PREFIX}")
        return

    ok = _git_clone_with_retry(GCC_IA16_REPO, GCC_IA16_DIR, desc=tr("gcc-ia16 source"))
    if not ok:
        sys.exit(1)

    binutils_url = "https://github.com/tkchia/binutils-ia16.git"
    binutils_dir = "/tmp/binutils-ia16"
    ok = _git_clone_with_retry(binutils_url, binutils_dir, desc=tr("binutils-ia16 source"))
    if not ok:
        sys.exit(1)

    work_dir = "/tmp/build-gcc-ia16"
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir, exist_ok=True)

    binutils_env = os.environ.copy()
    binutils_env["CFLAGS"] = "-g -O2"
    ok = run_step(tr("Configure binutils-ia16"),
                  ["../binutils-ia16/configure",
                   "--target=ia16-elf", f"--prefix={GCC_IA16_PREFIX}",
                   "--disable-nls", "--disable-werror"],
                  env=binutils_env, cwd=work_dir)
    if not ok:
        sys.exit(1)

    ok = run_step(tr("Compile binutils-ia16"),
                  ["make", "-C", work_dir, "-j", str(os.cpu_count() or 4)])
    if not ok:
        sys.exit(1)

    ok = run_step(tr("Install binutils-ia16"),
                  ["make", "-C", work_dir, "install"], sudo=True)
    if not ok:
        sys.exit(1)

    gcc_build_dir = "/tmp/build-gcc-ia16-gcc"
    if os.path.exists(gcc_build_dir):
        shutil.rmtree(gcc_build_dir)
    os.makedirs(gcc_build_dir, exist_ok=True)

    gcc_env = os.environ.copy()
    gcc_env["PATH"] = f"{GCC_IA16_PREFIX}/bin:" + os.environ.get("PATH", "")
    ok = run_step(tr("Configure gcc-ia16"),
                  ["../gcc-ia16/configure",
                   "--target=ia16-elf", f"--prefix={GCC_IA16_PREFIX}",
                   "--disable-nls", "--enable-languages=c",
                   "--without-headers"],
                  env=gcc_env, cwd=gcc_build_dir)
    if not ok:
        sys.exit(1)

    ok = run_step(tr("Compile gcc-ia16 (~15-30 min)"),
                  ["make", "-j", str(os.cpu_count() or 4)],
                  env=gcc_env, cwd=gcc_build_dir)
    if not ok:
        sys.exit(1)

    ok = run_step(tr("Install gcc-ia16"),
                  ["make", "-C", gcc_build_dir, "install"], sudo=True)
    if not ok:
        sys.exit(1)

    if os.path.exists(f"{GCC_IA16_PREFIX}/bin/ia16-elf-gcc"):
        print(f"[✓] {tr('gcc-ia16 installation complete:')} {GCC_IA16_PREFIX}")
        print(f"    {tr('Please add the following to your shell config:')}")
        print(f"    export PATH={GCC_IA16_PREFIX}/bin:$PATH")
    else:
        print(f"[!] {tr('Installation finished but ia16-elf-gcc not found')}")


# [DEPRECATED] Kept intentionally (see AGENTS.md "已弃用但保留的代码").
# No caller in the repo; deepin-specific gcc-ia16 install path.
def _install_gcc_ia16_deepin():
    os.chdir(GCC_IA16_DIR)

    ok = _git_clone_with_retry(
        "https://github.com/edouardlicn/gcc-ia16.git",
        os.path.join(GCC_IA16_DIR, "gcc-ia16"),
        desc=tr("gcc-ia16 deepin custom build"),
    )
    if not ok:
        sys.exit(1)

    os.chdir(os.path.join(GCC_IA16_DIR, "gcc-ia16"))
    ok = run_step(tr("Configure gcc-ia16-deepin"),
                  ["./configure", "--prefix=/usr", "--enable-languages=c",
                   "--target=ia16-elf", "--disable-nls"])
    if not ok:
        sys.exit(1)

    ok = run_step(tr("Compile gcc-ia16-deepin"),
                  ["make", "-j4"])
    if not ok:
        sys.exit(1)

    ok = run_step(tr("Install gcc-ia16-deepin"),
                  ["sudo", "make", "install"])
    if not ok:
        sys.exit(1)
