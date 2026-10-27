/*
 * audio.c — Engine audio manager: MIDI BGM scheduling + 86-board PCM pump.
 *
 * Devdoc 101 + 123:
 *   - BGM: .mid read from AUDIO.DAT, parsed into a resident event table
 *     (lib/midi), then streamed either to the MPU-401 UART as real-time
 *     bytes on the 60Hz tick (hal_midi_out) or, when no MPU-401 is present
 *     and an OPNA answers on 0x188-0x18E, rendered into OPNA registers by
 *     lib/fmseq (devdocs/123 M4).  Positioned by hal_wallclock_smooth_ms().
 *   - sound/voice: .pcm (8bit mono) read from AUDIO.DAT and pushed into
 *     the 86-board FIFO on the same tick (hal_pcm_*).  SE and voice share
 *     one mono channel; a later play replaces the current one.
 *   - No MPU board / no archive / unregistered key degrade to a logged
 *     no-op (legacy stub behaviour), never touching registers.
 */
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#include "hal.h"
#include "farchive.h"
#include "strutil.h"
#include "midi.h"
#include "fmopn.h"
#include "fmseq.h"
#include "mag.h"
#include "audio.h"
#include "nb_asset_table.h"

#define AUDIO_ARCHIVE "AUDIO.DAT"
#define AUDIO_MAX_ENTRIES 8192    /* TOC cap, mirrors IMAGE.DAT usage */
#define PCM_HDR_SIZE 16           /* "NAIZPCM" + rate + flags + reserved */

/* devdoc 164 phase 1: with the Timer-B ISR pumping audio_tick() from interrupt
 * context, the main thread must not mutate BGM state mid-flight.  These bracket
 * the state-commit windows so the handler cannot observe a half-swapped event
 * table.  Compiles to nothing when the interrupt pump is off (default), so the
 * co-operative build is unchanged. */
#if NAIZ_BGM_IRQ
#include <i86.h>
/* The engine never takes this lock with interrupts already disabled, so
 * disable on the outermost entry / enable on the outermost exit is correct.
 *
 * devdoc 167: it must also be RE-ENTRANT.  fm_sink_write() takes the lock
 * around every OPNA byte pair, and fmseq_stop() (called from inside
 * audio_bgm_start()/audio_bgm_stop()'s own critical section) drives it.  With
 * a flat disable/enable pair the inner unlock re-enabled interrupts in the
 * middle of the outer window, so the Handler could run while the event table
 * and the voice state were still being swapped.  Depth-count instead.
 *
 * In ISR context this is a pure no-op: the handler already runs with IF
 * cleared, and calling _enable() there would let it re-enter itself
 * (devdoc 166). */
static int g_irq_lock_depth;

static void bgm_irq_lock(void)
{
    if (hal_bgm_irq_in_isr()) return;
    if (g_irq_lock_depth++ == 0)
        _disable();
}
static void bgm_irq_unlock(void)
{
    if (hal_bgm_irq_in_isr()) return;
    if (g_irq_lock_depth > 0 && --g_irq_lock_depth == 0)
        _enable();
}
#else
#define bgm_irq_lock()   ((void)0)
#define bgm_irq_unlock() ((void)0)
#endif

/*=== Archive ============================================================*/

static FArchive g_arc;
static int g_arc_ok;              /* AUDIO.DAT opened successfully */
static int g_mpu_ok;              /* MPU-401 present (hal_audio_detect) */
static int g_fm_ok;               /* OPNA present (hal_fm_detect) */

/*=== BGM (MIDI / FM) ===================================================*/

typedef struct {
    MidEvent     *ev;             /* parsed event table (resident) */
    int           count;
    int           idx;            /* next event to fire (MIDI backend) */
    unsigned long wall0;          /* hal_wallclock_smooth_ms() at pass start */
    unsigned long len_ms;         /* song length incl. trailing silence (A1) */
    int           fm;             /* 1: rendered by fmseq on the OPNA */
    int           active;
    int           rewound;        /* ISR set a loop; frame path logs it (B3) */
} BgmState;

static BgmState g_bgm;

/* Player switches (devdoc 118).  Defaults are on: preserving the pre-0.3.011
 * behaviour means a missing USER.CFG plays everything. */
static int g_bgm_on = 1;
static int g_snd_on = 1;
static int g_vc_on = 1;

