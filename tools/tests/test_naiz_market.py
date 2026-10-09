"""Asset-market downloader tests (tools/naiz_market.market).

Covers the AGENTS.md §13 mandatory rules (pack = top-level dir, display-name
first-segment-paren rule, whole-pack download) plus download mechanics:
skip-existing (default) / force overwrite, atomic write, size validation,
path-boundary guard, LICENSE copy, dry-run, and the numeric-menu selection
parser. Also pins the interactive menu's one-shot screen clear (TTY-guarded,
not repeated per redraw) and the sync subcommand's git blob-sha diff
(add/update/unchanged, --purge prune scoped to synced pack dirs, --dry-run).
Network is fully monkeypatched; nothing touches the network or the filesystem
outside tmp_path.
"""

import pytest

from naiz_market import market
from naiz_market.market import Market, MarketError, parse_selection, safe_target

TREE = {
    "truncated": False,
    "tree": [
        {"path": "LICENSE", "type": "blob", "size": 1071,
         "sha": "4cadd774e3b512e4c010c60bf363026f3d191056"},
        {"path": "README.md", "type": "blob", "size": 57},
        {"path": "images_sample_scenebg", "type": "tree", "size": 0},
        {"path": "images_sample_scenebg/bg-city-day.jpg", "type": "blob",
         "size": 100, "sha": "d690765445339443e88fd770dad129c38e3521ff"},
        {"path": "images_sample_scenebg/bg-bridge.jpg", "type": "blob",
         "size": 200, "sha": "000f3af7b49d56e61f5c0ea6005d9a1c0c875228"},
        {"path": "images_sample_charactor_schoolgirl", "type": "tree", "size": 0},
        {"path": "images_sample_charactor_schoolgirl/mahoshojo.jpg",
         "type": "blob", "size": 300,
         "sha": "0d6506798e89ffc6c444fd7eae90859e224919a8"},
    ],
}


def _market(tmp_path, monkeypatch, **kwargs):
    monkeypatch.setattr(market, "_fetch_json", lambda url: TREE)
    monkeypatch.setattr(market, "_fetch_bytes", lambda url: b"x" * 1)

    def _bytes_for(url):
        if "LICENSE" in url:
            return b"y" * 1071
        if "bg-city-day.jpg" in url:
            return b"a" * 100
        if "bg-bridge.jpg" in url:
            return b"b" * 200
        if "mahoshojo.jpg" in url:
            return b"c" * 300
        return b"x" * 1

    monkeypatch.setattr(market, "_fetch_bytes", _bytes_for)
    opts = {"repo": "o/r", "ref": "main", "dest": str(tmp_path / "out")}
    opts.update(kwargs)
    return Market(**opts)


# ---------------------------------------------------------------------------
# Naming rules
# ---------------------------------------------------------------------------

def test_display_name_first_segment_paren():
    m = Market("o/r", "main", "assets")
    assert m.display_name("images_sample_scenebg") == "(images)sample scenebg"
    assert m.display_name("images_sample_charactor_schoolgirl") == \
        "(images)sample charactor schoolgirl"
    assert m.display_name("plain") == "plain"


def test_common_prefix_and_kinds():
    m = Market("o/r", "main", "assets")
    dirs = ["images_sample_scenebg", "images_sample_charactor_schoolgirl"]
    assert m.common_prefix(dirs) == "images_sample_"
    kinds = m.kinds(dirs)
    assert kinds["images_sample_scenebg"] == "scenebg"
    assert kinds["images_sample_charactor_schoolgirl"] == "charactor_schoolgirl"


def test_single_pack_falls_back_to_full_name():
    m = Market("o/r", "main", "assets")
    assert m.common_prefix(["images_sample_scenebg"]) == "images_sample_scenebg"
    assert m.kinds(["images_sample_scenebg"]) == {
        "images_sample_scenebg": "images_sample_scenebg"}


# ---------------------------------------------------------------------------
# Pack model
# ---------------------------------------------------------------------------

def test_packs_skip_root_files(tmp_path, monkeypatch):
    m = _market(tmp_path, monkeypatch)
    packs = m.packs()
    assert set(packs) == {"images_sample_scenebg",
                          "images_sample_charactor_schoolgirl"}
    assert [p for p, _ in packs["images_sample_scenebg"]] == \
        ["images_sample_scenebg/bg-bridge.jpg",
         "images_sample_scenebg/bg-city-day.jpg"]


