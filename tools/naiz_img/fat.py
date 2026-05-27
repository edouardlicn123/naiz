"""
参考 98Bridge (MIT) 的设计思路独立实现。
来源: https://github.com/NullMagic2/98Bridge
"""

import os
import struct
from .hdi import HDIImage
from .partition import detect_partitions


ATTR_DIRECTORY = 0x10
ATTR_ARCHIVE   = 0x20
ATTR_SYSTEM    = 0x04
ATTR_VOLUME_ID = 0x08
ATTR_LFN       = 0x0F

FAT12_EOC = 0x0FF8
FAT16_EOC = 0xFFF8

SYSTEM_FILES = {'IO.SYS', 'MSDOS.SYS'}


class FileEntry:
    __slots__ = ('name', 'ext', 'attr', 'cluster', 'size', 'children')

    def __init__(self, name, ext, attr, cluster, size):
        self.name = name.strip()
        self.ext = ext.strip()
        self.attr = attr
        self.cluster = cluster
        self.size = size
        self.children = {}

    @property
    def is_directory(self):
        return bool(self.attr & ATTR_DIRECTORY)

    @property
    def display_name(self):
        return self.name if not self.ext else f"{self.name}.{self.ext}"


def _to_dos_name(name):
    name = name.upper()
    if '.' in name:
        base, ext = name.rsplit('.', 1)
    else:
        base, ext = name, ''
    base = base[:8].ljust(8, ' ')
    ext = ext[:3].ljust(3, ' ')
    return base.encode('ascii', errors='replace'), ext.encode('ascii', errors='replace')


def _unique_83(name8, ext3, used):
    key = name8 + ext3
    if key not in used:
        used.add(key)
        return name8, ext3
    base = name8.rstrip(b' ')
    for n in range(1, 1000):
        suffix = f"~{n}".encode('ascii')
        mangled = base[:8 - len(suffix)] + suffix
        mangled = mangled.ljust(8, b' ')
        key = mangled + ext3
        if key not in used:
            used.add(key)
            return mangled, ext3
    raise RuntimeError("Cannot generate unique 8.3 name")


def _make_entry(name8, ext3, attr, cluster, size):
    e = bytearray(32)
    e[0:8] = name8[:8]
    e[8:11] = ext3[:3]
    e[11] = attr
    struct.pack_into('<H', e, 26, cluster & 0xFFFF)
    struct.pack_into('<I', e, 28, size & 0xFFFFFFFF)
    return bytes(e)


def _alloc_cluster(fat, next_free):
    while next_free[0] < len(fat):
        if fat[next_free[0]] == 0:
            c = next_free[0]
            next_free[0] += 1
            return c
        next_free[0] += 1
    raise RuntimeError("Disk full")


