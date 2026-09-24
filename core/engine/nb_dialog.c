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
#include "settings.h"
#include "strutil.h"

/* Debug logging — shared macro in debug.h */
#include "debug.h"

/* Dialog text buffer (max 1KB). */
static char dialog_text_buf[1024];

/* Dialog paging state — private to this module. */
typedef struct {
    const char *text;
    int         text_offset;
    const char *charname;
    int         pending;   /* page live on screen; script must yield */
    int         page_start;   /* current page first byte offset (UTF-8 boundary) */
    int         page_end;     /* current page end byte offset (exclusive) */
    int         reveal_end;   /* bytes revealed so far (absolute offset) */
    int         reveal_active;/* 1 while this page is still revealing */
} DialogState;

static DialogState dialog_state;

/* Typewriter reveal clock (devdoc 106 plan A+ / 0.2.133, virtual clock
 * sunk to HAL in devdoc 107 / 0.2.134).
 *
 * Absolute expected position: characters revealed = speed * elapsed_ms / 1000
 * from a page baseline.  Each pass recomputes the target directly — no
 * per-char accumulator — so a single stalled pass cannot freeze the reveal and the
 * value is monotonic (only advances toward page_end).
 *
 * The elapsed input is the HAL virtual clock hal_wallclock_smooth_ms(): its
 * per-pass delta is bounded to [SMOOTH_CLOCK_MIN_MS, SMOOTH_CLOCK_MAX_MS]
 * (hal.h), so NP2kai's chunked DOS system time (frozen 3-6s, then
 * +1000..+6000ms jumps) neither stalls the reveal during the holes nor bursts
 * the page on catch-up.  Previously these bounds lived here as
 * REVEAL_PASS_MIN/MAX_MS (0.2.133); the single source of truth is now the
 * shared HAL clock, and the floor keeps flowing at pass cadence for every
 * micro-rhythm consumer (typewriter / animation / BGM). */
static unsigned long reveal_page_ms = 0;    /* virtual clock at page baseline */
static unsigned long reveal_char_count = 0; /* chars revealed on this page */
static int           reveal_armed = 0;      /* 0 = next pass records baseline */

#ifdef NAIZ_TRACE_CURSOR
static unsigned long nz_dlg_seq;
#endif

/* Advance off to the next UTF-8 character codepoint within [off, end].
 * Stray continuation bytes advance by one.  Returns end when data is
 * exhausted (never exceeds end). */
static int utf8_step_forward(int off, int end)
{
    unsigned char b;
    int step;

    if (off >= end) return end;
    b = (unsigned char)dialog_text_buf[off];
    if (b < 0x80) step = 1;
    else if ((b & 0xE0) == 0xC0) step = 2;
    else if ((b & 0xF0) == 0xE0) step = 3;
    else if ((b & 0xF8) == 0xF0) step = 4;
    else step = 1;   /* stray continuation byte */
    if (off + step > end) return end;
    return off + step;
}

/* Repaint the dialog composite so it shows only the revealed
 * [page_start, reveal_end) prefix of the current page (devdoc 105, plan A:
 * caller-side truncated string — draw_text core untouched).  The render
 * projection is synced to the truncated state so a later bg/cg recompose
 * redraws the reveal state.  Does not blit. */
static void dialog_render_reveal(void)
{
    char tmp[1024];
    int len = dialog_state.reveal_end - dialog_state.page_start;

    if (len < 0) len = 0;
    if (len > (int)sizeof(tmp) - 1) len = (int)sizeof(tmp) - 1;
    if (len > 0)
        memcpy(tmp, dialog_text_buf + dialog_state.page_start, (size_t)len);
    tmp[len] = '\0';

    layer_dialog_render_page(dialog_state.charname, tmp, 0);
    dialog_layer_store_render(dialog_state.charname, tmp, 0);
}

