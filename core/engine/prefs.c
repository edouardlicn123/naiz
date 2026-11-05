/*
 * prefs.c — Player preferences (USER.CFG) parser.
 *
 * USER.CFG is the only file the engine writes at runtime.  Project-level
 * configuration (version, dialog/button style, blackletter flags, the
 * shipping default language) is not parsed here at all: it arrives as
 * compile-time macros in nb_config.h, generated from config.toml by
 * export_config.py (devdoc 120).  The split matters — anything the player
 * changes must live in a file the build never overwrites (devdoc 118).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "prefs.h"
#include "audio.h"
#include "scene_layers.h"
#include "strutil.h"
#include "hal.h"

static Prefs g_pref;

static const int g_bgm_vol_ladder[PREFS_BGM_VOL_N] = PREFS_BGM_VOL_LADDER;
static const int g_pcm_vol_ladder[PREFS_PCM_VOL_N] = PREFS_PCM_VOL_LADDER;

/* Valid typewriter speeds (single source of truth; see prefs.h). */
const int PREFS_TEXT_SPEEDS[PREFS_TEXT_SPEED_N] = {
    TEXT_SPEED_INSTANT, 16, TEXT_SPEED_DEFAULT, 64
};

/* Display labels, index-aligned with PREFS_TEXT_SPEEDS.  These are
 * English tr() keys, resolved by the settings menu at draw time. */
const char *const PREFS_TEXT_SPEED_LABELS[PREFS_TEXT_SPEED_N] = {
    "Instant", "16/s", "32/s", "64/s"
};

const char *prefs_get_version(void)
{
    return NAIZ_VERSION;
}

int prefs_get_blackletter_title(void)
{
    return NAIZ_BLACKLETTER_TITLE;
}

int prefs_get_blackletter_dialog(void)
{
    return NAIZ_BLACKLETTER_DIALOG;
}

/* The effective language: the player's choice, else the project's shipping
 * default.  Must read the SAME field prefs_set_lang() writes — the two were
 * split across different structs in 0.3.011-0.3.013, so a boot-menu choice
 * was written to USER.CFG and then read back as the build default
 * (devdoc 120).
 */
const char *prefs_get_lang(void)
{
    if (g_pref.lang[0])
        return g_pref.lang;
    return NAIZ_DEFAULT_LANG;
}

int prefs_get_text_speed(void)
{
    return g_pref.text_speed;
}

/* The live switch/volume state lives in audio.c, so read it back from there
 * rather than from g_pref: one source of truth, and a menu redraw after an
 * in-flight change sees what the hardware was actually told. */
int prefs_get_bgm_enabled(void)  { return audio_get_bgm_enabled(); }
int prefs_get_snd_enabled(void)  { return audio_get_snd_enabled(); }
int prefs_get_vc_enabled(void)   { return audio_get_vc_enabled(); }
int prefs_get_bgm_volume(void)   { return audio_get_bgm_volume(); }
int prefs_get_pcm_volume(void)   { return audio_get_pcm_volume(); }

static void pref_set_text_speed(int speed)
{
    int i;
    for (i = 0; i < PREFS_TEXT_SPEED_N; i++) {
        if (PREFS_TEXT_SPEEDS[i] == speed) {
            g_pref.text_speed = speed;
            return;
        }
    }
    /* unknown values fall back to the default (32) */
    g_pref.text_speed = TEXT_SPEED_DEFAULT;
}

/* Snap a raw BGM volume to the nearest ladder rung so a hand-edited
 * USER.CFG can never put a value on screen the menu cannot show. */
static void pref_set_bgm_volume(int v)
{
    int i, best = 0, bestd = -1, d;

    for (i = 0; i < PREFS_BGM_VOL_N; i++) {
        d = v - g_bgm_vol_ladder[i];
        if (d < 0) d = -d;
        if (bestd < 0 || d < bestd) {
            bestd = d;
            best = i;
        }
    }
    g_pref.bgm_vol = g_bgm_vol_ladder[best];
}

static void pref_set_pcm_volume(int step)
{
    if (step < 0) step = 0;
    if (step > PREFS_PCM_VOL_MAX) step = PREFS_PCM_VOL_MAX;
    g_pref.pcm_vol = step;
}

void prefs_set_text_speed(int speed) { pref_set_text_speed(speed); }

/* Setter side mirrors the getter: the value is applied to audio.c first and
 * then recorded in g_pref, which is what prefs_save() writes. */
void prefs_set_bgm_enabled(int on)
{
    g_pref.bgm_on = on ? 1 : 0;
    audio_set_bgm_enabled(g_pref.bgm_on);
}

void prefs_set_snd_enabled(int on)
{
    g_pref.snd_on = on ? 1 : 0;
    audio_set_snd_enabled(g_pref.snd_on);
}

void prefs_set_vc_enabled(int on)
{
    g_pref.vc_on = on ? 1 : 0;
    audio_set_vc_enabled(g_pref.vc_on);
}

void prefs_set_bgm_volume(int v)
{
    pref_set_bgm_volume(v);
    audio_set_bgm_volume(g_pref.bgm_vol);
}

void prefs_set_pcm_volume(int step)
{
    pref_set_pcm_volume(step);
    audio_set_pcm_volume(g_pref.pcm_vol);
}

