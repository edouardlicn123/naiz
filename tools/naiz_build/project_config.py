#!/usr/bin/env python3
"""Unified read-only accessor for projects/<game>/config.toml.

Single source of truth for reading project config. Consumers:
  - build_game.py      (project.version, blackletter.*)
  - export_config.py   (transition.*)
  - i18n_gen.py        (i18n.*)
  - bump_version.py    (project.version, read-only)

Only bump_version.py writes config.toml (line-based, preserves comments).
"""

import tomllib
from pathlib import Path


class ProjectConfig:
    def __init__(self, project_dir):
        self.path = Path(project_dir) / "config.toml"
        if not self.path.exists():
            raise FileNotFoundError(f"config.toml not found: {self.path}")
        with open(self.path, "rb") as f:
            self.raw = f.read().decode("utf-8")
        try:
            self.data = tomllib.loads(self.raw)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"config.toml parse error: {e}") from e

    def get(self, section, key, default=None):
        return (self.data.get(section) or {}).get(key, default)

    def get_str(self, section, key, default=None):
        v = self.get(section, key, default)
        return v if isinstance(v, str) else default

    def get_bool(self, section, key, default=False):
        v = self.get(section, key, default)
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes")
        return default

    def get_int(self, section, key, default=None):
        v = self.get(section, key, default)
        if isinstance(v, bool):
            return default
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                return default
        return default

    def get_list(self, section, key, default=None):
        v = self.get(section, key, default)
        return v if isinstance(v, list) else default

    def version(self):
        return self.get_str("project", "version", "")


def load_project_config(project_dir):
    return ProjectConfig(project_dir)
