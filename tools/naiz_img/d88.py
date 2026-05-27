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
                c = self._data[pos]
                h = self._data[pos + 1]
                r = self._data[pos + 2]
                n = self._data[pos + 3]
                sec_size = 128 << (n & 0x03) if n <= 3 else 1024
                self._total_sectors += 1
                pos += 16 + sec_size
                if r == 0:
                    break

    def read_sector(self, lba):
        count = 0
        for toff in self._track_offsets:
            if toff == 0:
                break
            pos = toff
            while pos < len(self._data):
                if pos + 4 > len(self._data):
                    break
                n = self._data[pos + 3]
                sec_size = 128 << (n & 0x03) if n <= 3 else 1024
                if count == lba:
                    return bytes(self._data[pos + 16:pos + 16 + sec_size])
                count += 1
                pos += 16 + sec_size
                if self._data[pos - 16 + 2] == 0:
                    break
        raise IndexError(f"LBA {lba} out of range")

    def write_sector(self, lba, data):
        count = 0
        for toff in self._track_offsets:
            if toff == 0:
                break
            pos = toff
            while pos < len(self._data):
                if pos + 4 > len(self._data):
                    break
                n = self._data[pos + 3]
                sec_size = 128 << (n & 0x03) if n <= 3 else 1024
                if count == lba:
                    self._data[pos + 16:pos + 16 + len(data)] = data[:sec_size]
                    return
                count += 1
                pos += 16 + sec_size
                if self._data[pos - 16 + 2] == 0:
                    break
        raise IndexError(f"LBA {lba} out of range")
