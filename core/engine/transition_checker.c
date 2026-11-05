/*
 * transition_checker.c — Checkered staggered wipe transition.
 *
 * Split from transition.c: blackens CHK_CELL square cells in a staggered
 * diagonal wave that keeps a checkerboard texture until the end.
 */
#include "render.h"
#include "transition_internal.h"

/* Checker cell size (px).  40 divides the 640x400 demo screen into an
 * exact 16x10 grid of square cells; non-divisible sizes fall back to a
 * clamped trailing edge so any rect stays valid. */
#define CHK_CELL  40

/* Advance the checkered staggered wipe by one step.
 * The rect is divided into CHK_CELL square cells indexed (i, j) with rank
 * r = i + j; cells of the same rank are the same checker color (r & 1).
 * Even-rank cells sweep to black during the first half of the timeline,
 * odd-rank cells during the second half, each in diagonal wave order:
 *   act_even(r) = 0.5 * r / R
 *   act_odd(r)  = 0.5 + 0.5 * r / R      (R = max rank)
 * A cell is painted 'color' on exactly the frame its activation step is
 * reached, so adjacent cells always differ until the end: the advancing
 * wave front keeps a classic checkerboard texture.  Every rank fires at
 * or before the final frame, so the screen is fully black when the
 * transition ends (the last odd rank fires one frame early when R is
 * even, which only means black completes slightly sooner). */
void transition_checker_wipe(int x, int y, int w, int h,
                             int step, int frames,
                             unsigned char color)
{
    int cols, rows, i, j, r;
    int last_col, last_row, max_rank;

    if (w < 1 || h < 1 || frames < 1)
        return;
    cols = w / CHK_CELL;
    rows = h / CHK_CELL;
    if (cols < 1 || rows < 1)
        return;
    max_rank = (cols - 1) + (rows - 1);

    for (j = 0; j < rows; j++) {
        for (i = 0; i < cols; i++) {
            int act;
            r = i + j;
            if (r & 1) /* odd rank: second half of the timeline */
                act = ((frames - 1) * (max_rank + r)) / (2 * max_rank);
            else       /* even rank: first half of the timeline */
                act = ((frames - 1) * r) / (2 * max_rank);
            if (act < 0) act = 0;
            if (act > frames - 1) act = frames - 1;
            if (act != step)
                continue;
            last_col = (i + 1 < cols) ? (i + 1) * CHK_CELL : w;
            last_row = (j + 1 < rows) ? (j + 1) * CHK_CELL : h;
            fill_rect(x + i * CHK_CELL, y + j * CHK_CELL,
                      last_col - i * CHK_CELL, last_row - j * CHK_CELL,
                      color);
        }
    }
}
