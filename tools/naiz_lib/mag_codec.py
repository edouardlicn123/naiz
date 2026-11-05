"""
Shared MAG (MAKI02) codec — single source for encode/decode utilities.
Used by mag_convert.py and pack_images.py.
"""
import struct

from naiz_lib.mag_constants import (
    MAG_SIGNATURE,
    MAG_SPRITE_MARKER,
    MAG_HEADER_SIZE,
    MAG_USER_TERM,
    MAG_MODEL_3BIT,
    MAG_MODEL_5BIT,
    MAG_MODEL_8BIT,
    MAG_MODEL_8BIT2,
)


def expand_comp(v, bits):
    """Expand n-bit color channel to 8-bit by replicating MSBs to LSBs."""
    if bits >= 8:
        return v
    v &= (1 << bits) - 1
    if bits == 0:
        return 0
    result = 0
    for i in range(8):
        bit_idx = (bits - 1) - (i % bits)
        result = (result << 1) | ((v >> bit_idx) & 1)
    return result


def _ref_offset(n, row_bytes):
    """Compute relative reference offset for MAG control byte n (1..15).
    Shared by build_ref_table and the inline decoder. n ranges 1-15;
    n <= 11 covers one/two rows back, n >= 12 reaches three rows back."""
    if n <= 3:
        return -2 * n
    elif n <= 7:
        return -row_bytes + (-2 * (n - 4))
    elif n <= 11:
        return -2 * row_bytes + (-2 * (n - 8))
    else:
        return -3 * row_bytes + (-2 * (n - 12))


def build_ref_table(row_bytes):
    """Build 15-entry relative-reference offset table (byte offsets from current pos)."""
    t = [0] * 16
    for n in range(1, 16):
        t[n] = _ref_offset(n, row_bytes)
    return t