void dialog_show(const char *charname, const char *text)
{
    NB_DEBUG("dialog_show: enter\r\n");
    NB_DEBUG("dialog_show: charname=%s text_offset=%d\r\n",
             charname ? charname : "NULL", dialog_state.text_offset);

    if (dialog_state.text_offset < 0) {
        dialog_state.charname = charname;
        if (strlen(text) >= sizeof(dialog_text_buf) - 1) {
            NB_DEBUG("WARN: dialog text truncated at %d bytes\r\n", (int)sizeof(dialog_text_buf) - 1);
            hal_log("WARN: dialog text truncated\r\n");
        }
        str_copy(dialog_text_buf, sizeof(dialog_text_buf), text);
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

    /* A displayed page always keeps the script yielded: the page is left on
     * screen (self-recomposed by layer_dialog_recompose + dialog_render_*
     * projection, no per-frame redraw) until a wake advances or dismisses it.
     * No vm_pause_process() here — nb_process() owns the yield (stage 2 B). */
    dialog_state.pending = 1;

    layer_dialog_show();

    {
        /* Render the page into the dialog composite buffer (box + text) and
         * blit once.  store_render keeps a copy of the page parameters so a
         * later bg(){}/cg(){} change can redraw this page (devdoc 96 A). */
        int next;

        /* Start of the current page; the render below re-reads text_offset,
         * which keeps its paging meaning until it is rewritten after render. */
        dialog_state.page_start = dialog_state.text_offset;

        next = layer_dialog_render_page(dialog_state.charname, dialog_state.text,
                                        dialog_state.text_offset);

        NB_DEBUG("dialog_show: draw_text returned %d (vm_flags=0x%02X)\r\n",
                 next, vm_get_flags());

#ifdef AUTOEXIT
        /* Headless test build: never page — display the whole text at once
         * so the script can run to SCENE_STATUS_FINALEND without input. */
        dialog_state.text_offset = -1;
        dialog_state.text = NULL;
        dialog_layer_store_render(dialog_state.charname, dialog_state.text,
                                  dialog_state.page_start);
#else
        if (next >= 0) {
            dialog_state.text_offset = next;
            dialog_state.page_end = next;
            NB_DEBUG("dialog_show: text_offset set to %d\r\n",
                     dialog_state.text_offset);
        } else {
            dialog_state.text_offset = -1;
            dialog_state.text = NULL;
            dialog_state.page_end = (int)strlen(dialog_text_buf);
            NB_DEBUG("dialog_show: text fully displayed\r\n");
        }
        dialog_state.reveal_end = dialog_state.page_start;
        dialog_state.reveal_active =
            (settings_get_text_speed() != TEXT_SPEED_INSTANT) ? 1 : 0;
        if (dialog_state.reveal_active) {
            reveal_armed = 0;   /* recalibrate wall-clock baseline per page */
            /* Typewriter on: overwrite the just-painted full page with the
             * revealed prefix (empty at first — box + charname only). */
            dialog_render_reveal();
        } else {
            dialog_layer_store_render(dialog_state.charname, dialog_state.text,
                                      dialog_state.page_start);
        }
#endif
        dialog_layer_blit();
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

int nb_dialog_pending(void)
{
    return dialog_state.pending;
}

void nb_dialog_reveal_tick(void)
{
    unsigned long now, target;
    int speed;

    if (!dialog_state.reveal_active) return;

    /* Nothing to reveal when the page has no body (empty/consumed page):
     * the page_end <= page_start guard replaces the old text==NULL abort
     * that killed the reveal of the FINAL (or single) page — that page has
     * text==NULL by design while its body still needs revealing. */
    if (dialog_state.page_end <= dialog_state.page_start) {
        nb_dialog_reveal_finish();
        return;
    }

    speed = settings_get_text_speed();
    if (speed <= 0) {
        nb_dialog_reveal_finish();
        return;
    }

    /* Absolute expected position (devdoc 106 plan A+ / 0.2.134): the target
     * count is speed * elapsed / 1000 revealed from the page baseline,
     * recomputed each pass — so any one stalled pass cannot freeze the
     * reveal.  The elapsed input is the HAL smooth virtual clock (hal.h), whose
     * per-pass delta is bounded, so NP2kai's coarse chunked DOS clock neither
     * freezes a pass (floor) nor bursts the page on catch-up (ceiling); the
     * smooth clock is monotonic, so no previous-pass delta bookkeeping or
     * wrap-reanchor is needed.  The first pass after a page arms only records
     * the baseline (calibration, no advancement). */
    now = hal_wallclock_smooth_ms();
    if (!reveal_armed) {
        reveal_page_ms = now;
        reveal_char_count = 0;
        reveal_armed = 1;
        return;
    }

    target = (unsigned long)speed * (now - reveal_page_ms) / 1000UL;
    while (reveal_char_count < target &&
           dialog_state.reveal_end < dialog_state.page_end) {
        dialog_state.reveal_end = utf8_step_forward(
            dialog_state.reveal_end, dialog_state.page_end);
        reveal_char_count++;
    }

    dialog_render_reveal();
#ifdef NAIZ_TRACE_CURSOR
    hal_logf("[CT]%08lX r %d\r\n", ++nz_dlg_seq, dialog_state.reveal_end);
#endif
    dialog_layer_blit();
    if (dialog_state.reveal_end >= dialog_state.page_end)
        nb_dialog_reveal_finish();
}

int nb_dialog_reveal_active(void)
{
    return dialog_state.reveal_active;
}

void nb_dialog_reveal_finish(void)
{
    if (!dialog_state.reveal_active) return;
    dialog_state.reveal_active = 0;
    if (dialog_state.reveal_end != dialog_state.page_end) {
        dialog_state.reveal_end = dialog_state.page_end;
        dialog_render_reveal();
        dialog_layer_blit();
    }
}

void nb_dialog_dismiss(void)
{
    dialog_state.pending = 0;
    dialog_state.reveal_active = 0;   /* page consumed; stop any reveal */
}

void nb_dialog_reset(void)
{
    dialog_state.text_offset = -1;
    dialog_state.text = NULL;
    dialog_state.charname = NULL;
    dialog_state.pending = 0;
    dialog_state.page_start = 0;
    dialog_state.page_end = 0;
    dialog_state.reveal_end = 0;
    dialog_state.reveal_active = 0;
    reveal_armed = 0;
    reveal_page_ms = 0;
    reveal_char_count = 0;
}
