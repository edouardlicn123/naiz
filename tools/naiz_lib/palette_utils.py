"""
palette_utils — palette processing utilities for the NAiz build pipeline.

Provides:
    is_near_magenta()      — detect alpha-compositing artifacts near key color
    warm_skin_tone()       — compensate NP2kai RGB565 G-loss on skin tones
    find_skin_entries()    — locate skin-tone indices in a palette
    validate_skin_palette() — compare shared palette against source MAG palettes
"""


from naiz_lib import PROTECTED_IDX_ALL

MAGENTA_KEY = (255, 0, 255)
"""Chroma-key color used for transparency compositing."""

KEY_DIST_SQ = 22500
"""Squared Euclidean distance threshold (150^2) — matches _merge_small_purple."""

SKIN_WARM_R_OFFSET = 4
"""Skin-tone warming: R increase per entry (compensates R=5b precision in RGB565)."""

SKIN_WARM_G_DELTA = -2
"""Skin-tone warming: G decrease per entry."""

SKIN_R_MIN = 200
SKIN_G_LO = 160
SKIN_G_HI = 245
SKIN_B_LO = 120
SKIN_B_HI = 220
"""Heuristic skin-tone RGB range.  Uses strict comparisons (>, <) matching the
original inline code — boundary values are NOT treated as skin tones."""

VALIDATE_GR_WARN = 0.03
"""Maximum allowed G/R ratio increase before emitting a warning."""

VALIDATE_DE_MAX = 3.0
"""Maximum allowed ΔE before emitting a warning."""


# ---------------------------------------------------------------------------
# Detection / filtering
# ---------------------------------------------------------------------------

def is_near_magenta(r, g, b, key=None, threshold_sq=None):
    """Return True if (r,g,b) is within *threshold_sq* of *key*.

    Used to skip alpha-compositing edge pixels that bleed into
    transparent-background sprites.
    """
    if key is None:
        key = MAGENTA_KEY
    if threshold_sq is None:
        threshold_sq = KEY_DIST_SQ
    dr = r - key[0]
    dg = g - key[1]
    db = b - key[2]
    return dr * dr + dg * dg + db * db < threshold_sq


def is_skin_tone(r, g, b):
    """Return True if (r,g,b) falls within the heuristic skin-tone range.
    
    Matches the same thresholds used by find_skin_entries and warm_skin_tone.
    """
    return (r > SKIN_R_MIN and SKIN_G_LO < g < SKIN_G_HI
            and SKIN_B_LO < b < SKIN_B_HI and g < r)


def find_skin_entries(palette):
    indices = []
    for i, (r, g, b) in enumerate(palette):
        if is_skin_tone(r, g, b):
            indices.append(i)
    return indices


def warm_skin_tone(r, g, b, r_offset=None, g_delta=None):
    if r_offset is None:
        r_offset = SKIN_WARM_R_OFFSET
    if g_delta is None:
        g_delta = SKIN_WARM_G_DELTA
    if is_skin_tone(r, g, b):
        return (min(255, r + r_offset), max(0, g + g_delta), b)
    return (r, g, b)


# ---------------------------------------------------------------------------
# Nearest colour search
# ---------------------------------------------------------------------------

def nearest_color_index(palette, r, g, b, skip=None, best_start=None):
    """Return the index of the palette entry nearest to (r,g,b).

    Args:
        palette: iterable of (r,g,b) tuples.
        r, g, b: target colour components.
        skip: optional iterable of indices to exclude (e.g. protected entries).
        best_start: initial squared-distance bound (default 256*256*3).
    """
    if skip is None:
        skip = set()
    elif not isinstance(skip, set):
        skip = set(skip)
    if best_start is None:
        best_start = 256 * 256 * 3
    best_idx = 0
    best_dist = best_start
    for i, (mr, mg, mb) in enumerate(palette):
        if i in skip:
            continue
        dr = r - mr
        dg = g - mg
        db = b - mb
        d = dr * dr + dg * dg + db * db
        if d < best_dist:
            best_dist = d
            best_idx = i
    return best_idx


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def colour_distance(c1, c2):
    """Euclidean distance between two (r,g,b) tuples."""
    dr = c1[0] - c2[0]
    dg = c1[1] - c2[1]
    db = c1[2] - c2[2]
    return (dr * dr + dg * dg + db * db) ** 0.5


def validate_skin_palette(shared_palette, source_palettes, gr_warn=None, de_max=None):
    """Compare skin-tone entries in *shared_palette* against *source_palettes*.

    Args:
        shared_palette: list of 256 (r,g,b) tuples from build_shared_palette().
        source_palettes: iterable of source MAG palettes (list of (r,g,b)).
        gr_warn: G/R increase threshold (default VALIDATE_GR_WARN).
        de_max: ΔE threshold (default VALIDATE_DE_MAX).

    Returns:
        list of warning strings (empty if all checks pass).
    """
    if gr_warn is None:
        gr_warn = VALIDATE_GR_WARN
    if de_max is None:
        de_max = VALIDATE_DE_MAX

    warnings = []

    for src_idx, src_pal in enumerate(source_palettes):
        skin_idx = find_skin_entries(src_pal)
        if not skin_idx:
            continue

        for si in skin_idx:
            sr, sg, sb = src_pal[si]
            if sg == 0:
                continue
            src_gr = sg / sr

            # Find nearest entry in shared palette (excluding protected)
            best_i = 0
            best_d = 1e9
            for i, (mr, mg, mb) in enumerate(shared_palette):
                if i in PROTECTED_IDX_ALL:
                    continue
                d = colour_distance((sr, sg, sb), (mr, mg, mb))
                if d < best_d:
                    best_d = d
                    best_i = i

            mr, mg, mb = shared_palette[best_i]
            shared_gr = mg / mr if mr > 0 else 0.0
            gr_delta = shared_gr - src_gr

            if best_d > de_max:
                warnings.append(
                    f"  src[#{src_idx}][{si}] ({sr},{sg},{sb}) "
                    f"→ shared[{best_i}] ({mr},{mg},{mb})  "
                    f"ΔE={best_d:.1f}  (threshold {de_max})"
                )
            elif gr_delta > gr_warn:
                warnings.append(
                    f"  src[#{src_idx}][{si}] G/R={src_gr:.4f} "
                    f"→ shared[{best_i}] G/R={shared_gr:.4f}  "
                    f"ΔG/R={gr_delta:+.4f}  (threshold +{gr_warn})"
                )

    return warnings
