"""Animation script (.na) parser tests — devdoc 78 §3, devdoc 79.

Covers positive parsing (pixel/palette tracks, multi-name brace
sequences, tick conversion, comment handling, encoding tolerance),
bare-name DB resolution, the F1 .na-suffix gate, and every V1-V8
rejection branch, plus the V7 .pal difference-file validator.
"""

import re
import sqlite3
from pathlib import Path

import pytest

from naiz_build.anim_script import parse_anim_script, parse_pal_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    name     TEXT NOT NULL,
    filename TEXT NOT NULL,
    kind     TEXT NOT NULL,
    mtime    REAL NOT NULL,
    size     INTEGER NOT NULL,
    PRIMARY KEY (name, kind)
)
"""

_RE_HEADER = re.compile(r'^\s*animaconf\s*\(([^)]*)\)', re.MULTILINE)


def _header_project(text):
    """Peek the animaconf project name from script text."""
    if text.startswith('\ufeff'):
        text = text[1:]
    m = _RE_HEADER.search(text)
    if m:
        args = [a.strip() for a in m.group(1).split(',')]
        if len(args) == 3 and args[2]:
            return args[2]
    return "_loose"   # scripts without a valid header still need a home


def _db_root(tmp_path, ref):
    """Per-project db dir (animation/projects/<p>/db/) for a script."""
    text = ref.read_text(encoding="utf-8") if isinstance(ref, Path) else ref
    return tmp_path / "animation" / "projects" / _header_project(text) / "db"


def _make_asset(assets_root, project, filename):
    """Create one dummy asset file under assets/<project>/anim/."""
    anim_dir = assets_root / project / "anim"
    anim_dir.mkdir(parents=True, exist_ok=True)
    (anim_dir / filename).write_bytes(b"x")


def _make_db(tmp_path, project, rows):
    """Create the project animation DB; rows are (name, kind, filename)."""
    db_dir = tmp_path / "animation" / "projects" / project / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_dir / f"{project}.db")
    conn.execute(_DB_SCHEMA)
    conn.executemany(
        "INSERT INTO assets(name, filename, kind, mtime, size) "
        "VALUES (?, ?, ?, 0, 0)",
        [(n, f, k) for n, k, f in rows])
    conn.commit()
    conn.close()


PIXEL_NB = """\
animaconf(fullscreen,pixel,aniframe)
frame(0.5){a}
frame(0.5){b}
"""


def _write_script(tmp_path, text, name="test", suffix=".na"):
    script_dir = (tmp_path / "animation" / "projects"
                  / _header_project(text) / "scripts")
    script_dir.mkdir(parents=True, exist_ok=True)
    script = script_dir / f"{name}{suffix}"
    script.write_text(text, encoding="utf-8")
    return script


def _expect_fail(script, assets_root, db_root, capsys, frag):
    with pytest.raises(SystemExit) as ei:
        parse_anim_script(script, assets_root, db_root)
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "anim_script:" in err
    assert frag in err
    return err


# ---------------------------------------------------------------------------
# Positive cases
# ---------------------------------------------------------------------------

def test_pixel_minimal(tmp_path):
    root = tmp_path / "assets"
    for f in ("a.png", "b.png"):
        _make_asset(root, "aniframe", f)
    _make_db(tmp_path, "aniframe",
             [("a", "png", "a.png"), ("b", "png", "b.png")])
    script = _write_script(tmp_path, PIXEL_NB)
    d = parse_anim_script(script, root, _db_root(tmp_path, script))
    assert d.name == "test"
    assert (d.type, d.track, d.project) == ("fullscreen", "pixel", "aniframe")
    assert [s.ticks for s in d.steps] == [30, 30]
    assert d.steps[0].path == "a"
    assert d.steps[0].resolved == root / "aniframe" / "anim" / "a.png"
    assert d.base is None and d.warnings == []


def test_pixel_multi_name_sequence_expansion(tmp_path):
    root = tmp_path / "assets"
    for f in ("f1.png", "f2.png"):
        _make_asset(root, "p", f)
    _make_db(tmp_path, "p",
             [("f1", "png", "f1.png"), ("f2", "png", "f2.png")])
    script = _write_script(
        tmp_path, "animaconf(fullscreen,pixel,p)\nframe(0.5){f1,f2,f1,f2}\n")
    d = parse_anim_script(script, root, _db_root(tmp_path, script))
    assert [s.path for s in d.steps] == ["f1", "f2", "f1", "f2"]
    assert [s.ticks for s in d.steps] == [30, 30, 30, 30]
    assert all(s.seconds == 0.5 for s in d.steps)


def test_palette_minimal(tmp_path):
    root = tmp_path / "assets"
    _make_asset(root, "aniface", "bg.png")
    _make_asset(root, "aniface", "p1.pal")
    _make_db(tmp_path, "aniface",
             [("bg", "png", "bg.png"), ("p1", "pal", "p1.pal")])
    script = _write_script(tmp_path, """\
