#!/usr/bin/env python3
"""
env_np2kai.py — NP2kai build/install command handlers for Naiz env setup

Split from env_build.py (B5).  Covers: NP2kai IA-32 core (wxnp21kai),
libretro core, system deps, and all NP2kai source patchers.
env_build.py re-exports these for backward compatibility.
"""
import os
import shutil
import subprocess
import sys
from .env_utils import (
    MIRROR, REPO_MAP,
    SDL3_DIR, SDL3_TAG, SDL3_TTF_DIR, SDL3_TTF_TAG,
    run_step, _apt_has, _git_clone_with_retry, _get_np2kai_source,
    _resolve_repo, _pkg_install, _check_np2kai_patches,
)


# [DEPRECATED] Kept intentionally (see AGENTS.md "已弃用但保留的代码").
# i286 core only emulates 16-bit protected mode — cannot run the 32-bit
# DOS/4GW engine.  No start.sh entry point.  Not reached by normal flows.
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
         '/target_link_libraries(NP2kai_SDL2_base.*lib_dl_libraries})/ s|}|) crypto}|',
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
        print("[✓] 安装验证: sdlnp2kai_sdl2")
    else:
        print("[!] 警告: 未找到已安装的 i286 核心")
        print("    请检查 /usr/local/bin/ 或运行 start.sh → 检测开发环境")


def _apply_common_patches(np2kai_dir):
    """Apply tools/np2kaipatch/*.patch to the source tree before building.

    Patches are ordered by filename prefix (01-..05-..).  A patch already
    applied (checked via `git apply --reverse --check`) is skipped, so the
    step is idempotent on a reused checkout such as /tmp/NP2kai.
    """
    patch_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "np2kaipatch"))
    if not os.path.isdir(patch_dir):
        print("[✗] np2kaipatch 目录不存在")
        sys.exit(1)
    found = 0
    for patch_file in sorted(os.listdir(patch_dir)):
        if not patch_file.endswith(".patch"):
            continue
        found += 1
        full = os.path.join(patch_dir, patch_file)
        r = subprocess.run(["git", "apply", "--reverse", "--check", "--ignore-whitespace", full],
                           cwd=np2kai_dir, capture_output=True, text=True)
        if r.returncode == 0:
            print(f"  [✓] {patch_file} 已应用，跳过")
            continue
        if not run_step(f"应用补丁 {patch_file}", ["git", "apply", "--ignore-whitespace", full], cwd=np2kai_dir):
            print(f"[✗] 补丁 {patch_file} 应用失败（上游可能已更新）")
            print("    若基于旧的 /tmp/NP2kai，请删除后重跑 start.sh np2kai 重新检出")
            sys.exit(1)
    if found == 0:
        print("[✗] np2kaipatch 目录下无 .patch 文件")
        sys.exit(1)
    print("[✓] NP2kai 通用补丁应用完成")


