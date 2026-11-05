# PROVENANCE — ymfm (vendored third-party source)

This directory contains an unmodified copy of **ymfm**, a collection of
BSD-licensed Yamaha FM sound cores by Aaron Giles, used **offline only** as a
reference FM renderer (the "oracle") for Naiz's FM patch lab (devdocs/136).

## Upstream

| Field | Value |
|---|---|
| Project | ymfm |
| Author | Aaron Giles |
| URL | https://github.com/aaronsgiles/ymfm |
| Commit | `81aec25ccbb98f4873a255f7551ac4dadac59b4a` (branch `main`, 2026-07-27) |
| Retrieved | `codeload.github.com/aaronsgiles/ymfm/tar.gz/refs/heads/main` |
| License | BSD 3-Clause (see `LICENSE` in this directory) |

## What is vendored

- `src/` — the full ymfm source tree, **verbatim** (no edits).
- `LICENSE` — upstream BSD 3-Clause license text, verbatim.
- `UPSTREAM_README.md`, `GeneralInfo.md` — upstream docs, verbatim (for context).

## Why this is here (and why it is safe)

- ymfm is a **host-side development tool only**. It is compiled into the
  `fmbench` oracle under `tools/naiz_audio/fmbench/`, which runs on the
  developer machine (Linux). It is **never** linked into `engine.exe`, never
  injected into the HDI, and never runs on the PC-98 / NP2kai target.
- The engine's own runtime FM playback is `core/lib/fmopn.c` +
  `core/lib/fmseq.c` + `core/plat/hal_audio.c`; that path is unaffected by
  this directory.
- ymfm's BSD 3-Clause license permits redistribution and use in source and
  binary forms, with the license and copyright notice retained (both are
  present here). No GPL contamination: BSD is permissive.

## Updating

To move to a newer ymfm, re-download the tarball for the chosen commit,
replace `src/` and `LICENSE`, and update the commit hash / date above.
