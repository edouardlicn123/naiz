#ifndef NB_SAVELOAD_H
#define NB_SAVELOAD_H

#include "save.h"

/* Save dialog menu: in-place UI within dialog area (used by cmd_mainmenu) */
void save_dialog_menu(void);

/* NB command handler: loadscene */
void cmd_loadscene(int argc, const char **argv, const char *cmd_name);

/* Shared save-slot display label (chapter title, fall back to filename). */
const char *slot_chapter_label(const SlotInfo *si);

/*=== Save/load request funnel (single access point for save/load ops) =====*/

/* Every save/load operation (hotkey F5/F6/ESC + menu-internal save/load)
 * routes through save_request(); no caller invokes the save primitives or
 * the loadscen/mainmenu scene loads directly.  COOKS with slot == -1 keep
 * the current slot semantics of the underlying primitive. */
typedef enum {
    SAVE_OP_CAPTURE_TEMP = 0,   /* save_game_temp()               (returns 0/-1) */
    SAVE_OP_RESTORE_TEMP,       /* load_game_temp()               (returns 0/-1) */
    SAVE_OP_SLOT_SAVE,          /* save_game_slot(slot)           (always 0)     */
    SAVE_OP_SLOT_LOAD,          /* load_game_slot(slot)           (returns 0/-1) */
    SAVE_OP_OPEN_SAVE,          /* open in-dialog save menu       (F5)           */
    SAVE_OP_OPEN_LOAD,          /* open load-scene menu           (F6)           */
    SAVE_OP_OPEN_MAINMENU       /* return to the main menu        (ESC)          */
} SlotOp;

/* Execute one save/load request.  Returns 0 on success, nonzero on failure
 * (matching the underlying primitive; SAVE_OP_OPEN_* always return 0). */
int save_request(SlotOp op, int slot);

#endif