/* BGM volume as MIDI CC7, 0-127.  127 == full == 0x7F in the SMF stream. */
#define AUDIO_BGM_VOL_MAX  127
static int g_bgm_vol = AUDIO_BGM_VOL_MAX;

/* Per-pass dispatch cap for the MIDI backend: bounds how many events one
 * audio_tick() may send to the MPU-401, so a large clock jump is spread over
 * several frames instead of flushing a whole backlog in one pass (devdoc 147
 * A3).  Generous enough that steady playback (0-1 events per frame) is
 * unaffected.  The FM backend caps internally via FMSEQ_PUMP_MAX_PER_CALL. */
#define AUDIO_BGM_MAX_EVENTS_PER_TICK 32

/* devdoc 150 opt-in dispatch trace.  Logs each BGM note dispatch with its
 * virtual-clock timestamp so a recording's timing can be attributed to the
 * frame-pump quantization (axis A) rather than to voicing/LFO (axes B/C).
 * Off by default: zero cost, zero output.  Enable with
 *   make -C core EXTRA_DEFS=-DBGM_TICK_TRACE=1
 * and capture with makegame.sh test --serial. */
#ifndef BGM_TICK_TRACE
#define BGM_TICK_TRACE 0
#endif

/* devdoc 163 Phase 1 pump-gap + music-time-debt trace.  audio_tick() is the
 * only pump for fmseq/PCM, so the gap between two of its calls is exactly
 * how long the BGM was starved; the debt (wall clock minus virtual clock) is
 * what the stall cost musically.  On by default like the [VC] trace: it only
 * emits when a gap exceeds AUDIO_PUMP_TRACE_GAP_MS, so a healthy loop is
 * silent.  Compile out with
 *   make -C core EXTRA_DEFS=-DAUDIO_PUMP_TRACE=0 */
#ifndef AUDIO_PUMP_TRACE
#define AUDIO_PUMP_TRACE 1
#endif
/* Audible-stall threshold in ms: a shorter gap between pumps is not heard
 * as a pause, so it is not worth a serial line. */
#define AUDIO_PUMP_TRACE_GAP_MS 150UL

/* PCM attenuation 0-15 (0 = loudest, 15 = softest).  Mirrors the A466 bit
 * layout; see F02 §4.2.  Distinct from AUDIO_PCM_VOL_DEFAULT so the two
 * units can never be confused at a call site. */
#define AUDIO_PCM_ATTEN_MAX  15
static int g_pcm_vol = 0;

/* Free any current BGM event table.  midi_free(NULL) is safe. */
static void bgm_release(void)
{
    if (g_bgm.ev) {
        midi_free(g_bgm.ev);
        g_bgm.ev = NULL;
    }
    g_bgm.count = 0;
    g_bgm.idx = 0;
    g_bgm.len_ms = 0;
    g_bgm.fm = 0;
    g_bgm.active = 0;
}

/*=== BGM (FM backend, devdocs/123 M4) ===================================*/

/* Patch family table capacity.  Content design is a separate devdoc (S6);
 * this S5 wiring only guarantees a wired audible default. */
#define FM_FAMILY_MAX  16
static FmopnPatch g_fm_patches[FM_FAMILY_MAX];
static int g_fm_families;
static Fmseq *g_fm_seq;           /* opaque; allocated at init (fmseq_size) */
static FmseqSink g_fm_sink;

/* Built-in fallback patch: one loud fast-attack/release family so a project
 * with no FMP assets still plays (devdocs/123 §1.5 判据 1).  Replaces the
 * patch table entirely when every FMP asset fails or none exists. */
static const FmopnPatch g_fm_default_patch = {
    {   /* op1 */ 0x08, 0x00, 0x1F, 0x00, 0x00, 0x0F,
        /* op2 */ 0x08, 0x00, 0x1F, 0x00, 0x00, 0x0F,
        /* op3 */ 0x08, 0x00, 0x1F, 0x00, 0x00, 0x0F,
        /* op4 */ 0x08, 0x00, 0x1F, 0x00, 0x00, 0x0F,
        /* FB<<3|AL */ 0x01,
        /* pan L+R */  0xC0,
        /* reserved */ 0, 0, 0, 0, 0, 0 }
};

/* fmseq emits register writes here.  bank 0/1 route to the ordinary /
 * extended OPNA port pairs (F03 §3.8). */
