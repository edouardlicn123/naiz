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
#include "scene_layers.h"
#include "strutil.h"

static GameSettings g_settings;

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
    return g_settings.text_speed;
}

void settings_set_text_speed(int speed)
{
    int i;
    for (i = 0; i < SETTINGS_TEXT_SPEED_N; i++) {
        if (SETTINGS_TEXT_SPEEDS[i] == speed) {
            g_settings.text_speed = (unsigned char)speed;
            return;
        }
    }
}

/*
 * settings_load — Parse settings.txt into GameSettings and apply the
 * dialog/button style to the layer modules.
 * Missing file or malformed lines use defaults. Returns 0 (never fails).
 */
int settings_load(void)
{
    FILE *f = fopen("settings.txt", "r");
    char line[64];
    char *eq, *val, *nl;
    int known, ds, bs, ts, i;

    memset(&g_settings, 0, sizeof(g_settings));
    g_settings.text_speed = TEXT_SPEED_DEFAULT;

    if (!f) {
        /* defaults: style 0, empty version, blackletter off */
        return 0;
    }

    while (fgets(line, sizeof(line), f)) {
        known = 0;

        if (strchr(line, '\n') == NULL && strlen(line) >= sizeof(line) - 1) {
            while (strchr(line, '\n') == NULL && !feof(f) && fgets(line, sizeof(line), f));
            continue;
        }

        /* Skip comment lines. */
        if (line[0] == ';' || line[0] == '#') continue;

        eq = strchr(line, '=');
        if (!eq) continue;
        *eq = '\0';
        val = eq + 1;
        nl = strchr(val, '\n');
        if (nl) *nl = '\0';

        if (val[0] == '\0')
            continue;

        if (strcmp(line, "dlgstyle") == 0) {
            known = 1;
            ds = atoi(val);
            if (ds >= 0 && ds <= 9)
                g_settings.dialog_style = (unsigned char)ds;
        } else if (strcmp(line, "btnstyle") == 0) {
            known = 1;
            bs = atoi(val);
            if (bs >= 0 && bs <= 4)
                g_settings.button_style = (unsigned char)bs;
        } else if (strcmp(line, "lang") == 0) {
            known = 1;
            str_copy(g_settings.lang, sizeof(g_settings.lang), val);
        } else if (strcmp(line, "version") == 0) {
            known = 1;
            str_copy(g_settings.version, sizeof(g_settings.version), val);
        } else if (strcmp(line, "blacktitle") == 0) {
            known = 1;
            g_settings.blackletter_title = (atoi(val) != 0);
        } else if (strcmp(line, "blackdialog") == 0) {
            known = 1;
            g_settings.blackletter_dialog = (atoi(val) != 0);
        } else if (strcmp(line, "text_speed") == 0) {
            known = 1;
            ts = atoi(val);
            for (i = 0; i < SETTINGS_TEXT_SPEED_N; i++) {
                if (SETTINGS_TEXT_SPEEDS[i] == ts) {
                    g_settings.text_speed = (unsigned char)ts;
                    break;
                }
            }
            /* unknown values fall back to the default (32) */
        }

        (void)known;
    }
    fclose(f);

    dlg_set_style(g_settings.dialog_style);
    btn_set_style(g_settings.button_style);
    return 0;
}

int settings_save(void)
{
    FILE *f = fopen("settings.txt", "w");
    if (!f) return -1;

    if (g_settings.version[0])
        fprintf(f, "version=%s\n", g_settings.version);
    fprintf(f, "dlgstyle=%d\n", (int)g_settings.dialog_style);
    fprintf(f, "btnstyle=%d\n", (int)g_settings.button_style);
    if (g_settings.lang[0])
        fprintf(f, "lang=%s\n", g_settings.lang);
    fprintf(f, "blacktitle=%d\n", g_settings.blackletter_title);
    fprintf(f, "blackdialog=%d\n", g_settings.blackletter_dialog);
    fprintf(f, "text_speed=%d\n", (int)g_settings.text_speed);

    fclose(f);
    return 0;
}

void settings_set_lang(const char *lang)
{
    if (!lang) lang = "eng";
    str_copy(g_settings.lang, sizeof(g_settings.lang), lang);
}
