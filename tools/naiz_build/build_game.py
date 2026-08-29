#!/usr/bin/env python3
"""
游戏数据编译：PNG→MAG, 引擎部署, IMAGE.DAT, 运行时部署

Usage:
    python -m tools.naiz_build.build_game <game_name>

    流程:
        1. 解析 assets/<game>/images.map, 增量转换 PNG→MAG
        2. 编译引擎 (调用 core/build.sh)
        3. 部署 engine.exe
        4. 导出 C 头（ASSETS.DB / variables.json / config.toml → nb_*.h）
        5. IMAGE.DAT 打包 (ASSETS.DB → IMAGE.DAT)
        6. 部署字库/设置/剧本/DOS extender
"""
import json
import os
import sys
import shutil
import subprocess
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
VENV_PYTHON = ROOT / "tools" / "env_setup" / "venv" / "bin" / "python3"
if not VENV_PYTHON.exists():
    print("WARN: venv not found at", VENV_PYTHON, "falling back to sys.executable")
    VENV_PYTHON = Path(sys.executable)

sys.path.insert(0, str(ROOT / "tools"))

from naiz_lib import PROTECTED_IDX_ALL, COMMERCIAL_DOS_DIR
from naiz_lib.palette_utils import validate_skin_palette, VALIDATE_DE_MAX
from naiz_lib.mag_codec import decode_mag_palette
from naiz_build.project_config import ProjectConfig
from naiz_conv.i18n_gen import generate as i18n_gen

PROTECTED_IDX_NO15 = PROTECTED_IDX_ALL - {15}


def safe_copy2(src, dst, desc=""):
    try:
        shutil.copy2(src, dst)
    except FileNotFoundError:
        print(f"ERROR: source file disappeared before copy: {src} ({desc})")
        sys.exit(1)
    except PermissionError:
        print(f"ERROR: permission denied copying {src} -> {dst} ({desc})")
        sys.exit(1)


def load_asset_db(proj_dir):
    """Read ASSETS.DB img_map + expressions.json, return {filename: type} dict."""
    db_path = os.path.join(proj_dir, 'ASSETS.DB')
    if not os.path.isfile(db_path):
        return {}

    expr_path = os.path.join(proj_dir, 'expressions.json')

    try:
        db = sqlite3.connect(db_path)
        try:
            rows = db.execute('SELECT filename, type FROM img_map').fetchall()
            result = {row[0]: row[1] for row in rows}

            # Check dangling expression asset references
            if os.path.isfile(expr_path):
                with open(expr_path, 'r', encoding='utf-8') as f:
                    edata = json.load(f)
                img_ids = {r[0] for r in db.execute('SELECT id FROM img_map')}
                for expr in edata.get('expressions', []):
                    aid = expr.get('asset_id')
                    if aid is not None and aid not in img_ids:
                        print(f"WARN: expression references non-existent asset_id={aid}")
        finally:
            db.close()
        return result
    except sqlite3.Error as e:
        print(f"ERROR: cannot open ASSETS.DB: {e}")
        sys.exit(1)


