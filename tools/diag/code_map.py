"""code_map.py — 生成/查询代码地图（devdoc 202）。

三种模式：
  python -m tools.diag.code_map            # 生成 docs/CODE_MAP.auto.md
  python -m tools.diag.code_map --find RE  # 输出 file:line  name
  python -m tools.diag.code_map --check    # 生成物是否最新（过期退出码 1）

只做正则扫描：不依赖编译器，不写行号到生成物（避免重构后漂移）。
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET_DIRS = ("core/engine", "core/lib", "core/plat")
OUTPUT = ROOT / "docs" / "CODE_MAP.auto.md"

# 行首允许的返回类型（与 symbol_audit.py 的判定保持一致）
RET_TYPES = {
    "void", "int", "unsigned", "signed", "char", "short", "long", "float",
    "double", "size_t", "uint8_t", "uint16_t", "uint32_t", "int8_t",
    "int16_t", "int32_t", "const", "static", "MagImage", "MagArchive",
    "SoundDrv", "HAL_MOUSE", "UiRequest", "ImageCacheSlot", "Layer",
}

DEF_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_ \t*]*?)\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
CONTROL = {"if", "while", "for", "switch", "return", "sizeof", "else", "do"}


def file_purpose(path):
    """取文件头注释里第一个 '—' 或 '-' 之后的描述。"""
    try:
        head = path.read_text(encoding="utf-8", errors="ignore").splitlines()[:16]
    except OSError:
        return path.name
    for line in head:
        text = line.strip()
        if not text.startswith("*") and not text.startswith("/*"):
            continue
        for sep in ("—", " - "):
            if sep in text:
                desc = text.split(sep, 1)[1].strip().rstrip("*/").strip()
                if desc:
                    return desc
    return path.name


def public_symbols(path):
    """返回 [(line_no, name)]，跳过 static / 控制语句 / 原型。"""
    out = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return out
    for i, line in enumerate(lines, 1):
        if not line or line[0] in " \t#}/*":
            continue
        if "static" in line.split("(")[0]:
            continue
        m = DEF_RE.match(line)
        if not m:
            continue
        ret, name = m.group(1).strip(), m.group(2)
        if not ret or name in CONTROL:
            continue
        if not (set(ret.split()) & RET_TYPES):
            continue
        if line.rstrip().endswith(";"):
            continue
        out.append((i, name))
    return out


def related_doc(path, doc_index):
    hits = doc_index.get(path.name)
    return hits[0] if hits else "-"


def build_doc_index():
    """文件名 -> [文档名]（只扫 docs/B*.md，跳过 refdocs）。"""
    idx = {}
    for doc in sorted((ROOT / "docs").glob("B*.md")):
        # 跳过地图与全量索引/速查：它们提到每个文件，会淹没真正的模块规范
        if doc.name.startswith(("B90-", "B91-", "B99-")):
            continue
        try:
            text = doc.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for src in (ROOT / "core").rglob("*.c"):
            if src.name in text:
                idx.setdefault(src.name, []).append(doc.name)
    return idx


def iter_sources():
    for rel in TARGET_DIRS:
        for path in sorted((ROOT / rel).glob("*.c")):
            yield rel, path


def generate():
    doc_index = build_doc_index()
    parts = [
        "# CODE_MAP（自动生成，勿手改）",
        "",
        "> 生成命令：`python -m tools.diag.code_map`；校验：`--check`；"
        "定位：`--find <前缀或正则>`",
        "> 只列公共符号与职责，不含行号——需要行号用 `--find`。",
        "",
    ]
    for rel, _ in ((d, None) for d in TARGET_DIRS):
        rows = []
        for d, path in iter_sources():
            if d != rel:
                continue
            syms = public_symbols(path)
            names = ", ".join(n for _, n in syms) or "-"
            rows.append(
                f"| {path.name} | {file_purpose(path)} | {names} ({len(syms)}) "
                f"| {related_doc(path, doc_index)} |"
            )
        parts.append(f"## {rel}/")
        parts.append("")
        parts.append("| 文件 | 职责 | 公共符号 | 相关规范 |")
        parts.append("|---|---|---|---|")
        parts.extend(rows)
        parts.append("")
    return "\n".join(parts) + "\n"


def do_find(pattern):
    rx = re.compile(pattern)
    count = 0
    for _, path in iter_sources():
        rel = path.relative_to(ROOT).as_posix()
        for line_no, name in public_symbols(path):
            if rx.search(name):
                print(f"{rel}:{line_no}  {name}")
                count += 1
    return 0 if count else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Code map generator (devdoc 202).")
    ap.add_argument("--find", metavar="RE", help="按符号名（正则）定位 file:line")
    ap.add_argument("--check", action="store_true", help="生成物是否最新")
    args = ap.parse_args(argv)

    if args.find:
        return do_find(args.find)

    content = generate()
    if args.check:
        if not OUTPUT.exists():
            print(f"missing: {OUTPUT.relative_to(ROOT)}")
            return 1
        if OUTPUT.read_text(encoding="utf-8") != content:
            print("stale: docs/CODE_MAP.auto.md (run python -m tools.diag.code_map)")
            return 1
        print("ok: docs/CODE_MAP.auto.md is up to date")
        return 0

    OUTPUT.write_text(content, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
