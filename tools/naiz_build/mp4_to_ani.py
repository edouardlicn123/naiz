#!/usr/bin/env python3
"""MP4 → ANI converter — scan assets/<project>/anim/ for .mp4 files
and convert them to standalone .ANI animation containers.

Usage:
    python -m tools.naiz_build.mp4_to_ani <project>
             [--fps N] [--width W] [--height H] [--type fullscreen|cine]
             [--out DIR]

Pipeline per MP4:
    FFmpeg抽帧 (subprocess, raw RGB stdout) ->
    PIL resize + quantize (256色, FLOYDSTEINBERG) ->
    encode_mag() -> MAG blob ->
    build_ani() -> .ANI file

Output: animation/output/<8.3_UPCASE_NAME>.ANI
"""

import argparse
import subprocess
import struct
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "tools"))

from naiz_lib import PROTECTED_IDX_ALL                     # noqa: E402
from naiz_lib.mag_codec import encode_mag                   # noqa: E402
from naiz_lib.anim_container import (                       # noqa: E402
    ANI_TRACK_PIXEL,
    AnimContainerDef,
    build_ani,
)

ANIM_OUTPUT_DIR = _REPO_ROOT / "animation" / "output"

# DOS 8.3: stem up to 8 chars, uppercased
_DOS_83_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-^~$!#%&()@{}'")


