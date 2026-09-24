"""
参考 98Bridge (MIT) 的设计思路独立实现。
来源: https://github.com/NullMagic2/98Bridge
"""

import os

from .base import DiskImage
from .hdi import HDIImage
from .d88 import D88Image
from .raw import RawImage
from .nhd import NHDImage
from .partition import detect_partitions, PartitionEntry
from .fat import NAIZFatFS, FileEntry
from .inject_common import inject_into_hdi, generate_autoexec

__all__ = [
    'DiskImage', 'HDIImage', 'D88Image', 'RawImage', 'NHDImage',
    'detect_partitions', 'PartitionEntry', 'NAIZFatFS', 'FileEntry',
    'open_image', 'create_blank_image',
    'inject_into_hdi', 'generate_autoexec',
]

_EXT_MAP = {
    '.hdi': HDIImage,
    '.d88': D88Image,
    '.d68': D88Image,
    '.d77': D88Image,
    '.nhd': NHDImage,
    '.raw': RawImage,
    '.bin': RawImage,
    '.img': RawImage,
}


def open_image(path):
    ext = os.path.splitext(path)[1].lower()
    cls = _EXT_MAP.get(ext)
    if cls is None:
        raise ValueError(f"Unknown image format: {ext}")
    return cls(path)


def create_blank_image(path, format='hdi', sectors=50277632 // 512, sector_size=512,
                       spt=17, heads=8, cylinders=722):
    if format == 'hdi':
        from .hdi import HDI_HEADER_SIZE, pack_hdi_header
        total_data = sectors * sector_size
        hdr_size = HDI_HEADER_SIZE
        data = bytearray(hdr_size + total_data)
        data[0x00:0x20] = pack_hdi_header(hdr_size, sector_size, total_data,
                                          spt, heads, cylinders)
        with open(path, 'wb') as f:
            f.write(data)
        return HDIImage(path)
    else:
        raise ValueError(f"create_blank_image: unsupported format '{format}'")