animaconf(cine,palette,aniface)
base(){bg}
pal(0.1){p1}
""")
    d = parse_anim_script(script, root, _db_root(tmp_path, script))
    assert (d.type, d.track, d.project) == ("cine", "palette", "aniface")
    assert d.base == root / "aniface" / "anim" / "bg.png"
    assert len(d.steps) == 1 and d.steps[0].kind == "pal"
    assert d.steps[0].ticks == 6


@pytest.mark.parametrize("sec,ticks", [
    ("0.5", 30),
    ("0.1", 6),
    ("0.016", 1),   # round(0.96) -> 1
    ("1", 60),
    ("2.5", 150),
])
def test_tick_conversion(tmp_path, sec, ticks):
    root = tmp_path / "assets"
    _make_asset(root, "p", "f.png")
    _make_db(tmp_path, "p", [("f", "png", "f.png")])
    script = _write_script(
        tmp_path, f"animaconf(fullscreen,pixel,p)\nframe({sec}){{f}}\n")
    d = parse_anim_script(script, root, _db_root(tmp_path, script))
    assert d.steps[0].ticks == ticks


def test_inline_comment_and_blank_lines(tmp_path):
    root = tmp_path / "assets"
    _make_asset(root, "p", "f.png")
    _make_db(tmp_path, "p", [("f", "png", "f.png")])
    script = _write_script(tmp_path, """\
# 整行注释