def cmd_np2kai():
    print("")
    print("===== 编译 NP2kai (IA-32 核心, wxWidgets/GTK3) =====")
    print("    (设置 NAIZ_NP2KAI_REBUILD=1 可强制重编译)")

    if os.path.exists("/usr/local/bin/wxnp21kai") and not os.environ.get("NAIZ_NP2KAI_REBUILD"):
        print(f"[✓] NP2kai 已安装: /usr/local/bin/wxnp21kai")
        print("    如需重编译，请运行: NAIZ_NP2KAI_REBUILD=1 start.sh np2kai")

        print("[*] 检查补丁状态:")
        if not _check_np2kai_patches():
            print("  [!] 请卸载后重装")
        return

    np2kai_dir = _get_np2kai_source()
    _apply_common_patches(np2kai_dir)
    _np2kai_deps()
    _build_sdl3()

    build_dir = os.path.join(np2kai_dir, "build_wx")
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)

    ok = run_step("生成构建系统 (IA32 core, GTK3, wxWidgets)",
                  ["cmake", "-S", np2kai_dir, "-B", build_dir,
                   "-DBUILD_I286=OFF", "-DBUILD_WX=ON",
                   # USE_SDL=3 runs find_package(SDL3/SDL3_ttf), satisfied
                   # either by distro dev packages (newer releases) or by
                   # the source build in _build_sdl3().
                   "-DUSE_SDL=3",
                   "-DCMAKE_BUILD_TYPE=Release"])
    if not ok:
        sys.exit(1)

    ok = run_step("编译 NP2kai wxnp21kai",
                  ["cmake", "--build", build_dir, "--target", "wxnp21kai",
                   "-j", str(os.cpu_count() or 4)])
    if not ok:
        sys.exit(1)

    binary = os.path.join(build_dir, "wxnp21kai")
    if os.path.exists(binary):
        print(f"[✓] 编译完成：{binary}")
    else:
        print(f"[✗] 编译失败：未生成 {binary}")
        sys.exit(1)

    run_step("安装到 /usr/local/bin",
             ["cp", binary, "/usr/local/bin/wxnp21kai"], sudo=True)

    if os.path.exists("/usr/local/bin/wxnp21kai"):
        print("[✓] 安装验证: wxnp21kai")
    else:
        print("[!] 警告: 未找到已安装的 wxnp21kai")
        print("    请检查 /usr/local/bin/")
    print("[✓] NP2kai 安装完成（含补丁 P1-P6）")


def cmd_np2kai_libretro():
    print("")
    print("===== 编译 NP2kai libretro 核心 =====")

    np2kai_dir = _get_np2kai_source()

    build_dir = os.path.join(np2kai_dir, "build_libretro")
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)

    ok = run_step("生成构建系统 (libretro)",
                  ["cmake", "-S", np2kai_dir, "-B", build_dir,
                   "-DBUILD_LIBRETRO=ON", "-DBUILD_WX=OFF",
                   "-DBUILD_SDL=OFF", "-DBUILD_I286=OFF",
                   "-DCMAKE_BUILD_TYPE=Release"])
    if not ok:
        sys.exit(1)

    ok = run_step("编译 libretro 核心",
                  ["cmake", "--build", build_dir, "-j",
                   str(os.cpu_count() or 4)])
    if not ok:
        sys.exit(1)

    core_path = os.path.join(build_dir, "np2kai_libretro.so")
    if os.path.exists(core_path):
        print(f"[✓] libretro 核心: {core_path}")
    else:
        print(f"[✗] 编译失败：未生成 np2kai_libretro.so")
        sys.exit(1)

    retro_dir = os.path.expanduser("~/.config/retroarch/cores")
    os.makedirs(retro_dir, exist_ok=True)
    shutil.copy2(core_path, os.path.join(retro_dir, "np2kai_libretro.so"))
    print("[✓] 已复制到 RetroArch cores 目录")


def cmd_deps():
    print("")
    print("===== 系统依赖安装 =====")
    np2kai_dir = _get_np2kai_source()
    _np2kai_deps()


def _patch_sdl2ttf_cmake(np2kai_dir):
    cmake_file = os.path.join(np2kai_dir, "CMakeLists.txt")
    if not os.path.exists(cmake_file):
        return
    with open(cmake_file, "r", encoding="utf-8") as f:
        content = f.read()
    old = 'find_package(Freetype REQUIRED)'
    new = (
        '# find_package(Freetype REQUIRED)\n'
        'set(FREETYPE_LIBRARY /usr/lib/x86_64-linux-gnu/libfreetype.so)\n'
        'set(FREETYPE_INCLUDE_DIRS /usr/include/freetype2)\n'
    )
    if old in content:
        content = content.replace(old, new, 1)
        with open(cmake_file, "w", encoding="utf-8") as f:
            f.write(content)
        print("  已打补丁: SDL2_ttf CMake freetype 路径")


