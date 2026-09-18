#ifndef NB_SAVELOAD_H
#define NB_SAVELOAD_H

#include "save.h"

/* Save dialog menu: in-place UI within dialog area (used by cmd_mainmenu) */
void save_dialog_menu(void);

/* NB command handler: loadscene */
void cmd_loadscene(int argc, const char **argv, const char *cmd_name);

/* Shared save-slot display label (chapter title, fall back to filename). */
const char *slot_chapter_label(const SlotInfo *si);

#endif
