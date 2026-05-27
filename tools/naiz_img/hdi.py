"""
参考 98Bridge (MIT) 的设计思路独立实现。
来源: https://github.com/NullMagic2/98Bridge
"""

import struct
from .base import DiskImage


HDI_HEADER_SIZE = 4096


class HDIImage(DiskImage):
    def _parse(self):
        hdr_size = struct.unpack_from('<I', self._data, 0x08)[0]
        sec_size = struct.unpack_from('<I', self._data, 0x10)[0]
        spt      = struct.unpack_from('<I', self._data, 0x14)[0]
        heads    = struct.unpack_from('<I', self._data, 0x18)[0]
        cyls     = struct.unpack_from('<I', self._data, 0x1C)[0]
        self._sector_size = sec_size
        self._raw_offset  = hdr_size
        self._total_sectors = (len(self._data) - hdr_size) // sec_size
        self._spt = spt
        self._heads = heads
        self._cyls = cyls

    @property
    def spt(self):
        return self._spt

    @property
    def heads(self):
        return self._heads

    @property
    def cylinders(self):
        return self._cyls

    def read_sector(self, lba):
        off = self._raw_offset + lba * self._sector_size
        return bytes(self._data[off:off + self._sector_size])

    def write_sector(self, lba, data):
        off = self._raw_offset + lba * self._sector_size
        self._data[off:off + self._sector_size] = data[:self._sector_size]
