# Diagnostic Tools

Tools in `tools/diag/` for diagnosing boot, file I/O, video output, and emulator
write-back issues without requiring engine modifications.

## Quick Reference

| Tool | File | Purpose |
|------|------|---------|
| `gen_com` | `tools/diag/gen_com.py` | Generate DOS COM test programs |
| `hdi_patch_autoexec` | `tools/diag/hdi_patch_autoexec.py` | Replace AUTOEXEC.BAT directly in an HDI |
| `hdi_find_file` | `tools/diag/hdi_find_file.py` | Search files in HDI by name, content, or FAT chain |
| `hdi_integrity` | `tools/diag/hdi_integrity.py` | SHA256 checkpoint to detect NP2kai disk writes |
| `np2kai_screenshot` | `tools/diag/np2kai_screenshot.py` | NP2kai window capture (auto-selects main display) |
| `np2kai_serial` | `tools/diag/np2kai_serial.py` | Serial port debugging (inject + launch + capture) |

These tools complement the main `tools/naiz_img/` toolchain (`inject.py`, `listhdi.py`).
All accept an HDI path and run in read-only mode unless explicitly writing.

---

## 1. gen_com — COM Test File Generator

Generate COM-format executables for targeted DOS subsystem testing.

### Built-in Presets

| Preset | Produces | What It Tests |
|--------|----------|---------------|
| `rwcheck` | `RWCHECK.LOG` → `RWCHECK OK` | DOS file create + write (INT 21h AH=3Ch / AH=40h) |
| `vramwrite` | Writes `ABCD` to text VRAM @ 0xA000:0, then HLTs | Text VRAM layer visible via emulator screenshot |
| `serialwrite` | Inits COM1 (9600 8N1), sends `Hello from DOS!\r\n`, exits | Serial port output (INT 14h) captured via PTY |

### Custom COM

Any 8.3 filename + ASCII data via `--create` / `--data`.

### Usage

```bash
# List presets
python -m tools.diag.gen_com --list-presets

# Generate preset
python -m tools.diag.gen_com --preset rwcheck -o /tmp/rwcheck.com
python -m tools.diag.gen_com --preset vramwrite -o /tmp/vram.com
python -m tools.diag.gen_com --preset serialwrite -o /tmp/serial.com

# Generate custom file-writer
python -m tools.diag.gen_com -o /tmp/test.com --create TEST.LOG --data "PASSED"
```

### Typical Workflow

```bash
# 1. Generate
python -m tools.diag.gen_com --preset rwcheck -o /tmp/rwcheck.com

# 2. Inject into game's HDI directory
cp /tmp/rwcheck.com games/demo-A1/
python -m tools.naiz_img.inject --game demo-A1 --yes

# 3. Patch autoexec to run it instead of ENGINE.EXE
python -m tools.diag.hdi_patch_autoexec disks/demo-A1.hdi "Rwcheck.com"

# 4. Run emulator
makegame.sh test demo-A1

# 5. Check output file in HDI
python -m tools.diag.hdi_find_file disks/demo-A1.hdi "RWCHECK.LOG"
python -m tools.diag.hdi_find_file disks/demo-A1.hdi "RWCHECK.LOG" --dump

# 6. Restore autoexec
python -m tools.diag.hdi_patch_autoexec disks/demo-A1.hdi "ENGINE.EXE"
```

---

## 2. hdi_patch_autoexec — Direct AUTOEXEC.BAT Patcher

Modify AUTOEXEC.BAT in a compiled HDI without rebuilding the entire image.
Works by patching the first cluster's data and updating the directory entry size.

### Limitations

- New content must not exceed the original file's cluster allocation (typically
  2048 bytes for one-cluster files). For larger replacements, use `inject.py`
  with `--no-autoexec` + a custom AUTOEXEC.BAT in the game directory.
- Only patches the root-directory `AUTOEXECBAT` entry.

### Usage

```bash
# Simple replacement
python -m tools.diag.hdi_patch_autoexec disks/demo-A1.hdi "TEST.COM"

# From file
python -m tools.diag.hdi_patch_autoexec disks/demo-A1.hdi --file custom.bat

# Preview without writing
python -m tools.diag.hdi_patch_autoexec disks/demo-A1.hdi "TEST.COM" --dry-run

# List root directory (all entries, not just autoexec)
python -m tools.diag.hdi_patch_autoexec disks/demo-A1.hdi --list
```

---

## 3. hdi_find_file — HDI File Search

Search files in an HDI by glob pattern, inspect FAT chains, dump contents,
or search for strings across file data.

### Usage

```bash
# Search by filename pattern
python -m tools.diag.hdi_find_file disks/demo-A1.hdi "*.LOG"
python -m tools.diag.hdi_find_file disks/demo-A1.hdi "ENGINE.*"

# Show FAT cluster chain
python -m tools.diag.hdi_find_file disks/demo-A1.hdi "ENGINE.EXE" --chain

# Dump file content to terminal
python -m tools.diag.hdi_find_file disks/demo-A1.hdi "AUTOEXEC.BAT" --dump
python -m tools.diag.hdi_find_file disks/demo-A1.hdi "ENGINE.LOG" --hex

# Search for a string across all matching files
python -m tools.diag.hdi_find_file disks/demo-A1.hdi "*.LOG" --search "Naiz engine"

# Output raw bytes of first match (for piping)
python -m tools.diag.hdi_find_file disks/demo-A1.hdi "ENGINE.LOG" --raw-bytes > /tmp/engine.log

# List all files in the HDI
python -m tools.diag.hdi_find_file disks/demo-A1.hdi "" --list-all
```

