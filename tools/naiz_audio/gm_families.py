"""GM program clusters -> FM patch families (devdocs/124 S6).

Single source of truth for the default YM2608 FM patch families.  `FAMILIES`
is an ordered list of (family_name, [GM programs...]) in the **default
registration order**: a project registers its assets/<project>/fm/<name>.fmp
files in exactly this order so that the family index (the position of the
family in ASSETS.DB type='FMP' ORDER BY id / fmp_map / the engine's
g_fm_patches table) matches the index used by fmp_gm_map.

The GM cluster table is DATA, kept apart from both the engine code and the
patch binaries.  Danger of silently losing a mapping is the one thing this
module exists to prevent:

  * every GM program 0..127 must map to exactly one family (no gaps, no
    duplicates) - enforced by build_gm_map() below;
  * the project's FMP row order must be exactly the FAMILIES order, else
    the generated family indices would not match the engine's patch table
    (fmp_gm_map is emitted by export_asset_table.py which raises here).

Projects that deliberately register a different/subset patch set must keep
every listed family present and in this same order (the override mechanism
is a future step; for now a mismatch fails loudly rather than mapping wrong).
"""

# (family_name, [GM programs...]): name == the .fmp basename and the
# ASSETS.DB `name` column (script key, DOS 8.3 safe).  Order is the patch
# load order.  Programs are GM program numbers 0..127.
FAMILIES = [
    ('piano',   list(range(0, 8))),
    ('bell',    list(range(8, 16))),
    ('organ',   list(range(16, 24))),
    ('guitar',  list(range(24, 32))),
    ('bass',    list(range(32, 40))),
    ('strings', list(range(40, 47)) + list(range(48, 55))),
    ('brass',   list(range(56, 64))),
    ('reeds',   list(range(64, 72))),
    ('flute',   list(range(72, 80))),
    ('synlead', list(range(80, 88))),
    ('synpad',  list(range(88, 96))),
    ('synfx',   list(range(96, 104))),
    ('ethnic',  list(range(104, 112))),
    ('perc',    [47, 55] + list(range(112, 120))),
    ('sfx',     list(range(120, 128))),
]

# Keep the register logic in one place so a future override reuses it.
GM_PROGRAM_COUNT = 128


def build_gm_map(order):
    """Map every GM program 0..127 to a family index.

    `order` is the project's FMP asset order: a list of family names from
    ASSETS.DB type='FMP' ORDER BY id (== fmp_map order == AUDIO.DAT order).
    Returns a list of GM_PROGRAM_COUNT ints (family index == position in
    `order`).  Raises ValueError if `order` is not exactly the FAMILIES
    order or if any program is left unmapped / mapped twice.
    """
    expected = [name for name, _programs in FAMILIES]
    if list(order) != expected:
        raise ValueError(
            f"FMP asset order {order} != gm_families order {expected}\n"
            "  Register assets/<project>/fm/<name>.fmp in FAMILIES order "
            "so family indices match the engine patch table.")
    gm = [None] * GM_PROGRAM_COUNT
    for index, (_name, programs) in enumerate(FAMILIES):
        for prog in programs:
            if not (0 <= prog < GM_PROGRAM_COUNT):
                raise ValueError(f"program {prog} out of range 0..127")
            if gm[prog] is not None:
                raise ValueError(f"program {prog} mapped twice")
            gm[prog] = index
    gaps = [p for p, v in enumerate(gm) if v is None]
    if gaps:
        raise ValueError(
            f"GM programs {gaps} have no family (all 0..127 must be "
            "mapped; a silent unmapped note would fall back to family 0)")
    return gm