#!/usr/bin/env python3
"""
env_toolchains.py — Toolchain build/install command handlers for Naiz env setup

Split from env_build.py (B5).  Covers: pip deps, Open Watcom, DJGPP, gcc-ia16.
env_build.py re-exports these for backward compatibility.
"""
import os
import shutil
import sys
from .env_utils import (
    OW_DIR, DJGPP_DIR, DJGPP_BIN,
    GCC_IA16_DIR, GCC_IA16_REPO, GCC_IA16_PREFIX,
    MIRROR, _resolve_repo,
    run_step, _git_clone_with_retry, _pkg_install,
)


def cmd_pip_install():
    print("")
    print("───── Python 依赖安装 ─────")
    requirements = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if not os.path.exists(requirements):
        print(f"[✗] 未找到 requirements.txt: {requirements}")
        sys.exit(1)

    venv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools", "env_setup", "venv")
    venv_python = os.path.join(venv_dir, "bin", "python3")
    venv_pip = os.path.join(venv_dir, "bin", "pip")
    if not os.path.exists(venv_python):
        print("  [*] 创建虚拟环境...")
        ok = run_step("创建 Python venv",
                      [sys.executable, "-m", "venv", venv_dir])
        if not ok:
            sys.exit(1)

    pip_cmd = [venv_pip, "install", "-r", requirements]
    run_step("安装 Python 依赖", pip_cmd)


def cmd_install_watcom():
    print("")
    print("───── 安装 Open Watcom 工具链 ─────")

    _pkg_install(["git", "build-essential", "dos2unix"], "安装构建依赖")

    if os.path.exists(os.path.join(OW_DIR, "rel", "binl64", "wcl386")) or \
       os.path.exists(os.path.join(OW_DIR, "rel", "binl", "wcl386")):
        print(f"[✓] Open Watcom 已安装在 {OW_DIR}")
        return

    repo_url = os.environ.get("NAIZ_OW_REPO") or _resolve_repo("openwatcom", MIRROR)
    ok = _git_clone_with_retry(repo_url, OW_DIR, desc="Open Watcom v2 源码", max_retries=5)
    if not ok:
        print("[✗] Open Watcom 克隆失败")
        sys.exit(1)

    env = os.environ.copy()
    env["OWDOCBUILD"] = "0"
    env["OWNOWGML"] = "1"
    env["OWDISTRBUILD"] = "0"

    ok = run_step("构建 Open Watcom (跳过文档，约 20-40 分钟)",
                  ["bash", "-c", ". ./setvars.sh && ./build.sh rel"],
                  env=env, cwd=OW_DIR)
    if not ok:
        print("[✗] Open Watcom 构建失败")
        sys.exit(1)

    rel_bin = os.path.join(OW_DIR, "rel")
    wcl_path = None
    for candidate in ["binl64", "binl"]:
        p = os.path.join(rel_bin, candidate, "wcl386")
        if os.path.exists(p):
            wcl_path = p
            break
    if wcl_path:
        print("[✓] Open Watcom 安装完成")
        print(f"    wcl386: {wcl_path}")
        print("    请手动设置环境变量:")
        print(f"    export WATCOM={OW_DIR}/rel")
        print("    export PATH=$WATCOM/binl64:$PATH")
        print("    export INCLUDE=$WATCOM/h")
    else:
        print("[!] 构建完成但未找到 wcl386")
        print(f"    请检查 {rel_bin}/")


def cmd_install_djgpp():
    print("")
    print("───── 安装 DJGPP 工具链 ─────")

    _pkg_install(["git", "build-essential", "texinfo", "flex", "bison",
                  "libgmp-dev", "libmpfr-dev", "libmpc-dev"],
                 "安装构建依赖")

    if os.path.exists(DJGPP_BIN):
        print(f"[✓] DJGPP 已安装在 {DJGPP_DIR}")
        return

    repo_url = os.environ.get("NAIZ_DJGPP_REPO") or "https://github.com/andrewwutw/build-djgpp.git"
    ok = _git_clone_with_retry(repo_url, DJGPP_DIR, desc="build-djgpp 源码", max_retries=5)
    if not ok:
        print("[✗] build-djgpp 克隆失败")
        sys.exit(1)

    ok = run_step("构建 DJGPP 工具链（耗时约 30-60 分钟）",
                  ["./build-djgpp.sh", f"--prefix={DJGPP_DIR}/djgpp"],
                  cwd=DJGPP_DIR)
    if not ok:
        print("[✗] DJGPP 构建失败")
        sys.exit(1)

    gcc_path = os.path.join(DJGPP_DIR, "djgpp", "bin", "i586-pc-msdosdjgpp-gcc")
    if os.path.exists(gcc_path):
        print("[✓] DJGPP 安装完成")
        print(f"    二进制路径: {DJGPP_DIR}/djgpp/bin/")
        print(f"    请手动添加至 PATH: export PATH={DJGPP_DIR}/djgpp/bin:$PATH")
    else:
        print("[!] 构建完成但未找到 i586-pc-msdosdjgpp-gcc")
        print(f"    请检查 {DJGPP_DIR}")


