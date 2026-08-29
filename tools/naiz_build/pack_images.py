#!/usr/bin/env python3
"""
IMAGE.DAT packer — reads ASSETS.DB, builds IMAGE.DAT archive.
Builds a shared 256-color palette from ALL images, then remaps every
image to it, so sprites and backgrounds share one true palette.
"""
import sqlite3, struct, sys, os, hashlib
from pathlib import Path
from functools import lru_cache

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from naiz_lib.mag_codec import encode_mag, decode_mag_full
from naiz_lib.mag_constants import MAG_SPRITE_MARKER, MAG_USER_TERM
from naiz_lib import PROTECTED_IDX_ALL
from naiz_lib.palette_utils import is_near_magenta, warm_skin_tone, nearest_color_index


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROTECTED_IDX = PROTECTED_IDX_ALL
"""Indices reserved by engine runtime: 7=text, 15=transparent, 248-255=menu."""

USABLE_COLORS = 256 - len(PROTECTED_IDX)  # 246


# ---------------------------------------------------------------------------
# Shared palette builder
# ---------------------------------------------------------------------------

def build_shared_palette(image_data):
    """Build a 256-color shared palette from all image pixel data.

    image_data: list of (id_val, filename, asset_type, raw_bytes, decoded_or_None)
                Must already be decoded.

    Returns list of 256 (r,g,b) tuples.  Protected indices are filled with
    white/black.  The remaining 246 slots are PIL median-cut quantized from
    all non-transparent pixels.
    """
    from PIL import Image

    all_rgb = bytearray()

    for _id_val, _fn, _typ, raw, result in image_data:
        if result is None:
            continue
        pixels, _w, _h, pal, _bpp, _is_spr = result
        for px in pixels:
            if px == 15:                       # skip transparent
                continue
            if px < len(pal):
                r, g, b = pal[px]
                if is_near_magenta(r, g, b):   # skip alpha-compositing artifacts
                    continue
                all_rgb.extend([r, g, b])

    # Fallback if no pixel data collected (all pixels were transparent/magenta).
    # All-black + white at indices 7 and 15 matches engine startup palette.
    # Not a bug: degenerate input produces a usable palette.
    if not all_rgb:
        pal = [(0, 0, 0)] * 256
        pal[7] = (255, 255, 255)
        pal[15] = (255, 255, 255)
        print("Shared palette: fallback (no pixel data)")
        return pal

    # PIL quantize: reduce all pixel colours to USABLE_COLORS
    num_pixels = len(all_rgb) // 3
    img = Image.frombuffer('RGB', (num_pixels, 1), bytes(all_rgb))
    quantized = img.quantize(colors=USABLE_COLORS)
    pal_data = list(quantized.getpalette()[:USABLE_COLORS * 3])
    # PIL may return fewer entries than requested when the source has fewer
    # distinct colours (degenerate low-colour images). Pad unused slots black.
    if len(pal_data) < USABLE_COLORS * 3:
        pal_data.extend([0] * (USABLE_COLORS * 3 - len(pal_data)))

    # Build 246-colour list
    palette_246 = [
        (pal_data[i * 3], pal_data[i * 3 + 1], pal_data[i * 3 + 2])
        for i in range(USABLE_COLORS)
    ]

    # Warm up skin-tone entries to compensate for NP2kai RGB565 display loss
    # (observed G/R increases ~6% through the pipeline)
    palette_246 = [warm_skin_tone(r, g, b) for (r, g, b) in palette_246]

    # Insert protected indices into 256-slot array
    shared = [None] * 256
    src = 0
    for dst in range(256):
        if dst == 7:
            shared[dst] = (255, 255, 255)
        elif dst == 15:
            shared[dst] = (255, 255, 255)
        elif 248 <= dst <= 255:
            shared[dst] = (0, 0, 0)
        else:
            shared[dst] = palette_246[src]
            src += 1

    print("Shared palette: 256 colours (246 quantised + 10 reserved)")
    return shared


# ---------------------------------------------------------------------------
# Palette remapping
# ---------------------------------------------------------------------------

