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

static GameSettings g_settings;

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
    int known, ds, bs;

    memset(&g_settings, 0, sizeof(g_settings));

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
            strncpy(g_settings.lang, val, sizeof(g_settings.lang) - 1);
            g_settings.lang[sizeof(g_settings.lang) - 1] = '\0';
        } else if (strcmp(line, "version") == 0) {
            known = 1;
            strncpy(g_settings.version, val, sizeof(g_settings.version) - 1);
            g_settings.version[sizeof(g_settings.version) - 1] = '\0';
        } else if (strcmp(line, "blacktitle") == 0) {
            known = 1;
            g_settings.blackletter_title = (atoi(val) != 0);
        } else if (strcmp(line, "blackdialog") == 0) {
            known = 1;
            g_settings.blackletter_dialog = (atoi(val) != 0);
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

    fclose(f);
    return 0;
}

void settings_set_lang(const char *lang)
{
    if (!lang) lang = "eng";
    strncpy(g_settings.lang, lang, sizeof(g_settings.lang) - 1);
    g_settings.lang[sizeof(g_settings.lang) - 1] = '\0';
}
