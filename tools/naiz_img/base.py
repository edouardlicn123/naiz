"""
参考 98Bridge (MIT) 的设计思路独立实现。
来源: https://github.com/NullMagic2/98Bridge
"""


class DiskImage:
    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            self._data = bytearray(f.read())
        self._sector_size = 512
        self._total_sectors = 0
        self._parse()

    def _parse(self):
        raise NotImplementedError

    @property
    def sector_size(self):
        return self._sector_size

    @property
    def total_sectors(self):
        return self._total_sectors

    def read_sector(self, lba):
        off = lba * self._sector_size
        return bytes(self._data[off:off + self._sector_size])

    def read_sectors(self, lba, count):
        out = bytearray()
        for i in range(count):
            out.extend(self.read_sector(lba + i))
        return bytes(out)

    def write_sector(self, lba, data):
        off = lba * self._sector_size
        end = off + self._sector_size
        self._data[off:end] = data[:self._sector_size]

    def save(self, path=None):
        dst = path or self.path
        with open(dst, 'wb') as f:
            f.write(self._data)
