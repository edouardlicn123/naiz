"""
参考 98Bridge (MIT) 的设计思路独立实现。
来源: https://github.com/NullMagic2/98Bridge

Re-export compatibility layer for the fat_entries / fat_table / fat_fs
split. All names previously defined here are re-exported so that existing
``from .fat import ...`` call sites keep working unchanged.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from naiz_lib import to_dos_name
from .fat_entries import (
    ATTR_READ_ONLY, ATTR_HIDDEN, ATTR_SYSTEM, ATTR_VOLUME_ID,
    ATTR_DIRECTORY, ATTR_ARCHIVE, ATTR_LFN,
    ATTR_SYSTEM_FILE,
    FAT12_EOC, FAT16_EOC,
    SYSTEM_FILES,
    FileEntry,
    _unique_83,
    make_fat_entry,
    get_entry_cluster, get_entry_size,
    set_entry_cluster, set_entry_size,
)
from .fat_table import (
    set_fat_entry,
    build_fat_bytes,
    alloc_next_free,
    free_cluster_chain,
    make_alloc_fn,
)
from .fat_fs import NAIZFatFS
