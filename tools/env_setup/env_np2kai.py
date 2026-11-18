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
try:
    from i18n import tr
except ImportError:  # imported as `tools.env_setup` (repo root on sys.path)
    from tools.i18n import tr
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
    print(f"[DEPRECATED] {tr('i286 core is deprecated, use the IA32 core (wxnp21kai, wxWidgets/GTK3)')}")
    print(f"===== {tr('Compiling i286 core')} =====")

    np2kai_dir = _get_np2kai_source()
    _patch_sdl2ttf_cmake(np2kai_dir)
    build_dir = os.path.join(np2kai_dir, "build")

    print(f"--- {tr('Apply upstream patches')} ---")
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
            print(f"  {tr('Added SUPPORT_SASI macro')}")
        else:
            print(f"  {tr('SUPPORT_SASI already present, skipped')}")

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
            print(f"  {tr('Fixed sxsi_issasi() NC detection logic')}")
        else:
            print(f"  {tr('sxsi_issasi() already fixed, skipped')}")

    if os.path.exists(sxsi_c):
        with open(sxsi_c, "r") as f:
            sxsi_content = f.read()
        if "return(SXSIMEDIA_INVSASI + 7);" in sxsi_content:
            sxsi_content = sxsi_content.replace(
                "return(SXSIMEDIA_INVSASI + 7);",
                "return(7);		// 非 SASI 标准几何，标记为未知类型但不设为 INVSASI")
            with open(sxsi_c, "w") as f:
                f.write(sxsi_content)
            print(f"  {tr('Fixed gethddtype() INVSASI flag')}")
        else:
            print(f"  {tr('gethddtype() already fixed, skipped')}")
    subprocess.run(
        ["sed", "-i",
         '/target_link_libraries(NP2kai_SDL2_base.*lib_dl_libraries})/ s|}|) crypto}|',
         cmake_file],
        check=False)

    _patch_fontmng_sdlttf(np2kai_dir)

    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)

    ok = run_step(tr("Generate build system (i286 core, SDL2)"),
                  ["cmake", "-S", np2kai_dir, "-B", build_dir,
                   "-DBUILD_I286=ON", "-DBUILD_SDL=ON",
                   "-DUSE_SDL=2", "-DBUILD_WX=OFF"])
    if not ok:
        sys.exit(1)

    ok = run_step(tr("Compile sdlnp2kai_sdl2"),
                  ["cmake", "--build", build_dir, "--target", "sdlnp2kai_sdl2",
                   "-j", str(os.cpu_count() or 4)])
    if not ok:
        sys.exit(1)

    binary = os.path.join(build_dir, "sdlnp2kai_sdl2")
    if os.path.exists(binary):
        print(f"[✓] {tr('Compilation complete:')} {binary}")
    else:
        print(f"[✗] {tr('Compilation failed:')} {tr('not generated')} {binary}")
        sys.exit(1)

    run_step(tr("Install to /usr/local/bin"),
             ["cp", binary, "/usr/local/bin/sdlnp2kai_sdl2"], sudo=True)

    if os.path.exists("/usr/local/bin/sdlnp2kai_sdl2"):
        print(f"[✓] {tr('Install verification:')} sdlnp2kai_sdl2")
    else:
        print(f"[!] {tr('Warning:')} {tr('installed i286 core not found')}")
        print(f"    {tr('Please check /usr/local/bin/ or run')} start.sh → {tr('detect dev environment')}")


def _apply_common_patches(np2kai_dir):
    """Apply tools/np2kaipatch/*.patch to the source tree before building.

    Patches are ordered by filename prefix (01-..05-..).  A patch already
    applied (checked via `git apply --reverse --check`) is skipped, so the
    step is idempotent on a reused checkout such as /tmp/NP2kai.
    """
    patch_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "np2kaipatch"))
    if not os.path.isdir(patch_dir):
        print(f"[✗] {tr('np2kaipatch directory does not exist')}")
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
            print(f"  [✓] {patch_file} {tr('already applied, skipped')}")
            continue
        if not run_step(f"{tr('Apply patch')} {patch_file}", ["git", "apply", "--ignore-whitespace", full], cwd=np2kai_dir):
            print(f"[✗] {tr('Patch')} {patch_file} {tr('failed to apply (upstream may have changed)')}")
            print(f"    {tr('If using an old /tmp/NP2kai, delete it and re-run start.sh np2kai to re-checkout')}")
            sys.exit(1)
    if found == 0:
        print(f"[✗] {tr('No .patch files under np2kaipatch directory')}")
        sys.exit(1)
    print(f"[✓] {tr('NP2kai common patches applied')}")


