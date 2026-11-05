/*
 * bootmenu.h — Pre-game boot menu (C-code rendered, English only).
 *
 * Shown on first launch, before the translation table and the CJK font exist,
 * so it is pure ASCII. Lets the user choose a language before the game starts.
 */
#ifndef BOOTMENU_H
#define BOOTMENU_H

/* Run the boot menu (blocking). Lets user choose language.
 * Returns after user clicks "Start Game". */
void bootmenu_run(void);

#endif
