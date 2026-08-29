"""
mag_convert.py — Unified MAG (MAKI02) converter.
Merges functionality of png2mag.py and img2mag.py.

CLI:
    python -m tools.naiz_conv.mag_convert input.png -o output.mag
    python -m tools.naiz_conv.mag_convert input.png -o output.mag --sprite
    python -m tools.naiz_conv.mag_convert input.png -o output.mag --dither --16color
    python -m tools.naiz_conv.mag_convert input.png -o output.mag --master-mag palette.mag

Import API:
    from naiz_conv.mag_convert import convert_file, convert_image
    convert_file("input.png", "output.mag", sprite=True, reserved={7, 248})
    mag_bytes = convert_image(pil_img, bpp=8, user_string=b"sprt\\x1a")
"""
import argparse
import sys
from pathlib import Path
from functools import lru_cache

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from naiz_lib.mag_codec import encode_mag, decode_mag_palette
from naiz_lib.mag_constants import MAG_SPRITE_MARKER, MAG_USER_TERM
from naiz_lib.palette_utils import MAGENTA_KEY as SPRITE_KEY_COLOR
from naiz_lib.palette_utils import nearest_color_index

MAG_WIDTH = 640
MAG_HEIGHT = 400


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def parse_reserved(s):
    """Parse '7,15,248-255' -> {7, 15, 248, 249, 250, 251, 252, 253, 254, 255}"""
    indices = set()
    for part in s.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-', 1)
            indices.update(range(int(a.strip()), int(b.strip()) + 1))
        elif part:
            indices.add(int(part))
    return indices


def _hex_color(s):
    s = s.lstrip('#')
    if len(s) != 6:
        raise argparse.ArgumentTypeError(f"expected 6 hex digits, got '{s}'")
    try:
        return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid hex color: '{s}'")



# ---------------------------------------------------------------------------
# Image processing
# ---------------------------------------------------------------------------