static void fm_sink_write(void *ctx, int bank, uint8_t reg, uint8_t val)
{
    (void)ctx;
#if BGM_TICK_TRACE
    /* $28 with a non-zero slot mask is a key-on: one per FM note attack.
     * devdoc 150. */
    if (bank == 0 && reg == 0x28 && (val & 0xF0))
        hal_logf("BGMT on t=%lu ch=%d\n",
                 (unsigned long)hal_wallclock_smooth_ms(), val & 0x03);
#endif
#if NAIZ_BGM_IRQ
    /* Serialize with the main thread: OPNA port pairs are not safe to
     * interleave between ISR and non-ISR contexts (devdoc 166). */
    if (hal_bgm_irq_active()) {
        bgm_irq_lock();
        hal_fm_write_reg(bank, reg, val);
        bgm_irq_unlock();
        return;
    }
#endif
    hal_fm_write_reg(bank, reg, val);
}

/* GM programs without a patch family are a loud log + fall back to family
 * 0 (never a silent mapping; AGENTS §九.6). */
static void fm_unmapped(void *ctx, int midi_ch, int program, int def_family)
{
    (void)ctx;
    hal_logf("FM: program %d on channel %d unmapped -> family %d\r\n",
             program, midi_ch, def_family);
}

/* Load the project's FMP patch families from AUDIO.DAT (id order ==
 * fmp_map order == AUDIO.DAT order).  Every fmp_map entry owns a FIXED
 * family slot: fmp_gm_map[] stores family indices positionally into
 * g_fm_patches[], so a missing/invalid/dummy entry must leave the built-in
 * default in its slot — never be skipped, which would shift every later
 * family down by one and silently reroute all higher GM programs (e.g.
 * program 73 -> flute would land on the next family instead). */
static void fm_load_patches(void)
{
    const AudioAssetMap *m;
    int n = 0;

    for (m = fmp_map; m->name != NULL; m++) {
        long off = 0, size = 0;
        char k8[9];

        if (n >= FM_FAMILY_MAX)
            break;

        g_fm_patches[n] = g_fm_default_patch;   /* placeholder for this slot */

        if (strcmp(m->name, "__dummy__") != 0) {
            str_toc8(k8, sizeof k8, m->name);
            if (farchive_lookup_name(&g_arc, k8, &off, &size, NULL) != 0) {
                hal_logf("FM WARN: patch '%s' missing in %s; family %d "
                         "uses default\r\n", m->name, AUDIO_ARCHIVE, n);
            } else if (size != FMOPN_PATCH_BYTES) {
                hal_logf("FM WARN: patch '%s' has %ld bytes, need %d; "
                         "family %d uses default\r\n", m->name, size,
                         FMOPN_PATCH_BYTES, n);
            } else {
                uint8_t *raw = farchive_read_alloc(&g_arc, off, size, NULL);
                if (!raw) {
                    hal_logf("FM WARN: read patch '%s' failed; family %d "
                             "uses default\r\n", m->name, n);
                } else {
                    memcpy(g_fm_patches[n].data, raw, FMOPN_PATCH_BYTES);
                    free(raw);
                    if (fmopn_patch_validate(&g_fm_patches[n]) != 0) {
                        hal_logf("FM WARN: patch '%s' fails validation; "
                                 "family %d uses default\r\n", m->name, n);
                        g_fm_patches[n] = g_fm_default_patch;
                    }
                }
            }
        }
        n++;
    }

    if (n == 0) {
        g_fm_patches[0] = g_fm_default_patch;
        n = 1;
        hal_log("FM: no valid FMP patches, using built-in default\r\n");
    }
    g_fm_families = n;
    hal_logf("FM: %d patch famil%s ready\r\n", n, n == 1 ? "y" : "ies");
}

/* Compile-time registry check (ASSETS.DB) for one audio asset map. */
static int audio_map_find(const AudioAssetMap *map, const char *key)
{
    for (; map->name != NULL; map++)
        if (strcmp(map->name, key) == 0)
            return map->id;
    return -1;
}

/* Push CC7 (channel volume) to all 16 channels on the MIDI backend, or
 * write the OPNA VOL1 attenuation on the FM backend (F02 §4.2: each A466
 * path has its own 4-bit attenuation, so VOL1 and VOL6 do not overwrite
 * each other — no unified entry needed).  Reuses the all-16-channel shape
 * of audio_bgm_stop. */
