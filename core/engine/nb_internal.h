/*
 * nb_internal.h — Shared declarations across nb.c, nb_menu.c, nb_cmd.c
 *
 * Provides cross-file visibility for the NB interpreter sub-modules.
 */
#ifndef NB_INTERNAL_H
#define NB_INTERNAL_H

/* Public NB API (nb_load lives here) is visible to all sub-modules. */
#include "nb.h"

/*=== Constants ============================================================*/

#define NB_LINE_MAX      256
#define NB_ARGS_MAX      20
#define NB_BUF_SIZE      32768
#define NB_FILENAME_MAX  64

#define MENU_ITEM_H    20
#define QUESTION_INDENT  8

#define SPRITE_X_LEFT    27
#define SPRITE_X_CENTER  220
#define SPRITE_X_RIGHT   413

/*=== Shared declarations ==================================================*/

/*=== Global interpreter state =============================================*/

/* Interpreter state is owned by nb.c.  Direct field access from other
 * translation units is forbidden; use the narrow accessors below. */

/* 1 when the runtime language is CJK (chi/jpn/kor) — blackletter is Latin-only */
int  nb_lang_is_cjk(void);

/* Narrow state accessors (implemented in nb.c).
 * Direct reads/writes of nb.<field> outside nb.c are not allowed. */
void nb_set_scene_conf(const char *title, const char *type);
void nb_set_last_choice(int choice);
const char *nb_get_filename(void);
/* Return the loaded script buffer (read-only), used by the line parser. */
const char *nb_get_buffer(void);

/*=== Line parser (implemented in nb_parser.c) ==============================*/

/* Parse one NB script line into cmd + args.  See nb_parser.c. */
int nb_parse_line(char *line, char *cmd, int cmd_size,
                  const char **args, int max_args);

/* Parse one NB script line using ';' as the top-level argument delimiter
 * (multi-segment commands: question/scene).  See nb_parser.c. */
int nb_parse_line_semi(char *line, const char **args, int max_args);

/* Extract line line_num from the script buffer.  See nb_parser.c. */
void nb_get_line(int line_num, char *out, int out_size);

/*=== Shared function declarations =========================================*/

/* nb.c: core — nb_load moved to nb.h (public API) */

/* DialogState + dialog_show moved to nb_dialog.h */

/* nb_menu.c: menu UI */
#define MENU_PAL_WHITE  250
#define MENU_PAL_YELLOW 251

int  menu_show(int mx, int my, int cols, int argc, const char **argv);
void menu_save_item_palette(void);
void menu_restore_item_palette(void);
void menu_consume_key(unsigned char key);

#endif
