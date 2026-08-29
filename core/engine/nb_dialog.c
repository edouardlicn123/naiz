/*
 * nb_dialog.c — Dialog paging state machine for NB script engine.
 *
 * Extracted from nb.c (Phase 4.3 refactoring).
 */
#include <stdio.h>
#include <string.h>
#include "vm.h"
#include "render.h"
#include "scene_layers.h"
#include "hal.h"
#include "nb_dialog.h"

/* Debug logging — shared macro in debug.h */
#include "debug.h"

/* Dialog text buffer (max 1KB). */
static char dialog_text_buf[1024];

/* Dialog paging state — private to this module. */
typedef struct {
    const char *text;
    int         text_offset;
    const char *charname;
} DialogState;

static DialogState dialog_state;

void dialog_show(const char *charname, const char *text)
{
    int mw = LAYER_DIALOG_W - LAYER_DIALOG_INDENT - LAYER_DIALOG_RIGHT_INDENT;
    NB_DEBUG("dialog_show: enter\r\n");
    NB_DEBUG("dialog_show: charname=%s text_offset=%d\r\n",
             charname ? charname : "NULL", dialog_state.text_offset);

    if (dialog_state.text_offset < 0) {
        dialog_state.charname = charname;
        if (strlen(text) >= sizeof(dialog_text_buf) - 1) {
            NB_DEBUG("WARN: dialog text truncated at %d bytes\r\n", (int)sizeof(dialog_text_buf) - 1);
            hal_log("WARN: dialog text truncated\r\n");
        }
        strncpy(dialog_text_buf, text, sizeof(dialog_text_buf) - 1);
        dialog_text_buf[sizeof(dialog_text_buf) - 1] = '\0';
        {
            int slen = (int)strlen(dialog_text_buf);
            while (slen > 0 && ((unsigned char)dialog_text_buf[slen - 1] & 0xC0) == 0x80)
                dialog_text_buf[--slen] = '\0';
            if (slen == 1 && (dialog_text_buf[0] & 0x80))
                dialog_text_buf[--slen] = '\0';
        }
        dialog_state.text = dialog_text_buf;
        dialog_state.text_offset = 0;
    }

    layer_dialog_show();

    if (dialog_state.charname)
        draw_text(dialog_state.charname, 0,
                  LAYER_DIALOG_X + LAYER_DIALOG_INDENT, LAYER_DIALOG_Y + LAYER_DIALOG_HEADER_Y,
                   mw, LAYER_DIALOG_BOTTOM, 1, PAL_WHITE);

    {
        int next = draw_text(dialog_state.text, dialog_state.text_offset,
                             LAYER_DIALOG_X + LAYER_DIALOG_INDENT, LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y,
                             mw, LAYER_DIALOG_Y + LAYER_DIALOG_TEXT_Y + 60, 0, PAL_WHITE);

        NB_DEBUG("dialog_show: draw_text returned %d (vm_flags=0x%02X)\r\n",
                 next, vm_get_flags());

#ifdef AUTOEXIT
        /* Headless test build: never page — display the whole text at once
         * so the script can run to SCENE_STATUS_FINALEND without input. */
        dialog_state.text_offset = -1;
        dialog_state.text = NULL;
        vm_pause_process();
#else
        if (next >= 0) {
            dialog_state.text_offset = next;
            vm_pause_process();
            NB_DEBUG("dialog_show: text_offset set to %d, VMFLAG_PROCESS cleared\r\n",
                     dialog_state.text_offset);
        } else {
            dialog_state.text_offset = -1;
            dialog_state.text = NULL;
            vm_pause_process();
            NB_DEBUG("dialog_show: text fully displayed, VMFLAG_PROCESS cleared\r\n");
        }
#endif
    }
}

const char *nb_dialog_get_text(void)
{
    return dialog_state.text;
}

int nb_dialog_get_offset(void)
{
    return dialog_state.text_offset;
}

const char *nb_dialog_get_charname(void)
{
    return dialog_state.charname;
}

void nb_dialog_reset(void)
{
    dialog_state.text_offset = -1;
    dialog_state.text = NULL;
    dialog_state.charname = NULL;
}
