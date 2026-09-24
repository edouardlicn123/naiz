"""Animation script (.na) parser (devdoc 78 §3, devdoc 79).

Animation scripts are separated from story scripts (.nb) by extension
and directory (animation/projects/<project>/scripts/<name>.na); this
parser enforces the .na suffix at entry so a story script can never be
fed through the animation toolchain.

Parses one .na animation script into an AnimScriptDef. Text-level duties
only: command dispatch, field validation, name resolution against the
project animation DB, tick conversion. Image/pal *content* loading happens
in the assembly layer (anim_import.py); parse_pal_file() is provided here
as the shared V7 validator for .pal difference files.

Grammar (duration in parens, brace payload = bare asset names):

    animaconf(<type>,<track>,<project>)   # exactly once, first, bare-paren form
                                          # e.g. animaconf(cine,pixel,animatest);
                                          # <project> selects both the assets
                                          # folder and animation/db/<project>.db;
                                          # loop policy belongs to the player,
                                          # never the script/container
    frame(<seconds>){<name>[,<name>...]}  # pixel track; explicit sequence,
                                          # each entry shares <seconds>
    base(){<name>}                        # palette track base image, once
    pal(<seconds>){<name>[,<name>...]}    # palette difference tables

Name resolution: bare names are looked up in the per-project SQLite index
animation/db/<project>.db (table `assets`, kind 'png' for frame/base and
'pal' for pal), then mapped to assets/<project>/anim/<filename>. Register
files with `anima.sh register <project>` before building.

Validation rules V1-V7 per devdoc 78 §3.3. All failures raise SystemExit(1)
with "anim_script: <file>:<line>: <reason>" messages — no silent fallbacks.
"""

import math
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

from naiz_lib.nb_line import parse_nb_line


@dataclass
class AnimStep:
    """One frame()/pal() declaration line."""
    kind: str          # 'frame' | 'pal'
    path: str          # bare asset name from the script (DB key)
    resolved: Path     # absolute path resolved via the project animation DB
    seconds: float
    ticks: int
    line: int          # 1-based script line number


@dataclass
class AnimScriptDef:
    name: str              # script stem, e.g. "test"
    type: str = ""         # 'fullscreen' | 'cine'
    track: str = ""        # 'pixel' | 'palette'
    project: str = ""      # assets/<project>/ scope; must exist
    base: object = None    # Path | None (palette track base image)
    steps: list = field(default_factory=list)    # list[AnimStep]
    warnings: list = field(default_factory=list) # non-fatal notices


def _fail(filename, lineno, msg):
    print(f"anim_script: {filename}:{lineno}: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _strip_inline_comment(line):
    """Strip '#' comments outside {...} (mirrors nb.c depth-aware logic)."""
    depth = 0
    for i, ch in enumerate(line):
        if ch == '{':
            depth += 1
        elif ch == '}' and depth > 0:
            depth -= 1
        elif ch == '#' and depth == 0:
            return line[:i]
    return line


def _convert_ticks(filename, lineno, seconds):
    """seconds -> 60Hz ticks; warns on non-integer frame boundaries."""
    exact = seconds * 60
    ticks = max(1, round(exact))
    if abs(exact - ticks) > 0.005:
        print(f"anim_script: {filename}:{lineno}: WARN 秒数非整帧边界 "
              f"({seconds}s -> tick {ticks}, 精确值 {exact:.3f})")
    return ticks


def _name_list(filename, lineno, cmdname, text):
    """Split the brace payload into bare asset names and validate each."""
    names = [n.strip() for n in text.split(',')]
    for n in names:
        if not n:
            _fail(filename, lineno, f"{cmdname} 花括号存在空项")
        if n.startswith('.') or '/' in n or '\\' in n:
            _fail(filename, lineno, f"非法素材名: '{n}'（须为裸名字，"
                                    f"不含路径分隔符与扩展名）")
    return names


def _resolve_name(filename, lineno, cmdname, name, db_path, scope_dir):
    """Look up one bare name in the project animation DB.

    kind is 'pal' for pal() entries and 'png' otherwise. Returns the
    concrete file path under assets/<project>/anim/.
    """
    if not db_path.is_file():
        _fail(filename, lineno,
              f"动画数据库不存在: {db_path}"
              f"（先运行 anima.sh register 登记素材）")
    kind = 'pal' if cmdname == 'pal' else 'png'
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT filename FROM assets WHERE name=? AND kind=?",
            (name, kind)).fetchone()
        known = [r[0] for r in conn.execute(
            "SELECT name FROM assets WHERE kind=? ORDER BY name", (kind,))]
    finally:
        conn.close()
    if row is None:
        listing = ', '.join(known) if known else '（库为空）'
        _fail(filename, lineno,
              f"未登记的名字: '{name}'（{cmdname} 查询 kind={kind}；"
              f"库中名单: {listing}）")
    resolved = scope_dir / row[0]
    if not resolved.is_file():
        _fail(filename, lineno,
              f"已登记但文件缺失: {resolved}（重新运行 anima.sh register）")
    return resolved


