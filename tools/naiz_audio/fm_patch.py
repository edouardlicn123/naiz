#!/usr/bin/env python3
"""Compile text YM2608 FM patches to the 32-byte binary layout and register
them in ASSETS.DB (devdocs/123 S3; label semantics fixed in devdocs/136 P1).

The .fmp authoring format reads like a register listing.  Each file is ONE
patch:

    alg=4 fb=5 pan=0xc0
    op=1 dt=2 mul=9  tl=40 ks=0 ar=24 am=0 d1r=5 d2r=4 sl=1 rr=5
    op=2 dt=0 mul=3  tl=42 ks=1 ar=20 am=0 d1r=5 d2r=3 sl=1 rr=6
    op=3 dt=0 mul=4  tl=44 ks=1 ar=20 am=0 d1r=4 d2r=3 sl=1 rr=5
    op=4 dt=0 mul=3  tl=46 ks=1 ar=24 am=0 d1r=5 d2r=4 sl=2 rr=6

`op=N` labels *algorithm operator* N (1..4) — the operator numbers found in
connection diagrams and FMP editors, so `alg=4` really is the two pairs
op1->op2 and op3->op4.  Do NOT read N as a chip register slot: the OPN core
addresses operators in register-slot order 1-3-2-4, i.e. algorithm operator
k lives in register slot FMOPN_OP_SLOT[k] = {0,2,1,3} (confirmed against
ymfm `operator_map` and NP2kai fmgen `slottable`).  That map lives in
core/lib/fmopn.c fmopn_op_slot (single source of truth).

Compiled layout (32 bytes, one patch): the file stores operators in
algorithm order, so file idx k holds algorithm operator k+1 (this file's
OP_FILE is the identity permutation).
  op 1 (file idx 0): DT<<4|MUL  TL  KS<<6|AR  AM<<7|D1R  D2R  SL<<4|RR
  op 2 (file idx 1):   same 6-byte shape
  op 3 (file idx 2):   same 6-byte shape
  op 4 (file idx 3):   same 6-byte shape
  byte 24: FB<<3|AL
  byte 25: pan<<6 | AMS<<4 | PMS  (bits7-6 pan, 5-4 AMS, bit3 reserved 0,
           bits2-0 PMS; fmseq packs the fields back and writes reg $B4).
           bytes 26..31: 0

The binary is validated by fmopn_patch_validate (reserved bits must stay
clear), so range checks below mirror its FMOPN_E_* bits.

Usage:
    fm_patch.py <project_dir> <name> <src.fmp>
Registers a FMP row (id auto).  Rewrites name/type when the same source
file is already registered.
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from naiz_lib import project_assets_dir  # noqa: E402

# Source `op=N` (algorithm operator) is stored at file idx N-1, so the file is
# laid out in algorithm order (identity).  core/lib/fmopn.c maps file idx ->
# chip register slot via fmopn_op_slot = {0,2,1,3}.
OP_FILE = [0, 1, 2, 3]

# (key, min, max) — mirrors the FMOPN_E_* ranges in fmopn.h.
_OP_KEYS = [
    ('dt', 0, 0x07),
    ('mul', 0, 0x0F),
    ('tl', 0, 0x7F),
    ('ks', 0, 0x03),
    ('ar', 0, 0x1F),
    ('am', 0, 0x01),
    ('d1r', 0, 0x1F),
    ('d2r', 0, 0x1F),
    ('sl', 0, 0x0F),
    ('rr', 0, 0x0F),
]
_GLOBAL_KEYS = ['alg', 'fb', 'pan', 'ams', 'pms']


class _PatchError(RuntimeError):
    """Text source is malformed.  Message carries line info and err bit."""


def _require(key, line, value, lo, hi):
    if not (lo <= value <= hi):
        raise _PatchError(
            f"line {line}: {key}={value} out of range {lo}..{hi}")
    return value


def _parse_value(key, line, val):
    try:
        return int(val, 0)   # permits hex like 0xc0 / 0x2A
    except ValueError:
        raise _PatchError(f"line {line}: {key}={val!r} is not a number")


def parse_patch(text):
    """Parse .fmp text into (params, ops).  ops keyed by algorithm operator 1..4.

    Authoring format: whitespace-separated `key=value` tokens.  `op=N` starts
    an operator block (algorithm operator 1..4); every other key on the line
    belongs to that op.  Lines without `op=` carry the global keys
    alg/fb/pan.  Raises _PatchError on bad content.
    """
    ops = {}
    params = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        slot = None
        fields = {}
        for tok in line.split():
            key, _, val = tok.partition('=')
            if not key:
                raise _PatchError(f"line {lineno}: malformed token {tok!r}")
            if key == 'op':
                if slot is not None:
                    raise _PatchError(
                        f"line {lineno}: two op= on one line are ambiguous")
                slot = _parse_value('op', lineno, val)
                if not (1 <= slot <= 4):
                    raise _PatchError(f"line {lineno}: op={slot} not in 1..4")
            elif slot is None:
                if key not in _GLOBAL_KEYS:
                    raise _PatchError(
                        f"line {lineno}: op must precede {key!r}; global "
                        f"keys are alg/fb/pan/ams/pms only")
                params[key] = (lineno, _parse_value(key, lineno, val))
            else:
                fields[key] = (lineno, _parse_value(key, lineno, val))
        if slot is not None:
            if slot in ops:
                raise _PatchError(f"line {lineno}: duplicate op={slot}")
            ops[slot] = fields

    for k in (1, 2, 3, 4):
        if k not in ops:
            raise _PatchError(f"patch missing op={k}")

    params.setdefault('pan', (0, 0xC0))
    params.setdefault('ams', (0, 0))
    params.setdefault('pms', (0, 0))
    known = {kk for kk, _lo, _hi in _OP_KEYS}
    ranges = {kk: (lo, hi) for kk, lo, hi in _OP_KEYS}
    for slot, fields in ops.items():
        extra = set(fields) - known
        if extra:
            raise _PatchError(f"op={slot}: unknown key(s) {sorted(extra)}")
        missing = known - set(fields)
        if missing:
            raise _PatchError(
                f"op={slot}: missing key(s) {sorted(missing)}")
        for kk, (lineno, value) in fields.items():
            lo, hi = ranges[kk]
            _require(kk, lineno, value, lo, hi)

    for kk in ('alg', 'fb'):
        if kk not in params:
            raise _PatchError(f"missing global {kk}")
    _global_ranges = {'pan': (0, 0xC0), 'ams': (0, 3), 'pms': (0, 7)}
    for kk, (lineno, value) in params.items():
        if kk in _global_ranges:
            lo, hi = _global_ranges[kk]
            _require(kk, lineno, value, lo, hi)
            # FMOPN_E_PAN: bit3 is reserved on the chip write path.
            if kk == 'pan' and value & 0x3F:
                raise _PatchError(
                    f"line {lineno}: pan=0x{value:X}: only the L/R bits "
                    f"(0xC0) belong to pan; use ams=/pms= for the rest")
        else:
            _require(kk, lineno, value, 0, 0x07)

    return params, ops


def to_bytes(params, ops):
    """32-byte binary in algorithm order.  ops keyed by algorithm operator,
    values are (line, value) pairs from parse_patch (line kept for
    diagnostics)."""
    out = bytearray(32)
    for op in (1, 2, 3, 4):
        file_idx = OP_FILE[op - 1]
        f = {k: v for k, (_l, v) in ops[op].items()}
        off = file_idx * 6
        out[off + 0] = (f['dt'] << 4) | f['mul']
        out[off + 1] = f['tl']
        out[off + 2] = (f['ks'] << 6) | f['ar']
        out[off + 3] = (f['am'] << 7) | f['d1r']
        out[off + 4] = f['d2r']
        out[off + 5] = (f['sl'] << 4) | f['rr']
    out[24] = (params['fb'][1] << 3) | params['alg'][1]
    pan = params['pan'][1] if 'pan' in params else 0xC0
    ams = params['ams'][1] if 'ams' in params else 0
    pms = params['pms'][1] if 'pms' in params else 0
    out[25] = (pan & 0xC0) | (ams << 4) | pms
    return bytes(out)


def compile_source(path):
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    params, ops = parse_patch(text)
    return to_bytes(params, ops)


def register_patch(project_dir, src_fmp, name, assets_dir=None):
    """INSERT a FMP row.  Idempotent by (filename, type)."""
    db_path = os.path.join(project_dir, 'ASSETS.DB')
    if not os.path.isfile(db_path):
        print(f"ERROR: ASSETS.DB not found: {db_path}")
        sys.exit(1)
    if assets_dir is None:
        assets_dir = project_assets_dir(project_dir)
    root = Path(assets_dir).resolve()
    src_abs = Path(src_fmp).resolve()
    try:
        rel_name = src_abs.relative_to(root).as_posix()
    except ValueError:
        print(f"ERROR: FM patch source must live under {root}: {src_fmp}")
        sys.exit(1)

    data = compile_source(src_abs)
    if len(data) != 32:
        raise RuntimeError(f"{src_fmp}: compiled {len(data)} bytes, want 32")

    db = sqlite3.connect(db_path)
    try:
        row = db.execute(
            "SELECT id FROM img_map WHERE filename=? AND type='FMP'",
            (rel_name,)).fetchone()
        if row is not None:
            db.execute(
                "UPDATE img_map SET name=? WHERE id=?",
                (name, row[0]))
            print(f"  ASSETS.DB: updated id={row[0]} → {rel_name} (FMP)")
        else:
            cur = db.execute(
                "INSERT INTO img_map (filename, type, name) VALUES (?,?,?)",
                (rel_name, 'FMP', name))
            print(f"  ASSETS.DB: registered id={cur.lastrowid} "
                  f"{rel_name} (FMP)")
        db.commit()
    finally:
        db.close()


def main():
    ap = argparse.ArgumentParser(description="FM patch text -> 32B + register")
    ap.add_argument("project_dir", help="project directory (ASSETS.DB lives here)")
    ap.add_argument("name", help="script key (e.g. brass)")
    ap.add_argument("src", help="path to the .fmp text (must stay under assets/)")
    args = ap.parse_args()

    if not os.path.isfile(args.src):
        print(f"ERROR: no such patch file: {args.src}")
        sys.exit(1)
    try:
        data = compile_source(args.src)
    except _PatchError as e:
        print(f"ERROR: {args.src}:\n  {e}")
        sys.exit(1)
    print(f"fm_patch: {args.src} → {len(data)} bytes (validated)")

    register_patch(args.project_dir, args.src, args.name)


if __name__ == '__main__':
    main()