def test_resolve_pack_exact_dir_then_kind(tmp_path, monkeypatch):
    m = _market(tmp_path, monkeypatch)
    packs = m.packs()
    directory, files = m.resolve_pack("images_sample_scenebg", packs)
    assert directory == "images_sample_scenebg"
    directory, _ = m.resolve_pack("scenebg", packs)
    assert directory == "images_sample_scenebg"
    directory, _ = m.resolve_pack("charactor_schoolgirl", packs)
    assert directory == "images_sample_charactor_schoolgirl"


def test_resolve_pack_unknown_raises(tmp_path, monkeypatch):
    m = _market(tmp_path, monkeypatch)
    packs = m.packs()
    with pytest.raises(MarketError):
        m.resolve_pack("nope", packs)


# ---------------------------------------------------------------------------
# Download mechanics
# ---------------------------------------------------------------------------

def test_download_pack_writes_under_dest(tmp_path, monkeypatch):
    m = _market(tmp_path, monkeypatch)
    files = m.packs()["images_sample_scenebg"]
    m.download_pack("images_sample_scenebg", files)
    out = tmp_path / "out"
    assert (out / "images_sample_scenebg/bg-city-day.jpg").read_bytes() == b"a" * 100
    assert (out / "images_sample_scenebg/bg-bridge.jpg").read_bytes() == b"b" * 200
    assert not list(out.rglob("*.part"))


def test_download_skips_existing(tmp_path, monkeypatch, capsys):
    m = _market(tmp_path, monkeypatch)
    target = tmp_path / "out/images_sample_scenebg/bg-city-day.jpg"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"stale")
    m.download_pack("images_sample_scenebg",
                    m.packs()["images_sample_scenebg"])
    assert target.read_bytes() == b"stale"          # untouched, not re-downloaded
    assert not list((tmp_path / "out").rglob("*.part"))
    assert "SKIP (exists)" in capsys.readouterr().out


def test_download_force_overwrites(tmp_path, monkeypatch):
    m = _market(tmp_path, monkeypatch, force=True)
    target = tmp_path / "out/images_sample_scenebg/bg-city-day.jpg"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"stale")
    m.download_pack("images_sample_scenebg",
                    m.packs()["images_sample_scenebg"])
    assert target.read_bytes() == b"a" * 100


def test_size_mismatch_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(market, "_fetch_json", lambda url: TREE)
    monkeypatch.setattr(market, "_fetch_bytes",
                        lambda url: b"short")
    m = Market("o/r", "main", str(tmp_path / "out"))
    files = m.packs()["images_sample_scenebg"]
    with pytest.raises(MarketError):
        m.download_pack("images_sample_scenebg", files)


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    m = _market(tmp_path, monkeypatch, dry_run=True)
    files = m.packs()["images_sample_scenebg"]
    m.download_pack("images_sample_scenebg", files)
    out = tmp_path / "out"
    assert not out.exists() or not list(out.rglob("*"))


def test_license_skipped_when_present(tmp_path, monkeypatch, capsys):
    m = _market(tmp_path, monkeypatch)
    out = tmp_path / "out"
    out.mkdir(parents=True)
    license_f = out / "LICENSE"
    license_f.write_bytes(b"existing")
    m.download_packs(["images_sample_scenebg"])
    assert license_f.read_bytes() == b"existing"
    assert "SKIP (exists)" in capsys.readouterr().out


def test_license_copied_to_dest_root(tmp_path, monkeypatch):
    m = _market(tmp_path, monkeypatch)
    m.download_packs(["images_sample_scenebg"])
    out = tmp_path / "out"
    assert (out / "LICENSE").read_bytes() == b"y" * 1071


def test_download_packs_summary(tmp_path, monkeypatch, capsys):
    m = _market(tmp_path, monkeypatch)
    m.download_packs(["images_sample_scenebg",
                      "images_sample_charactor_schoolgirl"])
    captured = capsys.readouterr().out
    assert "2 packs" in captured
    assert "4 files" in captured


