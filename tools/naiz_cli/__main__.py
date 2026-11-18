"""Entry point: `python -m tools.naiz_cli <script_name> [args...]`.

script_name is the shell wrapper that invoked us: `start` / `makegame` / `anima`.
Each thin shell wrapper does nothing but resolve ROOT and exec this module.
"""
from __future__ import annotations

import sys


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print("Usage: python -m tools.naiz_cli <start|makegame|anima> [args...]")
        return 1

    script = argv[0]
    args = argv[1:]

    # Import lazily so unused backends don't slow down startup
    if script == "start":
        from . import start as backend
    elif script == "makegame":
        from . import makegame as backend
    elif script == "anima":
        from . import anima as backend
    else:
        print(f"Unknown script: {script}", file=sys.stderr)
        print("Available: start, makegame, anima")
        return 1

    return backend.dispatch(args)


if __name__ == "__main__":
    sys.exit(main())