def convert_png_to_mag(assets_dir: Path, proj_dir: Path):
    """Parse images.map, incrementally convert PNG→MAG"""
    map_file = assets_dir / "images.map"
    if not map_file.exists():
        print("WARN: images.map not found, skipping PNG conversion")
        return

    # Load ASSETS.DB to auto-detect sprite vs background
    asset_types = load_asset_db(proj_dir)

    # Direct API import (no subprocess)
    from naiz_conv.mag_convert import convert_file

    converted = 0
    skipped = 0

    # Persist conversion signatures so a change in inline options
    # (e.g. --filter-white) forces a rebuild even when PNG mtime is older.
    state_path = proj_dir / ".mag_conv_state.json"
    try:
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
    except (OSError, ValueError):
        state = {}

    for line in map_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        if len(parts) < 2:
            print(f"WARN: malformed line in images.map: {line!r}")
            continue
        png_rel, mag_rel = parts[0], parts[1]
        opts = parts[2:] if len(parts) > 2 else []

        png_src = assets_dir / png_rel
        mag_dst = proj_dir / mag_rel

        if not png_src.exists():
            print(f"  ERROR: PNG not found: {png_rel}")
            sys.exit(1)

        # Determine type from ASSETS.DB
        mag_filename = Path(mag_rel).name
        atype = asset_types.get(mag_filename)
        if atype is not None and atype not in ('IMG', 'SPR'):
            print(f"ERROR: unknown asset type {atype!r} for {mag_filename}")
            sys.exit(1)

        # Conversion options affect the output; record a signature so a
        # changed option to a stale-but-present .mag forces re-conversion.
        sig = json.dumps({"opts": sorted(opts), "atype": atype, "png_mtime": png_src.stat().st_mtime},
                         sort_keys=True)
        prev = state.get(mag_rel)

        if mag_dst.exists() and png_src.stat().st_mtime < mag_dst.stat().st_mtime \
                and prev == sig:
            print(f"  [PNG→MAG] 已是最新: {mag_rel}")
            skipped += 1
            continue

        mag_dst.parent.mkdir(parents=True, exist_ok=True)
        print(f"  [PNG→MAG] {png_rel} → {mag_rel}")

        kwargs = {}
        if atype == 'SPR':
            kwargs['sprite'] = True
            kwargs['reserved'] = PROTECTED_IDX_NO15
        else:
            kwargs['reserved'] = PROTECTED_IDX_ALL

        # Parse inline options from images.map
        for o in opts:
            if o == '--256color':
                pass
            elif o == '--filter-white':
                kwargs['filter_white'] = True
            elif o == '--sprite':
                kwargs['sprite'] = True
                kwargs['reserved'] = PROTECTED_IDX_NO15
            elif o == '--dither':
                kwargs['dither'] = True
            elif o == '--no-resize':
                kwargs['no_resize'] = True

        convert_file(str(png_src), str(mag_dst), **kwargs)
        converted += 1
        state[mag_rel] = sig

    try:
        state_path.write_text(json.dumps(state, indent=1))
    except OSError as e:
        print(f"  WARN: could not write conversion state {state_path}: {e}")

    print(f"  PNG→MAG 完成: {converted} 转换, {skipped} 跳过")


def compile_engine():
    """Compile the engine (calls make -C core)"""
    print("=== 编译引擎 ===")
    subprocess.run([str(ROOT / "core" / "build.sh")], check=True)


def deploy_engine(game_dir: Path):
    """Deploy engine.exe and engine_a.exe"""
    engine_src = ROOT / "core" / "engine.exe"
    if engine_src.exists():
        safe_copy2(engine_src, game_dir / "engine.exe")
        print("  部署 engine.exe → games/{}/".format(game_dir.name))
    engine_a_src = ROOT / "core" / "engine_a.exe"
    if engine_a_src.exists():
        safe_copy2(engine_a_src, game_dir / "engine_a.exe")
        print("  部署 engine_a.exe → games/{}/".format(game_dir.name))
    else:
        print("WARN: engine_a.exe not found, skip deploy")


def pack_images(proj_dir: Path, game_dir: Path):
    """Pack IMAGE.DAT (ASSETS.DB → IMAGE.DAT)"""
    if not (proj_dir / "ASSETS.DB").exists():
        return

    pack_images_py = ROOT / "tools" / "naiz_build" / "pack_images.py"
    subprocess.run(
        [str(VENV_PYTHON), str(pack_images_py), str(proj_dir)],
        check=True,
    )
    image_src = proj_dir / "IMAGE.DAT"
    if image_src.exists():
        safe_copy2(image_src, game_dir / "IMAGE.DAT")
        print("  IMAGE.DAT → games/{}/".format(game_dir.name))


