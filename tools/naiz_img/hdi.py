"""
参考 98Bridge (MIT) 的设计思路独立实现。
来源: https://github.com/NullMagic2/98Bridge
"""

import logging
import struct
from .base import DiskImage

HDI_HEADER_SIZE = 4096

# HDI header geometry field offsets (all <I little-endian)
_OFF_DATA_SIZE = 0x0C
_OFF_SEC_SIZE  = 0x10
_OFF_SPT       = 0x14
_OFF_HEADS     = 0x18
_OFF_CYLS      = 0x1C


def parse_hdi_header(data):
    """Unpack the geometry fields of an HDI header into a dict."""
    hdr_size = struct.unpack_from('<I', data, 0x08)[0]
    sec_size = struct.unpack_from('<I', data, _OFF_SEC_SIZE)[0]
    spt      = struct.unpack_from('<I', data, _OFF_SPT)[0]
    heads    = struct.unpack_from('<I', data, _OFF_HEADS)[0]
    cyls     = struct.unpack_from('<I', data, _OFF_CYLS)[0]
    return {'hdr_size': hdr_size, 'sec_size': sec_size,
            'spt': spt, 'heads': heads, 'cyls': cyls}


def pack_hdi_header(hdr_size, sec_size, data_size, spt, heads, cyls):
    """Build the 0x20-byte HDI header geometry block."""
    data = bytearray(0x20)
    struct.pack_into('<I', data, 0x04, 0)
    struct.pack_into('<I', data, 0x08, hdr_size)
    struct.pack_into('<I', data, _OFF_DATA_SIZE, data_size)
    struct.pack_into('<I', data, _OFF_SEC_SIZE, sec_size)
    struct.pack_into('<I', data, _OFF_SPT, spt)
    struct.pack_into('<I', data, _OFF_HEADS, heads)
    struct.pack_into('<I', data, _OFF_CYLS, cyls)
    return bytes(data)


_logger = logging.getLogger(__name__)


class HDIImage(DiskImage):
    def _parse(self):
        if len(self._data) < 32:
            raise ValueError(f"HDI too small: {len(self._data)} bytes")
        geo = parse_hdi_header(self._data)
        sec_size = geo['sec_size']
        hdr_size = geo['hdr_size']
        if sec_size <= 0 or hdr_size < HDI_HEADER_SIZE or hdr_size > len(self._data):
            raise ValueError(f"Invalid HDI header: sec_size={sec_size}, hdr_size={hdr_size}")
        self._sector_size = sec_size
        self._raw_offset  = hdr_size
        remainder = (len(self._data) - hdr_size) % sec_size
        if remainder:
            _logger.warning("HDI data area has %d trailing bytes beyond sector alignment", remainder)
        self._total_sectors = (len(self._data) - hdr_size) // sec_size
        self._spt = geo['spt']
        self._heads = geo['heads']
        self._cyls = geo['cyls']

    @property
    def spt(self):
        return self._spt

    @property
    def heads(self):
        return self._heads

    @property
    def cylinders(self):
        return self._cyls
