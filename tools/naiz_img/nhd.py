"""
参考 98Bridge (MIT) 的设计思路独立实现。
来源: https://github.com/NullMagic2/98Bridge
"""

import logging
from .base import DiskImage

_logger = logging.getLogger(__name__)


NHD_HEADER_SIZE = 512


class NHDImage(DiskImage):
    def _parse(self):
        header = self._data[:NHD_HEADER_SIZE]
        if not header.startswith(b'T98HDDIMAGE.R0\0'):
            raise ValueError("Not a valid NHD image")
        sec_size = 512
        spt = 0
        heads = 0
        cyls = 0
        for line in header.decode('ascii', errors='replace').split('\n'):
            line = line.strip()
            if '=' in line:
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip()
                if k == 'bytes/sector':
                    sec_size = int(v)
                elif k == 'sectors/track':
                    spt = int(v)
                elif k == 'heads':
                    heads = int(v)
                elif k == 'cylinders':
                    cyls = int(v)
        self._sector_size = sec_size
        if sec_size <= 0:
            raise ValueError(f'NHD invalid bytes/sector: {sec_size}')
        self._raw_offset = NHD_HEADER_SIZE
        remainder = (len(self._data) - NHD_HEADER_SIZE) % sec_size
        if remainder:
            _logger.warning("NHD data area has %d trailing bytes beyond sector alignment", remainder)
        self._total_sectors = (len(self._data) - NHD_HEADER_SIZE) // sec_size
        self._spt = spt
        self._heads = heads
        self._cyls = cyls