def cmd_gcc_ia16():
    print("")
    print("───── 安装 gcc-ia16 工具链 ─────")

    _pkg_install(["git", "build-essential", "flex", "bison", "libgmp-dev",
                  "libmpfr-dev", "libmpc-dev", "texinfo", "ccache"],
                 "安装构建依赖")

    if os.path.exists(f"{GCC_IA16_PREFIX}/bin/ia16-elf-gcc"):
        print(f"[✓] gcc-ia16 已安装: {GCC_IA16_PREFIX}")
        return

    ok = _git_clone_with_retry(GCC_IA16_REPO, GCC_IA16_DIR, desc="gcc-ia16 源码")
    if not ok:
        sys.exit(1)

    binutils_url = "https://github.com/tkchia/binutils-ia16.git"
    binutils_dir = "/tmp/binutils-ia16"
    ok = _git_clone_with_retry(binutils_url, binutils_dir, desc="binutils-ia16 源码")
    if not ok:
        sys.exit(1)

    work_dir = "/tmp/build-gcc-ia16"
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir, exist_ok=True)

    binutils_env = os.environ.copy()
    binutils_env["CFLAGS"] = "-g -O2"
    ok = run_step("配置 binutils-ia16",
                  ["../binutils-ia16/configure",
                   "--target=ia16-elf", f"--prefix={GCC_IA16_PREFIX}",
                   "--disable-nls", "--disable-werror"],
                  env=binutils_env, cwd=work_dir)
    if not ok:
        sys.exit(1)

    ok = run_step("编译 binutils-ia16",
                  ["make", "-C", work_dir, "-j", str(os.cpu_count() or 4)])
    if not ok:
        sys.exit(1)

    ok = run_step("安装 binutils-ia16",
                  ["make", "-C", work_dir, "install"], sudo=True)
    if not ok:
        sys.exit(1)

    gcc_build_dir = "/tmp/build-gcc-ia16-gcc"
    if os.path.exists(gcc_build_dir):
        shutil.rmtree(gcc_build_dir)
    os.makedirs(gcc_build_dir, exist_ok=True)

    gcc_env = os.environ.copy()
    gcc_env["PATH"] = f"{GCC_IA16_PREFIX}/bin:" + os.environ.get("PATH", "")
    ok = run_step("配置 gcc-ia16",
                  ["../gcc-ia16/configure",
                   "--target=ia16-elf", f"--prefix={GCC_IA16_PREFIX}",
                   "--disable-nls", "--enable-languages=c",
                   "--without-headers"],
                  env=gcc_env, cwd=gcc_build_dir)
    if not ok:
        sys.exit(1)

    ok = run_step("编译 gcc-ia16 (约 15-30 分钟)",
                  ["make", "-j", str(os.cpu_count() or 4)],
                  env=gcc_env, cwd=gcc_build_dir)
    if not ok:
        sys.exit(1)

    ok = run_step("安装 gcc-ia16",
                  ["make", "-C", gcc_build_dir, "install"], sudo=True)
    if not ok:
        sys.exit(1)

    if os.path.exists(f"{GCC_IA16_PREFIX}/bin/ia16-elf-gcc"):
        print(f"[✓] gcc-ia16 安装完成: {GCC_IA16_PREFIX}")
        print("    请将以下内容加入 shell 配置:")
        print(f"    export PATH={GCC_IA16_PREFIX}/bin:$PATH")
    else:
        print("[!] 安装完成但未找到 ia16-elf-gcc")


# [DEPRECATED] Kept intentionally (see AGENTS.md "已弃用但保留的代码").
# No caller in the repo; deepin-specific gcc-ia16 install path.
def _install_gcc_ia16_deepin():
    os.chdir(GCC_IA16_DIR)

    ok = _git_clone_with_retry(
        "https://github.com/edouardlicn/gcc-ia16.git",
        os.path.join(GCC_IA16_DIR, "gcc-ia16"),
        desc="gcc-ia16 深度定制版",
    )
    if not ok:
        sys.exit(1)

    os.chdir(os.path.join(GCC_IA16_DIR, "gcc-ia16"))
    ok = run_step("配置 gcc-ia16-deepin",
                  ["./configure", "--prefix=/usr", "--enable-languages=c",
                   "--target=ia16-elf", "--disable-nls"])
    if not ok:
        sys.exit(1)

    ok = run_step("编译 gcc-ia16-deepin",
                  ["make", "-j4"])
    if not ok:
        sys.exit(1)

    ok = run_step("安装 gcc-ia16-deepin",
                  ["sudo", "make", "install"])
    if not ok:
        sys.exit(1)
