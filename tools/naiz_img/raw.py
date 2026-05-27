"""
参考 98Bridge (MIT) 的设计思路独立实现。
来源: https://github.com/NullMagic2/98Bridge
"""

from .base import DiskImage


KNOWN_GEOMETRIES = [
    (0x168000, 512, 8, 77, 26),    # 1.2MB (1024B/sector)
    (0xA8000,  512, 8, 77, 26),    # 720KB
    (0xB40000, 512, 8, 77, 26),    # 5MB (approx.)
]


class RawImage(DiskImage):
    def _parse(self):
        size = len(self._data)
        self._sector_size = 512
        if size % 1024 == 0 and size % 512 != 0:
            self._sector_size = 1024
        self._total_sectors = size // self._sector_size
