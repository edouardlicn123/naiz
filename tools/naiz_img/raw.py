"""
参考 98Bridge (MIT) 的设计思路独立实现。
来源: https://github.com/NullMagic2/98Bridge
"""

import struct
from .base import DiskImage


KNOWN_GEOMETRIES = [
    (0x168000, 512, 8, 77, 26),    # 1.2MB (1024B/sector)
    (0xA8000,  512, 8, 77, 26),    # 720KB
    (0xB40000, 512, 8, 77, 26),    # 5MB (approx.)
]

_SECTOR_SIZES = [128, 256, 512, 1024, 2048, 4096]

def _probe_sector_size(data):
    """Probe sector size from first-sector VBR BPB, or fall back to heuristic."""
    for sz in _SECTOR_SIZES:
        if len(data) % sz == 0:
            vbr = data[:sz]
            if not vbr:
                continue
            if vbr[0] in (0xEB, 0xE9):
                bps = struct.unpack_from('<H', vbr, 0x0B)[0]
                if bps in _SECTOR_SIZES and len(data) % bps == 0:
                    return bps
            if vbr[4:8] == b'IPL1':
                return sz
    for sz in _SECTOR_SIZES:
        if len(data) % sz == 0:
            return sz
    return 512


class RawImage(DiskImage):
    def _parse(self):
        self._sector_size = _probe_sector_size(self._data)
        self._total_sectors = len(self._data) // self._sector_size