def remap_pixels_to_palette(pixels, width, height, old_palette, master_palette,
                             transparent_idx=15, protected_indices=None):
    """Remap pixel bytes from old_palette to nearest color in master_palette.
    Preserves transparent_idx (keeps index 15 as transparent)."""

    @lru_cache(maxsize=65536)
    def _nearest(r, g, b):
        return nearest_color_index(master_palette, r, g, b)

    if protected_indices is None:
        protected_indices = set()

    # Build old_idx → new_idx mapping
    remap = [0] * len(old_palette)
    for old_idx in range(len(old_palette)):
        if old_idx == transparent_idx:
            remap[old_idx] = transparent_idx  # preserve
        else:
            r, g, b = old_palette[old_idx]
            if r == 255 and g == 255 and b == 255 and master_palette[7] == (255, 255, 255):
                remap[old_idx] = 7   # exact white stays engine-white (reserved idx 7)
                continue
            idx = _nearest(r, g, b)
            if idx in protected_indices:
                idx = nearest_color_index(master_palette, r, g, b,
                                          skip=protected_indices)
            remap[old_idx] = idx

    new_pixels = bytearray(width * height)
    for i in range(width * height):
        old = pixels[i]
        if old >= len(remap):
            new_pixels[i] = 0
        else:
            new_pixels[i] = remap[old]

    return bytes(new_pixels)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Post-build verification
# ---------------------------------------------------------------------------

def verify_shared_palette(out_path):
    """Re-read just-written IMAGE.DAT and verify all MAG entries share
    an identical 256-colour palette with correct protected indices."""
    from naiz_lib.image_dat import verify_shared_palette_file
    if not os.path.isfile(out_path):
        print("  IMAGE.DAT palette verification: file missing, skipped")
        return
    if verify_shared_palette_file(out_path):
        sys.exit(1)


# ---------------------------------------------------------------------------
# Asset loading
# ---------------------------------------------------------------------------

def load_img_map_assets(project_dir, types=None):
    """Read ASSETS.DB img_map rows, load each file and decode its MAG.

    types: optional iterable filter (e.g. ('IMG', 'SPR')); None = all rows.
    Requires ASSETS.DB to exist.  Missing asset files are fatal.
    MAGs that fail to decode degrade to result=None with a WARN line:
    they contribute no palette pixels but are still packed as-is.

    Returns [(id_val, filename, asset_type, raw_bytes, decoded_or_None)]
    ordered by id — the tuple shape consumed by build_shared_palette().
    """
    db_path = os.path.join(project_dir, 'ASSETS.DB')
    if not os.path.isfile(db_path):
        print(f"ERROR: ASSETS.DB not found: {db_path}")
        sys.exit(1)
    query = 'SELECT id, filename, type FROM img_map'
    params = ()
    if types is not None:
        query += ' WHERE type IN (%s)' % ','.join('?' * len(types))
        params = tuple(types)
    query += ' ORDER BY id'
    db = sqlite3.connect(db_path)
    rows = db.execute(query, params).fetchall()
    db.close()

    image_data = []  # (id, filename, type, raw_bytes, decoded_or_None)
    for id_val, filename, asset_type in rows:
        path = os.path.join(project_dir, filename)
        if not os.path.isfile(path):
            print(f"ERROR: file not found: {path}")
            sys.exit(1)
        with open(path, 'rb') as f:
            raw = f.read()
        if asset_type == 'ANI':
            # .ANI containers are opaque payloads: never decode, never
            # contribute palette pixels; packed verbatim into the TOC.
            image_data.append((id_val, filename, asset_type, raw, None))
            continue
        result = None
        try:
            result = decode_mag_full(raw)
        except Exception as e:
            print(f"WARN: [{id_val}] {filename}: decode failed ({e})")
        image_data.append((id_val, filename, asset_type, raw, result))
    return image_data