static void bgm_apply_volume(void)
{
    int ch;
#if NAIZ_BGM_IRQ
    int locked = 0;
#endif
    int atten;

    if (g_bgm.fm) {
#if NAIZ_BGM_IRQ
        locked = (g_fm_ok && hal_bgm_irq_active());
        if (locked) bgm_irq_lock();
#endif
        atten = (g_bgm_vol * 15) / AUDIO_BGM_VOL_MAX;
        hal_fm_set_volume(15 - atten);   /* reversed 0(loud)..15(quiet) */
#if NAIZ_BGM_IRQ
        if (locked) bgm_irq_unlock();
#endif
        return;
    }
    if (!g_mpu_ok) return;
    for (ch = 0; ch < 16; ch++) {
        hal_midi_out((uint8_t)(0xB0 + ch));
        hal_midi_out(0x07);
        hal_midi_out((uint8_t)g_bgm_vol);
    }
}

void audio_bgm_start(const char *key)
{
    long off, size;
    uint8_t *raw;
    MidEvent *ev;
    int count = 0;
    uint32_t len_ms = 0;

    /* devdoc 167: do NOT hold the ISR lock across the file read + MIDI parse.
     * That window is tens of milliseconds of blocking archive I/O, and masking
     * the Timer-B for its whole length is itself an audible BGM stall.  The
     * lock now covers only the state commit below; every early return here
     * leaves interrupts untouched. */
    if (!key || !key[0]) return;
    if (!g_bgm_on) {
        hal_logf("BGM WARN: '%s' ignored (BGM disabled)\r\n", key);
        return;
    }
    if (!g_mpu_ok && !g_fm_ok) {
        hal_logf("BGM WARN: '%s' ignored (no audio backend)\r\n", key);
        return;
    }
    if (!g_arc_ok) {
        hal_logf("BGM WARN: '%s' ignored (no %s)\r\n", key, AUDIO_ARCHIVE);
        return;
    }
    if (audio_map_find(bgm_map, key) < 0) {
        hal_logf("BGM WARN: '%s' is not a registered BGM asset\r\n", key);
        return;
    }
    {
        char k8[9];
        str_toc8(k8, sizeof k8, key);
        if (farchive_lookup_name(&g_arc, k8, &off, &size, NULL) != 0) {
            hal_logf("BGM WARN: '%s' missing in %s\r\n", key, AUDIO_ARCHIVE);
            return;
        }
    }
    raw = farchive_read_alloc(&g_arc, off, size, NULL);
    if (!raw) {
        hal_logf("BGM WARN: read '%s' failed\r\n", key);
        return;
    }
    if (midi_parse(raw, (uint32_t)size, &ev, &count, &len_ms) != 0) {
        hal_logf("BGM WARN: parse '%s' failed\r\n", key);
        free(raw);
        return;
    }
    free(raw);   /* event table is independently owned by midi_parse */

    /* An empty/zero-length stream loops forever; treat as no BGM. */
    if (count <= 0 || len_ms == 0) {
        hal_logf("BGM WARN: '%s' has no playable events\r\n", key);
        midi_free(ev);
        return;
    }

    /* Cut any still-sounding FM voices from the previous BGM before swapping
     * the event table: a mid-scene bgm(){key} while a song plays would
     * otherwise leave the old voices ringing under the new one and keep the
     * per-voice ages stale (scene_switch covers the common path via
     * audio_stop_all, but this start must be safe on its own, devdoc 157).
     * devdoc 164: hold off the ISR across the FM touch + state commit. */
    bgm_irq_lock();
    if (g_fm_ok)
        fmseq_stop(g_fm_seq, &g_fm_sink);
    bgm_release();
    g_bgm.ev = ev;
    g_bgm.count = count;
    g_bgm.idx = 0;
    g_bgm.len_ms = len_ms;
    g_bgm.wall0 = hal_wallclock_smooth_ms();
    g_bgm.active = 1;
    if (g_mpu_ok) {
        g_bgm.fm = 0;   /* MIDI is the preferred backend when a card is present */
    } else {
        g_bgm.fm = 1;
        fmseq_events(g_fm_seq, ev, count);
    }
    bgm_apply_volume();
    bgm_irq_unlock();
    hal_logf("BGM start '%s' (%d events, %lums)%s\r\n", key, count,
             (unsigned long)len_ms, g_bgm.fm ? " (FM)" : "");
}

