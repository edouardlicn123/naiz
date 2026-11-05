#!/usr/bin/env python3
"""Export a 32-byte FM patch binary to FMP `@` and VOPM text (devdoc 186,
was 模仿升级计划 161 §三 B).

Input is the single-source 32-byte layout documented in fm_patch.py:
  per op (file idx k = algorithm operator k+1), 6 bytes:
    DT<<4|MUL  TL  KS<<6|AR  AM<<7|D1R  D2R  SL<<4|RR
  byte 24: FB<<3|ALG
  byte 25: PAN<<6 | AMS<<4 | PMS
  bytes 26..31: 0

Outputs two text forms for human audit / cross-check against editors:
  - FMP `@` voice definition: parameter order and ranges follow the project's
    verified FMP reference (docs/refdocs/F03_opna_fm_and_bgm_routes.md §4.3:
    header `@ num ALG FB [=name]`, then 4 lines of AR DR SR RR SL TL KS ML DT
    AMS; SR is FMP's name for D2R; DT printed 0-7 in register form).
  - VOPM paste text: per-op `AR D1R D2R RR SL TL KS DT MUL DT2 AMS` plus
    AL/FB/PAN/AMS/PMS globals (DT2 is OPM-only, emitted as 0).

This is a one-way export; text -> binary already exists (fm_patch.compile_source).

Usage:
    fmp_export.py <patch.bin | -> [--num N] [--name NAME]
"""

import argparse
import sys


def _fields(blob):
    if len(blob) != 32:
        raise SystemExit(f"ERROR: patch must be 32 bytes, got {len(blob)}")
    ops = []
    for i in range(4):
        base = i * 6
        ops.append({
            "dt": (blob[base + 0] >> 4) & 0x07,
            "mul": blob[base + 0] & 0x0F,
            "tl": blob[base + 1],
            "ks": (blob[base + 2] >> 6) & 0x03,
            "ar": blob[base + 2] & 0x1F,
            "am": (blob[base + 3] >> 7) & 0x01,   # per-op LFO AM enable
            "d1r": blob[base + 3] & 0x1F,
            "d2r": blob[base + 4],
            "sl": (blob[base + 5] >> 4) & 0x0F,
            "rr": blob[base + 5] & 0x0F,
        })
    alg = blob[24] & 0x07
    fb = (blob[24] >> 3) & 0x07
    pan = (blob[25] >> 6) & 0x03
    ams = (blob[25] >> 4) & 0x03
    pms = blob[25] & 0x0F
    return ops, alg, fb, pan, ams, pms


def to_fmp(blob, num=0, name=None):
    """FMP `@` voice definition (F03 §4.3 order: AR DR SR RR SL TL KS ML DT
    AMS; SR == D2R)."""
    ops, alg, fb, _pan, _ams, _pms = _fields(blob)
    head = f"@ {num} {alg} {fb}"
    if name:
        head += f" ={name}"
    lines = [head]
    for o in ops:
        lines.append("   {:d} {:d} {:d} {:d} {:d} {:d} {:d} {:d} {:d} {:d}"
                     .format(o["ar"], o["d1r"], o["d2r"], o["rr"], o["sl"],
                             o["tl"], o["ks"], o["mul"], o["dt"], o["am"]))
    return "\n".join(lines)


def to_vopm(blob, name=None):
    """VOPM paste text (DT2 emitted as 0: OPM-only, absent on OPN)."""
    ops, alg, fb, pan, ams, pms = _fields(blob)
    lines = [f'@:0 :"{name if name else ""}"',
             f"AL: {alg}",
             f"FB: {fb}"]
    for o in ops:
        lines.append(
            "AR: {ar}  D1R: {d1r}  D2R: {d2r}  RR: {rr}  SL: {sl}  "
            "TL: {tl}  KS: {ks}  DT: {dt}  MUL: {mul}  DT2: 0  AMS: {am}"
            .format(**o))
    lines.append(f"PAN: {pan}")
    lines.append(f"AMS: {ams}")
    lines.append(f"PMS: {pms}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("patch", help="32-byte .fmp binary, or - for stdin")
    ap.add_argument("--num", type=int, default=0,
                    help="voice number for the FMP @ line")
    ap.add_argument("--name", help="voice name")
    args = ap.parse_args()

    blob = sys.stdin.buffer.read() if args.patch == "-" \
        else open(args.patch, "rb").read()
    print("# --- FMP @ ---")
    print(to_fmp(blob, num=args.num, name=args.name))
    print()
    print("# --- VOPM ---")
    print(to_vopm(blob, name=args.name))


if __name__ == "__main__":
    main()
