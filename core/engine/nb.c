/*
 * NB interpreter — pure-text script engine for Naiz
 * Replaces scene.c binary VM with text-based .nb script execution.
 * Reference: devdocs/0.1版开发文档总结.html#doc-21
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "vm.h"
#include "scene_layers.h"
#include "render.h"
#include "settings.h"
#include "hal.h"
#include "tr.h"
#include "nb_internal.h"
#include "nb_dialog.h"
#include "nb_vars.h"
#include "nb_anim.h"   /* ANI animation support */
#include "save.h"

/* Known unimplemented menu commands: continue, load, scenes,
 * special, music, cg, settings. Their handlers log and return. */

/*=== Debug macros ========================================================*/

/* Debug logging — shared macro in debug.h (defines NB_DEBUG_ENABLE from NAIZ_DEBUG) */
#include "debug.h"

/* Constants moved to nb_internal.h (NB_LINE_MAX, NB_ARGS_MAX, NB_BUF_SIZE, NB_FILENAME_MAX, MENU_ITEM_H, SPRITE_X_*) */

/*=== Interpreter state ===================================================*/

/* Interpreter state structure — private to nb.c.  Other modules use the
 * nb_* accessors declared in nb_internal.h (direct field access is
 * forbidden outside this file). */
typedef struct {
    char   filename[NB_FILENAME_MAX];
    char   buf[NB_BUF_SIZE];
    int    num_lines;
    int    pc;
    char   lang[8];
    int    last_choice;
    char   chapter_title[64];
    char   scene_type[16];
} NbState;

static NbState nb;  /* Interpreter state — owned exclusively by nb.c */

/* Set the chapter title string (metadata, saved to save files). */
static void nb_set_chapter_title(const char *title)
{
    strncpy(nb.chapter_title, title, sizeof(nb.chapter_title) - 1);
    nb.chapter_title[sizeof(nb.chapter_title) - 1] = '\0';
}

/* Set scene configuration (chapter title + scene type).
 * type: "normal" / "cg" / "menu".  Invalid/empty type falls back to "normal". */
void nb_set_scene_conf(const char *title, const char *type)
{
    nb_set_chapter_title(title);
    if (type && strcmp(type, "normal") != 0 &&
        strcmp(type, "cg") != 0 && strcmp(type, "menu") != 0) {
        hal_log("WARN: sceneconf: unknown type, fallback to normal\r\n");
        type = "normal";
    }
    if (type)
        strncpy(nb.scene_type, type, sizeof(nb.scene_type) - 1);
    else
        nb.scene_type[0] = '\0';
    nb.scene_type[sizeof(nb.scene_type) - 1] = '\0';
}

/* Remember the last question choice (or -1 when unanswered). */
void nb_set_last_choice(int choice)
{
    nb.last_choice = choice;
}

/* Return the currently loaded script filename. */
const char *nb_get_filename(void)
{
    return nb.filename;
}

/* Return the loaded script buffer (read-only).  Used by the line parser. */
const char *nb_get_buffer(void)
{
    return nb.buf;
}

/* Return 1 when the runtime language is CJK (chi/jpn/kor) — blackletter
 * covers Latin only, so it is disabled for CJK languages. */
int nb_lang_is_cjk(void)
{
    return strcmp(nb.lang, "chi") == 0
        || strcmp(nb.lang, "jpn") == 0
        || strcmp(nb.lang, "kor") == 0;
}

#include "nb_commands.h"

/*=== Core: nb_init / nb_load / nb_process ================================*/

/*
 * nb_init — NB engine initialization.
 * Sequence: clear state -> read settings -> init translation table
 *   -> button/dialog palette -> load logo.nb
 * @return 0 (currently never fails)
 */
int nb_init(void)
{
    hal_log("[NB] nb_init start\r\n");
    memset(&nb, 0, sizeof(nb));
    nb_dialog_reset();

    settings_load();
    /* Sync the language into the NB state (owned here), then inject the
     * blackletter dialog style into the render layer. Blackletter is
     * Latin-only, so it applies only for non-CJK languages. */
    strncpy(nb.lang, settings_get_lang(), sizeof(nb.lang) - 1);
    nb.lang[sizeof(nb.lang) - 1] = '\0';
    text_set_blackletter(settings_get_blackletter_dialog() && !nb_lang_is_cjk());
    tr_init(nb.lang);

    /* Fallback: if chosen language loaded no translations, revert to 'eng'. */
    if (tr_get_count() == 0 && strcmp(nb.lang, "eng") != 0) {
        NB_DEBUG("WARN: no translations for lang='%s', falling back to 'eng'\r\n", nb.lang);
        tr_init("eng");
    }

    nb_var_init();

    nb_load("logo.nb");
    vm_request_process();
    vm_delay_reset();

    NB_DEBUG("init: lang=%s dlgstyle=%d\r\n", nb.lang, dlg_get_style());
    return 0;
}

