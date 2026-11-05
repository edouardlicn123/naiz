"""TOC archive writer shared by IMAGE.DAT and SCENE.DAT.

Single source of truth for the on-disk archive layout:

    uint32 count
    count x { char name[12]; uint32 offset(abs); uint32 size }    20 B/entry
    concatenated data blobs

`make_toc_archive()` reproduces byte-for-byte the writer that built IMAGE.DAT
before this module existed, so pack_images and pack_scenes both call it and
the two archives can never drift apart.
"""

import struct

from naiz_lib.image_dat import IMAGE_DAT_HEADER, IMAGE_DAT_TOC_SIZE


def make_toc_archive(entries):
    """Serialize name/data entries into archive bytes.

    entries: iterable of (name, data); name is ASCII bytes <= 12 chars
             (trailing NUL padding added), data is the raw entry bytes.
             A legal archive hole is expressed with data=b'' (size 0),
             matching the empty id slots IMAGE.DAT uses for sparse ASSETS.DB.
    """
    prepared = []
    for name, data in entries:
        if isinstance(name, str):
            name = name.encode('ascii', errors='replace')
        if len(name) > 12:
            raise ValueError(f"TOC name too long ({len(name)} > 12): {name!r}")
        prepared.append((name.ljust(12, b'\0'), data))

    count = len(prepared)
    header_size = IMAGE_DAT_HEADER + count * IMAGE_DAT_TOC_SIZE
    buf = bytearray(struct.pack('<I', count))
    offset = header_size
    for name, data in prepared:
        buf.extend(name)
        buf.extend(struct.pack('<II', offset, len(data)))
        offset += len(data)
    for _, data in prepared:
        buf.extend(data)
    return bytes(buf)