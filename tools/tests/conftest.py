"""Shared pytest fixtures and import-path setup for the naiz toolchain.

naiz_lib modules import each other via `from naiz_lib import ...` (absolute
imports), so the repository root must be on sys.path for tests to resolve.
Running `pytest` from the repository root works because the rootdir
auto-insertion covers `tools/naiz_lib` when imported as a package; this
fixture makes it explicit and robust regardless of the invocation directory.
"""

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")


@pytest.fixture(scope="session", autouse=True)
def _ensure_tools_on_path():
    if TOOLS_DIR not in sys.path:
        sys.path.insert(0, TOOLS_DIR)
    return None
