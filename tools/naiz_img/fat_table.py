"""
fat_table.py — FAT table helpers (entry packing, chain allocation).

Imported/re-exported via fat.py.
"""

import struct

from .fat_entries import FAT12_EOC, FAT16_EOC


def set_fat_entry(buf, i, val, fat_type):
    """Write one FAT entry into a bytearray buffer in-place."""
    if fat_type == 12:
        offset = i + (i // 2)
        if offset + 1 >= len(buf):
            return
        word = struct.unpack_from('<H', buf, offset)[0]
        if i & 1:
            word = (word & 0x000F) | ((val & 0x0FFF) << 4)
        else:
            word = (word & 0xF000) | (val & 0x0FFF)
        struct.pack_into('<H', buf, offset, word)
    else:
        offset = i * 2
        if offset + 1 >= len(buf):
            return
        struct.pack_into('<H', buf, offset, val & 0xFFFF)


def build_fat_bytes(fat, fat_type, total_len):
    buf = bytearray(total_len)
    for i, val in enumerate(fat):
        set_fat_entry(buf, i, val, fat_type)
    return bytes(buf)


def alloc_next_free(fat_list, next_free):
    """Return the next free cluster index at or after next_free."""
    while next_free < len(fat_list) and fat_list[next_free] != 0:
        next_free += 1
    if next_free >= len(fat_list):
        raise RuntimeError("Disk full")
    return next_free


def free_cluster_chain(fat_list, start_cluster, fat_type):
    """Mark all clusters from start_cluster to EOC as free (0) in fat_list."""
    eoc = FAT12_EOC if fat_type == 12 else FAT16_EOC
    c = start_cluster
    seen = set()
    while c < len(fat_list) and c >= 2:
        if c in seen:
            break  # cycle detected
        seen.add(c)
        next_c = fat_list[c]
        fat_list[c] = 0
        if next_c >= eoc:
            break
        c = next_c


def make_alloc_fn(fat_list, next_free):
    """Create a closure that allocates the next free FAT cluster.

    Tracks the running next_free cursor across calls (avoids re-scanning
    already-allocated clusters). Used by inject_common.
    The returned function exposes the running cursor as ``fn.next_free``.
    """
    state = {"next_free": next_free}

    def _alloc():
        c = alloc_next_free(fat_list, state["next_free"])
        state["next_free"] = c + 1
        return c

    _alloc.next_free = state
    return _alloc
