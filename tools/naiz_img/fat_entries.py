"""
fat_entries.py — FAT directory entry structures and 8.3 name helpers.

Shared by fat_fs.py and external callers. Imported/re-exported via fat.py.
"""

import struct


ATTR_READ_ONLY = 0x01
ATTR_HIDDEN    = 0x02
ATTR_SYSTEM    = 0x04
ATTR_VOLUME_ID = 0x08
ATTR_DIRECTORY = 0x10
ATTR_ARCHIVE   = 0x20
ATTR_LFN       = 0x0F

ATTR_SYSTEM_FILE = ATTR_READ_ONLY | ATTR_HIDDEN | ATTR_SYSTEM | ATTR_ARCHIVE

FAT12_EOC = 0x0FF8
FAT16_EOC = 0xFFF8

SYSTEM_FILES = {'IO.SYS', 'MSDOS.SYS', 'DBLSPACE.BIN'}


class FileEntry:
    __slots__ = ('name', 'ext', 'attr', 'cluster', 'size', 'children')

    def __init__(self, name, ext, attr, cluster, size):
        if name is None: name = b''
        if ext is None: ext = b''
        self.name = name.strip()
        self.ext = ext.strip()
        self.attr = attr
        self.cluster = cluster
        self.size = size
        self.children = {}

    @property
    def is_directory(self):
        return bool(self.attr & ATTR_DIRECTORY)

    @property
    def display_name(self):
        return self.name if not self.ext else f"{self.name}.{self.ext}"


def _unique_83(name8, ext3, used):
    key = name8 + ext3
    if key not in used:
        used.add(key)
        return name8, ext3
    base = name8.rstrip(b' ')
    for n in range(1, 1000):
        suffix = f"~{n}".encode('ascii')
        mangled = base[:8 - len(suffix)] + suffix
        mangled = mangled.ljust(8, b' ')
        key = mangled + ext3
        if key not in used:
            used.add(key)
            return mangled, ext3
    raise RuntimeError("Cannot generate unique 8.3 name")


def make_fat_entry(name8, ext3, attr, cluster, size, timestamp=None):
    e = bytearray(32)
    e[0:8] = name8[:8]
    e[8:11] = ext3[:3]
    e[11] = attr
    if cluster > 0xFFFF:
        print(f"WARN: make_fat_entry cluster {cluster} truncated to 16-bit")
    if size > 0xFFFFFFFF:
        print(f"WARN: make_fat_entry size {size} truncated to 32-bit")
    struct.pack_into('<H', e, 26, cluster & 0xFFFF)
    struct.pack_into('<I', e, 28, size & 0xFFFFFFFF)
    if timestamp is None:
        import datetime
        timestamp = datetime.datetime.now()
    date = ((timestamp.year - 1980) << 9) | (timestamp.month << 5) | timestamp.day
    time = (timestamp.hour << 11) | (timestamp.minute << 5) | (timestamp.second // 2)
    struct.pack_into('<H', e, 22, time)
    struct.pack_into('<H', e, 24, date)
    return bytes(e)


def get_entry_cluster(data, off):
    """Read the first-cluster field (offset 26) of a 32-byte dir entry."""
    return struct.unpack_from('<H', data, off + 26)[0]


def get_entry_size(data, off):
    """Read the size field (offset 28) of a 32-byte dir entry."""
    return struct.unpack_from('<I', data, off + 28)[0]


def set_entry_cluster(data, off, cluster):
    """Patch the first-cluster field (offset 26) of a 32-byte dir entry."""
    struct.pack_into('<H', data, off + 26, cluster & 0xFFFF)


def set_entry_size(data, off, size):
    """Patch the size field (offset 28) of a 32-byte dir entry."""
    struct.pack_into('<I', data, off + 28, size & 0xFFFFFFFF)
