"""anima.sh backend — animation production (project management, build, MP4->ANI)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .common import find_root, require_root, get_venv_python, VENV_DIR, press_enter
try:
    from i18n import tr
except ImportError:
    from tools.i18n import tr


def dispatch(args: list[str]) -> int:
    root = require_root()
    (root / "animation" / "projects").mkdir(parents=True, exist_ok=True)
    (root / "animation" / "output").mkdir(parents=True, exist_ok=True)

    cmd = args[0] if args else ""
    rest = args[1:]

    handlers = {
        "init": _init,
        "register": _register,
        "check": _check,
        "mp4": _mp4,
        "build": _build,
        "buildall": _buildall,
        "list": _list_cmd,
    }
    if cmd in handlers:
        return handlers[cmd](root, rest)
    if cmd == "":
        return _interactive(root)

    _usage()
    return 1


def _usage() -> None:
    print(tr("Usage:"), "$0 [{init|register|check|mp4|build|buildall|list} args]")
    print(f"  init <{tr('project')}>           {tr('Create animation project skeleton')} animation/projects/<{tr('project')}>/")
    print(f"  register <{tr('project')}>       {tr('Register')} assets/<{tr('project')}>/anim/ {tr('assets into project')} db/<{tr('project')}>.db")
    print(f"  check <{tr('project')}>          {tr('Read-only reconcile asset registration DB (exit 1 on differences)')}")
    print(f"  mp4 <{tr('project')}>            {tr('Scan anim/*.mp4, convert to .ANI (interactive file pick)')}")
    print(f"       [--fps N]        {tr('Sample frame rate (default 10)')}")
    print(f"       [--width W]      {tr('Target width (default 640)')}")
    print(f"       [--height H]     {tr('Target height (default 400)')}")
    print(f"  build <{tr('project')}>/<{tr('script')}>   {tr('Compile')} <{tr('project')}>/scripts/<{tr('script')}>.na → animation/output/")
    print(f"       [--out PATH]     {tr('Specify output path')}")
    print(f"       [--sync]         {tr('Sync this project\'s asset registration DB before building')}")
    print(f"  buildall [--flags]    {tr('Compile all scripts in all projects (summary)')}")
    print(f"  list                  {tr('List all')} <{tr('project')}>/<{tr('script')}>")
    print("")
    print(tr("No args: interactive animation production menu"))
    print("")
    print(tr("Animation scripts use .na extension, separate from scenario scripts .nb (devdocs/79)"))
    print(tr("Run start.sh first to set up the environment"))


# --- Python tool helpers --------------------------------------------------

def _call_python(root: Path, module: str, *argv: str) -> int:
    cmd = [get_venv_python(), "-m", module, *argv]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + ":" + env.get("PYTHONPATH", "")
    return subprocess.call(cmd, env=env)


def _list_projects(root: Path) -> list[str]:
    cmd = [get_venv_python(), "-m", "tools.naiz_build.anim_project", "list"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + ":" + env.get("PYTHONPATH", "")
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    return [p.strip() for p in r.stdout.splitlines() if p.strip()]


# --- Subcommand handlers --------------------------------------------------

def _init(root: Path, args: list[str]) -> int:
    project = args[0] if args else ""
    if not project:
        print(tr("Usage:"), f"anima.sh init <{tr('project')}>")
        return 1
    return _call_python(root, "tools.naiz_build.anim_project", "init", project)


def _register(root: Path, args: list[str]) -> int:
    project = args[0] if args else ""
    if not project:
        print(tr("Usage:"), f"anima.sh register <{tr('project')}>")
        return 1
    return _call_python(root, "tools.naiz_build.anim_register", project)


def _check(root: Path, args: list[str]) -> int:
    project = args[0] if args else ""
    if not project:
        print(tr("Usage:"), f"anima.sh check <{tr('project')}>")
        return 1
    return _call_python(root, "tools.naiz_build.anim_register", "--check", project)


def _mp4(root: Path, args: list[str]) -> int:
    project = args[0] if args else ""
    rest = args[1:]
    if not project:
        print(tr("Usage:"), f"anima.sh mp4 <{tr('project')}> [--fps N] [--width W] [--height H]")
        return 1
    return _call_python(root, "tools.naiz_build.mp4_to_ani", project, *rest)


def _build(root: Path, args: list[str]) -> int:
    spec = args[0] if args else ""
    rest = args[1:]
    if not spec or "/" not in spec:
        print(tr("Usage:"), f"anima.sh build <{tr('project')}>/<{tr('script')}> [--out PATH] [--sync]")
        print(tr("Example:"), "anima.sh build animatest/animatest")
        return 1

    project, name = spec.split("/", 1)
    if not project or not name or "/" in name:
        print(tr("Error: address format must be <project>/<script> (exactly one /):"), spec)
        return 1

    script = root / "animation" / "projects" / project / "scripts" / f"{name}.na"
    if not script.is_file():
        print(tr("Error: animation script not found:"), script)
        print(tr("Available scripts:"))
        _list_cmd(root, [])
        return 1

    return _call_python(root, "tools.naiz_build.anim_import",
                        str(script), *rest, "--project", project)


def _buildall(root: Path, args: list[str]) -> int:
    projects = _list_projects(root)
    if not projects:
        print(tr("Error: no animation projects under animation/projects/"))
        print(tr("First create a project skeleton with"), "anima.sh init <project>")
        return 1

    ok = fail = 0
    failed: list[str] = []
    for p in projects:
        scripts = sorted((root / "animation" / "projects" / p / "scripts").glob("*.na"))
        for script in scripts:
            print()
            print(f"=== {tr('Building animation:')} {p}/{script.stem} ===")
            rc = _call_python(root, "tools.naiz_build.anim_import", str(script), *args)
            if rc == 0:
                ok += 1
            else:
                fail += 1
                failed.append(f"{p}/{script.stem}")
    print()
    print(f"=== {tr('Summary:')} {ok} {tr('success')} / {fail} {tr('failed')} ===")
    if fail > 0:
        for name in failed:
            print(f"  {tr('Failed:')} {name}")
        return 1
    return 0


def _list_cmd(root: Path, _args: list[str]) -> int:
    projects = _list_projects(root)
    if not projects:
        print(f"({tr('No animation projects — create with')} anima.sh init <{tr('project')}>)")
        return 0
    found = False
    for p in projects:
        for script in sorted((root / "animation" / "projects" / p / "scripts").glob("*.na")):
            print(f"{p}/{script.stem}")
            found = True
    if not found:
        print(f"({tr('Animation projects exist but none have scripts — create .na under each project\'s scripts/')})",
              file=sys.stderr)
    return 0


# --- Interactive menus ----------------------------------------------------

def _interactive(root: Path) -> int:
    while True:
        projects = _list_projects(root)
        print()
        print(f"===== {tr('Naiz Animation Production')} =====")
        if not projects:
            print(f"({tr('No animation projects yet')})")
        else:
            print(tr("Select animation project:"))
            for i, p in enumerate(projects, 1):
                print(f"  {i}) {p}")
        print(f"  i) {tr('New project (init)')}")
        print(f"  0) {tr('Exit')}")
        choice = input(f"{tr('Choose')} [0/i/{tr('number')}]: ").strip()
        if choice == "0":
            return 0
        if choice in ("i", "I"):
            newp = input(f"{tr('New project name:')} ").strip()
            if newp:
                rc = _init(root, [newp])
                if rc != 0:
                    print(tr("Init failed:"), newp)
                press_enter()
            continue
        if choice.isdigit() and projects:
            idx = int(choice) - 1
            if 0 <= idx < len(projects):
                _proj_menu(root, projects[idx])
            else:
                print(tr("Invalid selection:"), choice)
        else:
            print(tr("Invalid selection:"), choice)


def _proj_menu(root: Path, project: str) -> None:
    while True:
        print()
        print(f"===== {tr('Project:')} {project} =====")
        print(tr("Choose an action:"))
        print(f"  1) {tr('Check asset registration (check, read-only reconcile)')}")
        print(f"  2) {tr('register sync registration DB')}")
        print(f"  3) {tr('Generate animation (select .na script)')}")
        print(f"  4) {tr('MP4 -> ANI conversion (scan anim/*.mp4)')}")
        print(f"  0) {tr('Back')}")
        choice = input(f"{tr('Choose')} [0-4]: ").strip()
        if choice == "0":
            return
        if choice == "1":
            if _check(root, [project]) != 0:
                print(tr("Reconciliation has differences or check failed:"), project)
            press_enter()
        elif choice == "2":
            if _register(root, [project]) != 0:
                print(tr("Registration failed:"), project)
            press_enter()
        elif choice == "3":
            _script_menu(root, project)
        elif choice == "4":
            if _mp4(root, [project]) != 0:
                print(tr("MP4 conversion failed:"), project)
            press_enter()
        else:
            print(tr("Invalid option:"), choice)


def _script_menu(root: Path, project: str) -> None:
    while True:
        scripts = sorted(
            (root / "animation" / "projects" / project / "scripts").glob("*.na"))
        print()
        print(f"===== {tr('Generate animation:')} {project} =====")
        if not scripts:
            print(f"({tr('No animation scripts for this project yet — create .na under')} animation/projects/{project}/scripts/)")
        else:
            print(tr("Select animation script:"))
            for i, s in enumerate(scripts, 1):
                print(f"  {i}) {s.stem}")
        print(f"  0) {tr('Back')}")
        choice = input(f"{tr('Choose')} [0/{tr('number')}]: ").strip()
        if choice == "0":
            return
        if not choice.isdigit() or int(choice) < 1 or int(choice) > len(scripts):
            print(tr("Invalid selection:"), choice)
            continue
        _action_menu(root, project, scripts[int(choice) - 1].stem)


def _action_menu(root: Path, project: str, name: str) -> None:
    while True:
        print()
        print(f"=== {project}/{name} ===")
        print(tr("Choose an action:"))
        print(f"  1) build        — {tr('build .ANI (auto-derive palette from script project name)')}")
        print(f"  2) build --sync — {tr('sync asset registration DB before building')}")
        print(f"  0) {tr('Back')}")
        choice = input(f"{tr('Choose')} [0-2]: ").strip()
        if choice == "1":
            if _build(root, [f"{project}/{name}"]) != 0:
                print(tr("Build failed:"), f"{project}/{name}")
        elif choice == "2":
            if _build(root, [f"{project}/{name}", "--sync"]) != 0:
                print(tr("Build failed:"), f"{project}/{name}")
        elif choice == "0":
            return
        else:
            print(tr("Invalid option"))
        press_enter()
