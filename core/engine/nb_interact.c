/*
 * nb_interact.c — blocking option-list interaction primitive (ui_interact).
 *
 * Stage 1 of devdoc 103: cmd_question's option blocking loop converges here
 * so the choice UI is a single reusable interaction point.  The dialog-band
 * option rendering, hit testing and keyboard navigation are preserved
 * byte-for-byte from nb_question.c; only the "loop + input read" was
 * relocated into ui_interact().
 *
 * Labels must already be tr()'d by the caller (see UiRequest in
 * nb_internal.h); the caller owns palette save/restore around the call.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "render.h"
#include "ui.h"
#include "scene_layers.h"
#include "hal.h"
#include "nb_internal.h"
#include "tr.h"
#include "frame.h"

/* Debug logging — shared macro in debug.h */
#include "debug.h"
#include "input_boundary.h"

/* Hit-test the option rows within the dialog content band.  Mirrors the
 * legacy question_hittest geometry (base_x + 448 width). */
static int interact_hittest(int mx, int my, int num_opts)
{
    int i;
    int base_x = LAYER_DIALOG_CONTENT_X + QUESTION_INDENT;
    int base_y = LAYER_DIALOG_CONTENT_Y;
    for (i = 0; i < num_opts; i++) {
        int y0 = base_y + i * MENU_ITEM_H;
        if (mx >= base_x && mx < base_x + 448 &&
            my >= y0    && my < y0 + MENU_ITEM_H)
            return i;
    }
    return -1;
}

/* Draw one option row: emboss outline + label.  Mirrors the legacy
 * question_draw_opt rendering. */
static void interact_draw_opt(const char *label, int i, int y, int mw, int highlighted)
{
    int pal = highlighted ? MENU_PAL_YELLOW : MENU_PAL_WHITE;
    int x = LAYER_DIALOG_CONTENT_X + QUESTION_INDENT;
    int opt_y = y + i * MENU_ITEM_H;
    draw_rounded_emboss_outline(x - 2, opt_y - 1, mw + 4, MENU_ITEM_H, 2,
                                BTN_HIGHLIGHT_IDX, BTN_SHADOW_IDX);
    draw_text(label, 0, x, opt_y, mw - 8, opt_y + MENU_ITEM_H, 1, pal);
}

/* Safety valve: how long a blocking choice may wait before giving up.
 * Time-based, not frame-based — the frame pump can run far above the display
 * rate (VSYNC not emulated), which made the old "600 frames" expire in
 * well under a second and skip the question as if it were auto-answered.
 *
 * Timeout SEMANTICS (devdoc 211 §7.1): -1 used to mean BOTH "cancel" and
 * "timeout", and every caller treated it as "continue with the script" —
 * so any clock error silently skipped the question.  The separation:
 *   UI_INTERACT_CANCEL   (-1)  invalid request / explicit cancel
 *   UI_INTERACT_TIMEOUT  (-2)  safety valve expired (only after the valve
 *                              re-armed itself several times, see below)
 * On expiry the list is REDRAWN and the deadline re-armed in place — the
 * player sees the choice is still waiting instead of the story moving on.
 * Only after UI_INTERACT_MAX_TIMEOUTS consecutive re-arms (a truly absent
 * player; also keeps automated runs finite) does -2 come out, and the
 * callers keep their "continue after the line" behaviour for that case.
 */
#define UI_INTERACT_TIMEOUT_MS  30000UL
#define UI_INTERACT_TIMEOUT     (-2)
#define UI_INTERACT_CANCEL      (-1)
#define UI_INTERACT_MAX_TIMEOUTS  3

/* Deadline drift guard (devdoc 211 §7.2).  The deadline is computed from the
 * SMOOTH clock, but the smooth clock is a rate-calibrated metronome, not a
 * wall clock (its whole contract is "rate matters, phase does not" —
 * vclock.h).  If the wall clock and the smooth clock ever disagree by more
 * than this, the deadline is re-based from the wall clock; a 30 s wait must
 * not silently become 8 s because the metronome ran hot. */
#define UI_INTERACT_DRIFT_LIMIT_MS  2000UL

/* Input-ready gate: ignore ALL input (mouse clicks and the confirm keys)
 * for this long after the option list opens.  Two stale sources reach the
 * list otherwise:
 *   - the emulator turns the key press that advanced the previous line
 *     into a synthetic left-button edge, which picks the row under the
 *     centred pointer;
 *   - a still-held confirm key keeps emitting auto-repeat MAKE codes.
 * While the gate is open every such event is consumed and thrown away, and
 * a confirm key that is still down moves the gate forward, so the player
 * must actually release the key before a choice can register.  Time-based,
 * so it does not shrink when the frame pump runs fast. */
#define UI_INTERACT_INPUT_READY_MS  400UL