void audio_bgm_stop(void)
{
    bgm_irq_lock();   /* devdoc 164: no ISR pump while we tear the voices down */
    if (g_bgm.fm && g_fm_ok) {
        /* fmseq_stop keyoffs every sounding voice and silences the SSG. */
        fmseq_stop(g_fm_seq, &g_fm_sink);
    } else if (g_mpu_ok) {
        int ch;
        /* All-Notes-Off on all 16 channels, then drop the event table. */
        for (ch = 0; ch < 16; ch++) {
            hal_midi_out((uint8_t)(0xB0 + ch));
            hal_midi_out(0x7B);
            hal_midi_out(0x00);
        }
    }
    bgm_release();
    bgm_irq_unlock();
    hal_log("BGM stop\r\n");
}

/*=== PCM (sound/voice, shared channel) ==================================*/

static uint8_t *g_pcm_buf;        /* owned container; freed on release */

/* Which channel currently owns the shared PCM path (devdoc 118).  snd and
 * voice share one mono channel, so turning one off must not cut the other:
 * a release is issued only when the disabled channel is the current owner. */
#define PCM_CH_NONE 0
#define PCM_CH_SND  1
#define PCM_CH_VC   2
static int g_pcm_channel;

static void pcm_release(void)
{
    /* devdoc 165: the ISR pumps the PCM FIFO (hal_pcm_advance_units) and the frame path
     * may release here -- the stop + buffer swap must be atomic against it. */
    bgm_irq_lock();
    hal_pcm_stop();
    if (g_pcm_buf) {
        free(g_pcm_buf);
        g_pcm_buf = NULL;
    }
    g_pcm_channel = PCM_CH_NONE;
    bgm_irq_unlock();
}

/* 'chan' is PCM_CH_SND / PCM_CH_VC, recorded on every successful play. */
static void pcm_play(const AudioAssetMap *map, const char *key, int chan)
{
    long off, size;
    uint8_t *raw;
    uint8_t rate;

    if (!key || !key[0]) return;
    if (!g_arc_ok) {
        hal_logf("PCM WARN: '%s' ignored (no %s)\r\n", key, AUDIO_ARCHIVE);
        return;
    }
    if (audio_map_find(map, key) < 0) {
        hal_logf("PCM WARN: '%s' is not a registered audio asset\r\n", key);
        return;
    }
    {
        char k8[9];
        str_toc8(k8, sizeof k8, key);
        if (farchive_lookup_name(&g_arc, k8, &off, &size, NULL) != 0) {
            hal_logf("PCM WARN: '%s' missing in %s\r\n", key, AUDIO_ARCHIVE);
            return;
        }
    }
    raw = farchive_read_alloc(&g_arc, off, size, NULL);
    if (!raw) {
        hal_logf("PCM WARN: read '%s' failed\r\n", key);
        return;
    }
    if (size < PCM_HDR_SIZE || memcmp(raw, "NAIZPCM", 8) != 0) {
        hal_logf("PCM WARN: '%s' bad .pcm header\r\n", key);
        free(raw);
        return;
    }
    rate = raw[8];
    if (rate > 7) {
        hal_logf("PCM WARN: '%s' rate code %u out of range\r\n", key, rate);
        free(raw);
        return;
    }

    /* Replace current stream.  hal_pcm_play rebinds its borrow instantly,
     * so the old buffer is free to release straight after.  One-shot:
     * SE/voice never loop (loop=0), per devdoc 101 §4.3 caller semantics.
     * The rebind + buffer swap is atomic against the ISR PCM tick (devdoc
     * 165): without the lock an IRQ landing mid-swap could tick a buffer we
     * are about to free. */
    bgm_irq_lock();
    hal_pcm_play(raw + PCM_HDR_SIZE, (uint32_t)(size - PCM_HDR_SIZE), rate, 0);
    free(g_pcm_buf);
    g_pcm_buf = raw;
    g_pcm_channel = chan;
    bgm_irq_unlock();
    hal_logf("PCM start '%s' (%ld B, rate %u)\r\n", key, size - PCM_HDR_SIZE, rate);
}

void audio_snd_play(const char *key)
{
    if (!g_snd_on) {
        hal_logf("PCM WARN: '%s' ignored (sound effects disabled)\r\n", key);
        return;
    }
    pcm_play(snd_map, key, PCM_CH_SND);
}

