/*
 * transition_blinds.c — Blinds (strip sweep) transition family.
 *
 * Split from transition.c: sweeps N thin parallel strips that grow from
 * thin bars to full black in lockstep; the scene stays visible until the
 * front covers it.
 */
#include "render.h"
#include "transition.h"
#include "transition_internal.h"

/* Strip geometry shared by the blinds family.  The screen shows N thin
 * parallel strips: the black front grows from 0 to one strip period over
 * the frames, so every strip is visible as a thin growing bar.  The strip
 * period is derived from the primary axis (V/D: w, H: h) so all variants
 * render the same N visible strips. */
#define PBLINDS_BANDS  20    /* Number of visible strips (N). */

/* Advance the blinds black-front sweep by one step.
 * Every pixel gets a strip position along its primary axis:
 *   VBLINDS  : (col - x)
 *   HBLINDS  : (row - y)
 *   DBLINDS  : (col - x) + row            (forward diagonal)
 *   RDBLINDS : (col - x) + (h - 1 - row)  (reverse diagonal)
 * A pixel is painted 'color' (normally black) once
 * (strip position % period) < front, so N thin parallel bars grow in
 * lockstep from the leading edge and merge to full black.  Only the newly
 * covered cells are drawn each frame. */
void transition_pblinds_wipe(int x, int y, int w, int h,
                             unsigned char type,
                             int step, int frames,
                             unsigned char color)
{
    int period, front_prev, front_cur, delta;

    period = (type == TRANSITION_HBLINDS) ? (h / PBLINDS_BANDS)
                                          : (w / PBLINDS_BANDS);
    if (period < 1) period = 1;

    front_prev = step * period / frames;
    front_cur  = (step + 1) * period / frames;
    if (front_cur > period) front_cur = period;
    delta = front_cur - front_prev;
    if (delta <= 0)
        return;

    if (type == TRANSITION_VBLINDS) {
        int per;
        for (per = 0; ; per++) {
            int cs = per * period + front_prev;
            int cw = delta;
            if (cs >= w) break;
            if (cs + cw > w) cw = w - cs;
            fill_rect(x + cs, y, cw, h, color);
        }
    } else if (type == TRANSITION_HBLINDS) {
        int per;
        for (per = 0; ; per++) {
            int rs = per * period + front_prev;
            int rh = delta;
            if (rs >= h) break;
            if (rs + rh > h) rh = h - rs;
            fill_rect(x, y + rs, w, rh, color);
        }
    } else {
        /* Diagonal: single-pass sweep primitive; the per-row/per-band
         * cells are written with the bank tracked across the whole frame
         * (fill_rect per cell would cost thousands of bank selects). */
        int reverse = (type == TRANSITION_RDBLINDS);
        fill_diag_sweep(x, y, w, h, color,
                        front_prev, front_cur, period, reverse);
    }
}
