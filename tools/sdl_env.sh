# Auto-detect display server and set SDL driver accordingly.
# Source this file in any script that launches NP2kai:
#   source tools/sdl_env.sh

detect_sdl_video_driver() {
    # Respect user override
    if [ -n "${SDL_VIDEODRIVER+set}" ]; then
        return
    fi

    if [ "${XDG_SESSION_TYPE:-}" = "wayland" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
        export SDL_VIDEODRIVER=wayland
    elif [ -z "${DISPLAY:-}" ]; then
        echo "WARNING: No display server detected (DISPLAY and WAYLAND_DISPLAY both unset)." >&2
        echo "NP2kai may fail to open a window." >&2
    fi
}

# Audio: prefer PulseAudio, SDL will fall back if unavailable
export SDL_AUDIODRIVER=pulse

detect_sdl_video_driver