def _patch_np2_idetype(np2kai_dir):
    path = os.path.join(np2kai_dir, "sdl", "unix", "compiler.h")
    if not os.path.exists(path):
        return
    with open(path, "r") as f:
        content = f.read()
    if "SUPPORT_IDE" not in content:
        content = content.replace(
            "#define\tUSE_SDL_JOYSTICK",
            "#define\tUSE_SDL_JOYSTICK\n\n#define SUPPORT_IDE\t\t1")
        with open(path, "w") as f:
            f.write(content)
        print("  已添加 SUPPORT_IDE 宏")
    else:
        print("  SUPPORT_IDE 已存在，跳过")

    if "SUPPORT_SASI" not in content:
        content = content.replace(
            "#define\tUSE_SDL_JOYSTICK",
            "#define\tUSE_SDL_JOYSTICK\n\n#define SUPPORT_SASI")
        with open(path, "w") as f:
            f.write(content)
        print("  已添加 SUPPORT_SASI 宏")


def _patch_fontmng_sdlttf(np2kai_dir):
    path = os.path.join(np2kai_dir, "sdl2", "fontmng", "fontmng_sdlttf.cpp")
    if not os.path.exists(path):
        return
    with open(path, "r") as f:
        content = f.read()
    old = 'fontmng.szFaceName = (char *)"Sans Serif";'
    new = 'fontmng.szFaceName = (char *)"Noto Sans CJK JP";'
    if old in content:
        content = content.replace(old, new)
        new2 = (
            '#include <fontconfig/fontconfig.h>\n'
            '#include "fontmng_sdlttf.h"\n'
        )
        if new2 not in content:
            content = content.replace(
                '#include "fontmng_sdlttf.h"',
                new2, 1)
        with open(path, "w") as f:
            f.write(content)
        print("  已替换 CJK 字体为 Noto Sans CJK JP")
    else:
        print("  字体补丁已应用或无需，跳过")


def _np2kai_deps(pkg_manager="apt"):
    pkgs = [
        "build-essential", "cmake", "git", "pkg-config",
        "libgtk-3-dev", "libglib2.0-dev", "libgl1-mesa-dev",
        "libglu1-mesa-dev", "libsdl2-dev", "libsdl2-ttf-dev",
        "libavcodec-dev", "libavformat-dev", "libavutil-dev",
        "libswscale-dev", "libx11-dev", "libxext-dev",
        "libxxf86vm-dev", "libxxf86dga-dev",
        "libsdl2-mixer-dev",
        "libfreetype-dev", "libfontconfig1-dev",
        "libasound2-dev", "libpulse-dev",
        # libcdio: NP2kai CMakeLists unconditionally compiles diskimage/cd/cdd_libcdio.c
        # and defines SUPPORT_LIBCDIO via pkg_check_modules(LIBCDIO libcdio) (non-REQUIRED).
        # Without the dev package cmake silently disables the CD backend; if the headers
        # vanish after a configure that found them, cdd_libcdio.c fails to compile.  Pin the
        # dev package so the CD backend is deterministic across machines.
        "libcdio-dev",
        # wxWidgets GUI front-end + harfbuzz (system dep of SDL3_ttf)
        "libharfbuzz-dev",
    ]
    if pkg_manager == "apt":
        # wxWidgets dev package name differs across releases; pick the
        # first one the apt cache knows about.
        for wx in ("libwxgtk3.2-dev", "libwxgtk3.0-gtk3-dev"):
            if _apt_has(wx):
                pkgs.append(wx)
                break
        else:
            print("[!] 未探测到 wxWidgets 开发包（libwxgtk*-dev），"
                  "cmake 配置阶段可能失败，请手动安装")
        # SDL3 distro packages only exist on newer releases
        # (Ubuntu 25.04+); probe instead of hard-failing on 24.04.
        for sdl3_pkg in ("libsdl3-dev", "libsdl3-ttf-dev"):
            if _apt_has(sdl3_pkg):
                pkgs.append(sdl3_pkg)
    _pkg_install(pkgs, "安装 NP2kai 编译依赖")


def _np2kai_x_deps(pkg_manager="apt"):
    _pkg_install([
        "libx11-dev", "libxext-dev", "libxxf86vm-dev",
        "libxxf86dga-dev", "libsdl2-dev",
    ], "安装 NP2kai X11 依赖")