/*
 * nb_load — Load and switch to a new NB script file.
 * Sequence: open file -> read lines into nb.buf -> record total lines
 *   -> clear screen + reset layers/keyboard/dialog state
 * @param filename  .nb script file path (relative to ENGINE.EXE)
 * Side effect: sets VMFLAG_SCENE_CHANGED | VMFLAG_PROCESS
 */
void nb_load(const char *filename)
{
    FILE *f;
    int pos;
    int nb_old_skip;

    f = fopen(filename, "r");
    if (!f) {
        hal_log("ERROR: cannot open file\r\n");
        vm_set_error();
        return;
    }

    pos = 0;
    nb.num_lines = 0;
    nb.pc = 0;
    nb_old_skip = (strcmp(nb.filename, "logo.nb") == 0 || strcmp(nb.filename, "op.nb") == 0);
    strncpy(nb.filename, filename, NB_FILENAME_MAX - 1);
    nb.filename[NB_FILENAME_MAX - 1] = '\0';
    {
        int incomplete = 0, n;
        while (pos < NB_BUF_SIZE - 1 && fgets(nb.buf + pos, NB_BUF_SIZE - pos, f)) {
            if (!incomplete) nb.num_lines++;
            n = (int)strlen(nb.buf + pos);
            incomplete = (n > 0 && nb.buf[pos + n - 1] != '\n');
            pos += n;
            if (pos >= NB_BUF_SIZE - 1) {
                /* Known limit: scripts must fit in NB_BUF_SIZE (32 KB).
                 * Any trailing lines beyond the buffer are dropped with a
                 * WARN; num_lines only counts complete lines, so the script
                 * halts cleanly rather than mis-executing partial lines. */
                {
                    char _b[160];
                    snprintf(_b, sizeof(_b), "WARN: '%s' truncated at %d bytes (max %d)\r\n",
                             filename, pos, NB_BUF_SIZE);
                    hal_log(_b);
                }
                break;
            }
        }
    }
    fclose(f);

    /* Full scene reset (skip transition for logo/op — both entering and exiting) */
    scene_end(nb_old_skip || strcmp(filename, "logo.nb") == 0 || strcmp(filename, "op.nb") == 0);
    nb_dialog_reset();
    nb.chapter_title[0] = '\0';
    nb.scene_type[0] = '\0';

    { char _b[160]; snprintf(_b, sizeof(_b), "[LOAD] nb_load '%s' (%d lines)\r\n", filename, nb.num_lines); hal_log(_b); }
    vm_request_scene_change();
}

/* Menu / non-game scenes where F5/F6 save hotkeys must be disabled.
 * Scene type is declared per-scene via sceneconf(..., menu). */
int nb_is_menu_scene(void)
{
    return nb.scene_type[0] != '\0' && strcmp(nb.scene_type, "menu") == 0;
}

/* Copy interpreter filename/lang/chapter_title into caller buffers. */
void nb_get_state(char *filename, int fn_size,
                  char *lang, int lang_size,
                  char *title, int title_size)
{
    strncpy(filename, nb.filename, fn_size - 1);
    filename[fn_size - 1] = '\0';
    strncpy(lang, nb.lang, lang_size - 1);
    lang[lang_size - 1] = '\0';
    strncpy(title, nb.chapter_title, title_size - 1);
    title[title_size - 1] = '\0';
}

/* Restore the runtime language from a saved snapshot.  Reloads the
 * translation table so the language switch takes effect immediately. */
void nb_set_lang(const char *lang)
{
    strncpy(nb.lang, lang, sizeof(nb.lang) - 1);
    nb.lang[sizeof(nb.lang) - 1] = '\0';
    tr_init(nb.lang);
}

/*
 * nb_process — NB engine main execution loop (called each frame).
 *
 * Per-frame flow:
 *   1) If dialog has paging (text_offset >= 0) -> continue drawing, pause
 *   2) Check VMFLAG_FINALEND/ERROR -> exit
 *   3) Check if pc exceeds total lines -> stop
 *   4) Read next line -> skip empty/'#' comments -> strip inline comments
 *   5) parse_line -> dispatch via cmd_table to handler
 *   6) Scene change flag -> break loop
 *
 * @return 0=normal, SCENE_STATUS_FINALEND=exit, SCENE_STATUS_ERROR=error
 */