def _paren_seconds(filename, lineno, cmdname, args):
    """Extract exactly one seconds argument from the paren list."""
    if len(args) != 1:
        _fail(filename, lineno,
              f"{cmdname} 括号内需要恰好 1 个秒数参数"
              f"（正确形式 {cmdname}(<秒数>){{<名>[,<名>...]}}），得到 {len(args)} 个")
    return _parse_seconds(filename, lineno, args[0])


def parse_anim_script(script_path, assets_root, db_root):
    """Parse one animation script (.na).

    <db_root> is the project's animation DB directory
    (animation/projects/<project>/db/); the per-project index lives at
    db_root/<project>.db.

    Returns AnimScriptDef; raises SystemExit(1) on any F1/V1-V7 violation.
    """
    script_path = Path(script_path)
    filename = script_path.name

    # F1 (devdoc 79): animation scripts carry the dedicated .na suffix;
    # anything else (notably story .nb) is refused before any parsing.
    if script_path.suffix.lower() != '.na':
        _fail(str(script_path), 0,
              f"动画脚本须为 .na 后缀（与剧本脚本 .nb 分离）: {script_path}")

    db_root = Path(db_root)

    try:
        text = script_path.read_text(encoding='utf-8')
    except OSError as e:
        print(f"anim_script: 无法读取脚本 {script_path}: {e}", file=sys.stderr)
        raise SystemExit(1)
    if text.startswith('\ufeff'):
        text = text[1:]

    defn = AnimScriptDef(name=script_path.stem)
    conf_seen = False
    base_seen = False

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = _strip_inline_comment(raw_line).strip()
        if not line or line.startswith('#'):
            continue

        parsed = parse_nb_line(line)
        if parsed is None:
            _fail(filename, lineno,
                  f"无法识别的行（须为 cmd(){{字段}} 或 cmd(<秒数>){{路径}} 花括号形式）: "
                  f"{raw_line.strip()}")

        cmd = parsed.cmd

        if cmd == 'animaconf':
            if conf_seen:
                _fail(filename, lineno, "animaconf 重复声明")
            if parsed.text is not None:
                _fail(filename, lineno,
                      f"animaconf 参数应写在括号内（裸括号形式，无花括号载荷）"
                      f"（正确形式 animaconf(<区域>,<轨道>,<项目名>)）")
            if len(parsed.args) != 3:
                _fail(filename, lineno,
                      f"animaconf 需要 3 个参数（区域,轨道,项目名），"
                      f"得到 {len(parsed.args)} 个")
            type_str, track_str, project_str = parsed.args
            if type_str not in ('fullscreen', 'cine'):
                _fail(filename, lineno, f"区域类型非法: {type_str}")
            if track_str not in ('pixel', 'palette'):
                _fail(filename, lineno, f"轨道类型非法: {track_str}")
            if (not project_str or project_str in ('.', '..')
                    or '/' in project_str or '\\' in project_str):
                _fail(filename, lineno, f"项目名非法: {project_str}")
            if not (assets_root / project_str).is_dir():
                _fail(filename, lineno,
                      f"项目目录不存在: assets/{project_str}/ "
                      f"（需先创建并放入素材）")
            defn.type = type_str
            defn.track = track_str
            defn.project = project_str
            conf_seen = True
            continue

        if cmd not in ('frame', 'base', 'pal'):
            _fail(filename, lineno, f"未知命令: {cmd}")

        if parsed.text is None:
            _fail(filename, lineno,
                  f"{cmd} 必须使用花括号形式（cmd(<秒数>){{<名>[,<名>...]}}）；"
                  f"仅 animaconf 使用裸括号参数形式")

        if not conf_seen:
            _fail(filename, lineno, "首条命令必须是 animaconf")

        db_path = db_root / f"{defn.project}.db"
        scope_dir = assets_root / defn.project / "anim"

        if cmd == 'frame':
            if defn.track != 'pixel':
                _fail(filename, lineno, "frame 仅限 pixel 轨使用")
            names = _name_list(filename, lineno, 'frame', parsed.text)
            seconds = _paren_seconds(filename, lineno, 'frame', parsed.args)
            ticks = _convert_ticks(filename, lineno, seconds)
            for n in names:
                resolved = _resolve_name(filename, lineno, 'frame', n,
                                         db_path, scope_dir)
                defn.steps.append(AnimStep(
                    kind='frame', path=n, resolved=resolved,
                    seconds=seconds, ticks=ticks, line=lineno))

        elif cmd == 'base':
            if defn.track != 'palette':
                _fail(filename, lineno, "base 仅限 palette 轨使用")
            if base_seen:
                _fail(filename, lineno, "base 重复声明")
            names = _name_list(filename, lineno, 'base', parsed.text)
            if len(names) != 1:
                _fail(filename, lineno,
                      f"base 需要恰好 1 个底图名字，得到 {len(names)} 个")
            defn.base = _resolve_name(filename, lineno, 'base', names[0],
                                      db_path, scope_dir)
            base_seen = True

        elif cmd == 'pal':
            if defn.track != 'palette':
                _fail(filename, lineno, "pal 仅限 palette 轨使用")
            if not base_seen:
                _fail(filename, lineno, "pal 必须出现在 base 之后")
            names = _name_list(filename, lineno, 'pal', parsed.text)
            seconds = _paren_seconds(filename, lineno, 'pal', parsed.args)
            ticks = _convert_ticks(filename, lineno, seconds)
            for n in names:
                resolved = _resolve_name(filename, lineno, 'pal', n,
                                         db_path, scope_dir)
                defn.steps.append(AnimStep(
                    kind='pal', path=n, resolved=resolved,
                    seconds=seconds, ticks=ticks, line=lineno))

        else:
            _fail(filename, lineno, f"未知命令: {cmd}")

    if not conf_seen:
        _fail(filename, 0, "缺少 animaconf 头部声明")
    if defn.track == 'pixel':
        if not any(s.kind == 'frame' for s in defn.steps):
            _fail(filename, 0, "pixel 轨至少需要一帧 frame()")
    else:
        if not base_seen:
            _fail(filename, 0, "palette 轨需要恰好一个 base()")
        if not any(s.kind == 'pal' for s in defn.steps):
            _fail(filename, 0, "palette 轨至少需要一个 pal()")

    return defn


