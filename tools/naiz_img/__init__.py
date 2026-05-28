"""
参考 98Bridge (MIT) 的设计思路独立实现。
来源: https://github.com/NullMagic2/98Bridge
"""

import os

from .base import DiskImage
from .hdi import HDIImage
from .fdi import FDIImage
from .d88 import D88Image
from .raw import RawImage
from .nhd import NHDImage
from .partition import detect_partitions, PartitionEntry
from .fat import NAIZFatFS, FileEntry
from .inject_common import inject_into_hdi, generate_autoexec

__all__ = [
    'DiskImage', 'HDIImage', 'FDIImage', 'D88Image', 'RawImage', 'NHDImage',
    'detect_partitions', 'PartitionEntry', 'NAIZFatFS', 'FileEntry',
    'open_image', 'create_blank_image',
    'inject_into_hdi', 'generate_autoexec',
]

_EXT_MAP = {
    '.hdi': HDIImage,
    '.fdi': FDIImage,
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
        import struct
        total_data = sectors * sector_size
        hdr_size = 4096
        data = bytearray(hdr_size + total_data)
        struct.pack_into('<I', data, 0x04, 0)
        struct.pack_into('<I', data, 0x08, hdr_size)
        struct.pack_into('<I', data, 0x0C, total_data)
        struct.pack_into('<I', data, 0x10, sector_size)
        struct.pack_into('<I', data, 0x14, spt)
        struct.pack_into('<I', data, 0x18, heads)
        struct.pack_into('<I', data, 0x1C, cylinders)
        with open(path, 'wb') as f:
            f.write(data)
        return HDIImage(path)
    else:
        raise ValueError(f"create_blank_image: unsupported format '{format}'")
