/*
 * nb_mainmenu.c — NB main-menu flow commands.
 *
 * Split from nb_commands.c: the main-menu command (continue/load/start
 * routing) and its placeholder menu stubs form a distinct feature track.
 * Registered in nb_commands.c cmd_table.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "vm.h"
#include "render.h"
#include "nb_internal.h"
#include "nb_commands.h"
#include "nb_vars.h"
#include "save.h"
#include "nb_saveload.h"
#include "nb.h"
#include "debug.h"
#include "settings.h"
#include "tr.h"
#include "image.h"
#include "scene_layers.h"
#include "ui.h"
#include "nb_asset_table.h"
#include "strutil.h"

/* Menu-parent scene (e.g. special.nb) consumed by sub-menus (cg view) on
 * exit; cleared whenever the main menu hands off to a sub-menu directly. */
static char g_menu_return[64];

void nb_set_menu_return(const char *scene)
{
    str_copy(g_menu_return, sizeof(g_menu_return),
             scene != NULL ? scene : "");
}

const char *nb_get_menu_return(void)
{
    return g_menu_return;
}

void cmd_mainmenu(int argc, const char **argv, const char *cmd_name)
{
    int mx, my, mw, sel;

    (void)cmd_name;
    if (argc < 5) { NB_DEBUG("mainmenu: not enough args (need x,y,w,h,opt...)\r\n"); return; }
    if (argc > NB_ARGS_MAX) {
        NB_DEBUG("WARN: mainmenu args=%d exceeds NB_ARGS_MAX (%d), truncated\r\n", argc, NB_ARGS_MAX);
        argc = NB_ARGS_MAX;
    }

    mx = atoi(argv[0]);
    my = atoi(argv[1]);
    mw = atoi(argv[2]);
    if (mw < 1) mw = 1;
    if (mx < 0 || mx >= LAYER_SCREEN_W || my < 0 || my >= LAYER_SCREEN_H) {
        NB_DEBUG("WARN: mainmenu coords (%d,%d) out of range, defaulting\r\n", mx, my);
        mx = 400; my = 200;
    }
    NB_DEBUG("mainmenu: pos=(%d,%d) cols=%d %d items argc=%d\r\n", mx, my, mw, argc - 4, argc);

    sel = menu_show(mx, my, mw, argc - 4, argv + 4);
    if (sel < 0 || sel >= argc - 4) return;
    NB_DEBUG("mainmenu: selected=%d (%s)\r\n", sel, argv[sel + 4]);

    if (strcmp(argv[sel + 4], "continue") == 0) {
        int slot, best_slot = -1;
        char best_ts[20] = "";
        SlotInfo si;
        for (slot = 0; slot < SAVE_SLOTS; slot++) {
            slot_info(slot, &si);
            if (si.exists && strcmp(si.timestamp, best_ts) > 0) {
                best_slot = slot;
                str_copy(best_ts, sizeof(best_ts), si.timestamp);
            }
        }
        if (best_slot >= 0)
            save_request(SAVE_OP_SLOT_LOAD, best_slot);
        else
            { nb_var_init(); scene_switch("nbook001.nb", SCENE_SWITCH_MENU); }
    } else if (strcmp(argv[sel + 4], "load") == 0) {
        save_request(SAVE_OP_CAPTURE_TEMP, -1);
        save_request(SAVE_OP_OPEN_LOAD, -1);
    } else if (strcmp(argv[sel + 4], "start") == 0) {
        nb_var_init();
        scene_switch("nbook001.nb", SCENE_SWITCH_MENU);
    } else if (strcmp(argv[sel + 4], "scenes") == 0) {
        hal_log("TODO: scene select\r\n");
    } else if (strcmp(argv[sel + 4], "special") == 0) {
        nb_set_menu_return("");
        scene_switch("special.nb", SCENE_SWITCH_MENU);
    } else if (strcmp(argv[sel + 4], "music") == 0) {
        hal_log("TODO: music room\r\n");
    } else if (strcmp(argv[sel + 4], "gallery") == 0) {
        nb_set_menu_return("");
        scene_switch("cgview.nb", SCENE_SWITCH_MENU);
    } else if (strcmp(argv[sel + 4], "settings") == 0) {
        hal_log("TODO: settings menu\r\n");
    } else if (strcmp(argv[sel + 4], "exit") == 0) {
        vm_set_finalend();
    }
}

void cmd_startsetting(int argc, const char **argv, const char *cmd_name)
{
    const char *old_lang;
    (void)argc; (void)argv; (void)cmd_name;

    old_lang = settings_get_lang();
    settings_menu_run();
    settings_save();

    if (strcmp(old_lang, settings_get_lang()) != 0) {
        /* nb_set_lang applies the full language-driven state (translation
         * table, CJK glyph font, blackletter style). */
        nb_set_lang(settings_get_lang());
    }
}

void cmd_settingmenu(int argc, const char **argv, const char *cmd_name)
{
    (void)argc; (void)argv; (void)cmd_name;
    NB_DEBUG("settingmenu: not implemented yet\r\n");
}

void cmd_musicmenu(int argc, const char **argv, const char *cmd_name)
{
    (void)argc; (void)argv; (void)cmd_name;
    NB_DEBUG("musicmenu: not implemented yet\r\n");
}
