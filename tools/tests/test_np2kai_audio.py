import os
import sys
import tempfile
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_np2kai_audio_smoke():
    """Smoke test: SDL3 disk-driver tone generation produces non-silent output."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "smoke.raw"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        env["SDL_AUDIODRIVER"] = "disk"
        env["SDL_AUDIO_DISK_OUTPUT_FILE"] = str(out)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.diag.np2kai_audio",
                "--smoke",
                "--out",
                str(out),
            ],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
        )
        stdout = result.stdout
        assert result.returncode == 0, f"smoke failed: {stdout}"
        assert out.exists(), f"smoke did not create output: {stdout}"
        data = out.read_bytes()
        assert len(data) > 0, f"empty smoke file: {stdout}"
        import struct
        import math
        n = len(data) // 2
        samples = struct.unpack("<" + "h" * n, data)
        rms = math.sqrt(sum(s * s for s in samples) / len(samples))
        assert rms >= 8.0, f"smoke capture is silent (rms={rms:.1f}): {stdout}"


def test_np2kai_audio_rms_gate():
    """Gate behavior: empty/silent-like files should be rejected by preflight."""
    # Empty file case: the tool's RMS check exits non-zero if n==0
    from tools.diag import np2kai_audio
    with tempfile.TemporaryDirectory() as td:
        empty = Path(td) / "empty.raw"
        empty.write_bytes(b"")
        try:
            np2kai_audio.rms_of(empty)
        except Exception:
            pass
        # rms_of returns (0,0,0) for empty; tool exits on n==0
        rms, peak, n = np2kai_audio.rms_of(empty)
        assert n == 0 and rms == 0.0


def test_np2kai_audio_smoke_nonempty_and_non_silent():
    """Stronger smoke assertion: output exists, non-empty, RMS >= SILENCE_RMS."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "smoke.raw"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        env["SDL_AUDIODRIVER"] = "disk"
        env["SDL_AUDIO_DISK_OUTPUT_FILE"] = str(out)
        res = subprocess.run(
            [sys.executable, "-m", "tools.diag.np2kai_audio", "--smoke", "--out", str(out)],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
        )
        assert res.returncode == 0, res.stdout
        st = out.stat()
        assert st.st_size > 0
        from tools.diag import np2kai_audio
        rms, peak, n = np2kai_audio.rms_of(out)
        assert n > 0
        assert rms >= np2kai_audio.SILENCE_RMS