def pixels_to_padded(pixels, width, height, bpp=4):
    """Pack indexed pixel array into padded byte array for MAG compression.
    Returns (padded_bytes, byte_width).
    """
    px_per_byte = 8 // bpp
    pad_left_byte = (0 // px_per_byte) & ~3
    pad_right_byte = ((width - 1) // px_per_byte + 4) & ~3
    byte_width = pad_right_byte - pad_left_byte
    pad_offset = pad_left_byte // px_per_byte

    padded = bytearray(byte_width * height)
    for y in range(height):
        row_off = y * byte_width
        if bpp == 4:
            b = 0
            for x in range(0, width, 2):
                lo = pixels[y * width + x] & 0x0F
                hi = pixels[y * width + x + 1] & 0x0F if x + 1 < width else 0
                padded[row_off + pad_offset + b] = lo | (hi << 4)
                b += 1
        else:
            for x in range(width):
                padded[row_off + pad_offset + x] = pixels[y * width + x] & 0xFF
    return bytes(padded), byte_width


def encode_mag_stream(padded, byte_width):
    """Core MAG compression: flag-A / flag-B / color stream.
    Returns (flag_a, flag_b, color_stream) as bytearray objects.
    """
    output_total = len(padded)
    action_size = byte_width // 4
    if action_size <= 0:
        raise ValueError("Image too narrow for MAG encoding")
    num_steps = output_total // 4

    ref_tab = build_ref_table(byte_width)
    desired = bytearray(num_steps)
    color_stream = bytearray()

    out_pos = 0
    step = 0
    while out_pos + 3 < output_total:
        nib_hi = 0
        nib_lo = 0

        v_lo = padded[out_pos]
        v_hi = padded[out_pos + 1]
        for n in range(1, 16):
            src = out_pos + ref_tab[n]
            if 0 <= src < out_pos and src + 1 < output_total:
                if padded[src] == v_lo and padded[src + 1] == v_hi:
                    nib_hi = n
                    break
        if nib_hi == 0:
            color_stream.extend([v_lo, v_hi])

        if out_pos + 2 < output_total:
            v2_lo = padded[out_pos + 2]
            v2_hi = padded[out_pos + 3]
            for n in range(1, 16):
                src2 = out_pos + 2 + ref_tab[n]
                if 0 <= src2 < out_pos + 2 and src2 + 1 < output_total:
                    if padded[src2] == v2_lo and padded[src2 + 1] == v2_hi:
                        nib_lo = n
                        break
            if nib_lo == 0:
                color_stream.extend([v2_lo, v2_hi])

        desired[step] = (nib_hi << 4) | nib_lo
        out_pos += 4
        step += 1

    current_action = bytearray(action_size)
    flag_a = bytearray()
    flag_b = bytearray()
    fa_cur = 0
    fa_bit = 0x80

    for step in range(num_steps):
        act_pos = step % action_size
        d = desired[step]
        if current_action[act_pos] != d:
            fa_cur |= fa_bit
            flag_b.append(current_action[act_pos] ^ d)
            current_action[act_pos] = d
        fa_bit >>= 1
        if fa_bit == 0:
            flag_a.append(fa_cur)
            fa_cur = 0
            fa_bit = 0x80

    if fa_bit != 0x80:
        flag_a.append(fa_cur)

    return flag_a, flag_b, color_stream


def filter_near_white(palette, threshold=50, pixels=None, protected_indices=None):
    """Replace near-white palette entries with the nearest non-white entry.
    Uses Euclidean distance from white (255,255,255) for detection.
    If pixels provided, excludes the most common index (background) from filtering.
    threshold=50 filters entries within ~29% brightness of white.
    protected_indices: set of palette indices not to use as remap targets.
    Returns (new_palette, remap) where remap maps old indices to new indices.
    """
    from collections import Counter

    protected = protected_indices or set()

    # Find background index (most common pixel) to exclude
    bg_idx = -1
    if pixels:
        counts = Counter(pixels)
        if counts:
            bg_idx = counts.most_common(1)[0][0]

    white_indices = []
    for i, (r, g, b) in enumerate(palette):
        if i == bg_idx or i in protected:
            continue  # skip background and protected indices
        dist = ((255 - r) ** 2 + (255 - g) ** 2 + (255 - b) ** 2) ** 0.5
        if dist < threshold:
            white_indices.append(i)

    if not white_indices:
        return palette, list(range(len(palette)))

    print(f"WARN: filter_near_white merged {len(white_indices)} near-white entries")

    non_white = [(i, r, g, b) for i, (r, g, b) in enumerate(palette)
                 if i not in white_indices and i != bg_idx and i not in protected]

    if not non_white:
        return palette, list(range(len(palette)))

    remap = list(range(len(palette)))
    new_palette = list(palette)

    for wi in white_indices:
        wr, wg, wb = palette[wi]
        best_idx, best_dist = non_white[0][0], float('inf')
        for idx, r, g, b in non_white:
            dist = (r - wr) ** 2 + (g - wg) ** 2 + (b - wb) ** 2
            if dist < best_dist:
                best_dist = dist
                best_idx = idx
        remap[wi] = best_idx
        new_palette[wi] = new_palette[best_idx]

    return new_palette, remap


def merge_similar_palette(palette, threshold=25, protected_indices=None):
    """Merge palette entries that are too similar (distance < threshold).
    Protected indices are never merged into or out of.
    Returns (new_palette, remap) where remap maps old indices to new indices.
    """
    n = len(palette)
    protected = protected_indices or set()
    merged = set()
    remap = list(range(n))

    for i in range(n):
        if i in merged or i in protected:
            continue
        r1, g1, b1 = palette[i]
        for j in range(i + 1, n):
            if j in merged or j in protected:
                continue
            r2, g2, b2 = palette[j]
            dist = ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5
            if dist < threshold:
                merged.add(j)
                remap[j] = i

    new_palette = list(palette)
    for m in merged:
        new_palette[m] = new_palette[remap[m]]

    if merged:
        print(f"WARN: merge_similar_palette merged {len(merged)} similar entries")

    return new_palette, remap


def encode_mag(pixels, width, height, palette, user_string=b"naiz\x1a", bpp=4,
               filter_white=False, protected_indices=None):
    """Encode pixel array + palette -> MAG file bytes."""
    if filter_white:
        palette, remap = filter_near_white(palette, pixels=pixels, protected_indices=protected_indices)
        pixels = [remap[p] for p in pixels]
        # bg_idx (0) must also be protected from merging
        merge_protected = set(protected_indices or {})
        merge_protected.add(0)
        palette, remap2 = merge_similar_palette(palette, protected_indices=merge_protected)
        pixels = [remap2[p] for p in pixels]

    if bpp == 8 and len(palette) > 256:
        raise ValueError(f"8bpp palette has {len(palette)} entries, max 256")
    if bpp == 4 and len(palette) > 16:
        raise ValueError(f"4bpp palette has {len(palette)} entries, max 16")

    screen_mode = 0x80 if bpp == 8 else 0x00
    padded, byte_width = pixels_to_padded(pixels, width, height, bpp)
    flag_a, flag_b, color_stream = encode_mag_stream(padded, byte_width)
    palette_bytes = bytearray()
    for pr, pg, pb in palette:
        palette_bytes.extend([pg, pr, pb])  # GRB order
    min_pal = 256 * 3 if bpp == 8 else 48
    while len(palette_bytes) < min_pal:
        palette_bytes.append(0)

    fixed_hdr_size = MAG_HEADER_SIZE
    flag_a_off = fixed_hdr_size + len(palette_bytes)
    flag_b_off = flag_a_off + len(flag_a)
    color_off = flag_b_off + len(flag_b)

    hdr = struct.pack(
        "<BBBBHHHHIIIII",
        0x00, 0x00, 0x00, screen_mode,
        0, 0,
        width - 1, height - 1,
        flag_a_off, flag_b_off, len(flag_b),
        color_off, len(color_stream),
    )

    result = bytearray()
    result.extend(MAG_SIGNATURE)
    result.extend(b"PC98")
    result.extend(user_string)
    result.extend(hdr)
    result.extend(palette_bytes)
    result.extend(flag_a)
    result.extend(flag_b)
    result.extend(color_stream)
    return bytes(result)


def decode_mag_palette(data):
    """Extract palette from MAG data. Returns list of (r, g, b) tuples."""
    if len(data) < 40:
        return []
    if data[0:8] != MAG_SIGNATURE:
        return []

    pos = 8 + 4  # skip signature + machine ID
    while pos < len(data) and data[pos] != MAG_USER_TERM:
        pos += 1
    if pos >= len(data):
        return []
    pos += 1  # skip MAG_USER_TERM

    if pos + MAG_HEADER_SIZE > len(data):
        return []
    model_code = data[pos + 1]
    flag_a_off = struct.unpack_from("<I", data, pos + 12)[0]

    pbits = 4
    if model_code == MAG_MODEL_3BIT:
        pbits = 3
    elif model_code == MAG_MODEL_5BIT:
        pbits = 5
    elif model_code == MAG_MODEL_8BIT:
        pbits = 8

    palette_end = pos + flag_a_off
    palette_bytes = palette_end - (pos + MAG_HEADER_SIZE)
    num_colors = palette_bytes // 3
    # palette_bytes can be negative when flag_a_off < MAG_HEADER_SIZE;
    # Python floor division produces a negative num_colors,
    # caught by the guard below — safe.
    if num_colors < 1 or num_colors > 256:
        return []

    # model_code MAG_MODEL_8BIT2 uses a different palette storage format
    # (2 bytes/entry, 6-bit R/G/B packed) not handled here;
    # naiz encoder never produces MAG_MODEL_8BIT2, so excluded intentionally.
    if num_colors == 256 and model_code not in (MAG_MODEL_3BIT, MAG_MODEL_8BIT2):
        pbits = 8

    palette = []
    ppos = pos + MAG_HEADER_SIZE
    for i in range(min(num_colors, 256)):
        g = expand_comp(data[ppos], pbits); ppos += 1
        r = expand_comp(data[ppos], pbits); ppos += 1
        b = expand_comp(data[ppos], pbits); ppos += 1
        palette.append((r, g, b))
    return palette


def decode_mag_full(data):
    """Full MAG decoder. Returns (pixels, width, height, palette, bpp, is_sprite) or None.
    pixels: bytes object (w*h), palette: list of (r,g,b) tuples."""
    if len(data) < 40 or data[0:8] != MAG_SIGNATURE:
        return None

    pos = 8 + 4  # skip signature + machine ID
    is_sprite = (pos + 4 <= len(data) and data[pos:pos+4] == MAG_SPRITE_MARKER)
    while pos < len(data) and data[pos] != MAG_USER_TERM:
        pos += 1
    if pos >= len(data):
        return None
    pos += 1  # skip MAG_USER_TERM
    if pos + MAG_HEADER_SIZE > len(data):
        return None

    hdr_start = pos
    pos += 1   # start_marker
    model_code = data[pos]; pos += 1
    pos += 1   # model_flags
    screen_mode = data[pos]; pos += 1
    bpp = 8 if (screen_mode & 0x80) else 4

    left = data[pos] | (data[pos+1] << 8); pos += 2
    top = data[pos] | (data[pos+1] << 8); pos += 2
    right = data[pos] | (data[pos+1] << 8); pos += 2
    bottom = data[pos] | (data[pos+1] << 8); pos += 2
    flag_a_off = struct.unpack_from("<I", data, pos)[0]; pos += 4
    flag_b_off = struct.unpack_from("<I", data, pos)[0]; pos += 4
    flag_b_size = struct.unpack_from("<I", data, pos)[0]; pos += 4
    color_off = struct.unpack_from("<I", data, pos)[0]; pos += 4
    color_size = struct.unpack_from("<I", data, pos)[0]; pos += 4

    # Validate the three data streams against the file bounds before slicing;
    # otherwise a truncated MAG would silently decode into a corrupted image.
    if (flag_a_off > flag_b_off
            or hdr_start + flag_b_off + flag_b_size > len(data)
            or hdr_start + color_off + color_size > len(data)):
        return None

    # Palette
    palette_end = hdr_start + flag_a_off
    palette_start = pos
    pbits = 4
    if model_code == MAG_MODEL_3BIT: pbits = 3
    elif model_code == MAG_MODEL_5BIT: pbits = 5
    elif model_code == MAG_MODEL_8BIT: pbits = 8
    pal_bytes = palette_end - palette_start
    num_colors = pal_bytes // 3
    if num_colors < 1 or num_colors > 256:
        return None
    # model_code MAG_MODEL_8BIT2 uses a different palette storage format
    # (2 bytes/entry, 6-bit R/G/B packed) not handled here;
    # naiz encoder never produces MAG_MODEL_8BIT2, so excluded intentionally.
    if num_colors == 256 and model_code not in (MAG_MODEL_3BIT, MAG_MODEL_8BIT2):
        pbits = 8

    palette = []
    ppos = palette_start
    for _ in range(min(num_colors, 256)):
        g = expand_comp(data[ppos], pbits); ppos += 1
        r = expand_comp(data[ppos], pbits); ppos += 1
        b = expand_comp(data[ppos], pbits); ppos += 1
        palette.append((r, g, b))

    # Dimensions
    px_per_byte = 8 // bpp
    pad_left = (left // px_per_byte) & ~3
    pad_right = ((right // px_per_byte) + 4) & ~3
    byte_width = pad_right - pad_left
    pixel_width = byte_width * px_per_byte
    pixel_height = bottom - top + 1

    # Streams
    flag_a = data[hdr_start + flag_a_off:hdr_start + flag_b_off]
    flag_b = data[hdr_start + flag_b_off:hdr_start + flag_b_off + flag_b_size]
    color = data[hdr_start + color_off:hdr_start + color_off + color_size]

    output_total = byte_width * pixel_height
    output = bytearray(output_total + 16)
    action_size = byte_width // 4
    action = bytearray(action_size + 4)
    row_bytes = byte_width

    # Bit reader
    fa_byte_pos = 0
    fa_bit_mask = 0x80
    def fa_read():
        nonlocal fa_byte_pos, fa_bit_mask
        if fa_byte_pos >= len(flag_a):
            return -1
        b = 1 if (flag_a[fa_byte_pos] & fa_bit_mask) else 0
        fa_bit_mask >>= 1
        if fa_bit_mask == 0:
            fa_bit_mask = 0x80
            fa_byte_pos += 1
        return b

    fb_pos = 0
    col_pos = 0
    out_pos = 0
    act_idx = 0

    while out_pos + 1 < output_total:
        a = fa_read()
        if a == 1:
            if fb_pos < len(flag_b):
                action[act_idx % action_size] ^= flag_b[fb_pos]
                fb_pos += 1
        ab = action[act_idx % action_size]
        act_idx += 1

        for nib in range(2):
            if out_pos + 1 >= output_total:
                break
            n = (ab >> 4) if nib == 0 else (ab & 0x0F)
            if n == 0:
                if col_pos + 1 >= len(color):
                    raise ValueError(f"MAG decode: color stream exhausted at out_pos={out_pos}")
                v = color[col_pos] | (color[col_pos + 1] << 8)
                col_pos += 2
                output[out_pos] = v & 0xFF
                output[out_pos + 1] = v >> 8
            else:
                ref = _ref_offset(n, row_bytes)
                src = out_pos + ref
                if src >= 0 and src + 1 < output_total:
                    output[out_pos] = output[src]
                    output[out_pos + 1] = output[src + 1]
                else:
                    raise ValueError(f"MAG decode: reference OOB src={src} output_total={output_total}")
            out_pos += 2

    # Crop left/right padding
    pad_px_left = left - (pad_left * px_per_byte)
    crop_width = right - left + 1
    crop_height = pixel_height
    pixels = bytearray(crop_width * crop_height)
    if bpp == 4:
        for y in range(crop_height):
            row_off = y * byte_width
            for x in range(crop_width):
                px = x + pad_px_left
                bv = output[row_off + px // 2]
                pixels[y * crop_width + x] = (bv >> (4 * (px & 1))) & 0x0F
    else:
        for y in range(crop_height):
            for x in range(crop_width):
                pixels[y * crop_width + x] = output[y * pixel_width + x + pad_px_left]

    return bytes(pixels), crop_width, crop_height, palette, bpp, is_sprite