int nb_process(void)
{
    char line[NB_LINE_MAX];          /* Current line buffer */
    const char *args[NB_ARGS_MAX];   /* Parsed argument pointer array */
    int argc;                        /* Argument count */
    char cmd_name[64];               /* Command name */

    /* NOTE: no per-call logging here — nb_process() runs every frame at 60Hz;
     * serial_puts costs ~200 port-I/O traps per byte and would throttle the
     * whole loop to a few Hz. Event logs ([LOAD]/[INPUT]/lifecycle) only. */

    while (vm_get_flags() & VMFLAG_PROCESS) {
        /* waitanima hold: stay paused until the animation terminates;
         * anim_stop_internal() re-requests processing when it ends, so
         * spurious wakeups (input, delay expiry) can never skip the wait. */
        if (anim_waiting()) {
            vm_pause_process();
            break;
        }

        /* Handle multi-page dialog continuation first. */
        if (nb_dialog_get_offset() >= 0 && nb_dialog_get_text()) {
            dialog_show(nb_dialog_get_charname(), nb_dialog_get_text());
            hal_mouse_update();
            continue;
        }

        /* Check termination/error flags. */
        if (vm_get_flags() & (VMFLAG_FINALEND | VMFLAG_ERROR))
            break;

        /* Check if script has finished. */
        if (nb.pc >= nb.num_lines) {
            if (nb.num_lines == 0)
                { char _b[160]; snprintf(_b, sizeof(_b), "[LOAD] ERROR: script '%s' has 0 lines, halting\r\n", nb.filename); hal_log(_b); }
            else
                NB_DEBUG("WARN: pc=%d beyond end, stopping\r\n", nb.pc);
            vm_pause_process();
            break;
        }

        nb_get_line(nb.pc, line, sizeof(line));
        NB_DEBUG("nb_process: line[%d]: %s\r\n", nb.pc, line);
        nb.pc++;
        if (strlen(line) >= sizeof(line) - 1) {
            NB_DEBUG("WARN: line %d truncated (max %d bytes), skipping\r\n", nb.pc - 1, (int)sizeof(line) - 1);
            continue;
        }

        /* Skip empty lines and full-line comments. */
        if (line[0] == '\0' || line[0] == '#') {
            NB_DEBUG("nb_process: skipping empty/comment line\r\n");
            continue;
        }

        /* Strip inline comments (# outside {...} only). */
        {
            char *p = line, *hash = NULL;
            int depth = 0;
            while (*p) {
                if (*p == '{') depth++;
                if (*p == '}' && depth > 0) depth--;
                if (depth == 0 && *p == '#') { hash = p; break; }
                p++;
            }
            if (hash) *hash = '\0';
        }

        /* Save raw line before parse_line (commas/semicolons still intact). */
        {
            char line_copy[NB_LINE_MAX];
            strncpy(line_copy, line, sizeof(line_copy) - 1);
            line_copy[sizeof(line_copy) - 1] = '\0';

            /* Parse command and arguments (comma-separated). */
            argc = nb_parse_line(line, cmd_name, sizeof(cmd_name),
                              args, NB_ARGS_MAX);

            if (argc < 0) {
                NB_DEBUG("ERROR: parse failed: %s\r\n", line);
                continue;
            }

            /* For question/scene: re-parse with ';' as the top-level
             * delimiter (segments are themselves comma-delimited). */
            if (strcmp(cmd_name, "question") == 0 ||
                strcmp(cmd_name, "scene") == 0) {
                int semi_argc = nb_parse_line_semi(line_copy, args,
                                                   NB_ARGS_MAX);
                if (semi_argc >= 0) argc = semi_argc;
            }

            NB_DEBUG("exec[%d]: %s\r\n", nb.pc - 1, line);

            nb_commands_dispatch(cmd_name, argc, args);
        }

        hal_mouse_update();

        /* Scene change: break current frame, restart new scene next time. */
        if (vm_get_flags() & VMFLAG_SCENE_CHANGED) {
            NB_DEBUG("[LOAD] scene changed, clearing flag and breaking\r\n");
            vm_clear_scene_change();
            break;
        }
    }

    /* Return status to main loop. */
    if (vm_get_flags() & VMFLAG_FINALEND) return SCENE_STATUS_FINALEND;
    if (vm_get_flags() & VMFLAG_ERROR)    return SCENE_STATUS_ERROR;
    return 0;
}
