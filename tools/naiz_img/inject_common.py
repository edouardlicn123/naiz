"""
参考 98Bridge (MIT) 的设计思路独立实现。
来源: https://github.com/NullMagic2/98Bridge

Incremental injection core: copy base HDI, then make targeted FAT edits.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from .hdi import HDIImage
from naiz_lib import to_dos_name, COMMERCIAL_BASE_HDI
from .fat import NAIZFatFS, make_fat_entry, make_alloc_fn
from .fat import ATTR_DIRECTORY, ATTR_ARCHIVE, FAT12_EOC, FAT16_EOC
from .fat import get_entry_cluster


DEFAULT_BASE = COMMERCIAL_BASE_HDI


def _generate_config(game_name):
    """Generate CONFIG.SYS with VEM486.EXE memory manager."""
    return (
        b'FILES=30\r\n'
        b'BUFFERS=6,0\r\n'
        b'DOS=HIGH,UMB\r\n'
        b'DEVICE=A:\\VEM486.EXE /U\r\n'
        b'SHELL=A:\\COMMAND.COM A:\\ /P\r\n'
    )


def generate_autoexec(game_name):
    content = (
        b'@ECHO OFF\r\n'
        b'SET DOS16M=1\r\n'
        b'QMOUSE -a- -z\r\n'
        b'engine.exe\r\n'
    )
    return content


def inject_into_hdi(hdi_path, game_name, game_dir,
                    no_config=False, no_autoexec=False):
    if os.path.realpath(hdi_path) == os.path.realpath(DEFAULT_BASE):
        raise ValueError("Refusing to inject into the base HDI directly")

    print(f"Opening HDI: {hdi_path}")
    img = HDIImage(hdi_path)
    fs = NAIZFatFS(img)

    print(f"  {fs.total_sectors} sectors, {fs.bytes_per_sector} B/sector, "
          f"{fs.cluster_size} B/cluster, FAT{fs.fat_type}")

    fat_list = fs.read_fat_list()
    fat_eoc = FAT12_EOC if fs.fat_type == 12 else FAT16_EOC
    next_free = NAIZFatFS.alloc_next_free(fat_list, 2)
    _alloc = make_alloc_fn(fat_list, next_free)

    # --- Step 0: Remove DBLSPACE.BIN (causes "how many files" prompt during boot) ---
    root_data = fs.read_root()
    ds_name8, ds_ext3 = to_dos_name('DBLSPACE.BIN')
    ds_off = NAIZFatFS.find_entry_offset(root_data, ds_name8, ds_ext3)
    if ds_off is not None:
        ds_cluster = get_entry_cluster(root_data, ds_off)
        if ds_cluster != 0:
            ds_chain = fs._get_cluster_chain(ds_cluster)
            for c in ds_chain:
                fat_list[c] = 0
        root_data[ds_off] = 0xE5
        print("DBLSPACE.BIN removed from root directory")
        fs.write_root(root_data)
        fs.write_fat(fat_list)

    # --- Step 1: AUTOEXEC.BAT ---
    if not no_autoexec:
        autoexec_content = generate_autoexec(game_name)
        print(f"\nAUTOEXEC.BAT: {len(autoexec_content)} bytes (SET DOS16M=1 + launch)")

    # --- Step 2: Replace CONFIG.SYS ---
    if not no_config:
        config_new = _generate_config(game_name)
        print(f"\nCONFIG.SYS: {len(config_new)} bytes (VEM486.EXE)")

        root_data = fs.read_root()
        cfg_name8, cfg_ext3 = to_dos_name('CONFIG.SYS')
        cfg_off = NAIZFatFS.find_entry_offset(root_data, cfg_name8, cfg_ext3)
        if cfg_off is not None:
            in_place = fs.overwrite_entry(root_data, cfg_off, config_new, fat_list, _alloc)
            if in_place:
                print(f"  Overwrote {len(config_new)} bytes in-place")
            else:
                print("  Reallocated CONFIG.SYS to new clusters")
        else:
            print("WARN: CONFIG.SYS not found in root directory")

        fs.write_root(root_data)

    # --- Step 2.2: Overwrite AUTOEXEC.BAT content ---
    if not no_autoexec:
        ae_content = autoexec_content
        root_data = fs.read_root()
        ae_name8, ae_ext3 = to_dos_name('AUTOEXEC.BAT')
        ae_off = NAIZFatFS.find_entry_offset(root_data, ae_name8, ae_ext3)
        if ae_off is not None:
            in_place = fs.overwrite_entry(root_data, ae_off, ae_content, fat_list, _alloc)
            if in_place:
                print(f"  AUTOEXEC.BAT: overwritten in-place ({len(ae_content)} bytes)")
            else:
                print(f"  AUTOEXEC.BAT: reallocated to new clusters ({len(ae_content)} bytes)")
        else:
            print("  WARNING: AUTOEXEC.BAT not found in root directory")
        fs.write_root(root_data)

    # --- Step 3: Inject game files into root directory ---
    root_data = fs.read_root()

    existing_entries = {}
    for i, key, _attr in NAIZFatFS.iter_dir_entries(root_data):
        existing_entries[key] = i

    game_files = []
    subdirs = []
    for f in sorted(os.listdir(game_dir)):
        fpath = os.path.join(game_dir, f)
        if os.path.isfile(fpath):
            game_files.append(f)
        elif os.path.isdir(fpath):
            subdirs.append(f)

    # Detect 8.3 name collision BEFORE writing — abort to prevent data loss
    dos_names = {}
    for ff in game_files:
        ffn8, ffe3 = to_dos_name(ff)
        ddos = (ffn8.ljust(8, b' '), ffe3.ljust(3, b' '))
        if ddos in dos_names:
            raise RuntimeError(
                f"8.3 name collision: '{ff}' and '{dos_names[ddos]}' "
                f"both map to '{ddos[0].decode()}.{ddos[1].decode()}'. "
                f"Rename one of the source files."
            )
        dos_names[ddos] = ff

    print(f"\nInjecting {len(game_files)} game file(s) into root:")
    for f in game_files:
        fpath = os.path.join(game_dir, f)
        with open(fpath, 'rb') as fh:
            file_data = fh.read()

        file_size = len(file_data)
        fn8, fe3 = to_dos_name(f)
        dos_name = fn8.rstrip(b' ').decode('ascii', errors='replace') + '.' + fe3.rstrip(b' ').decode('ascii', errors='replace')
        fkey = f.upper()

        if fkey in existing_entries:
            eoff = existing_entries[fkey]
            in_place = fs.overwrite_entry(root_data, eoff, file_data, fat_list, _alloc)
            if in_place:
                print(f"  {f}: overwritten in-place ({file_size} bytes)")
            else:
                print(f"  {f}: reallocated to new clusters ({file_size} bytes)")
        else:
            slot = NAIZFatFS.find_free_root_slot(root_data, fs.root_entries)
            if slot is None:
                raise RuntimeError("Root directory full")

            first_cluster = fs.write_file_entry(root_data, slot, fn8, fe3, file_data,
                                                fat_list, _alloc, ATTR_ARCHIVE)
            if first_cluster == 0:
                print(f"  {f}: new, {file_size} bytes (empty)")
            else:
                print(f"  {f}: new, {file_size} bytes -> cluster={first_cluster}")

    fs.write_root(root_data)

    # --- Step 4: Inject subdirectory contents ---
    for dir_name in subdirs:
        dpath = os.path.join(game_dir, dir_name)
        dn8, de3 = to_dos_name(dir_name)

        dir_off = NAIZFatFS.find_entry_offset(root_data, dn8, de3)
        if dir_off is None:
            slot = NAIZFatFS.find_free_root_slot(root_data, fs.root_entries)
            if slot is None:
                raise RuntimeError("Root directory full")
            dir_cluster = _alloc()
            fs.zero_cluster(dir_cluster)
            fat_list[dir_cluster] = fat_eoc
            dir_data = bytearray(fs.cluster_size)
            dir_data[0:32] = make_fat_entry(b'.       ', b'   ', ATTR_DIRECTORY, dir_cluster, 0)
            dir_data[32:64] = make_fat_entry(b'..      ', b'   ', ATTR_DIRECTORY, 0, 0)
            fs.write_cluster(dir_cluster, bytes(dir_data))
            entry = make_fat_entry(dn8, de3, ATTR_DIRECTORY, dir_cluster, 0)
            root_data[slot:slot + 32] = entry
            print(f"  {dir_name}/: new directory")
            dir_off = slot

        dir_cluster = get_entry_cluster(root_data, dir_off)
        fs.sync_fat(fat_list)
        chain = fs._get_cluster_chain(dir_cluster)
        if not chain:
            print(f"  WARNING: {dir_name}/ has no clusters, skipping")
            continue

        dir_data = bytearray()
        for c in chain:
            dir_data.extend(fs.read_cluster( c, fs.cluster_size))

        existing_sub = {}
        for j, key, _attr in NAIZFatFS.iter_dir_entries(dir_data):
            existing_sub[key] = j

        # Original scan left dir_end at the end of the cluster-chain data
        # (len is a multiple of 32, so the scan always consumes the whole buffer).
        dir_end = len(dir_data)

        sub_files = [f for f in sorted(os.listdir(dpath)) if os.path.isfile(os.path.join(dpath, f))]
        print(f"  Injecting {len(sub_files)} file(s) into {dir_name}/:")

        for f in sub_files:
            fpath = os.path.join(dpath, f)
            with open(fpath, 'rb') as fh:
                file_data = fh.read()
            file_size = len(file_data)
            fn8, fe3 = to_dos_name(f)
            fkey = f.upper()

            if fkey in existing_sub:
                eoff = existing_sub[fkey]
                fs.overwrite_entry(dir_data, eoff, file_data, fat_list, _alloc)
                print(f"    {f}: updated ({file_size} bytes)")
            else:
                if dir_end + 32 > len(dir_data):
                    # Zero-pad dir_data to avoid index errors
                    extend_len = max(fs.cluster_size, dir_end + 32 - len(dir_data))
                    dir_data.extend(b'\x00' * extend_len)

                first_cluster = fs.write_file_entry(dir_data, dir_end, fn8, fe3,
                                                    file_data, fat_list, _alloc,
                                                    ATTR_ARCHIVE)
                if first_cluster == 0:
                    print(f"    {f}: new, {file_size} bytes (empty)")
                else:
                    print(f"    {f}: new, {file_size} bytes")
                dir_end += 32

        # Write back directory data
        cluster_cnt = (dir_end + fs.cluster_size - 1) // fs.cluster_size
        while len(chain) < cluster_cnt:
            extra = _alloc()
            fs.zero_cluster(extra)
            fat_list[chain[-1]] = extra
            fat_list[extra] = fat_eoc
            chain.append(extra)
            print(f"    Extended directory {dir_name}/: cluster {extra}")
        for i, c in enumerate(chain):
            chunk = dir_data[i * fs.cluster_size:(i+1)*fs.cluster_size]
            if chunk:
                fs.write_cluster(c, chunk)

    fs.write_root(root_data)

    # --- Step 5: Update FAT copies ---
    print(f"\nUpdating FAT ({fs.num_fats} copies)...")
    fs.write_fat(fat_list)
    print(f"  FAT entries: {len(fat_list)}, free clusters: {fat_list.count(0)}")

    # --- Step 6: Save ---
    print(f"\nSaving to: {hdi_path}")
    img.save(hdi_path)

    written = len([f for f in game_files if f.upper() not in existing_entries])
    updated = len(game_files) - written
    total_free = fat_list.count(0)
    print(f"Done: {written} new, {updated} updated, {len(game_files)} total, "
          f"{total_free} free clusters")

    return len(game_files), len(existing_entries)
