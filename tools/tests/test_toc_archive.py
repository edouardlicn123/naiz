"""TOC archive writer (make_toc_archive) + scene packer (pack_scenes).

Locks the shared archive layout (uint32 count + 20 B/entry TOC + blobs) for
IMAGE.DAT and SCENE.DAT, guards the pack_images refactor against byte-level
regression, and exercises the pack_scenes 8.3-collision / empty-file / size
rules that protect SCENE.DAT from the R25 truncation clash.
"""

import struct

import pytest

from naiz_lib import image_dat
from naiz_lib.toc_archive import make_toc_archive


def _legacy_writer(toc):
    """Historical IMAGE.DAT writer (pre-refactor inline loop), verbatim."""
    header_size = 4 + len(toc) * 20
    buf = bytearray()
    buf.extend(struct.pack('<I', len(toc)))
    offset = header_size
    for name, data in toc:
        buf.extend(name)
        buf.extend(struct.pack('<II', offset, len(data)))
        offset += len(data)
    for _, data in toc:
        buf.extend(data)
    return bytes(buf)


# ---------------------------------------------------------------------------
# make_toc_archive
# ---------------------------------------------------------------------------

def test_make_toc_archive_byte_vector():
    out = make_toc_archive([(b"A", b"hello"), (b"BIGNAME12", b"xy")])
    count = struct.unpack('<I', out[0:4])[0]
    assert count == 2
    # header_size = 4 + 2*20 = 44; offsets absolute
    assert struct.unpack_from('<I', out, 4 + 12)[0] == 44
    assert struct.unpack_from('<I', out, 4 + 12 + 4)[0] == 5
    assert struct.unpack_from('<I', out, 4 + 20 + 12)[0] == 49
    assert struct.unpack_from('<I', out, 4 + 20 + 12 + 4)[0] == 2
    assert out[44:49] == b"hello"
    assert out[49:51] == b"xy"


def test_make_toc_archive_pads_names_and_roundtrips():
    out = make_toc_archive([(b"LOGO", b"abc"), (b"P", b"")])  # empty = hole
    toc = list(image_dat.iter_image_dat_toc(out))
    assert len(toc) == 2
    assert toc[0][1] == b"LOGO" + b"\x00" * 8
    assert toc[1][1] == b"P" + b"\x00" * 11
    assert toc[1][3] == 0
    assert out[toc[0][2]:toc[0][2] + toc[0][3]] == b"abc"


def test_make_toc_archive_accepts_str_names():
    out = make_toc_archive([("NBOOK001.NB", b"x" * 7)])
    toc = list(image_dat.iter_image_dat_toc(out))
    assert toc[0][1] == b"NBOOK001" + b".NB" + b"\x00"


def test_make_toc_archive_rejects_long_name():
    with pytest.raises(ValueError, match="too long"):
        make_toc_archive([(b"1234567890123", b"data")])


def test_make_toc_archive_empty():
    out = make_toc_archive([])
    assert out == b"\x00\x00\x00\x00"
    assert list(image_dat.iter_image_dat_toc(out)) == []


def test_make_toc_archive_byte_identical_to_legacy_writer():
    toc = [
        (b"A.DAT" + b"\x00" * 7, b"0123456789"),
        (b"B.DAT" + b"\x00" * 7, b"xyz"),
        (b"\x00" * 12, b""),                       # sparse hole
    ]
    assert make_toc_archive(toc) == _legacy_writer(toc)


# ---------------------------------------------------------------------------
# pack_scenes
# ---------------------------------------------------------------------------

@pytest.fixture
def _scene_proj(tmp_path):
    proj = tmp_path / "proj"
    scene = proj / "scene"
    scene.mkdir(parents=True)
    return proj, scene


