"""Guard the openpack AUTOEXEC load-address pad line (devdoc 212).

`REM naiz ae pad` has no semantic effect: it only shifts where DOS loads
ENGINE.EXE, which is the difference between booting and dying with DOS/32A
fatal 4005 (devdoc 212 §六).  Its byte count is part of the address
calculation, so accidentally deleting or rewording it must fail loudly --
without these tests nothing in the suite reads this line at all.
"""

from tools.naiz_img.inject_common import generate_autoexec

PAD = b"REM naiz ae pad\r\n"


def _autoexec(monkeypatch, pack=None, extender=None, ae_pad=None):
    """Call generate_autoexec() with a clean, explicit chain environment."""
    for key in ("NAIZ_PACK", "NAIZ_EXTENDER", "NAIZ_AE_PAD"):
        monkeypatch.delenv(key, raising=False)
    if pack is not None:
        monkeypatch.setenv("NAIZ_PACK", pack)
    if extender is not None:
        monkeypatch.setenv("NAIZ_EXTENDER", extender)
    if ae_pad is not None:
        monkeypatch.setenv("NAIZ_AE_PAD", str(ae_pad))
    return generate_autoexec("demo-a2", b"CTMOUSE.COM")


def test_openpack_autoexec_contains_pad_17_bytes(monkeypatch):
    """openpack (DOS/32A) must carry the pad; its length is load-bearing."""
    content = _autoexec(monkeypatch, pack="openpack")
    assert len(PAD) == 17, "pad length changed -- load address moves with it"
    assert PAD in content
    assert content.endswith(b"engine.exe\r\n")


def test_pad_sits_between_dos16m_and_engine(monkeypatch):
    """Order is part of the contract: SET DOS16M=1 -> pad -> engine.exe."""
    content = _autoexec(monkeypatch, pack="openpack")
    dos16m = content.index(b"SET DOS16M=1\r\n")
    pad = content.index(PAD)
    engine = content.index(b"engine.exe\r\n")
    assert dos16m < pad < engine


def test_dos4g_autoexec_has_no_pad(monkeypatch):
    """The commercial DOS/4GW chain must stay byte-identical to before."""
    content = _autoexec(monkeypatch, pack="cmpack", extender="dos4g")
    assert PAD not in content
    assert b"SET DOS16M=1\r\n" in content  # DOS/4GW still needs the switch


def test_extender_env_alone_selects_pad(monkeypatch):
    """Manual inject sets NAIZ_EXTENDER without NAIZ_PACK (devdoc 210 §11.4)."""
    content = _autoexec(monkeypatch, extender="dos32a")
    assert PAD in content


def test_diagnostic_pad_stacks_after_production_pad(monkeypatch):
    """NAIZ_AE_PAD offsets the production pad instead of replacing it."""
    content = _autoexec(monkeypatch, pack="openpack", ae_pad=1)
    assert content.count(PAD) == 1
    assert content.index(PAD) < content.index(b"REM .\r\n")
    assert content.endswith(b"engine.exe\r\n")
