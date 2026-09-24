#!/usr/bin/env bash
# Build NP2kai AppImage with all Naiz patches applied.
# Output: NP2kai-*.AppImage in project root.
# Run on a machine where Naiz mouse input works correctly,
# then copy the AppImage to the problematic machine for testing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PATCH_DIR="$SCRIPT_DIR/tools/np2kaipatch"

BUILD_ROOT="/tmp/np2kai_appimage_build"
NP2KAI_SRC="$BUILD_ROOT/np2kai"
BUILD_DIR="$NP2KAI_SRC/build"
APPDIR="$BUILD_ROOT/AppDir"
OUTPUT_DIR="$SCRIPT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[*]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
err()   { echo -e "${RED}[E]${NC} $*"; }

# Build artifacts remain in /tmp/ for inspection on failure.
# Clean manually: rm -rf /tmp/np2kai_appimage_build

# ──────────────────────────────────────────────
# Dependency check (prints commands, does not install)
# ──────────────────────────────────────────────
check_deps() {
    local missing=()
    for pkg in git cmake gcc g++ make pkg-config \
               libsdl3-dev libsdl3-ttf-dev \
               libwxgtk3.2-dev libwxgtk-gl3.2-dev \
               libcdio-dev libgtk-3-dev; do
        if ! dpkg -l "$pkg" &>/dev/null 2>&1; then
            missing+=("$pkg")
        fi
    done
    if [ ${#missing[@]} -gt 0 ]; then
        echo "Missing build dependencies:"
        echo "  sudo apt install ${missing[*]}"
        echo ""
        # Also check for linuxdeploy runtime requirements
        if ! command -v wget &>/dev/null; then
            echo "  sudo apt install wget"
        fi
        exit 1
    fi
    if ! command -v wget &>/dev/null && ! command -v curl &>/dev/null; then
        echo "Need wget or curl to download linuxdeploy."
        echo "  sudo apt install wget"
        exit 1
    fi
    info "All build dependencies found"
}

# ──────────────────────────────────────────────
# Clone NP2kai
# ──────────────────────────────────────────────
clone_np2kai() {
    if [ -d "$NP2KAI_SRC" ]; then
        info "NP2kai source already exists at $NP2KAI_SRC"
        return 0
    fi
    mkdir -p "$BUILD_ROOT"
    info "Cloning NP2kai..."
    git clone --depth 1 "https://github.com/AZO234/NP2kai.git" "$NP2KAI_SRC"
    info "Clone done"
}

# ──────────────────────────────────────────────
# Apply all patches (P1-P6)
# ──────────────────────────────────────────────
apply_patches() {
    info "Applying patches..."
    if [ ! -d "$PATCH_DIR" ]; then
        err "Patch directory not found: $PATCH_DIR"
        exit 1
    fi
    for patch in "$PATCH_DIR"/*.patch; do
        local name
        name="$(basename "$patch")"
        if git -C "$NP2KAI_SRC" apply --reverse --check "$patch" &>/dev/null; then
            info "  [skip] $name already applied"
            continue
        fi
        if git -C "$NP2KAI_SRC" apply "$patch"; then
            info "  [ok]   $name"
        else
            err "  [fail] $name"
            err "Upstream may have diverged from the patches. Try a different commit."
            exit 1
        fi
    done
    info "All patches applied"
}

# ──────────────────────────────────────────────
# SDL2→SDL3 & crypto fixes (same as start.sh np2kai does)
# ──────────────────────────────────────────────
fix_cmake() {
    info "Applying SDL3 / crypto fixes..."

    local cmake_file="$NP2KAI_SRC/CMakeLists.txt"
    local compiler_h="$NP2KAI_SRC/wx/compiler.h"

    # wx/compiler.h: force USE_SDL 3
    if grep -q '#define USE_SDL 2' "$compiler_h" 2>/dev/null; then
        sed -i 's/#define USE_SDL 2/#define USE_SDL 3/' "$compiler_h"
        info "  wx/compiler.h: USE_SDL 2 → 3"
    fi

    # CMakeLists.txt: add SUPPORT_DEBUGSS
    if ! grep -q 'SUPPORT_DEBUGSS' "$cmake_file" 2>/dev/null; then
        sed -i 's/"VERMOUTH_LIB")/"VERMOUTH_LIB" "SUPPORT_DEBUGSS")/' "$cmake_file"
        info "  CMakeLists.txt: added SUPPORT_DEBUGSS"
    fi

    # wxnp21kai: add crypto link
    local old_crypto='target_link_libraries(wxnp21kai NP21kai_base NP2kai_WX_base)'
    local new_crypto='target_link_libraries(wxnp21kai NP21kai_base NP2kai_WX_base crypto)'
    if grep -q "$old_crypto" "$cmake_file" 2>/dev/null; then
        sed -i "s/$old_crypto/$new_crypto/" "$cmake_file"
        info "  CMakeLists.txt: added crypto to wxnp21kai"
    fi

    # SDL2→SDL3 link fix for NP2kai_WX_base
    local sdl2_link='target_link_libraries(NP2kai_WX_base INTERFACE ${lib_math_libraries} ${wxWidgets_LIBRARIES} ${lib_tomlplusplus_libraries} SDL2::SDL2 SDL2_ttf::SDL2_ttf ${LIBCDIO_LINK_LIBRARIES} ${lib_dl_libraries})'
    if grep -q "$sdl2_link" "$cmake_file" 2>/dev/null; then
        # Replace with conditional SDL2/SDL3 block
        local sdl3_block='\t\tif(USE_SDL EQUAL 3)\n\t\t\ttarget_link_libraries(NP2kai_WX_base INTERFACE ${lib_math_libraries} ${wxWidgets_LIBRARIES} ${lib_tomlplusplus_libraries} SDL3::SDL3 SDL3_ttf::SDL3_ttf ${LIBCDIO_LINK_LIBRARIES} ${lib_dl_libraries})\n\t\telseif(USE_SDL EQUAL 2)\n\t\t\ttarget_link_libraries(NP2kai_WX_base INTERFACE ${lib_math_libraries} ${wxWidgets_LIBRARIES} ${lib_tomlplusplus_libraries} SDL2::SDL2 SDL2_ttf::SDL2_ttf ${LIBCDIO_LINK_LIBRARIES} ${lib_dl_libraries})\n\t\telse()\n\t\t\ttarget_link_libraries(NP2kai_WX_base INTERFACE ${lib_math_libraries} ${wxWidgets_LIBRARIES} ${lib_tomlplusplus_libraries} SDL::SDL SDL_ttf::SDL_ttf ${LIBCDIO_LINK_LIBRARIES} ${lib_dl_libraries})\n\t\tendif()'
        sed -i "s|$sdl2_link|$sdl3_block|" "$cmake_file"
        info "  CMakeLists.txt: NP2kai_WX_base SDL2→SDL3 conditional"
    fi

    # SDL2→SDL3 for NP2kai_SDL3_base
    local sdl3_sdl2='target_link_libraries(NP2kai_SDL3_base INTERFACE ${lib_math_libraries} ${lib_vst3sdk_libraries} SDL2::SDL2 SDL2_ttf::SDL2_ttf'
    if grep -q "$sdl3_sdl2" "$cmake_file" 2>/dev/null; then
        sed -i "s|SDL2::SDL2 SDL2_ttf::SDL2_ttf|SDL3::SDL3 SDL3_ttf::SDL3_ttf|" "$cmake_file"
        info "  CMakeLists.txt: NP2kai_SDL3_base SDL2→SDL3"
    fi

    # SDL2→SDL3 for NP2kai_X_SDL3_base
    local x_sdl2='target_link_libraries(NP2kai_X_SDL3_base INTERFACE ${lib_math_libraries} ${lib_glib_libraries} ${GTK2_LIBRARIES} ${X11_LIBRARIES} ${Fontconfig_LIBRARIES} ${Freetype_LIBRARIES} ${lib_vst3sdk_libraries} ${lib_Threads_libraries} SDL2::SDL2 SDL2_ttf::SDL2_ttf'
    if grep -q "$x_sdl2" "$cmake_file" 2>/dev/null; then
        sed -i "s|SDL2::SDL2 SDL2_ttf::SDL2_ttf|SDL3::SDL3 SDL3_ttf::SDL3_ttf|" "$cmake_file"
        info "  CMakeLists.txt: NP2kai_X_SDL3_base SDL2→SDL3"
    fi

    info "CMake fixes done"
}

# ──────────────────────────────────────────────
# Build NP2kai wx port
# ──────────────────────────────────────────────
build_np2kai() {
    if [ -d "$BUILD_DIR" ]; then
        info "Build directory exists, removing..."
        rm -rf "$BUILD_DIR"
    fi

    info "Configuring..."
    cmake -S "$NP2KAI_SRC" -B "$BUILD_DIR" \
        -DBUILD_WX=ON -DBUILD_SDL=OFF -DBUILD_X=OFF -DUSE_SDL=3

    info "Building (this may take a while)..."
    cmake --build "$BUILD_DIR" -j "$(nproc)"

    if [ ! -f "$BUILD_DIR/wxnp21kai" ]; then
        err "Build failed: wxnp21kai not found in $BUILD_DIR"
        exit 1
    fi
    info "Build done: $(file "$BUILD_DIR/wxnp21kai")"
}

# ──────────────────────────────────────────────
# Set up AppDir structure
# ──────────────────────────────────────────────
setup_appdir() {
    info "Setting up AppDir..."
    rm -rf "$APPDIR"
    mkdir -p "$APPDIR/usr/bin"

    # Binary
    cp "$BUILD_DIR/wxnp21kai" "$APPDIR/usr/bin/"

    # .desktop file
    local desktop_src="$NP2KAI_SRC/wx/resources/wxnp21kai.desktop"
    if [ -f "$desktop_src" ]; then
        cp "$desktop_src" "$APPDIR/"
    else
        # Create minimal desktop entry if source doesn't have it
        cat > "$APPDIR/wxnp21kai.desktop" <<DESKEOF
[Desktop Entry]
Type=Application
Name=wxNP21kai IA-32
GenericName=PC-9821 Emulator IA-32
Comment=NP2kai for Naiz testing
Exec=wxnp21kai
Icon=np2
Categories=Game;Emulator;
DESKEOF
    fi

    # Minimal icon (1x1 transparent PNG placeholder — linuxdeploy just needs the file to exist)
    mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
    # Create a minimal valid 256x256 PNG from the default NP2kai icon if available
    local icon_src
    icon_src=$(find "$NP2KAI_SRC" -name 'np2*.png' -o -name 'np2*.xpm' 2>/dev/null | head -1)
    if [ -n "$icon_src" ]; then
        cp "$icon_src" "$APPDIR/usr/share/icons/hicolor/256x256/apps/np2.png"
        cp "$icon_src" "$APPDIR/np2.png"
    else
        # Create minimal valid 1x1 blue PNG
        printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82' \
            > "$APPDIR/usr/share/icons/hicolor/256x256/apps/np2.png"
        cp "$APPDIR/usr/share/icons/hicolor/256x256/apps/np2.png" "$APPDIR/np2.png"
    fi

    # Symlink for AppRun
    ln -sf "usr/bin/wxnp21kai" "$APPDIR/AppRun"

    info "AppDir ready at $APPDIR"
}

# ──────────────────────────────────────────────
# Download and prepare linuxdeploy (+ appimagetool)
# ──────────────────────────────────────────────
prepare_linuxdeploy() {
    local ld_cache="$BUILD_ROOT/linuxdeploy_cache"
    mkdir -p "$ld_cache"

    local ld_bin="$ld_cache/linuxdeploy-x86_64.AppImage"
    local ld_gtk="$ld_cache/linuxdeploy-plugin-gtk-x86_64.AppImage"
    local at_bin="$ld_cache/appimagetool-x86_64.AppImage"

    # Download if missing
    if [ ! -f "$ld_bin" ]; then
        info "Downloading linuxdeploy..."
        wget -q "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage" -O "$ld_bin"
        chmod +x "$ld_bin"
    fi
    if [ ! -f "$ld_gtk" ]; then
        info "Downloading linuxdeploy-plugin-gtk..."
        wget -q "https://github.com/linuxdeploy/linuxdeploy-plugin-gtk/releases/download/continuous/linuxdeploy-plugin-gtk-x86_64.AppImage" -O "$ld_gtk"
        chmod +x "$ld_gtk"
    fi
    if [ ! -f "$at_bin" ]; then
        info "Downloading appimagetool..."
        wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -O "$at_bin"
        chmod +x "$at_bin"
    fi

    # Check FUSE by trying --help (works on any AppImage)
    local fuse_ok=1
    if ! "$ld_bin" --help &>/dev/null; then
        fuse_ok=0
        warn "FUSE not available — will extract AppImages"
    fi

    # Prepare linuxdeploy executable
    if [ "$fuse_ok" -eq 1 ]; then
        LD_RUN="$ld_bin"
    else
        "$ld_bin" --appimage-extract &>/dev/null
        mv squashfs-root "$BUILD_ROOT/linuxdeploy-root"
        LD_RUN="$BUILD_ROOT/linuxdeploy-root/AppRun"
    fi

    # Prepare gtk plugin — linuxdeploy checks PATH for linuxdeploy-plugin-*
    if [ "$fuse_ok" -eq 1 ]; then
        # Symlink with the exact name the plugin discovery expects
        ln -sf "$ld_gtk" "$ld_cache/linuxdeploy-plugin-gtk"
    else
        "$ld_gtk" --appimage-extract &>/dev/null
        mv squashfs-root "$BUILD_ROOT/linuxdeploy-gtk-root"
        mkdir -p "$ld_cache/plugins"
        ln -sf "$BUILD_ROOT/linuxdeploy-gtk-root/AppRun" "$ld_cache/plugins/linuxdeploy-plugin-gtk"
        export PATH="$ld_cache/plugins:$PATH"
    fi
    export PATH="$ld_cache:$PATH"

    # Prepare appimagetool (for --output appimage fallback)
    if [ "$fuse_ok" -eq 1 ]; then
        APPIMAGETOOL="$at_bin"
    else
        "$at_bin" --appimage-extract &>/dev/null
        mv squashfs-root "$BUILD_ROOT/appimagetool-root"
        APPIMAGETOOL="$BUILD_ROOT/appimagetool-root/AppRun"
    fi

    info "linuxdeploy tools ready (FUSE=$([ "$fuse_ok" -eq 1 ] && echo yes || echo no))"
}

# ──────────────────────────────────────────────
# Bundle deps + create AppImage
# ──────────────────────────────────────────────
run_linuxdeploy() {
    prepare_linuxdeploy

    info "Running linuxdeploy to bundle GTK3/wx deps..."
    DEPLOY_GTK_VERSION=3 "$LD_RUN" \
        --appdir "$APPDIR" \
        --plugin gtk

    # Create AppImage from AppDir
    info "Creating AppImage with appimagetool..."
    "$APPIMAGETOOL" "$APPDIR" "$OUTPUT_DIR/NP2kai-test-$(date +%Y%m%d).AppImage"

    info "AppImage bundle done"
}

# ──────────────────────────────────────────────
# Finalize: confirm output
# ──────────────────────────────────────────────
finalize() {
    local f
    f="$OUTPUT_DIR/NP2kai-test-$(date +%Y%m%d).AppImage"
    if [ -f "$f" ]; then
        chmod +x "$f"
        info "AppImage created: $f"
        info "  Size: $(du -h "$f" | cut -f1)"
    else
        warn "Expected output not found: $f"
        warn "Check $OUTPUT_DIR/ for .AppImage files."
    fi
}

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
main() {
    echo ""
    echo "===== NP2kai AppImage builder for Naiz ====="
    echo "Build directory: $BUILD_ROOT"
    echo "Output:          $OUTPUT_DIR/NP2kai-test-*.AppImage"
    echo ""

    check_deps
    clone_np2kai
    apply_patches
    fix_cmake
    build_np2kai
    setup_appdir
    run_linuxdeploy
    finalize

    echo ""
    echo "===== Done ====="
    echo "Copy the AppImage to your Deepin machine and test:"
    echo "  ./NP2kai-test-<date>.AppImage"
    info "Remember to load the same HDI and test mouse behavior."
}

main "$@"