---

## 4. hdi_integrity — SHA256 Checkpoint Tool

Detects whether NP2kai (or any emulator) actually writes disk changes back to
the `.hdi` file. Computes SHA256 of the data area (FAT + directory + file data,
excluding VBR and reserved sectors) and saves it as a JSON checkpoint.

The guest OS writes to the HDI via INT 13h; NP2kai should forward those writes
to the host file. A mismatch between saved and current SHA256 confirms writes
are being persisted.

### Usage

```bash
# Save checkpoint before test
python -m tools.diag.hdi_integrity save disks/demo-A1.hdi -l "before_emu"

# Run emulator...

# Verify checkpoint
python -m tools.diag.hdi_integrity verify disks/demo-A1.hdi

# Quick check (no comparison)
python -m tools.diag.hdi_integrity check disks/demo-A1.hdi

# List all checkpoints
python -m tools.diag.hdi_integrity list

# Clean up
python -m tools.diag.hdi_integrity clean
```

### Checkpoint Location

Checkpoints are stored as `{hdi_name}.json` in `.hdi_checkpoints/` at the
project root. They contain the HDI basename, label, data-area hash, full-file
hash, and BPB metadata to detect structural changes.

### Interpreting Results

| Data area | Full file | Meaning |
|-----------|-----------|---------|
| MATCH | MATCH | No disk writes at all (emu may not have run, or disk is read-only) |
| DIFFERENT | MATCH | HDI rebuilt by inject.py or other tool (same size, different content) |
| DIFFERENT | DIFFERENT | Emulator wrote back guest OS disk changes |

---

## 5. np2kai_screenshot — NP2kai Screen Capture

Captures the NP2kai emulator window using ImageMagick (`import`). Handles
correct window selection: the emulator PID creates 3 X11 windows — a 10×10
tray icon, a 200×200 toolbar, and the 640×459 main display. This tool
automatically picks the main display.

### Background

The window title `wx NP21kai (IA-32)` does not match naive `xdotool search --name NP2kai` because the title contains `NP21` not `NP2`. The tool searches by
substring `NP21kai` instead.

Sub-windows with title `wxnp21kai` (10×10 and 200×200) are rejected by size
threshold; only the 640×459 display window is captured.

### Usage

```bash
# Capture with emulator already running
python -m tools.diag.np2kai_screenshot -o /tmp/np2kai.png

# Launch emulator, wait 8 seconds for boot, then capture
python -m tools.diag.np2kai_screenshot --launch --wait 8 -o /tmp/boot.png

# List all NP2kai windows (for debugging window selection)
python -m tools.diag.np2kai_screenshot --list-windows

# Capture a specific window by ID
python -m tools.diag.np2kai_screenshot --wid 12345678 -o /tmp/custom.png
```

### Typical Workflow

```bash
# 1. Generate vramwrite COM
python -m tools.diag.gen_com --preset vramwrite -o /tmp/vram.com

# 2. Deploy to HDI
cp /tmp/vram.com games/demo-A1/
python -m tools.naiz_img.inject --game demo-A1 --yes
python -m tools.diag.hdi_patch_autoexec disks/demo-A1.hdi "VRAM.COM"

# 3. Launch emulator and capture
python -m tools.diag.np2kai_screenshot --launch --wait 8 -o /tmp/vram_test.png

# Check the image: should show "ABCD" on screen if text VRAM works
```

### makegame.sh

The normal build/test cycle still works:

```bash
makegame.sh make demo-A1     # compile + inject
makegame.sh test demo-A1     # run emulator
makegame.sh test demo-A1 --serial  # run with serial capture
```

### inject.py

Extract runtime files from an HDI after emulation:

```bash
python -m tools.naiz_img.inject --game demo-A1 --extract "DEMO-A1/ENGINE.LOG"
```

This pulls the file to `logs/ENGINE.RUN.{timestamp}.log`.

### listhdi.py

Already available for basic tree listing:

```bash
python -m tools.naiz_img.listhdi disks/demo-A1.hdi
```

### np2kai_screenshot.py

Visual verification of emulator screen output:

```bash
# Capture current emulator state
python -m tools.diag.np2kai_screenshot -o /tmp/current.png

# Launch + capture
python -m tools.diag.np2kai_screenshot --launch --wait 8 -o /tmp/boot.png
```

### np2kai_serial.py

End-to-end serial debugging (inject → launch → capture):

```bash
python -m tools.diag.np2kai_serial --game demo-A1 --timeout 20
```

### debug workflow: engine-side

Engine log output is mirrored to:
1. `ENGINE.LOG` on disk (via `log_flush()`)
2. Text VRAM layer (segment 0xA000, via `log_write_screen_len()`, auto-called
   from `buf_write()`)
3. Serial port (via `log_enable_serial()`, requires `--serial` at test time)

To verify text VRAM output, run with `np2kai_screenshot` and inspect the
resulting image. To verify serial output, run with `--serial` and follow
`logs/serial_*.log`.

---

## Known Limitations

| Issue | Description |
|-------|-------------|
| HDI not written back | NP2kai may not flush INT 13h writes to the `.hdi` file on non-graceful exit. `hdi_integrity` confirms this. Workaround: use `--serial` or text VRAM for real-time output. |
| AUTOEXEC not picked up | If `CD` in AUTOEXEC fails (e.g. unfresh directory cluster), DOS may not find the game files. Use `hdi_find_file` with `--list-all` to verify directory structure. |
| COM file path | AUTOEXEC.BAT runs from root; use `CD \GAMEDIR` and relative paths, or absolute `\GAMEDIR\FILE.COM`. |
