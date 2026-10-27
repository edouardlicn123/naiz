#ifndef NB_COMMANDS_H
#define NB_COMMANDS_H

#include <stddef.h>

/* Command metadata flags (shared with nb_process for yield-after-display logic).
 * See nb_commands.c cmd_table for per-command assignments. */
enum {
    CMD_BLOCKING         = 0x01,   /* [doc-only] handler blocks until script may continue */
    CMD_NEEDS_INPUT      = 0x02,   /* [doc-only] waits for user input (keyboard/mouse) */
    CMD_TOUCHES_DISPLAY  = 0x04,   /* writes VRAM / layers / palette / animation */
    CMD_TOUCHES_AUDIO    = 0x08,   /* starts/stops audio */
    CMD_TERMINATES_SCENE = 0x10    /* switches scene (scene_switch) */
};

/* NB command dispatch: look up cmd_name in command table and execute handler.
 * Returns the command's metadata flags (0 if unknown). */
unsigned char nb_commands_dispatch(const char *cmd_name, int argc, const char **argv);

/* Public asset-key lookup (asset_map, then spr_asset_map). Returns id or -1. */
int  nb_asset_id(const char *key);

/* Resolve a display command's brace key (cg/bg/char) to the IMAGE.DAT id it
 * will show, for cache prefetch (devdoc 131 方案 D).  `expr` is the char
 * command's expression argument (NULL/"" = default).  Returns id or -1. */
int  nb_prefetch_key(const char *cmd, const char *key, const char *expr);

/* Handlers split into nb_scene.c / nb_question.c (registered in cmd_table). */
void cmd_scene(int argc, const char **argv, const char *cmd_name);
void cmd_question(int argc, const char **argv, const char *cmd_name);

/* CG display command (nb_cg.c, registered in cmd_table). */
void cmd_cg(int argc, const char **argv, const char *cmd_name);

/* Handlers split into nb_audio.c / nb_mainmenu.c (registered in cmd_table). */
void cmd_bgm(int argc, const char **argv, const char *cmd_name);
void cmd_sound(int argc, const char **argv, const char *cmd_name);
void cmd_voice(int argc, const char **argv, const char *cmd_name);
void cmd_mainmenu(int argc, const char **argv, const char *cmd_name);
void cmd_startsetting(int argc, const char **argv, const char *cmd_name);
void cmd_settingmenu(int argc, const char **argv, const char *cmd_name);
void cmd_cgvmenu(int argc, const char **argv, const char *cmd_name);
void cmd_musicmenu(int argc, const char **argv, const char *cmd_name);
void cmd_specialmenu(int argc, const char **argv, const char *cmd_name);

/* Shared comma-field parser (defined in nb_commands.c), used by
 * nb_scene.c and nb_question.c.  Returns 1 on success.
 * NOTE: returns 0 when no ',' follows the current position, i.e. a LAST
 * field without a trailing comma is NOT consumed.  Callers wanting the
 * remainder of the segment as a final field must take *s directly
 * (see cmd_sceneconf), not call nb_next_field again.
 * ESCAPES: "\," is a literal comma inside a field and "\\" a literal
 * backslash; any other "\x" is preserved verbatim.  A question option label
 * containing a comma must therefore write it as "\," — e.g.
 *   question(Pick one?;Ira\, Jr.,bond_ira,+,1)
 * naiz_lib.nb_line.next_field() mirrors this exactly for the i18n extractor. */
int nb_next_field(const char **s, char *buf, size_t bufsz);

/* nb_has_field_delim — 1 when the segment still contains an UNESCAPED comma
 * (another "label,var,..." field follows), 0 when only a final field remains.
 * Callers that peek for the next delimiter must use this rather than
 * strchr(..., ',') so an escaped comma is not read as a boundary. */
int nb_has_field_delim(const char *s);

#endif
