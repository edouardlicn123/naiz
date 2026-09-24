/*
 * audio.c — Engine audio manager: MIDI BGM scheduling + 86-board PCM pump.
 *
 * Devdoc 101:
 *   - BGM: .mid read from AUDIO.DAT, parsed into a resident event table
 *     (lib/midi), then streamed to the MPU-401 UART as real-time bytes on
 *     the 60Hz tick (hal_midi_out), positioned by hal_wallclock_ms().
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
#include "midi.h"
#include "audio.h"
#include "nb_asset_table.h"

#define AUDIO_ARCHIVE "AUDIO.DAT"
#define AUDIO_MAX_ENTRIES 8192    /* TOC cap, mirrors IMAGE.DAT usage */
#define PCM_HDR_SIZE 16           /* "NAIZPCM" + rate + flags + reserved */

/*=== Archive ============================================================*/

static FArchive g_arc;
static int g_arc_ok;              /* AUDIO.DAT opened successfully */
static int g_mpu_ok;              /* MPU-401 present (hal_audio_detect) */

/*=== BGM (MIDI) =========================================================*/

typedef struct {
    MidEvent     *ev;             /* parsed event table (resident) */
    int           count;
    int           idx;            /* next event to fire */
    unsigned long wall0;          /* hal_wallclock_ms() at pass start */
    int           active;
} BgmState;

static BgmState g_bgm;

/* Free any current BGM event table.  midi_free(NULL) is safe. */
static void bgm_release(void)
{
    if (g_bgm.ev) {
        midi_free(g_bgm.ev);
        g_bgm.ev = NULL;
    }
    g_bgm.count = 0;
    g_bgm.idx = 0;
    g_bgm.active = 0;
}

/* Compile-time registry check (ASSETS.DB) for one audio asset map. */
static int audio_map_find(const AudioAssetMap *map, const char *key)
{
    for (; map->name != NULL; map++)
        if (strcmp(map->name, key) == 0)
            return map->id;
    return -1;
}

void audio_bgm_start(const char *key)
{
    long off, size;
    uint8_t *raw;
    MidEvent *ev;
    int count = 0;

    if (!key || !key[0]) return;
    if (!g_mpu_ok) {
        hal_logf("BGM WARN: '%s' ignored (no MPU detected)\r\n", key);
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
    if (farchive_lookup_name(&g_arc, key, &off, &size, NULL) != 0) {
        hal_logf("BGM WARN: '%s' missing in %s\r\n", key, AUDIO_ARCHIVE);
        return;
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
    hal_logf("BGM start '%s' (%d events)\r\n", key, count);
}

void audio_bgm_stop(void)
{
    if (g_mpu_ok) {
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

static void pcm_release(void)
{
    hal_pcm_stop();
    if (g_pcm_buf) {
        free(g_pcm_buf);
        g_pcm_buf = NULL;
    }
}

static void pcm_play(const AudioAssetMap *map, const char *key)
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
    if (farchive_lookup_name(&g_arc, key, &off, &size, NULL) != 0) {
        hal_logf("PCM WARN: '%s' missing in %s\r\n", key, AUDIO_ARCHIVE);
        return;
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
    hal_logf("PCM start '%s' (%ld B, rate %u)\r\n", key, size - PCM_HDR_SIZE, rate);
}

void audio_snd_play(const char *key) { pcm_play(snd_map, key); }
void audio_vc_play(const char *key)  { pcm_play(voice_map, key); }

/*=== Lifecycle ==========================================================*/

void audio_init(void)
{
    if (farchive_open(&g_arc, AUDIO_ARCHIVE, AUDIO_MAX_ENTRIES) != 0) {
        hal_logf("AUD WARN: no %s (audio disabled)\r\n", AUDIO_ARCHIVE);
        g_arc_ok = 0;
        g_mpu_ok = 0;
        return;
    }
    if (g_arc.truncated)
        hal_logf("AUD WARN: %s TOC truncated to %d entries\r\n",
                 AUDIO_ARCHIVE, AUDIO_MAX_ENTRIES);
    g_arc_ok = 1;

    g_mpu_ok = hal_audio_detect();
    if (g_mpu_ok)
        hal_log("AUD MPU OK\r\n");
    else
        hal_log("AUD WARN: no MPU-401 (BGM disabled, PCM unchanged)\r\n");
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
}
