/*
 * settings.h — Runtime game configuration (settings.txt).
 *
 * Owned by settings.c; single parse entry point that replaces the old
 * read_settings() in nb.c, which wrote six cross-module globals directly.
 */
#ifndef SETTINGS_H
#define SETTINGS_H

#define SETTINGS_VERSION_MAX  32

/* Parsed game settings (settings.txt). */
typedef struct {
    unsigned char dialog_style;
    unsigned char button_style;
    char          version[SETTINGS_VERSION_MAX];
    int           blackletter_title;
    int           blackletter_dialog;
    char          lang[8];
} GameSettings;

/* Parse settings.txt and apply dialog/button style to the layer modules.
 * Missing file or malformed lines use defaults. Returns 0 (never fails). */
int settings_load(void);

/* Save current settings to settings.txt. Returns 0 on success, -1 on error. */
int settings_save(void);

/* Accessors */
const char *settings_get_version(void);
int  settings_get_blackletter_title(void);
int  settings_get_blackletter_dialog(void);
const char *settings_get_lang(void);

/* Mutators */
void settings_set_lang(const char *lang);

/* Pre-game settings menu (C-code rendered). Always shown on startup. */
void settings_menu_run(void);

#endif
