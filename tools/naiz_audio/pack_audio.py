#!/usr/bin/env python3
"""Pack registered BGM/SND/VC assets into AUDIO.DAT (devdoc 101).

Reads ASSETS.DB img_map rows with type BGM / SND / VC and writes a single
AUDIO.DAT archive using the same TOC layout as IMAGE.DAT / SCENE.DAT
(shared writer: tools/naiz_lib/toc_archive.py).

TOC entry name = the asset `name` column (the script key), must satisfy
DOS 8.3 and be unique after `to_dos_name()` (same hard rule as SCENE.DAT,
R25).  Missing source files are fatal — an archive entry whose payload is
missing would fail at runtime silently.

Usage:
    pack_audio.py <project_dir> <out_dir>
"""

import os
import sqlite3
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from naiz_lib import to_dos_name
from naiz_lib.toc_archive import make_toc_archive

# .pcm header validity check (magic + rate code range), mirrors the engine
# checks in core/engine/audio.c.
_PCM_MAGIC = b"NAIZPCM\x00"


def _validate_pcm(data, fname):
    if len(data) < 16:
        raise RuntimeError(f"{fname}: .pcm shorter than 16-byte header")
    if data[0:8] != _PCM_MAGIC:
        raise RuntimeError(f"{fname}: bad .pcm magic")
    rate = data[8]
    if rate > 7:
        raise RuntimeError(f"{fname}: .pcm rate code {rate} out of range")


def pack_audio(project_dir, out_dir):
    db_path = os.path.join(project_dir, 'ASSETS.DB')
    if not os.path.isfile(db_path):
        print("pack_audio: no ASSETS.DB, skipping")
        return

    db = sqlite3.connect(db_path)
    try:
        rows = db.execute(
            "SELECT id, filename, type, name FROM img_map "
            "WHERE type IN ('BGM','SND','VC') ORDER BY id"
        ).fetchall()
    finally:
        db.close()

    if not rows:
        print("pack_audio: no BGM/SND/VC assets registered, skipping")
        return

    entries = []
    seen = {}
    for _id, filename, asset_type, name in rows:
        if not name:
            print(f"ERROR: audio asset {filename} has no name column")
            sys.exit(1)
        # 8.3 short name is the TOC entry key; reject truncation collisons.
        ffn8, _ext3 = to_dos_name(name)
        short = ffn8.rstrip(b' ').decode('ascii', errors='replace')
        if not short:
            raise RuntimeError(f"audio asset {filename}: empty short name")
        if short in seen:
            raise RuntimeError(
                f"AUDIO.DAT name collision after 8.3 truncation: "
                f"{seen[short]} and {filename} both map to {short}")
        seen[short] = filename

        path = os.path.join(project_dir, filename)
        if not os.path.isfile(path):
            print(f"ERROR: audio asset file missing: {path}")
            sys.exit(1)
        data = Path(path).read_bytes()
        if asset_type != 'BGM':
            _validate_pcm(data, filename)
        entries.append((short, data))

    if not entries:
        return

    payload = make_toc_archive(entries)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "AUDIO.DAT"
    if out.exists() and out.read_bytes() == payload:
        print(f"  AUDIO.DAT 未变化（{len(entries)} assets）")
        return
    out.write_bytes(payload)
    print(f"  AUDIO.DAT: {len(payload)} bytes, {len(entries)} assets "
          f"→ {out}")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: pack_audio.py <project_dir> <out_dir>")
        sys.exit(1)
    pack_audio(sys.argv[1], sys.argv[2])