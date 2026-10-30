#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Naiz 剧本工坊 — 本地网页 IDE 服务端（仅标准库，无第三方依赖）

提供：
  - studio/static/ 静态页面服务
  - NB 剧本读写 / 校验代理
  - 构建・打包・启动测试任务队列（后台 job，轮询获取输出）
  - 模拟器串口日志、HDI 新急性状态
"""
import argparse
import io
import json
import re
import sqlite3
import struct
import subprocess
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

# ── 全局状态 ────────────────────────────────────────────────────────────────
ROOT = None            # naiz 项目根，启动时注入
SCENE_RE = re.compile(r"^[A-Za-z0-9_]{1,8}\.nb$")   # 剧本文件名 8.3 规则
GAME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")         # 项目名规则
# 项目配置文件白名单（config.toml 等 + 素材映射表）
CFG_FILES = ["config.toml", "characters.json", "expressions.json", "variables.json"]


def cfg_path(game, name):
    """配置文件名 → 实际路径；不在白名单返回 None。"""
    if name == "images.map":
        return ROOT / "assets" / game / "images.map"
    if name in CFG_FILES:
        return project_dir(game) / name
    return None
JOBS = {}              # job_id -> job dict
JOBS_LOCK = threading.Lock()
JOB_SEQ = [0]
_CMD_CACHE = []

# makegame.sh 子命令映射（studio 动作名 → 实际子命令）
ACTION_MAP = {"build": "build", "pack": "make", "launch": "test"}

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


def project_dir(game):
    return ROOT / "projects" / game


def scene_dir(game):
    return project_dir(game) / "scene"


def load_commands():
    """从 nb_validator 的 SIGNATURES 提取已知命令名（导入失败则正则兜底）。"""
    global _CMD_CACHE
    if _CMD_CACHE:
        return _CMD_CACHE
    try:
        sys.path.insert(0, str(ROOT / "tools" / "naiz_build"))
        import nb_validator  # noqa
        _CMD_CACHE = sorted(nb_validator.SIGNATURES.keys())
    except Exception:
        src_path = ROOT / "tools" / "naiz_build" / "nb_validator.py"
        try:
            src = src_path.read_text(encoding="utf-8", errors="replace")
            keys = set(re.findall(r"^\s*'([a-z_]+)'\s*:\s*\(", src, re.M))
            _CMD_CACHE = sorted(keys)
        except Exception:
            _CMD_CACHE = []
    return _CMD_CACHE


def load_assets(game):
    """读 ASSETS.DB，按 kind 分组返回补全用的 key 列表。"""
    buckets = {"img": [], "bgm": [], "snd": [], "vc": []}
    db = project_dir(game) / "ASSETS.DB"
    if not db.exists():
        return buckets
    kind_map = {
        "IMG": "img", "SPR": "img", "CG": "img", "THUMB": "img", "ANI": "img",
        "BGM": "bgm", "SND": "snd", "SE": "snd", "VC": "vc", "VOICE": "vc",
    }
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            if not tables:
                return buckets
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({tables[0]})")]
            name_col = "name" if "name" in cols else ("filename" if "filename" in cols else None)
            kind_col = "kind" if "kind" in cols else ("type" if "type" in cols else None)
            if not name_col:
                return buckets
            sel = f'SELECT {name_col}{", " + kind_col if kind_col else ""} FROM {tables[0]}'
            for row in con.execute(sel):
                name, kind = row[0], (row[1] if kind_col else "")
                key = kind_map.get(str(kind).upper(), "img")
                if name and name not in buckets[key]:
                    buckets[key].append(str(name))
        finally:
            con.close()
    except Exception:
        pass
    for k in buckets:
        buckets[k].sort()
    return buckets


def load_json_list(game, fname, *keys):
    """从项目 json 里抽取名字列表（兼容多种字段名）。"""
    path = project_dir(game) / fname
    out = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    if isinstance(data, dict):
        for k in keys:
            v = data.get(k)
            if isinstance(v, dict):
                out.extend(str(x) for x in v.keys())
            elif isinstance(v, list):
                for it in v:
                    out.append(str(it.get("name") or it.get("id") or it) if isinstance(it, dict) else str(it))
    elif isinstance(data, list):
        for it in data:
            out.append(str(it.get("name") or it.get("id") or it) if isinstance(it, dict) else str(it))
    return sorted(set(out))


def load_meta(game):
    return {
        "commands": load_commands(),
        "chars": load_json_list(game, "characters.json", "characters", "chars"),
        "expressions": load_json_list(game, "expressions.json", "expressions", "faces"),
        "variables": load_json_list(game, "variables.json", "variables", "flags"),
        "assets": load_assets(game),
    }


# ── 后台任务（构建/打包/启动测试）─────────────────────────────────────────
def start_job(action, game):
    """启动后台 job；同项目同动作已在跑则返回 None（409）。"""
    with JOBS_LOCK:
        for j in JOBS.values():
            if j["kind"] == action and j["game"] == game and j["status"] == "running":
                return None
        JOB_SEQ[0] += 1
        jid = "j%d" % JOB_SEQ[0]
        sub = ACTION_MAP[action]
        args = ["bash", "makegame.sh", sub, game]
        if action == "launch":
            args.append("--serial")
        job = {"id": jid, "kind": action, "game": game, "status": "running",
               "code": None, "lines": [], "t0": time.time(), "t1": None}
        JOBS[jid] = job

    def run():
        try:
            p = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True,
                                 errors="replace", bufsize=1)
            for line in p.stdout:
                job["lines"].append(line.rstrip("\n"))
                if len(job["lines"]) > 1000:
                    del job["lines"][: len(job["lines"]) - 1000]
            job["code"] = p.wait()
            job["status"] = "done" if job["code"] == 0 else "failed"
        except Exception as e:  # noqa
            job["lines"].append("[studio] 任务异常: %s" % e)
            job["status"] = "failed"
        job["t1"] = time.time()

    threading.Thread(target=run, daemon=True).start()
    return job


# ── 素材与音频 ─────────────────────────────────────────────────────────────
# 86 板 PCM 采样率码表（与 tools/naiz_audio/wav_convert.py 一致）
_PCM_RATES = (44100.0, 33075.0, 22050.0, 16537.5, 11025.0, 8268.75, 5501.25, 4134.375)
_MAG_PNG_CACHE = {}    # (game, name, mtime) -> png bytes


def list_assets(game):
    """列出项目素材：图片（含 MAG 映射）与音频文件。"""
    base = ROOT / "assets" / game
    imgs = []
    mag_map = {}
    mp = base / "images.map"
    if mp.is_file():
        for line in mp.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                mag_map[parts[0]] = parts[1]
    png_root = base / "png"
    if png_root.is_dir():
        for p in sorted(png_root.rglob("*.png")):
            rel = p.relative_to(base).as_posix()
            imgs.append({"rel": rel, "name": p.name, "mag": mag_map.get(rel, "")})
    def _names(sub, ext):
        d = base / sub
        return sorted(p.name for p in d.glob(ext)) if d.is_dir() else []
    return {
        "imgs": imgs,
        "bgm": _names("bgm", "*.mid"),
        "se": _names("se", "*.pcm"),
        "voice": _names("voice", "*.pcm"),
    }


def mag_to_png_bytes(game, name):
    """MAG → PNG bytes（内存缓存，按 mtime 失效）。依赖 venv 里的 PIL。"""
    fp = project_dir(game) / "images" / name
    if not fp.is_file():
        return None
    mt = int(fp.stat().st_mtime)
    hit = _MAG_PNG_CACHE.get((game, name))
    if hit and hit[0] == mt:
        return hit[1]
    try:
        sys.path.insert(0, str(ROOT / "tools"))  # naiz_lib 包位于 tools/ 下
        from naiz_lib import mag_codec
        from PIL import Image
        decoded = mag_codec.decode_mag_full(fp.read_bytes())
        if not decoded:
            return None
        px, w, h, pal = decoded[0], decoded[1], decoded[2], decoded[3]
        img = Image.frombytes("P", (w, h), bytes(px))
        flat = []
        for rgb in pal:
            flat.extend(int(c) for c in rgb)
        while len(flat) < 768:
            flat.extend((0, 0, 0))
        img.putpalette(flat[:768])
        buf = io.BytesIO()
        img.save(buf, "PNG")
        body = buf.getvalue()
        _MAG_PNG_CACHE[(game, name)] = (mt, body)
        return body
    except Exception:
        return None


def pcm_to_wav_bytes(fp):
    """NAIZPCM(.pcm) → WAV bytes，按头部采样率码还原。"""
    data = fp.read_bytes()
    if data[:8] == b"NAIZPCM\x00":
        code = data[8]
        rate = int(_PCM_RATES[code]) if code < len(_PCM_RATES) else 22050
        pcm = data[16:]
    else:
        rate = 22050            # 裸 PCM 兜底
        pcm = data
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def midi_to_wav_bytes(game, name):
    """MIDI → WAV（缓存到 studio/audio_cache，源文件更新后重渲）。"""
    src = ROOT / "assets" / game / "bgm" / name
    if not src.is_file():
        return None
    cache_dir = ROOT / "studio" / "audio_cache" / game
    cache_dir.mkdir(parents=True, exist_ok=True)
    dst = cache_dir / (name + ".wav")
    if not dst.is_file() or dst.stat().st_mtime < src.stat().st_mtime:
        sys.path.insert(0, str(ROOT / "studio"))
        import midi_render
        dst.write_bytes(midi_render.render_midi_file(src))
    return dst.read_bytes()


_ANIM_PNG_CACHE = {}


def find_ani(game, name):
    """在 projects/<game>/ani 与 animation/output 中定位 .ANI。"""
    for d in (ROOT / "projects" / game / "ani", ROOT / "animation" / "output"):
        fp = d / name
        if fp.is_file():
            return fp
    return None


def _load_ani(game, name):
    fp = find_ani(game, name)
    if fp is None:
        return None
    sys.path.insert(0, str(ROOT / "tools"))
    from naiz_lib.anim_container import parse_ani
    try:
        return parse_ani(fp.read_bytes())
    except ValueError:
        return None


def anim_meta(game, name):
    ani = _load_ani(game, name)
    if ani is None:
        return None
    return {"type": ani.type, "track": ani.track,
            "w": ani.width, "h": ani.height,
            "nframes": ani.nframes, "ticks": ani.ticks}


def anim_frame_png(game, name, n):
    """第 n 帧 → PNG（pixel 轨逐帧 MAG；palette 轨基底图+逐帧调色板）。"""
    fp = find_ani(game, name)
    if fp is None:
        return None
    key = (str(fp), n, int(fp.stat().st_mtime))
    hit = _ANIM_PNG_CACHE.get(key)
    if hit:
        return hit
    sys.path.insert(0, str(ROOT / "tools"))
    from naiz_lib import mag_codec
    from PIL import Image
    ani = _load_ani(game, name)
    if ani is None or n >= ani.nframes:
        return None
    if ani.track == 0:  # pixel
        dec = mag_codec.decode_mag_full(ani.blobs[n])
        if not dec:
            return None
        img = Image.frombytes("P", (dec[1], dec[2]), bytes(dec[0]))
        flat = [int(c) for rgb in dec[3] for c in rgb]
    else:               # palette：基底图 indices + 第 n 帧调色板
        dec = mag_codec.decode_mag_full(ani.blobs[0])
        if not dec:
            return None
        img = Image.frombytes("P", (dec[1], dec[2]), bytes(dec[0]))
        flat = list(ani.palettes[n])
    while len(flat) < 768:
        flat.extend((0, 0, 0))
    img.putpalette(flat[:768])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    body = buf.getvalue()
    _ANIM_PNG_CACHE[key] = body
    return body


def hdi_status(game):
    """镜像/引擎存在性与新急性（对齐 makegame.sh 的守卫逻辑）。"""
    hdi = ROOT / "disks" / ("%s.hdi" % game)
    engine = ROOT / "games" / game / "engine.exe"
    hdi_exists, engine_exists = hdi.exists(), engine.exists()
    stale = hdi_exists and engine_exists and hdi.stat().st_mtime < engine.stat().st_mtime
    serial = ROOT / "logs" / ("serial_%s.log" % game)
    return {
        "hdi_exists": hdi_exists,
        "engine_exists": engine_exists,
        "hdi_stale": stale,
        "serial_size": serial.stat().st_size if serial.exists() else 0,
    }


# ── HTTP 服务 ───────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = "NaizStudio/0.1"

    def log_message(self, fmt, *args):  # 安静模式，避免刷屏
        pass

    # -- 基础工具 --
    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def send_static(self, rel):
        base = ROOT / "studio" / "static"
        target = (base / rel).resolve()
        if not str(target).startswith(str(base.resolve())) or not target.is_file():
            self.send_json({"error": "not found"}, 404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- 路由 --
    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)

        if path == "/" or path == "/index.html":
            return self.send_static("index.html")
        if path.startswith("/static/"):
            return self.send_static(path[len("/static/"):])

        m = re.match(r"^/api/projects$", path)
        if m:
            games = sorted(p.name for p in (ROOT / "projects").iterdir() if p.is_dir())
            return self.send_json({"projects": games})

        m = re.match(r"^/api/scenes/([a-z0-9_-]+)$", path)
        if m:
            g = m.group(1)
            d = scene_dir(g)
            if not d.is_dir():
                return self.send_json({"error": "scene 目录不存在"}, 404)
            files = sorted(d.glob("*.nb"))
            cfgs = []
            for n in CFG_FILES + ["images.map"]:
                p = cfg_path(g, n)
                cfgs.append({"name": n, "exists": bool(p and p.is_file()),
                             "size": p.stat().st_size if (p and p.is_file()) else 0})
            return self.send_json({"scenes": [
                {"name": f.name, "size": f.stat().st_size,
                 "mtime": int(f.stat().st_mtime)} for f in files],
                "configs": cfgs})

        m = re.match(r"^/api/scene/([a-z0-9_-]+)/([A-Za-z0-9_]{1,8}\.nb)$", path)
        if m:
            g, f = m.group(1), m.group(2)
            fp = scene_dir(g) / f
            if not fp.is_file():
                return self.send_json({"error": "文件不存在"}, 404)
            return self.send_json({"content": fp.read_text(encoding="utf-8", errors="replace")})

        # 项目配置文件读取（白名单）
        m = re.match(r"^/api/cfg/([a-z0-9_-]+)/([A-Za-z0-9_.]{1,32})$", path)
        if m:
            fp = cfg_path(m.group(1), m.group(2))
            if fp is None:
                return self.send_json({"error": "forbidden"}, 403)
            if not fp.is_file():
                return self.send_json({"error": "文件不存在"}, 404)
            return self.send_json({"content": fp.read_text(encoding="utf-8", errors="replace")})

        m = re.match(r"^/api/meta/([a-z0-9_-]+)$", path)
        if m:
            return self.send_json(load_meta(m.group(1)))

        m = re.match(r"^/api/status/([a-z0-9_-]+)$", path)
        if m:
            return self.send_json(hdi_status(m.group(1)))

        m = re.match(r"^/api/serial/([a-z0-9_-]+)$", path)
        if m:
            log = ROOT / "logs" / ("serial_%s.log" % m.group(1))
            offset = int(q.get("from", ["0"])[0])
            if not log.exists():
                return self.send_json({"size": 0, "chunk": ""})
            size = log.stat().st_size
            offset = max(0, min(offset, size))
            with log.open("rb") as fh:
                fh.seek(offset)
                chunk = fh.read(65536).decode("utf-8", "replace")
            return self.send_json({"size": size, "chunk": chunk})

        m = re.match(r"^/api/jobs/([a-z0-9]+)$", path)
        if m:
            job = JOBS.get(m.group(1))
            if not job:
                return self.send_json({"error": "任务不存在"}, 404)
            return self.send_json({k: job[k] for k in
                                   ("id", "kind", "game", "status", "code", "lines")})

        m = re.match(r"^/api/jobs$", path)
        if m:
            with JOBS_LOCK:
                active = [{"id": j["id"], "kind": j["kind"], "game": j["game"],
                           "status": j["status"]} for j in JOBS.values()
                          if j["status"] == "running"]
            return self.send_json({"jobs": active})

        # ── 素材预览 ──
        m = re.match(r"^/api/assets/([a-z0-9_-]+)$", path)
        if m:
            return self.send_json(list_assets(m.group(1)))

        m = re.match(r"^/api/asset/img/([a-z0-9_-]+)/(.+)$", path)
        if m:
            rel = unquote(m.group(2))
            if ".." in rel or not re.match(r"^png/[A-Za-z0-9_/.-]+\.png$", rel):
                return self.send_json({"error": "forbidden"}, 403)
            fp = ROOT / "assets" / m.group(1) / rel
            if not fp.is_file():
                return self.send_json({"error": "文件不存在"}, 404)
            return self.send_bytes(fp.read_bytes(), "image/png")

        m = re.match(r"^/api/asset/mag/([a-z0-9_-]+)/([A-Za-z0-9_]{1,8}\.MAG)$", path)
        if m:
            body = mag_to_png_bytes(m.group(1), m.group(2))
            if body is None:
                return self.send_json({"error": "MAG 解码失败或不存在"}, 404)
            return self.send_bytes(body, "image/png")

        m = re.match(r"^/api/asset/audio/([a-z0-9_-]+)/(bgm|se|voice)/(.+)$", path)
        if m:
            g, kind, name = m.group(1), m.group(2), unquote(m.group(3))
            if "/" in name or ".." in name:
                return self.send_json({"error": "forbidden"}, 403)
            try:
                if kind == "bgm":
                    if not name.lower().endswith(".mid"):
                        return self.send_json({"error": "forbidden"}, 403)
                    body = midi_to_wav_bytes(g, name)
                else:
                    if not name.lower().endswith(".pcm"):
                        return self.send_json({"error": "forbidden"}, 403)
                    fp = ROOT / "assets" / g / ("bgm" if kind == "bgm" else
                                                ("se" if kind == "se" else "voice")) / name
                    body = pcm_to_wav_bytes(fp) if fp.is_file() else None
            except Exception as e:  # noqa
                return self.send_json({"error": "音频处理失败: %s" % e}, 500)
            if body is None:
                return self.send_json({"error": "文件不存在"}, 404)
            return self.send_bytes(body, "audio/wav")

        # ── 动画预览 ──
        m = re.match(r"^/api/anims/([a-z0-9_-]+)$", path)
        if m:
            d = ROOT / "projects" / m.group(1) / "ani"
            anims = []
            if d.is_dir():
                for f in sorted(d.glob("*.ANI")):
                    anims.append({"name": f.name, "size": f.stat().st_size})
            return self.send_json({"anims": anims})

        m = re.match(r"^/api/anim/meta/([a-z0-9_-]+)/([A-Za-z0-9_]{1,8}\.ANI)$", path)
        if m:
            info = anim_meta(m.group(1), m.group(2))
            if info is None:
                return self.send_json({"error": "文件不存在或容器损坏"}, 404)
            return self.send_json(info)

        m = re.match(r"^/api/anim/frame/([a-z0-9_-]+)/([A-Za-z0-9_]{1,8}\.ANI)/([0-9]{1,4})$", path)
        if m:
            try:
                body = anim_frame_png(m.group(1), m.group(2), int(m.group(3)))
            except Exception:  # noqa
                body = None
            if body is None:
                return self.send_json({"error": "帧解码失败或不存在"}, 404)
            return self.send_bytes(body, "image/png")

        # ── guildbook 手册站点（只读静态映射；cn=中文 / en=英文）──
        m = re.match(r"^/guidebook(?:/(.*))?$", path)
        if m:
            rest = m.group(1) or ""
            if rest.startswith("en/"):
                base, rel = "guildbook_en", rest[3:]
            elif rest.startswith("cn/"):
                base, rel = "guildbook_cn", rest[3:]
            else:
                base, rel = "guildbook_cn", rest      # 默认中文
            rel = rel.lstrip("/") or "index.html"
            if ".." in rel:
                return self.send_json({"error": "禁止访问"}, 403)
            fp = ROOT / base / rel
            if not fp.is_file():
                return self.send_json({"error": "文件不存在"}, 404)
            ct = {"html": "text/html", "css": "text/css", "js": "text/javascript",
                  "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                  "svg": "image/svg+xml", "gif": "image/gif"
                  }.get(fp.suffix[1:], "application/octet-stream")
            return self.send_bytes(fp.read_bytes(), ct)

        return self.send_json({"error": "unknown api"}, 404)

    def do_PUT(self):
        u = urlparse(self.path)
        m = re.match(r"^/api/scene/([a-z0-9_-]+)/([A-Za-z0-9_]{1,8}\.nb)$", u.path)
        if m:
            fp = scene_dir(m.group(1)) / m.group(2)
        else:
            m = re.match(r"^/api/cfg/([a-z0-9_-]+)/([A-Za-z0-9_.]{1,32})$", u.path)
            if not m:
                return self.send_json({"error": "forbidden"}, 403)
            fp = cfg_path(m.group(1), m.group(2))
            if fp is None:
                return self.send_json({"error": "forbidden"}, 403)
        if not fp.parent.is_dir():
            return self.send_json({"error": "目标目录不存在"}, 404)
        try:
            raw = self.read_body().decode("utf-8")
            try:
                payload = json.loads(raw)
                text = payload.get("content", "") if isinstance(payload, dict) else raw
            except ValueError:
                text = raw  # 兼容纯文本提交
            # 二进制兜底校验：拒绝 NUL 字节
            if "\x00" in text:
                return self.send_json({"error": "非法内容"}, 400)
            (fp).write_text(text, encoding="utf-8")
        except Exception as e:  # noqa
            return self.send_json({"error": str(e)}, 500)
        return self.send_json({"ok": True})

    def do_POST(self):
        u = urlparse(self.path)
        m = re.match(r"^/api/lint/([a-z0-9_-]+)$", u.path)
        if m:
            g = m.group(1)
            if not scene_dir(g).is_dir():
                return self.send_json({"error": "scene 目录不存在"}, 404)
            try:
                p = subprocess.run(
                    [sys.executable, "tools/naiz_build/nb_validator.py", "projects/%s" % g],
                    cwd=str(ROOT), capture_output=True, text=True,
                    errors="replace", timeout=15)
                out = (p.stdout or "") + (p.stderr or "")
                return self.send_json({"code": p.returncode, "output": out.strip()})
            except subprocess.TimeoutExpired:
                return self.send_json({"error": "校验超时"}, 500)

        m = re.match(r"^/api/(build|pack|launch)/([a-z0-9_-]+)$", u.path)
        if m:
            action, g = m.group(1), m.group(2)
            if not (ROOT / "games").exists() and action != "build":
                pass  # make/test 由 makegame.sh 自行报错
            job = start_job(action, g)
            if job is None:
                return self.send_json({"error": "该任务已在运行"}, 409)
            return self.send_json({"job_id": job["id"], "kind": job["kind"]})

        return self.send_json({"error": "unknown api"}, 404)


def main():
    global ROOT
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="Naiz 剧本工坊服务端")
    ap.add_argument("--port", type=int, default=7130)
    ap.add_argument("--root", default=str(here.parent))
    args = ap.parse_args()
    ROOT = Path(args.root).resolve()
    if not (ROOT / "makegame.sh").is_file():
        print("[studio] 错误: 未在 %s 找到 makegame.sh，请用 --root 指定 naiz 根目录" % ROOT)
        sys.exit(1)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("[studio] Naiz 剧本工坊已启动: http://127.0.0.1:%d/  (项目根: %s)" % (args.port, ROOT))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[studio] 已停止")


if __name__ == "__main__":
    main()
