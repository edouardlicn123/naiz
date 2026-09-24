/*
 * nb_internal.h — Shared declarations across nb.c, nb_menu.c, nb_cmd.c
 *
 * Provides cross-file visibility for the NB interpreter sub-modules.
 */
#ifndef NB_INTERNAL_H
#define NB_INTERNAL_H

#include <stdint.h>

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

/*=== Interaction primitive (ui_interact, implemented in nb_interact.c) ====*/

/* Blocking option-list interaction request.  labels must already be tr()'d
 * by the caller and remain valid for the duration of ui_interact().
 * n==0 is reserved for a pure confirm box (Yes/No drawn by the caller) —
 * Stage 1 keeps the save confirm boxes on menu_confirm_input() instead. */
typedef struct {
    const char *const *labels;   /* option labels (already translated) */
    int  n;                      /* option count */
    int  focus0;                 /* initial focus index */
} UiRequest;

/* Run one option-list interaction: draw the rows in the dialog band, then
 * dispatch mouse/keyboard input until a row is chosen (returns 0..n-1) or
 * the 600-frame timeout elapses and nothing was chosen (returns -1). */
int ui_interact(const UiRequest *req);

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

/* Parse one NB script line into cmd + args.  See nb_parser.c.
 * brace_arg returns the argv index of the '{...}' payload (or -1 when the
 * line carries none); the payload is always the last arg. */
int nb_parse_line(char *line, char *cmd, int cmd_size,
                  const char **args, int max_args,
                  int *brace_arg);

/* Argv index of the brace payload on the most recently parsed line, or -1
 * when that line carried none.  Lets commands distinguish cg(){key} from the
 * paren-only form cg(key) — the paren position is reserved for parameters. */
int  nb_get_last_brace_arg(void);

/* Parse one NB script line using ';' as the top-level argument delimiter
 * (multi-segment commands: question/scene).  See nb_parser.c. */
int nb_parse_line_semi(char *line, const char **args, int max_args);

/* Extract line line_num from the script buffer.  See nb_parser.c. */
void nb_get_line(int line_num, char *out, int out_size);

/*=== Shared function declarations =========================================*/

/* nb.c: core — nb_load moved to nb.h (public API) */

/* nb_mainmenu.c: menu-parent scene routing.  Sub-menus (dlgview) read the
 * parent scene via nb_get_menu_return(); empty falls back to mainmenu.nb. */
void nb_set_menu_return(const char *scene);
const char *nb_get_menu_return(void);

/* DialogState + dialog_show moved to nb_dialog.h */

/* nb_menu.c: menu UI */
#define MENU_PAL_WHITE  250
#define MENU_PAL_YELLOW 251

int  menu_show(int mx, int my, int cols, int argc, const char **argv);
void menu_save_item_palette(void);
void menu_restore_item_palette(void);
void menu_consume_key(unsigned char key);

/* Shared menu-exit contract: close the menu layer (base snapshot back to
 * VRAM), flush the mouse, restore the shared menu palette. */
void menu_finish(void);

/* Page navigation + Back-button chrome (shared by the paged save/load and
 * CG-gallery menus).  Draw helpers must be called between
 * menu_layer_begin_draw() and menu_layer_commit(); with the layer closed
 * (OOM fallback) they degrade to direct VRAM. */
int  menu_pagecount(int count, int per);
void menu_pagenav_draw(int arrows_y, int count_y, uint8_t fg,
                       int page, int total_pages);
int  menu_page_hit(int arrows_y, int mx, int my);   /* 0 none / 1 prev / 2 next */
void menu_back_draw(int y, int focus, int emboss, uint8_t idle_fg);
int  menu_back_hit(int y, int mx, int my);

/* Shared Yes/No confirm state machine.  Consumes one frame of confirm-mode
 * input (keyboard Left/Right toggle + Enter/Space/XFER + Esc, mouse Yes/No
 * button clicks).  cfg holds caller geometry + an action callback:
 *   action(slot, &fail)  returns 1 = operation succeeded, menu should exit;
 *                        0 = operation done, stay in the menu (refresh list);
 *                        -1 = operation failed (MENU_CONFIRM_FAILED). */
enum {
    MENU_CONFIRM_NONE = 0,
    MENU_CONFIRM_TOGGLE = 1,  /* Yes/No focus toggled — redraw confirm */
    MENU_CONFIRM_CLOSED = 2,  /* confirm cancelled/answered-no — redraw list */
    MENU_CONFIRM_EXIT = 3,    /* action succeeded and wants to leave the menu */
    MENU_CONFIRM_FAILED = 4   /* action reported failure — redraw + error box */
};
typedef struct {
    int yes_x0;                 /* Yes button rect (60 px wide from x0) */
    int no_x0;                  /* No button rect (60 px wide from x0) */
    int y0, y1;                 /* button band */
    int mouse_yes_always;       /* mouse Yes click confirms regardless of focus */
    int (*action)(int slot);    /* performs the confirmed operation */
} MenuConfirmCfg;
int menu_confirm_input(int *confirm_yes, int slot, const MenuConfirmCfg *cfg);

#endif