int ui_interact(const UiRequest *req)
{
    int sel;
    int i, y, mw, n;
    unsigned long deadline;
    unsigned long ready_at;
    int timeouts = 0;

    if (!req || req->n < 1 || !req->labels) {
        NB_DEBUG("interact: invalid request\r\n");
        return UI_INTERACT_CANCEL;
    }

    n = req->n;
    sel = (req->focus0 >= 0 && req->focus0 < n) ? req->focus0 : 0;
    mw = LAYER_DIALOG_CONTENT_W;
    y = LAYER_DIALOG_CONTENT_Y;

    /* Initial option list render (focus highlighted). */
    for (i = 0; i < n; i++)
        interact_draw_opt(req->labels[i], i, y, mw, i == sel);

    input_drain_boundary();
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);
    deadline = hal_wallclock_smooth_ms() + UI_INTERACT_TIMEOUT_MS;
    ready_at = hal_wallclock_smooth_ms() + UI_INTERACT_INPUT_READY_MS;

    for (;;) {
        unsigned long now = hal_wallclock_smooth_ms();
        unsigned long wall = hal_wallclock_ms();

        /* Drift guard: re-base the deadline from the REAL clock when the two
         * disagree badly.  Covers both directions — a hot metronome would
         * fire the valve early (skip the question), a stalled one would hold
         * it open for minutes. */
        {
            long drift = (long)wall - (long)now;
            if (drift < 0) drift = -drift;
            if (drift > (long)UI_INTERACT_DRIFT_LIMIT_MS) {
                NB_DEBUG("interact: clock drift %ld ms, re-basing deadline\r\n",
                         drift);
                deadline = wall + UI_INTERACT_TIMEOUT_MS;
                ready_at = wall + UI_INTERACT_INPUT_READY_MS;
            }
        }

        if (now >= deadline) {
            /* devdoc 211 §7.1: a timeout no longer skips the choice.  Redraw
             * the list (the focus flash is the visible "still waiting") and
             * re-arm.  Only the safety valve's repeated expiry returns, and
             * it returns TIMEOUT (-2), never CANCEL (-1). */
            timeouts++;
            NB_DEBUG("interact: timeout #%d\r\n", timeouts);
            if (timeouts >= UI_INTERACT_MAX_TIMEOUTS) {
                NB_DEBUG("interact: safety valve expired\r\n");
                return UI_INTERACT_TIMEOUT;
            }
            for (i = 0; i < n; i++)
                interact_draw_opt(req->labels[i], i, y, mw, i == sel);
            deadline = hal_wallclock_smooth_ms() + UI_INTERACT_TIMEOUT_MS;
            continue;
        }

        engine_frame_pump();  /* keep BGM/PCM + clock ticking while waiting */
        hal_kbd_update();
        hal_mouse_update();
        hal_mouse_recenter_if_idle();

        /* Input-ready gate: swallow clicks and key events that were already
         * in flight when the list opened, and keep extending the gate while a
         * confirm key is physically held so its auto-repeat cannot pick the
         * focused option. */
        if (now < ready_at) {
            int held = 0;
            (void)hal_mouse_was_clicked(HAL_MOUSE_LBUTTON);
            (void)hal_kbd_is_down(KC_UP);
            (void)hal_kbd_is_down(KC_DOWN);
            if (hal_kbd_is_down(KC_SPACE))  held = 1;
            if (hal_kbd_is_down(KC_ENTER))  held = 1;
            if (hal_kbd_is_down(KC_XFER))   held = 1;
            if (held)
                ready_at = now + UI_INTERACT_INPUT_READY_MS;
            hal_mouse_draw_cursor();
            continue;
        }

        /* devdoc 211 §7.4: hit-test with the EVENT's coordinates, not the
         * current pointer position — a stale queued click must not pick the
         * row the pointer happens to be over now. */
        {
            int cx, cy;
            if (hal_mouse_pop_click(HAL_MOUSE_LBUTTON, &cx, &cy)) {
                int hit = interact_hittest(cx, cy, n);
                if (hit >= 0) {
                    NB_DEBUG("interact: mouse sel=%d (%d,%d)\r\n", hit, cx, cy);
                    return hit;
                }
            }
        }

        if (hal_kbd_is_down(KC_UP) && sel > 0) {
            interact_draw_opt(req->labels[sel], sel, y, mw, 0);
            sel--;
            interact_draw_opt(req->labels[sel], sel, y, mw, 1);
            menu_consume_key(KC_UP);
        }
        if (hal_kbd_is_down(KC_DOWN) && sel < n - 1) {
            interact_draw_opt(req->labels[sel], sel, y, mw, 0);
            sel++;
            interact_draw_opt(req->labels[sel], sel, y, mw, 1);
            menu_consume_key(KC_DOWN);
        }
        if (hal_kbd_is_down(KC_SPACE) || hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_XFER)) {
            NB_DEBUG("interact: keyboard sel=%d\r\n", sel);
            return sel;
        }

        hal_mouse_draw_cursor();
    }
}