def resize_to_screen(img, width=MAG_WIDTH, height=MAG_HEIGHT):
    from PIL import Image as PIL_Image
    src_w, src_h = img.size
    scale = min(width / src_w, height / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    resized = img.resize((new_w, new_h), PIL_Image.LANCZOS)
    canvas = PIL_Image.new("RGB", (width, height), (0, 0, 0))
    ox = (width - new_w) // 2
    oy = (height - new_h) // 2
    canvas.paste(resized, (ox, oy))
    return canvas


def normalize_near_white(pil_img, threshold=50):
    """Normalize near-white pixels to pure white before quantization.
    This avoids wasting palette entries on white-adjacent colors.
    """
    from PIL import Image as PIL_Image
    import numpy as np
    if pil_img.mode == 'RGBA':
        return pil_img
    arr = np.array(pil_img, dtype=np.float32)
    h, w, c = arr.shape
    pixels = arr.reshape(-1, 3)
    white = np.array([255, 255, 255])
    dist_w = np.sqrt(np.sum((pixels - white) ** 2, axis=1))
    pixels[dist_w < threshold] = white
    return PIL_Image.fromarray(pixels.reshape(h, w, c).astype(np.uint8))


def quantize_image(pil_img, num_colors=256, dither=False):
    """Quantize image to indexed (RGB or RGBA)."""
    from PIL import Image as PIL_Image

    if pil_img.mode == 'RGBA':
        return quantize_sprite_image(pil_img, num_colors=num_colors)

    if pil_img.mode not in ("P", "RGB"):
        pil_img = pil_img.convert("RGB")

    orig_colors = None
    if pil_img.mode == "P":
        colors = pil_img.getcolors()
        if colors is None:
            orig_colors = 0  # >= 256 colors, will be quantized
        else:
            orig_colors = len(colors)

    dith = PIL_Image.FLOYDSTEINBERG if dither else PIL_Image.NONE
    indexed = pil_img.quantize(colors=num_colors, method=2, dither=dith)

    if orig_colors is not None and orig_colors > num_colors:
        print(f"WARN: {orig_colors} colors quantized to {num_colors}")

    return indexed


def _merge_small_purple(indexed, num_colors, key_color=SPRITE_KEY_COLOR,
                         dist_sq_threshold=22500, px_threshold=50):
    """Post-process: merge small purple-halo entries into nearest clean neighbor.

    After key-color swap and alpha-mask, some leftover palette entries
    close to the key color may have very few pixels (anti-aliasing noise).
    Remap those pixels to the nearest non-purple entry to reduce color
    fringing (the "purple noise" effect).

    *dist_sq_threshold* is squared Euclidean distance from *key_color*.
    *px_threshold* is the maximum pixel count for an entry to be merged.

    Modifies *indexed* in place.  Returns True if any remapping occurred.
    """
    from collections import Counter

    kr, kg, kb = key_color
    pal = list(indexed.getpalette()[:num_colors * 3])

    # ── find "clean" (non-purple, non-15) indices ──────────────────────
    clean = []
    for i in range(num_colors):
        if i == 15:
            continue
        r = pal[i * 3]; g = pal[i * 3 + 1]; b = pal[i * 3 + 2]
        dist = (r - kr) ** 2 + (g - kg) ** 2 + (b - kb) ** 2
        if dist >= dist_sq_threshold:
            clean.append(i)

    if not clean:
        return False

    # ── count pixel usage ──────────────────────────────────────────────
    px = list(indexed.tobytes())
    counts = Counter(px)

    # ── find purple-halo entries and build remap table ──────────────────
    remap = {}
    for i in range(num_colors):
        if i == 15 or i in remap:
            continue
        if counts.get(i, 0) >= px_threshold:
            continue
        r = pal[i * 3]; g = pal[i * 3 + 1]; b = pal[i * 3 + 2]
        d_sq = (r - kr) ** 2 + (g - kg) ** 2 + (b - kb) ** 2
        if d_sq >= dist_sq_threshold:
            continue

        # find nearest clean entry
        best_idx = clean[0]
        best_dist = 256 * 256 * 3
        for ci in clean:
            cr = pal[ci * 3]; cg = pal[ci * 3 + 1]; cb = pal[ci * 3 + 2]
            d = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
            if d < best_dist:
                best_dist = d
                best_idx = ci
        remap[i] = best_idx

    if not remap:
        return False

    # ── apply remap ────────────────────────────────────────────────────
    for i in range(len(px)):
        if px[i] in remap:
            px[i] = remap[px[i]]
    indexed.putdata(px)
    return True


def quantize_sprite_image(img_rgba, num_colors=256, key_color=SPRITE_KEY_COLOR):
    """Quantize RGBA sprite: alpha -> key_color, swap key -> index 15."""
    from PIL import Image

    w, h = img_rgba.size
    alpha_raw = img_rgba.split()[3]
    alpha_mask = [a < 128 for a in alpha_raw.tobytes()]

    bg = Image.new('RGB', (w, h), key_color)
    bg.paste(img_rgba, mask=alpha_raw)
    indexed = bg.quantize(colors=num_colors, method=2, dither=Image.NONE)

    raw_pal = list(indexed.getpalette()[:num_colors * 3])
    key_idx = -1
    best_dist = 999999
    kr, kg, kb = key_color
    for i in range(num_colors):
        ri = raw_pal[i * 3]
        gi = raw_pal[i * 3 + 1]
        bi = raw_pal[i * 3 + 2]
        dist = (ri - kr) ** 2 + (gi - kg) ** 2 + (bi - kb) ** 2
        if dist < best_dist:
            best_dist = dist
            key_idx = i

    # Swap key colour into index 15 for sprite transparency
    if key_idx < 0 or best_dist > 0:
        # Force key colour into palette if quantizer eliminated it
        raw_pal[15*3:15*3+3] = [kr, kg, kb]
        indexed.putpalette(raw_pal)
        key_idx = 15
    if key_idx != 15:
        px = list(indexed.tobytes())
        for i in range(len(px)):
            p = px[i]
            if p == key_idx:
                px[i] = 15
            elif p == 15:
                px[i] = key_idx
        indexed.putdata(px)
        for c in range(3):
            tmp = raw_pal[key_idx * 3 + c]
            raw_pal[key_idx * 3 + c] = raw_pal[15 * 3 + c]
            raw_pal[15 * 3 + c] = tmp
        indexed.putpalette(raw_pal)

    # Force semi-transparent pixels to index 15 regardless of quantization result
    if alpha_mask and any(alpha_mask):
        px = list(indexed.tobytes())
        for i in range(len(px)):
            if alpha_mask[i]:
                px[i] = 15
        indexed.putdata(px)

    # Post-process: merge small purple-halo entries into nearest neighbor.
    # This reduces color fringing on sprite edges without affecting the
    # main character body.
    # dist_threshold is squared Euclidean distance (150^2 = 22500 ≈
    # visually-purple cutoff).  px_threshold keeps main-body colors.
    _merge_small_purple(indexed, num_colors, key_color,
                        dist_sq_threshold=22500, px_threshold=50)

    return indexed


def extract_palette(indexed_img, num_colors=256):
    """Extract (R, G, B) list from indexed PIL image, pad to num_colors."""
    raw = indexed_img.getpalette()
    colors = []
    n = min(num_colors, len(raw) // 3)
    for i in range(n):
        colors.append((raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]))
    while len(colors) < num_colors:
        colors.append((0, 0, 0))
    return colors


def remap_reserved(pixels, palette, reserved):
    """Remap pixel indices in reserved set to nearest non-reserved index."""
    non_reserved = [i for i in range(len(palette)) if i not in reserved]
    if len(non_reserved) == len(palette):
        return pixels

    @lru_cache(maxsize=256)
    def nearest(idx):
        r, g, b = palette[idx]
        return nearest_color_index(palette, r, g, b, skip=reserved)

    remapped = [nearest(p) if p in reserved else p for p in pixels]
    changed = sum(1 for old, new in zip(pixels, remapped) if old != new)
    if changed:
        print(f"WARN: {changed} pixels remapped from reserved index")
    return remapped


def quantize_to_palette(img_rgba, master_palette, key_color=None,
                         transparent_idx=15, num_colors=256,
                         reserved=None):
    """Quantize RGBA image to a fixed master palette.
    Pixels matching key_color or alpha<128 become transparent_idx.
    Returns (indexed PIL Image, palette_list).
    """
    from PIL import Image

    master_rgb = list(master_palette[:num_colors])
    flat = []
    for r, g, b in master_rgb:
        flat.extend([r, g, b])
    while len(flat) < 768:
        flat.extend([0, 0, 0])

    skip = set(reserved) if reserved else set()

    @lru_cache(maxsize=65536)
    def nearest(r, g, b):
        return nearest_color_index(master_rgb, r, g, b, skip=skip)

    w, h = img_rgba.size
    indexed = Image.new('P', (w, h))
    indexed.putpalette(flat)
    pixels = bytearray(w * h)
    raw = img_rgba.tobytes()
    nch = len(img_rgba.getbands())
    for i in range(w * h):
        o = i * nch
        # Always respect alpha channel: semi-transparent → transparent
        if nch == 4 and raw[o + 3] < 128:
            pixels[i] = transparent_idx
            continue
        if key_color is not None:
            if raw[o] == key_color[0] and raw[o + 1] == key_color[1] and raw[o + 2] == key_color[2]:
                pixels[i] = transparent_idx
                continue
        pixels[i] = nearest(raw[o], raw[o + 1], raw[o + 2])
    indexed.putdata(list(pixels))
    return indexed, master_rgb


# ---------------------------------------------------------------------------
# Core conversion
# ---------------------------------------------------------------------------

def convert_image(pil_img, *,
                  sprite=False, sprite_key=None,
                  num_colors=256, bpp=8,
                  dither=False, no_resize=False,
                  master_mag_path=None,
                  reserved=None, filter_white=False,
                  user_string=None):
    """Convert PIL Image to MAG bytes.

    Args:
        pil_img: PIL Image object.
        sprite: True = sprite mode (keep size, alpha->idx 15, 'sprt\\x1a').
        sprite_key: Custom transparent RGB tuple (default magenta).
        num_colors: 16 or 256.
        bpp: 4 or 8.
        dither: Floyd-Steinberg dither (background only).
        no_resize: Skip 640x400 resize (background only).
        master_mag_path: Path to MAG file for shared palette.
        reserved: Set of protected palette indices to avoid.
        filter_white: Apply near-white normalization + filtering.
        user_string: Override MAG user string (auto from sprite).
    Returns:
        bytes: Encoded MAG data.
    """
    if user_string is None:
        user_string = (MAG_SPRITE_MARKER + bytes([MAG_USER_TERM])
                       if sprite else b"naiz\x1a")

    key = sprite_key if sprite_key else SPRITE_KEY_COLOR

    # ---- Master palette (shared palette mode) ----
    master_pal = None
    if master_mag_path:
        data = Path(master_mag_path).read_bytes()
        master_pal = decode_mag_palette(data)
        if not master_pal:
            raise RuntimeError(f"failed to extract palette from {master_mag_path}")

    # ---- Pre-quantize: normalize near-white to pure white ----
    if filter_white and not sprite:
        pil_img = normalize_near_white(pil_img)

    # ---- Sprite path ----
    if sprite:
        if pil_img.mode != 'RGBA':
            pil_img = pil_img.convert('RGBA')
        w, h = pil_img.size

        if master_pal:
            indexed, palette = quantize_to_palette(
                pil_img, master_pal, key_color=key,
                transparent_idx=15, num_colors=num_colors,
                reserved=reserved)
        else:
            indexed = quantize_sprite_image(pil_img, num_colors=num_colors, key_color=key)
            palette = extract_palette(indexed, num_colors=num_colors)

    # ---- Background path ----
    else:
        if pil_img.mode not in ("RGB", "RGBA"):
            pil_img = pil_img.convert("RGB")
        elif pil_img.mode == "RGBA":
            from PIL import Image
            bg = Image.new("RGB", pil_img.size, (0, 0, 0))
            bg.paste(pil_img, mask=pil_img.split()[3])
            pil_img = bg
            print("WARN: alpha channel flattened")

        if not no_resize:
            pil_img = resize_to_screen(pil_img)

        if not master_pal:
            indexed = quantize_image(pil_img, num_colors=num_colors, dither=dither)
            palette = extract_palette(indexed, num_colors=num_colors)
        else:
            indexed, palette = quantize_to_palette(
                pil_img.convert('RGBA'), master_pal,
                key_color=None, transparent_idx=15,
                num_colors=num_colors, reserved=reserved)

    # ---- Common encode ----
    pixels = list(indexed.tobytes())
    w, h = indexed.size

    if reserved:
        pixels = remap_reserved(pixels, palette, reserved)
        for i in reserved:
            if i < len(palette):
                palette[i] = (0, 0, 0)

    protected = reserved if reserved else None

    if filter_white:
        mag_data = encode_mag(pixels, w, h, palette, user_string=user_string,
                              bpp=bpp, filter_white=True, protected_indices=protected)
    else:
        mag_data = encode_mag(pixels, w, h, palette, user_string=user_string,
                              bpp=bpp, protected_indices=protected)

    return mag_data


def convert_file(input_path, output_path, **kwargs):
    """Convert image file to MAG file.

    Args:
        input_path: Path to input image.
        output_path: Path to output MAG.
        **kwargs: Forwarded to convert_image().
    """
    from PIL import Image
    pil_img = Image.open(input_path)
    mag_data = convert_image(pil_img, **kwargs)
    Path(output_path).write_bytes(mag_data)
    w, h = pil_img.size
    num_colors = kwargs.get('num_colors', 256)
    tag = "sprite" if kwargs.get('sprite') else ("dithered" if kwargs.get('dither') else "direct")
    print(f"  Encoded {w}x{h} {num_colors}-color ({tag}) -> {output_path}  ({len(mag_data)} bytes)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert image to PC-98 MAG (MAKI02) format")
    parser.add_argument("input", help="Input image (PNG, JPG, etc.)")
    parser.add_argument("-o", "--output", required=True, help="Output MAG path")
    parser.add_argument("--sprite", action="store_true",
                        help="Sprite mode: keep size, alpha->idx 15, 'sprt\\x1a'")
    parser.add_argument("--sprite-key", type=_hex_color, default=None,
                        help="Transparent color (e.g. '#FF00FF'). Default: magenta")
    parser.add_argument("--16color", action="store_true", dest="color_16",
                        help="16-color mode (default: 256)")
    parser.add_argument("--dither", action="store_true",
                        help="Floyd-Steinberg dither (background only)")
    parser.add_argument("--no-resize", action="store_true",
                        help="Skip auto-resize to 640x400 (background only)")
    parser.add_argument("--master-mag", type=str, default=None,
                        help="Shared palette from another MAG file")
    parser.add_argument("--reserved", type=str, default=None,
                        help="Protected indices: '7,15,248-255'")
    parser.add_argument("--filter-white", action="store_true",
                        help="Normalize near-white to pure white and filter")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    kwargs = {}
    if args.sprite:
        kwargs['sprite'] = True
    if args.sprite_key:
        kwargs['sprite_key'] = args.sprite_key
    if getattr(args, 'color_16', False):
        kwargs['num_colors'] = 16
        kwargs['bpp'] = 4
    if args.dither:
        kwargs['dither'] = True
    if args.no_resize:
        kwargs['no_resize'] = True
    if args.master_mag:
        kwargs['master_mag_path'] = args.master_mag
    if args.reserved:
        kwargs['reserved'] = parse_reserved(args.reserved)
    if args.filter_white:
        kwargs['filter_white'] = True

    # Handle --256 -> --16color mapping (compat)
    # (argparse doesn't know --256; we handle this in wrappers)

    convert_file(input_path, args.output, **kwargs)


if __name__ == "__main__":
    main()
