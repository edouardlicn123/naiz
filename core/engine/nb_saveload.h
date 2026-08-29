#ifndef NB_SAVELOAD_H
#define NB_SAVELOAD_H

/* Save dialog menu: in-place UI within dialog area (used by cmd_mainmenu) */
void save_dialog_menu(void);

/* NB command handler: loadscene */
void cmd_loadscene(int argc, const char **argv, const char *cmd_name);

#endif