void audio_vc_play(const char *key)
{
    if (!g_vc_on) {
        hal_logf("PCM WARN: '%s' ignored (voice disabled)\r\n", key);
        return;
    }
    pcm_play(voice_map, key, PCM_CH_VC);
}

/*=== Player switches and volume (devdoc 118) ==============================*/

/* Cut the shared PCM path only when the disabled channel owns it, so
 * switching sound effects off mid-voice leaves the voice playing. */
static void pcm_disable(int chan)
{
    if (g_pcm_channel == chan)
        pcm_release();
}

void audio_set_bgm_enabled(int on)
{
    int want = on ? 1 : 0;

    if (want == g_bgm_on) return;
    g_bgm_on = want;
    if (!want)
        audio_bgm_stop();
    hal_logf("AUD bgm %s\r\n", want ? "on" : "off");
}

void audio_set_snd_enabled(int on)
{
    int want = on ? 1 : 0;

    if (want == g_snd_on) return;
    g_snd_on = want;
    if (!want)
        pcm_disable(PCM_CH_SND);
    hal_logf("AUD snd %s\r\n", want ? "on" : "off");
}

void audio_set_vc_enabled(int on)
{
    int want = on ? 1 : 0;

    if (want == g_vc_on) return;
    g_vc_on = want;
    if (!want)
        pcm_disable(PCM_CH_VC);
    hal_logf("AUD vc %s\r\n", want ? "on" : "off");
}

int audio_get_bgm_enabled(void) { return g_bgm_on; }
int audio_get_snd_enabled(void) { return g_snd_on; }
int audio_get_vc_enabled(void) { return g_vc_on; }

void audio_set_bgm_volume(int v)
{
    if (v < 0) v = 0;
    if (v > AUDIO_BGM_VOL_MAX) v = AUDIO_BGM_VOL_MAX;
    if (v == g_bgm_vol) return;
    g_bgm_vol = v;
    /* Immediate effect: CC7 is applied live, no restart needed. */
    bgm_apply_volume();
    hal_logf("AUD bgm volume %d\r\n", v);
}

void audio_set_pcm_volume(int step)
{
    if (step < 0) step = 0;
    if (step > AUDIO_PCM_ATTEN_MAX) step = AUDIO_PCM_ATTEN_MAX;
    g_pcm_vol = step;
    hal_pcm_set_volume(step);
    hal_logf("AUD pcm volume %d\r\n", step);
}

int audio_get_bgm_volume(void) { return g_bgm_vol; }
int audio_get_pcm_volume(void) { return g_pcm_vol; }

/*=== Lifecycle ==========================================================*/

void audio_tick(void);
/* devdoc 165: ISR-safe pump core -- no DOS clock read, no hal_logf, no free.
 * The Timer-B handler advances the virtual clock then calls this. */
void audio_tick_isr(unsigned long delta_units);
/* devdoc 131 方案 B: the MAG decode progress hook runs one decode-time frame
 * step (advance clock on vblank edge + pump audio) instead of a bare
 * audio_tick(), so a long decode no longer freezes the BGM schedule. */
void frame_decode_pump(void);

