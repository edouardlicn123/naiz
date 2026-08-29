#ifndef NB_COMMANDS_H
#define NB_COMMANDS_H

#include <stddef.h>

/* NB command dispatch: look up cmd_name in command table and execute handler. */
void nb_commands_dispatch(const char *cmd_name, int argc, const char **argv);

/* Public asset-key lookup (asset_map, then spr_asset_map). Returns id or -1. */
int  nb_asset_id(const char *key);

/* Handlers split into nb_scene.c / nb_question.c (registered in cmd_table). */
void cmd_scene(int argc, const char **argv, const char *cmd_name);
void cmd_question(int argc, const char **argv, const char *cmd_name);

/* Handlers split into nb_audio.c / nb_mainmenu.c (registered in cmd_table). */
void cmd_bgm(int argc, const char **argv, const char *cmd_name);
void cmd_sound(int argc, const char **argv, const char *cmd_name);
void cmd_voice(int argc, const char **argv, const char *cmd_name);
void cmd_mainmenu(int argc, const char **argv, const char *cmd_name);
void cmd_startsetting(int argc, const char **argv, const char *cmd_name);
void cmd_settingmenu(int argc, const char **argv, const char *cmd_name);
void cmd_cgvmenu(int argc, const char **argv, const char *cmd_name);
void cmd_musicmenu(int argc, const char **argv, const char *cmd_name);

/* Shared comma-field parser (defined in nb_commands.c), used by
 * nb_scene.c and nb_question.c.  Returns 1 on success.
 * NOTE: returns 0 when no ',' follows the current position, i.e. a LAST
 * field without a trailing comma is NOT consumed.  Callers wanting the
 * remainder of the segment as a final field must take *s directly
 * (see cmd_sceneconf), not call nb_next_field again. */
int nb_next_field(const char **s, char *buf, size_t bufsz);

#endif
