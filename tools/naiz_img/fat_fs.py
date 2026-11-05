"""
fat_fs.py — NAIZFatFS: FAT16/12 filesystem reader/writer over an image.

Parses VBR geometry, builds an in-memory directory tree, and provides
read/write primitives for FAT entries, root/subdirectories and clusters.
Imported/re-exported via fat.py.
"""

import os
import sys
import struct
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from naiz_lib import to_dos_name
from .partition import detect_partitions
from .fat_entries import (
    ATTR_DIRECTORY, ATTR_LFN, ATTR_VOLUME_ID, ATTR_ARCHIVE,
    FAT12_EOC, FAT16_EOC,
    FileEntry, make_fat_entry,
    get_entry_cluster, get_entry_size,
    set_entry_cluster, set_entry_size,
)
from .fat_table import (
    build_fat_bytes, set_fat_entry, alloc_next_free,
    free_cluster_chain as free_chain,
)


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

        if vbr[0] not in (0xEB, 0xE9):
            raise ValueError("No valid VBR (no jmp at offset 0)")
        self.bytes_per_sector = struct.unpack_from('<H', vbr, 0x0B)[0]
        if self.bytes_per_sector not in (512, 1024, 2048, 4096):
            raise ValueError(f"Invalid bytes_per_sector: {self.bytes_per_sector}")
        if self.bytes_per_sector % img.sector_size != 0:
            raise ValueError(
                f"VBR bytes_per_sector ({self.bytes_per_sector}) is not a "
                f"multiple of img.sector_size ({img.sector_size})")
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
            if self.fat_sectors == 0:
                raise ValueError("FAT32 not supported (fat_sectors == 0)")

        self.root_sectors = (self.root_entries * 32 + self.bytes_per_sector - 1) // self.bytes_per_sector
        self.fat_offset = self.part_offset + self.reserved_sectors * self.bytes_per_sector
        self.root_offset = self.fat_offset + self.num_fats * self.fat_sectors * self.bytes_per_sector
        self.data_offset = self.root_offset + self.root_sectors * self.bytes_per_sector
        self.cluster_size = self.bytes_per_sector * self.sectors_per_cluster

        data_sectors = self.total_sectors - self.reserved_sectors - self.num_fats * self.fat_sectors - self.root_sectors
        total_clusters = data_sectors // self.sectors_per_cluster
        self.fat_type = 12 if total_clusters < 4085 else (16 if total_clusters < 65525 else 32)
        if self.fat_type == 32:
            raise ValueError("FAT32 not supported by this tool (use FAT16)")

        self._fat_data = self._read_bytes(self.fat_offset, self.fat_sectors * self.bytes_per_sector)
        self._max_cluster = total_clusters + 2
        self.root = FileEntry("", "", ATTR_DIRECTORY, 0, 0)
        self._build_tree()

    def _read_bytes(self, abs_offset, length):
        ss = self.img.sector_size
        start_lba = abs_offset // ss
        local_off = abs_offset % ss
        count = (local_off + length + ss - 1) // ss
        if count > 65536:
            raise ValueError(
                f"_read_bytes size too large: offset={abs_offset} length={length}"
                f" -> {count} sectors (limit 65536)")
        data = self.img.read_sectors(start_lba, count)
        if local_off + length > len(data):
            raise ValueError(
                f"_read_bytes OOB: offset={abs_offset} length={length} "
                f"exceeds available data ({len(data)} bytes)")
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

    def sync_fat(self, fat_list):
        """Patch FAT entries in-place, reusing set_fat_entry for packing."""
        self._fat_data = bytearray(
            self._read_bytes(self.fat_offset, self.fat_sectors * self.bytes_per_sector))
        for i, val in enumerate(fat_list):
            set_fat_entry(self._fat_data, i, val, self.fat_type)
        self._fat_data = bytes(self._fat_data)

    def read_root(self):
        return bytearray(self._read_bytes(self.root_offset,
                                          self.root_sectors * self.bytes_per_sector))

    def write_root(self, root_data):
        self._write_bytes(self.root_offset, bytes(root_data))

    def read_fat_list(self):
        return [self._read_fat_entry(i) for i in range(self._max_cluster)]

    @staticmethod
    def iter_dir_entries(data):
        """Yield (offset, 'NAME.EXT', attr) for each entry in a 32-byte dir buffer."""
        i = 0
        while i + 32 <= len(data):
            raw = data[i:i + 32]
            first = raw[0]
            if first == 0:
                break
            if first == 0xE5 or raw[11] == ATTR_LFN or raw[11] == ATTR_VOLUME_ID:
                i += 32
                continue
            ename = raw[0:8].rstrip(b' ').decode('ascii', errors='replace')
            eext = raw[8:11].rstrip(b' ').decode('ascii', errors='replace')
            yield i, f"{ename}.{eext}".upper(), raw[11]
            i += 32

    def write_fat(self, fat_list):
        fat_len = self.fat_sectors * self.bytes_per_sector
        fat_bytes = build_fat_bytes(fat_list, self.fat_type, fat_len)
        for i in range(self.num_fats):
            self._write_bytes(self.fat_offset + i * fat_len, fat_bytes)

    def read_cluster(self, cluster, size=None):
        off = self.data_offset + (cluster - 2) * self.cluster_size
        n = size if size is not None else self.cluster_size
        return self._read_bytes(off, n)

    def write_cluster(self, cluster, data):
        off = self.data_offset + (cluster - 2) * self.cluster_size
        if len(data) < self.cluster_size:
            buf = bytearray(self.cluster_size)
            buf[:len(data)] = data
            self._write_bytes(off, bytes(buf))
        else:
            self._write_bytes(off, data)

    def zero_cluster(self, cluster):
        off = self.data_offset + (cluster - 2) * self.cluster_size
        self._write_bytes(off, b'\x00' * self.cluster_size)

    def free_cluster_chain(self, fat_list, start_cluster):
        free_chain(fat_list, start_cluster, self.fat_type)

    @staticmethod
    def find_entry_offset(root_data, name8, ext3):
        for i in range(len(root_data) // 32):
            off = i * 32
            first = root_data[off]
            if first == 0:
                return None
            if first == 0xE5:
                continue
            if root_data[off + 11] == ATTR_LFN:
                continue
            if root_data[off:off + 8] == name8 and root_data[off + 8:off + 11] == ext3:
                return off
        return None

    @staticmethod
    def find_free_root_slot(root_data, root_entries):
        for i in range(root_entries):
            off = i * 32
            first = root_data[off]
            if first == 0 or first == 0xE5:
                return off
        return None

    @staticmethod
    def alloc_next_free(fat_list, next_free):
        return alloc_next_free(fat_list, next_free)

    def overwrite_entry(self, root_data, entry_offset, new_data, fat_list, alloc_fn):
        """Overwrite an existing dir entry's file in-place, or reallocate clusters.

        Returns True if written in-place, False if clusters were reallocated.
        """
        fat_eoc = FAT12_EOC if self.fat_type == 12 else FAT16_EOC
        cluster = get_entry_cluster(root_data, entry_offset)
        chain = self._get_cluster_chain(cluster)
        capacity = len(chain) * self.cluster_size

        if len(new_data) <= capacity:
            buf = new_data + b'\x00' * (capacity - len(new_data))
            for i, c in enumerate(chain):
                chunk = buf[i * self.cluster_size:(i + 1) * self.cluster_size]
                self.write_cluster(c, chunk)
            set_entry_size(root_data, entry_offset, len(new_data))
            return True

        num_cl = (len(new_data) + self.cluster_size - 1) // self.cluster_size
        new_chain = [alloc_fn() for _ in range(num_cl)]
        for c in new_chain:
            self.zero_cluster(c)
        for i in range(len(new_chain) - 1):
            fat_list[new_chain[i]] = new_chain[i + 1]
        fat_list[new_chain[-1]] = fat_eoc
        for c in chain:
            fat_list[c] = 0
        for i, c in enumerate(new_chain):
            chunk = new_data[i * self.cluster_size:(i + 1) * self.cluster_size]
            self.write_cluster(c, chunk)
        set_entry_cluster(root_data, entry_offset, new_chain[0])
        set_entry_size(root_data, entry_offset, len(new_data))
        return False

    def write_file_entry(self, root_data, slot, name8, ext3, data, fat_list, alloc_fn, attr):
        """Write a brand-new file into a free root slot.

        Returns the first cluster (0 for an empty file).
        """
        fat_eoc = FAT12_EOC if self.fat_type == 12 else FAT16_EOC
        num_cl = (len(data) + self.cluster_size - 1) // self.cluster_size
        if num_cl == 0:
            entry = make_fat_entry(name8, ext3, attr, 0, 0)
            root_data[slot:slot + 32] = entry
            return 0
        chain = [alloc_fn() for _ in range(num_cl)]
        for c in chain:
            self.zero_cluster(c)
        for i in range(len(chain) - 1):
            fat_list[chain[i]] = chain[i + 1]
        fat_list[chain[-1]] = fat_eoc
        for i, c in enumerate(chain):
            chunk = data[i * self.cluster_size:(i + 1) * self.cluster_size]
            self.write_cluster(c, chunk)
        entry = make_fat_entry(name8, ext3, attr, chain[0], len(data))
        root_data[slot:slot + 32] = entry
        return chain[0]

    def _read_fat_entry(self, cluster):
        if cluster < 0 or cluster >= self._max_cluster:
            return FAT16_EOC if self.fat_type == 16 else FAT12_EOC  # sentinel: stop chain
        if self.fat_type == 12:
            offset = cluster + (cluster // 2)
            if offset + 1 >= len(self._fat_data):
                return FAT12_EOC
            word = struct.unpack_from('<H', self._fat_data, offset)[0]
            return (word >> 4) if (cluster & 1) else (word & 0x0FFF)
        else:
            offset = cluster * 2
            if offset + 2 > len(self._fat_data):
                return FAT16_EOC  # out of FAT range: end chain
            return struct.unpack_from('<H', self._fat_data, offset)[0]

    def _get_cluster_chain(self, start):
        chain = []
        c = start
        eoc = FAT12_EOC if self.fat_type == 12 else FAT16_EOC
        seen = set()
        while c >= 2 and c < eoc:
            if c in seen:
                break  # cycle detected
            seen.add(c)
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
            cluster = get_entry_cluster(raw, 0)
            if cluster >= self._max_cluster:
                print(f"WARN: entry {name}.{ext} cluster {cluster} >= max {self._max_cluster}, treating as empty")
                cluster = 0
            size = get_entry_size(raw, 0)
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
                    off = self.data_offset + (c - 2) * self.cluster_size  # cluster to byte offset
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
