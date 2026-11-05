#!/usr/bin/env python3
"""Pack registered BGM/SND/VC/FMP assets into AUDIO.DAT (devdocs 101/123).

Reads ASSETS.DB img_map rows with type BGM / SND / VC / FMP and writes a
single AUDIO.DAT archive using the same TOC layout as IMAGE.DAT / SCENE.DAT
(shared writer: tools/naiz_lib/toc_archive.py).

FMP rows — YM2608 FM patches (devdoc 123 S3) — are compiled from their text
form at pack time by tools/naiz_audio/fm_patch.py into a 32-byte binary,
so authors edit text and the binary layout stays a build artifact.

TOC entry name = the asset `name` column (the script key), must satisfy
DOS 8.3 and be unique after `to_dos_name()` (same hard rule as SCENE.DAT,
R25).  Missing source files are fatal — an archive entry whose payload is
missing would fail at runtime silently.

Source payloads are read from assets/<project>/ (naiz_lib.project_assets_dir),
the same root as the images.map PNG sources and the anim/ frame material;
the `filename` column is relative to it, not to the project directory.
Only the packed AUDIO.DAT reaches games/<game>/ — audio sources are never
copied or injected as loose files, so they carry no DOS 8.3 obligation
(only the TOC entry `name` does, checked below).

Usage:
    pack_audio.py <project_dir> <out_dir> [assets_dir]
"""

import os
import sqlite3
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from naiz_lib import project_assets_dir, to_dos_name  # noqa: E402
from naiz_lib.toc_archive import make_toc_archive  # noqa: E402
from naiz_audio import fm_patch  # noqa: E402

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


def pack_audio(project_dir, out_dir, assets_dir=None):
    db_path = os.path.join(project_dir, 'ASSETS.DB')
    if not os.path.isfile(db_path):
        print("pack_audio: no ASSETS.DB, skipping")
        return

    if assets_dir is None:
        assets_dir = project_assets_dir(project_dir)

    db = sqlite3.connect(db_path)
    try:
        rows = db.execute(
            "SELECT id, filename, type, name FROM img_map "
            "WHERE type IN ('BGM','SND','VC','FMP') ORDER BY id"
        ).fetchall()
    finally:
        db.close()

    if not rows:
        print("pack_audio: no BGM/SND/VC/FMP assets registered, skipping")
        return

    print(f"  audio sources: {assets_dir}")

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

        path = os.path.join(assets_dir, filename)
        if not os.path.isfile(path):
            print(f"ERROR: audio asset file missing: {path}")
            print(f"  BGM/SND/VC/FMP sources live under {assets_dir}; "
                  "the img_map.filename column is relative to it.")
            sys.exit(1)
        if asset_type == 'FMP':
            try:
                data = fm_patch.compile_source(path)
            except fm_patch._PatchError as e:
                print(f"ERROR: {path}:\n  {e}")
                sys.exit(1)
            if len(data) != 32:
                print(f"ERROR: {filename}: compiled {len(data)} bytes, "
                      "FMP patches are exactly 32 bytes")
                sys.exit(1)
        else:
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
        print("Usage: pack_audio.py <project_dir> <out_dir> [assets_dir]")
        sys.exit(1)
    pack_audio(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)