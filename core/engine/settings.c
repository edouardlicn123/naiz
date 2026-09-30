/*
 * settings.c — Runtime game configuration (settings.txt) parser.
 *
 * Single source for game settings. Replaces nb.c read_settings(), which
 * wrote six cross-module globals (dialog/button style, version, lang,
 * blackletter flags) directly. The parsed values are owned here and
 * applied through accessors/setters.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "settings.h"
#include "audio.h"
#include "scene_layers.h"
#include "strutil.h"
#include "hal.h"

static GameSettings g_settings;      /* from settings.txt (build-owned) */

/* Player preferences from USER.CFG.  Split from g_settings because the two
 * files have opposite owners: settings.txt is refreshed by every build, so
 * anything the player changed and that lives there is lost (devdoc 118). */
static struct {
    int text_speed;
    int bgm_on;
    int snd_on;
    int vc_on;
    int bgm_vol;                       /* CC7 0-127 */
    int pcm_vol;                       /* A466 attenuation 0-15 */
    char lang[8];
} g_pref;

static const int g_bgm_vol_ladder[SETTINGS_BGM_VOL_N] = SETTINGS_BGM_VOL_LADDER;
static const int g_pcm_vol_ladder[SETTINGS_PCM_VOL_N] = SETTINGS_PCM_VOL_LADDER;

/* Valid typewriter speeds (single source of truth; see settings.h). */
const int SETTINGS_TEXT_SPEEDS[SETTINGS_TEXT_SPEED_N] = {
    TEXT_SPEED_INSTANT, 16, TEXT_SPEED_DEFAULT, 64
};

/* Display labels, index-aligned with SETTINGS_TEXT_SPEEDS.  These are
 * English tr() keys, resolved by the settings menu at draw time. */
const char *const SETTINGS_TEXT_SPEED_LABELS[SETTINGS_TEXT_SPEED_N] = {
    "Instant", "16/s", "32/s", "64/s"
};

const char *settings_get_version(void)
{
    return g_settings.version;
}

int settings_get_blackletter_title(void)
{
    return g_settings.blackletter_title;
}

int settings_get_blackletter_dialog(void)
{
    return g_settings.blackletter_dialog;
}

const char *settings_get_lang(void)
{
    return g_settings.lang;
}

int settings_get_text_speed(void)
{
    return g_pref.text_speed;
}

/* The live switch/volume state lives in audio.c, so read it back from there
 * rather than from g_pref: one source of truth, and a menu redraw after an
 * in-flight change sees what the hardware was actually told. */
int settings_get_bgm_enabled(void)  { return audio_get_bgm_enabled(); }
int settings_get_snd_enabled(void)  { return audio_get_snd_enabled(); }
int settings_get_vc_enabled(void)   { return audio_get_vc_enabled(); }
int settings_get_bgm_volume(void)   { return audio_get_bgm_volume(); }
int settings_get_pcm_volume(void)   { return audio_get_pcm_volume(); }

static void pref_set_text_speed(int speed)
{
    int i;
    for (i = 0; i < SETTINGS_TEXT_SPEED_N; i++) {
        if (SETTINGS_TEXT_SPEEDS[i] == speed) {
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

    for (i = 0; i < SETTINGS_BGM_VOL_N; i++) {
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
    if (step > SETTINGS_PCM_VOL_MAX) step = SETTINGS_PCM_VOL_MAX;
    g_pref.pcm_vol = step;
}

void settings_set_text_speed(int speed) { pref_set_text_speed(speed); }

/* Setter side mirrors the getter: the value is applied to audio.c first and
 * then recorded in g_pref, which is what settings_save() writes. */
void settings_set_bgm_enabled(int on)
{
    g_pref.bgm_on = on ? 1 : 0;
    audio_set_bgm_enabled(g_pref.bgm_on);
}

void settings_set_snd_enabled(int on)
{
    g_pref.snd_on = on ? 1 : 0;
    audio_set_snd_enabled(g_pref.snd_on);
}

void settings_set_vc_enabled(int on)
{
    g_pref.vc_on = on ? 1 : 0;
    audio_set_vc_enabled(g_pref.vc_on);
}

void settings_set_bgm_volume(int v)
{
    pref_set_bgm_volume(v);
    audio_set_bgm_volume(g_pref.bgm_vol);
}

void settings_set_pcm_volume(int step)
{
    pref_set_pcm_volume(step);
    audio_set_pcm_volume(g_pref.pcm_vol);
}

/*
 * Read one key=value line into *out.  Returns 1 when 'line' held a value
 * (after the comment / overlong-line handling), 0 when the line carried
 * nothing.  Both files share this so a malformed line behaves identically
 * in settings.txt and USER.CFG.
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

/* settings_load — project settings.txt, then the player's USER.CFG on top,
 * then apply styles and audio preferences.  Both files may be absent.
 */
int settings_load(void)
{
    FILE *f;
    char line[64], key[32], val[48];
    int ds, bs;

    memset(&g_settings, 0, sizeof(g_settings));
    memset(&g_pref, 0, sizeof(g_pref));
    g_pref.text_speed = TEXT_SPEED_DEFAULT;
    g_pref.bgm_on = 1;
    g_pref.snd_on = 1;
    g_pref.vc_on = 1;
    g_pref.bgm_vol = SETTINGS_BGM_VOL_MAX;
    g_pref.pcm_vol = 0;

    /* Pass 1: settings.txt (project).  lang here is the project default and
     * is superseded by USER.CFG whenever the player chose a language. */
    f = fopen("settings.txt", "r");
    if (f) {
        while (fgets(line, sizeof(line), f)) {
            if (!read_kv(f, line, sizeof(line), key, sizeof(key),
                        val, sizeof(val)))
                continue;

            if (strcmp(key, "dlgstyle") == 0) {
                ds = atoi(val);
                if (ds >= 0 && ds <= 9)
                    g_settings.dialog_style = (unsigned char)ds;
            } else if (strcmp(key, "btnstyle") == 0) {
                bs = atoi(val);
                if (bs >= 0 && bs <= 4)
                    g_settings.button_style = (unsigned char)bs;
            } else if (strcmp(key, "lang") == 0) {
                str_copy(g_settings.lang, sizeof(g_settings.lang), val);
            } else if (strcmp(key, "version") == 0) {
                str_copy(g_settings.version, sizeof(g_settings.version), val);
            } else if (strcmp(key, "blacktitle") == 0) {
                g_settings.blackletter_title = (atoi(val) != 0);
            } else if (strcmp(key, "blackdialog") == 0) {
                g_settings.blackletter_dialog = (atoi(val) != 0);
            }
            /* text_speed / audio keys are ignored here: they are player
             * preferences and settings.txt must not set them. */
        }
        fclose(f);
    } else {
        hal_log("SET: no settings.txt (project defaults)\r\n");
    }

    /* Pass 2: USER.CFG (player) — wins over the project default. */
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

    if (!g_pref.lang[0])
        str_copy(g_pref.lang, sizeof(g_pref.lang), g_settings.lang);

    dlg_set_style(g_settings.dialog_style);
    btn_set_style(g_settings.button_style);

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

int settings_save(void)
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

void settings_set_lang(const char *lang)
{
    if (!lang) lang = "eng";
    str_copy(g_pref.lang, sizeof(g_pref.lang), lang);
}
