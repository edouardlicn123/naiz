"""makegame.sh backend — build / make / test workflow for game projects."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .common import (
    find_root, require_root, get_venv_python, VENV_DIR,
    resolve_pack_mode, describe_pack, PACK_FILE,
    menu_prompt, press_enter, safe_int,
)
try:
    from i18n import tr
except ImportError:
    from tools.i18n import tr


def dispatch(args: list[str]) -> int:
    root = require_root()

    # Pre-parse --pack from args
    explicit_pack = None
    normal: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--pack":
            if i + 1 >= len(args):
                print(f"{tr('Error: --pack requires a value (cmpack|openpack)')}", file=sys.stderr)
                return 1
            explicit_pack = args[i + 1]
            i += 2
            continue
        if a.startswith("--pack="):
            explicit_pack = a[len("--pack="):]
            i += 1
            continue
        normal.append(a)
        i += 1

    pack_mode, extender = resolve_pack_mode(root, explicit_pack)
    os.environ["NAIZ_PACK"] = pack_mode
    os.environ["NAIZ_EXTENDER"] = extender

    cmd = normal[0] if normal else ""
    rest = normal[1:]

    handlers = {
        "pack": _pack,
        "test": _test,
        "build": _build,
        "make": _make_only,
        "makegame": _makegame,
        "i18n-gen": _i18n_gen,
        "audio": _audio,
    }
    if cmd in handlers:
        return handlers[cmd](root, rest, pack_mode)

    if cmd == "":
        return _interactive(root, pack_mode)

    _usage()
    return 1


def _usage() -> None:
    print(tr("Usage:"), "$0 {makegame|make|test|build|i18n-gen|audio|pack} [--pack cmpack|openpack] [args]")
    print("")
    print(f"  makegame <game>   {tr('build game data and make HDI (build + make combined, one step)')}")
    print(f"  build <game>      {tr('build game data')}")
    print(f"  make <game>       {tr('make HDI image (only injects games/<game> -> disks/<game>.hdi)')}")
    print(f"  test <game>       {tr('launch NP2kai test')} [--serial] [--porttest] [--auto]")
    print(f"  audio             {tr('emulator audio latency (BGM vibrato/buzz, global)')}")
    print(f"  i18n-gen <game>   {tr('generate translation templates')} [--force]")
    print(f"  pack [cmpack|openpack]  {tr('view/switch pack mode (writes .naiz_pack as default)')}")
    print(f"\n  --pack cmpack/=  = tools_commercial + DOS/4GW ({tr('commercial chain, default')})")
    print(f"  --pack openpack/= = tools_open + DOS/32A ({tr('open-source chain, no closed-source components')})")
    print(f"\n{tr('No args: interactive game workflow')}")
    print(tr("Run start.sh first to set up the environment"))


# --- Shell helpers --------------------------------------------------------

def _ensure_venv() -> None:
    if not VENV_DIR.is_dir():
        print(tr("Error: Python virtual environment not found"), file=sys.stderr)
        print(tr("Please run first: bash start.sh pip"), file=sys.stderr)
        sys.exit(1)


def _detect_watcom(root: Path) -> int:
    """Source core/detect_watcom.sh as a bash subprocess, capture wcl386 availability."""
    script = root / "core" / "detect_watcom.sh"
    if not script.is_file():
        return 0
    # Run in bash, and check if wcl386 is on PATH afterwards
    r = subprocess.run(["bash", "-c", f"source {script} >/dev/null 2>&1 && command -v wcl386"],
                       capture_output=True, text=True)
    return 0 if r.stdout.strip() else 1


def _call_python(root: Path, module: str, *argv: str) -> int:
    cmd = [get_venv_python(), "-m", module, *argv]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + ":" + env.get("PYTHONPATH", "")
    return subprocess.call(cmd, env=env)


# --- Subcommand handlers --------------------------------------------------

def _pack(root: Path, args: list[str], _pack_mode: str) -> int:
    new_pack = args[0] if args else ""
    if new_pack:
        # Validate and normalize
        _, _ = resolve_pack_mode(root, new_pack)
        pack_mode, extender = resolve_pack_mode(root, new_pack)
        (root / PACK_FILE).write_text(pack_mode)
        print(f"[✓] {tr('Pack mode switched to')} {pack_mode} ({tr('default for subsequent makegame.sh commands')})")
        return 0

    # Interactive
    while True:
        print()
        print(f"===== {tr('Pack mode')} =====")
        print(f"  {tr('Current:')} {describe_pack(_pack_mode)}")
        print(f"  1) cmpack    — tools_commercial + DOS/4GW ({tr('commercial chain')})")
        print(f"  2) openpack  — tools_open + DOS/32A ({tr('open-source chain')})")
        print(f"  0) {tr('Back')}")
        choice = input(f"{tr('Choose')} [0-2]: ").strip()
        if choice == "1":
            (root / PACK_FILE).write_text("cmpack")
            break
        elif choice == "2":
            (root / PACK_FILE).write_text("openpack")
            break
        elif choice == "0":
            return 0
        else:
            print(tr("Invalid option"))
    print(f"[✓] {tr('Saved to')} .naiz_pack: {(root / PACK_FILE).read_text().strip()}")
    return 0


def _test(root: Path, args: list[str], _pack_mode: str) -> int:
    game = args[0] if args else ""
    rest = args[1:]

    if not game:
        print(tr("Usage:"), "makegame.sh test <game> [--serial] [--porttest] [--auto]")
        return 1

    # Handle --porttest
    if "--porttest" in rest:
        print(f"=== {tr('Serial port test:')} {game} ===")
        return _call_python(root, "tools.diag.np2kai_serial", "--game", game)

    # --auto: swap in engine_a.exe if available
    if "--auto" in rest:
        game_dir = root / "games" / game
        auto_exe = game_dir / "engine_a.exe"
        engine_exe = game_dir / "engine.exe"
        if auto_exe.is_file():
            shutil.copy(str(auto_exe), str(engine_exe))
            print("[auto] engine_a.exe → engine.exe")
            print(f"[auto] {tr('Rebuilding HDI with auto engine')}")
            _call_python(root, "tools.naiz_img.inject", "--game", game, "--yes")
        else:
            print(f"[auto] {tr('Warning:')} {auto_exe} {tr('not found, using original engine.exe')}")

    # HDI freshness gate
    hdi = root / "disks" / f"{game}.hdi"
    engine = root / "games" / game / "engine.exe"
    if hdi.is_file() and engine.is_file():
        if hdi.stat().st_mtime < engine.stat().st_mtime:
            print(f"=== ERROR: {tr('HDI stale:')} {hdi} {tr('is older than')} {engine} ===")
            print(f"    {tr('The emulator would run the old engine (build only deploys the DOS tree; make injects into the HDI).')}")
            print(f"    {tr('Fix:')} ./makegame.sh build {game} && ./makegame.sh make {game}")
            return 1

    # Pass through remaining flags
    extra = []
    for arg in rest:
        if arg in ("--serial", "--auto"):
            extra.append(arg)

    return _call_python(root, "tools.env_setup.install_env", "test-hdi",
                        "--hdi", str(hdi), *extra)


def _build(root: Path, args: list[str], _pack_mode: str) -> int:
    game = args[0] if args else ""
    if not game:
        print(tr("Usage:"), "makegame.sh build <game>")
        return 1
    rc = _detect_watcom(root)
    if rc != 0:
        return rc
    return _call_python(root, "tools.naiz_build.build_game", game)


def _makegame(root: Path, args: list[str], pack_mode: str) -> int:
    game = args[0] if args else ""
    if not game:
        print(tr("Usage:"), "makegame.sh makegame <game>")
        return 1
    rc = _detect_watcom(root)
    if rc != 0:
        return rc

    # build first
    rc = _call_python(root, "tools.naiz_build.build_game", game)
    if rc != 0:
        return rc

    print(f"=== {tr('Building HDI image:')} {game} [{describe_pack(pack_mode)}] ===")
    return _call_python(root, "tools.naiz_img.inject", "--game", game, "--yes")


def _i18n_gen(root: Path, args: list[str], _pack_mode: str) -> int:
    game = args[0] if args else ""
    rest = args[1:]
    if not game:
        print(tr("Usage:"), "makegame.sh i18n-gen <game> [--force]")
        return 1
    return _call_python(root, "tools.naiz_conv.i18n_gen",
                        str(root / "projects" / game), *rest)


def _make_only(root: Path, args: list[str], pack_mode: str) -> int:
    game = args[0] if args else ""
    if not game:
        print(tr("Usage:"), "makegame.sh make <game>")
        return 1

    # Engine freshness guard: games/<game>/engine.exe behind core/
    if pack_mode == "openpack":
        pairs = [(root / "core" / "engine32a.exe", "engine.exe"),
                 (root / "core" / "engine_a32a.exe", "engine_a.exe")]
    else:
        pairs = [(root / "core" / "engine.exe", "engine.exe"),
                 (root / "core" / "engine_a.exe", "engine_a.exe")]

    for core_exe_name, deployed_name in pairs:
        deployed = root / "games" / game / deployed_name
        if core_exe_name.is_file() and (not deployed.is_file()
                                        or deployed.stat().st_mtime < core_exe_name.stat().st_mtime):
            print(f"=== ERROR: games/{game}/{deployed_name} {tr('is behind')} core/{core_exe_name.name} ===")
            print(f"    {tr('make only injects games/<game>/; it does not deploy the engine.')}")
            print(f"    {tr('Fix:')} ./makegame.sh build {game} && ./makegame.sh make {game}")
            return 1

    print(f"=== {tr('Building HDI image:')} {game} [{describe_pack(pack_mode)}] ===")
    return _call_python(root, "tools.naiz_img.inject", "--game", game, "--yes")


def _audio_apply(root: Path, latency: str) -> int:
    return _call_python(root, "tools.env_setup.install_env", "audio-latency", "--latency", latency)


def _audio(root: Path, _args: list[str], _pack_mode: str) -> int:
    while True:
        print()
        print(f"===== {tr('Emulator audio latency (BGM vibrato/buzz)')} =====")
        print(f"  {tr('Writes')} ~/.config/wxnp21kai/wxnp21kai.toml [NP21kai] ({tr('global, affects all games')})")
        print(f"  1) Off     — {tr('do not change emulator (use its current settings)')}")
        print(f"  2) Short   — Latencys=47   (2048 {tr('blocks')} ≈ 23ms)")
        print(f"  3) Normal  — Latencys=93   (4096 {tr('blocks')} ≈ 93ms)   ← {tr('causes ~13.5Hz vibrato')}")
        print(f"  4) Long    — Latencys=186  (8192 {tr('blocks')} ≈ 186ms)  ← {tr('recommended')}")
        print(f"  5) Max     — Latencys=372  (16384 {tr('blocks')} ≈ 372ms) ← {tr('most thorough, most audible SE latency')}")
        print(f"  0) {tr('Back')}")
        choice = input(f"{tr('Choose')} [0-5]: ").strip()
        mapping = {"1": "off", "2": "short", "3": "normal", "4": "long", "5": "max"}
        if choice in mapping:
            _audio_apply(root, mapping[choice])
        elif choice == "0":
            return 0
        else:
            print(tr("Invalid option"))


def _interactive(root: Path, pack_mode: str) -> int:
    games = sorted(d.name for d in (root / "projects").iterdir() if d.is_dir())
    if not games:
        print(tr("Error: no projects found under projects/"))
        return 1

    while True:
        print()
        print(f"===== {tr('Naiz Project Workflow')} =====")
        print(tr("Detected projects:"))
        for i, g in enumerate(games, 1):
            print(f"  {i}) {g}")
        print(f"  0) {tr('Exit')}")
        choice = input(f"{tr('Choose a game')} [1]: ").strip() or "1"
        if choice == "0":
            return 0
        idx = safe_int(choice, 1, len(games))
        if idx is None:
            print(f"{tr('Invalid selection:')} {choice}")
            return 1
        game = games[idx - 1]

        while True:
            print()
            print(f"=== {game}  [{tr('pack mode:')} {pack_mode}] ===")
            print(tr("Choose an action:"))
            print(f"  1) makegame      — {tr('build project data + make HDI (build + make)')}")
            print(f"  2) build         — {tr('build project data')}")
            print(f"  3) make          — {tr('make HDI image')}")
            print(f"  4) test          — {tr('launch NP2kai test')}")
            print(f"  5) test --porttest — {tr('serial hardware test')}")
            print(f"  6) audio         — {tr('emulator audio latency (global)')}")
            print(f"  7) pack          — {tr('switch pack mode (cmpack / openpack)')}")
            print(f"  0) {tr('Back')}")
            action = input(f"{tr('Choose')} [0-7]: ").strip()
            actions = {
                "1": ("makegame", [game]),
                "2": ("build", [game]),
                "3": ("make", [game]),
                "4": ("test", [game]),
                "5": ("test", [game, "--porttest"]),
                "6": ("audio", []),
                "7": ("pack", []),
            }
            if action == "0":
                break
            if action in actions:
                cmd, rest = actions[action]
                dispatch([cmd, *rest])
            else:
                print(tr("Invalid option"))
            press_enter()
