#!/usr/bin/env python3
"""Read FAT16 partition from base_msdos5_scsi_48m.hdi and list all files."""

import struct
import os

HDI_PATH = os.path.join(os.path.dirname(__file__), "base_msdos5_scsi_48m.hdi")

with open(HDI_PATH, "rb") as f:
    hdi_data = f.read()

# 1. Parse HDI header (32 bytes, 8 x uint32 LE)
hdr = struct.unpack_from('<8I', hdi_data, 0)
raw_offset = hdr[2]
print(f"HDI raw_offset = {raw_offset} (0x{raw_offset:x})")

# 2. Physical sector 0 of the partition is at LBA 136
#    VBR occupies the first DOS logical sector (which may be >512 bytes)
PART_LBA = 136

# Read from raw_offset + PART_LBA * 512
vbr_offset = raw_offset + PART_LBA * 512
vbr = hdi_data[vbr_offset:vbr_offset + 1024]  # read up to 1024 bytes

# BPB fields
bytes_per_sector = struct.unpack_from('<H', vbr, 0x0B)[0]
spc = vbr[0x0D]  # sectors per cluster
reserved = struct.unpack_from('<H', vbr, 0x0E)[0]  # reserved DOS sectors
num_fats = vbr[0x10]
root_entries = struct.unpack_from('<H', vbr, 0x11)[0]
fat_size16 = struct.unpack_from('<H', vbr, 0x16)[0]  # FAT size in DOS sectors

print(f"BytesPerSector = {bytes_per_sector}")
print(f"SectorsPerCluster = {spc}")
print(f"Reserved (DOS sectors) = {reserved}")
print(f"NumFATs = {num_fats}")
print(f"RootEntries = {root_entries}")
print(f"FATsize16 (DOS sectors) = {fat_size16}")

# Physical sector calculations
phys_per_dos = bytes_per_sector // 512
reserved_phys = reserved * phys_per_dos
fat1_phys_lba = PART_LBA + reserved_phys
fat_phys = fat_size16 * phys_per_dos
fat2_phys_lba = fat1_phys_lba + fat_phys
root_phys_lba = fat2_phys_lba + fat_phys
root_phys_bytes = root_entries * 32
root_phys_sectors = (root_phys_bytes + 511) // 512
data_phys_lba = root_phys_lba + root_phys_sectors

print(f"phys_per_dos = {phys_per_dos}")
print(f"reserved_phys = {reserved_phys}")
print(f"fat1_phys_lba = {fat1_phys_lba}")
print(f"fat_phys = {fat_phys}")
print(f"fat2_phys_lba = {fat2_phys_lba}")
print(f"root_phys_lba = {root_phys_lba}")
print(f"root_phys_sectors = {root_phys_sectors}")
print(f"data_phys_lba = {data_phys_lba}")

# 3. Read the FAT (first copy)
fat_offset = raw_offset + fat1_phys_lba * 512
fat_bytes = hdi_data[fat_offset:fat_offset + fat_phys * 512]

# 4. Read root directory
root_offset = raw_offset + root_phys_lba * 512
root_bytes = hdi_data[root_offset:root_offset + root_phys_sectors * 512]

def read_fat_entry(fat, cluster):
    """Return next cluster from FAT16 table."""
    off = cluster * 2
    if off + 2 > len(fat):
        return 0
    return struct.unpack_from('<H', fat, off)[0]

def parse_dir_entry(entry):
    """Parse a 32-byte directory entry."""
    name_raw = entry[0:8]
    ext_raw = entry[8:11]
    attr = entry[11]
    first_cluster = struct.unpack_from('<H', entry, 26)[0]
    size = struct.unpack_from('<I', entry, 28)[0]
    name = name_raw.rstrip(b' ').decode('ascii', errors='replace')
    ext = ext_raw.rstrip(b' ').decode('ascii', errors='replace')
    return name, ext, attr, first_cluster, size

def attr_str(attr):
    parts = []
    if attr & 0x01: parts.append('R')
    if attr & 0x02: parts.append('H')
    if attr & 0x04: parts.append('S')
    if attr & 0x08: parts.append('V')
    if attr & 0x10: parts.append('D')
    if attr & 0x20: parts.append('A')
    return ''.join(parts) if parts else '-'

cluster_size = spc * bytes_per_sector  # bytes per cluster
cluster_phys_sectors = spc * phys_per_dos  # physical sectors per cluster

# 5. Print all files
print("\n=== Root Directory Files ===")
print(f"{'Name':<12} {'Ext':<4} {'Size':>10} {'Attr':<6} {'Cluster':>7}")
print('-' * 45)

files = []
for i in range(root_entries):
    off = i * 32
    entry = root_bytes[off:off + 32]
    if entry[0] == 0x00:
        break  # end of directory
    if entry[0] == 0xE5:
        continue  # deleted entry
    name, ext, attr, cluster, size = parse_dir_entry(entry)
    if attr & 0x08:  # Volume label
        print(f"{name:<12} {'VOL':<4} {'':>10} {'VOL':<6} {'':>7}")
        continue
    files.append((name, ext, attr, cluster, size))
    print(f"{name:<12} {ext:<4} {size:>10} {attr_str(attr):<6} {cluster:>7}")

# 6. Read file contents for CONFIG.SYS and AUTOEXEC.BAT
def read_file_clusters(fat, first_cluster):
    """Read all clusters of a file and return bytes."""
    data = bytearray()
    cluster = first_cluster
    while 0x0002 <= cluster <= 0xFFEF:
        # Cluster data location in physical sectors
        lba = data_phys_lba + (cluster - 2) * cluster_phys_sectors
        offset = raw_offset + lba * 512
        chunk = hdi_data[offset:offset + cluster_size]
        data.extend(chunk)
        next_cluster = read_fat_entry(fat, cluster)
        if next_cluster >= 0xFFF8:
            break
        cluster = next_cluster
    return bytes(data)

print("\n=== Config.SYS ===")
for name, ext, attr, cluster, size in files:
    if name.upper() == 'CONFIG' and ext.upper() == 'SYS':
        content = read_file_clusters(fat_bytes, cluster)[:size]
        print(content.decode('ascii', errors='replace'))
        break

print("\n=== AUTOEXEC.BAT ===")
for name, ext, attr, cluster, size in files:
    if name.upper() == 'AUTOEXEC' and ext.upper() == 'BAT':
        content = read_file_clusters(fat_bytes, cluster)[:size]
        print(content.decode('ascii', errors='replace'))
        break

# 7. Hex dump of root directory (first 20 entries)
print("\n=== Root Directory Hex Dump (first 20 entries) ===")
for i in range(min(20, root_entries)):
    off = i * 32
    entry = root_bytes[off:off + 32]
    hex_str = ' '.join(f'{b:02x}' for b in entry)
    ascii_str = ''.join(chr(b) if 0x20 <= b < 0x7f else '.' for b in entry)
    if entry[0] == 0x00:
        print(f"[{i:2d}] (empty / end)")
        break
    if entry[0] == 0xE5:
        marker = "DELETED"
    else:
        marker = ""
    print(f"[{i:2d}] {hex_str}  {ascii_str}  {marker}")
