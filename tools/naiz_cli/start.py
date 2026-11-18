"""start.sh backend — environment setup, audit, asset download, language."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .common import (
    find_root, require_root, VENV_PYTHON, get_venv_python,
    menu_prompt, press_enter, safe_int, naiz_set_lang,
)
try:
    from i18n import tr
except ImportError:
    from tools.i18n import tr


# ---------------------------------------------------------------------------
# Command-line dispatch
# ---------------------------------------------------------------------------

def dispatch(args: list[str]) -> int:
    cmd = args[0] if args else ""
    rest = args[1:]
    root = find_root()

    # Direct subcommands that already exec a Python tool
    direct = {
        "check": ["tools.env_setup.install_env", "check"],
        "pip": ["tools.env_setup.install_env", "pip-install"],
        "deps": ["tools.env_setup.install_env", "system-tools"],
        "np2kai": ["tools.env_setup.install_env", "np2kai"],
        "watcom": ["tools.env_setup.install_env", "install-watcom"],
        "mirror": ["tools.env_setup.install_env", "mirror"],
    }
    if cmd in direct:
        mod, *tail = direct[cmd]
        return _exec_python([mod, *tail, *rest], root)

    if cmd == "map":
        return _exec_python(["tools.diag.code_map", *rest], root)
    if cmd == "audit":
        return _run_audit(root)
    if cmd == "fullaudit":
        return _run_fullaudit(root, "--no-make" in rest)
    if cmd == "commercial":
        return _download_menu(root, _fetch_pack, "Commercial assets download (cmpack)",
                              "Commercial", "tools_commercial", COMMERCIAL_DOWNLOADS)
    if cmd == "openpack":
        return _download_menu(root, _fetch_pack, "Open-source assets download (openpack)",
                              "Open-source", "tools_open", OPEN_DOWNLOADS)
    if cmd == "lang":
        return _lang_menu()
    if cmd == "":
        return _main_menu(root)
    _usage()
    return 1


def _usage() -> None:
    print(tr("Usage:"), "start.sh {check|pip|deps|np2kai|watcom|mirror|commercial|openpack|audit|map|fullaudit|fullaudit --no-make|lang}")
    print(tr("No args: interactive menu"))


def _exec_python(argv: list[str], root: Path) -> int:
    """Run `python -m <module> [rest...]` via the venv python."""
    cmd = [get_venv_python(), "-m", *argv]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + ":" + env.get("PYTHONPATH", "")
    return subprocess.call(cmd, env=env)


# ---------------------------------------------------------------------------
# Interactive menus
# ---------------------------------------------------------------------------

def _main_menu(root: Path) -> int:
    while True:
        os.system("clear")
        print("=" * 40)
        print(f"     {tr('Naiz Environment Setup')}")
        print("=" * 40)
        print(f"  1) {tr('Environment check')}")
        print(f"  2) {tr('Environment install')}")
        print(f"  3) {tr('Symbol encapsulation/split audit')}")
        print(f"  4) {tr('Full project rule audit (fullaudit)')}")
        print(f"  5) {tr('Language')}")
        print(f"  0) {tr('Exit')}")
        print("=" * 40)
        choice = input(f"{tr('Choose')} [0-5]: ").strip()
        if choice == "1":
            _exec_python(["tools.env_setup.install_env", "check"], root)
        elif choice == "2":
            _env_menu(root)
        elif choice == "3":
            _run_audit(root)
        elif choice == "4":
            _run_fullaudit(root)
        elif choice == "5":
            _lang_menu()
        elif choice == "0":
            print(tr("Goodbye!"))
            return 0
        else:
            print(tr("Invalid option, please try again."))
            import time; time.sleep(1)
            continue
        print()
        press_enter()


def _env_menu(root: Path) -> None:
    while True:
        os.system("clear")
        print("=" * 40)
        print(f"     {tr('Environment Install')}")
        print("=" * 40)
        print(f"  1) {tr('Install Python dependencies')}")
        print(f"  2) {tr('System toolchain (deps + gcc-ia16)')}")
        print(f"  3) {tr('NP2kai emulator (wxWidgets/GTK3) [primary]')}")
        print(f"  4) {tr('Install Open Watcom toolchain')}")
        print(f"  5) {tr('Commercial assets download (cmpack)')}")
        print(f"  6) {tr('Open-source assets download (openpack)')}")
        print(f"  7) {tr('Git repository source (GitHub/domestic mirror)')}")
        print(f"  0) {tr('Back')}")
        print("=" * 40)
        choice = input(f"{tr('Choose')} [0-7]: ").strip()
        mapping = {
            "1": ["tools.env_setup.install_env", "pip-install"],
            "2": ["tools.env_setup.install_env", "system-tools"],
            "3": ["tools.env_setup.install_env", "np2kai"],
            "4": ["tools.env_setup.install_env", "install-watcom"],
            "7": ["tools.env_setup.install_env", "mirror"],
        }
        if choice == "0":
            return
        if choice in mapping:
            _exec_python(mapping[choice], root)
        elif choice == "5":
            _download_menu(root, _fetch_pack, "Commercial assets download (cmpack)",
                           "Commercial", "tools_commercial", COMMERCIAL_DOWNLOADS)
        elif choice == "6":
            _download_menu(root, _fetch_pack, "Open-source assets download (openpack)",
                           "Open-source", "tools_open", OPEN_DOWNLOADS)
        else:
            print(tr("Invalid option, please try again."))
            import time; time.sleep(1)
            continue
        print()
        press_enter()


# ---------------------------------------------------------------------------
# Language menu
# ---------------------------------------------------------------------------

def _lang_menu() -> None:
    root = find_root()
    while True:
        os.system("clear")
        print("=" * 40)
        print(f"     {tr('Language')}")
        print("=" * 40)
        print("  1) English")
        print("  2) 中文")
        print("  3) 日本語")
        print("  4) 한국어")
        print(f"  0) {tr('Back')}")
        print("=" * 40)
        choice = input(f"{tr('Choose')} [0-4]: ").strip()
        native = {"1": ("eng", "English"), "2": ("chi", "中文"),
                  "3": ("jpn", "日本語"), "4": ("kor", "한국어")}
        if choice in native:
            code, label = native[choice]
            naiz_set_lang(root, code)
            print(f"[✓] {label}")
            print()
            press_enter()
            continue
        if choice == "0":
            return
        print(tr("Invalid option, please try again."))
        import time; time.sleep(1)


# ---------------------------------------------------------------------------
# Symbol audit
# ---------------------------------------------------------------------------

def _run_audit(root: Path) -> int:
    print(f"===== {tr('Symbol encapsulation/split audit')} =====")
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = logs / f"symbol_audit_{stamp}.log"

    with out.open("w") as f:
        f.write(f"=== symbol_audit {stamp} ===\n")
        f.write(f"{tr('Command:')} {get_venv_python()} -m tools.diag.symbol_audit\n\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + ":" + env.get("PYTHONPATH", "")
    rc = subprocess.call(
        [get_venv_python(), "-m", "tools.diag.symbol_audit"],
        stdout=out.open("a"), stderr=subprocess.STDOUT,
        env=env)
    if rc != 0:
        out.unlink(missing_ok=True)
        print(f"[✗] {tr('Audit failed, log deleted')}")
        return 1
    # Cat to terminal (subprocess was the file above, but we need to show it)
    with out.open() as f:
        print(f.read())
    lines = sum(1 for _ in out.open())
    print(f"\n[✓] {tr('Audit done')}: {out} ({lines} {tr('lines')})")
    return 0


# ---------------------------------------------------------------------------
# Full audit (fullaudit)
# ---------------------------------------------------------------------------

def _run_fullaudit(root: Path, no_make: bool = False) -> int:
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = logs / f"fullaudit_{stamp}.log"

    def _log(msg: str) -> None:
        """Write msg to both terminal and log file."""
        print(msg, flush=True)
        with out.open("a") as f:
            f.write(msg + "\n")

    with out.open("w") as f:
        pass  # ensure log file exists

    _log(f"===== {tr('Full project rule audit')} {datetime.now():%F %T} =====")
    overall = 0

    def _step(n: int, total: int, label: str) -> str:
        return f"--- [{n}/{total}] {label} ---"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + ":" + env.get("PYTHONPATH", "")

    # 1) Rule audit
    _log(_step(1, 7, tr("Rule audit (git incremental, audit_state.json)")))
    rc = subprocess.call([get_venv_python(), "-m", "tools.audit.audit"],
                         env=env, stdout=out.open("a"), stderr=subprocess.STDOUT)
    if rc != 0:
        _log(f"[✗] {tr('Rule audit found deterministic violations')} (exit {rc})")
        overall = 1
    else:
        _log(f"[✓] {tr('Rule audit passed')}")

    # 2) pytest
    _log(_step(2, 7, f"pytest ({root / 'tools' / 'tests'})"))
    rc = subprocess.call([get_venv_python(), "-m", "pytest",
                          str(root / "tools" / "tests"), "-q"],
                         env=env, stdout=out.open("a"), stderr=subprocess.STDOUT)
    if rc != 0:
        _log(f"[✗] {tr('pytest failed')}")
        overall = 1
    else:
        _log(f"[✓] {tr('pytest passed')}")

    # 3) NB validator
    _log(_step(3, 7, tr("NB script static check (nb_validator, all projects)")))
    vr = 0
    for d in sorted((root / "projects").iterdir()):
        db = d / "ASSETS.DB"
        if not db.is_file():
            continue
        rc = subprocess.call(
            [get_venv_python(), str(root / "tools" / "naiz_build" / "nb_validator.py"), str(d)],
            env=env, stdout=out.open("a"), stderr=subprocess.STDOUT)
        if rc != 0:
            _log(f"[✗] {tr('NB check failed')}: {d}")
            vr = 1
        else:
            _log(f"[✓] {tr('NB check passed')}: {d}")
    if vr:
        _log(f"[✗] {tr('nb_validator has errors')}")
        overall = 1
    else:
        _log(f"[✓] {tr('nb_validator passed (all projects)')}")

    # 4) py_compile
    _log(_step(4, 7, "py_compile (tools/**/*.py)"))
    pc = 0
    for py in sorted((root / "tools").rglob("*.py")):
        try:
            py.relative_to(root / "tools" / "venv")
            continue
        except ValueError:
            pass
        if "__pycache__" in py.parts:
            continue
        rc = subprocess.call([get_venv_python(), "-m", "py_compile", str(py)])
        if rc != 0:
            _log(f"[✗] {tr('py_compile failed')}: {py}")
            pc = 1
    if pc:
        overall = 1
    else:
        _log(f"[✓] {tr('py_compile passed')}")

    # 5) bash -n
    _log(_step(5, 7, f"bash -n ({tr('shell syntax')})"))
    sn = 0
    shells = [root / "makegame.sh", root / "start.sh"] + sorted((root / "core").glob("*.sh"))
    for s in shells:
        rc = subprocess.call(["bash", "-n", str(s)])
        if rc != 0:
            with out.open("a") as f:
                f.write("--- bash -n " + str(s) + " ---\n")
                subprocess.call(["bash", "-n", str(s)], stdout=f, stderr=subprocess.STDOUT)
            _log(f"[✗] {tr('bash -n failed')}: {s}")
            sn = 1
    if sn:
        overall = 1
    else:
        _log(f"[✓] {tr('bash -n passed')}")

    # 6) symbol_audit --gate
    _log(_step(6, 7, tr("symbol_audit (A/B sections: unused static/dead exports, --gate)")))
    rc = subprocess.call([get_venv_python(), "-m", "tools.diag.symbol_audit",
                          "-s", "A,B", "--gate"],
                         env=env, stdout=out.open("a"), stderr=subprocess.STDOUT)
    if rc != 0:
        _log(f"[✗] {tr('symbol_audit failed (A/B sections non-empty)')}")
        overall = 1
    else:
        _log(f"[✓] {tr('symbol_audit passed (A/B sections empty)')}")

    # 7) make
    if not no_make:
        _log(_step(7, 7, "make -C core"))
        rc = subprocess.call(["make", "-C", str(root / "core")],
                             stdout=out.open("a"), stderr=subprocess.STDOUT)
        if rc != 0:
            _log(f"[✗] {tr('make failed')}")
            overall = 1
        else:
            text = out.read_text(errors="ignore") if out.is_file() else ""
            if "Warning" in text or "Error" in text:
                _log(f"[!] {tr('make produced Warning/Error output (see above)')}")
            else:
                _log(f"[✓] {tr('make passed (0 err / 0 warn)')}")
    else:
        _log(f"--- [7/7] {tr('make skipped (--no-make)')} ---")

    _log("")
    if overall == 0:
        _log(f"[✓] {tr('fullaudit all passed')}: {out}")
        return 0
    _log(f"[✗] {tr('fullaudit has failures')}: {out}")
    return 1


# ---------------------------------------------------------------------------
# Asset pack download
# ---------------------------------------------------------------------------

COMMERCIAL_DOWNLOADS = [
    "GitHub Releases (naiz_cmpack) v1.1|https://github.com/edouardlicn123/naiz_cmpack/releases/download/1.1/tools_commercial.zip|020af0e498e013886b196f8c8d6811a10618c6b51ba176608138e7b987a388a3"
]

OPEN_DOWNLOADS = [
    "GitHub Releases 1.1 (naiz-openpack)|https://github.com/edouardlicn123/naiz-openpack/releases/download/1.1/tools_open.zip|92f2859417f7aced53ff62368bb07a2ea97bf2f26219835236e7185b74d59eb7"
]


def _fetch_pack(root: Path, desc: str, url: str, sha: str, dirname: str, label: str) -> int:
    """Download zip, verify sha256, extract to ROOT."""
    print()
    print(f"===== {label}{tr(' download:')} {desc} =====")

    # Symlink check
    p = root / dirname
    if p.is_symlink():
        print(f"  {dirname} {tr('is a symlink ->')} {os.path.realpath(p)}")
        print(f"  {tr('Use this symlink directly in dev; to install from Release, delete the symlink first.')}")
        return 1

    if p.is_dir():
        print(f"  {dirname}/ {tr('already exists.')}")
        ans = input(f"  {tr('Enter y to re-download, any other key to skip:')} ").strip()
        if ans not in ("y", "Y"):
            print(f"[✓] {tr('Download skipped')}")
            return 0

    tmpzip = Path(tempfile.mktemp(suffix=f"/{dirname}.XXXXXX.zip"))
    tmpzip.parent.mkdir(parents=True, exist_ok=True)
    print(f"  {tr('Downloading:')} {url}")
    rc = subprocess.call(["curl", "-fsSL", "--retry", "3", "-o", str(tmpzip), url])
    if rc != 0:
        print(f"[✗] {tr('Download failed:')} {url}")
        tmpzip.unlink(missing_ok=True)
        return 1

    print(f"  {tr('Verifying sha256...')}")
    got = hashlib.sha256(tmpzip.read_bytes()).hexdigest()
    if sha and got != sha:
        print(f"[✗] {tr('sha256 verification failed:')} {got}")
        tmpzip.unlink(missing_ok=True)
        return 1

    print(f"  {tr('Extracting to project root...')}")
    rc = subprocess.call(["unzip", "-q", "-o", str(tmpzip), "-d", str(root)])
    tmpzip.unlink(missing_ok=True)
    if rc != 0:
        print(f"[✗] {tr('Extraction failed')}")
        return 1

    if p.is_dir():
        print(f"[✓] {label}{tr(' ready:')} {dirname}/")
        return 0
    print(f"[!] {tr('Extracted but')} {dirname}/ {tr('not found, please check')}")
    return 1


def _download_menu(root: Path, fetcher, title_tpl: str, label: str, dirname: str,
                   entries: list[str]) -> int:
    while True:
        os.system("clear")
        print("=" * 40)
        print(f"     {title_tpl}")
        print("=" * 40)
        print(f"  0) {tr('Back')}")
        for i, entry in enumerate(entries, 1):
            print(f"  {i}) {entry.split('|', 1)[0]}")
        last = len(entries) + 1
        print(f"  {last}) {tr('Enter URL manually')}")
        print("=" * 40)
        choice = input(f"{tr('Choose')} [0-{last}]: ").strip()
        if choice == "0":
            return 0
        if choice.isdigit():
            idx = int(choice)
            if idx == last:
                manual_url = input(f"  {tr('Enter zip download URL:')} ").strip()
                manual_sha = input(f"  {tr('Enter expected sha256 (blank to skip):')} ").strip()
                if not manual_url:
                    print(f"  {tr('Invalid URL')}")
                    import time; time.sleep(1)
                    continue
                fetcher(root, tr("Custom"), manual_url, manual_sha, dirname, label)
            elif 1 <= idx <= len(entries):
                desc, url, sha = entries[idx - 1].split("|")
                fetcher(root, desc, url, sha, dirname, label)
            else:
                print(f"  {tr('Invalid option')}")
                import time; time.sleep(1)
                continue
        else:
            print(f"  {tr('Invalid option')}")
            import time; time.sleep(1)
            continue
        print()
        press_enter()

