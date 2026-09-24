#!/usr/bin/env python3
"""Naiz asset-market downloader.

Downloads whole asset packs from a public GitHub market repo into a local
destination directory (default <root>/assets_samples, gitignored).

Model (AGENTS.md section 13, mandatory): every top-level directory of the
market repo is one downloadable asset pack; the folder-name prefix denotes
the asset kind. The pack display-name rule: split the directory name on
'_', wrap the first segment in '()', join the remaining segments with
spaces (images_sample_scenebg -> (images)sample scenebg). Packs are always
downloaded whole; there is no file-level selection.

Subcommands:
  list      list all packs (display name, file count, total size)
  cats      list pack display names and file counts only
  menu      interactive numeric pack picker (downloads in pack units)
  get       download one or more named packs (exact dir / suffix kind)
  get-all   download every pack

Common flags (on any subcommand): --repo --ref --dest --config --dry-run.
Files whose destination path already exists are skipped; pass --force to
re-download and overwrite them.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

GITHUB_API_ROOT = "https://api.github.com/repos"
RAW_ROOT = "https://raw.githubusercontent.com"
DEFAULT_CONFIG_NAME = "market.toml"


class MarketError(RuntimeError):
    """Raised for all user-facing failures (bad config, network, safety)."""


# ---------------------------------------------------------------------------
# Low-level HTTP
# ---------------------------------------------------------------------------

def _http_get(url, accept=None):
    headers = {"User-Agent": "naiz-market"}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _fetch_json(url):
    try:
        body = _http_get(url, accept="application/vnd.github+json")
    except urllib.error.HTTPError as e:
        raise MarketError(f"HTTP {e.code} fetching {url}") from None
    except (urllib.error.URLError, OSError) as e:
        raise MarketError(f"network error fetching {url}: {e}") from None
    try:
        return json.loads(body)
    except ValueError as e:
        raise MarketError(f"invalid JSON from {url}: {e}") from None


def _fetch_bytes(url):
    try:
        return _http_get(url)
    except urllib.error.HTTPError as e:
        raise MarketError(f"HTTP {e.code} downloading {url}") from None
    except (urllib.error.URLError, OSError) as e:
        raise MarketError(f"network error downloading {url}: {e}") from None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def human_size(num):
    num = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} GB"


def safe_target(dest, path):
    """Resolve market path under dest; reject traversal and absolute paths."""
    rel = Path(path)
    if rel.is_absolute() or any(seg == ".." for seg in rel.parts):
        raise MarketError(f"unsafe asset path: {path}")
    root = dest.resolve()
    target = (dest / rel).resolve()
    if not target.is_relative_to(root):
        raise MarketError(f"asset path escapes dest: {path}")
    return target


# ---------------------------------------------------------------------------
# Market model
# ---------------------------------------------------------------------------

class Market:
    def __init__(self, repo, ref, dest, dry_run=False, force=False):
        if "/" not in repo:
            raise MarketError(f"repo must be 'owner/repo', got {repo!r}")
        self.repo = repo
        self.ref = ref
        self.dest = Path(dest)
        self.dry_run = dry_run
        self.force = force
        self._tree = None

    # -- listing ------------------------------------------------------------

    def fetch_tree(self):
        if self._tree is not None:
            return self._tree
        qref = urllib.parse.quote(self.ref, safe="")
        url = f"{GITHUB_API_ROOT}/{self.repo}/git/trees/{qref}?recursive=1"
        data = _fetch_json(url)
        if data.get("truncated"):
            raise MarketError("tree listing truncated by GitHub; pack index incomplete")
        self._tree = data.get("tree", [])
        return self._tree

    def packs(self):
        """Return {top_level_dir: sorted [(path, size), ...]}."""
        blobs = [(e["path"], int(e.get("size") or 0))
                 for e in self.fetch_tree() if e.get("type") == "blob"]
        grouped = {}
        for path, size in blobs:
            if "/" not in path:
                continue          # root-level files (README/LICENSE) are not packs
            top = path.split("/", 1)[0]
            grouped.setdefault(top, []).append((path, size))
        return {directory: sorted(files)
                for directory, files in sorted(grouped.items())}

    # -- pack naming rules (AGENTS.md section 13) ---------------------------

    @staticmethod
    def display_name(directory):
        segs = directory.split("_")
        if len(segs) > 1:
            return "({}){}".format(segs[0], " ".join(segs[1:]))
        return directory

    @staticmethod
    def common_prefix(names):
        if not names:
            return ""
        prefix = names[0]
        for name in names[1:]:
            while not name.startswith(prefix):
                prefix = prefix[:-1]
                if not prefix:
                    return ""
        return prefix

    def kinds(self, all_packs):
        """Directory suffix after stripping the common prefix (the kind).

        Prefix is taken from the shared prefix of every top-level dir; a
        single pack or an empty common prefix falls back to the full name.
        """
        prefix = self.common_prefix(list(all_packs))
        return {directory: (directory[len(prefix):]
                            if prefix and prefix != directory
                            and directory.startswith(prefix) else directory)
                for directory in all_packs}

    def resolve_pack(self, name, all_packs):
        """Resolve a pack reference: exact top dir, suffix kind, display name."""
        if name in all_packs:
            return name, all_packs[name]
        kinds = self.kinds(all_packs)
        for directory, files in all_packs.items():
            if kinds[directory] == name:
                return directory, files
        for directory, files in all_packs.items():
            if self.display_name(directory) == name:
                return directory, files
        available = ", ".join(sorted(self.display_name(d) for d in all_packs))
        raise MarketError(f"unknown pack {name!r}; available: {available}")

    # -- downloading --------------------------------------------------------

    def download_pack(self, directory, files):
        shown = self.display_name(directory)
        print(f"[{shown}] -> {self.dest / directory}/")
        n = 0
        for path, size in files:
            target = safe_target(self.dest, path)
            n += 1
            if target.exists() and not self.force:
                print(f"  {target.name:<40} {human_size(size)}  SKIP (exists)")
                continue
            if self.dry_run:
                print(f"  {target.name:<40} {human_size(size)}  (dry-run)")
                continue
            qref = urllib.parse.quote(self.ref, safe="")
            qpath = urllib.parse.quote(path, safe="/")
            url = f"{RAW_ROOT}/{self.repo}/{qref}/{qpath}"
            data = _fetch_bytes(url)
            if len(data) != size:
                raise MarketError(
                    f"size mismatch for {path}: expected {size}, got {len(data)}")
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_name(target.name + ".part")
            part.write_bytes(data)
            os.replace(part, target)
            print(f"  {target.name:<40} {human_size(size)}  OK")
        return n

    def download_packs(self, directories):
        all_packs = self.packs()
        for directory in directories:
            if directory not in all_packs:
                raise MarketError(f"pack not found: {directory}")
        total_files = 0
        total_bytes = 0
        for i, directory in enumerate(directories, 1):
            files = all_packs[directory]
            total_files += self.download_pack(directory, files)
            total_bytes += sum(size for _, size in files)
        total_files += self.copy_license()
        print(f"Done: {len(directories)} packs · {total_files} files · "
              f"{human_size(total_bytes)} -> {self.dest}/")
        return total_files

    def copy_license(self):
        target = None
        for entry in self.fetch_tree():
            if entry.get("type") == "blob" and entry["path"] == "LICENSE":
                target = safe_target(self.dest, entry["path"])
                size = int(entry.get("size") or 0)
                break
        if target is None:
            print("LICENSE not present in market repo (skipped)")
            return 0
        if target.exists() and not self.force:
            print(f"LICENSE -> {self.dest}/LICENSE  SKIP (exists)")
            return 1
        if self.dry_run:
            print(f"LICENSE -> {self.dest}/LICENSE  (dry-run)")
            return 0
        qref = urllib.parse.quote(self.ref, safe="")
        url = f"{RAW_ROOT}/{self.repo}/{qref}/LICENSE"
        data = _fetch_bytes(url)
        if len(data) != size:
            raise MarketError(f"size mismatch for LICENSE: expected {size}, got {len(data)}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        print(f"LICENSE -> {self.dest}/LICENSE  OK")
        return 1

    # -- interactive numeric pack menu --------------------------------------

    def menu(self):
        while True:
            all_packs = self.packs()
            if not all_packs:
                raise MarketError(f"no packs found in {self.repo} @ {self.ref}")
            widths = [len(self.display_name(d)) for d in all_packs]
            pad = max(widths) if widths else 0
            print("")
            print("Naiz Asset Market")
            print(f"  repo : {self.repo}   @ {self.ref}")
            print(f"  {len(all_packs)} packs  ->  {self.dest}/ (gitignored)")
            print("")
            for i, (directory, files) in enumerate(all_packs.items(), 1):
                total = sum(size for _, size in files)
                print(f"  [{i}]  {self.display_name(directory):<{pad}}  "
                      f"{len(files)} files  {human_size(total)}")
            print("  [0]  退出")
            try:
                raw = input("  输入编号 (支持 1 2 或 1-2, 回车即整包下载): ").strip()
            except EOFError:
                print("")
                return
            if raw == "q" or raw == "0":
                return
            try:
                indexes = parse_selection(raw, len(all_packs))
            except ValueError as e:
                print(f"  无效输入: {e}")
                continue
            if not indexes:
                continue
            directories = [list(all_packs)[i - 1] for i in indexes]
            self.download_packs(directories)


def parse_selection(text, size):
    """Parse '1', '1 2', '1-3', '1,2 3' into 1-based ints (sorted, deduped)."""
    cleaned = text.replace(",", " ")
    result = []
    for token in cleaned.split():
        if "-" in token:
            left, _, right = token.partition("-")
            if not (left.isdigit() and right.isdigit()):
                raise ValueError(f"bad range {token!r}")
            if int(right) < int(left):
                raise ValueError(f"descending range {token!r}")
            result.extend(range(int(left), int(right) + 1))
        elif token.isdigit():
            result.append(int(token))
        else:
            raise ValueError(f"bad token {token!r}")
    if any(idx < 1 or idx > size for idx in result):
        raise ValueError(f"index out of range (1..{size})")
    return sorted(set(result))


# ---------------------------------------------------------------------------
# Non-interactive commands
# ---------------------------------------------------------------------------

def cmd_list(market):
    all_packs = market.packs()
    if not all_packs:
        print(f"(no packs in {market.repo} @ {market.ref})")
        return 0
    widths = [len(market.display_name(d)) for d in all_packs]
    pad = max(widths)
    print(f"Naiz Asset Market — {market.repo} @ {market.ref}")
    print(f"{len(all_packs)} packs · {sum(len(f) for f in all_packs.values())} files "
          f"({human_size(sum(s for f in all_packs.values() for _, s in f))})")
    print("")
    for directory, files in all_packs.items():
        total = sum(size for _, size in files)
        print(f"{market.display_name(directory):<{pad}}  {len(files)} files  "
              f"{human_size(total)}   ({directory})")
    return 0


def cmd_cats(market):
    all_packs = market.packs()
    print(f"{len(all_packs)} packs")
    for directory, files in all_packs.items():
        print(f"  {market.display_name(directory)}  {len(files)} files")
    return 0


# ---------------------------------------------------------------------------
# Config + entry point
# ---------------------------------------------------------------------------

def default_config_path():
    return Path(__file__).resolve().parent.parent.parent / DEFAULT_CONFIG_NAME


def load_config(ns):
    cfg_path = Path(getattr(ns, "config", "") or default_config_path())
    data = {}
    if cfg_path.is_file():
        import tomllib
        with open(cfg_path, "rb") as fh:
            data = tomllib.load(fh)
    cfg = data.get("market", {}) if isinstance(data, dict) else {}
    repo = getattr(ns, "repo", None) or cfg.get("repo")
    ref = getattr(ns, "ref", None) or cfg.get("ref") or "main"
    dest = getattr(ns, "dest", None) or cfg.get("dest") or "assets_samples"
    if not repo:
        raise MarketError(
            "no market repo configured: set [market] repo in "
            f"{cfg_path} or pass --repo OWNER/REPO")
    return repo, ref, dest


def build_parser():
    parser = argparse.ArgumentParser(
        prog="market",
        description="Naiz asset-market pack downloader (see AGENTS.md section 13).",
    )
    sub = parser.add_subparsers(dest="cmd")

    def add_common(sp):
        sp.add_argument("--repo", help="market repo OWNER/NAME (overrides market.toml)")
        sp.add_argument("--ref", help="git ref/branch to fetch (default: ref from market.toml)")
        sp.add_argument("--dest", help="download root (default: from market.toml)")
        sp.add_argument("--config", help=f"TOML config path (default: <root>/{DEFAULT_CONFIG_NAME})")
        sp.add_argument("--dry-run", action="store_true", help="plan only, no writes")
        sp.add_argument("--force", action="store_true",
                        help="re-download and overwrite existing files (default: skip)")

    sp = sub.add_parser("list", help="list all packs")
    add_common(sp)
    sp = sub.add_parser("cats", help="list pack display names and counts")
    add_common(sp)
    sp = sub.add_parser("menu", help="interactive numeric pack picker")
    add_common(sp)
    sp = sub.add_parser("get", help="download named packs")
    add_common(sp)
    sp.add_argument("packs", nargs="+", help="pack refs: exact dir / suffix kind")
    sp = sub.add_parser("get-all", help="download every pack")
    add_common(sp)
    return parser


def main(argv=None):
    ns = build_parser().parse_args(argv)
    try:
        repo, ref, dest = load_config(ns)
        market = Market(repo, ref, dest, dry_run=bool(getattr(ns, "dry_run", False)),
                        force=bool(getattr(ns, "force", False)))
        cmd = ns.cmd or "menu"
        if cmd == "list":
            return cmd_list(market)
        if cmd == "cats":
            return cmd_cats(market)
        if cmd == "menu":
            market.menu()
            return 0
        if cmd == "get":
            all_packs = market.packs()
            directories = []
            for arg in ns.packs:
                directory, _ = market.resolve_pack(arg, all_packs)
                directories.append(directory)
            market.download_packs(directories)
            return 0
        if cmd == "get-all":
            directories = list(market.packs())
            market.download_packs(directories)
            return 0
        raise MarketError(f"unknown command {cmd!r}")
    except MarketError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())