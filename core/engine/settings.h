/*
 * settings.h — Runtime game configuration (settings.txt).
 *
 * Owned by settings.c; single parse entry point that replaces the old
 * read_settings() in nb.c, which wrote six cross-module globals directly.
 */
#ifndef SETTINGS_H
#define SETTINGS_H

#define SETTINGS_VERSION_MAX  32

/* Typewriter text speed (chars/sec). 0 = Instant (typewriter disabled).
 * Valid values: TEXT_SPEED_INSTANT / 16 / 32 / 64. */
#define TEXT_SPEED_INSTANT  0
#define TEXT_SPEED_DEFAULT  32

/* Single source of truth for the valid typewriter speeds: the parser
 * whitelist, the setter whitelist and the settings-menu value list all
 * read this table, so adding a speed is a one-place change.
 * LABELS is index-aligned with SPEEDS and holds the English tr() keys
 * rendered by the in-game settings menu (both arrays share one length
 * macro, so a mismatch cannot compile). */
#define SETTINGS_TEXT_SPEED_N  4
extern const int SETTINGS_TEXT_SPEEDS[SETTINGS_TEXT_SPEED_N];
extern const char *const SETTINGS_TEXT_SPEED_LABELS[SETTINGS_TEXT_SPEED_N];

/* Parsed game settings (settings.txt). */
typedef struct {
    unsigned char dialog_style;
    unsigned char button_style;
    unsigned char text_speed;
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
int  settings_get_text_speed(void);

/* Mutators */
void settings_set_lang(const char *lang);
void settings_set_text_speed(int speed);

/* Pre-game settings menu (C-code rendered). Always shown on startup. */
void settings_menu_run(void);

#endif
