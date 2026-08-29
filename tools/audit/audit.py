#!/usr/bin/env python3
"""Incremental, scripted anti-regression audit for the naiz codebase.

Combines the AGENTS.md section-17 rule sets (rules_c/p/rules_s) with
git-aware incremental state (state.py): unchanged files are skipped, so a
repeat run only re-checks edited/new files and prints a compact report.
AUTO rule violations exit non-zero; HEUR candidates are printed for human
confirmation; MANUAL rules emit a targeted review checklist.

Run:
    python -m tools.audit.audit                # incremental (recommended)
    python -m tools.audit.audit --reset        # force full re-check
    python -m tools.audit.audit --rules C5,C11 # only selected rule ids
Exit codes:
    0  no AUTO violations
    1  at least one deterministic (AUTO) violation found
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from tools.audit import rules_c, rules_p, rules_s, state, verify


def _build_registry():
    reg = {}
    for mod in (rules_c, rules_p, rules_s):
        reg.update(mod.registry())
    return reg


def _build_manual_notes():
    notes = {}
    for mod in (rules_c, rules_p, rules_s):
        notes.update(getattr(mod, "MANUAL_NOTES", {}))
    return notes


def collect_files(root):
    """Return ordered [(relpath, abspath)] for every audited source file."""
    c_files = []
    for path in sorted((root / "core").glob("*/*.c")):
        if path.name == "vram.c":  # opt-in reference impl, excluded from build
            continue
        c_files.append(path)
    p_files = []
    for path in sorted((root / "tools").rglob("*.py")):
        rel = path.relative_to(root)
        parts = rel.parts
        # tools/audit is the audit engine itself (rule samples inside its
        # regexes would self-pollute results); its quality is covered by
        # test_audit_rules.py instead.
        if any(seg in ("venv", "__pycache__", "tests", "audit")
               for seg in parts):
            continue
        p_files.append(path)
    s_files = []
    for pattern in ("makegame.sh", "start.sh"):
        p = root / pattern
        if p.is_file():
            s_files.append(p)
    s_files += sorted((root / "core").glob("*.sh"))
    return c_files + p_files + s_files


def _kind_of(rel):
    if rel.endswith(".sh") or rel in ("makegame.sh", "start.sh"):
        return "S"
    if rel.startswith("core/"):
        return "C"
    if rel.startswith("tools/"):
        return "P"
    return None


def _run_rule(rule_id, func, text, path):
    try:
        return func(text, path)
    except (ValueError, IndexError) as exc:
        return [(1, f"audit rule {rule_id} itself raised: {exc}")]


def changed_lines(root, since):
    """Map relpath -> set(added line numbers) for lines new since `since`.

    Covers committed changes (``since..HEAD``) plus uncommitted working-tree
    edits (``HEAD``).  New/untracked files map to ``None`` (every line is
    new).  Only files returned here are in scope for a ``--since`` run.
    """
    git = ["git", "-C", str(root)]

    def _run(*args):
        r = subprocess.run(git + list(args), capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"audit --since: git {args[0]} failed: "
                     f"{r.stderr.strip() or r.stdout.strip()}")
        return r.stdout

    whole = set()
    partial = {}

    def _parse(out):
        cur_path = None
        cur_all = False
        cur_lineno = None
        for ln in out.splitlines():
            if ln.startswith("diff --git "):
                if " b/" in ln:
                    cur_path = ln.split(" b/", 1)[1].strip()
                else:
                    cur_path = None
                cur_all = False
                cur_lineno = None
            elif ln.startswith("new file mode"):
                cur_all = True
            elif ln.startswith("deleted file mode"):
                cur_path = None
            elif ln.startswith("@@"):
                if not cur_path:
                    continue
                m = re.search(r"\+(\d+)(?:,(\d+))?", ln)
                if not m:
                    continue
                cur_lineno = None if m.group(2) == "0" else int(m.group(1))
            elif cur_path and cur_lineno is not None:
                if ln.startswith("+"):
                    partial.setdefault(cur_path, set()).add(cur_lineno)
                    cur_lineno += 1
                elif ln.startswith("-"):
                    pass
                else:
                    cur_lineno += 1
        if cur_all and cur_path:
            whole.add(cur_path)

    _parse(_run("diff", "--unified=0", since, "HEAD", "--"))
    _parse(_run("diff", "--unified=0", "HEAD", "--"))
    for p in _run("ls-files", "--others", "--exclude-standard").split():
        whole.add(p)

    merged = {}
    for p in whole:
        merged[p] = None
    for p, lines in partial.items():
        if p not in merged:
            merged[p] = lines
    return merged


def run_audit(root=None, reset=False, verbose=False, quiet=False,
              manual=True, select=None, save_state=True, notes=None,
              since=None):
    """Run the rule audit. Returns process exit code (0 or 1).

    With ``since=<git-ref>`` only lines added after that ref (plus uncommitted
    edits) are reported; deterministic violations restricted to those lines
    still gate the exit code, making the audit usable as a pre-commit gate.
    """
    root = Path(root) if root else state.project_root()
    registry = _build_registry()
    manual_notes = _build_manual_notes()
    vnotes = verify.load(root) if notes is None else (notes or {})

    select = {s.upper().strip() for s in select.split(",")} if select else None
    wanted = {rid: spec for rid, spec in registry.items()
              if select is None or rid in select}

    files = collect_files(root)
    since_map = changed_lines(root, since) if since else None
    prev = None if reset else state.load(root)
    prev_files = (prev or {}).get("files", {}) or {}

    git = state.git_head(root)
    print(f"=== AUDIT RULES ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) "
          f"git={git} ===")
    if since_map is not None:
        affected = sum(1 for p in files
                       if str(p.relative_to(root)) in since_map)
        lines = sum(len(v) for v in since_map.values() if v)
        print(f"files={affected} (of {len(files)}; --since {since}) "
              f"changed-lines={lines} rules={len(wanted)}")
    else:
        print(f"files={len(files)} rules={len(wanted)} "
              f"state={'reset/full' if reset or not prev else 'incremental'}")

    new_state = {}
    # Run-local counts: deterministic violations found THIS run feed the
    # exit code; the state totals below additionally carry forward the
    # previously recorded counts of skipped (unchanged) files so the
    # summary / RESULT line reflects the project's full known status.
    fresh_violations = 0
    fresh_candidates = 0
    state_violations = 0
    state_candidates = 0
    skipped = 0
    changed = 0
    out_of_scope = 0

    for path in files:
        rel = str(path.relative_to(root))
        sha = state.sha256_of(path)
        info = {"sha256": sha, "violations": 0, "candidates": 0,
                "findings": []}

        allowed = None
        if since_map is not None:
            allowed = since_map.get(rel)
            if allowed is None:
                # Out of scope: carry previous records, do not scan.
                out_of_scope += 1
                prev_info = prev_files.get(rel)
                new_state[rel] = (dict(prev_info) if prev_info else info)
                continue

        if prev_files.get(rel, {}).get("sha256") == sha:
            skipped += 1
            # Carry previously recorded counts into the refreshed state so
            # incremental runs do not wipe candidate/violation visibility.
            prev_info = prev_files.get(rel, {})
            info["violations"] = prev_info.get("violations", 0)
            info["candidates"] = prev_info.get("candidates", 0)
            info["findings"] = list(prev_info.get("findings", []))
            state_violations += info["violations"]
            state_candidates += info["candidates"]
            if verbose:
                print(f"  [SKIP] {rel} (unchanged)")
            new_state[rel] = info
            continue

        changed += 1
        kind = _kind_of(rel)
        rule_ids = [rid for rid in sorted(wanted) if rid.startswith(kind)]
        if not rule_ids:
            new_state[rel] = info
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        findings = []
        for rid in rule_ids:
            func, level, desc = wanted[rid]
            hits = _run_rule(rid, func, text, path)
            for lineno, note in hits:
                if allowed is not None and lineno not in allowed:
                    continue
                if level == "AUTO":
                    info["violations"] += 1
                    fresh_violations += 1
                    state_violations += 1
                else:
                    info["candidates"] += 1
                    fresh_candidates += 1
                    state_candidates += 1
                findings.append((rid, level, lineno, note))

        if verbose or findings:
            print(f"  [{('VIOL' if info['violations'] else 'CAND')}] "
                  f"{rel} (viol={info['violations']} cand={info['candidates']})")
        for rid, level, lineno, note in findings:
            tag = ""
            loc = f"{rel}:{lineno}"
            vn = vnotes.get(loc)
            if vn:
                if verify.fresh(root, loc, vn):
                    tag = f" [verified-{vn.get('verdict')}]"
                else:
                    reason = ("line-changed"
                              if vn.get("line") is not None
                              else "file-changed")
                    tag = f" [verified-{vn.get('verdict')} STALE:{reason}]"
            print(f"    {loc} -- {rid}/{level} -- {note}{tag}")
        info["findings"] = [
            {"line": ln, "rule": rid, "level": level}
            for rid, level, ln, _ in findings]
        new_state[rel] = info

    # Project-wide verification state over every stored candidate (covers
    # skipped files carried from prior runs, so the number is a real total,
    # not just what happened to be printed this run).
    verified = stale = open_notes = 0
    for rel, finfo in new_state.items():
        for f in finfo.get("findings", []):
            if f["level"] == "AUTO":
                continue
            vn = vnotes.get(f"{rel}:{f['line']}")
            if not vn:
                open_notes += 1
            elif verify.fresh(root, f"{rel}:{f['line']}", vn):
                verified += 1
            else:
                stale += 1

    summary = {
        "files": len(files), "changed": changed,
        "skipped": skipped, "out_of_scope": out_of_scope,
        "violations": state_violations,
        "candidates": state_candidates,
        "fresh_violations": fresh_violations,
        "fresh_candidates": fresh_candidates,
        "verified": verified, "stale": stale, "open": open_notes,
    }
    out = fresh_violations
    if out:
        print(f"=== RESULT: {out} deterministic violations found this run "
              f"(state {state_violations}, exit 1) ===")
    else:
        print(f"=== RESULT: OK (violations={state_violations} "
              f"candidates={state_candidates} changed={changed} "
              f"skipped={skipped}) ===")
    print(f"=== Verification: {state_candidates} candidate(s), {verified} "
          f"verified, {stale} stale, {open_notes} open (--note "
          f"REL:LINENO:VERDICT to record) ===")

    if manual and not quiet and (changed > 0 or not prev):
        print("\n=== MANUAL REVIEW CHECKLIST (semantics that need a human) ===")
        for rid in sorted(manual_notes):
            if select is None or rid in select:
                print(f"  [{rid}] {manual_notes[rid]}")

    if save_state:
        state.save(root, new_state, summary,
                   checked_at=datetime.now().isoformat(timespec="seconds"))
        print(f"state saved: audit_state.json (git={git})")

    return 1 if out else 0


def parse_note_specs(notes, verdict=None, text=""):
    """Resolve repeatable --note flags into (loc, verdict, text) records.

    Self-contained form: ``REL:LINENO:VERDICT[:TEXT]`` (TEXT may contain
    further ':' characters).  A bare ``REL:LINENO`` falls back to the
    single-note ``--verdict``/``--text`` options; mixing a bare spec with
    multiple notes is rejected.
    """
    specs = []
    for spec in notes:
        parts = spec.split(":", 2)
        if len(parts) < 2 or not parts[1]:
            raise ValueError("--note expects REL:LINENO[:VERDICT[:TEXT]], "
                             f"got {spec!r}")
        lineno, v, t = parts[1], None, ""
        if len(parts) == 3:
            if not parts[2]:
                raise ValueError("--note verdict missing after ':', "
                                 f"got {spec!r}")
            if ":" in parts[2]:
                v, t = parts[2].split(":", 1)
            else:
                v, t = parts[2], ""
        loc = f"{parts[0]}:{lineno}"
        if v is None:
            if len(notes) > 1:
                raise ValueError("bare REL:LINENO notes without an inline "
                                 ":VERDICT only support a single --note; "
                                 "use REL:LINENO:VERDICT[:TEXT] instead")
            if verdict is None:
                raise ValueError("--note requires --verdict")
            v = verdict
            t = t or text
        if v not in verify.VERDICTS:
            raise ValueError(f"verdict must be one of {verify.VERDICTS}, "
                             f"got {v!r}")
        specs.append((loc, v, t))
    return specs


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Incremental anti-regression audit (AGENTS section 17)")
    parser.add_argument("--reset", action="store_true",
                        help="ignore saved state and re-check every file")
    parser.add_argument("--since", metavar="GIT-REF",
                        help="report only lines added after GIT-REF (plus "
                             "uncommitted edits); new deterministic "
                             "violations on those lines still exit 1")
    parser.add_argument("--rules", metavar="IDS",
                        help="comma-separated rule ids to run (default all)")
    parser.add_argument("--no-save", action="store_true",
                        help="do not update audit_state.json")
    parser.add_argument("--no-manual", action="store_true",
                        help="suppress the manual review checklist")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="log skipped (unchanged) files")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="minimal output (summary only)")
    parser.add_argument("--note", action="append",
                        metavar="REL:LINENO:VERDICT[:TEXT]",
                        help="record a verification note (repeatable, fully "
                             "self-contained). TEXT may contain extra ':' "
                             "characters. For a single note the older "
                             "REL:LINENO + --verdict + --text form still works.")
    parser.add_argument("--verdict", choices=verify.VERDICTS,
                        help="note verdict for a single bare --note: ok "
                             "(benign), fixed (bug fixed), todo (left open)")
    parser.add_argument("--text", default="", metavar="MSG",
                        help="free-form note text for a single bare --note")
    parser.add_argument("--list-notes", action="store_true",
                        help="print recorded verification notes and exit")
    args = parser.parse_args(argv)

    if args.list_notes:
        vnotes = verify.load()
        if not vnotes:
            print("no verification notes recorded")
            return 0
        for loc in sorted(vnotes):
            n = vnotes[loc]
            print(f"{loc} -- {n.get('verdict')} -- {n.get('text')} "
                  f"({n.get('date')})")
        return 0

    if args.note:
        try:
            specs = parse_note_specs(args.note, args.verdict, args.text)
        except ValueError as exc:
            parser.error(str(exc))
        vroot = verify.project_root()
        for loc, verdict, text in specs:
            path, _ = verify.add(vroot, loc, verdict, text)
        print(f"note saved: {path}")
        return 0

    rc = run_audit(
        reset=args.reset, verbose=args.verbose, quiet=args.quiet,
        manual=not args.no_manual, select=args.rules,
        save_state=not args.no_save, since=args.since)
    return rc


if __name__ == "__main__":
    sys.exit(main())