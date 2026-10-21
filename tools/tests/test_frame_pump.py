"""Frame pump + MAG progress-hook contract guard (devdoc 129).

Symptom: the formal BGM was audible but audibly stuttering, froze for the
whole time a `question` screen was open, and dropped out during the first
`char`/`cg` decode of a scene.

Three independent root causes, one contract each:

1.  **`hal_wallclock_smooth_advance()` is the sole writer of the virtual
    clock.**  `hal_wallclock_smooth_ms()` used to ADVANCE the clock by a
    bounded delta on every call, and three consumers (`audio_tick`,
    `nb_dialog_reveal_tick`, `anim_tick`) each polled it — so the BGM tempo
    was literally (calls per pass) x (passes per second).  Blocked in a
    menu, zero calls, the clock stalled; with the typewriter polling, 2-3
    calls per pass and the clock raced.  The split makes the clock
    independent of the caller count, which is what makes `audio_tick()`
    idempotent within a frame and the decode hook safe.

2.  **`engine_frame_pump()` exists and is called by every self-contained
    input loop.**  A loop that spins without it never advances BGM/PCM/
    typewriter/animation — the "question stops the music" bug.  Each loop
    in devdoc 129 §2.1 must call the pump.

3.  **`mag_set_progress_hook()` pumps audio from inside the decoder.**
    `mag.c` is a platform-agnostic lib and may not call into the engine,
    so the hook is the bridge.  There are FOUR call sites — the RLE loop
    and the 4bpp expand loop, on both the heap (`mag_decode`) and pool
    (`mag_decode_into`) ownership paths — and `audio_init()` must register
    the hook.  Missing any one of them re-freezes BGM in exactly one path.

These tests parse the C sources; a regression that unfreezes the clock,
drops a frame_pump from a blocking loop, or removes one decode call site
fails here.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HAL_H = ROOT / "core" / "plat" / "hal.h"
HAL_PC98_C = ROOT / "core" / "plat" / "hal_pc98.c"
FRAME_C = ROOT / "core" / "engine" / "frame.c"
FRAME_H = ROOT / "core" / "engine" / "frame.h"
MAG_C = ROOT / "core" / "lib" / "mag.c"
MAG_H = ROOT / "core" / "lib" / "mag.h"
AUDIO_C = ROOT / "core" / "engine" / "audio.c"
VCLOCK_H = ROOT / "core" / "lib" / "vclock.h"
IMAGE_H = ROOT / "core" / "engine" / "image.h"
IMAGE_C = ROOT / "core" / "engine" / "image.c"
IMAGE_CACHE_C = ROOT / "core" / "engine" / "image_cache.c"
NB_C = ROOT / "core" / "engine" / "nb.c"
MAIN_C = ROOT / "core" / "engine" / "main.c"

# Every self-contained input loop from devdoc 129 §2.1 plus main.c's three
# gameplay loops and the devdoc 150 BGM_BENCH loop (a #if-gated diagnostic
# loop that must also pump, or the clock would not advance while it spins).
# A loop missing here is a loop that freezes BGM.  bootmenu.c was the one loop
# that spun without the pump, so the virtual clock was never advanced before
# the game loop -- the first window closed seconds into scene 1 and the BGM
# played the nominal step until then (the "starts off-tempo" residual).
PUMP_CALLERS = [
    ("core/engine/main.c", 4),
    ("core/engine/bootmenu.c", 1),
    ("core/engine/nb_interact.c", 1),
    ("core/engine/nb_menu.c", 1),
    ("core/engine/nb_setting.c", 1),
    ("core/engine/nb_saveload.c", 1),
    ("core/engine/nb_save_dialog.c", 1),
    ("core/engine/nb_cggallery.c", 2),
    ("core/engine/nb_special.c", 1),
]


def _src(rel):
    p = ROOT / rel
    assert p.exists(), f"{rel} is missing"
    return p.read_text(encoding="utf-8")


def _func_body(src, name):
    """Return the body of the first definition of `name` in `src`."""
    m = re.search(r"(?:^|\n)[ \t\w\*]*\b" + re.escape(name) +
                  r"\s*\([^)]*\)\s*\n?\{", src)
    assert m, f"function {name}() not found"
    start = src.index("{", m.start())
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError(f"{name}(): unbalanced braces")


# --- 1. clock ownership: one writer, readers side-effect free ---------------

def test_smooth_advance_is_the_only_clock_writer():
    """The reader must be a plain read of vclock, and the writer must go
    through it.  The accumulator itself moved into lib/vclock (devdoc 129
    follow-up); what must hold is the split, not where the += lives."""
    c = HAL_PC98_C.read_text(encoding="utf-8")
    body = _func_body(c, "hal_wallclock_smooth_ms")
    assert "vclock_ms" in body, "reader must delegate to vclock"
    for bad in ("+=", "delta", "hal_wallclock_ms", "vclock_advance"):
        assert bad not in body, (
            f"hal_wallclock_smooth_ms() still moves the clock ({bad!r})"
        )


def test_smooth_advance_owns_the_step():
    c = HAL_PC98_C.read_text(encoding="utf-8")
    body = _func_body(c, "hal_wallclock_smooth_advance")
    assert "vclock_advance" in body, (
        "hal_wallclock_smooth_advance() must be the only writer path"
    )
    # exactly one vclock state, and nothing else pokes the accumulator
    assert c.count("VClock g_vclock") == 1, "vclock state must be a single instance"
    assert "vclock_advance" in body, "advance must go through vclock"


def test_smooth_step_is_slewed_not_clamped(monkeypatch=None):
    """The flutter defect: a floor/ceiling clamp on the step.

    The smoothing policy lives in lib/vclock; this pins that the old clamp
    constants are gone and the slew bound is what bounds the step, so the
    BGM's note onsets stay evenly spaced (devdoc 129 follow-up).
    """
    h = HAL_H.read_text(encoding="utf-8")
    for dead in ("SMOOTH_CLOCK_MIN_MS", "SMOOTH_CLOCK_MAX_MS"):
        assert dead not in h, f"{dead} (the flutter-causing clamp) is back in hal.h"
    vh = VCLOCK_H.read_text(encoding="utf-8")
    assert "VCLOCK_SLEW_UNITS" in vh, "vclock must bound step change via the slew"


def test_smooth_advance_is_declared_in_hal_h():
    assert "void hal_wallclock_smooth_advance(void)" in HAL_H.read_text(
        encoding="utf-8")


# --- 2. the frame pump and its call sites -----------------------------------

def test_frame_pump_sequence_is_exact():
    """vblank, clock, anim, audio, reveal — in that order, nothing dropped.

    Order matters twice: the clock must land BEFORE the consumers read it,
    and vblank_wait() must come first so the CPU yields at least once.
    """
    body = _func_body(FRAME_C.read_text(encoding="utf-8"), "engine_frame_pump")
    order = [call for call in ("vblank_wait()",
                               "hal_wallclock_smooth_advance()",
                               "anim_tick()",
                               "audio_tick()",
                               "nb_dialog_reveal_tick()")
             if call in body]
    assert order == ["vblank_wait()", "hal_wallclock_smooth_advance()",
                     "anim_tick()", "audio_tick()",
                     "nb_dialog_reveal_tick()"], (
        f"frame pump drifted (missing or reordered): {order}")


def test_every_blocking_loop_pumps_frames():
    """No self-contained input loop may spin without the pump (devdoc 129 §2.1)."""
    for rel, expected in PUMP_CALLERS:
        n = _src(rel).count("engine_frame_pump();")
        assert n == expected, (
            f"{rel} calls engine_frame_pump() {n}x, expected {expected}"
        )


# --- 3. decode progress hook: four sites, one registration ------------------

def test_mag_progress_hook_api_exists():
    h = MAG_H.read_text(encoding="utf-8")
    assert "void mag_set_progress_hook(void (*fn)(void))" in h
    c = MAG_C.read_text(encoding="utf-8")
    assert "MAG_PROGRESS_STRIDE" in c, "stride constant missing"
    assert re.search(r"static\s+void\s*\(\*g_mag_progress_hook\)\(void\)",
                     c), "hook storage missing"


def test_decode_has_four_pump_sites():
    """RLE loop + 4bpp expand loop, on BOTH the heap and the pool path.

    Losing one site re-freezes BGM on exactly one decode path.
    """
    c = MAG_C.read_text(encoding="utf-8")
    assert c.count("g_mag_progress_hook();") == 4, (
        f"expected 4 decode pump sites, found {c.count('g_mag_progress_hook();')}"
    )
    # ...and they must live in both decoders, not one four times.
    heap = _func_body(c, "mag_decode")
    pool = _func_body(c, "mag_decode_into")
    assert heap.count("g_mag_progress_hook();") == 2, "mag_decode lost a pump site"
    assert pool.count("g_mag_progress_hook();") == 2, "mag_decode_into lost a pump site"


def test_hook_is_null_guarded_and_bounded():
    """An unset hook must cost nothing, and a set hook must not spin forever."""
    c = MAG_C.read_text(encoding="utf-8")
    for guard in ("if (g_mag_progress_hook && _prog >= MAG_PROGRESS_STRIDE)",
                  "if (g_mag_progress_hook && (i % MAG_PROGRESS_STRIDE) == "
                  "(MAG_PROGRESS_STRIDE - 1))"):
        assert guard in c, f"missing stride guard: {guard}"
    assert "_prog = 0;" in c, "progress counter is never reset — stride fires once"


def test_engine_registers_the_hook_in_audio_init():
    """audio_init() must install the pump, else the hook is dead code.

    0.3.029 (devdoc 131 方案 B): the hook is no longer a bare audio_tick() —
    a long decode then only *read* the virtual clock and froze the BGM schedule.
    It is now frame_decode_pump(), which advances the clock on a real VBLANK
    edge and pumps audio, so the schedule keeps flowing through a decode."""
    body = _func_body(AUDIO_C.read_text(encoding="utf-8"), "audio_init")
    assert "mag_set_progress_hook(frame_decode_pump)" in body, (
        "audio_init() must route mag decode progress into frame_decode_pump() "
        "(devdoc 131 方案 B), not a bare audio_tick()"
    )


# --- 4. decode-time frame step (devdoc 131 方案 A/B) ------------------------

def test_decode_pump_advances_clock_unconditionally_and_stays_nonblocking():
    """devdoc 163 Phase 2 B2: the clock advance is UNCONDITIONAL (vclock
    self-measures its per-call rate, so decode-stride calls are rate-correct
    by construction; the old VBLANK gate froze the clock where the GDC poll
    never fires and raced it ~2x where it does).  Animation stays
    display-paced behind the poll, and the pump must never block (a full
    vblank_wait per 4 KB decode stride would make loading a portrait take
    seconds — devdoc 131 方案 B)."""
    body = _func_body(FRAME_C.read_text(encoding="utf-8"), "frame_decode_pump")
    i_adv = body.find("hal_wallclock_smooth_advance();")
    i_poll = body.find("hal_vblank_poll()")
    assert i_adv != -1, (
        "the decode pump must advance the virtual clock so the BGM flows")
    assert i_poll != -1, (
        "the decode pump must still poll hal_vblank_poll() for anim pacing")
    assert i_adv < i_poll, (
        "the clock advance must NOT sit behind the VBLANK gate "
        "(devdoc 163 B2: gate froze it where the poll never fires)")
    assert "vblank_wait()" not in body, (
        "the decode pump must not block on a full vblank_wait() per stride")
    assert re.search(r"if \(hal_vblank_poll\(\)\)[^\n]*\n\s*anim_tick\(\);",
                     body), (
        "anim_tick() must stay display-paced behind hal_vblank_poll() "
        "(devdoc 163 B2: only the clock advance moved out of the gate)")
    for call in ("audio_tick()", "nb_dialog_reveal_tick()"):
        assert call in body, f"the decode pump must keep pumping {call}"


def test_audio_tick_logs_pump_gaps_and_music_debt():
    """devdoc 163 Phase 1: audio_tick() must carry the AUDIO_PUMP_TRACE
    block — gap since the previous tick plus wall-vs-virtual debt — so BGM
    stalls are measurable from a serial capture, and the trace must be ON by
    default (it only emits past the audible threshold, healthy = silent)."""
    c = AUDIO_C.read_text(encoding="utf-8")
    body = _func_body(c, "audio_tick")
    assert "[AP] gap=%lu v=%lu w=%lu d=%+ld" in body, (
        "audio_tick() must emit the [AP] pump-gap/debt line (devdoc 163)")
    assert "AUDIO_PUMP_TRACE_GAP_MS" in body, (
        "the [AP] trace must threshold on the audible-stall gap")
    assert "#define AUDIO_PUMP_TRACE 1" in c, (
        "AUDIO_PUMP_TRACE must default to ON (devdoc 163 Phase 1)")


def test_vc_trace_carries_the_wall_clock():
    """devdoc 163 Phase 1: the [VC] line must include the wall clock (w=) so
    the long-run music-time debt (w - v) is readable from a serial capture."""
    c = HAL_PC98_C.read_text(encoding="utf-8")
    assert "[VC] v=%lu w=%lu step=%lu tgt=%lu cal=%d" in c, (
        "[VC] must include the wall clock (devdoc 163 Phase 1 debt metric)")


def test_irq_probe_is_gated_and_safe():
    """devdoc 163 Phase 3 C1: the GDC vsync IRQ probe must be compile-gated
    (NAIZ_IRQ_PROBE default 0) with its boot call site under the same gate —
    a default build pays nothing and cannot pick up a 2s busy-wait.  The
    probe must sample the PIC IRR only: never touch the mask (IMR write) and
    never hook a vector."""
    h = HAL_H.read_text(encoding="utf-8")
    assert "#define NAIZ_IRQ_PROBE 0" in h, (
        "NAIZ_IRQ_PROBE must default to 0 (probe compiled out by default)")
    assert "void hal_irq_probe_run(void);" in h
    c = HAL_PC98_C.read_text(encoding="utf-8")
    assert "#if NAIZ_IRQ_PROBE" in c, "the probe body must be compile-gated"
    assert "[IRQP] vsync irq2 hits=%lu samples=%lu imr=%02lx" in c, (
        "the probe must log [IRQP] hits/samples/imr (devdoc 163 C1)")
    body = _func_body(c, "hal_irq_probe_run")
    assert "outb(0x00, 0x0A)" in body, (
        "the probe must select IRR via OCW3 before sampling")
    assert "0x64" in body, "the probe must arm the GDC via port 0x64"
    assert "0x0205" not in body and "0x31" not in body, (
        "the probe must not hook vectors / call DPMI (IMR- and vector-neutral "
        "by design, devdoc 163 C1)")
    main = MAIN_C.read_text(encoding="utf-8")
    assert "#if NAIZ_IRQ_PROBE" in main and "hal_irq_probe_run();" in main, (
        "main.c must call the probe under the NAIZ_IRQ_PROBE gate")


def test_audio_tick_does_not_block_on_vblank():
    """devdoc 133: the periodic vblank yield (devdoc 131 方案 A) was removed --
    it hitched the main loop every ~0.8s on NP2kai's ~20Hz pass rate, and the
    decode path's frames are now kept flowing by frame_decode_pump() instead
    (which is non-blocking).  audio_tick() must never wait a full frame."""
    body = _func_body(AUDIO_C.read_text(encoding="utf-8"), "audio_tick")
    assert "hal_vblank_wait()" not in body, (
        "audio_tick() must not block on a vblank wait (devdoc 133 removed A)")
    assert "vblank_wait()" not in body, "audio_tick() must stay non-blocking"
    c = AUDIO_C.read_text(encoding="utf-8")
    assert "AUDIO_YIELD_EVERY" not in c, "the rate-limited yield was removed"
    assert "g_audio_yield_ctr" not in c, "the yield counter was removed"


def test_hal_exposes_a_vblank_edge_probe():
    """The decode pump's non-blocking edge detector must live in the HAL, and
    the blocking wait must keep its baseline fresh so pump + poll cannot
    double-count a frame."""
    h = HAL_H.read_text(encoding="utf-8")
    assert "int hal_vblank_poll(void)" in h, (
        "hal.h must declare hal_vblank_poll() (devdoc 131 方案 B)")
    c = HAL_PC98_C.read_text(encoding="utf-8")
    body = _func_body(c, "hal_vblank_poll")
    assert "GDC_VSYNC" in body and "return (prev == 0 && now == 1)" in body, (
        "hal_vblank_poll() must return exactly one rising edge per frame")
    wait = _func_body(c, "hal_vblank_wait")
    assert "g_vs_level = 1" in wait, (
        "hal_vblank_wait() must refresh the poll baseline to the asserted "
        "level, so a blocking pump and a polling decode do not double-count")


# --- 5. image-cache prefetch (devdoc 131 方案 D) ---------------------------

def test_image_prefetch_warms_cache_without_palette():
    """image_prefetch() must decode into the cache but NOT change the active
    palette (it runs during dialogue, before the image is shown) and must not
    leak a caller reference."""
    h = IMAGE_H.read_text(encoding="utf-8")
    assert "int image_prefetch(unsigned short id)" in h, (
        "image.h must declare image_prefetch() (devdoc 131 方案 D)")
    body = _func_body(IMAGE_C.read_text(encoding="utf-8"), "image_prefetch")
    assert "image_cache_lookup" in body and "image_cache_insert" in body, (
        "image_prefetch() must early-out on a cache hit and insert on miss")
    assert "image_set_palette" not in body, (
        "image_prefetch() must not touch the active palette")
    assert "image_cache_pin(" in body, (
        "image_prefetch() must pin the new slot so it is not evicted first "
        "(devdoc 133 方案 D)")


def test_image_cache_pin_lifts_the_hit_floor():
    """image_cache_pin() must raise a cached slot's hit floor (a freshly
    prefetched image has hits 0 and would be the first evicted)."""
    c = IMAGE_CACHE_C.read_text(encoding="utf-8")
    body = _func_body(c, "image_cache_pin")
    assert "IMAGE_CACHE_PREFETCH_HITS" in body, (
        "the pin must use a named hit floor")
    assert "hits" in body and "return" in body, "the pin must update the slot"
    h = (ROOT / "core" / "engine" / "image_internal.h").read_text(encoding="utf-8")
    assert "void image_cache_pin(int id)" in h, "image_internal.h must declare it"


def test_nb_warms_cache_while_parked_on_a_dialogue_page():
    """devdoc 133: the lookahead must run from main.c's three loops on every
    pass (a SINGLE-page line sets text_offset = -1 and never reached the old
    paged-only call site, so the common case was never prefetched).  The nb.c
    dialogue branch keeps its call; the done_pc guard keeps it cheap."""
    src = NB_C.read_text(encoding="utf-8")
    assert "nb_prefetch_lookahead()" in src, "the prefetch helper is missing"
    assert "NB_PREFETCH_LOOKAHEAD" in src, "the prefetch window must be bounded"
    body = _func_body(src, "nb_prefetch_lookahead")
    assert "done_pc == nb.pc" in body, (
        "prefetch must run at most once per script position (no per-frame "
        "rescan)")
    assert "nb_prefetch_key" in body, (
        "prefetch must resolve keys via nb_prefetch_key(), not ad-hoc parsing")
    # The idle branch that shows a dialogue page must call it.
    proc = _func_body(src, "nb_process")
    assert "dialog_show(" in proc and "nb_prefetch_lookahead();" in proc, (
        "nb_process() must warm the cache when it parks on a dialogue page")
    # Every main.c loop must call it after the pump (3 sites: AUTOEXIT, main,
    # and the input-wait inner loop).
    main = MAIN_C.read_text(encoding="utf-8")
    assert main.count("nb_prefetch_lookahead();") == 3, (
        "main.c must call nb_prefetch_lookahead() from all three loops")
    assert len(re.findall(
        r"engine_frame_pump\(\);[^\n]*\n\s*nb_prefetch_lookahead\(\);", main)) == 3, (
        "the prefetch must follow the frame pump in every loop")


def test_prefetch_key_resolves_the_display_commands():
    """nb_prefetch_key() must resolve cg (cg_map), bg (asset map incl. SPR) and
    char (with the command's expression argument, devdoc 133), and reject
    everything else."""
    cmd_c = (ROOT / "core" / "engine" / "nb_commands.c").read_text(encoding="utf-8")
    fn = _func_body(cmd_c, "nb_prefetch_key")
    assert 'strcmp(cmd, "cg")' in fn and "cg_map" in fn, "cg must use cg_map"
    assert 'strcmp(cmd, "bg")' in fn and "nb_asset_id" in fn, "bg must use nb_asset_id"
    assert 'strcmp(cmd, "char")' in fn and "resolve_expr(cid," in fn, (
        "char must resolve via resolve_expr()")
    assert '"normal"' in fn and "expr" in fn.split("resolve_expr", 1)[1], (
        "char must use the passed expression, falling back to 'normal'")
    assert "nb_prefetch_key(const char *cmd, const char *key, const char *expr)" in cmd_c, (
        "the signature must take the char expression argument (devdoc 133)")
    assert "return -1;" in fn, "unknown commands must resolve to -1"
    # nb.c must pass the same expression cmd_char derives.
    nb = NB_C.read_text(encoding="utf-8")
    assert "nb_prefetch_key(cmd, args[brace]," in nb and '(argc >= 3) ? args[1] : "normal"' in nb, (
        "nb.c must pass the char expression to nb_prefetch_key()")
