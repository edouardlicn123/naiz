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

/* Audio preference ranges (devdoc 118).  BGM is MIDI CC7 0-127 ascending;
 * PCM is the A466 attenuation 0-15 REVERSED (0 = loudest).  They are
 * deliberately different units — never reuse one for the other. */
#define SETTINGS_BGM_VOL_MAX   127
#define SETTINGS_PCM_VOL_MAX   15

/* Menu index of each audio preference step, shared by the menu and the
 * persistence layer so a value is never written that the menu cannot show. */
#define SETTINGS_BGM_VOL_LADDER   { 0, 64, 127 }
#define SETTINGS_PCM_VOL_LADDER   { 0, 5, 10, 15 }
#define SETTINGS_BGM_VOL_N        3
#define SETTINGS_PCM_VOL_N        4

/* Single source of truth for the valid typewriter speeds: the parser
 * whitelist, the setter whitelist and the settings-menu value list all
 * read this table, so adding a speed is a one-place change.
 * LABELS is index-aligned with SPEEDS and holds the English tr() keys
 * rendered by the in-game settings menu (both arrays share one length
 * macro, so a mismatch cannot compile). */
#define SETTINGS_TEXT_SPEED_N  4
extern const int SETTINGS_TEXT_SPEEDS[SETTINGS_TEXT_SPEED_N];
extern const char *const SETTINGS_TEXT_SPEED_LABELS[SETTINGS_TEXT_SPEED_N];

/* Parsed project settings (settings.txt, build-deployed). */
typedef struct {
    unsigned char dialog_style;
    unsigned char button_style;
    char          version[SETTINGS_VERSION_MAX];
    int           blackletter_title;
    int           blackletter_dialog;
    char          lang[8];
} GameSettings;

/* Parse settings.txt, then overlay USER.CFG (player preferences, which win),
 * then apply dialog/button style to the layer modules and the audio
 * preferences to audio.c.  A missing file is a legal first-boot state for
 * either.  Returns 0 (never fails). */
int settings_load(void);

/* Write USER.CFG.  settings.txt is build-owned and is never written back:
 * doing so would make the file drift from config.toml.  Returns 0 on
 * success, -1 on error. */
int settings_save(void);

/* Accessors */
const char *settings_get_version(void);
int  settings_get_blackletter_title(void);
int  settings_get_blackletter_dialog(void);
const char *settings_get_lang(void);
int  settings_get_text_speed(void);
int  settings_get_bgm_enabled(void);
int  settings_get_snd_enabled(void);
int  settings_get_vc_enabled(void);
int  settings_get_bgm_volume(void);
int  settings_get_pcm_volume(void);

/* Mutators */
void settings_set_lang(const char *lang);
void settings_set_text_speed(int speed);
void settings_set_bgm_enabled(int on);
void settings_set_snd_enabled(int on);
void settings_set_vc_enabled(int on);
void settings_set_bgm_volume(int v);
void settings_set_pcm_volume(int step);

/* Pre-game settings menu (C-code rendered). Always shown on startup. */
void settings_menu_run(void);

#endif