# ---------------------------------------------------------------------------
# Sync (git blob-sha diff)
# ---------------------------------------------------------------------------

def test_git_blob_sha_matches_git_object_id():
    assert market._git_blob_sha(b"abc") == \
        "f2ba8f84ab5c1bce84a7b441cb1959cfc7093b7f"


def test_packs_detailed_carries_blob_sha(tmp_path, monkeypatch):
    m = _market(tmp_path, monkeypatch)
    entries = m.packs_detailed()["images_sample_scenebg"]
    byname = {path: sha for path, _, sha in entries}
    assert byname["images_sample_scenebg/bg-city-day.jpg"] == \
        "d690765445339443e88fd770dad129c38e3521ff"


def test_sync_adds_missing_files(tmp_path, monkeypatch):
    m = _market(tmp_path, monkeypatch)
    m.sync_packs(["images_sample_scenebg"])
    out = tmp_path / "out"
    assert (out / "images_sample_scenebg/bg-city-day.jpg").read_bytes() == \
        b"a" * 100
    assert (out / "images_sample_scenebg/bg-bridge.jpg").read_bytes() == \
        b"b" * 200
    assert not list(out.rglob("*.part"))
    assert (out / "LICENSE").read_bytes() == b"y" * 1071


def test_sync_keeps_unchanged(tmp_path, monkeypatch, capsys):
    m = _market(tmp_path, monkeypatch)
    target = tmp_path / "out/images_sample_scenebg/bg-city-day.jpg"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"a" * 100)
    m.sync_packs(["images_sample_scenebg"])
    captured = capsys.readouterr().out
    assert target.read_bytes() == b"a" * 100
    assert "OK (unchanged)" in captured
    assert "ADDED" in captured          # bg-bridge.jpg still missing


def test_sync_updates_changed_content(tmp_path, monkeypatch, capsys):
    m = _market(tmp_path, monkeypatch)
    target = tmp_path / "out/images_sample_scenebg/bg-city-day.jpg"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"z" * 100)      # same size, different content
    m.sync_packs(["images_sample_scenebg"])
    assert target.read_bytes() == b"a" * 100
    assert "UPDATED" in capsys.readouterr().out


def test_sync_updates_size_change(tmp_path, monkeypatch, capsys):
    m = _market(tmp_path, monkeypatch)
    target = tmp_path / "out/images_sample_scenebg/bg-city-day.jpg"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"short")
    m.sync_packs(["images_sample_scenebg"])
    assert target.read_bytes() == b"a" * 100
    assert "UPDATED" in capsys.readouterr().out


def test_sync_dry_run_writes_nothing(tmp_path, monkeypatch, capsys):
    m = _market(tmp_path, monkeypatch, dry_run=True)
    m.sync_packs(["images_sample_scenebg"])
    out = tmp_path / "out"
    assert not out.exists() or not list(out.rglob("*"))
    assert "ADDED (dry-run)" in capsys.readouterr().out


def test_sync_unknown_pack_raises(tmp_path, monkeypatch):
    m = _market(tmp_path, monkeypatch)
    with pytest.raises(MarketError):
        m.sync_packs(["nope"])


def test_sync_stale_kept_without_purge(tmp_path, monkeypatch, capsys):
    m = _market(tmp_path, monkeypatch)
    ghost = tmp_path / "out/images_sample_scenebg/old-scrap.jpg"
    ghost.parent.mkdir(parents=True)
    ghost.write_bytes(b"old")
    m.sync_packs(["images_sample_scenebg"])
    captured = capsys.readouterr().out
    assert ghost.read_bytes() == b"old"
    assert "STALE" in captured
    assert "use --purge" in captured


def test_sync_purge_removes_stale(tmp_path, monkeypatch, capsys):
    m = _market(tmp_path, monkeypatch)
    ghost = tmp_path / "out/images_sample_scenebg/old-scrap.jpg"
    ghost.parent.mkdir(parents=True)
    ghost.write_bytes(b"old")
    m.sync_packs(["images_sample_scenebg"], purge=True)
    assert not ghost.exists()
    assert "PRUNE" in capsys.readouterr().out


