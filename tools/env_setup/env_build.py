#!/usr/bin/env python3
"""
env_build.py — Build/install command handlers for Naiz environment setup

Backward-compatibility re-export layer (B5 split).  Real handlers now live
in env_toolchains.py (pip/watcom/djgpp/gcc-ia16) and env_np2kai.py
(NP2kai/libretro/deps).  Existing `from .env_build import cmd_*` stays valid.
"""
from .env_toolchains import (
    cmd_pip_install, cmd_install_watcom, cmd_install_djgpp,
    cmd_gcc_ia16, _install_gcc_ia16_deepin,
)
from .env_np2kai import (
    cmd_build_i286, cmd_np2kai, cmd_np2kai_libretro, cmd_deps,
)