def cmd_np2kai():
    print("")
    print(f"===== {tr('Compiling NP2kai (IA-32 core, wxWidgets/GTK3)')} =====")
    print(f"    ({tr('set NAIZ_NP2KAI_REBUILD=1 to force rebuild')})")

    if os.path.exists("/usr/local/bin/wxnp21kai") and not os.environ.get("NAIZ_NP2KAI_REBUILD"):
        print(f"[✓] {tr('NP2kai already installed:')} /usr/local/bin/wxnp21kai")
        print(f"    {tr('To rebuild, run:')} NAIZ_NP2KAI_REBUILD=1 start.sh np2kai")

        print(f"[*] {tr('Check patch status:')}")
        if not _check_np2kai_patches():
            print(f"  [!] {tr('Please uninstall and reinstall')}")
        return

    np2kai_dir = _get_np2kai_source()
    _apply_common_patches(np2kai_dir)
    _np2kai_deps()
    _build_sdl3()

    build_dir = os.path.join(np2kai_dir, "build_wx")
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)

    ok = run_step(tr("Generate build system (IA32 core, GTK3, wxWidgets)"),
                  ["cmake", "-S", np2kai_dir, "-B", build_dir,
                   "-DBUILD_I286=OFF", "-DBUILD_WX=ON",
                   # USE_SDL=3 runs find_package(SDL3/SDL3_ttf), satisfied
                   # either by distro dev packages (newer releases) or by
                   # the source build in _build_sdl3().
                   "-DUSE_SDL=3",
                   "-DCMAKE_BUILD_TYPE=Release"])
    if not ok:
        sys.exit(1)

    ok = run_step(tr("Compile NP2kai wxnp21kai"),
                  ["cmake", "--build", build_dir, "--target", "wxnp21kai",
                   "-j", str(os.cpu_count() or 4)])
    if not ok:
        sys.exit(1)

    binary = os.path.join(build_dir, "wxnp21kai")
    if os.path.exists(binary):
        print(f"[✓] {tr('Compilation complete:')} {binary}")
    else:
        print(f"[✗] {tr('Compilation failed:')} {tr('not generated')} {binary}")
        sys.exit(1)

    run_step(tr("Install to /usr/local/bin"),
             ["cp", binary, "/usr/local/bin/wxnp21kai"], sudo=True)

    if os.path.exists("/usr/local/bin/wxnp21kai"):
        print(f"[✓] {tr('Install verification:')} wxnp21kai")
    else:
        print(f"[!] {tr('Warning:')} {tr('installed wxnp21kai not found')}")
        print(f"    {tr('Please check /usr/local/bin/')}")
    print(f"[✓] {tr('NP2kai installation complete (with patches P1-P6)')}")


def cmd_deps():
    print("")
    print(f"===== {tr('System dependency installation')} =====")
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
        print(f"  {tr('Patched: SDL2_ttf CMake freetype path')}")


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
        print(f"  {tr('Added SUPPORT_IDE macro')}")
    else:
        print(f"  {tr('SUPPORT_IDE already present, skipped')}")

    if "SUPPORT_SASI" not in content:
        content = content.replace(
            "#define\tUSE_SDL_JOYSTICK",
            "#define\tUSE_SDL_JOYSTICK\n\n#define SUPPORT_SASI")
        with open(path, "w") as f:
            f.write(content)
        print(f"  {tr('Added SUPPORT_SASI macro')}")


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
        print(f"  {tr('Replaced CJK font with Noto Sans CJK JP')}")
    else:
        print(f"  {tr('Font patch already applied or not needed, skipped')}")


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
            print(f"[!] {tr('No wxWidgets dev package detected (libwxgtk*-dev); cmake configure may fail, please install manually')}")
        # SDL3 distro packages only exist on newer releases
        # (Ubuntu 25.04+); probe instead of hard-failing on 24.04.
        for sdl3_pkg in ("libsdl3-dev", "libsdl3-ttf-dev"):
            if _apt_has(sdl3_pkg):
                pkgs.append(sdl3_pkg)
    _pkg_install(pkgs, tr("Installing NP2kai build dependencies"))


def _np2kai_x_deps(pkg_manager="apt"):
    _pkg_install([
        "libx11-dev", "libxext-dev", "libxxf86vm-dev",
        "libxxf86dga-dev", "libsdl2-dev",
    ], tr("Installing NP2kai X11 dependencies"))


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
    if not run_step(f"{tr('Configure')} {name}", argv):
        return False
    if not run_step(f"{tr('Compile')} {name}",
                    ["cmake", "--build", build_dir, "-j",
                     str(os.cpu_count() or 4)]):
        return False
    return run_step(f"{tr('Install')} {name}",
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
        print(f"  [!] {url} {tr('has no tag')} {tag}, {tr('trying next source')}")
    if chosen is None:
        print(f"[✗] {tr('No repo source has')} {desc} {tr('tag')} {tag}")
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
        print(f"[✓] {tr('SDL3 dev files installed, skipping source build')}")

    if not have_ttf:
        # Uses system freetype/harfbuzz (installed by _np2kai_deps).
        _build_sdl_component(
            "sdl_ttf", SDL3_TTF_DIR, SDL3_TTF_TAG, "SDL3_ttf",
            ["-DSDLTTF_VENDORED=OFF"])
    elif not have_sdl3:
        print(f"[✓] {tr('SDL3_ttf dev files installed, skipping source build')}")

    if have_sdl3 and have_ttf:
        print(f"[✓] {tr('SDL3 / SDL3_ttf installed')}")
        return
    run_step(tr("Refresh dynamic linker cache (ldconfig)"), ["ldconfig"], sudo=True)