def deploy_runtime(proj_dir: Path, game_dir: Path):
    """Deploy fonts, settings, scripts, and DOS extender"""
    # 字库: base + per-language CJK files
    font_dir = ROOT / "tools" / "naiz_font"
    for font_name in ("FONT.DAT", "CJK.DAT", "BLACK.DAT"):
        src = font_dir / font_name
        dst = game_dir / font_name
        if src.exists():
            if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                safe_copy2(src, dst)
                print(f"  {font_name} 已部署")

    # Deploy per-language CJK files (CJK_EN.DAT, CJK_JP.DAT, etc.)
    lang_codes = ("EN", "FR", "DE", "IT", "ES", "PT", "JP", "CN", "CT", "KR")
    for lang in lang_codes:
        cjk_name = f"CJK_{lang}.DAT"
        src = font_dir / cjk_name
        dst = game_dir / cjk_name
        if src.exists():
            if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                safe_copy2(src, dst)
                print(f"  {cjk_name} 已部署")

    # settings.txt
    settings_src = proj_dir / "scene" / "settings.txt"
    if settings_src.exists():
        safe_copy2(settings_src, game_dir / "settings.txt")
        print("  settings.txt 已部署")

    # inject version + blackletter flags from config.toml into deployed settings.txt
    if (proj_dir / "config.toml").exists():
        try:
            cfg = ProjectConfig(proj_dir)
            inject = {
                "version": cfg.version(),
                "blacktitle": "1" if cfg.get_bool("blackletter", "title", False) else "0",
                "blackdialog": "1" if cfg.get_bool("blackletter", "dialog", False) else "0",
            }
            settings_dst = game_dir / "settings.txt"
            for key, val in inject.items():
                if not val and key == "version":
                    continue
                if settings_dst.exists():
                    content = settings_dst.read_text().splitlines()
                    content = [l for l in content if not l.startswith(f"{key}=")]
                    content.append(f"{key}={val}")
                    settings_dst.write_text("\n".join(content) + "\n")
                else:
                    with open(settings_dst, "a") as f:
                        f.write(f"{key}={val}\n")
            ver = cfg.version()
            if ver:
                print(f"  版本 {ver} 已注入 settings.txt")
            print(f"  blacktitle={inject['blacktitle']} blackdialog={inject['blackdialog']} 已注入 settings.txt")
        except (ValueError, IOError) as e:
            print(f"  WARN: config.toml 读取失败: {e}")

    # .nb 剧本文件
    scene_dir = proj_dir / "scene"
    if scene_dir.is_dir():
        for nb in sorted(scene_dir.glob("*.nb")):
            safe_copy2(nb, game_dir / nb.name)
            print(f"  {nb.name} 已部署")

    # DOS extender + memory manager
    dos_dir = Path(COMMERCIAL_DOS_DIR)
    required_runtime = []
    for name in ("DOS4GW.EXE", "VEM486.EXE", "QMOUSE.COM"):
        src = dos_dir / name
        dst = game_dir / name
        if src.exists():
            if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                safe_copy2(src, dst)
                print(f"  {name} 已部署")
            required_runtime.append(dst)
        else:
            print(f"  WARNING: {name} not found in tools_commercial/dos_system/")
    for name in ("FONT.DAT", "CJK.DAT"):
        if not (game_dir / name).exists():
            print(f"  WARNING: {name} not deployed to game directory")
    # Warn if no per-language CJK files (engine will fallback to CJK.DAT)
    has_lang_cjk = any((game_dir / f"CJK_{lang}.DAT").exists() for lang in lang_codes)
    if not has_lang_cjk:
        print("  INFO: no per-language CJK files; engine will use CJK.DAT fallback")

    # Verify critical runtime files
    for f in required_runtime:
        if not f.exists():
            print(f"  ERROR: {f.name} missing after deployment")
            sys.exit(1)


def deploy_i18n(proj_dir: Path, game_dir: Path):
    """Deploy translation files i18n/*.txt"""
    i18n_src = proj_dir / "i18n"
    if not i18n_src.is_dir():
        return

    i18n_dst = game_dir / "i18n"
    i18n_dst.mkdir(exist_ok=True)

    for txt in sorted(i18n_src.glob("*.txt")):
        safe_copy2(txt, i18n_dst / txt.name)
        print(f"  i18n/{txt.name} 已部署")