def test_sync_purge_scoped_to_synced_pack(tmp_path, monkeypatch):
    m = _market(tmp_path, monkeypatch)
    out = tmp_path / "out"
    readme = out / "README.md"
    readme.parent.mkdir(parents=True)
    readme.write_bytes(b"keep")
    other = out / "images_sample_charactor_schoolgirl"
    other.mkdir(parents=True)
    orphan = other / "stray.jpg"
    orphan.write_bytes(b"keep")
    m.sync_packs(["images_sample_scenebg"], purge=True)
    assert readme.read_bytes() == b"keep"      # root files untouched
    assert orphan.read_bytes() == b"keep"      # other pack dirs untouched


def test_sync_all_packs_default(tmp_path, monkeypatch, capsys):
    m = _market(tmp_path, monkeypatch)
    m.sync_packs(list(m.packs()))
    captured = capsys.readouterr().out
    assert "2 packs" in captured
    out = tmp_path / "out"
    assert (out / "images_sample_scenebg/bg-city-day.jpg").exists()
    assert (out / "images_sample_charactor_schoolgirl/mahoshojo.jpg").exists()
    assert (out / "LICENSE").exists()


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

def test_safe_target_rejects_traversal(tmp_path):
    dest = tmp_path / "dest"
    with pytest.raises(MarketError):
        safe_target(dest, "../evil.png")
    with pytest.raises(MarketError):
        safe_target(dest, "/etc/passwd")
    with pytest.raises(MarketError):
        safe_target(dest, "images_sample_scenebg/../../evil.png")


def test_safe_target_accepts_nested_under_dest(tmp_path):
    dest = tmp_path / "dest"
    target = safe_target(dest, "images_sample_scenebg/bg-city-day.jpg")
    assert target.parent.name == "images_sample_scenebg"


# ---------------------------------------------------------------------------
# Menu selection parser
# ---------------------------------------------------------------------------

def test_parse_selection_syntax():
    assert parse_selection("2", 5) == [2]
    assert parse_selection("1 2", 5) == [1, 2]
    assert parse_selection("1-3", 5) == [1, 2, 3]
    assert parse_selection("1,3 2", 5) == [1, 2, 3]


def test_parse_selection_rejects_bad_input():
    with pytest.raises(ValueError):
        parse_selection("6", 5)
    with pytest.raises(ValueError):
        parse_selection("0", 5)
    with pytest.raises(ValueError):
        parse_selection("x", 5)
    with pytest.raises(ValueError):
        parse_selection("a-b", 5)
    with pytest.raises(ValueError):
        parse_selection("2-1", 5)


# ---------------------------------------------------------------------------
# Screen clear
# ---------------------------------------------------------------------------

class _FakeTTY:
    """Minimal stdout stand-in exposing only what clear_screen() touches."""

    def __init__(self, tty):
        self.tty = tty
        self.written = ""

    def isatty(self):
        return self.tty

    def write(self, text):
        self.written += text

    def flush(self):
        pass


def test_clear_screen_emits_ansi_on_tty(monkeypatch):
    fake = _FakeTTY(True)
    monkeypatch.setattr(market.sys, "stdout", fake)
    market.clear_screen()
    assert fake.written == market.CLEAR_SCREEN


def test_clear_screen_skipped_when_not_tty(monkeypatch):
    fake = _FakeTTY(False)
    monkeypatch.setattr(market.sys, "stdout", fake)
    market.clear_screen()
    assert fake.written == ""


def test_clear_screen_skipped_on_dumb_terminal(monkeypatch):
    fake = _FakeTTY(True)
    monkeypatch.setattr(market.sys, "stdout", fake)
    monkeypatch.setenv("TERM", "dumb")
    market.clear_screen()
    assert fake.written == ""


def test_menu_clears_screen_once_per_session(tmp_path, monkeypatch):
    m = _market(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(market, "clear_screen", lambda: calls.append(1))
    answers = iter(["1", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    m.menu()                              # downloads pack 1, then quits
    assert len(calls) == 1                # one clear, not one per redraw


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_load_config_requires_repo(tmp_path):
    from naiz_market.market import load_config

    class NS:
        repo = None
        ref = None
        dest = None
        config = str(tmp_path / "no-such-config.toml")

    with pytest.raises(MarketError):
        load_config(NS())