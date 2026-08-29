# naiz_lib shared utilities

import os

# === Project path constants ===
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
"""Absolute path to the naiz project root directory."""
GAMES_DIR = os.path.join(PROJECT_ROOT, 'games')
"""Directory containing deployable game files."""
DISKS_DIR = os.path.join(PROJECT_ROOT, 'disks')
"""Directory containing generated HDI images."""
COMMERCIAL_DIR = os.path.join(PROJECT_ROOT, 'tools_commercial')
"""Directory holding non-open-source (commercial/copyrighted) build assets."""
COMMERCIAL_BASE_HDI = os.path.join(COMMERCIAL_DIR, 'base_msdos5_scsi_48m_clean.hdi')
"""MS-DOS 5.0 base HDI image (commercial, kept out of the open-source repo)."""
COMMERCIAL_BIOS_DIR = os.path.join(COMMERCIAL_DIR, 'pc9821bios')
"""NEC PC-98 BIOS ROM directory (commercial firmware)."""
COMMERCIAL_DOS_DIR = os.path.join(COMMERCIAL_DIR, 'dos_system')
"""DOS system files (DOS4GW.EXE, VEM486.*, IO.SYS, ...)."""
DOS_SYSTEM_DIR = COMMERCIAL_DOS_DIR
"""Deprecated alias for COMMERCIAL_DOS_DIR (kept for backward compatibility)."""
VENV_DIR = os.path.join(PROJECT_ROOT, 'tools', 'env_setup', 'venv')
"""Shared Python virtualenv directory (single source of truth)."""
VENV_PYTHON = os.path.join(VENV_DIR, 'bin', 'python3')
"""Python interpreter inside the shared venv."""

# === VEM486 memory manager file set (injected into base HDI) ===
VEM486_FILES = ['VEM486.EXE', 'VEM486.HED', 'VEMEMM.SYS',
                'VEMHSB.SYS', 'VEMRSM.SYS']

# === Cross-language constants (mirrors core/engine/render.h + scene_layers.h) ===

# Palette indices
PAL_WHITE = 7
PAL_TRANSPARENT = 15
PAL_DIALOG_FILL = 248
BTN_FILL_IDX = 249
BTN_HIGHLIGHT_IDX = 252
BTN_SHADOW_IDX = 253

# All engine-reserved palette indices (must not be used by game art)
PROTECTED_IDX_ALL = {PAL_WHITE, PAL_TRANSPARENT, 248, 249, 250, 251, 252, 253, 254, 255}

# Screen dimensions
LAYER_SCREEN_W = 640
LAYER_SCREEN_H = 400

# Button dimensions (from scene_layers.h BTN_*)
BTN_W = 100
BTN_H = 34
BTN_R = 17
BTN_GAP = 10
BTN_COL_GAP = 14

# Dialog layout (from scene_layers.h LAYER_DIALOG_*)
DIALOG_X = 80
DIALOG_Y = 280
DIALOG_W = 480
DIALOG_H = 115
DIALOG_INDENT = 12
DIALOG_RIGHT_INDENT = 12
DIALOG_TEXT_Y = 28
DIALOG_HEADER_Y = 6
DIALOG_BORDER = 2
DIALOG_BOTTOM = DIALOG_Y + DIALOG_H - DIALOG_BORDER

# Sprite layout (from scene_layers.h LAYER_SPRITE_*)
LAYER_SPRITE_W = 200
LAYER_SPRITE_H = 400
LAYER_MAX_SPRITES = 16


def read_u32_le(data, offset):
    """Read an unsigned 32-bit little-endian integer from bytes at offset."""
    return int.from_bytes(data[offset:offset+4], "little")


def read_u16_le(data, offset):
    """Read an unsigned 16-bit little-endian integer from bytes at offset."""
    return int.from_bytes(data[offset:offset+2], "little")


def to_dos_name(name):
    """Convert 'FILE.EXT' to (base8, ext3) padded DOS 8.3 name bytes."""
    name = name.upper()
    if '.' in name:
        base, ext = name.rsplit('.', 1)
    else:
        base, ext = name, ''
    base8 = base[:8].ljust(8).encode('ascii', errors='replace')
    ext3 = ext[:3].ljust(3).encode('ascii', errors='replace')
    return base8, ext3
