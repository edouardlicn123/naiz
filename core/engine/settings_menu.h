/*
 * settings_menu.h — Pre-game settings menu (C-code rendered, English only).
 *
 * Shown on first launch (no settings.txt). Lets the user choose a language
 * before the game starts. Pure ASCII, no CJK needed for the menu itself.
 */
#ifndef SETTINGS_MENU_H
#define SETTINGS_MENU_H

/* Run the settings menu (blocking). Lets user choose language.
 * Returns after user clicks "Start Game". */
void settings_menu_run(void);

/* Check if settings.txt exists (non-zero = file exists). */
int settings_file_exists(void);

#endif