_CMAKE_PREFIXES = (
    "/usr/local/lib",
    "/usr/lib/x86_64-linux-gnu",
    "/usr/lib",
    "/usr/lib64",
)


def _sdl3_cmake_config(name):
    """Locate <name>Config.cmake as find_package() would resolve it."""
    for prefix in _CMAKE_PREFIXES:
        path = os.path.join(prefix, "cmake", name, f"{name}Config.cmake")
        if os.path.exists(path):
            return path
    return None


def _cmake_build_install(src_dir, name, extra=None):
    """Configure/build/install one CMake project from source."""
    build_dir = os.path.join(src_dir, "build")
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir, exist_ok=True)

    argv = (["cmake", "-S", src_dir, "-B", build_dir,
             "-DCMAKE_BUILD_TYPE=Release"] + list(extra or []))
    if not run_step(f"配置 {name}", argv):
        return False
    if not run_step(f"编译 {name}",
                    ["cmake", "--build", build_dir, "-j",
                     str(os.cpu_count() or 4)]):
        return False
    return run_step(f"安装 {name}",
                    ["cmake", "--install", build_dir], sudo=True)


def _tag_exists(url, tag):
    """Return True if <url> carries the given git tag (one round trip)."""
    r = subprocess.run(
        ["git", "ls-remote", "--tags", url, f"refs/tags/{tag}"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return r.returncode == 0 and bool(r.stdout.strip())


def _build_sdl_component(repo_name, src_dir, tag, desc, extra=None):
    """Clone a pinned tag from the first repo source that has it.

    China mirrors can lag upstream releases, so probe candidates in
    mirror-preferred order instead of burning clone retries on a
    mirror that simply lacks the tag yet.
    """
    primary = _resolve_repo(repo_name, MIRROR)
    candidates = [primary]
    for alt in REPO_MAP[repo_name].values():
        if alt not in candidates:
            candidates.append(alt)
    chosen = None
    for url in candidates:
        if _tag_exists(url, tag):
            chosen = url
            break
        print(f"  [!] {url} 无 tag {tag}，尝试下一来源")
    if chosen is None:
        print(f"[✗] 所有仓库源均无 {desc} tag {tag}")
        sys.exit(1)
    if not _git_clone_with_retry(chosen, src_dir, desc=desc, branch=tag):
        sys.exit(1)
    if not _cmake_build_install(src_dir, desc, extra):
        sys.exit(1)


def _build_sdl3():
    """Build SDL3 + SDL3_ttf from source when dev files are absent.

    The NP2kai wxWidgets front-end hardcodes SDL3::SDL3/SDL3_ttf::SDL3_ttf
    links (upstream CMakeLists.txt NP2kai_WX_base) and wx/fontmng.cpp uses
    SDL3_ttf APIs directly, so SDL2 cannot substitute.  Distro SDL3 dev
    packages only exist on newer releases; otherwise we build from source.
    """
    have_sdl3 = _sdl3_cmake_config("SDL3") is not None
    have_ttf = _sdl3_cmake_config("SDL3_ttf") is not None

    if not have_sdl3:
        _build_sdl_component(
            "sdl3", SDL3_DIR, SDL3_TAG, "SDL3",
            ["-DSDL_TESTS=OFF", "-DSDL_STATIC=OFF"])
    else:
        print("[✓] SDL3 开发文件已安装，跳过源码编译")

    if not have_ttf:
        # Uses system freetype/harfbuzz (installed by _np2kai_deps).
        _build_sdl_component(
            "sdl_ttf", SDL3_TTF_DIR, SDL3_TTF_TAG, "SDL3_ttf",
            ["-DSDLTTF_VENDORED=OFF"])
    elif not have_sdl3:
        print("[✓] SDL3_ttf 开发文件已安装，跳过源码编译")

    if have_sdl3 and have_ttf:
        print("[✓] SDL3 / SDL3_ttf 已安装")
        return
    run_step("刷新动态链接缓存 (ldconfig)", ["ldconfig"], sudo=True)