void audio_init(void)
{
    mag_set_progress_hook(frame_decode_pump);
    if (farchive_open(&g_arc, AUDIO_ARCHIVE, AUDIO_MAX_ENTRIES) != 0) {
        hal_logf("AUD WARN: no %s (audio disabled)\r\n", AUDIO_ARCHIVE);
        g_arc_ok = 0;
        g_mpu_ok = 0;
        g_fm_ok = 0;
        return;
    }
    if (g_arc.truncated)
        hal_logf("AUD WARN: %s TOC truncated to %d entries\r\n",
                 AUDIO_ARCHIVE, AUDIO_MAX_ENTRIES);
    g_arc_ok = 1;

    g_mpu_ok = hal_audio_detect();
    if (g_mpu_ok)
        hal_log("AUD MPU OK\r\n");

    /* FM backend (devdocs/123 §8.1): OPNA based, only engaged when no
     * MPU-401 is present.  Init must raise A460 bit0 first or the extended
     * window 0x18C/0x18E never routes (F03 §3.8 fact 1). */
    g_fm_ok = hal_fm_detect();
    if (g_fm_ok) {
        hal_log("AUD OPNA OK\r\n");
        hal_fm_init();
        fm_load_patches();
        g_fm_sink.ctx = NULL;
        g_fm_sink.write = fm_sink_write;
        g_fm_seq = malloc(fmseq_size());
        if (g_fm_seq) {
            fmseq_init(g_fm_seq, g_fm_patches, g_fm_families,
                       fmp_gm_map, fm_unmapped, NULL);
        } else {
            g_fm_ok = 0;   /* nothing to render BGM on; PCM keeps working */
            hal_log("AUD WARN: no memory for FM backend\r\n");
        }
#if NAIZ_BGM_IRQ
        /* devdoc 164 phase 1: hand the BGM beat to the OPNA Timer-B ISR so a
         * long CPU-bound pass can no longer starve it.  Only attempted once
         * the FM backend is up; a failed install logs and the co-operative
         * pump keeps running (frame.c checks hal_bgm_irq_active()). */
        if (g_fm_ok) {
            int irq_ok = hal_bgm_irq_init();
            if (!irq_ok)
                hal_log("BGM IRQ install failed; co-operative pump stays active\r\n");
            else
                hal_log("BGM IRQ: scanning FM IRQ line; co-operative pump stays active\r\n");
        }
#endif
    }

    if (!g_mpu_ok && !g_fm_ok)
        hal_log("AUD WARN: no audio backend (MPU-401 absent, no OPNA)\r\n");
}

/* Advance the loop start to the next whole song boundary, preserving musical
 * phase (devdoc 147 A2).  The old code reset wall0 to the current clock, which
 * dropped the (cur - len_ms) remainder every loop.  The arithmetic lives in
 * fmseq_loop_start() so it is host-testable; g_bgm.len_ms is non-zero for any
 * active BGM (audio_bgm_start rejects zero-length streams). */
static void bgm_rewind_phase(unsigned long now)
{
    g_bgm.wall0 = (unsigned long)fmseq_loop_start(g_bgm.wall0,
                                                  g_bgm.len_ms, now);
}

/* ISR-safe audio core (devdoc 165 §四 B3/B4).  No DOS call (the caller must
 * not read the platform clock here), no hal_logf, no free: a hardware handler
 * may only touch the OPNA/PCM ports and the sequence state.  The clock must be
 * advanced by the caller before this runs. */
void audio_tick_isr(unsigned long delta_units)
{
    unsigned long now = hal_wallclock_smooth_ms();  /* FM scheduling only; PCM uses delta_units */
    unsigned long cur;
    /* devdoc 167: the PCM pump is sized by the real time this tick covers, so
     * it must not push a fixed burst.  The caller has already advanced the
     * virtual clock, so its millisecond delta is exactly that span. */
    unsigned long pcm_units;
    /* devdoc 168: PCM pump sized by the fixed clock step (units, not ms),
     * so the virtual-clock rate is exactly the hardware timer rate (258 units
     * per tick at NB=200 / φM=7.9872 MHz). No virtual-clock read needed. */
    pcm_units = delta_units;
    if (pcm_units == 0 || pcm_units > 258UL * 4)
        pcm_units = 258UL;  /* default tick at 60Hz-equivalent rate; guard overflow */

    /* PCM push first.  hal_pcm_advance_units stops the channel at EOF but
     * does NOT free the buffer here (free() is not ISR-safe). */
    hal_pcm_advance_units(pcm_units);

    if (!g_bgm.active) return;

    if (g_bgm.fm) {
        cur = now - g_bgm.wall0;

        fmseq_pump(g_fm_seq, &g_fm_sink, cur);
        if (cur >= g_bgm.len_ms && fmseq_finished(g_fm_seq)) {
            /* Rewind preserves phase (devdoc 147 A2).  The "voices still
             * ringing" note is deferred to the frame path -- logging is not
             * ISR-safe (devdoc 165 B3).  The ISR only raises the flag. */
            fmseq_stop(g_fm_seq, &g_fm_sink);
            bgm_rewind_phase(now);
            g_bgm.rewound = 1;
        }
        return;
    }

    {
        int budget;
        cur = now - g_bgm.wall0;
        budget = AUDIO_BGM_MAX_EVENTS_PER_TICK;

        while (budget > 0 && g_bgm.idx < g_bgm.count &&
               g_bgm.ev[g_bgm.idx].tick_ms <= cur) {
            const MidEvent *e = &g_bgm.ev[g_bgm.idx];
            uint8_t st = e->b0;

            hal_midi_out(st);
            hal_midi_out(e->b1);
            if ((st & 0xF0) != 0xC0 && (st & 0xF0) != 0xD0)
                hal_midi_out(e->b2);
            g_bgm.idx++;
            budget--;
        }

        if (g_bgm.idx >= g_bgm.count && cur >= g_bgm.len_ms) {
            g_bgm.idx = 0;
            bgm_rewind_phase(now);
        }
    }
}