def test_pack_scenes_basic_skips_empty(_scene_proj, tmp_path):
    from naiz_build import build_game

    proj, scene = _scene_proj
    (scene / "logo.nb").write_bytes(b"line1\nline2\n")
    (scene / "nbook001.nb").write_bytes(b"scene\n")
    (scene / "empty.nb").write_bytes(b"")  # 0-byte residue, skipped

    game = tmp_path / "game"
    game.mkdir()
    build_game.pack_scenes(proj, game)

    payload = (game / "SCENE.DAT").read_bytes()
    toc = list(image_dat.iter_image_dat_toc(payload))
    names = {t[1].rstrip(b"\0").decode(): t[3] for t in toc}
    assert names == {"LOGO.NB": 12, "NBOOK001.NB": 6}
    assert game.joinpath("empty.nb").exists() is False  # never deployed


def test_pack_scenes_8_3_collision_raises(_scene_proj, tmp_path):
    from naiz_build import build_game

    proj, scene = _scene_proj
    (scene / "nbook001.nb").write_bytes(b"a\n")
    (scene / "nbook0012.nb").write_bytes(b"b\n")  # base truncates to NBOOK001

    game = tmp_path / "game"
    game.mkdir()
    with pytest.raises(RuntimeError, match="collision after 8.3 truncation"):
        build_game.pack_scenes(proj, game)


def test_pack_scenes_normalizes_crlf(_scene_proj, tmp_path):
    from naiz_build import build_game

    proj, scene = _scene_proj
    (scene / "logo.nb").write_bytes(b"line1\r\nline2\r\nline3")

    game = tmp_path / "game"
    game.mkdir()
    build_game.pack_scenes(proj, game)

    payload = (game / "SCENE.DAT").read_bytes()
    payloads = {n.rstrip(b"\0"): payload[o:o + s]
                for _, n, o, s in image_dat.iter_image_dat_toc(payload)}
    assert payloads[b"LOGO.NB"] == b"line1\nline2\nline3"


def test_pack_scenes_over_32k_raises(_scene_proj, tmp_path):
    from naiz_build import build_game

    proj, scene = _scene_proj
    (scene / "big.nb").write_bytes(b"x" * 32768)  # >= NB_BUF_SIZE

    game = tmp_path / "game"
    game.mkdir()
    with pytest.raises(RuntimeError, match="32 KiB"):
        build_game.pack_scenes(proj, game)


def test_pack_scenes_incremental_skips_rewrite(_scene_proj, tmp_path):
    from naiz_build import build_game

    proj, scene = _scene_proj
    (scene / "logo.nb").write_bytes(b"hello\n")

    game = tmp_path / "game"
    game.mkdir()
    build_game.pack_scenes(proj, game)
    out = game / "SCENE.DAT"
    mtime_first = out.stat().st_mtime_ns
    build_game.pack_scenes(proj, game)
    assert out.stat().st_mtime_ns == mtime_first  # unchanged payload untouched


# ---------------------------------------------------------------------------
# _prune_stale_scenes
# ---------------------------------------------------------------------------

def test_prune_stale_scenes_removes_legacy_empties(tmp_path):
    from naiz_build import build_game

    scene = tmp_path / "scene"
    scene.mkdir()
    (scene / "logo.nb").write_bytes(b"a\n")
    (scene / "nbook001.nb").write_bytes(b"b\n")

    game = tmp_path / "game"
    game.mkdir()
    for name in ("logo.nb", "nbook001.nb", "nbook005.nb", "nopbook.nb"):
        (game / name).write_bytes(b"")

    build_game._prune_stale_scenes(game, {"logo.nb", "nbook001.nb"})
    remaining = sorted(p.name for p in game.glob("*.nb"))
    assert remaining == ["logo.nb", "nbook001.nb"]


def test_prune_stale_scenes_keeps_every_deployed(tmp_path):
    from naiz_build import build_game

    game = tmp_path / "game"
    game.mkdir()
    (game / "cgview.nb").write_bytes(b"x\n")
    build_game._prune_stale_scenes(game, {"cgview.nb", "not_yet.nb"})
    assert (game / "cgview.nb").exists()