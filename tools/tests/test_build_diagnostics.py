"""Watcom diagnostics live in .err files, not on stdout.

`make -C core` prints the wcl386 command lines but NOT the diagnostics: a
warning lands in `core/<unit>.err`, named after the source file.  Grepping the
make output for "error|warning" therefore reports 0/0 on a build that just
emitted warnings -- the most expensive kind of false pass, because it certifies
the one thing the build was supposed to check.

Real instance (0.3.014): `engine/nb_mainmenu.c(113): Warning! W131: No
prototype found for function 'bootmenu_run'` was invisible to the stdout grep
and would have shipped.  The file had just been renamed from settings_menu.c
and the call site had lost its prototype.

Empirically wcl386 writes a .err file only when a unit has something to say,
so "no .err at all" is the clean state rather than a missing build.  These
tests therefore assert two things separately: no non-empty .err, and that the
binary is actually current (so the first assertion is not vacuous because
nothing was compiled).
"""

import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CORE = ROOT / "core"
ENGINE = CORE / "engine.exe"


def _err_files():
    return sorted(CORE.glob("*.err"))


def _newest_source_mtime():
    newest = 0.0
    newest_name = ""
    for pat in ("engine/*.c", "engine/*.h", "lib/*.c", "lib/*.h",
                "plat/*.c", "plat/*.h", "Makefile"):
        for path in CORE.glob(pat):
            if path.stat().st_mtime > newest:
                newest, newest_name = path.stat().st_mtime, path.name
    return newest, newest_name


def test_engine_binary_is_current():
    """Guards the guard: if nothing was compiled, the .err check below says
    nothing about the current sources.  `make` is incremental, so after a build
    engine.exe is at least as new as every translation unit input."""
    if not ENGINE.is_file():
        raise AssertionError(
            "core/engine.exe missing -- run `make -C core` before trusting "
            "the diagnostics check"
        )
    newest, newest_name = _newest_source_mtime()
    exe_mtime = ENGINE.stat().st_mtime
    assert exe_mtime >= newest, (
        f"engine.exe is older than {newest_name}: the build is stale, so "
        "core/*.err describes an earlier run and the diagnostics check is void"
    )


def test_build_emitted_no_watcom_diagnostics():
    noisy = {}
    for path in _err_files():
        text = io.open(path, encoding="utf-8", errors="replace").read()
        if text.strip():
            noisy[path.name] = text.strip()
    assert not noisy, (
        "Watcom diagnostics in core/*.err (invisible in make's stdout):\n"
        + "\n".join(f"  {name}: {body}" for name, body in sorted(noisy.items()))
    )
