#!/usr/bin/env python3
"""Animation script (.na) -> .ANI assembler (devdoc 78 §5.3, devdoc 79).

Usage:
    python -m tools.naiz_build.anim_import <script.na>
             [--out PATH] [--project GAME] [--assets-root DIR] [--sync]

<script.na> lives at animation/projects/<project>/scripts/<name>.na;
<--project>, when given, must equal the script's animaconf project name
(anima.sh build <project>/<name> passes it as the addressing check).

Pipeline:
    [--sync: refresh animation/projects/<project>/db/<project>.db from
     assets/<project>/anim/] ->
    parse_anim_script (bare names resolved via the per-project DB) ->
    load PNGs via mag_convert.convert_image ->
    (pixel track: optional shared-palette remap from the script's
    animaconf project ASSETS.DB) ->
    anim_container.build_ani -> write .ANI + size report.

Production-side tool only: writes a standalone .ANI file, never touches
ASSETS.DB / IMAGE.DAT.
"""

import argparse
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "tools"))

from naiz_lib import PROTECTED_IDX_ALL                     # noqa: E402
from naiz_lib.mag_codec import encode_mag, decode_mag_full  # noqa: E402
from naiz_lib.anim_container import (                       # noqa: E402
    ANI_TRACK_PALETTE,
    AnimContainerDef,
    build_ani,
)
from naiz_build.anim_script import parse_anim_script, parse_pal_file  # noqa: E402
from naiz_build.anim_register import sync_project                     # noqa: E402
from naiz_build.pack_images import load_img_map_assets                # noqa: E402
from naiz_build.anim_project import (                       # noqa: E402
    PROJECTS_ROOT,
    db_dir_for,
    load_project,
)
from naiz_build.pack_images import (                        # noqa: E402
    build_shared_palette,
    remap_pixels_to_palette,
)

ANIM_OUTPUT_DIR = _REPO_ROOT / "animation" / "output"

_RE_ANIMACONF = re.compile(r'^\s*animaconf\s*\(([^)]*)\)', re.MULTILINE)


def _peek_project(script_path):
    """Best-effort pre-parse read of the animaconf project name.

    Returns the project string, or None when no well-formed 3-arg
    animaconf(...) is found (the real parser then reports the precise
    syntax error; under --sync main() dies explicitly instead).
    """
    try:
        text = Path(script_path).read_text(encoding='utf-8')
    except OSError:
        return None
    m = _RE_ANIMACONF.search(text)
    if m is None:
        return None
    args = [a.strip() for a in m.group(1).split(',')]
    if len(args) != 3 or not args[2]:
        return None
    return args[2]