def _parse_seconds(filename, lineno, raw):
    try:
        seconds = float(raw)
    except ValueError:
        _fail(filename, lineno, f"秒数不是数字: {raw}")
    if not math.isfinite(seconds) or seconds <= 0:
        _fail(filename, lineno, f"秒数必须为正数: {raw}")
    return seconds


def parse_pal_file(pal_path):
    """Parse a .pal difference file (V7).

    Format: one entry per line, "<index> <R> <G> <B>" (4 integers);
    '#' comments and blank lines skipped; at most 256 entries;
    duplicate index within one file is an error.

    Returns dict {index: (r, g, b)}. Raises SystemExit(1) on violation.
    """
    pal_path = Path(pal_path)
    name = pal_path.name
    entries = {}
    try:
        text = pal_path.read_text(encoding='utf-8')
    except OSError as e:
        print(f"anim_script: 无法读取 pal 文件 {pal_path}: {e}", file=sys.stderr)
        raise SystemExit(1)

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split('#', 1)[0].strip()
        if not line:
            continue
        tokens = line.split()
        if len(tokens) != 4:
            _fail(name, lineno, f"需要 4 列整数 <index> <R> <G> <B>，得到 {len(tokens)} 列")
        try:
            idx, r, g, b = (int(t) for t in tokens)
        except ValueError:
            _fail(name, lineno, f"非整数值: {line}")
        if not (0 <= idx <= 255):
            _fail(name, lineno, f"索引越界 [0,255]: {idx}")
        if not all(0 <= v <= 255 for v in (r, g, b)):
            _fail(name, lineno, f"RGB 分量越界 [0,255]: {r} {g} {b}")
        if idx in entries:
            _fail(name, lineno, f"索引 {idx} 在同一文件中重复")
        entries[idx] = (r, g, b)

    return entries