def build_game(game_name: str):
    """Execute the full build pipeline"""
    proj_dir = ROOT / "projects" / game_name
    assets_dir = ROOT / "assets" / game_name
    game_dir = ROOT / "games" / game_name
    game_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== 编译游戏数据: {game_name} ===")

    common_dir = ROOT / "assets" / "common"
    if (common_dir / "images.map").exists():
        print("  [common] 处理通用素材...")
        convert_png_to_mag(common_dir, proj_dir)

    convert_png_to_mag(assets_dir, proj_dir)

    # 2a. Export ASSETS.DB → C header for engine compilation
    export_py = ROOT / "tools" / "naiz_build" / "export_asset_table.py"
    header_dst = ROOT / "core" / "engine" / "nb_asset_table.h"
    subprocess.run(
        [str(VENV_PYTHON), str(export_py), str(proj_dir), str(header_dst)],
        check=True,
    )

    # 2b. Export variables.json → C header for engine compilation
    export_vars_py = ROOT / "tools" / "naiz_build" / "export_vars.py"
    var_header_dst = ROOT / "core" / "engine" / "nb_var_table.h"
    subprocess.run(
        [str(VENV_PYTHON), str(export_vars_py), str(proj_dir), str(var_header_dst)],
        check=True,
    )

    # 2c. Export config.toml → C header
    export_config_py = ROOT / "tools" / "naiz_build" / "export_config.py"
    config_header_dst = ROOT / "core" / "engine" / "nb_config.h"
    subprocess.run(
        [str(VENV_PYTHON), str(export_config_py), str(proj_dir), str(config_header_dst)],
        check=True,
    )

    compile_engine()
    deploy_engine(game_dir)

    # Validate .nb scripts (warn only, don't block build)
    validator_py = ROOT / "tools" / "naiz_build" / "nb_validator.py"
    result = subprocess.run(
        [str(VENV_PYTHON), str(validator_py), str(proj_dir)],
        capture_output=True, text=True,
    )
    for line in result.stdout.splitlines():
        print(f"  {line}")
    for line in result.stderr.splitlines():
        print(f"  [stderr] {line}")
    if result.returncode != 0:
        n_err = max(result.returncode, 1)
        print(f"  ERROR: NB 脚本有 {n_err} 个错误，build 终止")
        print(f"  提示: 运行 '{VENV_PYTHON} {validator_py} {proj_dir}' 查看更多详情")
        sys.exit(1)

    pack_images(proj_dir, game_dir)

    # ---- Palette validation: compare shared palette against source MAGs ----
    image_dat = proj_dir / "IMAGE.DAT"
    src_mags = sorted(proj_dir.glob("**/*.MAG"))
    if image_dat.exists() and src_mags:
        from naiz_lib.image_dat import first_mag_palette
        iddata = image_dat.read_bytes()
        # Baseline = first decodable MAG entry; non-MAG entries (.ANI) are
        # skipped inside the helper so an ANI at id=0 cannot disable compare.
        shared_pal = first_mag_palette(iddata)
        if shared_pal is not None and len(shared_pal) == 256:
            source_pals = []
            for mp in src_mags:
                try:
                    pal = decode_mag_palette(mp.read_bytes())
                    if pal is not None and len(pal) >= 16:
                        source_pals.append(pal)
                except Exception:
                    pass
            if source_pals:
                warns = validate_skin_palette(shared_pal, source_pals)
                gr_warns = [w for w in warns if "G/R" in w]
                de_warns = [w for w in warns if "ΔE" in w]
                if gr_warns:
                    print("  Palette WARNING (skin tone G/R increase):")
                    for w in gr_warns:
                        print(f"    {w}")
                if de_warns:
                    print(f"  Palette info: {len(de_warns)} skin entries "
                          f"with ΔE>{VALIDATE_DE_MAX} (expected from median-cut quantization)")
                if not gr_warns and not de_warns:
                    print("  Palette validation OK (skin tones unchanged)")

    deploy_runtime(proj_dir, game_dir)
    if (proj_dir / "i18n").is_dir():
        print("  [i18n] 刷新翻译模板...")
        i18n_gen(proj_dir, force=False)
    deploy_i18n(proj_dir, game_dir)

    print(f"完成: {game_name}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    game_name = sys.argv[1]
    if not (ROOT / "projects" / game_name).is_dir():
        print(f"错误: 找不到项目目录 projects/{game_name}", file=sys.stderr)
        sys.exit(1)

    build_game(game_name)


if __name__ == "__main__":
    main()
