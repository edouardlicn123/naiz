/*
 * prefs.h — Player preferences (USER.CFG), the only runtime-written file.
 *
 * Owned by prefs.c; single parse entry point that replaces the old
 * read_settings() in nb.c, which wrote six cross-module globals directly.
 *
 * Project-level configuration is NOT here: version, dialog/button style and
 * the blackletter flags live in projects/<game>/config.toml and reach the
 * engine as compile-time macros in nb_config.h (devdoc 120).  Only the
 * player's own choices are parsed at runtime, from USER.CFG.
 */
#ifndef PREFS_H
#define PREFS_H

#include "nb_config.h"

/* Language code buffer: every code in langdefs.LANG_CODES is 3 chars, so 8
 * leaves room for a longer code without silently truncating. */
#define PREFS_LANG_MAX  8

/* Typewriter text speed (chars/sec). 0 = Instant (typewriter disabled).
 * Valid values: TEXT_SPEED_INSTANT / 16 / 32 / 64. */
#define TEXT_SPEED_INSTANT  0
#define TEXT_SPEED_DEFAULT  0

/* Audio preference ranges (devdoc 118).  BGM is MIDI CC7 0-127 ascending;
 * PCM is the A466 attenuation 0-15 REVERSED (0 = loudest).  They are
 * deliberately different units — never reuse one for the other. */
#define PREFS_BGM_VOL_MAX   127
#define PREFS_PCM_VOL_MAX   15

/* Menu index of each audio preference step, shared by the menu and the
 * persistence layer so a value is never written that the menu cannot show. */
#define PREFS_BGM_VOL_LADDER   { 0, 64, 127 }
#define PREFS_PCM_VOL_LADDER   { 0, 5, 10, 15 }
#define PREFS_BGM_VOL_N        3
#define PREFS_PCM_VOL_N        4

/* Single source of truth for the valid typewriter speeds: the parser
 * whitelist, the setter whitelist and the settings-menu value list all
 * read this table, so adding a speed is a one-place change.
 * LABELS is index-aligned with SPEEDS and holds the English tr() keys
 * rendered by the in-game settings menu (both arrays share one length
 * macro, so a mismatch cannot compile). */
#define PREFS_TEXT_SPEED_N  4
extern const int PREFS_TEXT_SPEEDS[PREFS_TEXT_SPEED_N];
extern const char *const PREFS_TEXT_SPEED_LABELS[PREFS_TEXT_SPEED_N];

/* Parsed player preferences from USER.CFG.  Project-level values live in
 * nb_config.h and are read directly from there — they must never be parsed
 * from a file, or build would be able to reset them. */
typedef struct {
    int text_speed;
    int bgm_on;
    int snd_on;
    int vc_on;
    int bgm_vol;                       /* CC7 0-127 */
    int pcm_vol;                       /* A466 attenuation 0-15 */
    char lang[PREFS_LANG_MAX];
} Prefs;

/* Parse USER.CFG (a missing file is a legal first-boot state), then apply the
 * dialog/button style from nb_config.h and the audio preferences to audio.c.
 * Returns 0 (never fails). */
int prefs_load(void);

/* Write USER.CFG.  Nothing else in the engine is writable at runtime: the
 * project-level values are compile-time constants, so there is no second file
 * to keep in sync.  Returns 0 on success, -1 on error. */
int prefs_save(void);

/* Accessors.  version / blackletter_* simply forward the compile-time
 * project config; lang returns the player's choice, falling back to the
 * project's shipping default. */
const char *prefs_get_version(void);
int  prefs_get_blackletter_title(void);
int  prefs_get_blackletter_dialog(void);
const char *prefs_get_lang(void);
int  prefs_get_text_speed(void);
int  prefs_get_bgm_enabled(void);
int  prefs_get_snd_enabled(void);
int  prefs_get_vc_enabled(void);
int  prefs_get_bgm_volume(void);
int  prefs_get_pcm_volume(void);

/* Mutators.  Each records into the Prefs struct and, where one exists, hands
 * the value to the module that owns the real state (audio.c). */
void prefs_set_lang(const char *lang);
void prefs_set_text_speed(int speed);
void prefs_set_bgm_enabled(int on);
void prefs_set_snd_enabled(int on);
void prefs_set_vc_enabled(int on);
void prefs_set_bgm_volume(int v);
void prefs_set_pcm_volume(int step);

#endif