def _build_fat_bytes(fat, fat_type, total_len):
    buf = bytearray(total_len)
    if fat_type == 12:
        for i, val in enumerate(fat):
            offset = i + (i // 2)
            if offset + 1 >= len(buf):
                break
            word = struct.unpack_from('<H', buf, offset)[0]
            if i & 1:
                word = (word & 0x000F) | ((val & 0x0FFF) << 4)
            else:
                word = (word & 0xF000) | (val & 0x0FFF)
            struct.pack_into('<H', buf, offset, word)
    else:
        for i, val in enumerate(fat):
            offset = i * 2
            if offset + 1 >= len(buf):
                break
            struct.pack_into('<H', buf, offset, val & 0xFFFF)
    return bytes(buf)


class NAIZFatFS:
    def __init__(self, img, part_offset=None):
        self.img = img
        self.part_offset = part_offset

        if part_offset is None:
            parts = detect_partitions(img)
            if not parts:
                raise ValueError("No partition found")
            self.part_offset = parts[0].byte_offset

        vbr_lba = self.part_offset // img.sector_size
        vbr = img.read_sector(vbr_lba)

        if vbr[0] != 0xEB:
            raise ValueError("No valid VBR (no jmp at offset 0)")
        self.bytes_per_sector = struct.unpack_from('<H', vbr, 0x0B)[0]
        if self.bytes_per_sector not in (512, 1024, 2048):
            raise ValueError(f"Invalid bytes_per_sector: {self.bytes_per_sector}")
        self.sectors_per_cluster = vbr[0x0D]
        self.reserved_sectors = struct.unpack_from('<H', vbr, 0x0E)[0]
        self.num_fats = vbr[0x10]
        self.root_entries = struct.unpack_from('<H', vbr, 0x11)[0]
        self.media_descriptor = vbr[0x15]
        fat_sectors_16 = struct.unpack_from('<H', vbr, 0x16)[0]

        total_16 = struct.unpack_from('<H', vbr, 0x13)[0]
        total_32 = struct.unpack_from('<I', vbr, 0x20)[0]
        self.total_sectors = total_16 if total_16 else total_32

        if fat_sectors_16:
            self.fat_sectors = fat_sectors_16
        else:
            self.fat_sectors = struct.unpack_from('<I', vbr, 0x24)[0]

        self.root_sectors = (self.root_entries * 32 + self.bytes_per_sector - 1) // self.bytes_per_sector
        self.fat_offset = self.part_offset + self.reserved_sectors * self.bytes_per_sector
        self.root_offset = self.fat_offset + self.num_fats * self.fat_sectors * self.bytes_per_sector
        self.data_offset = self.root_offset + self.root_sectors * self.bytes_per_sector
        self.cluster_size = self.bytes_per_sector * self.sectors_per_cluster

        data_sectors = self.total_sectors - self.reserved_sectors - self.num_fats * self.fat_sectors - self.root_sectors
        total_clusters = data_sectors // self.sectors_per_cluster
        self.fat_type = 12 if total_clusters < 4085 else 16

        self._fat_data = self._read_bytes(self.fat_offset, self.fat_sectors * self.bytes_per_sector)
        self._max_cluster = total_clusters + 2
        self.root = FileEntry("", "", ATTR_DIRECTORY, 0, 0)
        self._build_tree()

    def _read_bytes(self, abs_offset, length):
        ss = self.img.sector_size
        start_lba = abs_offset // ss
        count = (length + ss - 1) // ss
        data = self.img.read_sectors(start_lba, count)
        local_off = abs_offset % ss
        return data[local_off:local_off + length]

    def _write_bytes(self, abs_offset, data):
        pos = 0
        ss = self.img.sector_size
        while pos < len(data):
            lba = (abs_offset + pos) // ss
            sec_off = (abs_offset + pos) % ss
            can_write = min(ss - sec_off, len(data) - pos)
            if sec_off == 0 and can_write == ss:
                self.img.write_sector(lba, data[pos:pos + ss])
            else:
                sec = bytearray(self.img.read_sector(lba))
                sec[sec_off:sec_off + can_write] = data[pos:pos + can_write]
                self.img.write_sector(lba, bytes(sec))
            pos += can_write

    def _read_fat_entry(self, cluster):
        if self.fat_type == 12:
            offset = cluster + (cluster // 2)
            word = struct.unpack_from('<H', self._fat_data, offset)[0]
            return (word >> 4) if (cluster & 1) else (word & 0x0FFF)
        else:
            return struct.unpack_from('<H', self._fat_data, cluster * 2)[0]

    def _get_cluster_chain(self, start):
        chain = []
        c = start
        eoc = FAT12_EOC if self.fat_type == 12 else FAT16_EOC
        while c >= 2 and c < eoc:
            chain.append(c)
            c = self._read_fat_entry(c)
        return chain

    def _parse_dir(self, data):
        entries = []
        i = 0
        while i + 32 <= len(data):
            raw = data[i:i + 32]
            first = raw[0]
            if first == 0:
                break
            if first == 0xE5:
                i += 32
                continue
            attr = raw[11]
            if attr == ATTR_LFN:
                i += 32
                continue
            if attr == ATTR_VOLUME_ID or attr == (ATTR_VOLUME_ID | ATTR_ARCHIVE):
                i += 32
                continue
            name = raw[0:8].decode('ascii', errors='replace')
            ext = raw[8:11].decode('ascii', errors='replace')
            cluster = struct.unpack_from('<H', raw, 26)[0]
            size = struct.unpack_from('<I', raw, 28)[0]
            entries.append(FileEntry(name, ext, attr, cluster, size))
            i += 32
        return entries

    def _build_tree(self):
        root_data = self._read_bytes(self.root_offset, self.root_sectors * self.bytes_per_sector)
        for e in self._parse_dir(root_data):
            self.root.children[e.display_name.upper()] = e
        self._parse_subdirs(self.root)

    def _parse_subdirs(self, parent):
        for name, entry in list(parent.children.items()):
            if entry.is_directory and entry.name not in ('.', '..'):
                if entry.cluster < 2:
                    continue
                chain = self._get_cluster_chain(entry.cluster)
                data = bytearray()
                for c in chain:
                    off = self.data_offset + (c - 2) * self.cluster_size
                    data.extend(self._read_bytes(off, self.cluster_size))
                for e in self._parse_dir(bytes(data)):
                    if e.name not in ('.', '..'):
                        entry.children[e.display_name.upper()] = e
                self._parse_subdirs(entry)

    def resolve_path(self, path):
        parts = [p for p in path.replace('\\', '/').split('/') if p]
        cur = self.root
        for p in parts:
            if p.upper() not in cur.children:
                return None
            cur = cur.children[p.upper()]
        return cur

    def walk(self, path='/'):
        entries = self.list_dir(path) or []
        for e in entries:
            full = f"{path}/{e.display_name}".replace('//', '/')
            yield full, e
            if e.is_directory:
                yield from self.walk(full)

    def list_dir(self, path='/'):
        e = self.resolve_path(path)
        return list(e.children.values()) if e and e.is_directory else None

    def read_file(self, entry):
        if entry.is_directory:
            raise ValueError(f"{entry.display_name} is a directory")
        if entry.size == 0:
            return b''
        chain = self._get_cluster_chain(entry.cluster)
        data = bytearray()
        for c in chain:
            off = self.data_offset + (c - 2) * self.cluster_size
            data.extend(self._read_bytes(off, self.cluster_size))
        return bytes(data[:entry.size])

    def write_back_from_directory(self, dir_path, save_path=None):
        max_cluster = self._max_cluster
        fat = [0] * max_cluster
        if self.fat_type == 12:
            fat[0] = 0xF00 | (self.media_descriptor & 0xFF)
            fat[1] = 0xFFF
        else:
            fat[0] = 0xFF00 | (self.media_descriptor & 0xFF)
            fat[1] = 0xFFFF
        next_free = [2]

        fat_len = self.fat_sectors * self.bytes_per_sector
        root_len = self.root_sectors * self.bytes_per_sector
        data_len = (self.total_sectors - self.reserved_sectors - self.num_fats * self.fat_sectors - self.root_sectors) * self.bytes_per_sector

        self._write_bytes(self.fat_offset, b'\x00' * fat_len)
        for i in range(1, self.num_fats):
            self._write_bytes(self.fat_offset + i * fat_len, b'\x00' * fat_len)
        self._write_bytes(self.root_offset, b'\x00' * root_len)
        if data_len > 0:
            chunk = 65536
            written = 0
            while written < data_len:
                n = min(chunk, data_len - written)
                self._write_bytes(self.data_offset + written, b'\x00' * n)
                written += n

        counters = {'files': 0, 'dirs': 0, 'skipped': 0}

        def _process_dir(real_path, parent_cluster, is_root):
            nonlocal counters
            entries = bytearray()
            used_names = set()
            items = sorted(os.listdir(real_path))
            if is_root:
                system = [n for n in items if n.upper() in SYSTEM_FILES]
                rest = [n for n in items if n.upper() not in SYSTEM_FILES]
                system.sort(key=lambda n: 0 if n.upper() == 'IO.SYS' else 1)
                items = system + sorted(rest)
            for item_name in items:
                item_path = os.path.join(real_path, item_name)
                if not os.path.exists(item_path):
                    continue
                name8, ext3 = _to_dos_name(item_name)
                name8, ext3 = _unique_83(name8, ext3, used_names)
                if os.path.isdir(item_path):
                    dir_cluster = _alloc_cluster(fat, next_free)
                    eoc = FAT12_EOC if self.fat_type == 12 else FAT16_EOC
                    fat[dir_cluster] = eoc
                    child_data = _process_dir(item_path, dir_cluster, False)
                    full_dir = bytearray()
                    full_dir.extend(_make_entry(b'.       ', b'   ', ATTR_DIRECTORY, dir_cluster, 0))
                    full_dir.extend(_make_entry(b'..      ', b'   ', ATTR_DIRECTORY, parent_cluster if not is_root else 0, 0))
                    full_dir.extend(child_data)
                    remainder = len(full_dir) % self.cluster_size
                    if remainder:
                        full_dir.extend(b'\x00' * (self.cluster_size - remainder))
                    num_cl = len(full_dir) // self.cluster_size
                    chain = [dir_cluster]
                    for _ in range(num_cl - 1):
                        c = _alloc_cluster(fat, next_free)
                        fat[chain[-1]] = c
                        fat[c] = eoc
                        chain.append(c)
                    for i, c in enumerate(chain):
                        chunk = full_dir[i * self.cluster_size:(i + 1) * self.cluster_size]
                        self._write_bytes(self.data_offset + (c - 2) * self.cluster_size, chunk)
                    entries.extend(_make_entry(name8, ext3, ATTR_DIRECTORY, dir_cluster, 0))
                    counters['dirs'] += 1
                else:
                    try:
                        with open(item_path, 'rb') as fh:
                            file_data = fh.read()
                    except (IOError, OSError):
                        counters['skipped'] += 1
                        continue
                    file_size = len(file_data)
                    if file_size > 0:
                        num_cl = (file_size + self.cluster_size - 1) // self.cluster_size
                        chain = []
                        for _ in range(num_cl):
                            c = _alloc_cluster(fat, next_free)
                            if chain:
                                fat[chain[-1]] = c
                            chain.append(c)
                        eoc = FAT12_EOC if self.fat_type == 12 else FAT16_EOC
                        fat[chain[-1]] = eoc
                        for i, c in enumerate(chain):
                            chunk = file_data[i * self.cluster_size:(i + 1) * self.cluster_size]
                            self._write_bytes(self.data_offset + (c - 2) * self.cluster_size, chunk)
                        first_cluster = chain[0]
                    else:
                        first_cluster = 0
                    entries.extend(_make_entry(name8, ext3, ATTR_ARCHIVE, first_cluster, file_size))
                    counters['files'] += 1
            return bytes(entries)

        root_data = _process_dir(dir_path, 0, True)
        self._write_bytes(self.root_offset, root_data)

        fat_data = _build_fat_bytes(fat, self.fat_type, fat_len)
        for i in range(self.num_fats):
            self._write_bytes(self.fat_offset + i * fat_len, fat_data)

        self.img.save(save_path)
        return counters['files'], counters['dirs']
