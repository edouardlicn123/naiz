"""
参考 98Bridge (MIT) 的设计思路独立实现。
来源: https://github.com/NullMagic2/98Bridge

Incremental injection core: copy base HDI, then make targeted FAT edits.
"""

import os
import struct

from .hdi import HDIImage
from .fat import NAIZFatFS, _make_entry, _build_fat_bytes
from .fat import ATTR_DIRECTORY, ATTR_ARCHIVE, FAT16_EOC


PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
REF_CONFIG = os.path.join(PROJECT_ROOT, 'tools', 'ref_config')
DEFAULT_BASE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'base_msdos5_scsi_48m.hdi'))


def generate_autoexec(game_name):
    name = game_name.upper()
    content = (
        b'@ECHO OFF\r\n'
        b'PATH \\DOS\r\n'
        b'SET TEMP=\\DOS\r\n'
        b'SET DOSDIR=\\DOS\r\n'
        b'CD \\' + name.encode() + b'\r\n'
        b'ENGINE.EXE\r\n'
    )
    return content


def _find_free_root_slot(root_data, root_entries):
    for i in range(root_entries):
        off = i * 32
        first = root_data[off]
        if first == 0 or first == 0xE5:
            return off
    return None


def _find_entry_offset(root_data, name8, ext3):
    for i in range(len(root_data) // 32):
        off = i * 32
        first = root_data[off]
        if first == 0:
            return None
        if first == 0xE5:
            continue
        if root_data[off:off + 8] == name8 and root_data[off + 8:off + 11] == ext3:
            return off
    return None


def _write_fat(fs, fat_list):
    fat_len = fs.fat_sectors * fs.bytes_per_sector
    fat_bytes = _build_fat_bytes(fat_list, fs.fat_type, fat_len)
    for i in range(fs.num_fats):
        fs._write_bytes(fs.fat_offset + i * fat_len, fat_bytes)


def _read_root(fs):
    return bytearray(fs._read_bytes(fs.root_offset,
                                    fs.root_sectors * fs.bytes_per_sector))


def _write_root(fs, root_data):
    fs._write_bytes(fs.root_offset, bytes(root_data))


def _read_cluster(fs, cluster, size=None):
    off = fs.data_offset + (cluster - 2) * fs.cluster_size
    n = size if size is not None else fs.cluster_size
    return fs._read_bytes(off, n)


def _write_cluster(fs, cluster, data):
    off = fs.data_offset + (cluster - 2) * fs.cluster_size
    fs._write_bytes(off, data)


def _to_dos_name(name):
    name = name.upper()
    if '.' in name:
        base, ext = name.rsplit('.', 1)
    else:
        base, ext = name, ''
    base = base[:8].ljust(8, ' ')
    ext = ext[:3].ljust(3, ' ')
    return base.encode('ascii', errors='replace'), ext.encode('ascii', errors='replace')


def inject_into_hdi(hdi_path, game_name, game_dir,
                    no_config=False, no_autoexec=False):
    if os.path.abspath(hdi_path) == os.path.abspath(DEFAULT_BASE):
        raise ValueError("Refusing to inject into the base HDI directly")

    print(f"Opening HDI: {hdi_path}")
    img = HDIImage(hdi_path)
    fs = NAIZFatFS(img)

    print(f"  {fs.total_sectors} sectors, {fs.bytes_per_sector} B/sector, "
          f"{fs.cluster_size} B/cluster, FAT{fs.fat_type}")

    fat_list = [fs._read_fat_entry(i) for i in range(fs._max_cluster)]
    next_free = [2]
    while next_free[0] < len(fat_list) and fat_list[next_free[0]] != 0:
        next_free[0] += 1

    def _alloc():
        while next_free[0] < len(fat_list):
            if fat_list[next_free[0]] == 0:
                c = next_free[0]
                next_free[0] += 1
                return c
            next_free[0] += 1
        raise RuntimeError("Disk full")

    # --- Step 0: Remove DBLSPACE.BIN (causes "how many files" prompt during boot) ---
    root_data = _read_root(fs)
    ds_name8, ds_ext3 = _to_dos_name('DBLSPACE.BIN')
    ds_off = _find_entry_offset(root_data, ds_name8, ds_ext3)
    if ds_off is not None:
        root_data[ds_off] = 0xE5
        print("DBLSPACE.BIN removed from root directory")
        _write_root(fs, root_data)
        _write_fat(fs, fat_list)

    # --- Step 1: Replace AUTOEXEC.BAT ---
    if not no_autoexec:
        autoexec_new = generate_autoexec(game_name)
        print(f"\nAUTOEXEC.BAT: {len(autoexec_new)} bytes")

        root_data = _read_root(fs)
        ae_name8, ae_ext3 = _to_dos_name('AUTOEXEC.BAT')
        ae_off = _find_entry_offset(root_data, ae_name8, ae_ext3)
        if ae_off is None:
            print("  WARNING: AUTOEXEC.BAT not found in base HDI")
        else:
            ae_cluster = struct.unpack_from('<H', root_data, ae_off + 26)[0]
            ae_chain = fs._get_cluster_chain(ae_cluster)
            ae_capacity = len(ae_chain) * fs.cluster_size

            if len(autoexec_new) <= ae_capacity:
                buf = autoexec_new + b'\x00' * (ae_capacity - len(autoexec_new))
                for i, c in enumerate(ae_chain):
                    chunk = buf[i * fs.cluster_size:(i + 1) * fs.cluster_size]
                    _write_cluster(fs, c, chunk)
                struct.pack_into('<I', root_data, ae_off + 28, len(autoexec_new))
                print(f"  Overwrote {len(autoexec_new)} bytes in-place")
            else:
                num_cl = (len(autoexec_new) + fs.cluster_size - 1) // fs.cluster_size
                new_chain = []
                for _ in range(num_cl):
                    c = _alloc()
                    new_chain.append(c)
                for i in range(len(new_chain) - 1):
                    fat_list[new_chain[i]] = new_chain[i + 1]
                fat_list[new_chain[-1]] = FAT16_EOC
                for c in ae_chain:
                    fat_list[c] = 0
                for i, c in enumerate(new_chain):
                    chunk = autoexec_new[i * fs.cluster_size:(i + 1) * fs.cluster_size]
                    _write_cluster(fs, c, chunk)
                struct.pack_into('<H', root_data, ae_off + 26, new_chain[0] & 0xFFFF)
                struct.pack_into('<I', root_data, ae_off + 28, len(autoexec_new))
                print(f"  Reallocated to {num_cl} clusters")

        _write_root(fs, root_data)

    # --- Step 2: Replace CONFIG.SYS ---
    if not no_config:
        config_path = os.path.join(REF_CONFIG, 'CONFIG.SYS')
        with open(config_path, 'rb') as f:
            config_new = f.read()
        print(f"\nCONFIG.SYS: {len(config_new)} bytes")

        root_data = _read_root(fs)
        cfg_name8, cfg_ext3 = _to_dos_name('CONFIG.SYS')
        cfg_off = _find_entry_offset(root_data, cfg_name8, cfg_ext3)
        if cfg_off is not None:
            cfg_cluster = struct.unpack_from('<H', root_data, cfg_off + 26)[0]
            cfg_chain = fs._get_cluster_chain(cfg_cluster)
            cfg_capacity = len(cfg_chain) * fs.cluster_size

            if len(config_new) <= cfg_capacity:
                buf = config_new + b'\x00' * (cfg_capacity - len(config_new))
                for i, c in enumerate(cfg_chain):
                    chunk = buf[i * fs.cluster_size:(i + 1) * fs.cluster_size]
                    _write_cluster(fs, c, chunk)
                struct.pack_into('<I', root_data, cfg_off + 28, len(config_new))
                print(f"  Overwrote {len(config_new)} bytes in-place")
            else:
                num_cl = (len(config_new) + fs.cluster_size - 1) // fs.cluster_size
                new_chain = []
                for _ in range(num_cl):
                    c = _alloc()
                    new_chain.append(c)
                for i in range(len(new_chain) - 1):
                    fat_list[new_chain[i]] = new_chain[i + 1]
                fat_list[new_chain[-1]] = FAT16_EOC
                for c in cfg_chain:
                    fat_list[c] = 0
                for i, c in enumerate(new_chain):
                    chunk = config_new[i * fs.cluster_size:(i + 1) * fs.cluster_size]
                    _write_cluster(fs, c, chunk)
                struct.pack_into('<H', root_data, cfg_off + 26, new_chain[0] & 0xFFFF)
                struct.pack_into('<I', root_data, cfg_off + 28, len(config_new))
                print(f"  Reallocated to {num_cl} clusters")

        _write_root(fs, root_data)

    # --- Step 3: Create or update game directory ---
    game_name_upper = game_name.upper()
    dir_name8 = game_name_upper[:8].ljust(8, ' ').encode('ascii', errors='replace')
    dir_ext3 = b'   '

    root_data = _read_root(fs)
    dir_off = _find_entry_offset(root_data, dir_name8, dir_ext3)

    if dir_off is not None:
        dir_cluster = struct.unpack_from('<H', root_data, dir_off + 26)[0]
        dir_chain = fs._get_cluster_chain(dir_cluster)
        print(f"\n{game_name_upper}/ directory exists at cluster={dir_cluster}")
    else:
        dir_cluster = _alloc()
        fat_list[dir_cluster] = FAT16_EOC
        slot = _find_free_root_slot(root_data, fs.root_entries)
        if slot is None:
            raise RuntimeError("Root directory full")
        entry = _make_entry(dir_name8, dir_ext3, ATTR_DIRECTORY, dir_cluster, 0)
        root_data[slot:slot + 32] = entry
        dir_chain = [dir_cluster]
        _write_cluster(fs, dir_cluster, b'\x00' * fs.cluster_size)
        _write_root(fs, root_data)
        print(f"\n{game_name_upper}/ created at cluster={dir_cluster} (zeroed)")

    dir_data = bytearray()
    for c in dir_chain:
        dir_data.extend(_read_cluster(fs, c))

    existing_entries = {}
    i = 0
    while i + 32 <= len(dir_data):
        raw = dir_data[i:i + 32]
        first = raw[0]
        if first == 0 or first == 0xE5:
            i += 32
            continue
        attr = raw[11]
        if attr == 0x0F:
            i += 32
            continue
        ename = raw[0:8].rstrip(b' ').decode('ascii', errors='replace')
        eext = raw[8:11].rstrip(b' ').decode('ascii', errors='replace')
        existing_entries[f"{ename}.{eext}".upper()] = (i, raw)
        i += 32

    # --- Step 4: Add game files ---
    game_files = []
    for f in sorted(os.listdir(game_dir)):
        fpath = os.path.join(game_dir, f)
        if not os.path.isfile(fpath):
            continue
        game_files.append(f)

    print(f"\nInjecting {len(game_files)} game file(s):")
    for f in game_files:
        fpath = os.path.join(game_dir, f)
        file_data = open(fpath, 'rb').read()

        if f.upper() == 'ROOTINFO.DAT' and len(file_data) >= 0x22:
            file_data = bytearray(file_data)
            file_data[0x16:0x16 + 12] = b'FONT.DAT\x00\x00\x00\x00'
            file_data = bytes(file_data)

        file_size = len(file_data)
        fn8, fe3 = _to_dos_name(f)
        fkey = f.upper()

        if fkey in existing_entries:
            eoff, eraw = existing_entries[fkey]
            ecluster = struct.unpack_from('<H', eraw, 26)[0]
            echain = fs._get_cluster_chain(ecluster)
            ecapacity = len(echain) * fs.cluster_size

            if file_size <= ecapacity:
                buf = file_data + b'\x00' * (ecapacity - file_size)
                for i, c in enumerate(echain):
                    chunk = buf[i * fs.cluster_size:(i + 1) * fs.cluster_size]
                    _write_cluster(fs, c, chunk)
                struct.pack_into('<I', dir_data, eoff + 28, file_size)
                print(f"  {f}: overwritten in-place ({file_size} bytes)")
            else:
                num_cl = (file_size + fs.cluster_size - 1) // fs.cluster_size
                new_chain = []
                for _ in range(num_cl):
                    c = _alloc()
                    new_chain.append(c)
                for i in range(len(new_chain) - 1):
                    fat_list[new_chain[i]] = new_chain[i + 1]
                fat_list[new_chain[-1]] = FAT16_EOC
                for c in echain:
                    fat_list[c] = 0
                for i, c in enumerate(new_chain):
                    chunk = file_data[i * fs.cluster_size:(i + 1) * fs.cluster_size]
                    _write_cluster(fs, c, chunk)
                struct.pack_into('<H', dir_data, eoff + 26, new_chain[0] & 0xFFFF)
                struct.pack_into('<I', dir_data, eoff + 28, file_size)
                print(f"  {f}: reallocated to {num_cl} clusters ({file_size} bytes)")
        else:
            slot = None
            for ei in range(len(dir_data) // 32):
                soff = ei * 32
                if soff + 32 > len(dir_data):
                    break
                first = dir_data[soff]
                if first == 0 or first == 0xE5:
                    slot = soff
                    break
            if slot is None:
                if len(dir_data) & (fs.cluster_size - 1):
                    pad = fs.cluster_size - (len(dir_data) % fs.cluster_size)
                    dir_data.extend(b'\x00' * pad)
                new_cl = _alloc()
                fat_list[dir_chain[-1]] = new_cl
                fat_list[new_cl] = FAT16_EOC
                dir_chain.append(new_cl)
                _write_cluster(fs, new_cl, b'\x00' * fs.cluster_size)
                old_len = len(dir_data)
                dir_data.extend(b'\x00' * fs.cluster_size)
                slot = old_len

            if file_size == 0:
                first_cluster = 0
            else:
                num_cl = (file_size + fs.cluster_size - 1) // fs.cluster_size
                new_chain = []
                for _ in range(num_cl):
                    c = _alloc()
                    new_chain.append(c)
                for i in range(len(new_chain) - 1):
                    fat_list[new_chain[i]] = new_chain[i + 1]
                fat_list[new_chain[-1]] = FAT16_EOC
                first_cluster = new_chain[0]
                for i, c in enumerate(new_chain):
                    chunk = file_data[i * fs.cluster_size:(i + 1) * fs.cluster_size]
                    _write_cluster(fs, c, chunk)

            entry = _make_entry(fn8, fe3, ATTR_ARCHIVE, first_cluster, file_size)
            dir_data[slot:slot + 32] = entry
            print(f"  {f}: new, {file_size} bytes -> cluster={first_cluster}")

    for i, c in enumerate(dir_chain):
        chunk = bytes(dir_data[i * fs.cluster_size:(i + 1) * fs.cluster_size])
        if len(chunk) < fs.cluster_size:
            chunk = chunk + b'\x00' * (fs.cluster_size - len(chunk))
        _write_cluster(fs, c, chunk)

    # --- Step 5: Update FAT copies ---
    print(f"\nUpdating FAT ({fs.num_fats} copies)...")
    _write_fat(fs, fat_list)
    print(f"  FAT entries: {len(fat_list)}, free clusters: {fat_list.count(0)}")

    # --- Step 6: Save ---
    print(f"\nSaving to: {hdi_path}")
    img.save(hdi_path)

    written = len([f for f in game_files if f.upper() not in existing_entries])
    updated = len(game_files) - written
    total_free = fat_list.count(0)
    print(f"Done: {written} new, {updated} updated, {len(game_files)} total, "
          f"{total_free} free clusters")

    return len(game_files), 1
