"""ANI bypass in the packing pipeline (devdoc 80 §4.3).

Covers: .ANI rows never decoded / packed verbatim into the TOC /
IMAGE.DAT verification skips non-MAG entries / shared-palette baseline
probe ignores an ANI entry sitting at id=0.
"""

import os
import sqlite3
import struct

from naiz_lib import image_dat
from naiz_lib import mag_codec
from naiz_build import pack_images


# ---------------------------------------------------------------------------
# Fixture builders (mirrors test_image_dat.py style)
# ---------------------------------------------------------------------------

def _build_image_dat(entries):
    count = len(entries)
    header_size = image_dat.IMAGE_DAT_HEADER + count * image_dat.IMAGE_DAT_TOC_SIZE
    buf = bytearray(struct.pack('<I', count))
    offset = header_size
    for name, data in entries:
        buf.extend(name.ljust(12, b'\0'))
        buf.extend(struct.pack('<II', offset, len(data)))
        offset += len(data)
    for _, data in entries:
        buf.extend(data)
    return bytes(buf)


def _shared_256_palette():
    pal = [(0, 0, 0)] * 256
    pal[7] = (255, 255, 255)
    pal[15] = (255, 255, 255)
    return pal


def _mag_bytes():
    return mag_codec.encode_mag(bytes(4), 2, 2, _shared_256_palette(), bpp=8)


_ANI_BYTES = b"ANIZ" + bytes(range(1, 40))  # arbitrary opaque container body


def _make_project(tmp_path, rows):
    """rows: list of (filename, type). Writes ASSETS.DB + asset files."""
    db_path = tmp_path / "ASSETS.DB"
    db = sqlite3.connect(str(db_path))
    db.execute("CREATE TABLE img_map (id INTEGER PRIMARY KEY, name TEXT, "
               "filename TEXT, type TEXT)")
    for i, (fn, typ) in enumerate(rows):
        db.execute("INSERT INTO img_map (id, name, filename, type) VALUES (?,?,?,?)",
                   (i, "asset%d" % i, fn, typ))
        target = tmp_path / fn
        target.parent.mkdir(parents=True, exist_ok=True)
        if typ == "IMG":
            target.write_bytes(_mag_bytes())
        else:
            target.write_bytes(_ANI_BYTES)
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# verify_shared_palette / first_mag_palette
# ---------------------------------------------------------------------------

def test_verify_shared_palette_skips_ani_entries():
    mag = _mag_bytes()
    img = _build_image_dat([(b"A.MAG", mag), (b"TESTFULL.AN", _ANI_BYTES)])
    assert image_dat.verify_shared_palette(img) == []

    # ANI first must not become the baseline nor raise errors
    img2 = _build_image_dat([(b"TESTCINE.AN", _ANI_BYTES), (b"A.MAG", mag),
                             (b"B.MAG", mag)])
    assert image_dat.verify_shared_palette(img2) == []


def test_first_mag_palette_skips_ani_at_id0():
    mag = _mag_bytes()
    expected = mag_codec.decode_mag_palette(mag)

    img = _build_image_dat([(b"TESTFULL.AN", _ANI_BYTES), (b"A.MAG", mag)])
    assert image_dat.first_mag_palette(img) == expected

    # Pure-ANI archive has no MAG baseline at all
    img2 = _build_image_dat([(b"TESTCINE.AN", _ANI_BYTES)])
    assert image_dat.first_mag_palette(img2) is None


# ---------------------------------------------------------------------------
# load_img_map_assets / pack_images bypass
# ---------------------------------------------------------------------------

def test_load_img_map_assets_ani_row_never_decodes(tmp_path, capsys):
    _make_project(tmp_path, [("ani/TESTFULL.ANI", "ANI")])
    data = pack_images.load_img_map_assets(str(tmp_path))
    out = capsys.readouterr().out
    assert len(data) == 1
    id_val, filename, asset_type, raw, result = data[0]
    assert asset_type == "ANI"
    assert raw == _ANI_BYTES          # verbatim bytes kept for TOC packing
    assert result is None             # no decode attempted...
    assert "WARN" not in out          # ...and therefore no decode warning


def test_pack_images_ani_row_verbatim_into_toc(tmp_path, capsys):
    _make_project(tmp_path, [("ani/TESTFULL.ANI", "ANI")])
    pack_images.pack_images(str(tmp_path))
    out = capsys.readouterr().out

    imgdat = (tmp_path / "IMAGE.DAT").read_bytes()
    toc = list(image_dat.iter_image_dat_toc(imgdat))
    assert len(toc) == 1
    _i, _name, eoff, esz = toc[0]
    assert esz == len(_ANI_BYTES)
    assert imgdat[eoff:eoff + esz] == _ANI_BYTES

    # Post-pack palette verification must pass on an ANI-only archive
    assert "verification OK" in out