def _die(msg):
    print(f"anim_import: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_image_mag(path):
    """PNG -> quantized MAG bytes -> (pixels, w, h, palette).

    Mirrors background conversion in build_game.convert_png_to_mag:
    reserved-index protection, no resize, 256 colors, 8bpp.
    """
    from PIL import Image
    from naiz_conv.mag_convert import convert_image

    pil_img = Image.open(path)
    mag_data = convert_image(
        pil_img, no_resize=True, num_colors=256, bpp=8,
        reserved=PROTECTED_IDX_ALL)
    result = decode_mag_full(mag_data)
    if result is None:
        _die(f"MAG 解码失败: {path}")
    pixels, w, h, palette, _bpp, _is_sprite = result
    return pixels, w, h, palette


def derive_shared_palette(project_dir):
    """Derive the project shared palette from all IMG/SPR assets."""
    db_path = project_dir / "ASSETS.DB"
    if not db_path.is_file():
        _die(f"ASSETS.DB 不存在: {db_path}")
    image_data = load_img_map_assets(project_dir, types=('IMG', 'SPR'))
    if not image_data:
        _die(f"ASSETS.DB 无 IMG/SPR 资产，无法推导共享色板: {db_path}")
    return build_shared_palette(image_data)


def _check_dimensions(name, w, h, type_str, first_wh):
    if first_wh is None:
        return (w, h)
    if (w, h) != first_wh:
        _die(f"{name}: 帧尺寸不一致 {w}x{h}，首帧为 {first_wh[0]}x{first_wh[1]}")
    return first_wh


def _final_dimension_check(type_str, wh):
    w, h = wh
    if type_str == 'fullscreen':
        if (w, h) != (640, 400):
            _die(f"fullscreen 必须 640x400，实际 {w}x{h}")
    elif type_str == 'cine':
        if (w, h) != (640, 280):
            _die(f"cine 必须 640x280，实际 {w}x{h}")
    else:
        if not (1 <= w <= 640 and 1 <= h <= 400):
            _die(f"未知 type {type_str} 尺寸越界 [1,640]x[1,400]: {w}x{h}")


def assemble_pixel(defn, project_dir):
    """Pixel track: encode frames, optionally remapped to shared palette."""
    shared = None
    if project_dir is not None:
        shared = derive_shared_palette(project_dir)

    blobs = []
    ticks = []
    total_raw = 0
    first_wh = None
    for i, step in enumerate(defn.steps, start=1):
        pixels, w, h, own_pal = load_image_mag(step.resolved)
        first_wh = _check_dimensions(f"帧 {i} ({step.path})", w, h,
                                     defn.type, first_wh)
        if shared is not None:
            new_pixels = remap_pixels_to_palette(
                pixels, w, h, own_pal, shared,
                transparent_idx=None, protected_indices=PROTECTED_IDX_ALL)
            blob = encode_mag(new_pixels, w, h, shared,
                              user_string=b"naiz\x1a", bpp=8)
        else:
            blob = encode_mag(pixels, w, h, own_pal,
                              user_string=b"naiz\x1a", bpp=8)
        blobs.append(blob)
        ticks.append(step.ticks)
        total_raw += w * h * 4

    _final_dimension_check(defn.type, first_wh)
    if shared is None:
        print("=" * 60)
        print(f"WARN: 项目 {defn.project} 无已构建 ASSETS.DB"
              f"（projects/{defn.project}/），帧使用各自量化色板编码。")
        print("播放时若场景共享色板不同，颜色将明显偏差；")
        print("项目构建后需重新导入本动画以获得共享色板。")
        print("=" * 60)

    container = AnimContainerDef(
        type=0 if defn.type == 'fullscreen' else 1,
        track=0,
        width=first_wh[0], height=first_wh[1],
        blobs=blobs, ticks=ticks, palettes=None)
    return container, total_raw


def assemble_palette(defn, project_dir):
    """Palette track: one base blob + chained full palette tables."""
    base_pixels, bw, bh, base_pal = load_image_mag(defn.base)
    _final_dimension_check(defn.type, (bw, bh))

    base_blob = encode_mag(base_pixels, bw, bh, base_pal,
                           user_string=b"naiz\x1a", bpp=8)

    cur = list(base_pal)
    while len(cur) < 256:
        cur.append((0, 0, 0))
    tables = []
    for step in defn.steps:
        entries = parse_pal_file(step.resolved)
        for idx, rgb in entries.items():
            cur[idx] = rgb
        tables.append(bytes(v for rgb in cur for v in rgb))

    total_raw = bw * bh * 4 + len(tables) * 768
    container = AnimContainerDef(
        type=0 if defn.type == 'fullscreen' else 1,
        track=ANI_TRACK_PALETTE,
        width=bw, height=bh,
        blobs=[base_blob], ticks=[s.ticks for s in defn.steps],
        palettes=tables)
    return container, total_raw


def _fmt_int(n):
    return f"{n:,}"


def report(defn, container, out_path, total_raw, shared_used):
    total_ticks = sum(container.ticks)
    print(f"=== ANI 组装报告: {defn.name} ===")
    print(f"  type={defn.type} track={defn.track} project={defn.project}  "
          f"{container.width}x{container.height}  "
          f"{container.nframes} 帧  总时长 {total_ticks / 60:.3f}s")
    if container.track == ANI_TRACK_PALETTE:
        print(f"  底图  {defn.base.name}  MAG {_fmt_int(len(container.blobs[0]))} B")
        for i, step in enumerate(defn.steps, start=1):
            print(f"  帧 {i}  {step.path}  tick={step.ticks} ({step.seconds:.3f}s)"
                  f"  表 768 B")
    else:
        for i, (step, blob) in enumerate(zip(defn.steps, container.blobs), start=1):
            print(f"  帧 {i}  {step.path}  tick={step.ticks} ({step.seconds:.3f}s)"
                  f"  MAG {_fmt_int(len(blob))} B")
    data = out_path.read_bytes()
    print(f"  容器: {_fmt_int(len(data))} B"
          f"（头 28 + 偏移表 {container.nblob * 4}"
          f" + tick 表 {container.nframes * 2}"
          f" + 块 {_fmt_int(sum(len(b) for b in container.blobs))}"
          + (f" + 调色板表 {container.palsz}" if container.palettes else "")
          + "）")
    if total_raw > 0:
        print(f"  原始 RGBA 参考: {_fmt_int(total_raw)} B"
              f" → 压缩率 {len(data) / total_raw * 100:.1f}%")
    print(f"  调色板: {f'共享色板 (项目 {defn.project})' if shared_used else '动画自身色板'}")
    print(f"→ {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="动画脚本(.na) -> .ANI 容器组装工具")
    parser.add_argument("script", help="动画脚本路径 (.na)；"
                        "与剧本脚本 (.nb) 按后缀分离")
    parser.add_argument("--out", default=None,
                        help="输出 .ANI 路径（缺省 animation/output/<NAME>.ANI）")
    parser.add_argument("--project", default=None,
                        help="须与脚本 animaconf 项目名一致"
                             "（anima.sh build <项目>/<脚本> 自动传入）")
    parser.add_argument("--assets-root", default=None,
                        help="素材根目录（缺省 <repo>/assets）")
    parser.add_argument("--sync", action="store_true",
                        help="解析前先同步项目素材登记库")
    args = parser.parse_args()

    script_path = Path(args.script)
    if not script_path.is_file():
        _die(f"脚本不存在: {script_path}")

    assets_root = (Path(args.assets_root) if args.assets_root
                   else _REPO_ROOT / "assets")

    peeked = _peek_project(script_path)
    if args.sync:
        if peeked is None:
            _die("--sync 无法从脚本确定项目名"
                 "（须有 animaconf(<区域>,<轨道>,<项目名>) 头）")
        load_project(peeked, repo_root=_REPO_ROOT)
        sync_project(peeked, repo_root=_REPO_ROOT)

    # The parser touches the DB only after a valid animaconf header, so a
    # failed peek (malformed header) still exits with the precise syntax
    # error before any name lookup happens.
    if peeked is not None:
        db_root = db_dir_for(peeked, repo_root=_REPO_ROOT)
    else:
        db_root = PROJECTS_ROOT / "_" / "db"

    defn = parse_anim_script(script_path, assets_root, db_root)

    if args.project and args.project != defn.project:
        _die(f"--project {args.project} 与脚本项目名冲突: "
             f"animaconf 声明为 {defn.project}（脚本项目名固定，不可覆盖）")

    # Script-declared project wins; shared palette is derived only when that
    # project's ASSETS.DB has been built, else assemble_pixel warns and falls
    # back to per-frame own palettes.
    project_dir = None
    if (defn.project
            and (_REPO_ROOT / "projects" / defn.project / "ASSETS.DB").is_file()):
        project_dir = _REPO_ROOT / "projects" / defn.project

    if defn.track == 'palette':
        container, total_raw = assemble_palette(defn, project_dir)
    else:
        container, total_raw = assemble_pixel(defn, project_dir)

    data = build_ani(container)

    if args.out:
        out_path = Path(args.out)
    else:
        out_path = ANIM_OUTPUT_DIR / f"{script_path.stem.upper()}.ANI"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)

    shared_used = (defn.track != 'palette' and project_dir is not None)
    report(defn, container, out_path, total_raw, shared_used)


if __name__ == '__main__':
    main()
