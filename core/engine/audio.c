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
#include "audio.h"
#include "nb_asset_table.h"

#define AUDIO_ARCHIVE "AUDIO.DAT"
#define AUDIO_MAX_ENTRIES 8192    /* TOC cap, mirrors IMAGE.DAT usage */
#define PCM_HDR_SIZE 16           /* "NAIZPCM" + rate + flags + reserved */

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
    int           fm;             /* 1: rendered by fmseq on the OPNA */
    int           active;
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
 * fmp_map order == AUDIO.DAT order).  Invalid entries are skipped loudly;
 * if nothing valid remains, the built-in default takes over. */
static void fm_load_patches(void)
{
    const AudioAssetMap *m;
    int n = 0;

    for (m = fmp_map; m->name != NULL; m++) {
        long off = 0, size = 0;
        uint8_t *raw;

        if (strcmp(m->name, "__dummy__") == 0)
            continue;
        if (n >= FM_FAMILY_MAX)
            break;
        {
            char k8[9];
            str_toc8(k8, sizeof k8, m->name);
            if (farchive_lookup_name(&g_arc, k8, &off, &size, NULL) != 0) {
                hal_logf("FM WARN: patch '%s' missing in %s\r\n", m->name,
                         AUDIO_ARCHIVE);
                continue;
            }
        }
        if (size != FMOPN_PATCH_BYTES) {
            hal_logf("FM WARN: patch '%s' has %ld bytes, need %d\r\n",
                     m->name, size, FMOPN_PATCH_BYTES);
            continue;
        }
        raw = farchive_read_alloc(&g_arc, off, size, NULL);
        if (!raw) {
            hal_logf("FM WARN: read patch '%s' failed\r\n", m->name);
            continue;
        }
        memcpy(g_fm_patches[n].data, raw, FMOPN_PATCH_BYTES);
        free(raw);
        if (fmopn_patch_validate(&g_fm_patches[n]) != 0) {
            hal_logf("FM WARN: patch '%s' fails validation\r\n", m->name);
            continue;   /* slot not committed */
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

    if (g_bgm.fm) {
        int atten = (g_bgm_vol * 15) / AUDIO_BGM_VOL_MAX;
        hal_fm_set_volume(15 - atten);   /* reversed 0(loud)..15(quiet) */
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
    if (midi_parse(raw, (uint32_t)size, &ev, &count) != 0) {
        hal_logf("BGM WARN: parse '%s' failed\r\n", key);
        free(raw);
        return;
    }
    free(raw);   /* event table is independently owned by midi_parse */

    bgm_release();
    g_bgm.ev = ev;
    g_bgm.count = count;
    g_bgm.idx = 0;
    g_bgm.wall0 = hal_wallclock_smooth_ms();
    g_bgm.active = 1;
    if (g_mpu_ok) {
        g_bgm.fm = 0;   /* MIDI is the preferred backend when a card is present */
    } else {
        g_bgm.fm = 1;
        fmseq_events(g_fm_seq, ev, count);
    }
    bgm_apply_volume();
    hal_logf("BGM start '%s' (%d events)%s\r\n", key, count,
             g_bgm.fm ? " (FM)" : "");
}

void audio_bgm_stop(void)
{
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
    hal_pcm_stop();
    if (g_pcm_buf) {
        free(g_pcm_buf);
        g_pcm_buf = NULL;
    }
    g_pcm_channel = PCM_CH_NONE;
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
     * SE/voice never loop (loop=0), per devdoc 101 §4.3 caller semantics. */
    hal_pcm_play(raw + PCM_HDR_SIZE, (uint32_t)(size - PCM_HDR_SIZE), rate, 0);
    free(g_pcm_buf);
    g_pcm_buf = raw;
    g_pcm_channel = chan;
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

void audio_init(void)
{
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
    }

    if (!g_mpu_ok && !g_fm_ok)
        hal_log("AUD WARN: no audio backend (MPU-401 absent, no OPNA)\r\n");
}

/* Called from the 60Hz heartbeat every frame (AUTOEXIT, main and the
 * input-wait inner loop) — pumps MIDI events + PCM FIFO bytes. */
void audio_tick(void)
{
    /* PCM push first.  hal_pcm_tick stops the channel at EOF; a finished
     * buffer is then safe to release here. */
    hal_pcm_tick();
    if (g_pcm_buf && !hal_pcm_active()) {
        free(g_pcm_buf);
        g_pcm_buf = NULL;
    }

    if (!g_bgm.active) return;

    if (g_bgm.fm) {
        /* FM backend: feed the smooth virtual clock to fmseq (devdoc 107 /
         * 0.2.134 — raw hal_wallclock_ms deltas are chunked under NP2kai).
         * Loop by rewinding to the current clock and re-seeding fmseq. */
        unsigned long now = hal_wallclock_smooth_ms();
        unsigned long cur = now - g_bgm.wall0;

fmseq_pump(g_fm_seq, &g_fm_sink, cur);
        if (fmseq_finished(g_fm_seq)) {
            int ring = fmseq_fm_voices(g_fm_seq);
            if (ring > 0)
                hal_logf("FM loop: %d voice%s still ringing on rewind\r\n",
                         ring, ring == 1 ? "" : "s");
            g_bgm.wall0 = now;
            fmseq_stop(g_fm_seq, &g_fm_sink);
        }
        return;
    }

    {
        /* Smooth virtual clock (devdoc 107 / 0.2.134): raw
         * hal_wallclock_ms() deltas are chunked under NP2kai (frozen 3-6s,
         * then +1000..+6000ms jumps), which stalled cur during the holes and
         * tone-burst the whole event backlog on catch-up.  The smooth clock
         * advances cur at pass cadence with per-pass bounded deltas, so the
         * MIDI schedule tracks nominal event times through the holes. */
        unsigned long now = hal_wallclock_smooth_ms();
        unsigned long cur = now - g_bgm.wall0;

        while (g_bgm.idx < g_bgm.count &&
               g_bgm.ev[g_bgm.idx].tick_ms <= cur) {
            const MidEvent *e = &g_bgm.ev[g_bgm.idx];
            uint8_t st = e->b0;

            hal_midi_out(st);
            hal_midi_out(e->b1);
            /* 0xC0/0xD0 are single-data voice statuses (2-byte wire). */
            if ((st & 0xF0) != 0xC0 && (st & 0xF0) != 0xD0)
                hal_midi_out(e->b2);
            g_bgm.idx++;
        }

        /* End of table: loop by resetting the playhead to the current
         * smooth virtual clock (devdoc 101 §4.2, devdoc 107). */
        if (g_bgm.idx >= g_bgm.count) {
            g_bgm.wall0 = now;
            g_bgm.idx = 0;
        }
    }
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