def pack_images(project_dir):
    db_path = os.path.join(project_dir, 'ASSETS.DB')
    if not os.path.isfile(db_path):
        print(f"ASSETS.DB not found in {project_dir}, creating empty IMAGE.DAT")
        out_path = os.path.join(project_dir, 'IMAGE.DAT')
        Path(out_path).write_bytes(struct.pack('<I', 0))
        print(f"  Wrote empty IMAGE.DAT ({4} bytes)")
        return

    # ---- Step 1: load & decode all images ----
    image_data = load_img_map_assets(project_dir)

    if not image_data:
        print("ASSETS.DB is empty, creating empty IMAGE.DAT")
        out_path = os.path.join(project_dir, 'IMAGE.DAT')
        Path(out_path).write_bytes(struct.pack('<I', 0))
        return

    max_id = max(r[0] for r in image_data)
    count = max_id + 1
    toc = [None] * count

    # ---- Step 2: build shared palette from ALL images ----
    shared_palette = build_shared_palette(image_data)

    # ---- Step 3: remap every image to the shared palette ----
    encoded_data = {}
    for id_val, filename, asset_type, raw, result in image_data:
        if asset_type == 'ANI':
            continue          # opaque container: packed verbatim in Step 4
        is_sprite = (asset_type == 'SPR')

        if result is None:
            raise RuntimeError(f"MAG decode failed for id={id_val} ({filename})")
        else:
            pixels, w, h, old_pal, _, _ = result

            pal_match = (len(old_pal) == 256 and all(
                a == b for a, b in zip(old_pal, shared_palette)))
            if pal_match:
                print(f"  [{id_val}] {filename}: palette matches shared palette")
            else:
                print(f"  [{id_val}] {filename}: remapping {w}x{h} "
                      f"({len(old_pal)} colours → shared palette)…")
            new_pixels = remap_pixels_to_palette(
                pixels, w, h, old_pal, shared_palette,
                transparent_idx=15 if is_sprite else None,
                protected_indices=PROTECTED_IDX)

            user_string = (MAG_SPRITE_MARKER + bytes([MAG_USER_TERM])
                           if is_sprite else b"naiz\x1a")
            encoded_data[id_val] = encode_mag(
                new_pixels, w, h, shared_palette,
                user_string=user_string, bpp=8, filter_white=False)

    used_names = set()
    for id_val, filename, asset_type, raw, result in image_data:
        raw_name = os.path.basename(filename).encode('ascii', errors='replace')
        if b'?' in raw_name:
            ext = os.path.splitext(filename)[1][:4].encode('ascii', errors='replace')
            h = hashlib.md5(filename.encode()).hexdigest()[:8].encode('ascii')
            name_bytes = h + ext
        else:
            name_bytes = raw_name
        if len(name_bytes) > 11:
            name_bytes = name_bytes[:11]
        name_padded = name_bytes.ljust(12, b'\0')
        if name_padded in used_names:
            print(f"ERROR: name collision after truncation: {filename}")
            raise RuntimeError(f"TOC name collision: {filename}")
        used_names.add(name_padded)
        if asset_type == 'ANI':
            data_bytes = raw   # verbatim container bytes, never re-encoded
        else:
            data_bytes = encoded_data.get(id_val)
            if data_bytes is None:
                raise RuntimeError(f"no encoded data for id={id_val} ({filename})")
        toc[id_val] = (name_padded, data_bytes)

    for i in range(count):
        if toc[i] is None:
            toc[i] = (b'\0' * 12, b'')
            print(f"  id={i}: empty (no entry)")

    # ---- Write IMAGE.DAT ----
    header_size = 4 + count * 20
    buf = bytearray()
    buf.extend(struct.pack('<I', count))

    offset = header_size
    for name, data in toc:
        buf.extend(name)
        buf.extend(struct.pack('<II', offset, len(data)))
        offset += len(data)

    for _, data in toc:
        buf.extend(data)

    out_path = os.path.join(project_dir, 'IMAGE.DAT')
    Path(out_path).write_bytes(buf)

    # Post-build verification: shared palette invariant
    verify_shared_palette(out_path)

    print(f"IMAGE.DAT: {len(buf)} bytes, {count} entries → {out_path}")
    for i in range(count):
        name = toc[i][0].rstrip(b'\0').decode('ascii', errors='replace')
        sz = len(toc[i][1])
        print(f"  [{i}] {name} ({sz}B)")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <project_dir>")
        sys.exit(1)
    pack_images(sys.argv[1])