/* Drain the clock units the Timer-B handler accumulated since the last frame
 * and run one engine pump for them, on the MAIN thread's stack (devdoc 176).
 *
 * Why the pump cannot run inside the handler: DOS/4GW delivers the IRQ on its
 * own stack segment (SS=0x00B0 on this build) while the flat data selector is
 * DS=0x0160.  Engine code that writes through a pointer to a *stack* local --
 * fmopn_reg_addr()'s bank/addr out-params are the fatal example -- then lands
 * at the wrong linear address, the caller reads a stale value, and every FM
 * register write goes out as address 0x00 (silent BGM) plus a stray store into
 * low memory.  The handler now only advances the clock and bumps the counter;
 * everything that touches the OPNA happens here, where SS == DS. */
void audio_tick_isr_pending(void)
{
    unsigned long units = hal_bgm_irq_take_pending_units();

    if (units == 0)
        return;
    audio_tick_isr(units);
}

/* Called from the 60Hz heartbeat every frame (AUTOEXIT, main and the
 * input-wait inner loop) — pumps MIDI events + PCM FIFO bytes. */
void audio_tick(void)
{
    /* devdoc 133: the periodic vblank yield (devdoc 131 方案 A) was removed.
     * It blocked ~one frame every 16 calls, i.e. a hitch roughly every 0.8s on
     * the main loop at NP2kai's ~20Hz pass rate, and its "keep the display
     * alive during a decode" purpose is now covered by frame_decode_pump(),
     * which advances the clock and pumps audio without ever blocking. */

#if AUDIO_PUMP_TRACE
    /* devdoc 163 Phase 1: measure the stall that just happened before
     * pumping anything away.  gap = wall time since the previous tick (how
     * long the BGM was starved); d = wall minus virtual clock (the music
     * time debt the stall cost).  Runs at every entry, but only logs past
     * the audible threshold so a healthy loop stays silent. */
    {
        static unsigned long last_tick_wall;
        unsigned long wnow = hal_wallclock_ms();

        if (last_tick_wall != 0) {
            unsigned long gap = wnow - last_tick_wall;
            if (gap >= AUDIO_PUMP_TRACE_GAP_MS) {
                unsigned long vnow = hal_wallclock_smooth_ms();
                hal_logf("[AP] gap=%lu v=%lu w=%lu d=%+ld\r\n",
                         gap, vnow, wnow, (long)(wnow - vnow));
            }
        }
        last_tick_wall = wnow;
    }
#endif

    audio_tick_isr(hal_wallclock_last_advance_units());  /* stage 4: pass last emitted advance (devdoc 169) */

    /* The FM rewind note is logged here, not in the ISR (B3): the handler only
     * raised g_bgm.rewound.  fmseq_fm_voices() reports how many voices are
     * still ringing as the new loop begins (devdoc 147 A2 phase-preserving
     * rewind left them sounding). */
    if (g_bgm.rewound) {
        g_bgm.rewound = 0;
        hal_logf("FM loop: %d voices still ringing\r\n",
                 fmseq_fm_voices(g_fm_seq));
    }

    /* The ISR path defers buffer release to here: free() is not ISR-safe, and
     * the free + pointer clear must be atomic against the ISR PCM tick so it
     * cannot tick a buffer being released (devdoc 165). */
    bgm_irq_lock();
    if (g_pcm_buf && !hal_pcm_active()) {
        free(g_pcm_buf);
        g_pcm_buf = NULL;
    }
    bgm_irq_unlock();
}

/* Scene end: silence BGM (all-notes-off + release) and PCM. */
void audio_stop_all(void)
{
    audio_bgm_stop();
    pcm_release();
    /* OPNA hard silence as a final fallback even if no BGM was active. */
    if (g_fm_ok)
        hal_fm_shutdown();
}