def _die(msg):
    print(f"mp4_to_ani: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _check_ffmpeg():
    """Verify FFmpeg is available."""
    try:
        r = subprocess.run(["ffmpeg", "-version"],
                           capture_output=True, timeout=5)
        if r.returncode != 0:
            _die("ffmpeg 不可用（返回码非 0）\n"
                 "  请安装: sudo apt install ffmpeg")
    except FileNotFoundError:
        _die("未找到 ffmpeg\n"
             "  请安装: sudo apt install ffmpeg")
    except subprocess.TimeoutExpired:
        _die("ffmpeg -version 超时")


def _to_dos_83(stem):
    """Convert filename stem to DOS 8.3 uppercase format."""
    up = stem.upper()
    # keep only safe chars, replace others with underscore
    clean = ""
    for ch in up:
        if ch in _DOS_83_CHARS:
            clean += ch
        else:
            clean += "_"
    # collapse consecutive underscores
    while "__" in clean:
        clean = clean.replace("__", "_")
    clean = clean.strip("_")
    if not clean:
        clean = "ANI"
    return clean[:8]


def _extract_frames(mp4_path, fps, width, height):
    """Use FFmpeg to extract frames as raw RGB to stdout.

    Returns list of (pixels_bytes, w, h) tuples, one per frame.
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(mp4_path),
        "-vf", f"fps={fps},scale={width}:{height}:flags=lanczos",
        "-f", "image2pipe",
        "-pix_fmt", "rgb24",
        "-vcodec", "rawvideo",
        "-",
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=120)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", errors="replace").strip()
        _die(f"ffmpeg 失败: {mp4_path.name}\n  {err}")

    raw = r.stdout
    frame_bytes = width * height * 3
    if frame_bytes == 0:
        _die(f"帧大小为 0: {width}x{height}")
    if len(raw) % frame_bytes != 0:
        _die(f"ffmpeg 输出不是 {frame_bytes}B 的整数倍"
             f"（共 {len(raw)}B，期望每帧 {frame_bytes}B）")

    nframes = len(raw) // frame_bytes
    frames = []
    for i in range(nframes):
        chunk = raw[i * frame_bytes:(i + 1) * frame_bytes]
        frames.append((chunk, width, height))
    return frames


def _quantize_frame(rgb_bytes, width, height):
    """RGB raw bytes -> (pixels_list, palette_list).

    Uses PIL with FLOYDSTEINBERG dithering, 256 colors.
    Returns (pixels: list[int], palette: list[tuple(int,int,int)]).
    """
    from PIL import Image

    img = Image.frombytes("rgb", (width, height), rgb_bytes)
    # quantize with FLOYDSTEINBERG dithering, 256 colors
    q = img.quantize(colors=256, method=2, dither=1)  # MEDIANCUT + FLOYD
    palette_raw = q.getpalette()  # flat [r,g,b,r,g,b,...]
    palette = []
    for i in range(256):
        r = palette_raw[i * 3]
        g = palette_raw[i * 3 + 1]
        b = palette_raw[i * 3 + 2]
        palette.append((r, g, b))
    pixels = list(q.getdata())
    return pixels, palette


def convert_mp4(mp4_path, fps, width, height, ani_type, out_dir):
    """Convert a single MP4 file to .ANI. Returns output Path."""
    print(f"  转换: {mp4_path.name} ({width}x{height}, {fps}fps)")

    frames = _extract_frames(mp4_path, fps, width, height)
    if not frames:
        _die(f"未提取到帧: {mp4_path.name}")

    print(f"    抽取 {len(frames)} 帧")

    blobs = []
    ticks = []
    tick = max(1, round(60 / fps))

    for i, (rgb_bytes, fw, fh) in enumerate(frames):
        pixels, palette = _quantize_frame(rgb_bytes, fw, fh)
        blob = encode_mag(pixels, fw, fh, palette,
                          user_string=b"naiz\x1a", bpp=8,
                          protected_indices=PROTECTED_IDX_ALL)
        blobs.append(blob)
        ticks.append(tick)

        if (i + 1) % 10 == 0 or i == len(frames) - 1:
            print(f"    编码帧 {i + 1}/{len(frames)}")

    type_val = 0 if ani_type == "fullscreen" else 1
    container = AnimContainerDef(
        type=type_val,
        track=ANI_TRACK_PIXEL,
        width=width, height=height,
        blobs=blobs, ticks=ticks, palettes=None,
    )

    data = build_ani(container)

    dos_name = _to_dos_83(mp4_path.stem)
    out_path = out_dir / f"{dos_name}.ANI"
    out_path.write_bytes(data)

    total_ticks = sum(ticks)
    print(f"    {len(frames)} 帧, {total_ticks / 60:.3f}s,"
          f" {len(data):,} B → {out_path.name}")
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="MP4 → ANI 转换工具（扫描项目 anim/ 下的 .mp4 文件）")
    parser.add_argument("project",
                        help="动画项目名（扫描 assets/<project>/anim/*.mp4）")
    parser.add_argument("--fps", type=int, default=10,
                        help="采样帧率（默认 10）")
    parser.add_argument("--width", type=int, default=640,
                        help="目标宽度（默认 640）")
    parser.add_argument("--height", type=int, default=400,
                        help="目标高度（默认 400）")
    parser.add_argument("--type", choices=["fullscreen", "cine"],
                        default="fullscreen",
                        help="动画类型（默认 fullscreen）")
    parser.add_argument("--out", default=None,
                        help="输出目录（默认 animation/output/）")
    args = parser.parse_args()

    _check_ffmpeg()

    anim_dir = _REPO_ROOT / "assets" / args.project / "anim"
    if not anim_dir.is_dir():
        _die(f"素材目录不存在: {anim_dir}")

    mp4s = sorted(anim_dir.glob("*.mp4"))
    if not mp4s:
        _die(f"{anim_dir} 下无 .mp4 文件")

    out_dir = Path(args.out) if args.out else ANIM_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== MP4 → ANI: {args.project} ===")
    print(f"  目录: {anim_dir}")
    print(f"  参数: {args.width}x{args.height} {args.fps}fps {args.type}")
    print(f"  发现 {len(mp4s)} 个 MP4 文件:")
    for i, mp4 in enumerate(mp4s, 1):
        size_kb = mp4.stat().st_size / 1024
        print(f"    {i}) {mp4.name} ({size_kb:.0f} KB)")
    print()

    # Interactive selection
    raw = input("选择转换（序号逗号分隔，all=全部）: ").strip()
    if not raw:
        print("未选择，退出。")
        return

    if raw.lower() == "all":
        selected = list(range(len(mp4s)))
    else:
        selected = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                idx = int(part) - 1
            except ValueError:
                print(f"  忽略无效输入: {part}")
                continue
            if 0 <= idx < len(mp4s):
                selected.append(idx)
            else:
                print(f"  忽略越界序号: {part}")

    if not selected:
        print("无有效选择，退出。")
        return

    print(f"\n将转换 {len(selected)} 个文件:\n")
    ok = 0
    failed = 0
    for idx in selected:
        mp4 = mp4s[idx]
        try:
            convert_mp4(mp4, args.fps, args.width, args.height,
                        args.type, out_dir)
            ok += 1
        except Exception as e:
            print(f"  失败: {mp4.name} — {e}")
            failed += 1

    print(f"\n=== 汇总: {ok} 成功 / {failed} 失败 ===")
    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