animaconf(fullscreen,pixel,p)  # 行内注释
frame(0.5){f}      # 尾随注释
""")
    d = parse_anim_script(script, root, _db_root(tmp_path, script))
    assert len(d.steps) == 1


def test_crlf_and_bom_tolerated(tmp_path):
    root = tmp_path / "assets"
    _make_asset(root, "p", "f.png")
    _make_db(tmp_path, "p", [("f", "png", "f.png")])
    body = "animaconf(fullscreen,pixel,p)\r\nframe(0.5){f}\r\n"
    script = _write_script(tmp_path, "")
    script.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    d = parse_anim_script(script, root, _db_root(tmp_path, script))
    assert len(d.steps) == 1


# ---------------------------------------------------------------------------
# F1: .na suffix gate (devdoc 79)
# ---------------------------------------------------------------------------

def test_f1_rejects_nb_suffix(tmp_path, capsys):
    script = _write_script(tmp_path, PIXEL_NB, suffix=".nb")
    _expect_fail(script, tmp_path / "assets", _db_root(tmp_path, script),
                 capsys, "动画脚本须为 .na 后缀")


def test_f1_rejects_no_suffix(tmp_path, capsys):
    script = _write_script(tmp_path, PIXEL_NB, suffix="")
    _expect_fail(script, tmp_path / "assets", _db_root(tmp_path, script),
                 capsys, "动画脚本须为 .na 后缀")


# ---------------------------------------------------------------------------
# V1/V2: animaconf placement, form & enums
# ---------------------------------------------------------------------------

def test_v1_missing_animaconf(tmp_path, capsys):
    script = _write_script(tmp_path, "# 只有注释，无任何命令\n")
    _expect_fail(script, tmp_path / "assets", _db_root(tmp_path, script),
                 capsys, "缺少 animaconf")


def test_v1_duplicate_animaconf(tmp_path, capsys):
    root = tmp_path / "assets"
    _make_asset(root, "p", "f.png")
    script = _write_script(tmp_path,
                           "animaconf(fullscreen,pixel,p)\n"
                           "animaconf(fullscreen,pixel,p)\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys, "重复声明")


def test_v1_animaconf_not_first(tmp_path, capsys):
    root = tmp_path / "assets"
    _make_asset(root, "p", "f.png")
    script = _write_script(tmp_path,
                           "frame(0.5){f}\n"
                           "animaconf(fullscreen,pixel,p)\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys,
                 "首条命令必须是 animaconf")


@pytest.mark.parametrize("args_line,frag", [
    ("animaconf(full,pixel,p)", "区域类型非法"),
    ("animaconf(fullscreen,color,p)", "轨道类型非法"),
    ("animaconf(fullscreen,pixel)", "得到 2 个"),
    ("animaconf(fullscreen,pixel,p,x)", "得到 4 个"),
])
def test_v2_bad_args(tmp_path, capsys, args_line, frag):
    script = _write_script(tmp_path, args_line + "\n")
    _expect_fail(script, tmp_path / "assets", _db_root(tmp_path, script),
                 capsys, frag)


@pytest.mark.parametrize("line", [
    "animaconf(){fullscreen,pixel,p}",       # legacy braces form
    "animaconf(cine,pixel,p){x}",            # stray payload
])
def test_v2_braces_form_rejected(tmp_path, capsys, line):
    script = _write_script(tmp_path, line + "\n")
    _expect_fail(script, tmp_path / "assets", _db_root(tmp_path, script),
                 capsys, "裸括号")


# ---------------------------------------------------------------------------
# V8: project declaration
# ---------------------------------------------------------------------------

def test_v8_project_dir_missing(tmp_path, capsys):
    root = tmp_path / "assets"
    root.mkdir()
    script = _write_script(tmp_path, "animaconf(cine,pixel,nodir)\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys,
                 "项目目录不存在: assets/nodir/")


@pytest.mark.parametrize("bad", ["../p", ".", "a/b"])
def test_v8_bad_project_name(tmp_path, capsys, bad):
    root = tmp_path / "assets"
    _make_asset(root, "p", "f.png")
    script = _write_script(
        tmp_path,
        f"animaconf(cine,pixel,{bad})\nframe(0.5){{f}}\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys, "项目名非法")


# ---------------------------------------------------------------------------
# Name resolution against the project animation DB
# ---------------------------------------------------------------------------

def test_db_missing_hints_register(tmp_path, capsys):
    root = tmp_path / "assets"
    _make_asset(root, "p", "f.png")
    script = _write_script(
        tmp_path, "animaconf(fullscreen,pixel,p)\nframe(0.5){f}\n")
    err = _expect_fail(script, root, _db_root(tmp_path, script), capsys,
                       "动画数据库不存在")
    assert "register" in err


def test_unregistered_name_lists_known_names(tmp_path, capsys):
    root = tmp_path / "assets"
    _make_asset(root, "p", "a.png")
    _make_asset(root, "p", "b.png")
    _make_db(tmp_path, "p", [("a", "png", "a.png")])
    script = _write_script(
        tmp_path, "animaconf(fullscreen,pixel,p)\nframe(0.5){zzz}\n")
    err = _expect_fail(script, root, _db_root(tmp_path, script), capsys, "未登记的名字")
    assert "'zzz'" in err and "a" in err


def test_registered_but_file_missing(tmp_path, capsys):
    root = tmp_path / "assets"
    _make_asset(root, "p", "keep.png")   # keep anim/ dir alive
    _make_db(tmp_path, "p", [("gone", "png", "gone.png")])
    script = _write_script(
        tmp_path, "animaconf(fullscreen,pixel,p)\nframe(0.5){gone}\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys, "已登记但文件缺失")


def test_kind_separation_png_vs_pal(tmp_path, capsys):
    # 'p1' exists only as kind='pal'; frame() looks up kind='png' -> miss
    root = tmp_path / "assets"
    _make_asset(root, "p", "p1.pal")
    _make_db(tmp_path, "p", [("p1", "pal", "p1.pal")])
    script = _write_script(
        tmp_path, "animaconf(fullscreen,pixel,p)\nframe(0.5){p1}\n")
    err = _expect_fail(script, root, _db_root(tmp_path, script), capsys, "未登记的名字")
    assert "kind=png" in err


@pytest.mark.parametrize("payload", ["a,", ",a"])
def test_empty_brace_item_rejected(tmp_path, capsys, payload):
    root = tmp_path / "assets"
    _make_asset(root, "p", "a.png")
    _make_db(tmp_path, "p", [("a", "png", "a.png")])
    script = _write_script(
        tmp_path,
        f"animaconf(fullscreen,pixel,p)\nframe(0.5){{{payload}}}\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys, "空项")


@pytest.mark.parametrize("payload", ["../x", "a/b", ".hidden"])
def test_illegal_name_rejected(tmp_path, capsys, payload):
    root = tmp_path / "assets"
    _make_asset(root, "p", "a.png")
    _make_db(tmp_path, "p", [("a", "png", "a.png")])
    script = _write_script(
        tmp_path,
        f"animaconf(fullscreen,pixel,p)\nframe(0.5){{{payload}}}\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys, "非法素材名")


# ---------------------------------------------------------------------------
# V3: cross-track commands
# ---------------------------------------------------------------------------

def test_v3_frame_on_palette_track(tmp_path, capsys):
    root = tmp_path / "assets"
    for f in ("bg.png", "p.pal", "f.png"):
        _make_asset(root, "p", f)
    _make_db(tmp_path, "p", [
        ("bg", "png", "bg.png"), ("p1", "pal", "p.pal"),
        ("f", "png", "f.png")])
    script = _write_script(tmp_path,
                           "animaconf(cine,palette,p)\n"
                           "base(){bg}\n"
                           "frame(0.5){f}\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys, "frame 仅限 pixel 轨")


def test_v3_base_on_pixel_track(tmp_path, capsys):
    root = tmp_path / "assets"
    _make_asset(root, "p", "f.png")
    _make_asset(root, "p", "bg.png")
    _make_db(tmp_path, "p", [
        ("f", "png", "f.png"), ("bg", "png", "bg.png")])
    script = _write_script(tmp_path,
                           "animaconf(fullscreen,pixel,p)\n"
                           "base(){bg}\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys, "base 仅限 palette 轨")


def test_v3_pal_on_pixel_track(tmp_path, capsys):
    root = tmp_path / "assets"
    _make_asset(root, "p", "f.png")
    _make_asset(root, "p", "p.pal")
    _make_db(tmp_path, "p", [
        ("f", "png", "f.png"), ("pp", "pal", "p.pal")])
    script = _write_script(tmp_path,
                           "animaconf(fullscreen,pixel,p)\n"
                           "pal(0.1){pp}\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys, "pal 仅限 palette 轨")


# ---------------------------------------------------------------------------
# V4: per-track cardinality
# ---------------------------------------------------------------------------

def test_v4_pixel_without_frames(tmp_path, capsys):
    root = tmp_path / "assets"
    _make_asset(root, "p", "keep.png")
    script = _write_script(tmp_path, "animaconf(fullscreen,pixel,p)\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys, "至少需要一帧")


def test_v4_palette_missing_base(tmp_path, capsys):
    root = tmp_path / "assets"
    _make_asset(root, "p", "p.pal")
    _make_db(tmp_path, "p", [("pp", "pal", "p.pal")])
    script = _write_script(tmp_path,
                           "animaconf(cine,palette,p)\n"
                           "pal(0.1){pp}\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys, "base 之后")


def test_v4_duplicate_base(tmp_path, capsys):
    root = tmp_path / "assets"
    _make_asset(root, "p", "bg.png")
    _make_asset(root, "p", "p.pal")
    _make_db(tmp_path, "p", [
        ("bg", "png", "bg.png"), ("pp", "pal", "p.pal")])
    script = _write_script(tmp_path,
                           "animaconf(cine,palette,p)\n"
                           "base(){bg}\n"
                           "base(){bg}\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys, "base 重复")


def test_v4_palette_without_pal_steps(tmp_path, capsys):
    root = tmp_path / "assets"
    _make_asset(root, "p", "bg.png")
    _make_db(tmp_path, "p", [("bg", "png", "bg.png")])
    script = _write_script(tmp_path,
                           "animaconf(cine,palette,p)\n"
                           "base(){bg}\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys, "至少需要一个 pal")


def test_base_multi_name_rejected(tmp_path, capsys):
    root = tmp_path / "assets"
    _make_asset(root, "p", "bg.png")
    _make_asset(root, "p", "bg2.png")
    _make_db(tmp_path, "p", [
        ("bg", "png", "bg.png"), ("bg2", "png", "bg2.png")])
    script = _write_script(tmp_path,
                           "animaconf(cine,palette,p)\n"
                           "base(){bg,bg2}\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys,
                 "base 需要恰好 1 个底图名字")


# ---------------------------------------------------------------------------
# Seconds validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sec", ["0", "-1", "abc", "nan", "inf"])
def test_bad_seconds(tmp_path, capsys, sec):
    root = tmp_path / "assets"
    _make_asset(root, "p", "f.png")
    _make_db(tmp_path, "p", [("f", "png", "f.png")])
    script = _write_script(
        tmp_path,
        f"animaconf(fullscreen,pixel,p)\nframe({sec}){{f}}\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys, "秒数")


# ---------------------------------------------------------------------------
# Unknown commands / bare form
# ---------------------------------------------------------------------------

def test_unknown_command(tmp_path, capsys):
    root = tmp_path / "assets"
    _make_asset(root, "p", "f.png")
    script = _write_script(tmp_path,
                           "animaconf(fullscreen,pixel,p)\n"
                           "wait(){3}\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys, "未知命令")


def test_bare_paren_form_rejected(tmp_path, capsys):
    root = tmp_path / "assets"
    _make_asset(root, "p", "f.png")
    script = _write_script(tmp_path,
                           "animaconf(fullscreen,pixel,p)\n"
                           "frame(0.5)\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys, "花括号")


# ---------------------------------------------------------------------------
# Duration-in-paren validation (frame/pal)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("paren", ["", "0.5,x"])
def test_frame_paren_argument_count(tmp_path, capsys, paren):
    root = tmp_path / "assets"
    _make_asset(root, "p", "f.png")
    _make_db(tmp_path, "p", [("f", "png", "f.png")])
    script = _write_script(
        tmp_path,
        f"animaconf(fullscreen,pixel,p)\nframe({paren}){{f}}\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys,
                 "frame 括号内需要恰好 1 个秒数参数")


def test_pal_paren_argument_count(tmp_path, capsys):
    root = tmp_path / "assets"
    _make_asset(root, "p", "bg.png")
    _make_asset(root, "p", "p.pal")
    _make_db(tmp_path, "p", [
        ("bg", "png", "bg.png"), ("pp", "pal", "p.pal")])
    script = _write_script(tmp_path,
                           "animaconf(cine,palette,p)\n"
                           "base(){bg}\n"
                           "pal(0.1,0.2){pp}\n")
    _expect_fail(script, root, _db_root(tmp_path, script), capsys,
                 "pal 括号内需要恰好 1 个秒数参数")


# ---------------------------------------------------------------------------
# V7: .pal difference file validator
# ---------------------------------------------------------------------------

def test_pal_valid_sparse(tmp_path):
    p = tmp_path / "p.pal"
    p.write_text("# comment\n\n7 255 0 0\n250  1 2 3\n", encoding="utf-8")
    entries = parse_pal_file(p)
    assert entries == {7: (255, 0, 0), 250: (1, 2, 3)}


def test_pal_duplicate_index(tmp_path, capsys):
    p = tmp_path / "p.pal"
    p.write_text("7 1 2 3\n7 4 5 6\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        parse_pal_file(p)
    assert "重复" in capsys.readouterr().err


@pytest.mark.parametrize("line", [
    "256 1 2 3",     # index out of range
    "7 256 0 0",     # R out of range
    "7 1 2",         # too few columns
    "7 1 2 3 4",     # too many columns
    "x 1 2 3",       # non-integer
])
def test_pal_bad_lines(tmp_path, capsys, line):
    p = tmp_path / "p.pal"
    p.write_text(line + "\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        parse_pal_file(p)
    assert "anim_script:" in capsys.readouterr().err
