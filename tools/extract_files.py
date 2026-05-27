import struct

HDI_PATH = "/home/edo/naiz/pc98msdos5/msdos5.hdi"

with open(HDI_PATH, "rb") as f:
    hdi = f.read(32)
    raw_offset = struct.unpack_from("<I", hdi, 8)[0]
    raw_data_size = struct.unpack_from("<I", hdi, 12)[0]
    print(f"HDI: raw_offset={raw_offset} (0x{raw_offset:x}), raw_data_size={raw_data_size}", flush=True)

PART_LBA = 136
PHYS_SECTOR = 512

with open(HDI_PATH, "rb") as f:
    vbr_offset = raw_offset + PART_LBA * PHYS_SECTOR
    f.seek(vbr_offset)
    vbr = f.read(1024)

    bps = struct.unpack_from("<H", vbr, 0x0B)[0]
    spc = vbr[0x0D]
    reserved = struct.unpack_from("<H", vbr, 0x0E)[0]
    fat_count = vbr[0x10]
    root_entries = struct.unpack_from("<H", vbr, 0x11)[0]
    fats_sectors = struct.unpack_from("<H", vbr, 0x16)[0]

    print(f"VBR: BPS={bps} SPC={spc} Reserved={reserved} FATs={fat_count} FAT_sec={fats_sectors} Root_entries={root_entries}", flush=True)

    dos2phys = bps // PHYS_SECTOR

    fat1_lba = PART_LBA + reserved * dos2phys
    root_lba = PART_LBA + (reserved + fat_count * fats_sectors) * dos2phys
    root_dir_bytes = root_entries * 32
    root_dir_dos_sectors = (root_dir_bytes + bps - 1) // bps
    data_lba = root_lba + root_dir_dos_sectors * dos2phys

    print(f"FAT1 LBA={fat1_lba} Root LBA={root_lba} Data LBA={data_lba}", flush=True)

    f.seek(raw_offset + root_lba * PHYS_SECTOR)
    root_data = f.read(root_dir_dos_sectors * bps)

    def parse_entry(data, off):
        name = data[off:off+8].decode("ascii", errors="replace").rstrip()
        ext = data[off+8:off+11].decode("ascii", errors="replace").rstrip()
        attr = data[off+0x0B]
        first = struct.unpack_from("<H", data, off+0x1A)[0]
        size = struct.unpack_from("<I", data, off+0x1C)[0]
        return name, ext, attr, first, size

    targets = {"CONFIG": "SYS", "AUTOEXEC": "BAT"}
    found = {}

    for i in range(root_entries):
        off = i * 32
        if root_data[off] == 0 or root_data[off] == 0xE5:
            continue
        attr = root_data[off + 0x0B]
        if attr & 0x08:
            continue
        name, ext, attr, first, size = parse_entry(root_data, off)
        key = name.strip()
        if key in targets and ext == targets[key]:
            found[key] = (first, size)
            print(f"  Found: {name}.{ext}  cluster={first}  size={size}", flush=True)

    fat_bytes = fats_sectors * bps
    f.seek(raw_offset + fat1_lba * PHYS_SECTOR)
    fat = f.read(fat_bytes)

    def next_cluster(fat, cluster):
        return struct.unpack_from("<H", fat, cluster * 2)[0]

    for name, (start_cluster, file_size) in found.items():
        clusters = []
        c = start_cluster
        while c < 0xFFF8:
            clusters.append(c)
            c = next_cluster(fat, c)

        data = bytearray()
        for c in clusters:
            clba = data_lba + (c - 2) * spc * dos2phys
            f.seek(raw_offset + clba * PHYS_SECTOR)
            data.extend(f.read(spc * bps))

        content = bytes(data[:file_size])
        print(f"\n{'='*70}")
        print(f">>> {name} (size={file_size}, clusters={len(clusters)}):")
        print("---")
        print(content.decode("ascii", errors="replace"), end="")
        print("---")
