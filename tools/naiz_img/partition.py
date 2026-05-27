"""
参考 98Bridge (MIT) 的设计思路独立实现。
来源: https://github.com/NullMagic2/98Bridge
"""

import struct
from dataclasses import dataclass


@dataclass
class PartitionEntry:
    scheme: str
    type_id: int
    byte_offset: int
    byte_size: int


def detect_mbr(img):
    sec0 = img.read_sector(0)
    if sec0[0x1FE:0x200] != b'\x55\xAA':
        return []
    parts = []
    for i in range(4):
        off = 0x1BE + i * 16
        if off + 16 > len(sec0):
            break
        typ = sec0[off + 4]
        if typ == 0:
            continue
        lba = struct.unpack_from('<I', sec0, off + 8)[0]
        size = struct.unpack_from('<I', sec0, off + 12)[0]
        parts.append(PartitionEntry("MBR", typ, lba * img.sector_size, size * img.sector_size))
    return parts


def detect_pc98(img):
    sec0 = img.read_sector(0)
    if sec0[4:8] != b'IPL1':
        return []
    sec1 = img.read_sector(1)
    spt = getattr(img, 'spt', 17)
    heads = getattr(img, 'heads', 8)
    if callable(spt):
        spt = spt()
    if callable(heads):
        heads = heads()
    parts = []
    for i in range(16):
        off = i * 32
        if off + 32 > len(sec1):
            break
        entry = sec1[off:off + 32]
        if all(b == 0 for b in entry):
            continue
        sys_id = entry[1]
        head = entry[4]
        sector = entry[5]
        cyl = struct.unpack_from('<H', entry, 6)[0]
        lba = cyl * heads * spt + head * spt + sector
        size_sectors = struct.unpack_from('<I', entry, 12)[0]
        byte_off = lba * img.sector_size
        byte_size = size_sectors
        parts.append(PartitionEntry("PC-98", sys_id, byte_off, byte_size))
    return parts


def detect_partitions(img):
    parts = detect_mbr(img)
    if parts:
        return parts
    return detect_pc98(img)