/*
 * Read one key=value line into *out.  Returns 1 when 'line' held a value
 * (after the comment / overlong-line handling), 0 when the line carried
 * nothing.  USER.CFG is the only file parsed with this.
 */
static int read_kv(FILE *f, char *line, size_t line_sz,
                   char *key, size_t key_sz, char *val, size_t val_sz)
{
    char *eq, *nl;

    /* Overlong line: drain its continuation and ignore the whole key. */
    if (strchr(line, '\n') == NULL && strlen(line) >= line_sz - 1) {
        while (strchr(line, '\n') == NULL && !feof(f) && fgets(line, (int)line_sz, f));
        return 0;
    }
    if (line[0] == ';' || line[0] == '#') return 0;

    eq = strchr(line, '=');
    if (!eq) return 0;
    *eq = '\0';
    nl = strchr(eq + 1, '\n');
    if (nl) *nl = '\0';
    if (eq[1] == '\0') return 0;

    str_copy(key, key_sz, line);
    str_copy(val, val_sz, eq + 1);
    return 1;
}

/* prefs_load — parse USER.CFG (may be absent: legal first-boot state), then
 * apply the compile-time project style and the audio preferences.
 */
int prefs_load(void)
{
    FILE *f;
    char line[64], key[32], val[48];

    memset(&g_pref, 0, sizeof(g_pref));
    g_pref.text_speed = TEXT_SPEED_DEFAULT;
    g_pref.bgm_on = 1;
    g_pref.snd_on = 1;
    g_pref.vc_on = 1;
    g_pref.bgm_vol = PREFS_BGM_VOL_MAX;
    g_pref.pcm_vol = 0;

    /* USER.CFG — the player's own choices, and the only file parsed here. */
    f = fopen("USER.CFG", "r");
    if (f) {
        while (fgets(line, sizeof(line), f)) {
            if (!read_kv(f, line, sizeof(line), key, sizeof(key),
                        val, sizeof(val)))
                continue;

            if (strcmp(key, "lang") == 0)
                str_copy(g_pref.lang, sizeof(g_pref.lang), val);
            else if (strcmp(key, "text_speed") == 0)
                pref_set_text_speed(atoi(val));
            else if (strcmp(key, "bgm") == 0)
                g_pref.bgm_on = (atoi(val) != 0);
            else if (strcmp(key, "snd") == 0)
                g_pref.snd_on = (atoi(val) != 0);
            else if (strcmp(key, "vc") == 0)
                g_pref.vc_on = (atoi(val) != 0);
            else if (strcmp(key, "bgm_vol") == 0)
                pref_set_bgm_volume(atoi(val));
            else if (strcmp(key, "pcm_vol") == 0)
                pref_set_pcm_volume(atoi(val));
        }
        fclose(f);
        hal_log("SET: USER.CFG loaded\r\n");
    } else {
        /* Legal first-boot state; hal_log makes it visible in the trace. */
        hal_log("SET: no USER.CFG (defaults)\r\n");
    }

    /* g_pref.lang is left empty when the player has not chosen yet, so
     * prefs_get_lang() falls through to the project's shipping default. */

    /* Dialog/button style are compile-time project config, not preferences. */
    dlg_set_style(NAIZ_DLGSTYLE);
    btn_set_style(NAIZ_BTNSTYLE);

    /* Applied in the same order the setters use: volume before the switch,
     * so a disabled channel still carries the volume the player chose (turning
     * it back on must not silently reset the level). */
    audio_set_bgm_volume(g_pref.bgm_vol);
    audio_set_pcm_volume(g_pref.pcm_vol);
    audio_set_bgm_enabled(g_pref.bgm_on);
    audio_set_snd_enabled(g_pref.snd_on);
    audio_set_vc_enabled(g_pref.vc_on);
    return 0;
}

int prefs_save(void)
{
    FILE *f = fopen("USER.CFG", "w");
    if (!f) {
        hal_log("SET: USER.CFG write failed\r\n");
        return -1;
    }

    fprintf(f, "; naiz player preferences — not managed by build\r\n");
    if (g_pref.lang[0])
        fprintf(f, "lang=%s\n", g_pref.lang);
    fprintf(f, "text_speed=%d\n", g_pref.text_speed);
    fprintf(f, "bgm=%d\n", g_pref.bgm_on);
    fprintf(f, "snd=%d\n", g_pref.snd_on);
    fprintf(f, "vc=%d\n", g_pref.vc_on);
    fprintf(f, "bgm_vol=%d\n", g_pref.bgm_vol);
    fprintf(f, "pcm_vol=%d\n", g_pref.pcm_vol);

    if (ferror(f)) {
        fclose(f);
        hal_log("SET: USER.CFG write error\r\n");
        return -1;
    }
    fclose(f);
    return 0;
}

void prefs_set_lang(const char *lang)
{
    /* NULL means "no preference"; leave the field empty so prefs_get_lang()
     * falls back to the project default rather than pinning a language. */
    if (!lang) {
        g_pref.lang[0] = '\0';
        return;
    }
    str_copy(g_pref.lang, sizeof(g_pref.lang), lang);
}
