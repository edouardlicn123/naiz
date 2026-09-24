"""
IMAGE.DAT archive parsing + shared-palette verification.

Consolidates the TOC-walking and palette-verification logic that previously
lived in naiz_build/pack_images.py, diag/check_palette.py and
naiz_build/build_game.py (three independent copies of the same 20-byte TOC
format).
"""

import struct

IMAGE_DAT_HEADER = 4       # 4-byte entry count
IMAGE_DAT_TOC_SIZE = 20    # 12-byte name + 4-byte offset + 4-byte size


def iter_image_dat_toc(data):
    """Yield (index, name, offset, size) for every TOC entry of an IMAGE.DAT.
    Stops silently on a truncated TOC."""
    if len(data) < IMAGE_DAT_HEADER:
        return
    count = struct.unpack('<I', data[0:4])[0]
    for i in range(count):
        off = IMAGE_DAT_HEADER + i * IMAGE_DAT_TOC_SIZE
        if off + IMAGE_DAT_TOC_SIZE > len(data):
            return
        name = data[off:off + 12]
        eoff = struct.unpack_from('<I', data, off + 12)[0]
        esz = struct.unpack_from('<I', data, off + 16)[0]
        yield i, name, eoff, esz


def verify_shared_palette(data, max_count=65536):
    """Return a list of error strings; empty means all MAG entries share an
    identical 256-colour palette with correct protected indices.
    Non-MAG entries (e.g. .ANI containers) carry no palette and are skipped."""
    from naiz_lib.mag_codec import decode_mag_palette
    from naiz_lib.mag_constants import MAG_SIGNATURE

    if len(data) < IMAGE_DAT_HEADER:
        return []
    count = struct.unpack('<I', data[0:4])[0]
    if count > max_count:
        return []

    first_pal = None
    errors = []
    for i, _name, eoff, esz in iter_image_dat_toc(data):
        if esz == 0:
            continue
        if eoff + esz > len(data):
            errors.append(f"[{i}] data truncated at offset {eoff}")
            continue

        chunk = data[eoff:eoff + esz]
        if not chunk.startswith(MAG_SIGNATURE):
            # Non-MAG entry (e.g. .ANI container): no palette invariant applies.
            continue
        pal = decode_mag_palette(chunk)
        if len(pal) != 256:
            errors.append(f"[{i}] palette size {len(pal)}, expected 256")
            continue

        if first_pal is None:
            first_pal = pal
            if first_pal[7] != (255, 255, 255):
                errors.append("idx 7 != (255,255,255)")
            if first_pal[15] != (255, 255, 255):
                errors.append("idx 15 != (255,255,255)")
            for j in range(248, 256):
                if first_pal[j] != (0, 0, 0):
                    errors.append(f"idx {j} != (0,0,0)")
        elif pal != first_pal:
            errors.append(f"[{i}] palette differs from entry 0")
    return errors


def first_mag_palette(data, max_count=65536):
    """Return the decoded 256-colour palette of the first MAG-format entry,
    or None when the archive holds no decodable MAG entry.

    Used as the shared-palette baseline during game builds: non-MAG entries
    (e.g. .ANI containers) are skipped so an ANI entry at id=0 cannot zero
    out the baseline and silently disable source-palette comparison."""
    from naiz_lib.mag_codec import decode_mag_palette
    from naiz_lib.mag_constants import MAG_SIGNATURE

    if len(data) < IMAGE_DAT_HEADER:
        return None
    count = struct.unpack('<I', data[0:4])[0]
    if count > max_count:
        return None
    for _i, _name, eoff, esz in iter_image_dat_toc(data):
        if esz <= 0 or eoff + esz > len(data):
            continue
        chunk = data[eoff:eoff + esz]
        if not chunk.startswith(MAG_SIGNATURE):
            continue
        pal = decode_mag_palette(chunk)
        if pal is not None and len(pal) == 256:
            return pal
    return None


def verify_shared_palette_file(out_path):
    """Read an IMAGE.DAT from disk and run verify_shared_palette().
    Prints a report and returns 0 (OK) or 1 (failure)."""
    with open(out_path, 'rb') as f:
        data = f.read()
    errors = verify_shared_palette(data)
    count = struct.unpack('<I', data[0:4])[0] if len(data) >= IMAGE_DAT_HEADER else 0
    if errors:
        for e in errors:
            print(f"  ERROR: {e}")
        print("IMAGE.DAT palette verification FAILED")
        return 1
    print(f"IMAGE.DAT palette verification OK ({count} entries, shared 256-colour palette)")
    return 0
