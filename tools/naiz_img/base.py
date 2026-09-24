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
        self._raw_offset = 0
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
        off = self._raw_offset + lba * self._sector_size
        n = self._sector_size
        if off + n > len(self._data):
            raise IndexError(f"read_sector LBA {lba} out of range")
        return bytes(self._data[off:off + n])

    def read_sectors(self, lba, count):
        out = bytearray()
        for i in range(count):
            out.extend(self.read_sector(lba + i))
        return bytes(out)

    def write_sector(self, lba, data):
        off = self._raw_offset + lba * self._sector_size
        end = off + self._sector_size
        if end > len(self._data):
            raise IndexError(f"write_sector LBA {lba} out of range")
        chunk = data[:self._sector_size]
        if len(chunk) < self._sector_size:
            chunk = chunk.ljust(self._sector_size, b'\0')
        self._data[off:end] = chunk

    def save(self, path=None):
        dst = path or self.path
        with open(dst, 'wb') as f:
            f.write(self._data)
