"""
参考 98Bridge (MIT) 的设计思路独立实现。
来源: https://github.com/NullMagic2/98Bridge
"""

import struct
from .base import DiskImage


D88_HEADER_SIZE = 0x2B0
D88_MAX_TRACKS = 164


class D88Image(DiskImage):
    def _parse(self):
        if len(self._data) < D88_HEADER_SIZE:
            raise ValueError(
                f'D88 header truncated: need {D88_HEADER_SIZE} bytes, got {len(self._data)}')
        self._disk_type = struct.unpack_from('<B', self._data, 0x1A)[0]
        self._track_offsets = []
        for i in range(D88_MAX_TRACKS):
            off = struct.unpack_from('<I', self._data, 0x20 + i * 4)[0]
            if off == 0:
                break
            self._track_offsets.append(off)
        self._sector_size = 512
        self._total_sectors = 0
        for toff in self._track_offsets:
            if toff == 0:
                break
            pos = toff
            while pos < len(self._data):
                if pos + 4 > len(self._data):
                    break
                r = self._data[pos + 2]
                n = self._data[pos + 3]
                if n > 6:
                    raise ValueError(f'D88 invalid sector-size exponent n={n} at 0x{pos:X}')
                sec_size = 128 << n
                self._total_sectors += 1
                pos += 16 + sec_size
                if r == 0:
                    break

    def _find_sector(self, lba):
        count = 0
        for toff in self._track_offsets:
            if toff == 0:
                break
            pos = toff
            while pos < len(self._data):
                if pos + 4 > len(self._data):
                    break
                n = self._data[pos + 3]
                sec_size = 128 << n
                r = self._data[pos + 2]
                if count == lba:
                    return pos, sec_size
                count += 1
                pos += 16 + sec_size
                if r == 0:
                    break
        return -1, 0

    def read_sector(self, lba):
        pos, sec_size = self._find_sector(lba)
        if pos < 0:
            raise IndexError(f"LBA {lba} out of range")
        if pos + 16 + sec_size > len(self._data):
            raise IndexError(f"D88 read_sector LBA {lba} truncated")
        return bytes(self._data[pos + 16:pos + 16 + sec_size])

    def write_sector(self, lba, data):
        pos, sec_size = self._find_sector(lba)
        if pos < 0:
            raise IndexError(f"LBA {lba} out of range")
        if pos + 16 + sec_size > len(self._data):
            raise IndexError(f"D88 write_sector LBA {lba} out of range")
        self._data[pos + 16:pos + 16 + sec_size] = data[:sec_size]
